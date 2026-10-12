import { escape as e, number as n } from "./helpers.js";

export const statusLabels = {
  pending: "待查看",
  inspection: "待检查",
  observing: "观察中",
  resolved: "已处理",
};
const conclusions = {
  unknown: "尚不清楚",
  suspected: "怀疑原因",
  confirmed: "已确认原因",
};
const outcomes = {
  triggered: "本期触发",
  not_triggered: "本期未再次触发",
  unavailable: "本期无法评估",
  observed: "本期已复看",
};
const deviceTopics = {
  position: "点位位置",
  axis: "安装轴向",
  height: "货架高度",
  group: "空间点组",
  installation: "安装日期",
  connections: "货架连接",
  cadence: "预期上报周期",
};
const profileTopics = {
  layout: "布局图",
  ground_reference: "地面测量基准",
  connections: "整体连接关系",
  reference: "固定参考时期",
  threshold: "业务门槛依据",
  timezone: "导出时间口径",
};
const siteTypes = {
  load: "载荷调整",
  installation: "安装 / 设备更换",
  calibration: "校准",
  collision: "碰撞",
  maintenance: "维修",
  other: "其他",
};
const dateText = (value) =>
  e((value || "").replace("T", " ").replace("+00:00", " UTC"));
const optionList = (labels, value) =>
  Object.entries(labels)
    .map(
      ([key, label]) =>
        `<option value="${key}" ${key === value ? "selected" : ""}>${e(label)}</option>`,
    )
    .join("");
const area = (name, label, value = "", required = false) =>
  `<label class="wide">${label}<textarea name="${name}" rows="2" maxlength="4000" ${required ? "required" : ""}>${e(value)}</textarea></label>`;
const input = (name, label, value = "", type = "text", required = false) =>
  `<label>${label}<input name="${name}" type="${type}" value="${e(value ?? "")}" ${required ? "required" : ""}></label>`;

function evidenceEditor(topics, evidence, values) {
  return Object.entries(topics)
    .map(([key, label]) => {
      const stamp = evidence?.[key] || {};
      return `<fieldset class="evidence-card" data-evidence="${key}"><legend>${label}</legend><p class="small">当前资料：${e(values[key] || "未填写")}</p><div class="form-grid"><label>资料状态<select name="${key}.status">${optionList({ unknown: values[key] ? "待确认" : "未填写 / 待确认", inferred: "推测", confirmed: "已确认" }, stamp.status || "unknown")}</select></label>${input(key + ".confirmed_on", "确认日期", stamp.confirmed_on, "date")}${input(key + ".confirmed_by", "确认人", stamp.confirmed_by)}${area(key + ".source", "来源或依据", stamp.source)}</div></fieldset>`;
    })
    .join("");
}

export function readEvidence(form, topics) {
  const values = Object.fromEntries(new FormData(form));
  return Object.fromEntries(
    Object.keys(topics).map((key) => [
      key,
      {
        status: values[key + ".status"],
        source: values[key + ".source"] || "",
        confirmed_on: values[key + ".confirmed_on"] || null,
        confirmed_by: values[key + ".confirmed_by"] || "",
      },
    ]),
  );
}

export function deviceEvidence(form) {
  return readEvidence(form, deviceTopics);
}
export function profileEvidence(form) {
  return readEvidence(form, profileTopics);
}

export function deviceValues(device) {
  return {
    position:
      device.x == null || device.y == null
        ? ""
        : `图上 X ${(device.x * 100).toFixed(1)}%，Y ${(device.y * 100).toFixed(1)}%（非现场米制坐标）`,
    axis: `旋转 ${device.rotation_deg}°，X符号 ${device.x_sign}，Y符号 ${device.y_sign}`,
    height: device.height_mm ? `${device.height_mm / 1000} 米` : "",
    group: device.group,
    installation: device.installed_on,
    connections: device.connections,
    cadence: `${device.expected_hours} 小时`,
  };
}

function profileValues(warehouse) {
  const p = warehouse.profile || {},
    s = warehouse.settings;
  return {
    layout: warehouse.layout_url ? "已上传布局图" : "",
    ground_reference: p.ground_reference,
    connections: p.connections,
    reference: s.reference_start
      ? `${s.reference_start} 开始，${s.reference_days}天`
      : "",
    threshold: s.threshold_basis,
    timezone: s.source_timezone,
  };
}

