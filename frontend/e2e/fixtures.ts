import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

// Synthetic accounts only. Every /api request is intercepted; no real game,
// Supabase session, .env, cookie or credential is read by these tests.
const bundledMeta = JSON.parse(readFileSync(new URL("../../data/meta.json", import.meta.url), "utf8"));
export const defaultConfig = {
  enabled: false, intervalMs: 60000, autoMinor: true, autoSalvage: false, autoSalvageTier: 0,
  autoCleanup: false, cleanupMode: "salvage", cleanupMaxRarity: "dao", cleanupMaxTier: 0,
  cleanupSkipConfirmation: false,
  cleanupKeepPerDefinition: 0, cleanupMaxItems: 20, cleanupSlots: [],
  autoSalvageMode: "salvage", autoActivity: false, activityType: "farm", huntSpotId: "",
  autoQuests: true, autoDaily: true, autoWeekly: false, autoAchievements: false, autoMail: true,
  autoX2Daily: false, autoFallbackHunt: true, autoCraft: false, craftRecipeId: "", craftKeepQty: 10,
  autoUse: false, autoUseBuffs: true, autoUseExp: false, autoUseOnlyBest: true, useThresholdMin: 15,
  autoBoss: false, bossIntervalMin: 10, bossRegionId: "", autoFarm: false, farmHarvest: true,
  farmPlant: true, farmIncludeHabitats: true, farmSeedMode: "best", farmSeedId: "", farmReserveStones: 0,
  autoEquipBest: false, autoMinorTrial: false, autoSectTasks: false, autoSeasonTasks: false,
  autoTitles: false, autoPetAdopt: false, autoNpcTalk: false, autoNpcRewards: false,
  autoHunt: false, huntPetId: "", huntReserveRuns: 0, huntIntervalMin: 10,
  autoEncounter: false, encounterAllowCost: true, autoArena: false, arenaMinPowerEdge: 5000, arenaMaxRefresh: 3, arenaMaxFights: 3,
};
export const sampleState = {
  stateVersion: 127, serverNow: 1793790385866, power: 18940,
  character: { name: "Thanh Vân", gender: "male", realm: { realmId: "ket_dan", stage: 2 }, level: 21, exp: "17640", expNeed: "24000", rateMilli: 2500, autoMinor: true },
  activity: { type: "farm", targetId: "spot_xichsa_dunes", win: true },
  stats: { hp: 13200, mp: 485, atk: 925, matk: 640, def: 510, res: .21, speed: 125, crit: .16, pen: .12, critDmg: 1.65 },
  wallet: { spirit_stone: "1248650", insight: "3420", sect_contribution: "850" },
  materials: { item_spirit_herb: 126, item_qi_pill: 8 },
  equipment: [{ id: "equip-1", defId: "equip_t1_weapon", slot: "weapon", location: "equipped", rarity: "pham", locked: true }],
  cave: { unlocked: true, plots: 4, fields: [{ plot: 1, finishAt: 100 }, { plot: 2, finishAt: 100 }, { plot: 3, finishAt: 9999999999999 }] },
  quests: [{ id: Object.keys(bundledMeta.quests)[4], status: "active", current: 2, target: 5 }, { id: Object.keys(bundledMeta.quests)[5], status: "claimable", current: 1, target: 1 }],
};
export const meta = {
  realms: bundledMeta.realms, activities: bundledMeta.activities, spots: bundledMeta.spots,
  stats: bundledMeta.stats, slots: bundledMeta.slots, rarities: bundledMeta.rarities,
  equipment: Object.fromEntries(Object.entries(bundledMeta.equipment).map(([id, item]: any) => [id, { id, name: item.name, slot: item.slot, rarity: item.rarity, reqLevel: item.reqLevel }])),
  seeds: bundledMeta.seeds, regions: bundledMeta.regions, quests: bundledMeta.quests,
  recipes: Object.fromEntries(Object.entries(bundledMeta.recipes).filter(([, recipe]: any) => ["cultivation_buff", "cultivation_exp"].includes(bundledMeta.items[recipe.output?.itemId]?.use?.type))),
  huntTargets: { x2_pet_001: { id: "x2_pet_001", name: "Bích Nhĩ Linh Thỏ", reqLevel: 16, contractSeals: 20 }, x2_pet_033: { id: "x2_pet_033", name: "Thiên Cấm Huyền Xà", reqLevel: 62, contractSeals: 360 } },
};
type Options = { authenticated?: boolean; empty?: boolean; maintenance?: boolean; saveFailures?: number; authFailure?: boolean; bootFailures?: number; metaFailures?: number; itemFailure?: boolean; itemHtml?: boolean; holdItems?: Promise<void>; cleanup?: boolean; cleanupConflict?: boolean; cleanupFailure?: boolean; cleanupEmpty?: boolean; holdCleanup?: Promise<void> };
export async function mockApi(page: Page, options: Options = {}) {
  let authenticated = options.authenticated !== false;
  let saveFailures = options.saveFailures || 0, bootFailures = options.bootFailures || 0, metaFailures = options.metaFailures || 0;
  let accounts: any[] = options.empty ? [] : [
    { id: "account-1", label: "Thanh Vân", gameUsername: "fixture_alpha", status: "active", enabled: false, config: { ...defaultConfig }, state: structuredClone(sampleState), lastTickAt: "2026-11-04T09:30:00Z" },
    { id: "account-2", label: "Mặc Trần", gameUsername: "fixture_beta", status: "active", enabled: false, config: { ...defaultConfig }, state: { ...structuredClone(sampleState), stateVersion: 400, character: { ...sampleState.character, gender: "female", name: "Mặc Trần", realm: { realmId: "truc_co", stage: 1 } } }, lastTickAt: null },
  ];
  if (options.cleanup && accounts[0]) accounts[0].state.equipment = [
    { id: "keeper", defId: "equip_t1_weapon", slot: "weapon", location: "equipped", enhance: 0, locked: false, favorite: false, subs: [{ stat: "atk", add: 10 }] },
    { id: "weak-1", defId: "equip_t1_weapon", slot: "weapon", location: "bag", enhance: 0, locked: false, favorite: false, subs: [{ stat: "atk", add: 2 }] },
    { id: "weak-2", defId: "equip_t1_weapon", slot: "weapon", location: "bag", enhance: 0, locked: false, favorite: false, subs: [{ stat: "atk", add: 1 }] },
    { id: "protected", defId: "equip_t1_weapon", slot: "weapon", location: "bag", enhance: 0, locked: true, favorite: true, subs: [{ stat: "atk", add: 0 }] },
  ];
  const mutations: { method: string; path: string; body: any }[] = [], pageErrors: string[] = [], external: string[] = [];
  const cleanupLogs: Record<string, any[]> = {}, cleanupRules: Record<string, any> = {};
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => { if (!request.url().startsWith("http://127.0.0.1:4175")) external.push(request.url()); });
  await page.route("**/api/**", async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    const body = request.postDataJSON();
    if (method !== "GET") mutations.push({ method, path, body });
    const reply = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path.endsWith("/auth/me")) {
      if (bootFailures-- > 0) return reply({ detail: "Dịch vụ tạm thời gián đoạn" }, 503);
      return authenticated ? reply({ user: { id: "fixture-user", username: "Đạo hữu" } }) : reply({ detail: "Chưa đăng nhập" }, 401);
    }
    if (path.endsWith("/auth/login") || path.endsWith("/auth/bootstrap")) {
      if (options.authFailure) return reply({ detail: "Thông tin đăng nhập không đúng" }, 401);
      authenticated = true; return reply({ user: { id: "fixture-user", username: "Đạo hữu" } });
    }
    if (path.endsWith("/auth/logout")) { authenticated = false; return reply({ ok: true }); }
    if (path.endsWith("/meta")) { if (metaFailures-- > 0) return reply({ detail: "Metadata tạm thời lỗi" }, 503); return reply(meta); }
    if (path.endsWith("/game/server-status")) return reply({ status: options.maintenance ? "maintenance" : "active", maintenance: options.maintenance ? { message: "Bảo trì định kỳ của game" } : null });
    if (path.endsWith("/dashboard/overview")) return reply({ accounts });
    if (path === "/api/v1/accounts" && method === "POST") {
      const account = { id: "account-new", label: body.label, gameUsername: body.username, status: "active", enabled: false, state: sampleState, config: { ...defaultConfig } };
      accounts.push(account); return reply({ account }, 201);
    }
    const accountId = path.split("/")[4], account = accounts.find((row) => row.id === accountId);
    if (method === "DELETE" && account) { accounts = accounts.filter((row) => row.id !== accountId); return reply({ ok: true }); }
    if (!account) return reply({ detail: "Không tìm thấy fixture" }, 404);
    if (path.endsWith("/cleanup/preview")) { cleanupRules[accountId] = body.rules; return reply({
      previewId: options.cleanupEmpty ? null : "11111111-1111-4111-8111-111111111111", expiresAt: Math.floor(Date.now() / 1000) + 120,
      state: account.state,
      plan: { stateVersion: account.state.stateVersion, scanned: account.state.equipment.length, candidateCount: 2, deferredCount: 0,
        items: (options.cleanupEmpty ? [] : ["weak-1", "weak-2"]).map((id) => ({ id, name: "Thanh Khê Thiết Kiếm", rarity: "pham", tier: 1, slot: "weapon", reasonLabel: "Không mặc; giữ món đang trang bị cùng ô", keptItemId: "keeper" })),
        kept: [{ id: "keeper", name: "Thanh Khê Thiết Kiếm", reasonLabel: "Đang mặc" }, { id: "protected", name: "Thanh Khê Thiết Kiếm đã khóa", reasonLabel: "Đã khóa hoặc đánh dấu yêu thích" }],
        summary: [{ reason: "protected", label: "Đã khóa hoặc đánh dấu yêu thích", count: 1 }],
      },
    }); }
    if (path.endsWith("/cleanup/execute")) {
      if (options.holdCleanup) await options.holdCleanup;
      if (options.cleanupConflict) return reply({ detail: "State game đã thay đổi từ lúc xem trước. Hãy xem trước lại; chưa dọn món nào." }, 409);
      if (options.cleanupFailure) return reply({ detail: "Không xác nhận được kết quả dọn. Đồng bộ túi và kiểm tra nhật ký; không tự gửi lại lệnh." }, 502);
      account.state.equipment = account.state.equipment.filter((item: any) => !body.itemIds.includes(item.id)); account.state.stateVersion++;
      (cleanupLogs[accountId] ||= []).unshift({ id: 100, level: "success", action: "cleanup.manual", message: `Đã dọn ${body.itemIds.length} món (${body.skipConfirmation ? "không hỏi xác nhận" : "có xác nhận"}).`, created_at: new Date().toISOString(), details: {
        source: body.skipConfirmation ? "quick" : "manual", confirmation: body.skipConfirmation ? "skipped" : "dialog", status: "succeeded",
        mode: cleanupRules[accountId]?.mode || "salvage", rules: cleanupRules[accountId], itemIds: body.itemIds, removedIds: body.itemIds,
        stateVersionBefore: account.state.stateVersion - 1, stateVersionAfter: account.state.stateVersion,
        items: body.itemIds.map((id: string) => ({ id, defId: "equip_t1_weapon", name: "Thanh Khê Thiết Kiếm", keptItemId: "keeper" })),
      } });
      return reply({ state: account.state, removedCount: body.itemIds.length, mode: cleanupRules[accountId]?.mode || "salvage" });
    }
    if (path.endsWith("/state")) return reply({ state: account.state });
    if (path.endsWith("/config") && method === "PATCH") {
      if (saveFailures-- > 0) return reply({ detail: "Lưu cấu hình thất bại. Hãy thử lại." }, 500);
      account.config = { ...account.config, ...body.config }; account.enabled = account.config.enabled;
      return reply({ config: account.config, enabled: account.enabled });
    }
    if (path.endsWith("/config")) return reply({ config: account.config });
    if (path.endsWith("/tick")) { account.state.stateVersion += 1; return reply({ state: account.state, completed: true }); }
    if (path.endsWith("/items")) {
      if (options.holdItems) await options.holdItems;
      if (options.itemFailure) return reply({ detail: "Không tải được hành trang" }, 502);
      if (options.itemHtml) return route.fulfill({ status: 200, contentType: "text/html", body: "<html>Not JSON</html>" });
      return reply({ wallet: account.state.wallet, items: [{ id: "item_spirit_herb", name: "Linh thảo", kind: "material", qty: 126, desc: "Linh thảo mọc nơi có linh khí." }, { id: "item_qi_pill", name: "Dưỡng Khí Đan", kind: "consumable", qty: 8 }] });
    }
    if (path.endsWith("/logs")) return reply({ logs: [
      ...(cleanupLogs[accountId] || []),
      { id: 1, level: "success", action: "settle", message: "Kết toán tu vi: +2400", created_at: "2026-11-04T09:30:00Z" },
      { id: 2, level: "warning", action: "boss.fight", message: "Boss chưa hết hồi chiêu", created_at: "2026-11-04T09:25:00Z" },
      { id: 3, level: "error", action: "automation.tick", message: "Dừng vòng vì state thay đổi", created_at: "2026-11-04T09:20:00Z" },
    ] });
    return reply({ detail: `Unmocked API: ${method} ${path}` }, 404);
  });
  return { mutations, pageErrors, external };
}
export async function openDashboard(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hành trình tu đạo", exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Tiến độ tu vi" })).toBeVisible();
}
export const nav = (page: Page, name: string) => page.getByRole("navigation", { name: "Điều hướng chính" }).getByRole("button", { name, exact: true });
