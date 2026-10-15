"""Clinical intervention records: a small FastAPI + SQLite service.

Each intervention is stored as one row. The full form is kept as JSON in `data`;
a few columns are copied out so the table is easy to query or export directly.
"""
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Response
import re
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .pdf_form import render_pdf
from .xlsx_form import fill_xlsx

import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/data/interventions.db")
STATIC_DIR = Path(__file__).parent / "static"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    intervention_date TEXT,
    pharmacy TEXT,
    ward TEXT,
    mrn TEXT,
    patient_initials TEXT,
    drug_name TEXT,
    disease TEXT,
    pharmacist TEXT,
    hours REAL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interventions_date ON interventions (intervention_date);
"""


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with closing(connect()) as _c:
    _c.executescript(SCHEMA_SQL)
    _c.execute("PRAGMA journal_mode=WAL")
    _c.commit()


class Payload(BaseModel):
    data: Dict[str, Any]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def columns(data: Dict[str, Any]):
    fields = data.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(422, "Missing form fields")

    def s(key: str) -> str:
        return str(fields.get(key) or "").strip()

    for required in ("date", "initials", "drug_name"):
        if not s(required):
            raise HTTPException(422, f"'{required}' is required")
    try:
        hours = float(s("hours")) if s("hours") else None
    except ValueError:
        hours = None
    return (s("date"), s("pharmacy"), s("ward"), s("mrn"), s("initials"),
            s("drug_name"), s("disease"), s("pharmacist"), hours)


def to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "data": json.loads(row["data"]),
    }


app = FastAPI(title="Clinical interventions", docs_url="/api/docs", openapi_url="/api/openapi.json")

@app.middleware("http")
async def no_cache(request, call_next):
    """Never let browsers or proxies (e.g. Cloudflare) store responses: records are patient-related."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response



@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/interventions")
def list_interventions():
    with closing(connect()) as c:
        rows = c.execute(
            "SELECT * FROM interventions ORDER BY intervention_date DESC, id DESC"
        ).fetchall()
    return [to_dict(r) for r in rows]


@app.get("/api/interventions/{item_id}")
def get_intervention(item_id: int):
    with closing(connect()) as c:
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return to_dict(row)


@app.get("/api/interventions/{item_id}/pdf")
def intervention_pdf(item_id: int):
    with closing(connect()) as c:
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    rec = to_dict(row)
    f = rec["data"].get("fields", {})
    safe = lambda v: re.sub(r"[^A-Za-z0-9_-]+", "", str(v or ""))
    name = "-".join(p for p in ("intervention", str(item_id), safe(f.get("initials")), safe(f.get("date"))) if p)
    return Response(
        content=render_pdf(rec),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
    )


@app.get("/api/interventions/{item_id}/xlsx")
def intervention_xlsx(item_id: int):
    with closing(connect()) as c:
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    rec = to_dict(row)
    f = rec["data"].get("fields", {})
    safe = lambda v: re.sub(r"[^A-Za-z0-9_-]+", "", str(v or ""))
    name = "-".join(p for p in ("intervention", str(item_id), safe(f.get("initials")), safe(f.get("date"))) if p)
    return Response(
        content=fill_xlsx(rec),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )


@app.post("/api/interventions", status_code=201)
def create_intervention(payload: Payload):
    cols = columns(payload.data)
    ts = now()
    with closing(connect()) as c:
        cur = c.execute(
            """INSERT INTO interventions
               (created_at, updated_at, intervention_date, pharmacy, ward, mrn,
                patient_initials, drug_name, disease, pharmacist, hours, data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, ts, *cols, json.dumps(payload.data)),
        )
        c.commit()
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return to_dict(row)


@app.put("/api/interventions/{item_id}")
def update_intervention(item_id: int, payload: Payload):
    cols = columns(payload.data)
    with closing(connect()) as c:
        cur = c.execute(
            """UPDATE interventions SET updated_at=?, intervention_date=?, pharmacy=?, ward=?,
               mrn=?, patient_initials=?, drug_name=?, disease=?, pharmacist=?, hours=?, data=?
               WHERE id=?""",
            (now(), *cols, json.dumps(payload.data), item_id),
        )
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
        row = c.execute("SELECT * FROM interventions WHERE id = ?", (item_id,)).fetchone()
    return to_dict(row)


@app.delete("/api/interventions/{item_id}", status_code=204)
def delete_intervention(item_id: int):
    with closing(connect()) as c:
        cur = c.execute("DELETE FROM interventions WHERE id = ?", (item_id,))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
    return Response(status_code=204)


# Static front end (must be mounted last so /api routes win)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
