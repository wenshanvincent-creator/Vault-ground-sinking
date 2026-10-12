import { api, escape as e, number as n } from "./helpers.js";
import { lineChart } from "./charts.js";
import * as views from "./views.js";
import * as workflow from "./workflow.js";

const state = {
  warehouses: [],
  warehouse: null,
  report: null,
  view: "overview",
  selected: null,
  draft: [],
  placing: null,
  matrix: "angle_change",
  matrixRange: "period",
  common: [],
  detailMetric: "angle",
  detailRange: "period",
  busy: false,
  issues: [],
  issueSelected: null,
  issueFilter: "open",
  showDemo: false,
  archiveDevice: null,
};
const titles = {
  overview: "沉降线索评估",
  map: "点位与区域",
  trends: "趋势与矩阵",
  history: "报告记录",
  settings: "仓库配置",
  tracking: "异常追踪与现场检查",
  archive: "现场资料档案",
};
const content = document.getElementById("content");
let disposers = [];

function message(text, error = false) {
  const target = document.getElementById("message");
  target.textContent = text;
  target.hidden = !text;
  target.classList.toggle("error", error);
}
async function work(task, label = "正在处理…") {
  if (state.busy) return;
  state.busy = true;
  message(label);
  buttons();
  try {
    await task();
  } catch (error) {
    message(error.message, true);
  } finally {
    state.busy = false;
    buttons();
  }
}
function buttons() {
  document.getElementById("evaluate").disabled =
    state.busy || !state.warehouse?.record_count;
  document.getElementById("import-button").disabled = state.busy;
  document.getElementById("export-pdf").disabled = state.busy || !state.report;
  document.getElementById("warehouse-picker").disabled = state.busy;
  content
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = state.busy));
}
function picker() {
  const select = document.getElementById("warehouse-picker");
  select.innerHTML = state.warehouses.length
    ? state.warehouses
        .map((w) => `<option value="${e(w.id)}">${e(w.name)}</option>`)
        .join("")
    : '<option value="">尚未创建仓库</option>';
  select.value = state.warehouse?.id || "";
}
async function refreshWarehouse() {
  state.warehouse = await api(`/api/warehouses/${state.warehouse.id}`);
  state.issues = await api(`/api/warehouses/${state.warehouse.id}/issues`);
  state.warehouses = await api("/api/warehouses");
  picker();
  const cutoff = document.getElementById("cutoff");
  cutoff.max = state.warehouse.last_time?.slice(0, 10) || "";
  if (!cutoff.value || cutoff.value > cutoff.max) cutoff.value = cutoff.max;
}
async function loadWarehouse(key) {
  state.warehouse = await api(`/api/warehouses/${key}`);
  state.issues = await api(`/api/warehouses/${key}/issues`);
  state.issueSelected = null;
  state.archiveDevice = state.warehouse.devices[0]?.id || null;
  state.showDemo = false;
  state.draft = structuredClone(state.warehouse.devices);
  state.placing = state.draft[0]?.id || null;
  state.report = state.warehouse.reports.length
    ? await api(`/api/reports/${state.warehouse.reports[0].id}`)
    : null;
  state.selected = state.report?.devices[0]?.id || null;
  state.common = state.report?.devices.slice(0, 3).map((d) => d.id) || [];
  document.getElementById("cutoff").max =
    state.warehouse.last_time?.slice(0, 10) || "";
  document.getElementById("cutoff").value =
    state.report?.cutoff || state.warehouse.last_time?.slice(0, 10) || "";
  document.getElementById("cycle").value = state.report?.cycle || "week";
  state.view = "overview";
  picker();
  render();
}
function savedNotice() {
  if (!state.report || !state.warehouse) return "";
  const keys = Object.keys(state.report.settings).sort();
  const changed =
    JSON.stringify(state.report.settings, keys) !==
    JSON.stringify(state.warehouse.settings, keys);
  const snapshotIds = state.report.devices
    .map((d) => d.id)
    .sort()
    .join(",");
  const liveIds = state.warehouse.devices
    .map((d) => d.id)
    .sort()
    .join(",");
  const positionsChanged = state.report.devices.some((d) => {
    const live = state.warehouse.devices.find((v) => v.id === d.id);
    return (
      live &&
      [
        "x",
        "y",
        "group",
        "axis_confirmed",
        "rotation_deg",
        "x_sign",
        "y_sign",
        "height_mm",
        "installed_on",
        "connections",
        "expected_hours",
        "evidence",
      ].some((k) => JSON.stringify(live[k]) !== JSON.stringify(d[k]))
    );
  });
  return changed ||
    positionsChanged ||
    snapshotIds !== liveIds ||
    JSON.stringify(state.report.profile || {}) !==
      JSON.stringify(state.warehouse.profile || {})
    ? '<p class="saved-note">当前查看的是保存报告。配置已变化，重新生成评估后应用新配置。</p>'
    : "";
}
function render() {
  disposers.forEach((dispose) => dispose());
  disposers = [];
  document.getElementById("page-title").textContent = titles[state.view];
  document
    .querySelectorAll("nav button")
    .forEach((b) =>
      b.classList.toggle("active", b.dataset.view === state.view),
    );
  document.getElementById("source-status").textContent = state.warehouse
    ?.record_count
    ? `数据至 ${state.warehouse.last_time.slice(0, 10)} · ${state.warehouse.record_count.toLocaleString()}条`
    : "等待导入历史数据";
  const w = state.warehouse,
    r = state.report;
  if (!w) {
    content.innerHTML = views.welcome(false);
    buttons();
    return;
  }
  if (state.view === "settings")
    content.innerHTML = views.settingsView(w, state.draft, state.placing);
  else if (state.view === "archive")
    content.innerHTML = workflow.archiveView(w, state.archiveDevice);
  else if (state.view === "tracking")
    content.innerHTML = workflow.trackingView(
      w,
      state.issues,
      state.issueSelected,
      state.issueFilter,
      state.showDemo,
    );
  else if (state.view === "history") content.innerHTML = views.history(w, r);
  else if (state.view === "map")
    content.innerHTML =
      savedNotice() +
      views.mapView(
        w,
        r,
        state.selected,
        state.detailMetric,
        state.detailRange,
      );
  else if (!r)
    content.innerHTML = w.record_count
      ? '<div class="panel welcome"><h2>历史数据已就绪</h2><p>选择截止日期和评估周期，点击“生成评估”。可以先在仓库配置中标注布局与点组。</p><button class="button secondary" data-go="settings">配置点位</button></div>'
      : views.welcome(true);
  else if (state.view === "trends")
    content.innerHTML =
      savedNotice() +
      views.trends(r, state.matrix, state.common, state.matrixRange);
  else
    content.innerHTML =
      savedNotice() +
      views.overview(r) +
      workflow.reportTracking(r) +
      workflow.reportKnowledge(r);
  if (state.view === "map" && r) {
    const device =
      r.devices.find((d) => d.id === state.selected) || r.devices[0];
    if (device)
      content.insertAdjacentHTML(
        "beforeend",
        `<form id="manual-issue-form" class="panel" data-id="${e(device.id)}"><h2>持续追踪设备 ${e(device.label || device.id)}</h2><p class="note">即使本期未触发，也可以记录人工关注理由。重复操作会追加到同一个人工追踪档案。</p><label>追踪理由<textarea name="reason" required maxlength="2000" rows="2"></textarea></label><button class="button primary">开始 / 补充人工追踪</button></form>`,
      );
  }
  if (state.view === "map" && r) drawDetail();
  if (state.view === "trends" && r) drawCommon();
  buttons();
}
function drawDetail() {
  const d =
    state.report.devices.find((d) => d.id === state.selected) ||
    state.report.devices[0];
  const target = document.getElementById("detail-chart");
  if (!target || !d) return;
  let definitions, unit;
  if (state.detailMetric === "distance") {
    definitions = [
      ["distance", "二维距离"],
      ["legacy", "原表绝对值之和"],
    ];
    unit = "mm";
  } else if (state.detailMetric === "temperature") {
    definitions = [["temperature", "温度"]];
    unit = "℃";
  } else {
    definitions = [
      ["ax", "X轴角度"],
      ["ay", "Y轴角度"],
    ];
    unit = "°";
  }
  disposers.push(
    lineChart(
      target,
      definitions.map(([field, name]) => ({
        name,
        points: d.series.map((day) => ({ date: day.date, value: day[field] })),
      })),
      unit,
      state.detailRange === "period" ? state.report.start : null,
    ),
  );
}
function drawCommon() {
  const target = document.getElementById("common-chart");
  if (!target) return;
  if (!state.common.length) {
    target.innerHTML = '<p class="note">选择至少一个设备查看共同变化。</p>';
    return;
  }
  disposers.push(
    lineChart(
      target,
      state.common
        .map((id) => state.report.devices.find((d) => d.id === id))
        .filter(Boolean)
        .map((d) => ({
          name: "设备 " + (d.label || d.id),
          points: d.series.map((day) => ({
            date: day.date,
            value: day.angle_change,
          })),
        })),
      "°",
      state.report.start,
    ),
  );
}
function chooseDevice(id) {
  if (!state.report?.devices.some((d) => d.id === id)) {
    message("该设备未纳入当前报告，请查看较新的报告或生成评估。", true);
    return;
  }
  state.selected = id;
  state.view = "map";
  render();
  window.scrollTo(0, 0);
}
async function evaluate() {
  const r = await api(`/api/warehouses/${state.warehouse.id}/reports`, {
    method: "POST",
    body: {
      cycle: document.getElementById("cycle").value,
      cutoff: document.getElementById("cutoff").value || null,
    },
  });
  state.report = r;
  state.selected = r.devices[0]?.id;
  state.common = r.devices.slice(0, 3).map((d) => d.id);
  await refreshWarehouse();
  state.view = "overview";
  render();
  window.scrollTo(0, 0);
  message(`评估已保存：${r.start} 至 ${r.cutoff}。网页与PDF使用同一份结果。`);
}
function createDialog() {
  document.getElementById("warehouse-dialog").showModal();
}
document
  .getElementById("create-warehouse")
  .addEventListener("click", createDialog);
