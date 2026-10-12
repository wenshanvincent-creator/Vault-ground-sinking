import { escape as e, number as n, dates } from "./helpers.js";

export function welcome(hasWarehouse) {
  return `<div class="panel welcome"><span class="eyebrow">从历史数据开始</span><h2>看清长期变化，找到值得检查的位置</h2><p>上传现有 Excel，结合仓库布局，生成倾角趋势、多点共同变化与疑似沉降区域的周期报告。</p><div class="welcome-actions"><button class="button primary" data-action="demo">载入演示仓库</button><button class="button secondary" data-action="${hasWarehouse ? "import" : "create"}">${hasWarehouse ? "导入 Excel" : "新建自己的仓库"}</button></div><p class="small">公开版本使用合成读数和模拟布局；本机私有示例需单独配置。轴向与连接关系保持未确认。</p></div>`;
}

function deviceRows(report) {
  const attention = (value, limit, measurement) =>
    limit === null
      ? "未设门槛"
      : measurement === null
        ? "缺数据"
        : value
          ? "达到关注门槛"
          : "未达门槛";
  return report.devices
    .map(
      (d) =>
        `<tr><td><button class="device-link" data-device="${e(d.id)}">${e(d.label || d.id)}</button></td><td>${e(d.group || "未分组")}</td><td class="numeric">${n(d.baseline_shift_deg)}</td><td class="numeric">${n(d.trend_deg_week)}</td><td class="numeric">${n(d.current.distance, 2)}</td><td class="numeric">${d.valid_days}/${report.days}</td><td><span class="badge ${d.persistent ? "warning" : ""}">${e(d.status || d.quality)}</span></td><td>${attention(d.angle_attention, report.settings.angle_limit_deg, d.angle_max_deg)}</td><td>${attention(d.distance_attention, report.settings.distance_limit_mm, d.current.distance)}</td></tr>`,
    )
    .join("");
}

export function overview(report) {
  const c = report.counts,
    q = report.quality;
  return `<div class="intro"><div class="period-label">${e(report.start)} — ${e(report.cutoff)} · 最近${report.days}天</div><h2>本周期有哪些沉降线索？</h2><p>先看持续变化，再比较邻近点的时间关系。每项线索都能追溯到点位曲线与本次分析条件。</p></div>
  <div class="summary-grid"><div class="summary"><div class="label">长期参考偏移</div><div class="value">${c.reference_changes ?? "—"}<span>个点</span></div><small>仅表示与参考时期有差异，原因待核查</small></div><div class="summary"><div class="label">近期持续倾斜变化</div><div class="value">${c.persistent}<span>个点</span></div><small>结合变化速度与方向持续性</small></div><div class="summary attention"><div class="label">疑似沉降区域线索</div><div class="value">${c.regions}<span>个点组</span></div><small>需要现场核查原因</small></div></div>
  <div class="two-columns"><div class="panel"><div class="panel-head"><h2>区域线索</h2><button class="text-button" data-go="map">在布局图上查看 ↗</button></div>${regionCards(report)}</div>
  <div class="panel"><h2>如何理解本次结果</h2><p class="note">区域线索由“多点持续变化＋同期变化关联＋配置的空间点组”形成。温度、载荷变化、碰撞和安装调整，也可能产生类似模式。</p><div class="quality-strip"><span>未确认轴向：${q.axes_unknown}点</span><span>未定位：${q.unmapped}点</span></div><p class="note">${e(report.notes[0])}</p><details><summary>查看分析条件与业务门槛</summary><p class="note">参考变化≥${n(report.settings.angle_change_deg)}°；趋势≥${n(report.settings.trend_deg_week)}°/周；方向一致率≥${Math.round(report.settings.consistency * 100)}%；可用天数≥${Math.round(report.settings.min_day_coverage * 100)}%。这些是可调的演示分析条件。</p><p class="note">角度业务门槛：${report.settings.angle_limit_deg === null ? "未设置" : n(report.settings.angle_limit_deg) + "°"}；二维距离业务门槛：${report.settings.distance_limit_mm === null ? "未设置" : n(report.settings.distance_limit_mm, 2) + "mm"}。</p><button class="text-button" data-go="settings">调整配置</button></details></div></div>
  <div class="panel"><div class="panel-head"><h2>点位变化清单</h2><span class="small">优先列出持续变化点；点击设备查看依据</span></div><div class="table-wrap"><table><thead><tr><th>设备</th><th>点组</th><th class="numeric">参考变化 °</th><th class="numeric">趋势 °/周</th><th class="numeric">二维距离 mm</th><th class="numeric">可用天数</th><th>分析状态</th><th>角度关注</th><th>位移关注</th></tr></thead><tbody>${deviceRows(report)}</tbody></table></div><p class="metric-desc">参考变化为双轴角度变化的合成幅值；二维距离为 √(X²＋Y²)，保留原表绝对值之和作为另一指标。业务关注不等于事故判断。</p></div>
  <div class="quality-strip"><span>纳入 ${c.devices}点</span><span>数据不足 ${q.insufficient}点</span><span>心跳长间隔 ${q.large_gaps ?? 0}点</span><span>截止日期内记录 ${q.records.toLocaleString()}</span><span>缺少位移 ${q.missing_displacement.toLocaleString()}条</span><span>报警帧 ${q.alarms}条</span><span>时区：${e(report.settings.source_timezone)}</span></div>`;
}

