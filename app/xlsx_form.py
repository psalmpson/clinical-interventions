"""Fill the official NHF Clinical Intervention Form workbook with one record.

The template's structure is left untouched: we edit the sheet XML in place
(no re-save through a spreadsheet library) so the 66 underline shapes, merged
cells, borders, column widths and print setup survive exactly. Answers are
written in blue "pen" ink next to each printed label.
"""
import base64
import io
import re
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree
from PIL import Image

TEMPLATE = Path(__file__).parent / "templates" / "clinical_intervention_form.xlsx"

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
INK = "FF123A9E"
TICK = "\u2713"
BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")

# printed label cell -> answer key in the saved record
FIELD_CELLS = {"B9": "drug_name", "B10": "disease"}
CHECK_CELLS = {
    "B13": "drp_adr_toxicity", "B14": "drp_adr_allergic", "B15": "drp_adr_side",
    "B17": "drp_choice_needed", "B18": "drp_choice_inappropriate", "B19": "drp_choice_duplication",
    "B20": "drp_choice_cost", "B21": "drp_choice_contra", "B22": "drp_choice_form",
    "B24": "drp_dose_low", "B25": "drp_dose_high", "B26": "drp_dose_duration",
    "B28": "drp_use_wrongdose", "B29": "drp_use_wrongdrug", "B30": "drp_use_notgiven",
    "B31": "drp_use_unavailable", "B32": "drp_use_storage", "B33": "drp_use_route",
    "B35": "drp_int_drug", "B36": "drp_int_disease", "B37": "drp_int_food",
    "B39": "drp_pt_instructions", "B40": "drp_pt_misuse", "B41": "drp_pt_nonadherence",
    "E10": "act_tdm", "E12": "act_prescriber", "E13": "act_pharmacy",
    "E15": "act_dmp", "E16": "act_regimen", "E17": "act_contacted",
    "E19": "act_edu_disease", "E20": "act_edu_adherence", "E21": "act_edu_counsel", "E22": "act_edu_other",
    "E24": "act_train_device", "E25": "act_train_other",
    "E27": "act_life_diet", "E28": "act_life_exercise", "E29": "act_life_smoking", "E30": "act_life_alcohol",
    "H9": "rec_stop", "H10": "rec_change_med", "H11": "rec_add_rx", "H12": "rec_add_otc",
    "H13": "rec_change_dose", "H14": "rec_change_form", "H15": "rec_change_interval",
    "H16": "rec_tdm", "H17": "rec_education",
    "H20": "res_acc_prescriber", "H21": "res_acc_team", "H22": "res_acc_patient",
    "H23": "res_not_accepted", "H24": "res_unknown", "H25": "res_other",
    "H32": "out_efficacy", "H33": "out_safety", "H34": "out_adherence",
    "H35": "out_save_inst", "H36": "out_save_pt",
}
HEADER_CELLS = {"pharmacy": "B7", "ward": "C7", "date": "D7", "mrn": "E7", "initials": "F7",
                "age": "G7", "gender": "H7", "wthgt": "I7", "labs": "J7"}
SPECIFICS_CELLS = [f"E{r}" for r in range(33, 42)]   # nine merged lines E33:G33 ... E41:G41
SPECIFICS_CHARS_PER_LINE = 62


def q(tag: str) -> str:
    return f"{{{MAIN}}}{tag}"


def mdy(s: Any) -> str:
    try:
        y, m, d = str(s).split("-")
        return f"{m}/{d}/{y}"
    except ValueError:
        return str(s or "")


