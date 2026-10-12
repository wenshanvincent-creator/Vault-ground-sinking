import io
import os
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, PageBreak, Paragraph, SimpleDocTemplate,
                              Spacer, Table, TableStyle)

from .report_workflow import knowledge_sections, tracking_sections

BLUE = colors.HexColor("#245d79")
ORANGE = colors.HexColor("#b86d29")
INK = colors.HexColor("#243b47")
MUTED = colors.HexColor("#637b89")
PALE = colors.HexColor("#eef3f5")


def font():
    if "VaultCJK" in pdfmetrics.getRegisteredFontNames():
        return "VaultCJK"
    candidates = [os.environ.get("VAULT_REPORT_FONT"), r"C:\Windows\Fonts\msyh.ttc",
                  "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf"]
    for path in candidates:
        if path and Path(path).exists():
            pdfmetrics.registerFont(TTFont("VaultCJK", path, subfontIndex=0))
            return "VaultCJK"
    raise ValueError("PDF需要中文字体。请通过 VAULT_REPORT_FONT 指定可嵌入的中文 TTF/TTC 字体。")


def fmt(value, digits=3):
    return "缺数据" if value is None else f"{value:.{digits}f}"


def attention(value, threshold, measurement):
    if threshold is None:
        return "未设门槛"
    if measurement is None:
        return "缺数据"
    return "达到关注门槛" if value else "未达门槛"


class LayoutMap(Flowable):
    def __init__(self, result, width=510):
        from PIL import Image as PILImage
        self.result = result
        self.width = width
        with PILImage.open(result["layout_path"]) as image:
            self.height = width * image.height / image.width

    def draw(self):
        self.canv.drawImage(self.result["layout_path"], 0, 0, width=self.width, height=self.height)
        members = {d for r in self.result["regions"] for d in r["members"]}
        for device in self.result["devices"]:
            if device["x"] is None or device["y"] is None:
                continue
            self.canv.setStrokeColor(ORANGE if device["id"] in members else BLUE)
            self.canv.setLineWidth(2)
            self.canv.circle(device["x"] * self.width, (1 - device["y"]) * self.height, 9, stroke=1, fill=0)


def chart(device, fields, labels, width=510, height=155):
    drawing = Drawing(width, height)
    series = device["series"]
    usable = [d for d in series if any(d.get(field) is not None for field in fields)]
    if not usable:
        drawing.add(String(20, height / 2, "无可用数据", fontName=font(), fontSize=10, fillColor=MUTED))
        return drawing
    x0 = date.fromisoformat(series[0]["date"]).toordinal()
    x1 = date.fromisoformat(series[-1]["date"]).toordinal()
    values = [d[field] for d in series for field in fields if d[field] is not None]
    low, high = min(values), max(values)
    pad = max((high - low) * 0.12, 0.001 if fields[0] == "ax" else 0.1)
    low, high = low - pad, high + pad
    left, bottom, right, top = 60, 30, width - 12, height - 28
    def px(day):
        return left + (date.fromisoformat(day).toordinal() - x0) / max(1, x1 - x0) * (right - left)
    def py(value):
        return bottom + (value - low) / (high - low) * (top - bottom)
    for tick in range(4):
        value = low + (high - low) * tick / 3
        y = py(value)
        drawing.add(Line(left, y, right, y, strokeColor=colors.HexColor("#dce5e9"), strokeWidth=0.5))
        drawing.add(String(left - 7, y - 3, fmt(value, 3 if fields[0] == "ax" else 1), textAnchor="end", fontName=font(), fontSize=8, fillColor=MUTED))
    for tick in range(3):
        ordinal = round(x0 + (x1 - x0) * tick / 2)
        label = date.fromordinal(ordinal).isoformat()
        drawing.add(String(left + (right - left) * tick / 2, 10, label, textAnchor="middle", fontName=font(), fontSize=8, fillColor=MUTED))
    for index, (field, label) in enumerate(zip(fields, labels)):
        color = [BLUE, ORANGE][index % 2]
        drawing.add(String(left + index * 145, height - 12, label, fontName=font(), fontSize=9, fillColor=color))
        path, previous = [], None
        for day in series:
            value = day[field]
            ordinal = date.fromisoformat(day["date"]).toordinal()
            if value is None or (previous is not None and ordinal - previous > 2):
                if len(path) >= 4:
                    drawing.add(PolyLine(path, strokeColor=color, strokeWidth=1.2))
                path = []
            if value is not None:
                path.extend([px(day["date"]), py(value)])
                previous = ordinal
            else:
                previous = None
        if len(path) >= 4:
            drawing.add(PolyLine(path, strokeColor=color, strokeWidth=1.2))
    return drawing