export function regionCards(report) {
  if (!report.regions.length)
    return `<div class="empty-note"><h3>当前条件下，暂无区域线索</h3><p class="note">这不代表不存在沉降。可以查看单点趋势，检查点组配置和数据覆盖，并根据现场情况调整分析条件。</p></div>`;
  return report.regions
    .map(
      (r) =>
        `<div class="finding"><h3>${e(r.group)} <span class="badge warning">沉降待核查</span></h3><p>关联设备：${r.members.map((id) => `<button class="device-link" data-device="${e(id)}">${e(id)}</button>`).join("、")}</p><p>${e(r.evidence)}</p><p>${e(r.missing)}</p>${r.direction_supported ? "<p>按已确认轴向转换后，多数点的倾斜变化指向点组内部。</p>" : ""}<details><summary>查看共同变化证据</summary>${r.pairs.map((p) => `<p>${e(p.a)} / ${e(p.b)}：变化幅值相关系数 ${n(p.correlation, 2)}</p>`).join("")}<p>${e(r.interpretation)}</p></details></div>`,
    )
    .join("");
}

export function mapMarkup(
  warehouse,
  report,
  placement = false,
  selected = null,
) {
  const devices = !placement && report ? report.devices : warehouse.devices;
  const image =
    !placement && report
      ? report.layout_path
        ? `/api/reports/${report.id}/layout`
        : null
      : warehouse.layout_url;
  if (!image)
    return '<div class="empty-note note">尚未配置布局图。可以在“仓库配置”上传图片并标注点位，再生成新的评估。</div>';
  const regionMembers = new Set(
    (report?.regions || []).flatMap((r) => r.members),
  );
  return `<div class="map-frame" ${placement ? 'data-placement="true"' : ""}><img src="${e(image)}" alt="仓库俯视布局，通道与货架点位">${devices
    .filter((d) => d.x !== null && d.y !== null)
    .map(
      (d) =>
        `<button type="button" class="map-point ${d.id === selected ? "focused" : ""} ${!placement && regionMembers.has(d.id) ? "region" : ""}" style="left:${d.x * 100}%;top:${d.y * 100}%" data-${placement ? "select" : "device"}="${e(d.id)}" aria-label="设备${e(d.label || d.id)}${d.persistent ? "，持续变化" : ""}">${e(d.label || d.id)}</button>`,
    )
    .join("")}</div>`;
}

