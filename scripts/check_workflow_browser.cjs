const fs = require("fs");
const path = require("path");
const assert = require("assert/strict");
const { chromium } = require(
  path.join(process.env.VAULT_NODE_MODULES || "node_modules", "playwright"),
);

async function main() {
  const baseURL = process.env.VAULT_QA_URL || "http://127.0.0.1:8766";
  const out = path.resolve(__dirname, "../tmp/workflow-browser");
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.VAULT_BROWSER,
  });
  const page = await browser.newPage({
    baseURL,
    viewport: { width: 1440, height: 1050 },
    acceptDownloads: true,
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500)
      errors.push(`HTTP ${response.status()} ${response.url()}`);
  });
  try {
    const demoResponse = await page.request.post("/api/demo?synthetic=true");
    assert.equal(demoResponse.status(), 200);
    const warehouse = await demoResponse.json();
    const base = `/api/warehouses/${warehouse.id}`;
    const deviceId = warehouse.devices[0].id;
    await page.request.post(base + "/reports", { data: { cycle: "month" } });
    await page.goto("/");
    await page.locator("#warehouse-picker").selectOption(warehouse.id);
    await page.locator("#export-pdf:enabled").waitFor();

    await page.locator('nav [data-view="archive"]').click();
    await page.locator("#archive-device").selectOption(deviceId);
    const form = page.locator("#device-archive-form");
    await form.locator('[name="installed_on"]').fill("2026-01-01");
    await form
      .locator('[name="connections"]')
      .fill("仅用于隔离环境的模拟连接说明");
    await form.locator('[name="axis.status"]').selectOption("confirmed");
    await form
      .locator('[name="axis.source"]')
      .fill("隔离测试：模拟安装方向照片，不是真实现场证据");
    await form.locator('[name="axis.confirmed_on"]').fill("2026-10-01");
    await form.locator('[name="axis.confirmed_by"]').fill("浏览器验证人员");
    await form.getByRole("button", { name: "保存设备资料" }).click();
    await page
      .locator("#message")
      .getByText("记录已保存", { exact: false })
      .waitFor();
    let live = await (await page.request.get(base)).json();
    assert.equal(
      live.devices.find((d) => d.id === deviceId).axis_confirmed,
      true,
    );
    await page.screenshot({
      path: path.join(out, "archive.png"),
      fullPage: true,
    });

    await page.locator('nav [data-view="settings"]').click();
    const rotation = live.devices.find((d) => d.id === deviceId).rotation_deg;
    await page
      .locator(`[data-device-config="${deviceId}"] [data-field="rotation_deg"]`)
      .fill(String(rotation + 15));
    await page.locator('[data-action="save-devices"]').click();
    await page
      .locator("#message")
      .getByText("点位配置已保存", { exact: false })
      .waitFor();
    live = await (await page.request.get(base)).json();
    assert.equal(
      live.devices.find((d) => d.id === deviceId).axis_confirmed,
      false,
    );
    await page.locator('nav [data-view="archive"]').click();
    await page.getByText("新增现场变更记录", { exact: true }).click();
    const site = page.locator("#site-event-form");
    await site.locator('[name="event_on"]').fill("2026-10-02");
    await site.locator('[name="location"]').fill(`模拟${deviceId}点`);
    await site.locator('[name="recorded_by"]').fill("隔离测试人员");
    await site
      .locator('[name="description"]')
      .fill("隔离验证：模拟载荷调整记录");
    await site.locator(`[name="members"][value="${deviceId}"]`).check();
    await site.getByRole("button", { name: "保存现场变更" }).click();
    await page
      .locator("#message")
      .getByText("记录已保存", { exact: false })
      .waitFor();

    await page.locator('nav [data-view="overview"]').click();
    await page.locator(`[data-device="${deviceId}"]`).first().click();
    await page
      .locator("#manual-issue-form [name=reason]")
      .fill("隔离验证：人工关注并安排复测");
    await page.locator("#manual-issue-form button").click();
    await page.locator("#handling-form").waitFor();
    let issues = await (await page.request.get(base + "/issues")).json();
    const manual = issues.find((i) => i.kind === "manual" && !i.is_demo);
    assert.ok(manual);
    await page
      .locator("#handling-form [name=status]")
      .selectOption("inspection");
    await page.locator("#handling-form [name=author]").fill("模拟管理员");
    await page
      .locator("#handling-form [name=note]")
      .fill("隔离验证：安排现场检查");
    await page.locator("#handling-form button").click();
    await page
      .locator("#message")
      .getByText("记录已保存", { exact: false })
      .waitFor();
    await page.getByText("新增现场检查", { exact: true }).click();
    const inspection = page.locator("#inspection-form");
    await inspection.locator('[name="checked_on"]').fill("2026-10-11");
    await inspection.locator('[name="inspector"]').fill("模拟检查人");
    await inspection.locator('[name="location"]').fill(`模拟${deviceId}点`);
    await inspection
      .locator('[name="observation"]')
      .fill("隔离测试观察：等待复测资料");
    await inspection.locator('[name="follow_up"]').fill("一周后复测");
    await inspection.locator('[name="attachments"]').setInputFiles({
      name: "模拟测量.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(`point,height_mm\n${deviceId},0\n`),
    });
    await inspection.getByRole("button", { name: "保存检查记录" }).click();
    await page
      .locator("#message")
      .getByText("记录已保存", { exact: false })
      .waitFor();
    await page.getByRole("link", { name: "模拟测量.csv" }).first().waitFor();
    const oldId = live.reports[0].id;
    const oldReport = await (
      await page.request.get(`/api/reports/${oldId}`)
    ).json();
    const oldJson = JSON.stringify(oldReport);
    await page.screenshot({
      path: path.join(out, "tracking.png"),
      fullPage: true,
    });

    await page.locator('[data-action="simulation"]').click();
    await page.locator(".demo-banner").waitFor();
    await page.screenshot({
      path: path.join(out, "simulation.png"),
      fullPage: true,
    });
    await page.locator("#evaluate").click();
    await page
      .locator("#message")
      .getByText("评估已保存", { exact: false })
      .waitFor();
    live = await (await page.request.get(base)).json();
    const report = await (
      await page.request.get(`/api/reports/${live.reports[0].id}`)
    ).json();
    assert.ok(
      report.tracking.some(
        (i) =>
          i.id === manual.id &&
          i.events.some(
            (ev) => ev.kind === "inspection" && ev.attachments.length,
          ),
      ),
    );
    assert.ok(report.tracking.every((i) => !i.is_demo));
    assert.ok(
      report.archive_events.some(
        (e) => e.kind === "site_event" && e.payload.members.includes(deviceId),
      ),
    );
    assert.equal(
      JSON.stringify(
        await (await page.request.get(`/api/reports/${oldId}`)).json(),
      ),
      oldJson,
    );
    const pdf = await page.request.get(`/api/reports/${report.id}/pdf`);
    assert.equal(pdf.status(), 200);
    fs.writeFileSync(
      path.join(out, "workflow-qa-report.pdf"),
      await pdf.body(),
    );
    await page.screenshot({
      path: path.join(out, "overview.png"),
      fullPage: true,
    });
    await page.locator('nav [data-view="tracking"]').click();
    await page.locator("#show-demo").uncheck();
    assert.equal(await page.locator(".demo-banner").count(), 0);
    assert.equal(
      await page
        .locator(".issue-list")
        .getByText("模拟案例 · 载荷调整后继续观察", { exact: true })
        .count(),
      0,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(out, "tracking-mobile.png"),
      fullPage: true,
    });
    await page.locator('nav [data-view="archive"]').click();
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
        warehouse: warehouse.id,
        report: report.id,
        screenshots: out,
        isolation: "VAULT_DATA_DIR on QA server",
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