def build_pdf(result):
    cjk = font()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = cjk
        style.wordWrap = "CJK"
        style.textColor = INK
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 15
    styles["Title"].fontSize = 25
    styles["Title"].leading = 34
    styles["Title"].alignment = 0
    styles["Heading1"].fontSize = 17
    styles["Heading1"].leading = 24
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 19
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=12)
    def paragraph(text, style="Normal"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])
    def table(rows, widths=None):
        wrapped = [[Paragraph(escape(str(v)), small) for v in row] for row in rows]
        item = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT", splitInRow=1)
        item.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, BLUE),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dce5e9")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return item
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=46, bottomMargin=44,
                            title=f"{result['warehouse_name']} 周期沉降线索评估", author="仓库周期评估系统")
    body = [paragraph("仓库周期评估", "Title"), paragraph(result["warehouse_name"], "Heading1"),
            paragraph(f"评估周期：{result['start']} 至 {result['cutoff']}（最近{result['days']}天）"),
            paragraph(f"比较周期：{result['previous_start']} 至 {result['previous_end']}"),
            Spacer(1, 18), paragraph("本周期主要发现", "Heading1")]
    counts = result["counts"]
    body.append(paragraph(f"共{counts['devices']}个设备，{counts.get('reference_changes','未记录')}个点存在长期参考差异，{counts['persistent']}个点满足近期持续变化演示条件，{counts['regions']}个点组形成疑似沉降线索。"))
    body.append(paragraph("长期参考差异只表示与起始时期不同。安装调试、校准、载荷调整与真实变形都可能造成差异，需结合历史记录核查。"))
    if not result["regions"]:
        body.append(paragraph("本周期没有满足当前分析条件的区域线索；不代表不存在沉降。"))
    for region in result["regions"]:
        body.extend([paragraph(region["group"], "Heading2"), paragraph("关联设备：" + "、".join(region["members"])),
                     paragraph(region["evidence"]), paragraph(region["missing"]), paragraph(region["interpretation"])])
    if result.get("layout_path"):
        body.extend([Spacer(1, 12), paragraph("点位与区域", "Heading2"), LayoutMap(result),
                     paragraph("橙色圈表示区域线索成员，蓝色圈表示其他已定位点。")])
    body.extend([Spacer(1, 12), paragraph("待检查事项", "Heading2")])
    if result["regions"]:
        body.append(paragraph("优先复核上述点组的安装、载荷、立柱和支脚状况；如需确认沉降，补充相对于稳定基准的地面高程复测。"))
    else:
        body.append(paragraph("复核持续变化点及数据不足点；按需调整分析敏感度并补充点位和安装资料。"))
    body.extend([PageBreak(), paragraph("设备比较与数据质量", "Heading1")])
    rows = [["设备", "点组", "参考变化°", "趋势°/周", "二维距离mm", "可用天数", "状态"]]
    for d in result["devices"]:
        rows.append([d["label"] or d["id"], d["group"] or "未分组", fmt(d["baseline_shift_deg"]), fmt(d["trend_deg_week"]),
                     fmt(d["current"]["distance"], 2), f"{d['valid_days']}/{result['days']}", d.get("status", d["quality"])])
    body.append(table(rows, [43, 76, 68, 68, 76, 65, 115]))
    q = result["quality"]
    body.extend([Spacer(1, 12), paragraph(f"截止日期内共{q['records']}条记录（心跳{q['heartbeat']}，报警{q['alarms']}）；其中{q['missing_displacement']}条缺少双轴位移。"),
                 paragraph(f"未定位{q['unmapped']}个设备；轴向未确认{q['axes_unknown']}个；数据不足{q['insufficient']}个。"),
                 paragraph("按导出本地日期分组。时区说明：" + result["settings"]["source_timezone"]),
                 paragraph("业务关注阈值", "Heading2"),
                 paragraph("角度：" + (fmt(result["settings"]["angle_limit_deg"]) + "°" if result["settings"]["angle_limit_deg"] is not None else "未设置")),
                 paragraph("二维距离：" + (fmt(result["settings"]["distance_limit_mm"], 2) + "mm" if result["settings"]["distance_limit_mm"] is not None else "未设置")),
                 paragraph("阈值依据：" + (result["settings"]["threshold_basis"] or "尚未提供"))])
    body.extend(tracking_sections(result, paragraph, fmt))
    body.extend(knowledge_sections(result, paragraph, table))
    dates = [(date.fromisoformat(result["start"]) + timedelta(days=i)).isoformat() for i in range(result["days"])]
    for field, heading, digits in [("angle_change", "角度变化矩阵（双轴变化幅值，度）", 3),
                                    ("distance_change", "水平位置变化矩阵（二维距离，mm）", 2)]:
        for offset in range(0, len(dates), 7):
            columns = dates[offset:offset + 7]
            body.extend([PageBreak(), paragraph(heading, "Heading1"), paragraph("相对于各设备参考时期；缺数据保持为空，不填零。")])
            matrix = [["设备"] + [s[5:] for s in columns]]
            for device in result["devices"]:
                lookup = {d["date"]: d for d in device["series"]}
                matrix.append([device["label"] or device["id"]] + [fmt(lookup.get(s, {}).get(field), digits) for s in columns])
            body.append(table(matrix, [60] + [451 / len(columns)] * len(columns)))
    months = result.get("history_months", [])
    for field, heading, digits in [("angle_change", "完整历史月度矩阵：角度变化（度）", 3),
                                    ("distance_change", "完整历史月度矩阵：水平位置变化（mm）", 2)]:
        for offset in range(0, len(months), 7):
            columns = months[offset:offset + 7]
            body.extend([PageBreak(), paragraph(heading, "Heading1"),
                         paragraph("每格为该月日统计值的中位数；相对于参考时期。首末月可能只有部分日期，缺失月份不填零。")])
            matrix = [["设备"] + columns]
            for device in result["devices"]:
                lookup = {d["date"]: d for d in device.get("monthly_matrix", [])}
                matrix.append([device["label"] or device["id"]] + [fmt(lookup.get(s, {}).get(field), digits) for s in columns])
            body.append(table(matrix, [60] + [451 / len(columns)] * len(columns)))
    for device in result["devices"]:
        body.extend([PageBreak(), paragraph(f"设备 {device['label'] or device['id']} · 完整历史", "Heading1"),
                     paragraph(f"点组：{device['group'] or '未分组'}；参考时期：{device['reference_start']} 至 {device['reference_end']}；当前：{device['quality']}"),
                     paragraph("双轴角度（日中位数）", "Heading2"), chart(device, ["ax", "ay"], ["X轴角度（度）", "Y轴角度（度）"], height=135),
                     paragraph("合成水平位移（日中位数）", "Heading2"), chart(device, ["distance", "legacy"], ["二维距离（mm）", "原表绝对值之和（mm）"], height=135),
                     paragraph("温度（日中位数）", "Heading2"), chart(device, ["temperature"], ["温度（摄氏度）"], height=110),
                     paragraph(f"参考角度变化：{fmt(device['baseline_shift_deg'])}°；趋势强度：{fmt(device['trend_deg_week'])}°/周；方向一致率：{fmt(device['consistency'],2)}"),
                     paragraph(f"当前X/Y角度：{fmt(device['current']['ax'])}° / {fmt(device['current']['ay'])}°；当前二维距离：{fmt(device['current']['distance'],2)}mm"),
                     paragraph(f"当前周期报警帧：{device['alarm_count']}；心跳内部最大间隔：{fmt(device['largest_gap_hours'],1)}小时；预期周期：{device['expected_hours']}小时"),
                     paragraph("心跳间隔超过预期的1.5倍，需核查数据连续性。" if device.get("gap_attention") else "心跳间隔未形成超过预期1.5倍的提示；周期边界由可用天数另行检查。"),
                     paragraph("温度关联系数：" + fmt(device["temperature_r"], 2) + "（仅为关联，不自动修正角度）"),
                     paragraph("角度关注：" + attention(device["angle_attention"], result["settings"]["angle_limit_deg"], device["angle_max_deg"]) +
                               "；二维距离关注：" + attention(device["distance_attention"], result["settings"]["distance_limit_mm"], device["current"]["distance"]))])
    body.extend([PageBreak(), paragraph("方法、参数与来源", "Heading1")])
    for note in result["notes"]:
        body.append(paragraph(note))
    body.append(paragraph("分析条件", "Heading2"))
    labels = {"reference_start": "指定参考日期", "reference_days": "参考天数", "angle_change_deg": "参考角度变化条件（度）",
              "trend_deg_week": "近期趋势强度条件（度/周）", "consistency": "方向一致率", "min_day_coverage": "最低可用天数比例",
              "common_correlation": "共同变化相关系数条件", "angle_limit_deg": "最大轴角度业务门槛（度）",
              "distance_limit_mm": "二维距离业务门槛（mm）", "threshold_basis": "业务门槛依据", "source_timezone": "导出时间口径"}
    for key, value in result["settings"].items():
        if key == "reference_start" and value is None:
            value = "各设备最早数据覆盖充分的时期"
        body.append(paragraph(f"{labels[key]}：{'未设置' if value is None else value}"))
    body.extend([paragraph(f"算法版本：{result['algorithm_version']}；报告编号：{result['id']}"),
                 paragraph("生成时间（UTC）：" + result["created"]), paragraph("源文件与校验值", "Heading2")])
    for source in result["sources"]:
        body.append(paragraph(source["filename"]))
        body.append(paragraph(source["hash"]))
    def footer(canvas, document):
        canvas.setFont(cjk, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(42, 25, result["warehouse_name"][:35] + " · " + result["cutoff"])
        canvas.drawRightString(A4[0] - 42, 25, str(document.page))
    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
