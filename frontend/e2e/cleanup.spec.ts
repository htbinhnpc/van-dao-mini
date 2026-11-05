import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, nav, openDashboard } from "./fixtures";

async function enableQuickCleanup(page: import("@playwright/test").Page) {
  // This switch deliberately stays at its persisted value until PATCH succeeds.
  await page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true }).click();
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).toBeChecked();
  await expect(page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true })).toBeEnabled();
}

test("quick cleanup opts in without running, then disposes one fresh batch and shows detailed logs", async ({ page }, info) => {
  const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true })).toHaveCount(0);
  await enableQuickCleanup(page);
  expect(mock.mutations.filter((request) => request.path.includes("/cleanup/"))).toHaveLength(0);
  expect(mock.mutations.find((request) => request.method === "PATCH")?.body.config).toEqual({ cleanupSkipConfirmation: true });
  await page.getByRole("combobox", { name: "Cách xử lý", exact: true }).selectOption("sell");
  await page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true }).click();
  await expect(page.getByText(/Đã bán 2 món/)).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const requests = mock.mutations.filter((request) => request.path.includes("/cleanup/"));
  expect(requests.map((request) => request.path.split("/").at(-1))).toEqual(["preview", "execute"]);
  expect(requests[0].body.skipConfirmation).toBe(true);
  expect(requests[1].body).toMatchObject({ itemIds: ["weak-1", "weak-2"], skipConfirmation: true });
  await nav(page, "Nhật ký").click();
  await page.getByLabel("Tìm nhật ký", { exact: true }).fill("weak-2");
  await page.getByText("Chi tiết dọn đồ", { exact: true }).click();
  await expect(page.locator(".cleanup-log-details")).toContainText("Bỏ hỏi xác nhận (đã bật riêng)");
  await expect(page.locator(".cleanup-log-details")).toContainText("Bán lấy linh thạch");
  await expect(page.locator(".cleanup-log-details")).toContainText("Đã dọn (2)");
  await expect(page.locator(".cleanup-log-details")).toContainText("Giữ: keeper");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
  await page.screenshot({ path: info.outputPath("quick-cleanup-logs.png"), fullPage: true, animations: "disabled" });
  expect(mock.pageErrors).toEqual([]);
});

test("skip confirmation persists only for the selected account and can be disabled", async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await enableQuickCleanup(page);
  await nav(page, "Tổng quan").click(); await nav(page, "Túi đồ").click();
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).toBeChecked();
  await page.getByLabel("Tài khoản game", { exact: true }).selectOption("account-2");
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).not.toBeChecked();
  await page.getByLabel("Tài khoản game", { exact: true }).selectOption("account-1");
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).toBeChecked();
  await page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true })).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.path.includes("/cleanup/"))).toHaveLength(0);
});

test("failed preference save never enables quick disposal", async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true, saveFailures: 1 }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true }).click();
  await expect(page.locator(".cleanup-panel").getByRole("alert")).toContainText("Chưa lưu được tùy chọn");
  await expect(page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true })).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.path.includes("/cleanup/"))).toHaveLength(0);
});

test("quick mode also honors a manually reduced preview selection without a dialog", async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await enableQuickCleanup(page);
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await page.getByRole("checkbox", { name: "Dọn Thanh Khê Thiết Kiếm weak-2", exact: true }).uncheck();
  await page.getByRole("button", { name: "Phân giải 1 món đã chọn", exact: true }).click();
  await expect(page.getByText(/Đã phân giải 1 món/)).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mock.mutations.find((request) => request.path.endsWith("/cleanup/execute"))?.body.itemIds).toEqual(["weak-1"]);
});

test("quick cleanup has no blind retry and locks navigation until the result is known", async ({ page }) => {
  let release!: () => void; const holdCleanup = new Promise<void>((resolve) => { release = resolve; });
  const mock = await mockApi(page, { cleanup: true, holdCleanup, cleanupFailure: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await enableQuickCleanup(page);
  await page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true }).click();
  try {
    await expect(page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true })).toBeDisabled();
    await expect(page.getByLabel("Tài khoản game", { exact: true })).toBeDisabled();
    await expect(nav(page, "Tổng quan")).toBeDisabled();
    await expect.poll(() => mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute")).length).toBe(1);
  } finally { release(); }
  await expect(page.locator(".cleanup-panel").getByRole("alert")).toContainText("Không xác nhận được kết quả");
  await expect(page.locator(".cleanup-preview")).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(1);
});

test("quick cleanup does not execute an empty plan", async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true, cleanupEmpty: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await enableQuickCleanup(page);
  await page.getByRole("button", { name: "Tự chọn và dọn ngay", exact: true }).click();
  await expect(page.getByText("Không có bản trùng phù hợp; chưa gửi lệnh bán/phân giải.", { exact: true })).toBeVisible();
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(0);
});

