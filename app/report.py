"""Monthly report: counts for the two tables on the official
'Clinical Intervention Monthly Report' workbook, and the workbook fill.

Each row is (cell, kind, label, arg):
  item  - a count of records with that tick box; arg = answer key
  head  - a printed sub-heading inside a group (always 0 in the workbook)
  group / total - a subtotal; arg = list of cells it adds up
"""
import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from lxml import etree

TEMPLATE = Path(__file__).parent / "templates" / "clinical_intervention_monthly_report.xlsx"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _rng(col: str, a: int, b: int) -> List[str]:
    return [f"{col}{i}" for i in range(a, b + 1)]


T1 = [
    ("B12", "total", "THE PROBLEM (DRP)", ["B13", "B17", "B24", "B30", "B37", "B41"]),
    ("B13", "group", "ADVERSE DRUG REACTION", _rng("B", 14, 16)),
    ("B14", "item", "A) Toxicity", "drp_adr_toxicity"),
    ("B15", "item", "B) Allergic reaction", "drp_adr_allergic"),
    ("B16", "item", "C) Side Effect", "drp_adr_side"),
    ("B17", "group", "DRUG CHOICE", _rng("B", 18, 23)),
    ("B18", "item", "A) Drug needed for patient but not prescribed", "drp_choice_needed"),
    ("B19", "item", "B) Inappropriate drug according to guidelines", "drp_choice_inappropriate"),
    ("B20", "item", "C) Drug duplication", "drp_choice_duplication"),
    ("B21", "item", "D) Cost of therapy", "drp_choice_cost"),
    ("B22", "item", "E) Contraindication", "drp_choice_contra"),
    ("B23", "item", "F) Inappropriate Drug Choice", "drp_choice_form"),
    ("B24", "group", "DOSING", _rng("B", 25, 29)),
    ("B25", "item", "A) Dose too low/ frequency inadequate", "drp_dose_low"),
    ("B26", "item", "B) Dose too high/ frequency too often", "drp_dose_high"),
    ("B27", "item", "C) Duration inappropriate", "drp_dose_duration"),
    ("B28", "item", "E) Missing Frequency", "drp_dose_missing_freq"),
    ("B29", "item", "F) Missing Duration", "drp_dose_missing_duration"),
    ("B30", "group", "DRUG USE", _rng("B", 31, 36)),
    ("B31", "item", "A) Wrong Dose Administered", "drp_use_wrongdose"),
    ("B32", "item", "B) Wrong drug administered", "drp_use_wrongdrug"),
    ("B33", "item", "C) Drug not given", "drp_use_notgiven"),
    ("B34", "item", "D) Drug not available", "drp_use_unavailable"),
    ("B35", "item", "E) Incorrect storage", "drp_use_storage"),
    ("B36", "item", "F) Incorrect route of administration", "drp_use_route"),
    ("B37", "group", "INTERACTION", _rng("B", 38, 40)),
    ("B38", "item", "Drug \u2013food interaction", "drp_int_food"),
    ("B39", "item", "Drug- Disease", "drp_int_disease"),
    ("B40", "item", "Drug-Drug", "drp_int_drug"),
    ("B41", "group", "PATIENT/PROVIDER", _rng("B", 42, 44)),
    ("B42", "item", "A) Patient didn't follow instructions", "drp_pt_instructions"),
    ("B43", "item", "B) Patient misuse (over-use/under-use)", "drp_pt_misuse"),
    ("B44", "item", "C) Non-Adherence", "drp_pt_nonadherence"),
    ("B45", "total", "INTERVENTION", ["B46", "B48", "B51"]),
    ("B46", "group", "DRUG", ["B47"]),
    ("B47", "item", "A) Therapeutic drug monitoring", "act_tdm"),
    ("B48", "group", "PRESCRIBER/HEALTH CARE PROFESSIONALS", ["B49", "B50"]),
    ("B49", "item", "A) Prescriber contacted", "act_prescriber"),
    ("B50", "item", "B) Pharmacy Contacted", "act_pharmacy"),
    ("B51", "group", "PATIENT/CAREGIVER", _rng("B", 52, 67)),
    ("B52", "item", "A) Disease management program", "act_dmp"),
    ("B53", "item", "B) Drug regimen review", "act_regimen"),
    ("B54", "item", "C) Patient contacted", "act_contacted"),
    ("B55", "head", "D). Patient Education (patient/caregiver) related to", None),
    ("B56", "item", "i) Disease", "act_edu_disease"),
    ("B57", "item", "ii) Medication adherence", "act_edu_adherence"),
    ("B58", "item", "iii) Counseling", "act_edu_counsel"),
    ("B59", "item", "iv) Other", "act_edu_other"),
    ("B60", "head", "E).Patient /Caregiver Training", None),
    ("B61", "item", "i ) Adherence device", "act_train_device"),
    ("B62", "item", "ii) Other", "act_train_other"),
    ("B63", "head", "F. Life Style Changes", None),
    ("B64", "item", "i) Diet", "act_life_diet"),
    ("B65", "item", "ii) Exercise", "act_life_exercise"),
    ("B66", "item", "iii) Smoking cessation", "act_life_smoking"),
    ("B67", "item", "iv) Alcohol moderation", "act_life_alcohol"),
]

