"""Findings, human handling and field evidence remain separate records."""
import json
from uuid import uuid4

from . import storage
from .importer import canonical

STATUS = {"pending": "待查看", "inspection": "待检查", "observing": "观察中", "resolved": "已处理"}
CONCLUSION = {"unknown": "尚不清楚", "suspected": "怀疑原因", "confirmed": "已确认原因"}


class VersionConflict(ValueError):
    pass


def _event(db, issue_id, kind, payload, report_id=None):
    event_id = uuid4().hex
    db.execute("INSERT INTO issue_events VALUES (?,?,?,?,?,?)",
               (event_id, issue_id, storage.now(), kind, report_id, canonical(payload)))
    return event_id


def _read(db, issue_id, warehouse_id):
    row = db.execute("SELECT * FROM issues WHERE id=? AND warehouse_id=?", (issue_id, warehouse_id)).fetchone()
    if row is None:
        raise KeyError("异常档案不存在于当前仓库")
    issue = json.loads(row["payload"])
    issue.update(id=row["id"], is_demo=bool(row["is_demo"]))
    issue["events"] = []
    for r in db.execute("SELECT * FROM issue_events WHERE issue_id=? ORDER BY created,rowid", (issue_id,)):
        event = {"id": r["id"], "created": r["created"], "kind": r["kind"],
                 "report_id": r["report_id"], "data": json.loads(r["payload"])}
        event["attachments"] = [dict(a) for a in db.execute(
            "SELECT id,filename,mime,hash,created FROM attachments WHERE event_id=? ORDER BY created,rowid", (r["id"],))]
        issue["events"].append(event)
    assessments = [e for e in issue["events"] if e["kind"] == "assessment"]
    assessments.sort(key=lambda e: (e["data"]["cutoff"], e["created"]))
    issue["latest_assessment"] = assessments[-1]["data"] if assessments else None
    latest = assessments[-1] if assessments else None
    handled = next((e for e in reversed(issue["events"]) if e["kind"] == "handling"), None)
    issue["recheck_needed"] = bool(issue["status"] == "resolved" and latest and
        latest["data"]["outcome"] == "triggered" and handled and
        issue["events"].index(latest) > issue["events"].index(handled))
    detected = [e["data"]["cutoff"] for e in assessments if e["data"]["outcome"] == "triggered"]
    issue["first_detected"] = min(detected) if detected else None
    issue["last_detected"] = max(detected) if detected else None
    return issue


def list_issues(db, warehouse_id, include_demo=True):
    rows = db.execute("SELECT id FROM issues WHERE warehouse_id=?" + ("" if include_demo else " AND is_demo=0") + " ORDER BY rowid DESC", (warehouse_id,))
    return [_read(db, r["id"], warehouse_id) for r in rows]


def get_issues(key):
    with storage.database() as db:
        storage._read_warehouse(db, key)
        return list_issues(db, key)


def _ensure(db, warehouse_id, fingerprint, kind, target, title, members, is_demo=False):
    existing = db.execute("SELECT id FROM issues WHERE warehouse_id=? AND fingerprint=? AND is_demo=?", (warehouse_id, fingerprint, int(is_demo))).fetchone()
    if existing:
        return existing["id"]
    issue_id = uuid4().hex
    payload = {"kind": kind, "target": target, "title": title, "members": members,
               "status": "pending", "version": 1, "created": storage.now()}
    db.execute("INSERT INTO issues VALUES (?,?,?,?,?)", (issue_id, warehouse_id, fingerprint, int(is_demo), canonical(payload)))
    return issue_id


