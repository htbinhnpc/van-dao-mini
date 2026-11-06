import { test, expect } from "@playwright/test";
import { mockApi, nav, openDashboard } from "./fixtures";

test("sect donation is opt-in with reserves and daily cap, checkin is separate", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  await expect(page.getByRole("switch", { name: "Quyên góp vật phẩm dư", exact: true })).toBeDisabled();
  await expect(page.getByRole("switch", { name: "Điểm danh bang hội", exact: true })).not.toBeChecked();
  await page.getByRole("switch", { name: "Nhiệm vụ tông môn", exact: true }).check();
  await page.getByRole("switch", { name: "Quyên góp vật phẩm dư", exact: true }).check();
  await page.getByRole("switch", { name: "Điểm danh bang hội", exact: true }).check();
  await page.getByRole("spinbutton", { name: /Sàn vật phẩm quyên góp/ }).fill("500");
  await page.getByRole("spinbutton", { name: /Cống hiến quyên góp tối đa/ }).fill("200");
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Quyên góp vật phẩm dư");
  expect(mock.mutations).toHaveLength(0);
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  expect(mock.mutations).toHaveLength(1);
  expect(mock.mutations[0].body.config).toMatchObject({ autoSectTasks: true, autoSectDonate: true, autoGuildCheckin: true, sectDonateMatFloor: 500, sectDonateDaily: 200 });
  expect(mock.mutations[0].path).toBe("/api/v1/accounts/account-1/config");
  expect(mock.external).toEqual([]);
});

test("world and guild bosses have independent opt-in switches and risk confirmation", async ({ page }) => {
  const mock = await mockApi(page); await openDashboard(page); await nav(page, "Tự động").click();
  for (const name of ["Đánh boss thế giới", "Đánh boss bang hội"]) {
    await expect(page.getByRole("switch", { name, exact: true })).not.toBeChecked();
    await page.getByRole("switch", { name, exact: true }).check();
  }
  await page.getByRole("button", { name: "Lưu cấu hình", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Đánh boss thế giới");
  await expect(page.getByRole("dialog")).toContainText("Đánh boss bang hội");
  expect(mock.mutations).toHaveLength(0);
  await page.getByRole("button", { name: "Xác nhận & lưu", exact: true }).click();
  await expect(page.getByText("Đã đồng bộ cấu hình", { exact: true })).toBeVisible();
  expect(mock.mutations).toHaveLength(1);
  expect(mock.mutations[0].body.config).toMatchObject({ autoWorldBoss: true, autoGuildBoss: true, autoBoss: false });
  expect(mock.mutations.filter((request) => request.path.endsWith("/tick") || request.path.endsWith("/command"))).toHaveLength(0);
});
