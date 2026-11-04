import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3010);
const GAME_ORIGIN = process.env.GAME_ORIGIN || 'https://vandaonghichmenh.hongvan.net:60010';
const SESSION_FILE = path.join(__dirname, '.acc.session.json');
const CONFIG_FILE = path.join(__dirname, '.config.json');
const META_FILE = path.join(__dirname, 'data', 'meta.json');

const DEFAULT_CONFIG = {
  enabled: false,
  intervalMs: 15000,
  autoMinor: true,
  autoSalvage: false,
  autoSalvageTier: 0,
  autoSalvageMode: 'salvage',
  autoActivity: false,
  activityType: 'seclusion',
  huntSpotId: '',
  autoQuests: true,
  autoDaily: true,
  autoWeekly: false,
  autoAchievements: false,
  autoMail: true,
  autoX2Daily: false,
  autoFallbackHunt: true,
  autoCraft: false,
  craftRecipeId: '',
  craftKeepQty: 10,
  autoUse: false,
  autoUseBuffs: true,
  autoUseExp: false,
  autoUseOnlyBest: true,
  useThresholdMin: 15,
  autoBoss: false,
  bossIntervalMin: 10,
  bossRegionId: '',
  autoFarm: false,
  farmHarvest: true,
  farmPlant: true,
  farmIncludeHabitats: true,
  farmSeedMode: 'best',
  farmSeedId: '',
  farmReserveStones: 0,
};

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

let meta = null;
let session = null;
let state = null;
let config = { ...DEFAULT_CONFIG };
let logs = [];
let sseClients = new Set();
let loopTimer = null;
let tickBusy = false;
let lastCommandAt = 0;
let lastMailClaimAt = 0;
let lastCraftWarnAt = 0;
let lastUseWarnAt = 0;
let lastBossWarnAt = 0;
let lastFarmWarnAt = 0;
const bossLastFightAt = new Map();
let bossCursor = '';
let hasSavedConfig = false;
let mailCache = { at: 0, count: 0 };
let commandChain = Promise.resolve();

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function nowIso() {
  return new Date().toISOString();
}

function addLog(level, message, detail = null) {
  const entry = {
    id: crypto.randomUUID(),
    at: nowIso(),
    level,
    message,
    detail: detail ? String(detail).slice(0, 500) : null,
  };
  logs.push(entry);
  if (logs.length > 300) logs = logs.slice(-300);
  broadcast('log', entry);
  return entry;
}

function broadcast(event, data) {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of sseClients) {
    try { res.write(payload); } catch { sseClients.delete(res); }
  }
}

async function readJson(file, fallback = null) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch {
    return fallback;
  }
}

async function writeJson(file, value) {
  await fs.writeFile(file, JSON.stringify(value, null, 2), 'utf8');
}

const ACTIVITY_TYPES = new Set(['seclusion', 'farm', 'gather_herb', 'mine_ore', 'body_training']);

async function seedConfigFromGame({ force = false, persist = false } = {}) {
  if (!state || (hasSavedConfig && !force)) return false;
  const firstSeed = !hasSavedConfig;
  const settings = state.settings || {};
  const tier = Math.max(0, Math.min(5, Number(settings.autoSalvageTier) || 0));
  const before = JSON.stringify({
    autoMinor: config.autoMinor,
    autoSalvage: config.autoSalvage,
    autoSalvageTier: config.autoSalvageTier,
    autoSalvageMode: config.autoSalvageMode,
    activityType: config.activityType,
    huntSpotId: config.huntSpotId,
  });

  config.autoMinor = !!state.character?.autoMinor;
  config.autoSalvageTier = tier;
  config.autoSalvage = tier > 0;
  config.autoSalvageMode = settings.autoSalvageMode === 'sell' ? 'sell' : 'salvage';
  if (ACTIVITY_TYPES.has(state.activity?.type)) config.activityType = state.activity.type;
  if (state.activity?.type === 'farm' && state.activity?.targetId) config.huntSpotId = state.activity.targetId;

  hasSavedConfig = true;
  const after = JSON.stringify({
    autoMinor: config.autoMinor,
    autoSalvage: config.autoSalvage,
    autoSalvageTier: config.autoSalvageTier,
    autoSalvageMode: config.autoSalvageMode,
    activityType: config.activityType,
    huntSpotId: config.huntSpotId,
  });
  if (persist || firstSeed || before !== after) await writeJson(CONFIG_FILE, config);
  return before !== after;
}

async function loadLocal() {
  meta = await readJson(META_FILE, {});
  const savedConfig = await readJson(CONFIG_FILE, null);
  hasSavedConfig = !!savedConfig;
  if (savedConfig) config = { ...DEFAULT_CONFIG, ...savedConfig };
  const savedSession = await readJson(SESSION_FILE, null);
  if (savedSession?.cookie) {
    session = savedSession;
    try {
      const me = await gameFetch('/api/auth/me');
      if (!me?.user) {
        session = null;
        await fs.rm(SESSION_FILE, { force: true });
      } else {
        session.user = me.user;
        await refreshState(false);
        addLog('info', 'Khôi phục phiên đăng nhập', session.user?.username || '');
      }
    } catch (err) {
      addLog('warn', 'Không khôi phục được phiên', err.message);
      session = null;
      await fs.rm(SESSION_FILE, { force: true });
    }
  }
}

