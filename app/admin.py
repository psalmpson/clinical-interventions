"""Admin tools. Everything here (and record deletion) needs the ADMIN_PIN
set in the container environment. Editing records never needs it."""
import hmac
import json
import os
import time
from contextlib import closing
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api/admin")

ADMIN_PIN = os.environ.get("ADMIN_PIN", "")
MAX_FAILS, FAIL_WINDOW, LOCKOUT = 5, 300, 300      # 5 wrong PINs in 5 min => locked for 5 min
_fails: List[float] = []
_locked_until = 0.0


def check_pin(pin: str) -> None:
    global _locked_until
    t = time.time()
    if t < _locked_until:
        raise HTTPException(429, f"Too many wrong PINs. Try again in {int(_locked_until - t) + 1} seconds.")
    if not ADMIN_PIN:
        raise HTTPException(403, "The admin PIN is not set. Add ADMIN_PIN to the container environment.")
    if pin and hmac.compare_digest(pin.encode("utf8"), ADMIN_PIN.encode("utf8")):
        _fails.clear()
        return
    _fails.append(t)
    _fails[:] = [x for x in _fails if t - x < FAIL_WINDOW]
    if len(_fails) >= MAX_FAILS:
        _locked_until = t + LOCKOUT
        _fails.clear()
    raise HTTPException(403, "Wrong admin PIN.")


def require_admin(x_admin_pin: Optional[str] = Header(None)) -> None:
    check_pin(x_admin_pin or "")


class PinBody(BaseModel):
    pin: str = ""


class RenameBody(BaseModel):
    old: str
    new: str


class DeleteBody(BaseModel):
    month: str = ""
    pharmacy: str = ""
    dry_run: bool = True


class RestoreBody(BaseModel):
    records: List[Dict[str, Any]]


@router.get("/status")
def status():
    return {"configured": bool(ADMIN_PIN), "default_pin": ADMIN_PIN == "change-me"}


@router.post("/verify")
def verify(body: PinBody):
    check_pin(body.pin)
    return {"ok": True}


@router.get("/backup", dependencies=[Depends(require_admin)])
def backup():
    with closing(db.connect()) as c:
        rows = c.execute("SELECT * FROM interventions ORDER BY id").fetchall()
    return {"app": "clinical-interventions", "exported_at": db.now(), "records": [db.to_dict(r) for r in rows]}


@router.post("/restore", dependencies=[Depends(require_admin)])
def restore(body: RestoreBody):
    added = skipped = 0
    with closing(db.connect()) as c:
        existing = {(r["created_at"], r["data"]) for r in c.execute("SELECT created_at, data FROM interventions")}
        for rec in body.records:
            data = rec.get("data")
            if not isinstance(data, dict):
                skipped += 1
                continue
            cols = db.columns(data)
            blob = json.dumps(data)
            created = str(rec.get("created_at") or db.now())
            if (created, blob) in existing:
                skipped += 1
                continue
            c.execute(
                """INSERT INTO interventions
                   (created_at, updated_at, intervention_date, pharmacy, ward, mrn,
                    patient_initials, drug_name, disease, pharmacist, hours, data)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (created, str(rec.get("updated_at") or created), *cols, blob))
            existing.add((created, blob))
            added += 1
        c.commit()
    return {"added": added, "skipped": skipped}


@router.post("/rename-pharmacy", dependencies=[Depends(require_admin)])
def rename_pharmacy(body: RenameBody):
    new = body.new.strip()
    if not new:
        raise HTTPException(422, "Enter the new pharmacy name.")
    key, changed = db.norm(body.old), 0
    with closing(db.connect()) as c:
        for row in c.execute("SELECT id, data FROM interventions").fetchall():
            data = json.loads(row["data"])
            fields = data.setdefault("fields", {})
            if db.norm(fields.get("pharmacy")) == key:
                fields["pharmacy"] = new
                c.execute("UPDATE interventions SET pharmacy=?, data=?, updated_at=? WHERE id=?",
                          (new, json.dumps(data), db.now(), row["id"]))
                changed += 1
        c.commit()
    return {"changed": changed}


@router.post("/delete-matching", dependencies=[Depends(require_admin)])
def delete_matching(body: DeleteBody):
    ids = [r["id"] for r in db.select_records(body.month if body.month != "all" else "", body.pharmacy)]
    if not body.dry_run and ids:
        with closing(db.connect()) as c:
            c.executemany("DELETE FROM interventions WHERE id = ?", [(i,) for i in ids])
            c.commit()
    return {"count": len(ids), "deleted": not body.dry_run}