test("opting out of cleanup confirmations never skips other risky feature confirmations", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Dọn túi Mini", exact: true }).check();
  await page.getByRole("switch", { name: "Dọn không hỏi xác nhận", exact: true }).check();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.method === "PATCH")).toHaveLength(1);
  await page.getByRole("switch", { name: "Tự trang bị", exact: true }).check();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Tự trang bị");
  expect(mock.mutations.filter((request) => request.method === "PATCH")).toHaveLength(1);
});

test("cleanup preview is non-destructive, explains kept gear and requires confirmation", async ({ page }, info) => {
  const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await expect(page.locator(".cleanup-items li")).toHaveCount(2);
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(0);
  await page.getByText("Xem đồ được giữ và lý do (2)", { exact: true }).click();
  await expect(page.locator(".cleanup-kept")).toContainText("Đã khóa hoặc đánh dấu yêu thích");
  await page.getByRole("checkbox", { name: "Dọn Thanh Khê Thiết Kiếm weak-2", exact: true }).uncheck();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("cleanup-preview.png"), fullPage: true, animations: "disabled" });
  const previewAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(previewAudit.violations).toEqual([]);
  await page.getByRole("button", { name: "Phân giải 1 món đã chọn", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("không thể hoàn tác");
  const confirmationAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(confirmationAudit.violations).toEqual([]);
  await page.screenshot({ path: info.outputPath("cleanup-confirmation.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Quay lại", exact: true }).click();
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(0);
  await page.getByRole("button", { name: "Phân giải 1 món đã chọn", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận phân giải 1 món", exact: true }).click();
  await expect(page.getByText(/Đã phân giải 1 món/)).toBeVisible();
  const executions = mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"));
  expect(executions).toHaveLength(1); expect(executions[0].body.itemIds).toEqual(["weak-1"]);
  await expect(page.locator(".cleanup-preview")).toHaveCount(0);
  expect(mock.pageErrors).toEqual([]);
});

test("changing filters or clearing the selection invalidates destructive action", async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await page.getByRole("button", { name: "Bỏ chọn tất cả", exact: true }).click();
  await expect(page.getByRole("button", { name: "Phân giải 0 món đã chọn", exact: true })).toBeDisabled();
  await page.getByRole("combobox", { name: "Cách xử lý", exact: true }).selectOption("sell");
  await expect(page.locator(".cleanup-preview")).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(0);
});

test("expired cleanup preview cannot be executed", async ({ page }) => {
  await page.clock.install(); const mock = await mockApi(page, { cleanup: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await expect(page.locator(".cleanup-items li")).toHaveCount(2);
  await page.clock.fastForward(121_000);
  await expect(page.getByText("Đã hết hạn — xem trước lại", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Phân giải 2 món đã chọn", exact: true })).toBeDisabled();
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(0);
});

for (const scenario of ["conflict", "failure"] as const) test(`cleanup ${scenario} clears confirmation without blindly retrying`, async ({ page }) => {
  const mock = await mockApi(page, { cleanup: true, cleanupConflict: scenario === "conflict", cleanupFailure: scenario === "failure" });
  await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await page.getByRole("button", { name: "Phân giải 2 món đã chọn", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận phân giải 2 món", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(scenario === "conflict" ? "State game đã thay đổi" : "Không xác nhận được kết quả");
  await expect(page.locator(".cleanup-preview")).toHaveCount(0);
  expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(1);
  expect(mock.pageErrors).toEqual([]);
});

test("an in-flight cleanup locks account navigation and cannot be double submitted", async ({ page }) => {
  let release!: () => void; const holdCleanup = new Promise<void>((resolve) => { release = resolve; });
  const mock = await mockApi(page, { cleanup: true, holdCleanup }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByRole("button", { name: "Xem trước đồ sẽ dọn", exact: true }).click();
  await page.getByRole("button", { name: "Phân giải 2 món đã chọn", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận phân giải 2 món", exact: true }).click();
  try {
    await expect(page.getByRole("button", { name: "Xác nhận phân giải 2 món", exact: true })).toBeDisabled();
    await expect(page.getByLabel("Tài khoản game", { exact: true })).toBeDisabled();
    await expect(page.locator("nav button").filter({ hasText: "Tổng quan" })).toBeDisabled();
    expect(mock.mutations.filter((request) => request.path.endsWith("/cleanup/execute"))).toHaveLength(1);
  } finally { release(); }
  await expect(page.getByText(/Đã phân giải 2 món/)).toBeVisible();
});

test("Mini auto cleanup defaults off and opting in requires a risk confirmation", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await expect(page.getByRole("switch", { name: "Dọn túi Mini", exact: true })).not.toBeChecked();
  await page.getByRole("switch", { name: "Dọn túi Mini", exact: true }).check();
  await expect(page.getByRole("switch", { name: "Dọn đồ rơi gốc (cũ)", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Dọn túi Mini");
  expect(mock.mutations.filter((request) => request.method === "PATCH")).toHaveLength(0);
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  const saved = mock.mutations.find((request) => request.method === "PATCH")!;
  expect(saved.body.config.autoCleanup).toBe(true); expect(saved.body.config.autoSalvage).toBe(false);
});