async function saveSession() {
  if (session) await writeJson(SESSION_FILE, session);
}

async function clearSession() {
  session = null;
  state = null;
  await fs.rm(SESSION_FILE, { force: true });
}

function gameHeaders(extra = {}) {
  const headers = {
    origin: GAME_ORIGIN,
    referer: `${GAME_ORIGIN}/`,
    'user-agent': 'VanDaoMiniClient/1.0 (+local companion)',
    ...extra,
  };
  if (session?.cookie) headers.cookie = session.cookie;
  return headers;
}

async function gameFetch(pathname, options = {}) {
  const res = await fetch(GAME_ORIGIN + pathname, {
    ...options,
    headers: gameHeaders(options.headers || {}),
    signal: AbortSignal.timeout(25000),
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  if (!res.ok || json?.ok === false) {
    const err = new Error(json?.message || json?.errorCode || `HTTP ${res.status}`);
    err.code = json?.errorCode || `HTTP_${res.status}`;
    err.status = res.status;
    err.payload = json;
    throw err;
  }
  return json ?? { ok: true, raw: text };
}

async function login(username, password, remember = true) {
  const res = await fetch(GAME_ORIGIN + '/api/auth/login', {
    method: 'POST',
    headers: gameHeaders({ 'content-type': 'application/json' }),
    body: JSON.stringify({ username, password, remember: true }),
    signal: AbortSignal.timeout(25000),
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  if (!res.ok || json?.ok === false) {
    const err = new Error(json?.message || json?.errorCode || `HTTP ${res.status}`);
    err.code = json?.errorCode || `HTTP_${res.status}`;
    err.status = res.status;
    err.payload = json;
    throw err;
  }
  const setCookies = typeof res.headers.getSetCookie === 'function'
    ? res.headers.getSetCookie()
    : [res.headers.get('set-cookie')].filter(Boolean);
  const sid = setCookies
    .map((c) => String(c).split(';')[0])
    .find((c) => c.startsWith('vd_sid='));
  if (!sid) throw new Error('Máy chủ game không trả về phiên đăng nhập (vd_sid).');
  session = { cookie: sid, user: json.user || null, savedAt: nowIso() };
  if (remember) await saveSession();
  await refreshState(false);
  addLog('success', 'Đăng nhập thành công', session.user?.username || username);
  if (config.enabled) startLoop();
  return { user: session.user, hasCharacter: !!state };
}

async function refreshState(log = false) {
  if (!session) throw Object.assign(new Error('Chưa đăng nhập.'), { code: 'UNAUTHENTICATED' });
  const json = await gameFetch('/api/state');
  if (!json?.state) throw new Error('Phản hồi /api/state không hợp lệ.');
  state = json.state;
  await seedConfigFromGame();
  if (log) addLog('info', 'Đã làm mới trạng thái');
  broadcast('state', publicSnapshot());
  return state;
}

function publicSnapshot() {
  return {
    authenticated: !!session,
    user: session?.user || null,
    state,
    config,
    boss: bossSnapshot(),
    logs: logs.slice(-80),
    serverTime: Date.now(),
  };
}

function enqueue(fn) {
  const run = commandChain.then(fn, fn);
  commandChain = run.catch(() => {});
  return run;
}

async function sendCommand(cmd, payload = {}, { retry = true } = {}) {
  return enqueue(async () => {
    if (!session) throw Object.assign(new Error('Chưa đăng nhập.'), { code: 'UNAUTHENTICATED' });
    if (!state) await refreshState(false);

    const attempts = retry ? 2 : 1;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const wait = 350 - (Date.now() - lastCommandAt);
      if (wait > 0) await sleep(wait);
      lastCommandAt = Date.now();

      const expectedVersion = state?.stateVersion ?? 1;
      const body = JSON.stringify({ payload, expectedVersion });
      const headers = {
        'content-type': 'application/json',
        'idempotency-key': crypto.randomUUID(),
      };

      let res;
      try {
        res = await fetch(`${GAME_ORIGIN}/api/cmd/${encodeURIComponent(cmd)}`, {
          method: 'POST',
          headers: gameHeaders(headers),
          body,
          signal: AbortSignal.timeout(25000),
        });
      } catch (err) {
        throw Object.assign(new Error(`Không gọi được lệnh ${cmd}: ${err.message}`), { code: 'NETWORK' });
      }

      const text = await res.text();
      let json = null;
      try { json = JSON.parse(text); } catch {}
      if (!res.ok || json?.ok === false) {
        const code = json?.errorCode || `HTTP_${res.status}`;
        if (attempt < attempts - 1 && /VERSION|CONFLICT|STALE/i.test(code)) {
          await refreshState(false);
          continue;
        }
        const err = new Error(json?.message || code);
        err.code = code;
        err.status = res.status;
        err.payload = json;
        throw err;
      }

      if (json.state) {
        state = json.state;
        broadcast('state', publicSnapshot());
      }
      if (json.settle) summarizeSettle(cmd, json.settle);
      return json;
    }
    throw new Error(`Lệnh ${cmd} không hoàn tất.`);
  });
}

function summarizeSettle(cmd, settle) {
  const gained = Number(settle.expGained || 0);
  const bits = [];
  if (gained > 0) bits.push(`+${gained.toLocaleString('vi-VN')} tu vi`);
  if (settle.cycles) bits.push(`${settle.cycles} chu kỳ`);
  if (settle.layerUps?.length) bits.push(`lên ${settle.layerUps.length} tầng`);
  if (settle.equipment?.length) bits.push(`${settle.equipment.length} trang bị`);
  if (settle.craftsCompleted?.length) bits.push(`${settle.craftsCompleted.length} mẻ luyện xong`);
  if (settle.autoSalvaged) bits.push(`tự xử lý ${settle.autoSalvaged} món`);
  if (settle.stopReason) bits.push(`dừng: ${settle.stopReason}`);
  if (bits.length) addLog('info', `Kết toán ${cmd === 'settle' ? '' : `sau ${cmd} `}`, bits.join(' · '));
}

function formatNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString('vi-VN') : String(n);
}

function isRegionUnlocked(regionId) {
  return !!state?.regions?.find((r) => r.id === regionId)?.unlocked;
}

function availableSpots() {
  if (!state || !meta?.spots) return [];
  return Object.values(meta.spots)
    .filter((sp) => sp.reqLevel <= (state.character?.level || 1) && isRegionUnlocked(sp.regionId))
    .sort((a, b) => b.reqLevel - a.reqLevel || b.expPerCycle - a.expPerCycle);
}

function bestSpot(excludeId = '') {
  return availableSpots().find((sp) => sp.id !== excludeId) || null;
}

function fallbackSpot(currentId = '') {
  const spots = availableSpots();
  const current = meta?.spots?.[currentId] || null;
  const lower = spots
    .filter((sp) => sp.id !== currentId && (!current
      || sp.reqLevel < current.reqLevel
      || (sp.reqLevel === current.reqLevel && sp.expPerCycle < current.expPerCycle)))
    .sort((a, b) => b.reqLevel - a.reqLevel || b.expPerCycle - a.expPerCycle);
  if (lower.length) return lower[0];
  return spots.filter((sp) => sp.id !== currentId).sort((a, b) => a.reqLevel - b.reqLevel)[0] || null;
}

async function unclaimedMailCount() {
  if (Date.now() - mailCache.at < 60000) return mailCache.count;
  const json = await gameFetch('/api/mail');
  const count = (json.mails || []).filter((mail) => {
    if (mail.claimed) return false;
    const rewards = mail.rewards || {};
    return Object.keys(rewards).length > 0;
  }).length;
  mailCache = { at: Date.now(), count };
  return count;
}

async function applySettings() {
  if (!state) return;
  const desiredTier = config.autoSalvage ? Number(config.autoSalvageTier) : 0;
  const currentTier = Number(state.settings?.autoSalvageTier ?? 0);
  const currentMode = state.settings?.autoSalvageMode || 'salvage';
  const currentMinor = !!state.character?.autoMinor;
  if (currentMinor !== !!config.autoMinor || currentTier !== desiredTier || currentMode !== config.autoSalvageMode) {
    await sendCommand('settings.set', {
      autoMinor: !!config.autoMinor,
      autoSalvageTier: desiredTier,
      autoSalvageMode: config.autoSalvageMode,
    });
    addLog('success', 'Đã cập nhật thiết lập tự động', `autoMinor=${config.autoMinor}, autoSalvage=${desiredTier}`);
  }
}

async function ensureActivity() {
  if (!config.autoActivity || !state) return;
  const desiredType = config.activityType;
  const currentType = state.activity?.type;
  const desiredSpot = desiredType === 'farm'
    ? (config.huntSpotId || bestSpot()?.id || '')
    : null;
  const currentSpot = currentType === 'farm' ? state.activity?.targetId : null;

  if (desiredType === 'body_training' && !state.x2?.ancient) {
    addLog('warn', 'Luyện thể chưa mở', 'Cần mở Cổ Thần trước.');
    return;
  }

  if (currentType !== desiredType || (desiredType === 'farm' && desiredSpot && currentSpot !== desiredSpot)) {
    if (desiredType === 'farm' && !desiredSpot) {
      addLog('warn', 'Chưa có điểm săn phù hợp', 'Hãy chọn điểm săn trong tab Tự động.');
      return;
    }
    const payload = desiredType === 'farm'
      ? { type: 'farm', targetId: desiredSpot }
      : { type: desiredType };
    try {
      await sendCommand('activity.set', payload);
      addLog('success', 'Đã chuyển hoạt động', desiredType === 'farm'
        ? `Săn tại ${meta?.spots?.[desiredSpot]?.name || desiredSpot}`
        : (meta?.activities?.[desiredType]?.name || desiredType));
    } catch (err) {
      addLog('error', 'Không chuyển được hoạt động', err.message);
    }
    return;
  }

  if (desiredType === 'farm' && config.autoFallbackHunt && state.activity?.win === false) {
    const fallback = fallbackSpot(currentSpot);
    if (fallback) {
      try {
        await sendCommand('activity.set', { type: 'farm', targetId: fallback.id });
        addLog('warn', 'Điểm săn hiện tại không thắng được', `Chuyển sang ${fallback.name}`);
      } catch (err) {
        addLog('error', 'Không chuyển được điểm săn dự phòng', err.message);
      }
    } else {
      try {
        await sendCommand('activity.set', { type: 'seclusion' });
        addLog('warn', 'Không còn điểm săn phù hợp', 'Chuyển về Bế quan.');
      } catch (err) {
        addLog('error', 'Không chuyển về Bế quan được', err.message);
      }
    }
  }
}

async function claimRewards() {
  if (!state) return;

  if (config.autoQuests) {
    const claimable = (state.quests || []).filter((q) => q.status === 'claimable').slice(0, 6);
    for (const q of claimable) {
      try {
        await sendCommand('quest.claim', { questId: q.id });
        addLog('success', 'Nhận thưởng nhiệm vụ', meta?.quests?.[q.id]?.name || q.id);
      } catch (err) {
        addLog('error', 'Không nhận được nhiệm vụ', `${q.id}: ${err.message}`);
      }
    }
  }

  if (config.autoDaily) {
    const daily = state.periodic?.daily || [];
    const claims = Number(state.periodic?.dailyClaims || 0);
    const ready = daily.filter((d) => !d.claimed && d.current >= d.target).slice(0, Math.max(0, 4 - claims));
    for (const task of ready) {
      try {
        await sendCommand('daily.claim', { taskId: task.id });
        addLog('success', 'Nhận việc ngày', task.id);
      } catch (err) {
        addLog('error', 'Không nhận được việc ngày', `${task.id}: ${err.message}`);
      }
    }
  }

  if (config.autoWeekly) {
    const ready = (state.periodic?.weekly || []).filter((d) => !d.claimed && d.current >= d.target).slice(0, 3);
    for (const task of ready) {
      try {
        await sendCommand('weekly.claim', { taskId: task.id });
        addLog('success', 'Nhận việc tuần', task.id);
      } catch (err) {
        addLog('error', 'Không nhận được việc tuần', `${task.id}: ${err.message}`);
      }
    }
  }

  if (config.autoAchievements) {
    const ready = (state.periodic?.achievements || []).filter((d) => !d.claimed && d.current >= d.target).slice(0, 6);
    for (const task of ready) {
      try {
        await sendCommand('achievement.claim', { achievementId: task.id });
        addLog('success', 'Nhận thành tựu', task.id);
      } catch (err) {
        addLog('error', 'Không nhận được thành tựu', `${task.id}: ${err.message}`);
      }
    }
  }

  if (config.autoX2Daily && state.x2 && !state.x2.dailyClaimed) {
    try {
      await sendCommand('x2.daily.claim', {});
      addLog('success', 'Nhận phần mở rộng ngày');
    } catch (err) {
      addLog('error', 'Không nhận được phần mở rộng ngày', err.message);
    }
  }

  if (config.autoMail && Date.now() - lastMailClaimAt > 60000) {
    try {
      const count = await unclaimedMailCount();
      if (count > 0) {
        lastMailClaimAt = Date.now();
        await sendCommand('mail.claimAll', {});
        mailCache = { at: 0, count: 0 };
        addLog('success', `Nhận ${count} thư có quà`, 'Đã nhận tất cả thư trong hộp thư.');
      }
    } catch (err) {
      addLog('error', 'Không kiểm tra được hộp thư', err.message);
    }
  }
}

/* ------------------------------------------------------------------ */
/* Đan dược: tự chế tạo và tự sử dụng                                  */
/* ------------------------------------------------------------------ */

const PILL_USE_TYPES = new Set(['cultivation_buff', 'cultivation_exp']);

function recipeInfo(id) {
  return meta?.recipes?.[id] || null;
}

function isPillRecipe(recipe) {
  if (!recipe || recipe.output?.kind !== 'item') return false;
  const item = meta?.items?.[recipe.output.itemId];
  if (!item) return false;
  if (PILL_USE_TYPES.has(item.use?.type)) return true;
  if (item.kind === 'breakthrough') return true;
  return item.kind === 'consumable' && /đan|pill/i.test(`${item.name} ${item.id}`);
}

function isUsablePillRecipe(recipe) {
  const item = meta?.items?.[recipe?.output?.itemId];
  return PILL_USE_TYPES.has(item?.use?.type);
}

function pillRecipeList() {
  return Object.values(meta?.recipes || {}).filter(isPillRecipe);
}

function craftWeekRemaining(recipe) {
  if (!recipe?.weekLimit) return Infinity;
  const used = Number(state?.crafting?.weekUsed?.[recipe.id] || 0);
  return Math.max(0, Number(recipe.weekLimit) - used);
}

function recipeCraftable(recipe) {
  if (!recipe || !isPillRecipe(recipe) || !state) return false;
  if (Number(state.character?.level || 0) < Number(recipe.reqLevel || 0)) return false;
  if (craftWeekRemaining(recipe) < 1) return false;
  let stones = 0n;
  try {
    stones = BigInt(state.wallet?.spirit_stone ?? '0');
  } catch {
    stones = BigInt(Math.floor(Number(state.wallet?.spirit_stone) || 0));
  }
  if (stones < BigInt(Number(recipe.stones || 0))) return false;
  return (recipe.inputs || []).every((input) => (
    Number(state.materials?.[input.itemId] || 0) >= Number(input.qty || 0)
  ));
}

function recipePriority(recipe) {
  const item = meta?.items?.[recipe?.output?.itemId];
  const use = item?.use;
  if (use?.type === 'cultivation_buff') {
    return 2e15 + Number(use.ratePct || 0) * 1e9 + Number(recipe.reqLevel || 0);
  }
  if (use?.type === 'cultivation_exp') {
    return 1e15 + Number(use.exp || 0);
  }
  return Number(recipe?.reqLevel || 0);
}

function bestCraftRecipe() {
  return pillRecipeList()
    .filter((recipe) => isUsablePillRecipe(recipe) && recipeCraftable(recipe))
    .sort((a, b) => recipePriority(b) - recipePriority(a))[0] || null;
}

async function autoCraftTick() {
  if (!config.autoCraft || !state?.crafting) return;
  const crafting = state.crafting;
  const freeSlots = Math.max(0, Number(crafting.slots || 0) - (crafting.jobs?.length || 0));
  if (freeSlots < 1) return;

  const selected = config.craftRecipeId ? recipeInfo(config.craftRecipeId) : null;
  const recipe = selected && isPillRecipe(selected) ? selected : bestCraftRecipe();
  if (!recipe) return;

  if (!recipeCraftable(recipe)) {
    if (Date.now() - lastCraftWarnAt > 120000) {
      lastCraftWarnAt = Date.now();
      const missing = (recipe.inputs || [])
        .filter((input) => Number(state.materials?.[input.itemId] || 0) < Number(input.qty || 0))
        .map((input) => `${meta?.items?.[input.itemId]?.name || input.itemId} ${formatNum(state.materials?.[input.itemId] || 0)}/${formatNum(input.qty)}`);
      addLog('warn', 'Chưa thể tự luyện đan', missing.length
        ? `${recipe.name}: thiếu ${missing.join(', ')}`
        : `${recipe.name}: chưa đủ cấp, linh thạch hoặc lượt tuần.`);
    }
    return;
  }

  const outputId = recipe.output.itemId;
  const have = Number(state.materials?.[outputId] || 0);
  const inProgress = (crafting.jobs || [])
    .filter((job) => job.recipeId === recipe.id)
    .reduce((sum, job) => sum + Number(recipe.output.qty || 1), 0);
  const projected = have + inProgress;
  const keep = Math.max(0, Number(config.craftKeepQty) || 0);
  if (keep > 0 && projected >= keep) return;
  const need = keep > 0 ? keep - projected : freeSlots;

  const maxByMaterials = (recipe.inputs || []).length
    ? Math.min(...recipe.inputs.map((input) => Math.floor(
      Number(state.materials?.[input.itemId] || 0) / Math.max(1, Number(input.qty || 1)),
    )))
    : Infinity;
  const stones = Number(recipe.stones || 0);
  const maxByStones = stones > 0 ? Math.floor(Number(state.wallet?.spirit_stone || 0) / stones) : Infinity;
  const count = Math.max(0, Math.min(freeSlots, maxByMaterials, maxByStones, craftWeekRemaining(recipe), need, 8));
  if (count < 1) return;

  try {
    await sendCommand('craft.start', { recipeId: recipe.id, count });
    addLog('success', 'Bắt đầu luyện đan', `${recipe.name} ×${count} · ${meta?.items?.[outputId]?.name || outputId}`);
  } catch (err) {
    if (Date.now() - lastCraftWarnAt > 120000) {
      lastCraftWarnAt = Date.now();
      addLog('warn', 'Không bắt đầu được mẻ luyện', `${recipe.name}: ${err.message}`);
    }
  }
}

function buffRemainingMs(itemId) {
  const buff = (state?.buffs || []).find((entry) => entry.id === `buff:${itemId}`);
  if (!buff) return 0;
  const now = Number(state?.serverNow) || Date.now();
  return Math.max(0, Number(buff.expiresAt || 0) - now);
}

function availablePills(type) {
  return Object.values(meta?.items || {})
    .filter((item) => item.use?.type === type && Number(state?.materials?.[item.id] || 0) > 0)
    .sort((a, b) => {
      if (type === 'cultivation_buff') return Number(b.use.ratePct || 0) - Number(a.use.ratePct || 0);
      return Number(b.use.exp || 0) - Number(a.use.exp || 0);
    });
}

async function usePill(item) {
  await sendCommand('item.use', { itemId: item.id, qty: 1 });
  const use = item.use || {};
  const effect = use.type === 'cultivation_buff'
    ? `+${formatNum(use.ratePct)}% tốc độ tu vi trong ${Math.round(Number(use.durationMs || 0) / 60000)} phút`
    : use.type === 'cultivation_exp'
      ? `+${formatNum(use.exp)} tu vi`
      : 'đã dùng';
  addLog('success', 'Đã dùng đan dược', `${item.name} · ${effect}`);
}

async function autoUseTick() {
  if (!config.autoUse || !state) return false;
  const thresholdMs = Math.max(0, Number(config.useThresholdMin) || 0) * 60000;

  if (config.autoUseBuffs) {
    const pills = availablePills('cultivation_buff');
    const candidates = config.autoUseOnlyBest ? pills.slice(0, 1) : pills;
    for (const pill of candidates) {
      const remaining = buffRemainingMs(pill.id);
      const maxTotal = Number(pill.use?.maxTotalMs || 0);
      const duration = Number(pill.use?.durationMs || 0);
      if (maxTotal > 0 && duration > 0 && remaining + duration > maxTotal) continue;
      if (maxTotal > 0 && duration <= 0 && remaining >= maxTotal) continue;
      if (remaining > thresholdMs) continue;
      try {
        await usePill(pill);
        return true;
      } catch (err) {
        if (Date.now() - lastUseWarnAt > 120000) {
          lastUseWarnAt = Date.now();
          addLog('warn', 'Không dùng được đan dược', `${pill.name}: ${err.message}`);
        }
        return false;
      }
    }
  }

  if (config.autoUseExp) {
    const pills = availablePills('cultivation_exp');
    const candidates = config.autoUseOnlyBest ? pills.slice(0, 1) : pills;
    for (const pill of candidates) {
      try {
        await usePill(pill);
        return true;
      } catch (err) {
        if (Date.now() - lastUseWarnAt > 120000) {
          lastUseWarnAt = Date.now();
          addLog('warn', 'Không dùng được đan dược', `${pill.name}: ${err.message}`);
        }
        return false;
      }
    }
  }

  return false;
}

/* ------------------------------------------------------------------ */
/* Boss khu vực: tự đánh lại boss đã hạ                                */
/* ------------------------------------------------------------------ */

function bossInfo(id) {
  return meta?.bosses?.[id] || null;
}

function bossCooldownRemaining(region) {
  if (!region?.bossCooldownUntil) return 0;
  const now = Number(state?.serverNow) || Date.now();
  return Math.max(0, Number(region.bossCooldownUntil) - now);
}

function clearedBossEntries() {
  const entries = [];
  for (const region of state?.regions || []) {
    if (!region.unlocked || !region.bossCleared) continue;
    const regionMeta = meta?.regions?.[region.id];
    const boss = bossInfo(regionMeta?.bossId);
    if (!boss) continue;
    entries.push({ region, regionMeta, boss });
  }
  return entries.sort((a, b) => Number(a.boss.reqLevel || 0) - Number(b.boss.reqLevel || 0)
    || String(a.boss.id).localeCompare(String(b.boss.id)));
}

function bossLocalRemaining(entry) {
  const intervalMs = Math.max(0, Number(config.bossIntervalMin) || 0) * 60000;
  if (intervalMs <= 0) return 0;
  const last = bossLastFightAt.get(entry.boss.id) || 0;
  return Math.max(0, intervalMs - (Date.now() - last));
}

function bossEntryReady(entry) {
  if (!entry) return false;
  if (Number(state?.character?.level || 0) < Number(entry.boss.reqLevel || 0)) return false;
  if (bossCooldownRemaining(entry.region) > 0) return false;
  return bossLocalRemaining(entry) <= 0;
}

function nextBossEntry() {
  const ready = clearedBossEntries().filter(bossEntryReady);
  if (!ready.length) return null;
  if (config.bossRegionId) {
    return ready.find((entry) => entry.region.id === config.bossRegionId) || null;
  }
  const cursorIndex = ready.findIndex((entry) => entry.boss.id === bossCursor);
  return ready[(cursorIndex + 1) % ready.length];
}

function bossSnapshot() {
  const ready = clearedBossEntries().filter(bossEntryReady);
  return {
    cursor: bossCursor,
    nextId: nextBossEntry()?.boss.id || null,
    readyIds: ready.map((entry) => entry.boss.id),
  };
}

function bossRewardBits(rewards) {
  if (!rewards) return [];
  const bits = [];
  if (Number(rewards.stones) > 0) bits.push(`${formatNum(rewards.stones)} linh thạch`);
  if (rewards.items?.length) {
    bits.push(rewards.items.map((entry) => {
      const name = meta?.items?.[entry.itemId]?.name || entry.itemId;
      return `${name} ×${formatNum(entry.qty)}`;
    }).join(', '));
  }
  return bits;
}

async function autoBossTick() {
  if (!config.autoBoss || !state) return false;

  const target = nextBossEntry();
  if (!target) return false;

  try {
    const result = await sendCommand('boss.fight', { bossId: target.boss.id });
    bossLastFightAt.set(target.boss.id, Date.now());
    bossCursor = target.boss.id;
    const fight = result?.result || {};
    const won = fight.battle?.result?.winner === 'ally';
    const rewards = bossRewardBits(fight.rewards);
    addLog(
      won ? 'success' : 'warn',
      won ? 'Hạ boss khu vực' : 'Chưa hạ được boss khu vực',
      `${target.boss.name} · ${target.regionMeta?.name || target.region.id}${won && rewards.length ? ` · ${rewards.join(' · ')}` : ''}`,
    );
    return true;
  } catch (err) {
    if (Date.now() - lastBossWarnAt > 120000) {
      lastBossWarnAt = Date.now();
      addLog('warn', 'Không đánh được boss khu vực', `${target.boss.name}: ${err.message}`);
    }
    return false;
  }
}

async function autoTick({ manual = false } = {}) {
  if (tickBusy) return { skipped: true };
  if (!session) throw Object.assign(new Error('Chưa đăng nhập.'), { code: 'UNAUTHENTICATED' });
  tickBusy = true;
  try {
    if (!state) await refreshState(false);
    if (config.enabled || manual) {
      await sendCommand('settle', {});
      await applySettings();
      await ensureActivity();
      await claimRewards();
      await autoUseTick();
      await autoCraftTick();
      await autoBossTick();
    } else {
      await refreshState(false);
    }
    broadcast('state', publicSnapshot());
    return { ok: true, state, config };
  } catch (err) {
    addLog('error', 'Lỗi vòng tự động', err.message);
    if (err.code === 'UNAUTHENTICATED') {
      await clearSession();
      broadcast('session', { authenticated: false });
    }
    throw err;
  } finally {
    tickBusy = false;
  }
}

function startLoop() {
  stopLoop();
  if (!config.enabled || !session) return;
  const interval = Math.max(5000, Math.min(300000, Number(config.intervalMs) || 15000));
  loopTimer = setInterval(() => {
    autoTick().catch(() => {});
  }, interval);
  addLog('info', 'Bật vòng tự động', `Mỗi ${Math.round(interval / 1000)} giây`);
}

function stopLoop() {
  if (loopTimer) clearInterval(loopTimer);
  loopTimer = null;
}

function validateConfig(input) {
  const next = { ...config, ...input };
  next.enabled = !!next.enabled;
  next.intervalMs = Math.max(5000, Math.min(300000, Number(next.intervalMs) || 15000));
  next.autoMinor = !!next.autoMinor;
  next.autoSalvage = !!next.autoSalvage;
  next.autoSalvageTier = Math.max(-1, Math.min(5, Number(next.autoSalvageTier) || 0));
  next.autoSalvageMode = next.autoSalvageMode === 'sell' ? 'sell' : 'salvage';
  next.autoActivity = !!next.autoActivity;
  next.activityType = ['seclusion', 'farm', 'gather_herb', 'mine_ore', 'body_training'].includes(next.activityType)
    ? next.activityType : 'seclusion';
  next.huntSpotId = String(next.huntSpotId || '');
  next.autoQuests = !!next.autoQuests;
  next.autoDaily = !!next.autoDaily;
  next.autoWeekly = !!next.autoWeekly;
  next.autoAchievements = !!next.autoAchievements;
  next.autoMail = !!next.autoMail;
  next.autoX2Daily = !!next.autoX2Daily;
  next.autoFallbackHunt = !!next.autoFallbackHunt;
  next.autoCraft = !!next.autoCraft;
  next.craftRecipeId = String(next.craftRecipeId || '');
  next.craftKeepQty = Math.max(0, Math.min(9999, Number(next.craftKeepQty) || 0));
  next.autoUse = !!next.autoUse;
  next.autoUseBuffs = !!next.autoUseBuffs;
  next.autoUseExp = !!next.autoUseExp;
  next.autoUseOnlyBest = !!next.autoUseOnlyBest;
  next.useThresholdMin = Math.max(0, Math.min(240, Number(next.useThresholdMin) || 0));
  next.autoBoss = !!next.autoBoss;
  next.bossIntervalMin = Math.max(0, Math.min(240, Number(next.bossIntervalMin) || 0));
  next.bossRegionId = String(next.bossRegionId || '');
  delete next.craftIntervalMs;
  return next;
}

async function handleApi(req, res, url) {
  const send = (status, obj) => {
    res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
    res.end(JSON.stringify(obj));
  };

  if (url.pathname === '/api/health') {
    return send(200, { ok: true, session: !!session, state: !!state, uptime: process.uptime() });
  }

  if (url.pathname === '/api/meta') {
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-cache' });
    return res.end(JSON.stringify(meta));
  }

  if (url.pathname === '/api/session') {
    return send(200, publicSnapshot());
  }

  if (url.pathname === '/api/login' && req.method === 'POST') {
    const body = await readBody(req);
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    if (!/^[a-zA-Z0-9_]{3,24}$/.test(username)) {
      return send(400, { ok: false, errorCode: 'INVALID_USERNAME', message: 'Tên đăng nhập 3–24 chữ, số hoặc gạch dưới.' });
    }
    if (password.length < 8) {
      return send(400, { ok: false, errorCode: 'INVALID_PASSWORD', message: 'Mật khẩu cần ít nhất 8 ký tự.' });
    }
    try {
      const result = await login(username, password, body.remember !== false);
      return send(200, { ok: true, ...result, state, config, logs: logs.slice(-80) });
    } catch (err) {
      addLog('error', 'Đăng nhập thất bại', err.code || err.message);
      return send(err.status || 400, { ok: false, errorCode: err.code || 'LOGIN_FAILED', message: err.message, details: err.payload?.details });
    }
  }

  if (url.pathname === '/api/logout' && req.method === 'POST') {
    try { await gameFetch('/api/auth/logout', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' }); } catch {}
    stopLoop();
    await clearSession();
    addLog('info', 'Đã đăng xuất');
    return send(200, { ok: true });
  }

  if (url.pathname === '/api/state') {
    if (!session) return send(401, { ok: false, errorCode: 'UNAUTHENTICATED', message: 'Chưa đăng nhập.' });
    if (!state) await refreshState(false);
    return send(200, { ok: true, state, config });
  }

  if (url.pathname === '/api/config' && req.method === 'GET') {
    return send(200, { ok: true, config });
  }

  if (url.pathname === '/api/config/sync' && req.method === 'POST') {
    if (!session) return send(401, { ok: false, errorCode: 'UNAUTHENTICATED', message: 'Chưa đăng nhập.' });
    await refreshState(false);
    await seedConfigFromGame({ force: true, persist: true });
    addLog('info', 'Đã đồng bộ thiết lập từ game', 'Tự lên tầng, dọn trang bị và hoạt động hiện tại.');
    broadcast('config', config);
    return send(200, { ok: true, config });
  }

  if (url.pathname === '/api/config' && req.method === 'POST') {
    const body = await readBody(req);
    const wasEnabled = config.enabled;
    const previousInterval = config.intervalMs;
    config = validateConfig(body);
    await writeJson(CONFIG_FILE, config);
    hasSavedConfig = true;
    if (config.enabled) {
      if (!wasEnabled || previousInterval !== config.intervalMs || !loopTimer) startLoop();
    } else {
      stopLoop();
    }
    addLog('info', 'Đã lưu cấu hình tự động', `Mỗi ${Math.round(config.intervalMs / 1000)}s`);
    broadcast('config', config);
    return send(200, { ok: true, config });
  }

  if (url.pathname === '/api/command' && req.method === 'POST') {
    if (!session) return send(401, { ok: false, errorCode: 'UNAUTHENTICATED', message: 'Chưa đăng nhập.' });
    const body = await readBody(req);
    const cmd = String(body.cmd || '');
    if (!/^[a-zA-Z0-9_.]+$/.test(cmd)) return send(400, { ok: false, message: 'Lệnh không hợp lệ.' });
    try {
      const result = await sendCommand(cmd, body.payload || {});
      return send(200, { ok: true, result: result.result, settle: result.settle, state: result.state || state });
    } catch (err) {
      return send(err.status || 400, { ok: false, errorCode: err.code || 'COMMAND_FAILED', message: err.message, details: err.payload?.details });
    }
  }

  if (url.pathname === '/api/tick' && req.method === 'POST') {
    try {
      const result = await autoTick({ manual: true });
      return send(200, { ok: true, ...result });
    } catch (err) {
      return send(err.status || 400, { ok: false, errorCode: err.code || 'TICK_FAILED', message: err.message });
    }
  }

  if (url.pathname === '/api/events') {
    res.writeHead(200, {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
    });
    res.write(`event: hello\ndata: ${JSON.stringify(publicSnapshot())}\n\n`);
    sseClients.add(res);
    const keep = setInterval(() => {
      try { res.write(': keepalive\n\n'); } catch {}
    }, 20000);
    req.on('close', () => { clearInterval(keep); sseClients.delete(res); });
    return;
  }

  return send(404, { ok: false, message: 'Không tìm thấy API.' });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
      if (data.length > 1_000_000) {
        reject(new Error('Body quá lớn.'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!data) return resolve({});
      try { resolve(JSON.parse(data)); } catch { reject(new Error('JSON không hợp lệ.')); }
    });
    req.on('error', reject);
  });
}

async function serveStatic(req, res, url) {
  let pathname = decodeURIComponent(url.pathname);
  if (pathname === '/') pathname = '/index.html';
  const publicDir = path.join(__dirname, 'public');
  const filePath = path.normalize(path.join(publicDir, pathname));
  if (filePath !== publicDir && !filePath.startsWith(publicDir + path.sep)) {
    res.writeHead(403); return res.end('Forbidden');
  }
  try {
    const data = await fs.readFile(filePath);
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'content-type': MIME[ext] || 'application/octet-stream', 'cache-control': 'no-cache' });
    res.end(data);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  }
}