const changeLabels = {
  x: "位置X",
  y: "位置Y",
  label: "显示名",
  group: "点组",
  height_mm: "高度mm",
  expected_hours: "心跳周期h",
  axis_confirmed: "轴向确认",
  rotation_deg: "旋转角",
  x_sign: "X符号",
  y_sign: "Y符号",
  installed_on: "安装日期",
  connections: "连接关系",
  ground_reference: "地面基准",
  notes: "备注",
  evidence: "资料依据",
  status: "状态",
  source: "来源",
  confirmed_on: "确认日期",
  confirmed_by: "确认人",
  reference_start: "参考日期",
  reference_days: "参考天数",
  angle_change_deg: "参考变化条件",
  trend_deg_week: "趋势条件",
  consistency: "一致率",
  min_day_coverage: "覆盖率",
  common_correlation: "相关性条件",
  angle_limit_deg: "角度门槛",
  distance_limit_mm: "距离门槛",
  threshold_basis: "门槛依据",
  source_timezone: "时间口径",
  ...deviceTopics,
  ...profileTopics,
};
export function changes(before, after, path = "") {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (
    (before && typeof before === "object") ||
    (after && typeof after === "object")
  ) {
    return [
      ...new Set([...Object.keys(before || {}), ...Object.keys(after || {})]),
    ].flatMap((key) =>
      changes(
        before?.[key],
        after?.[key],
        path
          ? path + " / " + (changeLabels[key] || key)
          : changeLabels[key] || key,
      ),
    );
  }
  return [`${path || "内容"}：${before ?? "未填写"} → ${after ?? "未填写"}`];
}

export function archiveView(warehouse, selected) {
  const p = warehouse.profile || {},
    device =
      warehouse.devices.find((d) => d.id === selected) || warehouse.devices[0];
  return `<div class="intro"><h2>逐步补齐现场知识</h2><p>允许资料未知。推测与确认分开记录；确认需要依据、日期和确认人。安装或配置改变后，旧确认不会自动沿用。</p></div>
  <div class="panel"><h2>首次现场验证清单</h2><ol class="checklist"><li>核对点位、安装轴向和符号，拍摄安装照片。</li><li>记录货架尺寸、支脚间距、锚固与连接关系。</li><li>选定稳定高程基准，记录地面测点位置、测量日期、数值和方法，之后在同一位置复测。</li><li>记录载荷变化、货架调整、传感器更换或校准的时间。</li><li>与管理员确认检查分工、处理状态及复测安排。</li></ol><a class="button secondary" href="/field-checklist.md" download="首次现场验证清单.md">下载现场记录模板</a></div>
  <form id="profile-form" class="panel"><h2>仓库资料</h2><div class="form-grid">${area("ground_reference", "地面高程基准与测点说明", p.ground_reference)}${area("connections", "整体货架连接关系", p.connections)}${area("notes", "现场资料备注", p.notes)}</div><details><summary>资料来源与确认状态</summary>${evidenceEditor(profileTopics, p.evidence, profileValues(warehouse))}</details><p class="config-help">固定参考日期和业务门槛的具体值在仓库配置中修改。确认资料不等于工程安全认证。</p><button class="button primary">保存仓库资料</button></form>
  <section class="panel"><div class="panel-head"><h2>设备安装资料</h2><label>选择设备<select id="archive-device">${warehouse.devices.map((d) => `<option value="${e(d.id)}" ${d.id === device?.id ? "selected" : ""}>${e(d.label || d.id)}</option>`).join("")}</select></label></div>${device ? `<form id="device-archive-form" data-id="${e(device.id)}"><div class="form-grid">${input("installed_on", "安装日期（未知可留空）", device.installed_on, "date")}${area("connections", "该点货架连接、锚固与支脚说明", device.connections)}</div><p class="config-help">位置、高度、分组和轴向数值在仓库配置中填写。当前轴向：${device.axis_confirmed ? "已确认，可参与方向示意" : "待确认，不能判断是否向中间倾斜"}。</p><details open><summary>安装资料来源与确认状态</summary>${evidenceEditor(deviceTopics, device.evidence, deviceValues(device))}</details><button class="button primary">保存设备资料</button> <button type="button" class="text-button" data-go="settings">编辑点位数值 ↗</button></form>` : '<p class="note">导入设备数据后即可建立安装资料。</p>'}</section>
  <section class="panel"><h2>载荷、安装与现场变更</h2><p class="note">即使没有异常，也可以记录变更。实际发生日期与录入时间分开保存，不自动当作倾斜原因。</p><details><summary>新增现场变更记录</summary><form id="site-event-form"><div class="form-grid">${input("event_on", "实际发生日期", "", "date", true)}<label>变更类型<select name="event_type">${optionList(siteTypes, "load")}</select></label>${input("location", "位置 / 范围", "", "text", true)}${input("recorded_by", "记录人", "", "text", true)}<label>记录可信程度<select name="certainty">${optionList({ unknown: "待核实", inferred: "推测", confirmed: "有依据确认" }, "unknown")}</select></label>${area("description", "发生了什么", "", true)}${area("source", "来源依据")}<div class="wide selection-list">关联设备（可不选）${warehouse.devices.map((d) => `<label><input type="checkbox" name="members" value="${e(d.id)}">${e(d.label || d.id)}</label>`).join("")}</div></div><button class="button primary">保存现场变更</button></form></details></section>
  <section class="panel"><h2>现场、资料与配置历史</h2>${
    (warehouse.archive_events || []).length
      ? warehouse.archive_events
          .map(
            (event) =>
              `<details class="timeline-item"><summary>${dateText(event.created)} · ${e(event.target)}${event.kind === "site_event" ? " · " + siteTypes[event.payload.event_type] : ""}</summary>${
                event.kind === "site_event"
                  ? `<p>实际日期：${e(event.payload.event_on)}；记录人：${e(event.payload.recorded_by)}</p><p>内容：${e(event.payload.description)}</p><p>关联设备：${event.payload.members.map(e).join("、") || "未关联"}</p><p>可信程度：${e({ unknown: "待核实", inferred: "推测", confirmed: "有依据确认" }[event.payload.certainty])}；依据：${e(event.payload.source || "未提供")}</p>`
                  : changes(event.payload.before, event.payload.after)
                      .map((text) => `<p class="note">${e(text)}</p>`)
                      .join("")
              }</details>`,
          )
          .join("")
      : '<p class="note">尚无修改记录。既有点位保留原值，未自动认定为已确认。</p>'
  }</section>`;
}

