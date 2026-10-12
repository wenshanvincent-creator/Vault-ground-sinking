"""Render only the knowledge and follow-up frozen inside a report."""
from reportlab.platypus import PageBreak, Spacer

from .tracking import CONCLUSION, STATUS

DEVICE_TOPICS = {"position": "点位位置", "axis": "安装轴向", "height": "货架高度", "group": "空间点组",
                 "installation": "安装日期", "connections": "连接关系", "cadence": "上报周期"}
PROFILE_TOPICS = {"layout": "布局图", "ground_reference": "地面基准", "connections": "整体连接关系",
                  "reference": "固定参考时期", "threshold": "业务门槛", "timezone": "时间口径"}
OUTCOMES = {"triggered": "触发", "not_triggered": "未再次触发", "unavailable": "无法评估", "observed": "人工追踪已复看"}
LABELS = {**DEVICE_TOPICS, **PROFILE_TOPICS, "x": "位置X", "y": "位置Y", "label": "显示名", "group": "点组",
          "height_mm": "高度mm", "expected_hours": "周期h", "axis_confirmed": "轴向确认", "rotation_deg": "旋转角",
          "x_sign": "X符号", "y_sign": "Y符号", "installed_on": "安装日期", "notes": "备注", "evidence": "资料依据",
          "status": "状态", "source": "来源", "confirmed_on": "确认日期", "confirmed_by": "确认人",
          "reference_start": "参考开始", "reference_days": "参考天数", "threshold_basis": "门槛依据",
          "source_timezone": "时间口径", "angle_change_deg": "参考变化条件", "trend_deg_week": "趋势条件",
          "consistency": "一致率", "min_day_coverage": "覆盖率", "common_correlation": "相关性条件",
          "angle_limit_deg": "角度门槛", "distance_limit_mm": "距离门槛"}


def changes(before, after, path=""):
    if before == after:
        return []
    if isinstance(before, dict) or isinstance(after, dict):
        before, after = before or {}, after or {}
        result = []
        for key in sorted(before.keys() | after.keys()):
            name = LABELS.get(key, key)
            result.extend(changes(before.get(key), after.get(key), f"{path} / {name}" if path else name))
        return result
    return [f"{path or '内容'}：{before if before is not None else '未填写'} → {after if after is not None else '未填写'}"]


def stamp_row(target, label, value, stamp):
    stamp = stamp or {}
    state = {"unknown": "待确认" if value else "未填写", "inferred": "推测", "confirmed": "已确认"}.get(stamp.get("status", "unknown"), "待确认")
    confirmation = " / ".join(str(x) for x in (stamp.get("confirmed_on"), stamp.get("confirmed_by")) if x)
    return [target, label, value or "未填写", state, (stamp.get("source") or "尚无依据") + ("；" + confirmation if confirmation else "")]


def knowledge_sections(result, paragraph, table):
    body = [PageBreak(), paragraph("现场资料与待确认事项", "Heading1"),
            paragraph("资料按生成时保存。推测与确认分开记录；资料确认不等于工程安全认证。修改现场值后需要重新核对。")]
    profile, settings = result.get("profile", {}), result["settings"]
    profile_values = {"layout": "已上传布局图" if result.get("layout_path") else "", "ground_reference": profile.get("ground_reference"),
                      "connections": profile.get("connections"), "reference": f"{settings['reference_start']} 开始，{settings['reference_days']}天" if settings["reference_start"] else "",
                      "threshold": settings["threshold_basis"], "timezone": settings["source_timezone"]}
    rows = [["范围", "资料", "当前内容", "状态", "依据 / 确认"]]
    for key, label in PROFILE_TOPICS.items():
        rows.append(stamp_row("仓库", label, profile_values[key], profile.get("evidence", {}).get(key)))
    body.extend([table(rows, [40, 68, 143, 48, 212]), paragraph("现场备注：" + (profile.get("notes") or "尚未填写"))])
    body.extend([Spacer(1, 14), paragraph("设备安装档案", "Heading2")])
    rows = [["设备", "资料", "当前内容", "状态", "依据 / 确认"]]
    for device in result["devices"]:
        values = {"position": f"图上 X {device['x']*100:.1f}%，Y {device['y']*100:.1f}%" if device["x"] is not None and device["y"] is not None else "",
                  "axis": f"旋转 {device['rotation_deg']}°，符号 {device['x_sign']} / {device['y_sign']}",
                  "height": f"{device['height_mm']/1000:g}米" if device["height_mm"] else "", "group": device["group"],
                  "installation": device.get("installed_on"), "connections": device.get("connections"), "cadence": f"{device['expected_hours']:g}小时"}
        for key, label in DEVICE_TOPICS.items():
            rows.append(stamp_row(device["label"] or device["id"], label, values[key], device.get("evidence", {}).get(key)))
    body.append(table(rows, [40, 68, 143, 48, 212]))
    body.extend([Spacer(1, 14), paragraph("首次现场验证优先补充", "Heading2"),
        paragraph("核对安装轴向及照片；记录支脚间距、锚固和货架连接；选定稳定高程基准并在同一测点复测；记录载荷、安装和校准调整的时间；确认检查责任人与复测安排。"),
        paragraph("布局百分比坐标用于展示，不能代替现场米制距离。沉降量反推模型和工程门槛需要现场验证后再确定。")])
    events = result.get("archive_events", [])
    if events:
        body.extend([PageBreak(), paragraph("资料与参数修改历史", "Heading1")])
        for event in reversed(events):
            body.append(paragraph(f"{event['created']} · {event['target']}", "Heading2"))
            if event["kind"] == "site_event":
                p = event["payload"]
                types = {"load": "载荷调整", "installation": "安装 / 更换", "calibration": "校准", "collision": "碰撞", "maintenance": "维修", "other": "其他"}
                certainty = {"unknown": "待核实", "inferred": "推测", "confirmed": "有依据确认"}
                body.extend([paragraph(f"实际日期：{p['event_on']}；{types[p['event_type']]}；记录人：{p['recorded_by']}"),
                             paragraph("内容：" + p["description"]), paragraph("关联设备：" + ("、".join(p["members"]) or "未关联")),
                             paragraph(f"可信程度：{certainty[p['certainty']]}；依据：{p['source'] or '未提供'}"),
                             paragraph("现场变更记录不自动认定为倾斜原因。")])
                continue
            for text in changes(event["payload"]["before"], event["payload"]["after"]):
                body.append(paragraph(text))
    return body


