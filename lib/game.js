import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import crypto from 'node:crypto';
import { decryptSecret, supabaseRest } from './cloud.js';

const ORIGIN = process.env.GAME_ORIGIN || 'https://vandaonghichmenh.hongvan.net:60010';
const META = JSON.parse(readFileSync(resolve(process.cwd(), 'data/meta.json'), 'utf8'));

function headers(cookie, extra = {}) {
  return {
    origin: ORIGIN,
    referer: `${ORIGIN}/`,
    cookie,
    'user-agent': 'VanDaoMiniClient/1.0',
    ...extra,
  };
}

export async function gameFetch(cookie, route, options = {}) {
  const response = await fetch(`${ORIGIN}${route}`, {
    ...options,
    headers: headers(cookie, options.headers || {}),
    signal: AbortSignal.timeout(25000),
  });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { data = null; }
  if (!response.ok || data?.ok === false) {
    const error = new Error(data?.message || data?.errorCode || `Game API HTTP ${response.status}`);
    error.status = response.status;
    error.code = data?.errorCode || `HTTP_${response.status}`;
    throw error;
  }
  return data || {};
}

export async function loadGameState(account) {
  const cookie = decryptSecret(account);
  const result = await gameFetch(cookie, '/api/state');
  if (!result.state) throw new Error('Game API không trả trạng thái nhân vật.');
  return { cookie, state: result.state };
}