document
  .getElementById("cancel-create")
  .addEventListener("click", () =>
    document.getElementById("warehouse-dialog").close(),
  );
document
  .getElementById("warehouse-form")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    const name = new FormData(event.currentTarget).get("name");
    document.getElementById("warehouse-dialog").close();
    work(async () => {
      const w = await api("/api/warehouses", {
        method: "POST",
        body: { name },
      });
      state.warehouses = await api("/api/warehouses");
      await loadWarehouse(w.id);
      message("仓库已创建。可以上传现有格式的 Excel。");
    });
  });
document
  .getElementById("warehouse-picker")
  .addEventListener("change", (event) =>
    work(async () => {
      await loadWarehouse(event.target.value);
      message("");
    }),
  );
document.querySelector("nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) {
    state.view = button.dataset.view;
    render();
    window.scrollTo(0, 0);
  }
});
function importFile() {
  if (!state.warehouse) {
    createDialog();
    return;
  }
  document.getElementById("excel-file").click();
}
document.getElementById("import-button").addEventListener("click", importFile);
document.getElementById("excel-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  work(async () => {
    const data = new FormData();
    data.append("file", file);
    const result = await api(`/api/warehouses/${state.warehouse.id}/import`, {
      method: "POST",
      body: data,
    });
    await refreshWarehouse();
    state.draft = structuredClone(state.warehouse.devices);
    state.placing = state.draft[0]?.id;
    render();
    message(
      `读入${result.read}条，新增${result.added}条，重复${result.duplicates}条。${result.warnings.join("")} 请生成新的评估。`,
    );
  }, "正在读取 Excel 并核对重复记录…");
  event.target.value = "";
});
document.getElementById("layout-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  work(async () => {
    const data = new FormData();
    data.append("file", file);
    await api(`/api/warehouses/${state.warehouse.id}/layout`, {
      method: "POST",
      body: data,
    });
    await refreshWarehouse();
    render();
    message("布局图已上传。选择设备后点击图上位置，再保存点位配置。");
  });
  event.target.value = "";
});
document
  .getElementById("evaluate")
  .addEventListener("click", () => work(evaluate, "正在评估历史数据…"));
