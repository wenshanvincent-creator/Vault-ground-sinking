"""Deterministic, inspectable tilt evidence; no settlement-depth inversion."""
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations

from .models import Settings

VERSION = "0.2.0"


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def distance(x, y):
    return math.hypot(x, y) if x is not None and y is not None else None


def delta(a, b):
    return a - b if a is not None and b is not None else None


def level(series):
    return {key: median([day[key] for day in series])
            for key in ["ax", "ay", "dx", "dy", "distance", "legacy", "temperature"]}


def monthly_matrix(series):
    months = defaultdict(list)
    for day in series:
        months[day["date"][:7]].append(day)
    return [{"date": month, "days": len(items),
             **{key: median([d[key] for d in items]) for key in ["angle_change", "distance_change", "distance", "legacy"]}}
            for month, items in sorted(months.items())]


def reference_begin(series, settings, cutoff):
    if settings.reference_start:
        return date.fromisoformat(settings.reference_start)
    if not series:
        return None
    required = math.ceil(settings.reference_days * settings.min_day_coverage)
    has_displacement = any(d["dx"] is not None and d["dy"] is not None for d in series)
    for candidate in series:
        begin = date.fromisoformat(candidate["date"])
        end = begin + timedelta(days=settings.reference_days - 1)
        if end > cutoff:
            break
        window = [d for d in series if begin.isoformat() <= d["date"] <= end.isoformat()]
        angles = sum(d["ax"] is not None and d["ay"] is not None for d in window)
        positions = sum(d["dx"] is not None and d["dy"] is not None for d in window)
        if angles >= required and (not has_displacement or positions >= required):
            return begin
    return date.fromisoformat(series[0]["date"])


def slope(series, field):
    usable = [(date.fromisoformat(d["date"]).toordinal(), d[field]) for d in series if d[field] is not None]
    if len(usable) < 4:
        return None
    x, y = zip(*usable)
    xm, ym = statistics.mean(x), statistics.mean(y)
    denominator = sum((v - xm) ** 2 for v in x)
    return sum((a - xm) * (b - ym) for a, b in usable) / denominator * 7 if denominator else None


def correlation(a, b):
    if len(a) < 4:
        return None
    am, bm = statistics.mean(a), statistics.mean(b)
    av = sum((v - am) ** 2 for v in a)
    bv = sum((v - bm) ** 2 for v in b)
    if av < 1e-12 or bv < 1e-12:
        return None
    return sum((x - am) * (y - bm) for x, y in zip(a, b)) / math.sqrt(av * bv)


def aggregate(records):
    grouped = defaultdict(list)
    for record in records:
        if record["message_type"] == "Heartbeat":
            grouped[record["event_time"][:10]].append(record)
    result = []
    for day, items in sorted(grouped.items()):
        result.append({
            "date": day,
            "ax": median([r.get("angle_x") for r in items]),
            "ay": median([r.get("angle_y") for r in items]),
            "dx": median([r.get("x_displacement") for r in items]),
            "dy": median([r.get("y_displacement") for r in items]),
            "distance": median([distance(r.get("x_displacement"), r.get("y_displacement")) for r in items]),
            "legacy": median([r.get("x_y_displacement") for r in items]),
            "temperature": median([r.get("temperature") for r in items]),
            "count": len(items),
        })
    return result


def direction_consistency(series, sx, sy):
    if sx is None or sy is None or math.hypot(sx, sy) < 1e-12:
        return None
    projections = []
    complete = [d for d in series if d["ax"] is not None and d["ay"] is not None]
    for a, b in zip(complete, complete[1:]):
        dx, dy = b["ax"] - a["ax"], b["ay"] - a["ay"]
        if math.hypot(dx, dy) > 1e-6:
            projections.append(dx * sx + dy * sy > 0)
    return statistics.mean(projections) if len(projections) >= 3 else None


