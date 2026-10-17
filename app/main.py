"""Clinical intervention records: a small FastAPI + SQLite service.

Each intervention is stored as one row. The full form is kept as JSON in `data`;
a few columns are copied out so the table is easy to query or export directly.
"""
import json
import re
from contextlib import closing
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, report
from .admin import require_admin, router as admin_router
from .pdf_form import render_pdf
from .xlsx_form import fill_xlsx

STATIC_DIR = Path(__file__).parent / "static"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

db.init()


class Payload(BaseModel):
    data: Dict[str, Any]


app = FastAPI(title="Clinical interventions", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(admin_router)


@app.middleware("http")
async def no_cache(request, call_next):
    """Never let browsers or proxies (e.g. Cloudflare) store responses: records are patient-related."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def safe(v: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", str(v or ""))


def get_record(item_id: int) -> Dict[str, Any]:
    with closing(db.connect()) as c:
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return db.to_dict(row)


def file_name(rec: Dict[str, Any], ext: str) -> str:
    f = rec["data"].get("fields", {})
    return "-".join(p for p in ("intervention", str(rec["id"]), safe(f.get("initials")), safe(f.get("date"))) if p) + ext


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- records ---------------------------------------------------------------
@app.get("/api/interventions")
def list_interventions():
    with closing(db.connect()) as c:
        rows = c.execute("SELECT * FROM interventions ORDER BY intervention_date DESC, id DESC").fetchall()
    return [db.to_dict(r) for r in rows]


@app.get("/api/interventions/{item_id}")
def get_intervention(item_id: int):
    return get_record(item_id)


@app.get("/api/interventions/{item_id}/pdf")
def intervention_pdf(item_id: int):
    rec = get_record(item_id)
    return Response(content=render_pdf(rec), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{file_name(rec, ".pdf")}"'})


@app.get("/api/interventions/{item_id}/xlsx")
def intervention_xlsx(item_id: int):
    rec = get_record(item_id)
    return Response(content=fill_xlsx(rec), media_type=XLSX_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{file_name(rec, ".xlsx")}"'})


@app.post("/api/interventions", status_code=201)
def create_intervention(payload: Payload):
    cols = db.columns(payload.data)
    ts = db.now()
    with closing(db.connect()) as c:
        cur = c.execute(
            """INSERT INTO interventions
               (created_at, updated_at, intervention_date, pharmacy, ward, mrn,
                patient_initials, drug_name, disease, pharmacist, hours, data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, ts, *cols, json.dumps(payload.data)))
        c.commit()
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return db.to_dict(row)


@app.put("/api/interventions/{item_id}")
def update_intervention(item_id: int, payload: Payload):
    """Editing never needs the admin PIN."""
    cols = db.columns(payload.data)
    with closing(db.connect()) as c:
        cur = c.execute(
            """UPDATE interventions SET updated_at=?, intervention_date=?, pharmacy=?, ward=?,
               mrn=?, patient_initials=?, drug_name=?, disease=?, pharmacist=?, hours=?, data=?
               WHERE id=?""",
            (db.now(), *cols, json.dumps(payload.data), item_id))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    return db.to_dict(row)


@app.delete("/api/interventions/{item_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_intervention(item_id: int):
    """Deleting needs the admin PIN (X-Admin-Pin header)."""
    with closing(db.connect()) as c:
        cur = c.execute("DELETE FROM interventions WHERE id = ?", (item_id,))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
    return Response(status_code=204)


# ---- suggestions and monthly report ----------------------------------------------
@app.get("/api/pharmacies")
def pharmacies():
    return db.pharmacy_options()


def resolve_month(month: str) -> str:
    if month == "latest":
        months = db.month_options()
        return months[0]["value"] if months else "all"
    return month or "all"


@app.get("/api/report")
def monthly_report(month: str = "latest", pharmacy: str = ""):
    month = resolve_month(month)
    recs = db.select_records("" if month == "all" else month, pharmacy)
    values = report.compute(recs)
    return {
        "month": month,
        "pharmacy": pharmacy,
        "count": len(recs),
        "tables": report.ui_tables(values),
        "options": {
            "months": db.month_options(),
            "pharmacies": sorted(db.pharmacy_options(), key=lambda p: p["name"].lower()),
        },
    }


@app.get("/api/report/xlsx")
def monthly_report_xlsx(month: str = "latest", pharmacy: str = "", submitted_by: str = ""):
    month = resolve_month(month)
    recs = db.select_records("" if month == "all" else month, pharmacy)
    data = report.fill_report_xlsx(report.compute(recs), month, pharmacy.strip(), submitted_by.strip())
    name = "-".join(p for p in ("Clinical_Intervention_Monthly_Report", month, safe(pharmacy)) if p) + ".xlsx"
    return Response(content=data, media_type=XLSX_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# Static front end (must be mounted last so /api routes win)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
