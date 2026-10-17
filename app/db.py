"""SQLite access shared by the API, report and admin modules."""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

DB_PATH = os.environ.get("DB_PATH", "/data/interventions.db")

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


def init() -> None:
    with closing(connect()) as c:
        c.executescript(SCHEMA_SQL)
        c.execute("PRAGMA journal_mode=WAL")
        c.commit()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(s: Any) -> str:
    """Case- and spacing-insensitive key, so 'DS  Gordon Town' == 'ds gordon town'."""
    return " ".join(str(s or "").lower().split())


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


def select_records(month: str = "", pharmacy: str = "") -> List[Dict[str, Any]]:
    """Records for a month ('YYYY-MM', or '' for all) and pharmacy ('' for all)."""
    sql, args = "SELECT * FROM interventions", []
    if month:
        sql += " WHERE intervention_date LIKE ?"
        args.append(month + "-%")
    sql += " ORDER BY intervention_date DESC, id DESC"
    with closing(connect()) as c:
        rows = [to_dict(r) for r in c.execute(sql, args).fetchall()]
    if pharmacy:
        key = norm(pharmacy)
        rows = [r for r in rows if norm(r["data"].get("fields", {}).get("pharmacy")) == key]
    return rows


def pharmacy_options() -> List[Dict[str, Any]]:
    """Distinct pharmacy names (spelling variants merged), most used first."""
    with closing(connect()) as c:
        rows = c.execute(
            "SELECT pharmacy, COUNT(*) n FROM interventions WHERE TRIM(pharmacy) != '' GROUP BY pharmacy"
        ).fetchall()
    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        g = groups.setdefault(norm(r["pharmacy"]), {"name": r["pharmacy"].strip(), "count": 0, "best": 0})
        g["count"] += r["n"]
        if r["n"] > g["best"]:
            g["name"], g["best"] = r["pharmacy"].strip(), r["n"]
    out = [{"name": g["name"], "count": g["count"]} for g in groups.values()]
    return sorted(out, key=lambda x: (-x["count"], x["name"].lower()))


def month_options() -> List[Dict[str, Any]]:
    with closing(connect()) as c:
        rows = c.execute(
            "SELECT SUBSTR(intervention_date, 1, 7) m, COUNT(*) n FROM interventions "
            "WHERE LENGTH(intervention_date) >= 7 GROUP BY m ORDER BY m DESC"
        ).fetchall()
    return [{"value": r["m"], "count": r["n"]} for r in rows]