def summarize_device(metadata, records, settings, start, cutoff, previous_start):
    series = aggregate(records)
    current = [d for d in series if start <= date.fromisoformat(d["date"]) <= cutoff]
    previous = [d for d in series if previous_start <= date.fromisoformat(d["date"]) < start]
    reference_start = reference_begin(series, settings, cutoff)
    reference_end = reference_start + timedelta(days=settings.reference_days - 1) if reference_start else None
    reference = [d for d in series if reference_start <= date.fromisoformat(d["date"]) <= reference_end] if reference_start else []
    cur, prev, ref = level(current), level(previous), level(reference)
    days = (cutoff - start).days + 1
    valid_days = sum(d["ax"] is not None and d["ay"] is not None for d in current)
    reference_valid = sum(d["ax"] is not None and d["ay"] is not None for d in reference)
    reference_ready = bool(reference_end and reference_end <= cutoff and reference_valid >= math.ceil(settings.reference_days * settings.min_day_coverage))
    enough = valid_days >= max(4, math.ceil(days * settings.min_day_coverage))
    dx, dy = delta(cur["ax"], ref["ax"]), delta(cur["ay"], ref["ay"])
    baseline_shift = distance(dx, dy) if reference_ready else None
    sx, sy = slope(current, "ax"), slope(current, "ay")
    speed = distance(sx, sy)
    consistency = direction_consistency(current, sx, sy)
    persistent = bool(enough and reference_ready and baseline_shift is not None and
                      baseline_shift >= settings.angle_change_deg and speed is not None and
                      speed >= settings.trend_deg_week and consistency is not None and
                      consistency >= settings.consistency)
    angle_max = max(abs(cur["ax"]), abs(cur["ay"])) if cur["ax"] is not None and cur["ay"] is not None else None
    angle_attention = angle_max >= settings.angle_limit_deg if settings.angle_limit_deg is not None and angle_max is not None else None
    distance_attention = cur["distance"] >= settings.distance_limit_mm if settings.distance_limit_mm is not None and cur["distance"] is not None else None
    quality = "可评估" if enough and reference_ready else "当前周期数据不足" if not enough else "参考时期数据不足"
    reference_changed = baseline_shift is not None and baseline_shift >= settings.angle_change_deg
    status = "持续变化" if persistent else "参考偏移" if reference_changed and enough else quality
    temperature_pairs = [(d["temperature"], distance(delta(d["ax"], ref["ax"]), delta(d["ay"], ref["ay"]))) for d in current]
    temperature_pairs = [(a, b) for a, b in temperature_pairs if a is not None and b is not None]
    temperature_r = correlation(*zip(*temperature_pairs)) if len(temperature_pairs) >= 4 else None
    times = sorted(datetime.fromisoformat(r["event_time"]) for r in records if r["message_type"] == "Heartbeat" and start.isoformat() <= r["event_time"][:10] <= cutoff.isoformat())
    largest_gap = max(((b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])), default=None)
    for day in series:
        day["angle_change"] = distance(delta(day["ax"], ref["ax"]), delta(day["ay"], ref["ay"])) if reference_ready else None
        day["distance_change"] = distance(delta(day["dx"], ref["dx"]), delta(day["dy"], ref["dy"])) if reference_ready else None
    return {
        **metadata, "series": series, "monthly_matrix": monthly_matrix(series), "current": cur, "previous": prev, "reference": ref,
        "reference_start": reference_start.isoformat() if reference_start else None,
        "reference_end": reference_end.isoformat() if reference_end else None,
        "baseline_shift_deg": baseline_shift,
        "period_change_x": delta(cur["ax"], prev["ax"]), "period_change_y": delta(cur["ay"], prev["ay"]),
        "period_change_deg": distance(delta(cur["ax"], prev["ax"]), delta(cur["ay"], prev["ay"])),
        "distance_change_mm": distance(delta(cur["dx"], ref["dx"]), delta(cur["dy"], ref["dy"])) if reference_ready else None,
        "slope_x_week": sx, "slope_y_week": sy, "trend_deg_week": speed,
        "consistency": consistency, "persistent": persistent, "quality": quality,
        "reference_changed": reference_changed, "status": status,
        "valid_days": valid_days, "day_coverage": valid_days / days,
        "angle_attention": angle_attention, "distance_attention": distance_attention,
        "angle_max_deg": angle_max, "temperature_r": temperature_r, "largest_gap_hours": largest_gap,
        "alarm_count": sum(r["message_type"] == "Alarm" and start.isoformat() <= r["event_time"][:10] <= cutoff.isoformat() for r in records),
        "gap_attention": largest_gap is not None and largest_gap > metadata["expected_hours"] * 1.5,
        "last_time": max((r["event_time"] for r in records), default=None),
    }


