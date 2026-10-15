"""Render one intervention record onto a recreation of the paper
NHF Pharmacy Services Delivery Clinical Intervention Form (Rev. 4.0)."""
import base64
import io
from typing import Any, Dict, List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = letter
MX = 29.0
BODY_W = PAGE_W - 2 * MX
COL_FRAC = (0.333, 0.374, 0.293)
COL_W = [BODY_W * f for f in COL_FRAC]
COL_X = [MX, MX + COL_W[0], MX + COL_W[0] + COL_W[1]]

INK = (0.07, 0.20, 0.55)      # "pen" colour for filled-in data
BLACK = (0, 0, 0)
N_ROWS = 34                   # rows in the tallest (left) column
BODY_BOTTOM = 160.0

# ---- layout of the paper form -------------------------------------------
LEFT = [
    ("hdr", "A. DRUG AND/OR DISEASE INVOLVED"),
    ("field", "Drug Name", "drug_name"),
    ("field", "Disease", "disease"),
    ("hdr", "B. D.R.P. CLASSIFICATION"),
    ("sub", "1. Adverse Drug Reaction"),
    ("chk", "A) Toxicity", "drp_adr_toxicity"),
    ("chk", "B) Allergic reaction", "drp_adr_allergic"),
    ("chk", "C) Side effect", "drp_adr_side"),
    ("sub", "2. Drug Choice"),
    ("chk", "A) Drug needed for patient but not prescribed", "drp_choice_needed"),
    ("chk", "B) Inappropriate drug according to guidelines", "drp_choice_inappropriate"),
    ("chk", "C) Drug duplication", "drp_choice_duplication"),
    ("chk", "D) Cost of therapy", "drp_choice_cost"),
    ("chk", "E) Contraindication", "drp_choice_contra"),
    ("chk", "F) Inappropriate dosage form", "drp_choice_form"),
    ("sub", "3. Dosing"),
    ("chk", "A) Dose too low/ frequency inadequate", "drp_dose_low"),
    ("chk", "B) Dose too high/ frequency too often", "drp_dose_high"),
    ("chk", "C) Duration inappropriate", "drp_dose_duration"),
    ("sub", "4. Drug Use"),
    ("chk", "A) Wrong Dose Administered", "drp_use_wrongdose"),
    ("chk", "B) Wrong drug administered", "drp_use_wrongdrug"),
    ("chk", "C) Drug not given", "drp_use_notgiven"),
    ("chk", "D) Drug not available", "drp_use_unavailable"),
    ("chk", "E) Incorrect storage", "drp_use_storage"),
    ("chk", "F) Incorrect route of administration", "drp_use_route"),
    ("sub", "5. Interaction"),
    ("chk", "A) Drug-Drug", "drp_int_drug"),
    ("chk", "B) Drug-Disease", "drp_int_disease"),
    ("chk", "C) Drug-Food", "drp_int_food"),
    ("sub", "6. Patient"),
    ("chk", "A) Patient didn't follow instructions", "drp_pt_instructions"),
    ("chk", "B) Patient misuse (over-use/under-use)", "drp_pt_misuse"),
    ("chk", "C) Non-adherence", "drp_pt_nonadherence"),
]

