"""Public demo uses generated data; private source details stay outside Git."""
import hashlib
import io
import json
import math
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw

from . import storage
from .importer import canonical, import_excel
from .models import Device

SYNTHETIC_NAME = "模拟仓库 · 合成数据"


def synthetic_devices():
    return [Device(id=f"DEMO-{i+1:02d}", label=f"模拟点 {i+1}",
                   x=.25 if i % 2 == 0 else .75, y=.22 + (i // 2) * .28,
                   group=f"模拟区域 {i//2+1}", height_mm=9000).model_dump(mode="json")
            for i in range(6)]


def synthetic_excel():
    """Deterministic fabricated records, unrelated to any customer's readings."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Result"
    sheet.append(["name", "message_type", "angle_x", "angle_y", "event_time", "temperature",
                  "x_displacement", "y_displacement", "x_y_displacement"])
    devices = synthetic_devices()
    for i in range(84):
        day = date(2026, 7, 1) + timedelta(days=i)
        temperature = 24 + 3 * math.sin(i / 6)
        for j, device in enumerate(devices):
            sign = 1 if j % 2 == 0 else -1
            drift = max(0, i - 20) * .001 if j < 2 else max(0, i - 45) * .0003 if j < 4 else 0
            ax = sign * (.01 + drift + .0005 * math.sin(i / 6))
            ay = .002 * math.cos(i / 9 + j)
            dx, dy = 9000 * math.tan(math.radians(ax)), 9000 * math.tan(math.radians(ay))
            for hour in (0, 12):
                sheet.append([device["id"], "Heartbeat", ax, ay, f"{day.isoformat()} {hour:02d}:00:00",
                              temperature, dx, dy, abs(dx) + abs(dy)])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def synthetic_layout():
    image = Image.new("RGB", (800, 600), "#f4f7f8")
    draw = ImageDraw.Draw(image)
    draw.text((24, 18), "SYNTHETIC DEMO - NOT A REAL WAREHOUSE", fill="#243b47")
    draw.rectangle((365, 70, 435, 550), fill="#dce5e9")
    for device in synthetic_devices():
        x, y = device["x"] * image.width, device["y"] * image.height
        draw.rectangle((x - 100, y - 45, x + 100, y + 45), outline="#245d79", width=3)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#b86d29")
        draw.text((x - 36, y + 15), device["id"], fill="#243b47")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def load_demo(synthetic=False):
    # This ignored local manifest preserves optional private examples on the user's PC.
    manifest = storage.DATA / "private-demo.json"
    if manifest.exists() and not synthetic:
        private = json.loads(manifest.read_text(encoding="utf-8"))
        existing = next((w for w in storage.list_warehouses() if w["name"] == private["name"]), None)
        if existing:
            return existing["id"]
        excel, layout = Path(private["excel"]), Path(private["layout"])
        if not excel.is_file() or not layout.is_file():
            raise ValueError("本地私有示例源文件不可用；可载入合成示例或上传自己的文件")
        key = storage.create_warehouse(private["name"])
        import_excel(key, excel.name, excel.read_bytes())
        with Image.open(layout) as source:
            prepared = io.BytesIO()
            source.convert("RGB").save(prepared, format="PNG")
        layout_content = prepared.getvalue()
        devices = [Device.model_validate(d).model_dump(mode="json") for d in private["devices"]]
    else:
        existing = next((w for w in storage.list_warehouses() if w["name"] == SYNTHETIC_NAME), None)
        if existing:
            return existing["id"]
        key = storage.create_warehouse(SYNTHETIC_NAME)
        import_excel(key, "synthetic-demo.xlsx", synthetic_excel())
        layout_content, devices = synthetic_layout(), synthetic_devices()
    layout_path = storage.DATA / "layouts" / (hashlib.sha256(layout_content).hexdigest() + ".png")
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    layout_path.write_bytes(layout_content)
    with storage.database() as db:
        db.execute("UPDATE warehouses SET layout=? WHERE id=?", (str(layout_path), key))
        for device in devices:
            db.execute("UPDATE devices SET metadata=? WHERE warehouse_id=? AND id=?", (canonical(device), key, device["id"]))
    return key
