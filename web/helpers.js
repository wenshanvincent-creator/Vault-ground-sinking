export function escape(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
export function number(value, digits = 3) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : value.toFixed(digits);
}
export async function api(path, options = {}) {
  if (options.body && !(options.body instanceof FormData)) {
    options = {
      ...options,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options.body),
    };
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = "操作失败，请检查服务状态";
    }
    if (Array.isArray(detail))
      detail = detail
        .map((d) => `${d.loc.slice(1).join(".")}：${d.msg}`)
        .join("；");
    throw new Error(detail || "操作失败");
  }
  return response.json();
}
export function dates(start, count) {
  const first = new Date(start + "T00:00:00Z");
  return Array.from({ length: count }, (_, i) =>
    new Date(first.getTime() + i * 86400000).toISOString().slice(0, 10),
  );
}
