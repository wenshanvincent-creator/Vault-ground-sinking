from uuid import uuid4

from . import storage
from .analysis import analyze
from .importer import canonical
from .tracking import sync_report


def generate_report(warehouse_id, cycle="week", cutoff=None):
    with storage.database() as db:
        db.execute("BEGIN IMMEDIATE")
        warehouse = storage._read_warehouse(db, warehouse_id)
        result = analyze(warehouse, storage._read_records(db, warehouse_id), cycle, cutoff)
        result.update(id=uuid4().hex, created=storage.now(), profile=warehouse["profile"],
                      archive_events=warehouse["archive_events"], workflow_version="1.0")
        db.execute("INSERT INTO reports VALUES (?,?,?,?)", (result["id"], warehouse_id, result["created"], canonical(result)))
        result["tracking"] = sync_report(db, result)
        db.execute("UPDATE reports SET result=? WHERE id=?", (canonical(result), result["id"]))
    return result