async function proxyAsset(req, res, url) {
  const assetPath = url.pathname.replace(/^\/game-assets\//, '');
  if (!assetPath || assetPath.includes('..')) { res.writeHead(400); return res.end('Bad request'); }
  try {
    const upstream = await fetch(`${GAME_ORIGIN}/assets/${assetPath}`, {
      headers: { referer: `${GAME_ORIGIN}/`, 'user-agent': 'VanDaoMiniClient/1.0' },
      signal: AbortSignal.timeout(20000),
    });
    if (!upstream.ok) { res.writeHead(upstream.status); return res.end('Asset not found'); }
    const type = upstream.headers.get('content-type') || MIME[path.extname(assetPath)] || 'application/octet-stream';
    const buf = Buffer.from(await upstream.arrayBuffer());
    res.writeHead(200, { 'content-type': type, 'cache-control': 'public, max-age=86400' });
    res.end(buf);
  } catch {
    res.writeHead(502); res.end('Asset proxy error');
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
  try {
    if (url.pathname.startsWith('/api/')) return await handleApi(req, res, url);
    if (url.pathname.startsWith('/game-assets/')) return await proxyAsset(req, res, url);
    return await serveStatic(req, res, url);
  } catch (err) {
    addLog('error', 'Lỗi máy chủ', err.message);
    if (!res.headersSent) res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ ok: false, message: err.message }));
  }
});

await loadLocal();
if (session) startLoop();
server.listen(PORT, '127.0.0.1', () => {
  console.log(`Vấn Đạo Mini Client: http://127.0.0.1:${PORT}`);
  console.log(`Game: ${GAME_ORIGIN}`);
  console.log(`Phiên: ${session ? 'đã đăng nhập' : 'chưa đăng nhập'}`);
});

process.on('SIGINT', () => {
  stopLoop();
  server.close(() => process.exit(0));
});