MIDDLE = [
    ("hdr", "C. INTERVENTIONS"),
    ("sub", "1. Drug"),
    ("chk", "A) Therapeutic drug monitoring", "act_tdm"),
    ("sub", "2. Prescriber/Health Care Professional"),
    ("chk", "A) Prescriber contacted", "act_prescriber"),
    ("chk", "B) Pharmacy Contacted", "act_pharmacy"),
    ("sub", "3. Patient /Caregiver"),
    ("chk", "A) Disease management programme", "act_dmp"),
    ("chk", "B) Drug regimen review", "act_regimen"),
    ("chk", "C) Patient contacted", "act_contacted"),
    ("plain", "D. Patient Education (patient/caregiver) related to:"),
    ("chk", "i) Disease", "act_edu_disease"),
    ("chk", "ii) Medication adherence", "act_edu_adherence"),
    ("chk", "iii) Counseling", "act_edu_counsel"),
    ("chk", "iv) Other", "act_edu_other"),
    ("plain", "E. Patient /Caregiver Training"),
    ("chk", "i) Adherence device", "act_train_device"),
    ("chk", "ii) Other", "act_train_other"),
    ("plain", "F. Life Style Changes"),
    ("chk", "i) Diet", "act_life_diet"),
    ("chk", "ii) Exercise", "act_life_exercise"),
    ("chk", "iii) Smoking cessation", "act_life_smoking"),
    ("chk", "iv) Alcohol moderation", "act_life_alcohol"),
    ("bar", "Complete the INTERVENTION SPECIFICS SECTION"),
    ("hdr", "D. INTERVENTIONS SPECIFICS"),
    ("box", None, "specifics"),
]

RIGHT = [
    ("hdr", "E. RECOMMENDATIONS"),
    ("chk", "A) Discontinue therapy", "rec_stop"),
    ("chk", "B) Change medication", "rec_change_med"),
    ("chk", "C) Add medication (Rx)", "rec_add_rx"),
    ("chk", "D) Add medication (OTC)", "rec_add_otc"),
    ("chk", "E) Change dose", "rec_change_dose"),
    ("chk", "F) Change dosage form", "rec_change_form"),
    ("chk", "G) Change dosing interval", "rec_change_interval"),
    ("chk", "H) Therapeutic drug monitoring", "rec_tdm"),
    ("chk", "I) Patient education/counseling", "rec_education"),
    ("hdr", "F. RESULTS OF RECOMMENDATION"),
    ("note", "CHECK ALL that apply."),
    ("chk", "A) Accepted by prescriber", "res_acc_prescriber"),
    ("chk", "B) Accepted by consult team", "res_acc_team"),
    ("chk", "C) Accepted by patient/caregiver", "res_acc_patient"),
    ("chk", "D) Not accepted by", "res_not_accepted"),
    ("chk", "E) Unknown", "res_unknown"),
    ("chk", "F) Other", "res_other"),
    ("hdr", "G. ACTUAL TIME INVOLVED (Hrs)"),
    ("box", 5, "hours"),
    ("hdr", "H. EXPECTED OUTCOME"),
    ("chk", "A) Improved efficacy", "out_efficacy"),
    ("chk", "B) Improved safety", "out_safety"),
    ("chk", "C) Improved adherence", "out_adherence"),
    ("chk", "D) Cost saving (institution)", "out_save_inst"),
    ("chk", "E) Cost saving (patient)", "out_save_pt"),
]

HEADER_COLS = [  # label, field key(s), width as fraction of body
    ("PHARMACY", "pharmacy", 84.6),
    ("WARD", "ward", 39.5),
    ("DATE", "date", 60.6),
    ("PHARMACY MRN", "mrn", 98.7),
    ("PATIENT INITIALS", "initials", 54.3),
    ("AGE", "age", 53.6),
    ("GENDER", "gender", 40.2),
    ("WT / HGT", "wthgt", 47.9),
    ("OTHER (lab readings)", "labs", 74.7),
]


# ---- helpers ----------------------------------------------------------------
def clean(s: Any) -> str:
    return str(s or "").replace("\r", "").encode("cp1252", "replace").decode("cp1252")


def mdy(s: str) -> str:
    try:
        y, m, d = str(s).split("-")
        return f"{m}/{d}/{y}"
    except ValueError:
        return clean(s)


def fit(c, text, x, y, maxw, font="Helvetica", size=6.6, min_size=4.6) -> bool:
    """Draw text on one line, shrinking then truncating. Returns True if truncated."""
    text = clean(text).replace("\n", " ")
    s = size
    while s > min_size and stringWidth(text, font, s) > maxw:
        s -= 0.2
    truncated = False
    if stringWidth(text, font, s) > maxw:
        while text and stringWidth(text + "...", font, s) > maxw:
            text = text[:-1]
        text += "..."
        truncated = True
    c.setFont(font, s)
    c.drawString(x, y, text)
    return truncated