def candidates(result):
    findings = {}
    for device in result["devices"]:
        conditions = [("persistent", device["persistent"], "持续倾斜变化", "参考变化、趋势速度、方向一致率及数据覆盖满足本次条件。"),
                      ("reference", device["reference_changed"] and device["quality"] == "可评估", "长期参考偏移", "相对参考时期存在差异，需核查历史调整记录。"),
                      ("angle", device["angle_attention"] and device["quality"] == "可评估", "角度业务关注", "周期中位数最大轴角度达到配置门槛。"),
                      ("distance", device["distance_attention"] and device["quality"] == "可评估", "位移业务关注", "周期中位数二维距离达到配置门槛。")]
        for kind, triggered, label, reason in conditions:
            if triggered:
                findings[f"{kind}:{device['id']}"] = {
                    "kind": kind, "target": device["id"], "title": f"设备 {device['label'] or device['id']} · {label}",
                    "members": [device["id"]], "reason": reason,
                    "measurements": {"baseline_shift_deg": device["baseline_shift_deg"], "trend_deg_week": device["trend_deg_week"],
                                     "consistency": device["consistency"], "valid_days": device["valid_days"],
                                     "angle_max_deg": device["angle_max_deg"], "distance_mm": device["current"]["distance"],
                                     "reference_start": device["reference_start"], "reference_end": device["reference_end"]}}
    for region in result["regions"]:
        # Membership changes create a separate scope, rather than silently conflating racks.
        scope = sorted(d["id"] for d in result["devices"] if d["group"] == region["group"])
        fingerprint = "region:" + canonical([region["group"], scope])
        findings[fingerprint] = {"kind": "region", "target": region["group"], "title": region["group"] + " · 区域共同变化",
                                 "members": region["members"], "scope": scope, "reason": region["evidence"],
                                 "measurements": {"pairs": region["pairs"], "inward_fraction": region["inward_fraction"], "missing": region["missing"]}}
    return findings


def assessment_outcome(issue, result):
    lookup = {d["id"]: d for d in result["devices"]}
    members = issue.get("scope", issue["members"])
    if any(m not in lookup for m in members):
        return "unavailable", "关联设备未纳入本次评估。"
    current_scope = sorted(d["id"] for d in result["devices"] if d["group"] == issue["target"])
    if issue["kind"] == "region" and (any(lookup[m]["group"] != issue["target"] for m in members) or current_scope != sorted(members)):
        return "unavailable", "点组配置已变化，不能按旧范围继续比较。"
    if any(lookup[m]["quality"] != "可评估" for m in members):
        return "unavailable", "关联点当前或参考时期数据不足。"
    if issue["kind"] in ("angle", "distance"):
        device = lookup[members[0]]
        field = "angle_attention" if issue["kind"] == "angle" else "distance_attention"
        if device[field] is None:
            return "unavailable", "业务门槛未配置或对应测量缺失。"
    if issue["kind"] == "manual":
        return "observed", "人工追踪点：本期趋势已保存，是否处理由管理员判断。"
    return "not_triggered", "本期未再次满足该项条件；处理状态保留，不能据此认定恢复。"


def sync_report(db, result):
    warehouse_id = result["warehouse_id"]
    findings = candidates(result)
    for fingerprint, finding in findings.items():
        issue_id = _ensure(db, warehouse_id, fingerprint, finding["kind"], finding["target"], finding["title"], finding["members"])
        if "scope" in finding:
            row = db.execute("SELECT payload FROM issues WHERE id=?", (issue_id,)).fetchone()
            payload = json.loads(row["payload"])
            payload["scope"] = finding["scope"]
            db.execute("UPDATE issues SET payload=? WHERE id=?", (canonical(payload), issue_id))
    for row in db.execute("SELECT * FROM issues WHERE warehouse_id=? AND is_demo=0", (warehouse_id,)).fetchall():
        issue = json.loads(row["payload"])
        finding = findings.get(row["fingerprint"])
        outcome, reason = ("triggered", finding["reason"]) if finding else assessment_outcome(issue, result)
        snapshot = {"start": result["start"], "cutoff": result["cutoff"], "outcome": outcome,
                    "reason": reason, "members": finding["members"] if finding else issue["members"],
                    "settings": result["settings"], "algorithm_version": result["algorithm_version"]}
        if finding:
            snapshot["measurements"] = finding["measurements"]
        else:
            snapshot["measurements"] = [{"id": d["id"], "status": d["status"], "baseline_shift_deg": d["baseline_shift_deg"],
                                         "trend_deg_week": d["trend_deg_week"]} for d in result["devices"] if d["id"] in issue["members"]]
        _event(db, row["id"], "assessment", snapshot, result["id"])
    return list_issues(db, warehouse_id, include_demo=False)


