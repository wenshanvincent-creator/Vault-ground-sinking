import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import Device, Settings, WarehouseProfile

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("VAULT_DATA_DIR", ROOT / "data"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def database():
    DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATA / "vault.sqlite", timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with database() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL,
            settings TEXT NOT NULL, layout TEXT
        );
        CREATE TABLE IF NOT EXISTS devices (
            warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
            id TEXT NOT NULL, metadata TEXT NOT NULL,
            PRIMARY KEY (warehouse_id, id)
        );
        CREATE TABLE IF NOT EXISTS imports (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
            filename TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL,
            summary TEXT NOT NULL, source_path TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records (
            warehouse_id TEXT NOT NULL REFERENCES warehouses(id), device_id TEXT NOT NULL,
            event_time TEXT NOT NULL, message_type TEXT NOT NULL, payload TEXT NOT NULL,
            import_id TEXT NOT NULL REFERENCES imports(id),
            PRIMARY KEY (warehouse_id, device_id, event_time, message_type)
        );
        CREATE INDEX IF NOT EXISTS records_time ON records(warehouse_id, event_time);
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
            created TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS profiles (
            warehouse_id TEXT PRIMARY KEY REFERENCES warehouses(id), payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS archive_events (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
            created TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS issues (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL REFERENCES warehouses(id),
            fingerprint TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL,
            UNIQUE(warehouse_id, fingerprint, is_demo)
        );
        CREATE TABLE IF NOT EXISTS issue_events (
            id TEXT PRIMARY KEY, issue_id TEXT NOT NULL REFERENCES issues(id),
            created TEXT NOT NULL, kind TEXT NOT NULL, report_id TEXT REFERENCES reports(id), payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS issue_events_issue ON issue_events(issue_id, created);
        CREATE UNIQUE INDEX IF NOT EXISTS issue_report_once ON issue_events(issue_id, report_id) WHERE report_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY, issue_id TEXT NOT NULL REFERENCES issues(id),
            event_id TEXT NOT NULL REFERENCES issue_events(id), created TEXT NOT NULL,
            filename TEXT NOT NULL, mime TEXT NOT NULL, hash TEXT NOT NULL, path TEXT NOT NULL
        );
        """)


def create_warehouse(name):
    key = uuid4().hex
    with database() as db:
        db.execute("INSERT INTO warehouses VALUES (?,?,?,?,NULL)",
                   (key, name.strip(), now(), json.dumps(Settings().model_dump())))
    return key


def _read_warehouse(db, key):
    row = db.execute("SELECT * FROM warehouses WHERE id=?", (key,)).fetchone()
    if row is None:
        raise KeyError("仓库不存在")
    result = dict(row)
    result["settings"] = json.loads(result["settings"])
    result["devices"] = [Device.model_validate(json.loads(r["metadata"])).model_dump(mode="json") for r in db.execute(
        "SELECT metadata FROM devices WHERE warehouse_id=? ORDER BY id", (key,))]
    result["imports"] = [dict(r) for r in db.execute(
        "SELECT id,filename,created,summary,hash FROM imports WHERE warehouse_id=? ORDER BY created DESC", (key,))]
    for item in result["imports"]:
        item["summary"] = json.loads(item["summary"])
    result["reports"] = [dict(r) for r in db.execute(
        "SELECT id,created,json_extract(result,'$.start') start,json_extract(result,'$.cutoff') cutoff,json_extract(result,'$.days') days "
        "FROM reports WHERE warehouse_id=? ORDER BY created DESC", (key,))]
    stats = db.execute("SELECT COUNT(*) n, MIN(event_time) first, MAX(event_time) last FROM records WHERE warehouse_id=?", (key,)).fetchone()
    result["record_count"] = stats["n"]
    profile = db.execute("SELECT payload FROM profiles WHERE warehouse_id=?", (key,)).fetchone()
    result["profile"] = WarehouseProfile.model_validate(json.loads(profile["payload"]) if profile else {}).model_dump(mode="json")
    result["archive_events"] = [dict(r) for r in db.execute(
        "SELECT id,created,kind,target,payload FROM archive_events WHERE warehouse_id=? ORDER BY created DESC,rowid DESC", (key,))]
    for event in result["archive_events"]:
        event["payload"] = json.loads(event["payload"])
    result["first_time"], result["last_time"] = stats["first"], stats["last"]
    result["layout_url"] = f"/api/warehouses/{key}/layout" if result["layout"] else None
    result["layout_aspect"] = 1
    if result["layout"]:
        from PIL import Image
        with Image.open(result["layout"]) as image:
            result["layout_aspect"] = image.width / image.height
    return result


def get_warehouse(key):
    with database() as db:
        return _read_warehouse(db, key)


def list_warehouses():
    with database() as db:
        keys = [r["id"] for r in db.execute("SELECT id FROM warehouses ORDER BY created")]
    return [get_warehouse(key) for key in keys]


def _read_records(db, key):
    return [json.loads(r["payload"]) for r in db.execute(
        "SELECT payload FROM records WHERE warehouse_id=? ORDER BY event_time,device_id", (key,))]


def get_records(key):
    with database() as db:
        return _read_records(db, key)


def get_report(key):
    with database() as db:
        row = db.execute("SELECT result FROM reports WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("报告不存在")
        return json.loads(row["result"])
