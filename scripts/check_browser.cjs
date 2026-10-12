const fs = require("fs");
const path = require("path");
const assert = require("assert/strict");
const { chromium } = require(
  path.join(process.env.VAULT_NODE_MODULES || "node_modules", "playwright"),
);

async function main() {
  const root = path.resolve(__dirname, "..");
  const out = path.join(root, "tmp", "browser");
  const source =
    process.env.VAULT_QA_EXCEL || path.join(root, "tmp", "demo-export.xlsx");
  assert.ok(
    fs.existsSync(source),
    "先运行 scripts/make_demo_excel.py 生成模拟导出",
  );
  fs.mkdirSync(out, { recursive: true });
  const baseURL = process.env.VAULT_QA_URL || "http://127.0.0.1:8766";
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.VAULT_BROWSER,
  });
  const page = await browser.newPage({
    baseURL,
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    const response = await page.request.post("/api/demo?synthetic=true");
    assert.equal(response.status(), 200);
    const warehouse = await response.json();
    const base = `/api/warehouses/${warehouse.id}`;
    const deviceId = warehouse.devices[0].id;
    await page.request.post(base + "/reports", { data: { cycle: "month" } });
    await page.goto("/");
    await page.locator("#warehouse-picker").selectOption(warehouse.id);
    await page.locator("#export-pdf:enabled").waitFor();
    await page.locator(`[data-device="${deviceId}"]`).first().click();
    await page.locator("#detail-chart svg").waitFor();
    await page.locator("#detail-metric").selectOption("distance");
    await page.locator("#detail-chart svg").waitFor();
    await page.locator('nav [data-view="trends"]').click();
    await page.locator("#common-chart svg").waitFor();
    await page.locator("#matrix-metric").selectOption("distance_change");
    await page.locator("#matrix-range").selectOption("history");
    await page.screenshot({
      path: path.join(out, "matrix.png"),
      fullPage: true,
    });
    const old = await (await page.request.get(base)).json();
    const report = await (
      await page.request.get(`/api/reports/${old.reports[0].id}`)
    ).json();
    await page.locator("#excel-file").setInputFiles(source);
    await page
      .locator("#message")
      .getByText(/新增0条/)
      .waitFor();
    assert.equal(
      (await (await page.request.get(base)).json()).record_count,
      old.record_count,
    );
    assert.deepEqual(
      await (await page.request.get(`/api/reports/${report.id}`)).json(),
      report,
    );
    const downloading = page.waitForEvent("download");
    await page.locator("#export-pdf").click();
    await (await downloading).saveAs(path.join(out, "synthetic-report.pdf"));
    await page.locator('nav [data-view="settings"]').click();
    await page.locator("#placing-device").selectOption(deviceId);
    const image = page.locator("[data-placement] img");
    await image.scrollIntoViewIfNeeded();
    const box = await image.boundingBox();
    await image.click({
      position: { x: box.width * 0.4, y: box.height * 0.4 },
    });
    await page.locator('[data-action="save-devices"]').click();
    await page
      .locator("#message")
      .getByText("点位配置已保存", { exact: false })
      .waitFor();
    const moved = await (await page.request.get(base)).json();
    assert.ok(
      Math.abs(moved.devices.find((d) => d.id === deviceId).x - 0.4) < 0.01,
    );
    assert.deepEqual(
      await (await page.request.get(`/api/reports/${report.id}`)).json(),
      report,
    );
    await page.request.put(base + "/devices", { data: old.devices });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('nav [data-view="overview"]').click();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        result: "passed",
        synthetic: true,
        warehouse: warehouse.id,
      }),
    );
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