def tick(c, x, y):
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(1.3)
    p = c.beginPath()
    p.moveTo(x, y + 3.2)
    p.lineTo(x + 2.4, y + 0.4)
    p.lineTo(x + 7, y + 7)
    c.drawPath(p, stroke=1, fill=0)


def draw_column(c, ov: List[Tuple[str, str]], idx: int, spec, top: float, row: float,
                fields: Dict[str, Any], checks: Dict[str, Any]):
    x, w = COL_X[idx], COL_W[idx]
    y = top
    used = 0
    section = ""
    for item in spec:
        kind = item[0]
        base = y - row + 4.4
        if kind == "hdr":
            c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.6)
            c.line(x, y, x + w, y); c.line(x, y - row, x + w, y - row)
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica-Bold", 6.9)
            c.drawString(x + 3, base, item[1])
            c.setLineWidth(0.5)
            c.line(x + 3, base - 1.3, x + 3 + stringWidth(item[1], "Helvetica-Bold", 6.9), base - 1.3)
            section = item[1]
            y -= row
        elif kind == "sub":
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica-Bold", 6.8)
            c.drawString(x + 3, base, item[1]); y -= row
        elif kind == "note":
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica-Bold", 6.2)
            c.drawString(x + 3, base, item[1]); y -= row
        elif kind == "bar":
            c.setFillColorRGB(0.82, 0.82, 0.82); c.rect(x, y - row, w, row, stroke=0, fill=1)
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica", 7.4)
            c.drawString(x + 3, base, item[1]); y -= row
        elif kind == "plain":
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica", 6.4)
            c.drawString(x + 3, base, item[1])
            lw = stringWidth(item[1], "Helvetica", 6.4)
            c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.4)
            if x + 3 + lw + 12 < x + w - 4:
                c.line(x + 3 + lw + 4, base - 1.5, x + w - 4, base - 1.5)
            y -= row
        elif kind == "field":
            label, key = item[1], item[2]
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica", 6.6)
            c.drawString(x + 3, base, label)
            lx0 = x + 3 + stringWidth(label, "Helvetica", 6.6) + 6
            c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.4)
            c.line(lx0, base - 1.5, x + w - 4, base - 1.5)
            val = clean(fields.get(key))
            if val:
                c.setFillColorRGB(*INK)
                if fit(c, val, lx0 + 2, base, x + w - 6 - lx0 - 2, size=8.2, min_size=5):
                    ov.append((f"{section}: {label}", val))
            y -= row
        elif kind == "chk":
            label, key = item[1], item[2]
            c.setFillColorRGB(*BLACK); c.setFont("Helvetica", 6.4)
            c.drawString(x + 3, base, label)
            lx0 = x + 3 + stringWidth(label, "Helvetica", 6.4) + 4
            lx1 = x + w - 4
            c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.4)
            c.line(lx0, base - 1.5, lx1, base - 1.5)
            entry = checks.get(key)
            if entry:
                tick(c, lx0 + 2, base - 1)
                note = clean(entry.get("note")).strip()
                if note:
                    c.setFillColorRGB(*INK)
                    if fit(c, note, lx0 + 12, base, lx1 - lx0 - 14, size=6.6, min_size=4.4):
                        ov.append((f"{section}: {label}", note))
            y -= row
        elif kind == "box":
            n = item[1] if item[1] else N_ROWS - used
            h = n * row
            c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.6)
            c.line(x, y - h, x + w, y - h)
            key = item[2]
            c.setFillColorRGB(*INK)
            if key == "hours":
                val = clean(fields.get("hours"))
                if val:
                    c.setFont("Helvetica", 15); c.drawString(x + 10, y - h / 2 - 5, val)
            else:
                text = clean(fields.get("specifics")).strip()
                if text:
                    size, lead = 6.8, 8.3
                    lines: List[str] = []
                    for para in text.split("\n"):
                        lines += simpleSplit(para, "Helvetica", size, w - 8) or [""]
                    maxl = int((h - 6) / lead)
                    c.setFont("Helvetica", size)
                    shown = lines[:maxl]
                    if len(lines) > maxl:
                        ov.append(("D. INTERVENTIONS SPECIFICS", text))
                        shown = lines[:maxl - 1] + ["... (continued on next page)"]
                    for i, ln in enumerate(shown):
                        c.drawString(x + 4, y - 9 - i * lead, ln)
            y -= h
            used += n - 1
        used += 1
    return y