class Workbook:
    def __init__(self):
        with zipfile.ZipFile(TEMPLATE) as z:
            self.order = z.namelist()
            self.files = {n: z.read(n) for n in self.order}
            self.info = {n: z.getinfo(n) for n in self.order}
        self.sheet = etree.fromstring(self.files["xl/worksheets/sheet1.xml"])
        self.styles = etree.fromstring(self.files["xl/styles.xml"])
        sst = etree.fromstring(self.files["xl/sharedStrings.xml"])
        self.strings = ["".join(si.itertext()) for si in sst.findall(q("si"))]
        self.cells = {c.get("r"): c for c in self.sheet.iter(q("c"))}
        # anchor cell of every merged range: only these can safely use shrink-to-fit
        self.merged = {m.get("ref").split(":")[0] for m in self.sheet.iter(q("mergeCell"))}
        self.fonts = self.styles.find(q("fonts"))
        self.xfs = self.styles.find(q("cellXfs"))
        self._shrink: Dict[int, int] = {}

    # ---- styles -------------------------------------------------------------
    def shrink_style(self, s: int) -> int:
        """Clone cell style s with shrink-to-fit so long answers scale to the cell."""
        if s in self._shrink:
            return self._shrink[s]
        xf = etree.fromstring(etree.tostring(self.xfs[s]))
        xf.set("applyAlignment", "1")
        al = xf.find(q("alignment"))
        if al is None:
            al = etree.SubElement(xf, q("alignment"))
        al.attrib.pop("wrapText", None)
        al.set("shrinkToFit", "1")
        self.xfs.append(xf)
        self.xfs.set("count", str(len(self.xfs)))
        self._shrink[s] = len(self.xfs) - 1
        return self._shrink[s]

    def font_rpr(self, cell) -> etree._Element:
        """Run properties matching the cell's own font (so the printed label looks unchanged)."""
        xf = self.xfs[int(cell.get("s", "0"))]
        font = self.fonts[int(xf.get("fontId", "0"))]
        rpr = etree.Element(q("rPr"))
        for ch in font:
            tag = etree.QName(ch).localname
            new = etree.SubElement(rpr, q("rFont" if tag == "name" else tag))
            for k, v in ch.attrib.items():
                new.set(k, v)
        return rpr

    @staticmethod
    def ink_rpr(size: float, bold: bool = False) -> etree._Element:
        rpr = etree.Element(q("rPr"))
        if bold:
            etree.SubElement(rpr, q("b"))
        etree.SubElement(rpr, q("sz")).set("val", str(size))
        etree.SubElement(rpr, q("color")).set("rgb", INK)
        etree.SubElement(rpr, q("rFont")).set("val", "Calibri")
        etree.SubElement(rpr, q("family")).set("val", "2")
        return rpr

    # ---- cell writing -------------------------------------------------------
    def label_text(self, cell) -> str:
        return self.strings[int(cell.find(q("v")).text)] if cell.get("t") == "s" else ""

    def write(self, ref: str, runs: List[Tuple[str, etree._Element]], shrink: bool = True):
        cell = self.cells[ref]
        for ch in list(cell):
            cell.remove(ch)
        cell.set("t", "inlineStr")
        if shrink:
            cell.set("s", str(self.shrink_style(int(cell.get("s", "0")))))
        is_ = etree.SubElement(cell, q("is"))
        for text, rpr in runs:
            r = etree.SubElement(is_, q("r"))
            r.append(rpr)
            t = etree.SubElement(r, q("t"))
            t.text = BAD_XML.sub("", text)
            t.set(f"{{{XML_NS}}}space", "preserve")

    def append_to_label(self, ref: str, suffix: str):
        cell = self.cells[ref]
        label = self.label_text(cell)
        # merged label cells shrink to fit; single cells let text run on along the line like the label does
        self.write(ref, [(label, self.font_rpr(cell)), (suffix, self.ink_rpr(self._size(cell)))],
                   shrink=ref in self.merged)

    def _size(self, cell) -> float:
        xf = self.xfs[int(cell.get("s", "0"))]
        sz = self.fonts[int(xf.get("fontId", "0"))].find(q("sz"))
        return float(sz.get("val")) if sz is not None else 8.0

    # ---- output -------------------------------------------------------------
    def save(self, extra: Dict[str, bytes]) -> bytes:
        # numbers typed as text (MRN, age, hours) shouldn't show Excel's green warning triangle
        drawing = self.sheet.find(q("drawing"))
        ign = etree.Element(q("ignoredErrors"))
        etree.SubElement(ign, q("ignoredError")).attrib.update({"sqref": "A1:Q63", "numberStoredAsText": "1"})
        drawing.addprevious(ign)
        self.files["xl/worksheets/sheet1.xml"] = etree.tostring(
            self.sheet, xml_declaration=True, encoding="UTF-8", standalone=True)
        self.files["xl/styles.xml"] = etree.tostring(
            self.styles, xml_declaration=True, encoding="UTF-8", standalone=True)
        self.files.update(extra)
        names = self.order + [n for n in extra if n not in self.order]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, self.files[n])
        return out.getvalue()


# ---- signatures -------------------------------------------------------------
COL_I_PX, COL_J_PX = 75, 118          # widths of columns I and J in pixels
EMU = 9525


def signature_image(data_url: Any, box_w: int, box_h: int) -> Optional[Tuple[bytes, int, int]]:
    if not data_url or "," not in str(data_url):
        return None
    try:
        im = Image.open(io.BytesIO(base64.b64decode(str(data_url).split(",", 1)[1]))).convert("RGBA")
        bbox = im.getchannel("A").getbbox()
        if not bbox:
            return None
        pad = 6
        im = im.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                      min(bbox[2] + pad, im.width), min(bbox[3] + pad, im.height)))
        scale = min(box_w / im.width, box_h / im.height)
        w, h = max(int(im.width * scale), 1), max(int(im.height * scale), 1)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue(), w, h
    except Exception:
        return None


ROW_PX = {41: 51, 42: 37, 43: 24}      # rows 42-44 (0-based 41-43): fixed heights in pixels