document.getElementById("export-pdf").addEventListener("click", () =>
  work(async () => {
    const response = await fetch(`/api/reports/${state.report.id}/pdf`);
    if (!response.ok) {
      let msg = "PDF生成失败";
      try {
        msg = (await response.json()).detail;
      } catch {}
      throw new Error(msg);
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `仓库评估-${state.report.cutoff}.pdf`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    message(
      "完整PDF已导出，包含点位图、全部设备历史、两个变化矩阵和本次参数。",
    );
  }, "正在生成完整 PDF…"),
);

content.addEventListener("click", (event) => {
  const issue = event.target.closest("button[data-issue]");
  if (issue) {
    state.issueSelected = issue.dataset.issue;
    const item = state.issues.find((i) => i.id === state.issueSelected);
    if (item?.status === "resolved") state.issueFilter = "all";
    if (item?.is_demo) state.showDemo = true;
    state.view = "tracking";
    render();
    window.scrollTo(0, 0);
    return;
  }
  const device = event.target.closest("[data-device]");
  if (device) {
    chooseDevice(device.dataset.device);
    return;
  }
  const go = event.target.closest("[data-go]");
  if (go) {
    state.view = go.dataset.go;
    render();
    window.scrollTo(0, 0);
    return;
  }
  const select = event.target.closest("[data-select]");
  if (select) {
    state.placing = select.dataset.select;
    render();
    return;
  }
  const frame = event.target.closest("[data-placement]");
  if (frame && event.target.tagName === "IMG") {
    const d = state.draft.find((v) => v.id === state.placing);
    if (!d) return;
    const rect = event.target.getBoundingClientRect();
    d.x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    d.y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    render();
    const note = document.getElementById("draft-status");
    if (note) note.textContent = "位置已调整，尚未保存";
    return;
  }
  const saved = event.target.closest("[data-report]");
  if (saved) {
    work(async () => {
      state.report = await api(`/api/reports/${saved.dataset.report}`);
      state.selected = state.report.devices[0]?.id;
      state.common = state.report.devices.slice(0, 3).map((d) => d.id);
      document.getElementById("cutoff").value = state.report.cutoff;
      document.getElementById("cycle").value = state.report.cycle;
      state.view = "overview";
      render();
      message("正在查看已保存的评估结果。");
    });
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "create") createDialog();
  if (action === "simulation")
    work(async () => {
      const issue = await api(
        `/api/warehouses/${state.warehouse.id}/simulation`,
        { method: "POST" },
      );
      await refreshWarehouse();
      state.issueSelected = issue.id;
      state.issueFilter = "all";
      state.showDemo = true;
      render();
      message("模拟案例已载入。所有观察与检查都是模拟内容，不进入真实评估。");
    });
  if (action === "import") importFile();
  if (action === "layout") document.getElementById("layout-file").click();
  if (action === "demo")
    work(async () => {
      const w = await api("/api/demo", { method: "POST" });
      state.warehouses = await api("/api/warehouses");
      await loadWarehouse(w.id);
      await evaluate();
    }, "正在载入演示仓库…");
  if (action === "clear-point") {
    const d = state.draft.find((v) => v.id === state.placing);
    if (d) {
      d.x = null;
      d.y = null;
      render();
    }
  }
  if (action === "save-devices")
    work(async () => {
      await api(`/api/warehouses/${state.warehouse.id}/devices`, {
        method: "PUT",
        body: state.draft,
      });
      await refreshWarehouse();
      state.draft = structuredClone(state.warehouse.devices);
      render();
      message("点位配置已保存；重新生成评估后应用到报告。");
    });
});
content.addEventListener("input", (event) => {
  const row = event.target.closest("[data-device-config]"),
    field = event.target.dataset.field;
  if (!row || !field) return;
  const d = state.draft.find((v) => v.id === row.dataset.deviceConfig);
  let value =
    event.target.type === "checkbox"
      ? event.target.checked
      : event.target.value;
  if (!["label", "group"].includes(field)) {
    value = value === "" ? null : Number(value);
    if (value !== null && field === "height_mm") value *= 1000;
    if (value !== null && ["x", "y"].includes(field)) value /= 100;
  }
  d[field] = value;
  document.getElementById("draft-status").textContent = "配置已调整，尚未保存";
});
content.addEventListener("change", (event) => {
  if (event.target.id === "archive-device") {
    state.archiveDevice = event.target.value;
    render();
  }
  if (event.target.id === "issue-filter") {
    state.issueFilter = event.target.value;
    render();
  }
  if (event.target.id === "show-demo") {
    state.showDemo = event.target.checked;
    render();
  }
  if (event.target.dataset.attachmentEvent) {
    const files = [...event.target.files];
    const { issueId, attachmentEvent } = event.target.dataset;
    if (files.length)
      work(async () => {
        try {
          await uploadAttachments(issueId, attachmentEvent, files);
          message("附件已保存到这条检查记录；生成新评估后纳入报告。");
        } finally {
          await refreshWarehouse();
          render();
        }
      });
  }
  if (event.target.id === "placing-device") {
    state.placing = event.target.value;
    render();
  }
  if (event.target.id === "detail-metric") {
    state.detailMetric = event.target.value;
    render();
  }
  if (event.target.id === "detail-range") {
    state.detailRange = event.target.value;
    render();
  }
  if (event.target.id === "matrix-metric") {
    state.matrix = event.target.value;
    render();
  }
  if (event.target.id === "matrix-range") {
    state.matrixRange = event.target.value;
    render();
  }
  if (event.target.dataset.common) {
    const id = event.target.dataset.common;
    if (event.target.checked && state.common.length >= 6) {
      event.target.checked = false;
      message("最多同时比较6个点。");
      return;
    }
    state.common = event.target.checked
      ? [...state.common, id]
      : state.common.filter((v) => v !== id);
    disposers.forEach((dispose) => dispose());
    disposers = [];
    drawCommon();
  }
});
content.addEventListener("submit", (event) => {
  const form = event.target;
  if (
    [
      "profile-form",
      "device-archive-form",
      "site-event-form",
      "manual-issue-form",
      "handling-form",
      "inspection-form",
    ].includes(form.id)
  ) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    work(async () => {
      const base = `/api/warehouses/${state.warehouse.id}`;
      if (form.id === "profile-form") {
        await api(base + "/profile", {
          method: "PUT",
          body: {
            ground_reference: data.ground_reference,
            connections: data.connections,
            notes: data.notes,
            evidence: workflow.profileEvidence(form),
          },
        });
      } else if (form.id === "device-archive-form") {
        const devices = structuredClone(state.warehouse.devices);
        const device = devices.find((d) => d.id === form.dataset.id);
        Object.assign(device, {
          installed_on: data.installed_on || null,
          connections: data.connections,
          evidence: workflow.deviceEvidence(form),
        });
        await api(base + "/devices", { method: "PUT", body: devices });
      } else if (form.id === "site-event-form") {
        data.members = new FormData(form).getAll("members");
        await api(base + "/site-events", { method: "POST", body: data });
      } else if (form.id === "manual-issue-form") {
        const issue = await api(base + "/issues", {
          method: "POST",
          body: {
            report_id: state.report.id,
            device_id: form.dataset.id,
            reason: data.reason,
          },
        });
        state.issueSelected = issue.id;
        state.issueFilter = "all";
        state.view = "tracking";
      } else if (form.id === "handling-form") {
        try {
          await api(base + `/issues/${form.dataset.issue}`, {
            method: "PUT",
            body: { version: Number(form.dataset.version), ...data },
          });
        } catch (error) {
          await refreshWarehouse();
          render();
          throw error;
        }
      } else if (form.id === "inspection-form") {
        const files = [...form.querySelector('[name="attachments"]').files];
        delete data.attachments;
        const issue = await api(
          base + `/issues/${form.dataset.issue}/inspections`,
          { method: "POST", body: data },
        );
        const eventId = [...issue.events]
          .reverse()
          .find((v) => v.kind === "inspection").id;
        try {
          await uploadAttachments(issue.id, eventId, files);
        } catch (error) {
          await refreshWarehouse();
          render();
          throw new Error(
            "检查记录已保存。" +
              error.message +
              " 可在这条检查记录中补传附件。",
          );
        }
      }
      await refreshWarehouse();
      state.draft = structuredClone(state.warehouse.devices);
      render();
      message(
        "记录已保存。旧报告保持原快照；生成新评估后纳入新的网页报告和 PDF。",
      );
    });
    return;
  }
  if (event.target.id !== "settings-form") return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  const settings = { ...state.warehouse.settings };
  for (const [key, value] of Object.entries(values))
    settings[key] = ["source_timezone", "threshold_basis"].includes(key)
      ? value
      : key === "reference_start"
        ? value || null
        : value === ""
          ? null
          : Number(value);
  work(async () => {
    await api(`/api/warehouses/${state.warehouse.id}/settings`, {
      method: "PUT",
      body: settings,
    });
    await refreshWarehouse();
    render();
    message("分析配置已保存；请生成新评估。旧报告参数保持不变。");
  });
});