def draw_signature(c, data_url, x0, x1, y_line):
    if not data_url or "," not in str(data_url):
        return
    try:
        img = ImageReader(io.BytesIO(base64.b64decode(str(data_url).split(",", 1)[1])))
        h = 24.0
        wd = h * 3.2
        c.drawImage(img, x0 + (x1 - x0 - wd) / 2, y_line + 1, width=wd, height=h, mask="auto")
    except Exception:
        pass


def continuation(c, ov, rec_label):
    def head():
        c.setFillColorRGB(*BLACK)
        c.setFont("Times-Bold", 11)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 44, "CLINICAL INTERVENTION FORM (continued)")
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 58, rec_label)
        return PAGE_H - 84
    c.showPage()
    y = head()
    for label, text in ov:
        lines = simpleSplit(clean(text), "Helvetica", 8.5, BODY_W - 6)
        if y - 14 - len(lines) * 11 < 50:
            c.showPage(); y = head()
        c.setFillColorRGB(*BLACK); c.setFont("Helvetica-Bold", 8)
        c.drawString(MX, y, label); y -= 11
        c.setFillColorRGB(*INK); c.setFont("Helvetica", 8.5)
        for ln in lines:
            if y < 50:
                c.showPage(); y = head(); c.setFillColorRGB(*INK); c.setFont("Helvetica", 8.5)
            c.drawString(MX + 6, y, ln); y -= 11
        y -= 8