T2 = [
    ("E10", "total", "Recommendations (Total)", _rng("E", 12, 22)),
    ("E12", "item", "A) Discontinue therapy", "rec_stop"),
    ("E13", "item", "B) Change medication", "rec_change_med"),
    ("E14", "item", "C) Add medication(Rx)", "rec_add_rx"),
    ("E15", "item", "D) Add medication (OTC)", "rec_add_otc"),
    ("E16", "item", "E) Change dose", "rec_change_dose"),
    ("E17", "item", "F) Change dosage form", "rec_change_form"),
    ("E18", "item", "G) Change dosing interval", "rec_change_interval"),
    ("E19", "item", "H) Therapeutic drug monitoring", "rec_tdm"),
    ("E20", "item", "I) Patient education/counselling", "rec_education"),
    ("E21", "item", "J) Add Frequency", "rec_add_frequency"),
    ("E22", "item", "K) Add duration", "rec_add_duration"),
    ("E23", "group", "RESULTS OF RECOMMENDATION", _rng("E", 24, 29)),
    ("E24", "item", "Accepted by prescriber", "res_acc_prescriber"),
    ("E25", "item", "Accepted by consult team", "res_acc_team"),
    ("E26", "item", "Accepted by Patient/caregiver", "res_acc_patient"),
    ("E27", "item", "Not accepted", "res_not_accepted"),
    ("E28", "item", "Unknown", "res_unknown"),
    ("E29", "item", "Other", "res_other"),
    ("E31", "total", "ACTUAL TIME INVOLVED (Min)", ["E32"]),
    ("E32", "item", "Time in Minutes", "__minutes__"),
    ("E33", "group", "EXPECTED OUTCOME", _rng("E", 34, 38)),
    ("E34", "item", "Improved efficacy", "out_efficacy"),
    ("E35", "item", "Improves safety", "out_safety"),
    ("E36", "item", "Improved adherence", "out_adherence"),
    ("E37", "item", "Cost Saving (Hospital)", "out_save_inst"),
    ("E38", "item", "Cost Saving (patient)", "out_save_pt"),
]

# The template's own subtotal formulas that were wrong (see compute notes in the README).
FORMULA_FIX = {"B24": "SUM(B25:B29)", "E23": "SUM(E24:E29)", "E33": "SUM(E34:E38)"}
SPEC = {ref: (kind, label, arg) for ref, kind, label, arg in T1 + T2}


