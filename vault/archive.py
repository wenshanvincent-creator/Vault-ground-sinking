"""Installation knowledge and its append-only change history."""
from uuid import uuid4

from . import storage
from .importer import canonical
from .models import Device, Evidence

DEVICE_FIELDS = {
    "position": ("x", "y"), "axis": ("rotation_deg", "x_sign", "y_sign"),
    "height": ("height_mm",), "group": ("group",), "installation": ("installed_on",),
    "connections": ("connections",), "cadence": ("expected_hours",),
}
PROFILE_FIELDS = {
    "layout": ("layout",), "ground_reference": ("ground_reference",),
    "connections": ("connections",), "reference": ("reference_start", "reference_days"),
    "threshold": ("angle_limit_deg", "distance_limit_mm", "threshold_basis"),
    "timezone": ("source_timezone",),
}


def log_change(db, warehouse_id, kind, target, before, after):
    if before == after:
        return
    db.execute("INSERT INTO archive_events VALUES (?,?,?,?,?,?)",
               (uuid4().hex, warehouse_id, storage.now(), kind, target,
                canonical({"before": before, "after": after})))


def reset_changed_evidence(before, after, fields):
    """An old confirmation must not silently endorse a changed installation value."""
    for topic, keys in fields.items():
        if any(before.get(k) != after.get(k) for k in keys):
            old = before.get("evidence", {}).get(topic, {})
            current = after.get("evidence", {}).get(topic, {})
            if current == old and current.get("status") in ("confirmed", "inferred"):
                after.setdefault("evidence", {})[topic] = Evidence(
                    source="原确认资料对应旧值；本次修改后待重新核对").model_dump(mode="json")


def save_devices(key, data):
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        old = {d["id"]: d for d in warehouse["devices"]}
        if len(data) != len(old) or {d.id for d in data} != set(old):
            raise ValueError("请为全部已导入设备各提交一份配置，不能修改设备身份")
        for model in data:
            device = model.model_dump(mode="json")
            if (device["x"] is None) != (device["y"] is None):
                raise ValueError("点位X/Y坐标必须同时填写或同时留空")
            reset_changed_evidence(old[model.id], device, DEVICE_FIELDS)
            values = {"position": device["x"] is not None and device["y"] is not None,
                      "height": device["height_mm"] is not None, "group": bool(device["group"].strip()),
                      "installation": device["installed_on"] is not None, "connections": bool(device["connections"].strip()),
                      "axis": True, "cadence": True}
            for topic, stamp in device["evidence"].items():
                if stamp["status"] != "unknown" and not values[topic]:
                    raise ValueError(f"{topic} 尚未填写，不能标记为推测或已确认")
            device = Device.model_validate(device).model_dump(mode="json")
            log_change(db, key, "device", model.id, old[model.id], device)
            db.execute("UPDATE devices SET metadata=? WHERE warehouse_id=? AND id=?", (canonical(device), key, model.id))
    return storage.get_warehouse(key)


def save_profile(key, model):
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        profile = model.model_dump(mode="json")
        reset_changed_evidence(warehouse["profile"], profile, PROFILE_FIELDS)
        values = {**profile, **warehouse["settings"], "layout": warehouse["layout"]}
        available = {"layout": bool(values["layout"]), "ground_reference": bool(profile["ground_reference"].strip()),
                     "connections": bool(profile["connections"].strip()), "reference": bool(values["reference_start"]),
                     "threshold": bool(values["threshold_basis"].strip()) and
                         (values["angle_limit_deg"] is not None or values["distance_limit_mm"] is not None),
                     "timezone": bool(values["source_timezone"].strip())}
        for topic, stamp in profile["evidence"].items():
            if stamp["status"] != "unknown" and not available[topic]:
                raise ValueError(f"{topic} 尚未填写，不能标记为推测或已确认")
        log_change(db, key, "profile", "仓库资料", warehouse["profile"], profile)
        db.execute("INSERT INTO profiles VALUES (?,?) ON CONFLICT(warehouse_id) DO UPDATE SET payload=excluded.payload", (key, canonical(profile)))
    return storage.get_warehouse(key)


def add_site_event(key, model):
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        if not set(model.members).issubset({d["id"] for d in warehouse["devices"]}):
            raise ValueError("关联设备不在当前仓库")
        db.execute("INSERT INTO archive_events VALUES (?,?,?,?,?,?)",
                   (uuid4().hex, key, storage.now(), "site_event", model.location,
                    canonical(model.model_dump(mode="json"))))
    return storage.get_warehouse(key)


def invalidate_profile(db, warehouse, before, after):
    profile = warehouse["profile"]
    old = {**before, "evidence": profile["evidence"]}
    updated = {**after, "evidence": dict(profile["evidence"])}
    reset_changed_evidence(old, updated, PROFILE_FIELDS)
    if profile["evidence"] != updated["evidence"]:
        changed = {**profile, "evidence": updated["evidence"]}
        log_change(db, warehouse["id"], "profile", "配置改变，确认状态重置", profile, changed)
        db.execute("INSERT INTO profiles VALUES (?,?) ON CONFLICT(warehouse_id) DO UPDATE SET payload=excluded.payload", (warehouse["id"], canonical(changed)))