# ---- main -------------------------------------------------------------------
def render_pdf(record: Dict[str, Any]) -> bytes:
    data = record.get("data") or {}
    fields: Dict[str, Any] = data.get("fields") or {}
    checks: Dict[str, Any] = data.get("checks") or {}
    ov: List[Tuple[str, str]] = []

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"Clinical Intervention {record.get('id', '')}")
    c.setAuthor("Clinical interventions")

    # Title
    c.setFillColorRGB(*BLACK)
    c.setFont("Times-Bold", 11.5)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 40, "NATIONAL HEALTH FUND PHARMACY SERVICES DELIVERY")
    c.drawCentredString(PAGE_W / 2, PAGE_H - 54, "CLINICAL INTERVENTION FORM")
    c.setFont("Helvetica", 6.3)
    c.drawString(MX, PAGE_H - 76,
                 "Directions: Complete one form for each clinical intervention. "
                 "Document all the relevant information in each of the eight (8) fields.")

    # Header strip
    top = PAGE_H - 88
    lab_h, val_h = 14.0, 25.0
    c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.9)
    x = MX
    fields_h = dict(fields)
    wt, ht = clean(fields.get("weight")), clean(fields.get("height"))
    fields_h["wthgt"] = " / ".join(p for p in (wt, ht) if p)
    for label, key, w in HEADER_COLS:
        c.setLineWidth(0.6)
        c.rect(x, top - lab_h - val_h, w, lab_h + val_h)
        c.line(x, top - lab_h, x + w, top - lab_h)
        c.setFillColorRGB(*BLACK)
        fit(c, label, x + 3, top - lab_h + 4.6, w - 5, "Helvetica-Bold", 6.4, 4.6)
        val = fields_h.get(key, "")
        if key == "date":
            val = mdy(val)
        val = clean(val)
        if val:
            c.setFillColorRGB(*INK)
            if key == "labs":
                size, lead = 5.8, 6.8
                lines: List[str] = []
                for para in val.split("\n"):
                    lines += simpleSplit(para, "Helvetica", size, w - 5) or [""]
                maxl = 3
                shown = lines[:maxl]
                if len(lines) > maxl:
                    ov.append(("OTHER (lab readings)", val)); shown[-1] = shown[-1][:-3] + "..." if len(shown[-1]) > 3 else "..."
                c.setFont("Helvetica", size)
                for i, ln in enumerate(shown):
                    c.drawString(x + 3, top - lab_h - 8 - i * lead, ln)
            else:
                if fit(c, val, x + 3, top - lab_h - val_h / 2 - 2.5, w - 6, size=8.5, min_size=4.8):
                    ov.append((label, val))
        x += w

    # Body
    body_top = top - lab_h - val_h
    row = (body_top - BODY_BOTTOM) / N_ROWS
    for i, spec in enumerate((LEFT, MIDDLE, RIGHT)):
        draw_column(c, ov, i, spec, body_top, row, fields, checks)
    c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.9)
    c.rect(MX, BODY_BOTTOM, BODY_W, body_top - BODY_BOTTOM)
    c.setLineWidth(0.7)
    for xv in COL_X[1:]:
        c.line(xv, body_top, xv, BODY_BOTTOM)

    # Sign-off
    c.setFillColorRGB(*BLACK); c.setStrokeColorRGB(*BLACK); c.setLineWidth(0.5)
    sx0, sx1 = 385.0, PAGE_W - MX
    l1, l2 = 126.0, 90.0
    c.setFont("Times-Roman", 7.5)
    c.drawString(MX, l1 + 3, "Intervention conducted by:")
    c.line(112, l1, 345, l1)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(228, l1 - 9, "Name of Pharmacist")
    c.line(sx0, l1, sx1, l1)
    c.drawCentredString((sx0 + sx1) / 2, l1 - 9, "Signature")
    c.line(MX + 2, l2, 345, l2)
    c.line(sx0, l2, sx1, l2)
    c.drawCentredString((sx0 + sx1) / 2, l2 - 9, "Signature")
    c.setFont("Times-Roman", 9)
    c.drawCentredString(190, l2 - 10, "NAME")
    c.drawCentredString(190, l2 - 20, "TEAM LEADER/CHIEF PHARMACIST")
    c.setFont("Times-Roman", 7.5)
    c.drawString(MX, 52, "Date:")
    c.line(58, 50, 190, 50)
    c.setFont("Times-Roman", 9)
    c.drawCentredString(124, 40, "mm/dd/yyyy")
    c.setFont("Times-Roman", 7)
    c.drawString(MX, 20, "Date Issued: May 2018")
    c.drawCentredString(PAGE_W / 2, 20, "Revision #: 4.0")
    c.drawRightString(PAGE_W - MX, 20, "Revision Date:  January 14, 2021")

    c.setFillColorRGB(*INK)
    if fields.get("pharmacist"):
        fit(c, fields["pharmacist"], 116, l1 + 3, 225, size=9, min_size=5)
    if fields.get("team_leader"):
        fit(c, fields["team_leader"], MX + 6, l2 + 3, 310, size=9, min_size=5)
    if fields.get("signed_date"):
        c.setFont("Helvetica", 9); c.drawString(62, 52, mdy(fields["signed_date"]))
    draw_signature(c, fields.get("sig_pharmacist"), sx0, sx1, l1)
    draw_signature(c, fields.get("sig_leader"), sx0, sx1, l2)

    if ov:
        label = f"Record #{record.get('id', '')}  |  {clean(fields.get('initials'))}  |  {mdy(fields.get('date', ''))}"
        continuation(c, ov, label)

    c.save()
    return buf.getvalue()