def common_changes(a, b, start):
    ad = {d["date"]: d for d in a["series"] if d["date"] >= start.isoformat()}
    bd = {d["date"]: d for d in b["series"] if d["date"] >= start.isoformat()}
    paired = [(ad[t]["angle_change"], bd[t]["angle_change"]) for t in sorted(ad.keys() & bd.keys())]
    paired = [(x, y) for x, y in paired if x is not None and y is not None]
    return correlation(*zip(*paired)) if len(paired) >= 4 else None


def inward_fraction(members, aspect=1):
    if len(members) < 2 or not all(d["axis_confirmed"] and d["x_sign"] != 0 and d["y_sign"] != 0 for d in members):
        return None
    cx = statistics.mean(d["x"] for d in members)
    cy = statistics.mean(d["y"] for d in members)
    signs = []
    for device in members:
        ax, ay = device["period_change_x"], device["period_change_y"]
        if ax is None or ay is None:
            return None
        angle = math.radians(device["rotation_deg"])
        ax, ay = ax * device["x_sign"], ay * device["y_sign"]
        vx = ax * math.cos(angle) - ay * math.sin(angle)
        vy = -(ax * math.sin(angle) + ay * math.cos(angle))
        tx, ty = (cx - device["x"]) * aspect, cy - device["y"]
        if math.hypot(vx, vy) > 1e-12 and math.hypot(tx, ty) > 1e-12:
            signs.append(vx * tx + vy * ty > 0)
    return statistics.mean(signs) if len(signs) >= 2 else None


def regions(devices, settings, start, aspect=1):
    groups = defaultdict(list)
    for device in devices:
        if device["group"] and device["x"] is not None and device["y"] is not None:
            groups[device["group"]].append(device)
    findings = []
    for group, all_members in groups.items():
        members = [d for d in all_members if d["persistent"]]
        pairs = []
        for a, b in combinations(members, 2):
            r = common_changes(a, b, start)
            if r is not None and r >= settings.common_correlation:
                pairs.append({"a": a["id"], "b": b["id"], "correlation": r})
        participating = {p[k] for p in pairs for k in ["a", "b"]}
        if len(participating) < 2:
            continue
        selected = [d for d in members if d["id"] in participating]
        inward = inward_fraction(selected, aspect)
        findings.append({
            "group": group, "members": sorted(participating), "pairs": pairs,
            "x": statistics.mean(d["x"] for d in selected), "y": statistics.mean(d["y"] for d in selected),
            "direction_supported": inward is not None and inward >= settings.consistency,
            "inward_fraction": inward,
            "evidence": "多点持续变化且同期变化幅值相关；位置来自配置点组。",
            "missing": "安装轴向未完整确认，不能判断是否向同一位置倾斜。" if inward is None else "方向已按配置转换；仍需确认货架连接关系和地面高程变化。",
            "interpretation": "疑似局部沉降线索，待现场复测；温度、载荷和安装调整也可能形成类似变化。",
        })
    return sorted(findings, key=lambda r: -len(r["members"]))


