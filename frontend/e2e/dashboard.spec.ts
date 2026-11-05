import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, nav, openDashboard } from "./fixtures";

test("overview uses real metadata shapes, top-level stats and local game art", async ({ page }, info) => {
  const mock = await mockApi(page); await openDashboard(page);
  await expect(page.getByRole("heading", { name: "Kết Đan · Trung kỳ" })).toBeVisible();
  await expect(page.getByText("Đụn cát đỏ", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("13.200", { exact: true })).toBeVisible();
  await expect(page.getByText("1.248.650", { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "74");
  await expect(page.getByRole("heading", { name: "Động phủ", exact: true })).toBeVisible();
  await expect(page.locator(".cave-room")).toHaveCount(7);
  await expect(page.locator(".cave-room").filter({ hasText: "Đan Phòng" })).toContainText("Cấp 2/6");
  await expect(page.locator(".cultivator-art")).toHaveJSProperty("naturalWidth", 512);
  expect(mock.mutations).toEqual([]); expect(mock.external).toEqual([]); expect(mock.pageErrors).toEqual([]);
  await page.screenshot({ path: info.outputPath("overview.png"), fullPage: true, animations: "disabled" });
});

test("all destinations work and account switching never mixes snapshots", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page);
  for (const name of ["Túi đồ", "Tự động", "Tài khoản", "Nhật ký", "Tổng quan"]) { await nav(page, name).click(); await expect(nav(page, name)).toHaveAttribute("aria-current", "page"); }
  await page.getByLabel("Tài khoản game", { exact: true }).selectOption("account-2");
  await expect(page.getByRole("heading", { name: "Trúc Cơ · Sơ kỳ" })).toBeVisible();
  await expect(page.locator(".scene-eyebrow")).toHaveText("Mặc Trần");
  await expect(page.locator(".cultivator-art")).toHaveAttribute("src", /female/);
  expect(mock.pageErrors).toEqual([]);
});

test("safe config save is scoped, single-flight, and updates dirty state", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await expect(page.getByRole("button", { name: "Lưu cấu hình", exact: true })).toBeDisabled();
  await page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true }).uncheck();
  await expect(page.getByText("Có thay đổi chưa lưu", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByText("Đã lưu cấu hình tu hành.", { exact: true })).toBeVisible();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  expect(mock.mutations).toHaveLength(1); expect(mock.mutations[0].path).toBe("/api/v1/accounts/account-1/config");
  expect(mock.mutations[0].body.config.autoQuests).toBe(false);
  expect(mock.mutations.some((request) => request.path.endsWith("/tick"))).toBe(false);
});

test("cave auto saves room order and reserves only after confirmation", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Tự nâng phòng động phủ", exact: true }).check();
  await page.getByLabel("Thứ tự nâng phòng", { exact: false }).selectOption("balanced");
  await page.getByLabel("Động phủ: linh thạch dự trữ", { exact: false }).fill("2500");
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Tự nâng phòng động phủ");
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu cấu hình tu hành.", { exact: true })).toBeVisible();
  expect(mock.mutations).toHaveLength(1);
  expect(mock.mutations[0].body.config).toMatchObject({ autoCaveUpgrade: true, caveRoomOrder: "balanced", caveReserveStones: 2500 });
});

test("risky auto needs a target and explicit confirmation before saving", async ({ page }, info) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Săn khế ấn", exact: true }).check();
  await expect(page.getByRole("button", { name: "Lưu cấu hình", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("chọn linh thú mục tiêu");
  await page.getByLabel("Linh thú mục tiêu săn khế ấn", { exact: false }).selectOption("x2_pet_001");
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible(); expect(mock.mutations).toHaveLength(0);
  await expect(page.getByRole("dialog")).toContainText("Săn khế ấn");
  await page.screenshot({ path: info.outputPath("risky-confirmation.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(mock.mutations).toHaveLength(1); expect(mock.mutations[0].body.config.huntPetId).toBe("x2_pet_001");
});

test("navigation protects unsaved edits and cancel never submits the form", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true }).uncheck();
  await nav(page, "Túi đồ").click(); await expect(page.getByRole("dialog")).toContainText("Cấu hình chưa được lưu");
  await page.getByRole("button", { name: "Quay lại", exact: true }).click();
  await expect(page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true })).not.toBeChecked();
  expect(mock.mutations).toHaveLength(0);
  await nav(page, "Túi đồ").click(); await page.getByRole("button", { name: "Bỏ thay đổi & tiếp tục", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Hành trang", exact: true })).toBeVisible();
  await nav(page, "Tự động").click(); await expect(page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true })).toBeChecked();
});