def pic_anchor(rid: str, pid: int, name: str, row: int, off: int, w: int, h: int) -> str:
    """Two-cell anchor (like the template's own line shapes) so every viewer places it identically."""
    x1 = min(max((COL_I_PX + COL_J_PX - w) // 2, 2), COL_I_PX - 2)
    x2 = x1 + w - COL_I_PX                      # ends inside column J
    row2, off2 = row, off + h
    while off2 > ROW_PX[row2] and row2 + 1 in ROW_PX:
        off2 -= ROW_PX[row2]
        row2 += 1
    off2 = min(off2, ROW_PX[row2])
    return (
        '<xdr:twoCellAnchor editAs="oneCell">'
        f'<xdr:from><xdr:col>8</xdr:col><xdr:colOff>{x1 * EMU}</xdr:colOff><xdr:row>{row}</xdr:row><xdr:rowOff>{off * EMU}</xdr:rowOff></xdr:from>'
        f'<xdr:to><xdr:col>9</xdr:col><xdr:colOff>{max(x2, 1) * EMU}</xdr:colOff><xdr:row>{row2}</xdr:row><xdr:rowOff>{off2 * EMU}</xdr:rowOff></xdr:to>'
        f'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{pid}" name="{name}"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
        f'<xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="{rid}"/>'
        '<a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
        '<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
        '</xdr:pic><xdr:clientData/></xdr:twoCellAnchor>'
    )


# ---- main -------------------------------------------------------------------
def fill_xlsx(record: Dict[str, Any]) -> bytes:
    data = record.get("data") or {}
    fields: Dict[str, Any] = data.get("fields") or {}
    checks: Dict[str, Any] = data.get("checks") or {}
    wb = Workbook()

    def s(key: str) -> str:
        return str(fields.get(key) or "").strip()

    # header strip (row 7)
    fh = dict(fields)
    fh["wthgt"] = " / ".join(p for p in (s("weight"), s("height")) if p)
    fh["date"] = mdy(s("date"))
    for key, ref in HEADER_CELLS.items():
        val = str(fh.get(key) or "").replace("\n", ", ").strip()
        if val:
            wb.write(ref, [(val, wb.ink_rpr(9))])

    # drug / disease: answer follows the printed label
    for ref, key in FIELD_CELLS.items():
        if s(key):
            wb.append_to_label(ref, "  " + s(key).replace("\n", " "))

    # tick boxes with optional note
    for ref, key in CHECK_CELLS.items():
        entry = checks.get(key)
        if entry:
            note = str(entry.get("note") or "").replace("\n", " ").strip()
            wb.append_to_label(ref, f"  {TICK}" + (f" {note}" if note else ""))

    # intervention specifics: wrapped over the nine lines of the box
    text = s("specifics")
    if text:
        lines: List[str] = []
        for para in text.replace("\r", "").split("\n"):
            lines += textwrap.wrap(para, SPECIFICS_CHARS_PER_LINE, break_long_words=True) or [""]
        n = len(SPECIFICS_CELLS)
        if len(lines) > n:
            lines = lines[:n - 1] + [" ".join(lines[n - 1:])]
        for ref, line in zip(SPECIFICS_CELLS, lines):
            if line:
                wb.write(ref, [(line, wb.ink_rpr(8))])

    # actual time involved
    if s("hours"):
        wb.write("H27", [(s("hours"), wb.ink_rpr(12))], shrink=False)

    # sign-off (names overflow to the right along the line, so no shrink)
    if s("pharmacist"):
        wb.write("C42", [(s("pharmacist"), wb.ink_rpr(11))], shrink=False)
    if s("team_leader"):
        wb.write("B44", [(s("team_leader"), wb.ink_rpr(11))], shrink=False)
    if s("signed_date"):
        wb.write("C46", [(mdy(s("signed_date")), wb.ink_rpr(11))], shrink=False)

    # signature images
    extra: Dict[str, bytes] = {}
    anchors, rels = "", ""
    for i, (key, row_idx, row_off, box_h) in enumerate(
            [("sig_pharmacist", 41, 3, 44), ("sig_leader", 42, 17, 42)], start=1):
        img = signature_image(fields.get(key), 185, box_h)
        if img:
            png, w, h = img
            extra[f"xl/media/signature{i}.png"] = png
            anchors += pic_anchor(f"rId{i}", 2000 + i, f"Signature {i}", row_idx, row_off, w, h)
            rels += (f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                     f'relationships/image" Target="../media/signature{i}.png"/>')
    if anchors:
        d = wb.files["xl/drawings/drawing1.xml"].decode("utf8")
        wb.files["xl/drawings/drawing1.xml"] = d.replace("</xdr:wsDr>", anchors + "</xdr:wsDr>").encode("utf8")
        extra["xl/drawings/_rels/drawing1.xml.rels"] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{REL_NS}">{rels}</Relationships>'
        ).encode("utf8")
        ct = wb.files["[Content_Types].xml"].decode("utf8")
        if 'Extension="png"' not in ct:
            ct = ct.replace("<Override", '<Default Extension="png" ContentType="image/png"/><Override', 1)
        wb.files["[Content_Types].xml"] = ct.encode("utf8")

    return wb.save(extra)
