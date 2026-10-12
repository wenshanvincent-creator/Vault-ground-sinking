import { escape, number } from "./helpers.js";
const palette = [
  "#276683",
  "#b97135",
  "#62898a",
  "#735f88",
  "#536a96",
  "#a15263",
];

export function lineChart(container, series, unit, minDate = null) {
  const render = () => {
    const width = Math.max(280, container.clientWidth),
      height = 250;
    const datasets = series.map((s) => ({
      ...s,
      points: s.points.filter((p) => !minDate || p.date >= minDate),
    }));
    const values = datasets.flatMap((s) =>
      s.points
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => p.value),
    );
    if (!values.length) {
      container.innerHTML =
        '<div class="empty-note muted">此范围没有可用数据</div>';
      return;
    }
    const times = datasets.flatMap((s) =>
      s.points.map((p) => Date.parse(p.date + "T00:00:00Z")),
    );
    const t0 = Math.min(...times),
      t1 = Math.max(...times);
    let low = Math.min(...values),
      high = Math.max(...values),
      pad = Math.max((high - low) * 0.12, unit === "°" ? 0.001 : 0.1);
    low -= pad;
    high += pad;
    const left = 62,
      right = width - 18,
      top = 18,
      bottom = 205;
    const px = (t) =>
      left + ((t - t0) / Math.max(86400000, t1 - t0)) * (right - left);
    const py = (v) => bottom - ((v - low) / (high - low)) * (bottom - top);
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(series.map((s) => s.name).join("、"))}，单位${escape(unit)}"><title>历史曲线</title>`;
    for (let i = 0; i < 4; i++) {
      const value = low + ((high - low) * i) / 3,
        y = py(value);
      svg += `<line x1="${left}" x2="${right}" y1="${y}" y2="${y}" stroke="#e1e8ed"/><text x="${left - 9}" y="${y + 4}" text-anchor="end">${number(value, unit === "°" ? 3 : 1)}</text>`;
    }
    const ticks = width < 500 ? 3 : 5;
    for (let i = 0; i < ticks; i++) {
      const time = t0 + ((t1 - t0) * i) / (ticks - 1),
        x = left + ((right - left) * i) / (ticks - 1);
      svg += `<text x="${x}" y="${bottom + 23}" text-anchor="${i === 0 ? "start" : i === ticks - 1 ? "end" : "middle"}">${new Date(time).toISOString().slice(2, 10)}</text>`;
    }
    svg += `<text x="${left}" y="${height - 2}" class="plot-label">日期</text><text x="5" y="15" class="plot-label">${escape(unit)}</text>`;
    datasets.forEach((s, index) => {
      let path = "",
        lastTime = null;
      const paths = [];
      for (const point of s.points) {
        const time = Date.parse(point.date + "T00:00:00Z");
        if (point.value === null || point.value === undefined) {
          if (path) paths.push(path);
          path = "";
          lastTime = null;
          continue;
        }
        if (lastTime !== null && time - lastTime > 2 * 86400000) {
          if (path) paths.push(path);
          path = "";
        }
        path += `${path ? "L" : "M"}${px(time).toFixed(2)},${py(point.value).toFixed(2)} `;
        lastTime = time;
      }
      if (path) paths.push(path);
      paths.forEach(
        (d) =>
          (svg += `<path d="${d}" fill="none" stroke="${palette[index % palette.length]}" stroke-width="1.7"/>`),
      );
      if (s.points.length === 1 && s.points[0].value !== null)
        svg += `<circle cx="${px(Date.parse(s.points[0].date + "T00:00:00Z"))}" cy="${py(s.points[0].value)}" r="3" fill="${palette[index % palette.length]}"/>`;
    });
    svg += "</svg>";
    container.innerHTML =
      svg +
      `<div class="chart-legend">${datasets.map((s, i) => `<span><i class="swatch" style="background:${palette[i % palette.length]}"></i>${escape(s.name)}</span>`).join("")}</div>`;
  };
  render();
  const observer = new ResizeObserver(render);
  observer.observe(container);
  return () => observer.disconnect();
}