def tracking_sections(result, paragraph, fmt):
    body = [PageBreak(), paragraph("异常追踪与检查快照", "Heading1"),
            paragraph("处理、检查及附件目录截至本报告生成时间（UTC）：" + result["created"]),
            paragraph("检查日期可能晚于传感器评估截止日期，以各条记录为准。后续添加内容不改变旧报告。模拟案例不纳入本报告。")]
    if "tracking" not in result:
        return body + [paragraph("这份旧报告没有保存追踪快照。生成新评估后开始记录。")]
    if not result["tracking"]:
        return body + [paragraph("生成时尚无真实追踪事项。")]
    for issue in result["tracking"]:
        if issue.get("is_demo"):
            continue
        body.extend([Spacer(1, 12), paragraph(issue["title"], "Heading2"), paragraph("处理状态：" + STATUS[issue["status"]]),
                     paragraph("关联设备：" + "、".join(issue["members"])),
                     paragraph(f"首次触发：{issue['first_detected'] or '未记录'}；最近触发：{issue['last_detected'] or '未记录'}"),
                     paragraph("档案编号：" + issue["id"])])
        if issue.get("recheck_needed"):
            body.append(paragraph("处理后再次触发分析条件，待复核；原处理状态保留。"))
        for event in issue["events"]:
            d = event["data"]
            body.append(paragraph("记录时间（UTC）：" + event["created"]))
            if event["kind"] == "assessment":
                body.extend([paragraph(f"评估 {d['start']} 至 {d['cutoff']}：{OUTCOMES[d['outcome']]}"), paragraph(d["reason"]),
                             paragraph("当次报告：" + event["report_id"]),
                             paragraph(f"当次条件：参考变化≥{d['settings']['angle_change_deg']}°；趋势≥{d['settings']['trend_deg_week']}°/周；一致率≥{d['settings']['consistency']}；共同相关≥{d['settings']['common_correlation']}；算法 {d['algorithm_version']}")])
                measurements = d.get("measurements", {})
                if isinstance(measurements, list):
                    for point in measurements:
                        body.append(paragraph(f"设备 {point['id']}：{point['status']}；参考变化 {fmt(point['baseline_shift_deg'])}°；趋势 {fmt(point['trend_deg_week'])}°/周"))
                elif "pairs" in measurements:
                    for pair in measurements["pairs"]:
                        body.append(paragraph(f"设备 {pair['a']} / {pair['b']}：相关系数 {pair['correlation']:.3f}"))
                    body.append(paragraph(measurements["missing"]))
                else:
                    body.append(paragraph(f"参考变化 {fmt(measurements.get('baseline_shift_deg'))}°；趋势 {fmt(measurements.get('trend_deg_week'))}°/周；方向一致率 {fmt(measurements.get('consistency'), 2)}；有效 {measurements.get('valid_days')}天；参考 {measurements.get('reference_start')} 至 {measurements.get('reference_end')}"))
            elif event["kind"] == "handling":
                body.extend([paragraph(f"{STATUS[d['before']]} → {STATUS[d['after']]}；处理人：{d['author']}"), paragraph(d["note"])])
            elif event["kind"] == "inspection":
                body.append(paragraph(f"检查日期 {d['checked_on']}；检查人 {d['inspector']}；{CONCLUSION[d['conclusion']]}"))
                for key, label in [("location", "位置"), ("observation", "观察"), ("action", "措施"), ("cause", "原因"), ("basis", "依据"), ("follow_up", "后续安排")]:
                    body.append(paragraph(f"{label}：{d[key] or '尚未填写'}"))
                for attachment in event.get("attachments", []):
                    body.append(paragraph("附件：" + attachment["filename"] + "；SHA256：" + attachment["hash"]))
                if event.get("attachments"):
                    body.append(paragraph("PDF保存附件目录与校验值，原附件在网站对应检查记录中下载。"))
            else:
                body.append(paragraph(d["note"]))
                if d.get("report_id"):
                    body.append(paragraph("来源评估：" + d["report_id"]))
    return body