function measurementText(m) {
  if (!m) return "";
  if (Array.isArray(m))
    return m
      .map(
        (d) =>
          `设备${d.id}：${d.status}，参考变化 ${n(d.baseline_shift_deg)}°，趋势 ${n(d.trend_deg_week)}°/周`,
      )
      .join("；");
  if (m.pairs)
    return (
      m.pairs
        .map((p) => `${p.a} / ${p.b}：相关系数 ${n(p.correlation, 2)}`)
        .join("；") +
      "。" +
      (m.missing || "")
    );
  return `参考变化 ${n(m.baseline_shift_deg)}°；趋势 ${n(m.trend_deg_week)}°/周；方向一致率 ${n(m.consistency, 2)}；有效 ${m.valid_days}天；参考 ${m.reference_start} 至 ${m.reference_end}`;
}

function eventMarkup(event, warehouseId, issueId, interactive) {
  const d = event.data;
  let title, body;
  if (event.kind === "assessment") {
    title = `${d.start} 至 ${d.cutoff} · ${outcomes[d.outcome] || d.outcome}`;
    body = `<p>${e(d.reason)}</p><p class="note">${e(measurementText(d.measurements))}</p><details><summary>本次筛选条件</summary><p class="note">参考变化≥${n(d.settings.angle_change_deg)}°；趋势≥${n(d.settings.trend_deg_week)}°/周；一致率≥${n(d.settings.consistency, 2)}；共同相关≥${n(d.settings.common_correlation, 2)}；版本 ${e(d.algorithm_version)}</p></details>${interactive && event.report_id ? `<button class="text-button" data-report="${e(event.report_id)}">查看当次评估 ↗</button>` : ""}`;
  } else if (event.kind === "handling") {
    title = `${statusLabels[d.before]} → ${statusLabels[d.after]} · ${d.author}`;
    body = `<p>${e(d.note)}</p>`;
  } else if (event.kind === "inspection") {
    title = `检查 ${d.checked_on} · ${d.inspector} · ${conclusions[d.conclusion]}`;
    body = `<p>位置：${e(d.location)}</p><p>观察：${e(d.observation)}</p><p>措施：${e(d.action || "未填写")}</p><p>原因：${e(d.cause || "尚不清楚")}</p><p>依据：${e(d.basis || "尚未提供")}</p><p>后续：${e(d.follow_up || "未填写")}</p><div class="attachment-list">${(event.attachments || []).map((a) => `<a href="/api/warehouses/${e(warehouseId)}/issues/${e(issueId)}/attachments/${e(a.id)}">${e(a.filename)}</a><small>SHA256 ${e(a.hash)}</small>`).join("")}</div>${interactive ? `<label class="attachment-upload">补充附件<input type="file" data-attachment-event="${e(event.id)}" data-issue-id="${e(issueId)}" accept=".png,.jpg,.jpeg,.pdf,.csv,.txt" multiple></label>` : ""}`;
  } else {
    title = "追踪说明";
    body = `<p>${e(d.note)}</p>${interactive && d.report_id ? `<button class="text-button" data-report="${e(d.report_id)}">查看来源评估 ↗</button>` : ""}`;
  }
  return `<article class="timeline-item"><div class="small">记录时间 ${dateText(event.created)}</div><h3>${e(title)}</h3>${body}</article>`;
}