test("account switching also protects unsaved edits", async ({ page }) => {
  await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true }).uncheck();
  await page.getByLabel("Tài khoản game", { exact: true }).selectOption("account-2");
  await expect(page.getByRole("dialog")).toContainText("Cấu hình chưa được lưu");
  await page.keyboard.press("Escape"); await expect(page.getByLabel("Tài khoản game", { exact: true })).toHaveValue("account-1");
});

test("failed save preserves edits for retry without false success", async ({ page }) => {
  const mock = await mockApi(page, { saveFailures: 1 }); await openDashboard(page); await nav(page, "Tự động").click();
  await page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true }).uncheck();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Lưu cấu hình thất bại");
  await expect(page.getByRole("switch", { name: "Nhiệm vụ chính", exact: true })).not.toBeChecked();
  await expect(page.getByText("Có thay đổi chưa lưu", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  expect(mock.mutations).toHaveLength(2);
});

test("manual game tick requires confirmation and sends exactly once", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page);
  await page.getByRole("button", { name: "Chạy một vòng ngay", exact: true }).click();
  await page.getByRole("button", { name: "Quay lại", exact: true }).click(); expect(mock.mutations).toHaveLength(0);
  await page.getByRole("button", { name: "Chạy một vòng ngay", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Chạy một vòng", exact: true }).click();
  await expect(page.getByText(/Đã xử lý một vòng/)).toBeVisible();
  expect(mock.mutations.filter((request) => request.path.endsWith("/tick"))).toHaveLength(1);
  await expect(page.locator(".panel-footnote").filter({ hasText: "Dữ liệu đã lưu từ game" })).toContainText("128");
});

test("deleting an account is confirmed and never deletes the game character", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tài khoản").click();
  const card = page.locator(".account-card").filter({ has: page.getByRole("heading", { name: "Thanh Vân", exact: true }) });
  await card.getByRole("button", { name: "Gỡ liên kết", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Nhân vật game không bị xóa");
  await page.getByRole("dialog").getByRole("button", { name: "Gỡ liên kết", exact: true }).click();
  await expect(page.locator(".account-card")).toHaveCount(1);
  await expect(page.getByLabel("Tài khoản game", { exact: true })).toHaveValue("account-2");
  expect(mock.mutations.filter((request) => request.method === "DELETE")).toHaveLength(1);
});

test("inventory searches Vietnamese without accents, shows equipment and safe details", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Túi đồ").click();
  await page.getByLabel("Tìm vật phẩm", { exact: true }).fill("linh thao");
  await expect(page.locator(".item-card")).toHaveCount(1); await page.locator(".item-card").click();
  await expect(page.getByRole("dialog")).toContainText("Linh thảo");
  await page.keyboard.press("Escape"); await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByLabel("Tìm vật phẩm", { exact: true }).fill(""); await page.getByLabel("Loại vật phẩm", { exact: true }).selectOption("equipment");
  await expect(page.locator(".item-card")).toHaveCount(1); await expect(page.locator(".item-card")).toContainText("Thanh Khê Thiết Kiếm");
  await page.getByRole("button", { name: "Danh sách", exact: true }).click(); await expect(page.locator(".inventory-list")).toBeVisible();
  expect(mock.mutations).toEqual([]);
});