export function mapView(
  warehouse,
  report,
  selected,
  metric = "angle",
  range = "all",
) {
  const device =
    report?.devices.find((d) => d.id === selected) || report?.devices[0];
  return `<div class="intro"><h2>变化发生在哪里？</h2><p>橙色点参与区域线索，点击点位查看历史。点组由现场或用户配置，空间相邻不自动代表结构连接。</p></div><div class="panel"><div class="panel-head"><h2>仓库俯视布局</h2><span class="small">轴向未核对时，保留读数，不绘制方向结论</span></div>${mapMarkup(warehouse, report, false, device?.id)}</div><div class="two-columns"><div class="panel device-detail">${device ? detailMarkup(device, metric, range) : "<p>生成评估后可查看点位变化。</p>"}</div><div class="panel"><h2>区域证据</h2>${report ? regionCards(report) : '<p class="note">尚未生成评估</p>'}<h3>需要补充的资料</h3><p class="note">安装轴向与校准、货架连接关系、载荷与维护事件，以及相对于稳定基准的地面高程复测。当前原型不会反算地面沉降毫米数。</p></div></div>${device ? `<details class="panel"><summary>设备 ${e(device.id)} 的源数据（截止日期内最近100条）</summary><div id="raw-records" class="table-wrap"></div></details>` : ""}`;
}

export function detailMarkup(device, metric, range) {
  return `<div class="panel-head"><h2>设备 ${e(device.label || device.id)}</h2><span class="badge ${device.persistent ? "warning" : ""}">${e(device.status || device.quality)}</span></div><p class="note">${e(device.group || "未分组")} · 参考时期 ${e(device.reference_start || "缺数据")} 至 ${e(device.reference_end || "缺数据")}（未经现场认证）</p><div class="detail-row"><div><small>参考角度变化</small><div class="value">${n(device.baseline_shift_deg)}<small> °</small></div></div><div><small>水平位置变化距离</small><div class="value">${n(device.distance_change_mm, 2)}<small> mm</small></div></div></div><div class="chart-toolbar"><select id="detail-metric" aria-label="点位曲线指标"><option value="angle" ${metric === "angle" ? "selected" : ""}>双轴角度 · 度</option><option value="distance" ${metric === "distance" ? "selected" : ""}>合成水平位移 · mm</option><option value="temperature" ${metric === "temperature" ? "selected" : ""}>温度 · ℃</option></select><select id="detail-range" aria-label="曲线时间范围"><option value="all" ${range === "all" ? "selected" : ""}>完整历史</option><option value="period" ${range === "period" ? "selected" : ""}>当前评估周期</option></select></div><div id="detail-chart" class="chart"></div><p class="metric-desc">日中位数；缺失日保持间断。温度只作对照，不自动扣除。</p><div class="quality-strip"><span>可用天数 ${device.valid_days}</span><span>报警帧 ${device.alarm_count}</span><span>最大心跳间隔 ${n(device.largest_gap_hours, 1)}小时</span></div>`;
}

