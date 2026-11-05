import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, nav, openDashboard } from "./fixtures";

test("profession dashboard shows four tracks, ETA, budget and furnace reasons without mutations", async ({ page }, info) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Chế tạo").click();
  await expect(page.getByText("Giai đoạn: Cày tay nghề", { exact: true })).toBeVisible();
  await expect(page.locator(".craft-profession")).toHaveCount(4);
  await expect(page.getByRole("progressbar", { name: "Tiến độ Rèn khí", exact: true })).toHaveAttribute("value", "20");
  await expect(page.locator(".craft-professions")).toContainText("ETA tới max (ước tính)");
  await expect(page.locator(".craft-budget")).toContainText("20.000");
  await expect(page.locator(".craft-furnaces li")).toHaveCount(4);
  await expect(page.locator(".craft-furnaces")).toContainText("Dồn lò cày Rèn khí");
  await page.getByText("Công thức/nghề bị chặn (1)", { exact: true }).click();
  await expect(page.locator(".craft-blocked")).toContainText("Thiếu nguyên liệu dư");
  await page.getByRole("button", { name: "Đồng bộ lò", exact: true }).click();
  await expect(page.locator(".craft-profession")).toHaveCount(4);
  expect(mock.mutations).toEqual([]);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("craft-professions.png"), fullPage: true, animations: "disabled" });
  expect(mock.pageErrors).toEqual([]);
});

test("profession production only appears with explicit all-max state", async ({ page }) => {
  const mock = await mockApi(page, { craftMax: true }); await openDashboard(page); await nav(page, "Chế tạo").click();
  await expect(page.getByText("Giai đoạn: Sản xuất", { exact: true })).toBeVisible();
  await expect(page.locator(".craft-profession").filter({ hasText: "Đã tối đa" })).toHaveCount(4);
  await expect(page.locator(".craft-next")).toContainText("×1");
  expect(mock.mutations).toEqual([]);
});

test("missing profession state is not rendered as max or empty furnaces", async ({ page }) => {
  await mockApi(page, { craftUnknown: true }); await openDashboard(page); await nav(page, "Chế tạo").click();
  await expect(page.getByText("Giai đoạn: Chưa đủ dữ liệu tay nghề", { exact: true })).toBeVisible();
  await expect(page.locator(".craft-profession").filter({ hasText: "Chưa có dữ liệu" })).toHaveCount(4);
  await expect(page.locator(".craft-next")).toHaveCount(0);
});

test("craft state request is canceled on account switch, with no cross-account snapshot", async ({ page }) => {
  let release!: () => void; const holdCraft = new Promise<void>((resolve) => { release = resolve; });
  const mock = await mockApi(page, { holdCraft }); await openDashboard(page); await nav(page, "Chế tạo").click();
  await expect(page.getByText("Đang đọc trạng thái lò…", { exact: true })).toBeVisible();
  await page.getByLabel("Tài khoản game", { exact: true }).selectOption("account-2");
  release();
  await expect(page.locator(".craft-phase")).toContainText("state v400");
  expect(mock.mutations).toEqual([]); expect(mock.pageErrors).toEqual([]);
});

test("craft request failure has retry feedback, never false empty or success", async ({ page }) => {
  const mock = await mockApi(page, { craftFailure: true }); await openDashboard(page); await nav(page, "Chế tạo").click();
  await expect(page.getByRole("alert")).toContainText("Không đọc được trạng thái chế tạo");
  await expect(page.locator(".craft-furnaces")).toHaveCount(0);
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Không đọc được trạng thái chế tạo");
  expect(mock.mutations).toEqual([]);
});

test("craft settings are account scoped and require explicit risk confirmation", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Chế tạo").click();
  await page.getByRole("button", { name: "Cài đặt chế tạo", exact: true }).click();
  await expect(page.getByRole("switch", { name: "Cày tay nghề", exact: true })).toBeDisabled();
  await page.getByRole("switch", { name: "Tự chế tạo", exact: true }).check();
  await expect(page.getByRole("switch", { name: "Cày tay nghề", exact: true })).toBeChecked();
  await page.getByRole("combobox", { name: "Thứ tự cày nghề", exact: true }).selectOption("all-max-first");
  await page.getByRole("spinbutton", { name: /Ngân sách cày\/ngày/ }).fill("15");
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Tự chế tạo");
  expect(mock.mutations.filter((request) => request.method === "PATCH")).toHaveLength(0);
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  const saved = mock.mutations.find((request) => request.method === "PATCH")!;
  expect(saved.path).toContain("account-1");
  expect(saved.body.config).toMatchObject({ autoCraft: true, craftMastery: true, craftProduce: true, craftLevelOrder: "all-max-first", craftLevelDaily: 15 });
  expect(mock.mutations.filter((request) => request.path.endsWith("/tick") || request.path.endsWith("/command"))).toHaveLength(0);
});
