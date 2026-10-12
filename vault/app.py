import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from . import archive, storage, tracking
from .importer import canonical, import_excel
from .models import (Device, InspectionCreate, IssueCreate, IssueUpdate, ReportRequest, SiteEvent,
                     Settings, WarehouseCreate, WarehouseProfile)
from .report import build_pdf
from .service import generate_report


@asynccontextmanager
async def lifespan(app):
    storage.initialize()
    yield


app = FastAPI(title="仓库周期评估", lifespan=lifespan)


@app.exception_handler(tracking.VersionConflict)
async def conflict(request, exc):
    return Response(json.dumps({"detail": str(exc)}, ensure_ascii=False), status_code=409, media_type="application/json")


@app.exception_handler(KeyError)
async def missing(request, exc):
    return Response(json.dumps({"detail": str(exc.args[0])}, ensure_ascii=False), status_code=404, media_type="application/json")


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return Response(json.dumps({"detail": str(exc)}, ensure_ascii=False), status_code=400, media_type="application/json")


@app.get("/api/warehouses")
def warehouses():
    return storage.list_warehouses()


@app.post("/api/warehouses")
def create(data: WarehouseCreate):
    if not data.name.strip():
        raise ValueError("请填写仓库名称")
    return storage.get_warehouse(storage.create_warehouse(data.name))


@app.get("/api/warehouses/{key}")
def warehouse(key: str):
    return storage.get_warehouse(key)