export function trends(
  report,
  matrixMetric,
  commonIds,
  matrixRange = "period",
) {
  const labels = {
    angle_change: "角度变化幅值 · °",
    distance_change: "水平位置变化距离 · mm",
    distance: "当前二维距离 · mm",
    legacy: "原表绝对值之和 · mm",
  };
  const monthly = matrixRange === "history";
  const days = monthly
    ? report.history_months ||
      [
        ...new Set(
          report.devices.flatMap((d) =>
            (d.monthly_matrix || []).map((v) => v.date),
          ),
        ),
      ].sort()
    : dates(report.start, report.days);
  const lookup = new Map(
    report.devices.map((d) => [
      d.id,
      new Map(
        (monthly ? d.monthly_matrix || [] : d.series).map((v) => [v.date, v]),
      ),
    ]),
  );
  const values = report.devices.flatMap((d) =>
    days
      .map((day) => lookup.get(d.id).get(day)?.[matrixMetric])
      .filter((v) => v !== null && v !== undefined),
  );
  const scale = Math.max(...values.map(Math.abs), 0.000001);
  return `<div class="intro"><h2>把多个点放在同一个时间轴上</h2><p>先看共同变化曲线，再用日期表定位变化开始的时间。颜色表示相对变化大小，空白表示缺数据。</p></div><div class="panel"><h2>多点共同变化</h2><p class="metric-desc">相对各自参考时期的双轴角度变化幅值（°）。最多同时比较6个点。</p><div class="selection-list">${report.devices.map((d) => `<label><input type="checkbox" data-common="${e(d.id)}" ${commonIds.includes(d.id) ? "checked" : ""}>${e(d.label || d.id)}</label>`).join("")}</div><div id="common-chart" class="chart"></div></div><div class="panel"><div class="panel-head"><h2>设备 × 日期</h2><div class="chart-toolbar"><select id="matrix-range" aria-label="矩阵时间范围"><option value="period" ${monthly ? "" : "selected"}>当前周期 · 每日</option><option value="history" ${monthly ? "selected" : ""}>完整历史 · 每月</option></select><select id="matrix-metric" aria-label="矩阵指标">${Object.entries(
    labels,
  )
    .map(
      ([k, v]) =>
        `<option value="${k}" ${k === matrixMetric ? "selected" : ""}>${v}</option>`,
    )
    .join(
      "",
    )}</select></div></div><p class="metric-desc">${monthly ? "每格为该月日统计值的中位数；首末月可能只有部分日期。" : "每格为当天心跳读数的统计值。"}变化指标相对于参考时期。横向看一个设备，纵向看同一时期多个设备。</p><div class="table-wrap"><table class="matrix"><thead><tr><th>设备</th>${days.map((d) => `<th>${monthly ? d.slice(2) : d.slice(5)}</th>`).join("")}</tr></thead><tbody>${report.devices
    .map(
      (device) =>
        `<tr><td><button class="device-link" data-device="${e(device.id)}">${e(device.label || device.id)}</button></td>${days
          .map((day) => {
            const value = lookup.get(device.id).get(day)?.[matrixMetric];
            if (value === undefined || value === null)
              return '<td class="missing" title="缺数据">—</td>';
            const ratio = Math.min(1, Math.abs(value) / scale);
            return `<td class="heat" style="background:rgba(184,113,53,${0.04 + 0.3 * ratio})" title="${e(device.id)} · ${day} · ${n(value, matrixMetric === "angle_change" ? 4 : 3)}">${n(value, matrixMetric === "angle_change" ? 3 : 1)}</td>`;
          })
          .join("")}</tr>`,
    )
    .join("")}</tbody></table></div></div>`;
}