async function uploadAttachments(issueId, eventId, files) {
  let saved = 0;
  for (const file of files) {
    const body = new FormData();
    body.append("file", file);
    try {
      await api(
        `/api/warehouses/${state.warehouse.id}/issues/${issueId}/events/${eventId}/attachments`,
        { method: "POST", body },
      );
      saved++;
    } catch (error) {
      throw new Error(
        `已保存${saved}/${files.length}个附件；${file.name}：${error.message}`,
      );
    }
  }
}
content.addEventListener(
  "toggle",
  (event) => {
    if (!event.target.open || !event.target.querySelector("#raw-records"))
      return;
    const target = document.getElementById("raw-records");
    target.textContent = "正在读取…";
    api(
      `/api/warehouses/${state.warehouse.id}/records?device=${encodeURIComponent(state.selected || state.report.devices[0].id)}&before=${state.report.cutoff}`,
    )
      .then((rows) => {
        if (!target.isConnected) return;
        target.innerHTML = `<table class="raw"><thead><tr><th>时间</th><th>消息</th><th>X角度°</th><th>Y角度°</th><th>X位移mm</th><th>Y位移mm</th><th>原表合成mm</th><th>IT分级</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${e(r.event_time.replace("T", " "))}</td><td>${e(r.message_type)}</td>${["angle_x", "angle_y", "x_displacement", "y_displacement", "x_y_displacement"].map((k) => `<td>${n(r[k], 4)}</td>`).join("")}<td>${e(r.flag || "—")}</td></tr>`).join("")}</tbody></table>`;
      })
      .catch((error) => (target.textContent = error.message));
  },
  true,
);

work(async () => {
  state.warehouses = await api("/api/warehouses");
  picker();
  if (state.warehouses.length) await loadWarehouse(state.warehouses[0].id);
  else render();
  message("");
}, "正在加载仓库…");