def compute(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Value for every cell of both tables."""
    counts: Dict[str, int] = {}
    minutes = 0.0
    for r in records:
        data = r.get("data") or {}
        for key, entry in (data.get("checks") or {}).items():
            if entry:
                counts[key] = counts.get(key, 0) + 1
        try:
            minutes += float(str((data.get("fields") or {}).get("hours") or 0).replace(",", ".")) * 60
        except ValueError:
            pass
    counts["__minutes__"] = int(round(minutes))

    values: Dict[str, int] = {}

    def val(ref: str) -> int:
        if ref not in values:
            kind, _, arg = SPEC[ref]
            if kind == "item":
                values[ref] = counts.get(arg, 0)
            elif kind == "head":
                values[ref] = 0
            else:
                values[ref] = sum(val(c) for c in arg)
        return values[ref]

    for ref in SPEC:
        val(ref)
    return values


def ui_tables(values: Dict[str, int]) -> Dict[str, List[Dict[str, Any]]]:
    def rows(spec):
        return [{"ref": ref, "kind": kind, "label": label,
                 "value": None if kind == "head" else values[ref]} for ref, kind, label, _ in spec]
    return {"t1": rows(T1), "t2": rows(T2)}


# ---- Excel fill -----------------------------------------------------------------
def q(tag: str) -> str:
    return f"{{{MAIN}}}{tag}"


def _serial(d: date) -> int:
    return (d - date(1899, 12, 30)).days


def _set_number(cell, value: int, formula: Optional[str] = None, keep_formula: bool = True):
    f = cell.find(q("f")) if keep_formula else None
    for ch in list(cell):
        if ch is not f:
            cell.remove(ch)
    if f is not None and formula:
        f.text = formula
    cell.set("t", "n")
    etree.SubElement(cell, q("v")).text = str(int(value))


def _set_text(cell, text: str):
    for ch in list(cell):
        cell.remove(ch)
    if not text:
        cell.attrib.pop("t", None)
        return
    cell.set("t", "inlineStr")
    is_ = etree.SubElement(cell, q("is"))
    t = etree.SubElement(is_, q("t"))
    t.text = re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", "", text)
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def fill_report_xlsx(values: Dict[str, int], month: str, pharmacy: str, submitted_by: str) -> bytes:
    with zipfile.ZipFile(TEMPLATE) as z:
        order = z.namelist()
        files = {n: z.read(n) for n in order}

    sheet = etree.fromstring(files["xl/worksheets/sheet1.xml"])
    cells = {c.get("r"): c for c in sheet.iter(q("c")) if int(re.sub(r"\D", "", c.get("r"))) <= 80}

    for ref, (kind, _, _) in SPEC.items():
        cell = cells[ref]
        if kind in ("item", "head"):
            _set_number(cell, values[ref])
        else:
            _set_number(cell, values[ref], FORMULA_FIX.get(ref))

    # header block: these used to be links to another workbook
    _set_text(cells["D5"], pharmacy or "All pharmacies")
    _set_text(cells["D6"], submitted_by)
    _set_number(cells["D7"], _serial(datetime.now().date()), keep_formula=False)
    if month and month != "all":
        y, m = month.split("-")
        _set_number(cells["D8"], _serial(date(int(y), int(m), 1)), keep_formula=False)
    else:
        _set_text(cells["D8"], "All months")

    files["xl/worksheets/sheet1.xml"] = etree.tostring(
        sheet, xml_declaration=True, encoding="UTF-8", standalone=True)

    # drop the external-link part so Excel doesn't show the "update links" warning
    wb = files["xl/workbook.xml"].decode("utf8")
    wb = re.sub(r"<externalReferences>.*?</externalReferences>", "", wb, flags=re.S)
    wb = wb.replace("<calcPr ", '<calcPr fullCalcOnLoad="1" ', 1)
    files["xl/workbook.xml"] = wb.encode("utf8")
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf8")
    rels = re.sub(r'<Relationship [^>]*relationships/externalLink"[^>]*/>', "", rels)
    files["xl/_rels/workbook.xml.rels"] = rels.encode("utf8")
    ct = files["[Content_Types].xml"].decode("utf8")
    ct = re.sub(r'<Override [^>]*externalLink[^>]*/>', "", ct)
    files["[Content_Types].xml"] = ct.encode("utf8")
    for n in [n for n in order if n.startswith("xl/externalLinks/")]:
        order.remove(n)
        del files[n]

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n])
    return out.getvalue()