test("inventory errors are not presented as an empty bag", async ({ page }) => {
  await mockApi(page, { itemFailure: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await expect(page.getByRole("alert")).toContainText("Không tải được hành trang");
  await expect(page.getByText("Hành trang còn trống", { exact: true })).toHaveCount(0);
});

test("a non-JSON API response gets actionable error feedback", async ({ page }) => {
  const mock = await mockApi(page, { itemHtml: true }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await expect(page.getByRole("alert")).toContainText("dữ liệu không hợp lệ"); expect(mock.pageErrors).toEqual([]);
});

test("inventory has a loading state, not an incorrect empty state", async ({ page }) => {
  let release!: () => void; const holdItems = new Promise<void>((resolve) => { release = resolve; });
  await mockApi(page, { holdItems }); await openDashboard(page); await nav(page, "Túi đồ").click();
  await expect(page.getByRole("status", { name: "Đang tải dữ liệu" })).toBeVisible();
  await expect(page.getByText("Hành trang còn trống", { exact: true })).toHaveCount(0); release();
  await expect(page.locator(".item-card").first()).toBeVisible();
});

test("log filters use friendly labels and retain error messages", async ({ page }) => {
  await mockApi(page); await openDashboard(page); await nav(page, "Nhật ký").click();
  await page.getByLabel("Mức nhật ký", { exact: true }).selectOption("warning"); await expect(page.locator(".timeline > li")).toHaveCount(1);
  await expect(page.locator(".timeline")).toContainText("Boss chưa hết hồi chiêu");
  await page.getByLabel("Tìm nhật ký", { exact: true }).fill("khong-co-muc-nao");
  await expect(page.getByRole("heading", { name: "Không có nhật ký phù hợp", exact: true })).toBeVisible();
});

test("boot outage has retry instead of incorrectly signing the user out", async ({ page }) => {
  await mockApi(page, { bootFailures: 1 }); await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Dịch vụ tạm thời gián đoạn");
  await expect(page.getByRole("button", { name: "Đăng nhập", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Hành trình tu đạo", exact: true })).toBeVisible();
});

test("metadata failure never renders an object and can recover", async ({ page }) => {
  const mock = await mockApi(page, { metaFailures: 1 }); await openDashboard(page);
  await expect(page.getByText(/Chưa tải được tên vật phẩm/)).toBeVisible();
  await page.getByRole("button", { name: "Tải lại metadata", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Kết Đan · Trung kỳ", exact: true })).toBeVisible(); expect(mock.pageErrors).toEqual([]);
});

test("maintenance blocks manual ticks but preserves read-only dashboard", async ({ page }) => {
  const mock = await mockApi(page, { maintenance: true }); await openDashboard(page);
  await expect(page.getByText("Bảo trì định kỳ của game", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Chạy một vòng ngay", exact: true })).toBeDisabled(); expect(mock.mutations).toEqual([]);
});

test("empty accounts have onboarding and a safe account linking flow", async ({ page }) => {
  const mock = await mockApi(page, { empty: true }); await page.goto("/");
  await expect(page.getByRole("heading", { name: "Liên kết tài khoản game", exact: true })).toBeVisible();
  await page.getByLabel("Tên đăng nhập game", { exact: true }).fill("fixture_new");
  await page.getByLabel("Mật khẩu game", { exact: true }).fill("synthetic-test-password");
  await page.getByRole("button", { name: "Đăng nhập & liên kết", exact: true }).click();
  await expect(page.getByRole("progressbar")).toBeVisible();
  expect(mock.mutations.filter((request) => request.path === "/api/v1/accounts")).toHaveLength(1);
});

test("login handles auth errors, password visibility and first-time setup", async ({ page }, info) => {
  const mock = await mockApi(page, { authenticated: false, authFailure: true }); await page.goto("/");
  await expect(page.getByRole("heading", { name: "Trở về động phủ", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("login.png"), fullPage: true });
  await page.getByLabel("Tên đăng nhập", { exact: true }).fill("fixture_user"); await page.getByLabel("Mật khẩu", { exact: true }).fill("synthetic-password");
  await page.getByRole("button", { name: "Hiện mật khẩu", exact: true }).click(); await expect(page.getByLabel("Mật khẩu", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click(); await expect(page.getByRole("alert")).toContainText("không đúng");
  await page.getByRole("button", { name: /Lần đầu ghé thăm/ }).click(); await expect(page.getByLabel("Setup token", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Mật khẩu", { exact: true })).toBeEmpty(); expect(mock.pageErrors).toEqual([]);
});

test("keyboard focus is trapped in confirmation and Escape restores the action", async ({ page }) => {
  await mockApi(page); await openDashboard(page); const action = page.getByRole("button", { name: "Chạy một vòng ngay", exact: true });
  await action.click(); const dialog = page.getByRole("dialog"); await expect(dialog.getByRole("button", { name: "Quay lại", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab"); await expect(dialog.getByRole("button", { name: "Chạy một vòng", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(dialog.getByRole("button", { name: "Quay lại", exact: true })).toBeFocused();
  await page.keyboard.press("Escape"); await expect(dialog).not.toBeVisible(); await expect(action).toBeFocused();
});

test("WCAG checks pass for all main screens", async ({ page }) => {
  await mockApi(page); await openDashboard(page);
  for (const screen of ["Tổng quan", "Tự động", "Túi đồ", "Tài khoản", "Nhật ký"]) {
    await nav(page, screen).click();
    await expect(page.getByRole("status", { name: "Đang tải dữ liệu" })).toHaveCount(0);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations, `${screen}: ${JSON.stringify(results.violations.map((item) => ({ id: item.id, nodes: item.nodes.map((node) => node.target) })))}`).toEqual([]);
  }
});

test("responsive layouts do not overflow from 320px to desktop", async ({ page }, info) => {
  await mockApi(page); await openDashboard(page);
  for (const width of [320, 375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    for (const screen of ["Tổng quan", "Tự động", "Túi đồ", "Tài khoản", "Nhật ký"]) {
      await nav(page, screen).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${screen} at ${width}px`).toBe(true);
    }
  }
  await nav(page, "Tự động").click(); await page.screenshot({ path: info.outputPath("automation.png"), fullPage: true, animations: "disabled" });
});

test("logout is reachable on mobile and desktop without changing game state", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page);
  await page.getByRole("button", { name: "Đăng xuất", exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole("heading", { name: "Trở về động phủ", exact: true })).toBeVisible();
  expect(mock.mutations).toEqual([{ method: "POST", path: "/api/v1/auth/logout", body: null }]);
});

test("account card summarises the character, toggles auto and opens features in a modal", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tài khoản").click();
  const card = page.locator(".account-card").filter({ has: page.getByRole("heading", { name: "Thanh Vân", exact: true }) });
  const row = (label: string) => card.locator(".account-details > div").filter({ has: page.getByText(label, { exact: true }) });
  await expect(row("Nhân vật")).toContainText("Thanh Vân");
  await expect(row("Tông môn")).toContainText("Chưa gia nhập tông môn");
  await expect(row("Tốc độ tu vi")).toContainText("2,50 tu vi/giây");
  await expect(row("Dự kiến đủ tu vi")).not.toContainText("Chưa có dữ liệu");
  const toggle = card.getByRole("switch", { name: "Trợ lý tự động của Thanh Vân" });
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  expect(mock.mutations.filter((request) => request.method === "PATCH")).toEqual([
    expect.objectContaining({ path: "/api/v1/accounts/account-1/config", body: { config: { enabled: true } } }),
  ]);
  await card.getByRole("button", { name: "Tính năng", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Tính năng · Thanh Vân" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Săn khế ấn").first()).toBeVisible();
  const box = (await dialog.boundingBox())!, viewport = page.viewportSize()!;
  expect(box.width).toBeGreaterThanOrEqual(Math.min(1000, viewport.width - 40));
  await expect(dialog.getByRole("button", { name: "Lưu cấu hình" })).toBeInViewport();
  await dialog.getByRole("button", { name: "Đóng tính năng" }).click();
  await expect(dialog).toBeHidden();
});