def create_manual(key, model):
    with storage.database() as db:
        storage._read_warehouse(db, key)
        row = db.execute("SELECT result FROM reports WHERE id=? AND warehouse_id=?", (model.report_id, key)).fetchone()
        if not row:
            raise KeyError("当前仓库中没有该报告")
        result = json.loads(row["result"])
        device = next((d for d in result["devices"] if d["id"] == model.device_id), None)
        if device is None:
            raise ValueError("设备不在所选报告中")
        if not model.reason.strip():
            raise ValueError("请填写追踪原因")
        issue_id = _ensure(db, key, "manual:" + device["id"], "manual", device["id"], f"设备 {device['label'] or device['id']} · 人工追踪", [device["id"]])
        _event(db, issue_id, "note", {"note": model.reason, "report_id": model.report_id})
        return _read(db, issue_id, key)


def update_issue(key, issue_id, model):
    with storage.database() as db:
        db.execute("BEGIN IMMEDIATE")
        issue = _read(db, issue_id, key)
        if issue["version"] != model.version:
            raise VersionConflict("档案已被更新，请刷新后再保存")
        if not model.note.strip() or not model.author.strip():
            raise ValueError("请填写处理人和处理说明")
        _event(db, issue_id, "handling", {"before": issue["status"], "after": model.status, "author": model.author, "note": model.note})
        row = db.execute("SELECT payload FROM issues WHERE id=?", (issue_id,)).fetchone()
        payload = json.loads(row["payload"])
        payload.update(status=model.status, version=model.version + 1)
        db.execute("UPDATE issues SET payload=? WHERE id=?", (canonical(payload), issue_id))
        return _read(db, issue_id, key)


def add_inspection(key, issue_id, model):
    with storage.database() as db:
        _read(db, issue_id, key)
        _event(db, issue_id, "inspection", model.model_dump(mode="json"))
        return _read(db, issue_id, key)


def load_simulation(key):
    """Isolated human workflow example, never sensor findings or training truth."""
    with storage.database() as db:
        warehouse = storage._read_warehouse(db, key)
        members = [d["id"] for d in warehouse["devices"][:2]]
        issue_id = _ensure(db, key, "simulated-workflow", "manual", "模拟区域", "模拟案例 · 载荷调整后继续观察", members, True)
        if not db.execute("SELECT 1 FROM issue_events WHERE issue_id=?", (issue_id,)).fetchone():
            _event(db, issue_id, "note", {"note": "模拟情境：多个点位出现变化，管理员安排检查。没有对应真实测量。"})
            _event(db, issue_id, "handling", {"before": "pending", "after": "inspection", "author": "模拟管理员", "note": "安排核查载荷、安装与地面状况。"})
            _event(db, issue_id, "inspection", {"checked_on": "2026-10-01", "inspector": "模拟检查人", "location": "模拟区域",
                "observation": "模拟观察：近期货物集中在一侧。", "action": "模拟措施：调整货物分布。",
                "cause": "载荷分布变化", "conclusion": "suspected", "basis": "仅为流程演示，无真实照片或测量。", "follow_up": "后续复测并观察趋势。"})
            _event(db, issue_id, "handling", {"before": "inspection", "after": "observing", "author": "模拟管理员", "note": "继续观察；示例不代表真实原因已确认。"})
            row = db.execute("SELECT payload FROM issues WHERE id=?", (issue_id,)).fetchone()
            payload = json.loads(row["payload"])
            payload.update(status="observing", version=3)
            db.execute("UPDATE issues SET payload=? WHERE id=?", (canonical(payload), issue_id))
        return _read(db, issue_id, key)