export function trackingView(
  warehouse,
  issues,
  selected,
  filter = "open",
  showDemo = false,
) {
  const filtered = issues.filter(
    (i) =>
      (showDemo || !i.is_demo) &&
      (filter !== "open" || i.status !== "resolved" || i.recheck_needed),
  );
  const issue = filtered.find((i) => i.id === selected) || filtered[0];
  return `<div class="intro"><h2>把每次发现接成持续的记录</h2><p>这里是当前处理档案。报告保留生成时的快照；补充检查后，生成新评估才会进入新的 PDF。低于筛选条件不会自动关闭异常。</p></div>
  <div class="panel"><div class="panel-head"><div class="chart-toolbar"><label>处理范围<select id="issue-filter">${optionList({ open: "待处理与观察中", all: "全部（含已处理）" }, filter)}</select></label><label><input type="checkbox" id="show-demo" ${showDemo ? "checked" : ""}>显示模拟案例</label></div><button class="button secondary" data-action="simulation">载入模拟流程案例</button></div><p class="small">模拟案例独立存放，不参与真实分析、真实事项计数或评估 PDF。</p></div>
  <div class="tracking-grid"><section class="panel issue-list"><h2>异常档案 · ${filtered.length}项</h2>${filtered.length ? filtered.map((i) => `<button class="issue-card ${i.id === issue?.id ? "selected" : ""}" data-issue="${e(i.id)}"><strong>${e(i.title)}</strong><span class="badge ${i.is_demo || i.recheck_needed ? "warning" : ""}">${i.is_demo ? "模拟案例 · " : ""}${statusLabels[i.status]}${i.recheck_needed ? " · 再次触发待复核" : ""}</span><small>${i.latest_assessment ? `${e(i.latest_assessment.cutoff)} · ${outcomes[i.latest_assessment.outcome]}` : "人工记录"}</small></button>`).join("") : '<p class="note">当前没有对应事项。生成新评估会建立触发事项，也可在点位详情中手动开始追踪。</p>'}</section>
  <section class="panel issue-detail">${
    issue
      ? `<div class="panel-head"><h2>${e(issue.title)}</h2><span class="badge">${statusLabels[issue.status]}</span></div>${issue.is_demo ? '<p class="demo-banner">全部内容为模拟流程，没有对应真实检查或测量。</p>' : ""}${issue.recheck_needed ? '<p class="demo-banner">处理后再次触发分析条件，请复核；原处理状态保留。</p>' : ""}<p class="note">首次触发：${e(issue.first_detected || "未记录自动触发")}；最近触发：${e(issue.last_detected || "未记录自动触发")}</p><div class="selection-list">${issue.members.map((id) => `<button class="text-button" data-device="${e(id)}">设备 ${e(id)} ↗</button>`).join("")}</div>
  <details open><summary>记录处理状态</summary><form id="handling-form" data-issue="${e(issue.id)}" data-version="${issue.version}"><div class="form-grid"><label>状态<select name="status">${optionList(statusLabels, issue.status)}</select></label>${input("author", "处理人", "", "text", true)}${area("note", "处理说明（包含本次动作或继续观察的理由）", "", true)}</div><button class="button primary">保存处理记录</button></form></details>
  <details><summary>新增现场检查</summary><form id="inspection-form" data-issue="${e(issue.id)}"><p class="note">允许原因未知。确认原因需要测量或检查依据；检查结论由记录人提供。</p><div class="form-grid">${input("checked_on", "检查日期", "", "date", true)}${input("inspector", "检查人", "", "text", true)}${input("location", "检查位置", "", "text", true)}<label>原因确认程度<select name="conclusion">${optionList(conclusions, "unknown")}</select></label>${area("observation", "观察结果", "", true)}${area("action", "采取措施")}${area("cause", "怀疑或确认的原因")}${area("basis", "测量 / 检查依据")}${area("follow_up", "后续检查或复测安排")}<label class="wide">照片或测量附件（可后补）<input type="file" name="attachments" accept=".png,.jpg,.jpeg,.pdf,.csv,.txt" multiple><small>PNG/JPEG、PDF、UTF-8 CSV/TXT；每个附件不超过10MB。</small></label></div><button class="button primary">保存检查记录</button></form></details>
  <h3>发现、处理与检查历史</h3><p class="small">按记录时间排列；历史评估可补做，以各条评估截止日期辨认先后。</p>${[
    ...issue.events,
  ]
    .reverse()
    .map((event) => eventMarkup(event, warehouse.id, issue.id, true))
    .join("")}`
      : '<h2>选择一个异常档案</h2><p class="note">真实数据的检查记录初始为空，可先用模拟案例体验流程。</p>'
  }</section></div>`;
}