export function settingsView(warehouse, draft, selected) {
  const s = warehouse.settings;
  const input = (key, label, type = "number", step = "any") =>
    `<label>${label}<input name="${key}" type="${type}" ${type === "number" ? `step="${step}"` : ""} value="${e(s[key] ?? "")}"></label>`;
  return `<div class="intro"><h2>让分析适配这个仓库</h2><p>配置会用于下一次评估。已经保存的报告保留原参数与点位，方便复现。</p></div><form id="settings-form" class="panel"><h2>周期分析与参考时期</h2><div class="form-grid">${input("reference_start", "固定参考开始日期（留空：最早覆盖充分的时期）", "date")}${input("reference_days", "参考时期天数", "number", "1")}${input("source_timezone", "导出时间口径", "text")}${input("angle_change_deg", "参考角度变化条件 · °")}${input("trend_deg_week", "近期趋势强度条件 · °/周")}${input("consistency", "方向一致率 · 0.5至1")}${input("min_day_coverage", "最低可用天数比例 · 0.1至1")}${input("common_correlation", "共同变化相关系数条件 · 0至1")}</div><p class="config-help">分析条件控制报告敏感度，属于原型演示设置。固定参考时期用于长期变化，上周期用于近期比较；不将参考时期自动视为安全状态。</p><details><summary>角度与二维距离业务关注门槛（可留空）</summary><div class="form-grid">${input("angle_limit_deg", "周期中位数最大轴角度门槛 · °")}${input("distance_limit_mm", "周期中位数二维距离门槛 · mm")}<label class="wide">阈值依据与适用条件<textarea name="threshold_basis" rows="3">${e(s.threshold_basis)}</textarea></label></div><p class="config-help">原系统的合成位移分级不能自动用于新二维距离指标。业务门槛仅提供关注提示，不能直接判断货物是否掉落或货架是否倒塌。</p></details><button class="button primary">保存分析配置</button></form>
  <section class="panel"><div class="panel-head"><h2>布局与点位</h2><button class="button secondary" data-action="layout">上传布局图</button></div><div class="map-controls"><label>定位设备 <select id="placing-device">${draft.map((d) => `<option value="${e(d.id)}" ${selected === d.id ? "selected" : ""}>${e(d.label || d.id)}</option>`).join("")}</select></label><span class="small">选择设备，再点击图上位置；最后保存点位配置。</span><button class="text-button" data-action="clear-point">清除所选位置</button></div>${mapMarkup({ ...warehouse, devices: draft }, null, true, selected)}<div class="table-wrap"><table class="device-config"><thead><tr><th>设备</th><th>显示名</th><th>点组</th><th>货架高 m</th><th>心跳周期 h</th><th>位置 X %</th><th>位置 Y %</th><th>轴向已核对</th><th>旋转 °</th><th>X符号</th><th>Y符号</th></tr></thead><tbody>${draft
    .map(
      (d) =>
        `<tr data-device-config="${e(d.id)}"><td>${e(d.id)}</td><td><input class="device-name" data-field="label" aria-label="${e(d.id)}显示名" value="${e(d.label)}"></td><td><input class="group-input" data-field="group" aria-label="${e(d.id)}点组" value="${e(d.group)}"></td>${[
          ["height_mm", d.height_mm === null ? "" : d.height_mm / 1000],
          ["expected_hours", d.expected_hours],
          ["x", d.x === null ? "" : d.x * 100],
          ["y", d.y === null ? "" : d.y * 100],
        ]
          .map(
            ([field, value]) =>
              `<td><input type="number" step="any" data-field="${field}" aria-label="${e(d.id)} ${field}" value="${e(value)}"></td>`,
          )
          .join(
            "",
          )}<td><span class="badge">${d.axis_confirmed ? "已确认" : "待确认"}</span><button class="text-button" data-go="archive">资料依据 ↗</button></td><td><input type="number" step="any" data-field="rotation_deg" aria-label="${e(d.id)}旋转角度" value="${d.rotation_deg}"></td><td><input type="number" min="-1" max="1" step="2" data-field="x_sign" aria-label="${e(d.id)}X方向符号" value="${d.x_sign}"></td><td><input type="number" min="-1" max="1" step="2" data-field="y_sign" aria-label="${e(d.id)}Y方向符号" value="${d.y_sign}"></td></tr>`,
    )
    .join(
      "",
    )}</tbody></table></div><p class="config-help">位置按图宽/高的百分比记录。点组可按区域划分，不自动认定结构连接。在资料档案中填写依据并确认轴向后，X/Y先按±1校正符号，再按旋转角度转到图上“向右/向上”的方向；方向结果只作示意。已有Excel位移保持原值，修改货架高度不会重算历史数据。</p><div class="form-actions"><button class="button primary" data-action="save-devices">保存点位配置</button><span class="small" id="draft-status">${draft.length}个设备；未定位 ${draft.filter((d) => d.x === null || d.y === null).length}个</span></div></section><section class="panel"><h2>导入记录</h2>${warehouse.imports.length ? `<div class="table-wrap"><table><thead><tr><th>源文件</th><th>读入</th><th>新增</th><th>重复</th></tr></thead><tbody>${warehouse.imports.map((i) => `<tr><td>${e(i.filename)}</td><td>${i.summary.read}</td><td>${i.summary.added}</td><td>${i.summary.duplicates}</td></tr>`).join("")}</tbody></table></div>` : '<p class="note">尚未导入数据</p>'}</section>`;
}

export function history(warehouse, report) {
  return `<div class="intro"><h2>每次评估都可以回看</h2><p>保存的数据截止日期、参数、点位与分析结果保持一致。配置变化后生成新报告，旧报告仍可导出。</p></div><div class="panel">${warehouse.reports.length ? warehouse.reports.map((r) => `<div class="report-record"><div><strong>${e(r.start)} 至 ${e(r.cutoff)} · ${r.days === 7 ? "周" : "月"}评估</strong><small>编号 ${e(r.id.slice(0, 8))} · ${e(r.created.replace("T", " ").replace("+00:00", " UTC"))}</small></div>${report?.id === r.id ? '<span class="badge">当前查看</span>' : ""}<button class="text-button" data-report="${e(r.id)}">查看保存结果 ↗</button><a class="button secondary" href="/api/reports/${e(r.id)}/pdf">PDF</a></div>`).join("") : '<p class="note">尚未生成评估</p>'}</div>`;
}