@app.post("/api/warehouses/{key}/import")
def upload_excel(key: str, file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise ValueError("请上传现有格式的 .xlsx 文件")
    content = file.file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("原型单次导入上限20MB，请拆分导出")
    return import_excel(key, file.filename, content)


@app.put("/api/warehouses/{key}/settings")
def settings(key: str, data: Settings):
    if data.reference_start:
        date.fromisoformat(data.reference_start)
    if (data.angle_limit_deg is not None or data.distance_limit_mm is not None) and not data.threshold_basis.strip():
        raise ValueError("设置业务阈值时，请同时填写依据和适用条件")
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        updated = data.model_dump()
        archive.log_change(db, key, "settings", "分析配置", warehouse["settings"], updated)
        archive.invalidate_profile(db, warehouse, warehouse["settings"], updated)
        db.execute("UPDATE warehouses SET settings=? WHERE id=?", (canonical(data.model_dump()), key))
    return storage.get_warehouse(key)


@app.put("/api/warehouses/{key}/devices")
def devices(key: str, data: list[Device]):
    return archive.save_devices(key, data)


@app.put("/api/warehouses/{key}/profile")
def profile(key: str, data: WarehouseProfile):
    return archive.save_profile(key, data)


@app.post("/api/warehouses/{key}/site-events")
def site_event(key: str, data: SiteEvent):
    return archive.add_site_event(key, data)


@app.post("/api/warehouses/{key}/layout")
def upload_layout(key: str, file: UploadFile = File(...)):
    storage.get_warehouse(key)
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("布局图片上限5MB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("布局图尺寸过大")
            prepared = ImageOps.exif_transpose(image).convert("RGB")
            out = io.BytesIO()
            prepared.save(out, format="PNG")
    except (OSError, Image.DecompressionBombError):
        raise ValueError("请上传有效的PNG或JPEG布局图片") from None
    payload = out.getvalue()
    path = storage.DATA / "layouts" / (hashlib.sha256(payload).hexdigest() + ".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        archive.log_change(db, key, "layout", "布局图", warehouse["layout"], str(path))
        archive.invalidate_profile(db, warehouse, {"layout": warehouse["layout"]}, {"layout": str(path)})
        db.execute("UPDATE warehouses SET layout=? WHERE id=?", (str(path), key))
    return storage.get_warehouse(key)


@app.get("/api/warehouses/{key}/layout")
def layout(key: str):
    path = storage.get_warehouse(key)["layout"]
    if not path:
        raise KeyError("尚未上传布局图")
    return FileResponse(path)


@app.post("/api/warehouses/{key}/reports")
def evaluate(key: str, data: ReportRequest):
    return generate_report(key, data.cycle, data.cutoff)


@app.get("/api/reports/{key}")
def report(key: str):
    return storage.get_report(key)


@app.get("/api/reports/{key}/layout")
def report_layout(key: str):
    path = storage.get_report(key)["layout_path"]
    if not path:
        raise KeyError("报告没有布局图")
    return FileResponse(path)


@app.get("/api/reports/{key}/pdf")
def pdf(key: str):
    result = storage.get_report(key)
    return Response(build_pdf(result), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="warehouse-report-{result["cutoff"]}-{key[:8]}.pdf"'})


@app.get("/api/warehouses/{key}/records")
def records(key: str, device: str, before: str | None = None):
    storage.get_warehouse(key)
    with storage.database() as db:
        if before:
            date.fromisoformat(before)
        clause = " AND event_time<?" if before else ""
        params = [key, device] + [(date.fromisoformat(before) + timedelta(days=1)).isoformat() + "T00:00:00"] if before else [key, device]
        rows = db.execute("SELECT payload FROM records WHERE warehouse_id=? AND device_id=?" + clause + " ORDER BY event_time DESC LIMIT 100", params)
        return [json.loads(r["payload"]) for r in rows]


@app.post("/api/demo")
def demo(synthetic: bool = False):
    """Generate a synthetic demo; private examples require an ignored local manifest."""
    from .demo import load_demo
    return storage.get_warehouse(load_demo(synthetic=synthetic))


@app.get("/api/warehouses/{key}/issues")
def issues(key: str):
    return tracking.get_issues(key)


@app.post("/api/warehouses/{key}/issues")
def manual_issue(key: str, data: IssueCreate):
    return tracking.create_manual(key, data)


@app.put("/api/warehouses/{key}/issues/{issue_id}")
def handle_issue(key: str, issue_id: str, data: IssueUpdate):
    return tracking.update_issue(key, issue_id, data)


@app.post("/api/warehouses/{key}/issues/{issue_id}/inspections")
def inspection(key: str, issue_id: str, data: InspectionCreate):
    return tracking.add_inspection(key, issue_id, data)


@app.post("/api/warehouses/{key}/simulation")
def simulation(key: str):
    return tracking.load_simulation(key)


@app.post("/api/warehouses/{key}/issues/{issue_id}/events/{event_id}/attachments")
def upload_attachment(key: str, issue_id: str, event_id: str, file: UploadFile = File(...)):
    with storage.database() as db:
        tracking._read(db, issue_id, key)
        event = db.execute("SELECT kind FROM issue_events WHERE id=? AND issue_id=?", (event_id, issue_id)).fetchone()
        if not event or event["kind"] != "inspection":
            raise ValueError("附件必须关联当前档案的一条检查记录")
    content = file.file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise ValueError("附件不能为空，单个附件上限10MB")
    name = (file.filename or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
    if len(name) > 180 or any(ord(c) < 32 for c in name):
        raise ValueError("附件文件名过长或含无效字符")
    suffix = Path(name).suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain"}.get(suffix)
    if not mime:
        raise ValueError("请上传照片PNG/JPEG、测量PDF、CSV或TXT")
    if suffix in (".png", ".jpg", ".jpeg"):
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > 20_000_000:
                    raise ValueError("照片格式或尺寸无效")
                image.verify()
        except (OSError, Image.DecompressionBombError):
            raise ValueError("附件照片无法读取") from None
    elif suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("附件不是PDF文件")
    else:
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("CSV/TXT请使用UTF-8编码") from None
    digest = hashlib.sha256(content).hexdigest()
    path = storage.DATA / "attachments" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    with storage.database() as db:
        tracking._read(db, issue_id, key)
        db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)",
                   (uuid4().hex, issue_id, event_id, storage.now(), name, mime, digest, str(path)))
        return tracking._read(db, issue_id, key)


@app.get("/api/warehouses/{key}/issues/{issue_id}/attachments/{attachment_id}")
def attachment(key: str, issue_id: str, attachment_id: str):
    with storage.database() as db:
        tracking._read(db, issue_id, key)
        row = db.execute("SELECT * FROM attachments WHERE id=? AND issue_id=?", (attachment_id, issue_id)).fetchone()
        if not row:
            raise KeyError("附件不存在于当前档案")
        return FileResponse(row["path"], media_type=row["mime"], filename=row["filename"])


app.mount("/", StaticFiles(directory=storage.ROOT / "web", html=True), name="web")