def analyze(warehouse, records, cycle="week", cutoff=None):
    if not records:
        raise ValueError("请先导入 Excel 数据")
    settings = Settings(**warehouse["settings"])
    last_date = max(r["event_time"][:10] for r in records)
    cutoff = date.fromisoformat(cutoff or last_date)
    if cutoff.isoformat() > last_date:
        raise ValueError(f"报告截止日期不能晚于最新数据日期 {last_date}")
    if settings.reference_start:
        try:
            reference_date = date.fromisoformat(settings.reference_start)
        except ValueError:
            raise ValueError("参考时期日期格式错误") from None
        if reference_date + timedelta(days=settings.reference_days - 1) > cutoff:
            raise ValueError("参考时期尚未结束，请调整参考日期或报告截止日期")
    days = 7 if cycle == "week" else 30
    start = cutoff - timedelta(days=days - 1)
    previous_start = start - timedelta(days=days)
    included = [r for r in records if r["event_time"][:10] <= cutoff.isoformat()]
    if not included:
        raise ValueError("截止日期之前没有数据")
    by_device = defaultdict(list)
    for row in included:
        by_device[row["name"]].append(row)
    devices = [summarize_device(d, by_device[d["id"]], settings, start, cutoff, previous_start) for d in warehouse["devices"]]
    devices.sort(key=lambda d: (not d["persistent"], -(d["baseline_shift_deg"] or 0), d["id"]))
    region_findings = regions(devices, settings, start, warehouse.get("layout_aspect", 1))
    checks, matches = 0, 0
    for r in included:
        values = [r.get(k) for k in ["angle_x", "angle_y", "x_init_displacement", "y_init_displacement", "x_displacement", "y_displacement"]]
        if all(v is not None for v in values) and abs(values[0]) + abs(values[1]) > 1e-6:
            ax, ay, ix, iy, dx, dy = values
            checks += 1
            matches += abs(dx - ix - 10000 * math.tan(math.radians(ax))) < 0.001 and abs(dy - iy - 10000 * math.tan(math.radians(ay))) < 0.001
    source_hint = "位移数值符合10米倾角换算；来源与初始偏移含义待确认，暂不作为独立沉降证据。" if checks >= 10 and matches / checks > 0.95 else "位移来源需确认；二维距离只表示输入位移的合成结果。"
    notes = [source_hint, "区域结果是沉降调查线索，不提供地面沉降深度或事故发生概率。",
             "参考时期仅作为比较起点，未认定为安全状态。",
             "趋势使用心跳的日中位数；报警帧单独计数，避免重复报警改变日统计权重。",
             "分析敏感度为原型演示设置；角度与二维距离业务阈值分别配置，不沿用原表IT合成分级。"]
    first_month = date.fromisoformat(min(r["event_time"][:10] for r in included)).replace(day=1)
    history_months = []
    while first_month <= cutoff:
        history_months.append(first_month.isoformat()[:7])
        first_month = date(first_month.year + (first_month.month == 12), first_month.month % 12 + 1, 1)
    sources = {}
    for imported in reversed(warehouse["imports"]):
        sources.setdefault(imported["hash"], {"filename": imported["filename"], "hash": imported["hash"], "import_id": imported["id"]})
    return {
        "algorithm_version": VERSION, "warehouse_id": warehouse["id"], "warehouse_name": warehouse["name"],
        "cycle": cycle, "days": days, "start": start.isoformat(), "cutoff": cutoff.isoformat(),
        "previous_start": previous_start.isoformat(), "previous_end": (start - timedelta(days=1)).isoformat(),
        "settings": settings.model_dump(), "devices": devices, "regions": region_findings,
        "history_months": history_months, "layout_aspect": warehouse.get("layout_aspect", 1),
        "layout_path": warehouse["layout"], "notes": notes,
        "sources": list(sources.values()),
        "quality": {"records": len(included), "heartbeat": sum(r["message_type"] == "Heartbeat" for r in included),
                    "alarms": sum(r["message_type"] == "Alarm" for r in included),
                    "missing_displacement": sum(r.get("x_displacement") is None or r.get("y_displacement") is None for r in included),
                    "unmapped": sum(d["x"] is None or d["y"] is None for d in devices),
                    "axes_unknown": sum(not d["axis_confirmed"] for d in devices),
                    "large_gaps": sum(d["gap_attention"] for d in devices),
                    "insufficient": sum(d["quality"] != "可评估" for d in devices)},
        "counts": {"devices": len(devices), "reference_changes": sum(d["reference_changed"] for d in devices),
                   "persistent": sum(d["persistent"] for d in devices), "regions": len(region_findings)},
    }