export async function sendGameCommand(account, state, command, payload = {}) {
  const cookie = decryptSecret(account);
  const result = await gameFetch(cookie, `/api/cmd/${encodeURIComponent(command)}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'idempotency-key': crypto.randomUUID(),
    },
    body: JSON.stringify({ payload, expectedVersion: state?.stateVersion ?? 1 }),
  });
  return result;
}

export async function persistAccountState(accountId, state, extra = {}) {
  await supabaseRest('game_accounts', {
    method: 'PATCH',
    query: `id=eq.${encodeURIComponent(accountId)}`,
    prefer: 'return=minimal',
    body: { state_snapshot: state, updated_at: new Date().toISOString(), ...extra },
  });
}

export async function appendLog(account, level, message, detail = null) {
  await supabaseRest('automation_logs', {
    method: 'POST',
    prefer: 'return=minimal',
    body: {
      owner_id: account.owner_id,
      account_id: account.id,
      level,
      message,
      detail: detail ? String(detail).slice(0, 500) : null,
    },
  });
}

function countItem(state, id) {
  return Number(state.materials?.[id] || 0);
}

async function commandUpdate(account, state, command, payload, label) {
  const result = await sendGameCommand(account, state, command, payload);
  const next = result.state || state;
  if (label) await appendLog(account, 'success', label);
  return next;
}

async function claimReady(account, state, config) {
  const tasks = [];
  if (config.autoQuests) {
    for (const item of (state.quests || []).filter((quest) => quest.status === 'claimable').slice(0, 6)) {
      tasks.push(['quest.claim', { questId: item.id }, 'Nhận thưởng nhiệm vụ']);
    }
  }
  if (config.autoDaily) {
    const claims = Number(state.periodic?.dailyClaims || 0);
    const ready = (state.periodic?.daily || []).filter((task) => !task.claimed && Number(task.current) >= Number(task.target)).slice(0, Math.max(0, 4 - claims));
    for (const task of ready) tasks.push(['daily.claim', { taskId: task.id }, 'Nhận mốc ngày']);
  }
  if (config.autoWeekly) {
    for (const task of (state.periodic?.weekly || []).filter((entry) => !entry.claimed && Number(entry.current) >= Number(entry.target)).slice(0, 3)) {
      tasks.push(['weekly.claim', { taskId: task.id }, 'Nhận mốc tuần']);
    }
  }
  if (config.autoAchievements) {
    for (const task of (state.periodic?.achievements || []).filter((entry) => !entry.claimed && Number(entry.current) >= Number(entry.target)).slice(0, 6)) {
      tasks.push(['achievement.claim', { achievementId: task.id }, 'Nhận thành tựu']);
    }
  }
  for (const [cmd, payload, label] of tasks.slice(0, 3)) {
    try { state = await commandUpdate(account, state, cmd, payload, label); }
    catch (error) { await appendLog(account, 'warn', `${label} thất bại`, error.message); }
  }
  if (config.autoX2Daily && state.x2 && !state.x2.dailyClaimed) {
    try { state = await commandUpdate(account, state, 'x2.daily.claim', {}, 'Nhận phần thưởng mở rộng ngày'); }
    catch (error) { await appendLog(account, 'warn', 'Nhận phần mở rộng thất bại', error.message); }
  }
  if (config.autoMail && Number(state.unreadMail || state.mail?.unreadCount || 0) > 0) {
    try { state = await commandUpdate(account, state, 'mail.claimAll', {}, 'Nhận thư có quà'); }
    catch (error) { await appendLog(account, 'warn', 'Nhận thư thất bại', error.message); }
  }
  return state;
}

async function ensureActivity(account, state, config) {
  if (!config.autoActivity) return state;
  let type = config.activityType || 'seclusion';
  let targetId = null;
  if (type === 'farm') {
    const unlocked = new Set((state.regions || []).filter((region) => region.unlocked).map((region) => region.id));
    const spots = Object.values(META.spots || {}).filter((spot) => unlocked.has(spot.regionId)
      && Number(spot.reqLevel || 0) <= Number(state.character?.level || 0));
    if (config.autoFallbackHunt && state.activity?.type === 'farm' && state.activity?.win === false) {
      const current = META.spots?.[state.activity.targetId];
      const fallback = spots.filter((spot) => !current || Number(spot.reqLevel || 0) < Number(current.reqLevel || 0))
        .sort((a, b) => Number(b.reqLevel || 0) - Number(a.reqLevel || 0))[0];
      if (fallback) {
        targetId = fallback.id;
        await appendLog(account, 'warn', 'Hạ điểm săn sau khi thua', fallback.id);
      } else {
        type = 'seclusion';
      }
    }
    const spot = (config.huntSpotId && spots.find((entry) => entry.id === config.huntSpotId))
      || (!targetId && spots.sort((a, b) => Number(b.expPerCycle || 0) - Number(a.expPerCycle || 0))[0]);
    if (!spot) {
      if (type === 'farm') {
        await appendLog(account, 'warn', 'Không có điểm săn phù hợp');
        return state;
      }
    }
    if (spot) targetId = targetId || spot.id;
  }
  if (state.activity?.type === type && (type !== 'farm' || state.activity?.targetId === targetId)) return state;
  try {
    const payload = type === 'farm' ? { type, targetId } : { type };
    const result = await sendGameCommand(account, state, 'activity.set', payload);
    await appendLog(account, 'info', 'Đã chuyển hoạt động', type === 'farm' ? targetId : type);
    return result.state || state;
  } catch (error) {
    await appendLog(account, 'warn', 'Không chuyển được hoạt động', error.message);
    return state;
  }
}

function recipeCanCraft(state, recipe) {
  if (!recipe || Number(state.character?.level || 0) < Number(recipe.reqLevel || 0)) return false;
  if (Number(state.wallet?.spirit_stone || 0) < Number(recipe.stones || 0)) return false;
  if ((recipe.inputs || []).some((input) => countItem(state, input.itemId) < Number(input.qty || 0))) return false;
  if (recipe.weekLimit != null && Number(state.crafting?.weekUsed?.[recipe.id] || 0) >= Number(recipe.weekLimit)) return false;
  return true;
}

async function autoCraft(account, state, config) {
  if (!config.autoCraft || !state.crafting) return state;
  const free = Math.max(0, Number(state.crafting.slots || 0) - (state.crafting.jobs || []).length);
  if (!free) return state;
  const candidates = Object.values(META.recipes || {}).filter((recipe) => {
    const item = META.items?.[recipe.output?.itemId];
    return item && ['cultivation_buff', 'cultivation_exp'].includes(item.use?.type);
  }).filter((recipe) => !config.craftRecipeId || recipe.id === config.craftRecipeId)
    .filter((recipe) => recipeCanCraft(state, recipe))
    .sort((a, b) => {
      const ua = META.items[a.output.itemId].use;
      const ub = META.items[b.output.itemId].use;
      return Number(ub.ratePct || ub.exp || 0) - Number(ua.ratePct || ua.exp || 0);
    });
  const recipe = candidates[0];
  if (!recipe) return state;
  const existing = countItem(state, recipe.output.itemId) + (state.crafting.jobs || [])
    .filter((job) => job.recipeId === recipe.id).length * Number(recipe.output.qty || 1);
  const keep = Math.max(0, Number(config.craftKeepQty || 0));
  const maxByInputs = (recipe.inputs || []).length
    ? Math.min(...recipe.inputs.map((input) => Math.floor(countItem(state, input.itemId) / Math.max(1, Number(input.qty || 1)))))
    : free;
  const maxByStones = Number(recipe.stones || 0) > 0
    ? Math.floor(Number(state.wallet?.spirit_stone || 0) / Number(recipe.stones))
    : free;
  const maxByWeek = recipe.weekLimit == null
    ? free
    : Math.max(0, Number(recipe.weekLimit) - Number(state.crafting?.weekUsed?.[recipe.id] || 0));
  const count = Math.max(0, Math.min(free, 8, keep ? keep - existing : free, maxByInputs, maxByStones, maxByWeek));
  if (!count) return state;
  try {
    const result = await sendGameCommand(account, state, 'craft.start', { recipeId: recipe.id, count });
    await appendLog(account, 'success', 'Bắt đầu luyện đan', `${recipe.name} ×${count}`);
    return result.state || state;
  } catch (error) {
    await appendLog(account, 'warn', 'Không bắt đầu được mẻ luyện', error.message);
    return state;
  }
}

async function autoUse(account, state, config) {
  if (!config.autoUse) return state;
  const available = Object.values(META.items || {}).filter((item) =>
    Number(state.materials?.[item.id] || 0) > 0
    && ((config.autoUseBuffs && item.use?.type === 'cultivation_buff')
      || (config.autoUseExp && item.use?.type === 'cultivation_exp')),
  ).sort((a, b) => {
    const key = (item) => item.use.type === 'cultivation_buff' ? Number(item.use.ratePct || 0) : Number(item.use.exp || 0);
    return key(b) - key(a);
  });
  const item = available[0];
  if (!item) return state;
  if (item.use.type === 'cultivation_buff') {
    const buff = (state.buffs || []).find((entry) => entry.id === `buff:${item.id}`);
    const left = Math.max(0, Number(buff?.expiresAt || 0) - Number(state.serverNow || Date.now()));
    if (left > Number(config.useThresholdMin ?? 15) * 60000) return state;
    const totalLeft = Math.max(0, Number(item.use.maxTotalMs || 14400000) - left);
    if (totalLeft < Number(item.use.durationMs || 0)) return state;
    if (config.autoUseOnlyBest !== false && left > 0) return state;
  }
  try {
    const result = await sendGameCommand(account, state, 'item.use', { itemId: item.id, qty: 1 });
    await appendLog(account, 'success', 'Đã tự dùng đan', item.name);
    return result.state || state;
  } catch (error) {
    await appendLog(account, 'warn', 'Không dùng được đan', error.message);
    return state;
  }
}

async function autoBoss(account, state, config) {
  if (!config.autoBoss) return state;
  const now = Date.now();
  const cooldown = Math.max(0, Number(config.bossIntervalMin ?? 10)) * 60000;
  const history = account.automation_data?.bossLastFightAt || {};
  const entries = (state.regions || []).filter((region) => region.unlocked && region.bossCleared)
    .map((region) => ({ region, boss: META.bosses?.[META.regions?.[region.id]?.bossId] }))
    .filter((entry) => entry.boss && Number(state.character?.level || 0) >= Number(entry.boss.reqLevel || 0))
    .filter((entry) => !config.bossRegionId || entry.region.id === config.bossRegionId)
    .filter((entry) => !entry.region.bossCooldownUntil || Number(entry.region.bossCooldownUntil) <= now)
    .filter((entry) => !cooldown || now - Number(history[entry.boss.id] || 0) >= cooldown)
    .sort((a, b) => Number(a.boss.reqLevel || 0) - Number(b.boss.reqLevel || 0));
  if (!entries.length) return state;
  const cursor = account.automation_data?.bossCursor;
  const index = entries.findIndex((entry) => entry.boss.id === cursor);
  const target = entries[(index + 1) % entries.length];
  try {
    const result = await sendGameCommand(account, state, 'boss.fight', { bossId: target.boss.id });
    history[target.boss.id] = now;
    await supabaseRest('game_accounts', {
      method: 'PATCH', query: `id=eq.${encodeURIComponent(account.id)}`,
      prefer: 'return=minimal',
      body: { automation_data: { ...(account.automation_data || {}), bossLastFightAt: history, bossCursor: target.boss.id } },
    });
    await appendLog(account, 'success', 'Đánh boss khu vực', target.boss.name);
    return result.state || state;
  } catch (error) {
    await appendLog(account, 'warn', 'Không đánh được boss khu vực', `${target.boss.name}: ${error.message}`);
    return state;
  }
}

async function farm(account, state, config) {
  if (!config.autoFarm || !state.cave?.unlocked) return state;
  let fields = Array.isArray(state.cave.fields) ? state.cave.fields : [];
  if (config.farmHarvest !== false) {
    for (const field of fields.filter((plot) => Number(plot.finishAt) <= Date.now()).slice(0, 4)) {
      try {
        state = await commandUpdate(account, state, 'field.harvest', { plot: field.plot }, 'Thu hoạch linh điền');
      } catch (error) { await appendLog(account, 'warn', `Thu hoạch ô ${field.plot} thất bại`, error.message); }
    }
  }
  if (config.farmPlant === false) return state;
  const openedPlots = Array.from({ length: Number(state.cave.plots || 0) }, (_, index) => index + 1)
    .map((plot) => ({ plot, field: 'field', habitatId: null }));
  if (config.farmIncludeHabitats !== false) {
    for (const habitat of Object.values(META.habitats || {}).sort((a, b) => a.order - b.order)) {
      const data = state.x2?.habitats?.[habitat.id];
      const openCount = Math.max(0, Math.min(habitat.plotCount || 4, Number(data?.plots || 0)));
      for (let index = 0; index < openCount; index += 1) {
        openedPlots.push({ plot: habitat.plotStart + index, field: 'habitat', habitatId: habitat.id });
      }
    }
  }
  const current = () => Array.isArray(state.cave.fields) ? state.cave.fields : [];
  for (const target of openedPlots) {
    if (current().some((field) => Number(field.plot) === target.plot)) continue;
    const seeds = Object.values(META.seeds || {}).filter((seed) => {
      const correctLocation = target.habitatId
        ? seed.habitat === target.habitatId || seed.alsoHabitat === target.habitatId
        : !seed.habitat && Number(state.cave.plots) >= Number(seed.reqField || 1);
      if (!correctLocation || Number(state.character?.level || 0) < Number(seed.reqLevel || 0)) return false;
      return Number(state.wallet?.spirit_stone || 0) - Number(config.farmReserveStones || 0) >= Number(seed.stones || 0);
    }).sort((a, b) => (config.farmSeedMode === 'fast'
      ? a.durationMs - b.durationMs
      : Number(b.yield?.qty || 0) / Math.max(1, b.durationMs) - Number(a.yield?.qty || 0) / Math.max(1, a.durationMs))
      || (a.id === config.farmSeedId ? -1 : b.id === config.farmSeedId ? 1 : 0));
    const seed = seeds[0];
    if (!seed) continue;
    try {
      state = await commandUpdate(account, state, 'field.plant', { plot: target.plot, seedId: seed.id }, `Gieo ${seed.name} · ô ${target.plot}`);
      break;
    } catch (error) {
      await appendLog(account, 'warn', `Gieo ô ${target.plot} thất bại`, error.message);
    }
    fields = current();
  }
  return state;
}

export async function runAccountTick(account, { manual = false } = {}) {
  if (!account.enabled && !manual) return { skipped: true, state: account.state_snapshot };
  const config = account.config || {};
  let { state } = await loadGameState(account);
  try {
    const settled = await sendGameCommand(account, state, 'settle', {});
    state = settled.state || state;
    if (settled.settle?.expGained) await appendLog(account, 'info', 'Kết toán tu vi', `+${settled.settle.expGained} tu vi`);
  } catch (error) {
    await appendLog(account, 'warn', 'Kết toán tu vi thất bại', error.message);
  }
  const salvageTier = config.autoSalvage ? Number(config.autoSalvageTier || 1) : 0;
  if (Boolean(state.character?.autoMinor) !== Boolean(config.autoMinor)
    || Number(state.settings?.autoSalvageTier || 0) !== salvageTier
    || (state.settings?.autoSalvageMode || 'salvage') !== (config.autoSalvageMode || 'salvage')) {
    try {
      const result = await sendGameCommand(account, state, 'settings.set', {
        autoMinor: Boolean(config.autoMinor),
        autoSalvageTier: salvageTier,
        autoSalvageMode: config.autoSalvageMode === 'sell' ? 'sell' : 'salvage',
      });
      state = result.state || state;
      await appendLog(account, 'info', 'Đồng bộ thiết lập game');
    } catch (error) { await appendLog(account, 'warn', 'Cập nhật thiết lập thất bại', error.message); }
  }
  state = await claimReady(account, state, config);
  state = await ensureActivity(account, state, config);
  state = await autoUse(account, state, config);
  state = await autoCraft(account, state, config);
  state = await autoBoss(account, state, config);
  state = await farm(account, state, config);
  await persistAccountState(account.id, state, { last_tick_at: new Date().toISOString(), last_error: null });
  return { state, completedAt: new Date().toISOString() };
}

export { META };