export function reportTracking(report) {
  if (!report.tracking)
    return '<div class="panel"><h2>追踪档案</h2><p class="note">这份旧报告没有保存追踪快照。生成新评估后开始记录。</p></div>';
  return `<div class="panel"><div class="panel-head"><h2>本报告的追踪快照</h2><button class="text-button" data-go="tracking">打开当前处理档案 ↗</button></div><p class="note">截至生成时间 ${dateText(report.created)}。检查可能发生在评估截止日期之后，以各条检查日期为准。</p>${
    report.tracking.length
      ? report.tracking
          .map(
            (i) =>
              `<details><summary>${e(i.title)} · ${statusLabels[i.status]} · ${i.latest_assessment ? outcomes[i.latest_assessment.outcome] : "人工追踪"}</summary><p class="note">首次触发 ${e(i.first_detected || "未记录")}；最近触发 ${e(i.last_detected || "未记录")}</p>${[
                ...i.events,
              ]
                .reverse()
                .map((event) =>
                  eventMarkup(event, report.warehouse_id, i.id, false),
                )
                .join(
                  "",
                )}<button class="text-button" data-issue="${e(i.id)}">继续处理 ↗</button></details>`,
          )
          .join("")
      : '<p class="note">生成时尚无真实追踪事项。模拟案例不纳入报告。</p>'
  }</div>`;
}

export function reportKnowledge(report) {
  const missing = [];
  for (const d of report.devices) {
    for (const [key, label] of Object.entries(deviceTopics)) {
      if (d.evidence?.[key]?.status !== "confirmed")
        missing.push(`设备 ${d.label || d.id} · ${label}`);
    }
  }
  return `<div class="panel"><div class="panel-head"><h2>现场资料与待确认项</h2><button class="text-button" data-go="archive">补充资料档案 ↗</button></div><p class="note">${missing.length}项设备资料未确认。资料确认依据随本次报告保存。</p><details><summary>查看未确认项与仓库说明</summary><p class="note">${missing.map(e).join("；")}</p><p>地面基准：${e(report.profile?.ground_reference || "未填写")}</p><p>连接关系：${e(report.profile?.connections || "未填写")}</p></details></div>`;
}
