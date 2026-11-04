/* Vấn Đạo · Mini Client
 * Giao diện cục bộ, gọi API chính thức của game qua server Node đi kèm.
 */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const VIEW_META = {
  overview: { kicker: 'Bảng điều khiển', title: 'Tổng quan' },
  items: { kicker: 'Túi đồ', title: 'Vật phẩm' },
  auto: { kicker: 'Trợ lý', title: 'Tự động' },
  logs: { kicker: 'Nhật ký', title: 'Hoạt động' },
};

const STAT_ORDER = [
  'hp', 'mp', 'atk', 'matk', 'def', 'res', 'speed', 'acc', 'eva', 'crit',
  'critDmg', 'pen', 'regen', 'cdr', 'mpen', 'mpRegen', 'healRecv', 'shieldPct',
  'ctrlRes', 'dotRes', 'mpCost', 'buffDur',
];

const RARITY_TAG = {
  pham: '',
  linh: 'jade',
  huyen: 'blue',
  dia: 'purple',
  thien: 'gold',
  tien: 'red',
  dao: 'gold',
};

const ACTIVITY_ORDER = ['seclusion', 'farm', 'gather_herb', 'mine_ore', 'body_training'];

const app = {
  meta: null,
  snapshot: null,
  view: 'overview',
  itemFilter: 'all',
  itemQuery: '',
  logFilter: 'all',
  autoDraft: null,
  autoDirty: false,
  autoSaveTimer: null,
  saveSeq: 0,
  lastSavedAt: 0,
  lastAutoToastAt: 0,
  stateAt: 0,
  booted: false,
  sse: null,
  online: false,
  dailyMap: {},
  weeklyMap: {},
  achvMap: {},
};

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function prettify(id) {
  return String(id || '')
    .replace(/^(item|equip|skill|passive|pet|region|spot|boss|mob|quest|recipe|set|title|task|achv|origin|currency|daily|weekly)_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function toNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'bigint') return Number(value);
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function fmt(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'bigint') {
    try { return value.toLocaleString('vi-VN'); } catch { return String(value); }
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : '—';
  }
  const raw = String(value);
  if (/^-?\d+$/.test(raw)) {
    try { return BigInt(raw).toLocaleString('vi-VN'); } catch { /* ignore */ }
  }
  const n = Number(raw);
  if (Number.isFinite(n)) return n.toLocaleString('vi-VN', { maximumFractionDigits: 2 });
  return esc(raw);
}

function fmtRate(rateMilli) {
  const perSecond = toNumber(rateMilli) / 1000;
  return perSecond.toLocaleString('vi-VN', { maximumFractionDigits: 2 });
}

function fmtStat(key, value) {
  const kind = app.meta?.stats?.[key]?.kind || 'int';
  const n = Number(value ?? 0);
  if (kind === 'pct') {
    if (!Number.isFinite(n)) return fmt(value);
    return `${(n * 100).toLocaleString('vi-VN', { maximumFractionDigits: 2 })}%`;
  }
  if (kind === 'x') {
    if (!Number.isFinite(n)) return fmt(value);
    return `${n.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}x`;
  }
  return fmt(value);
}

function ratioPct(part, total) {
  try {
    const a = BigInt(part ?? 0);
    const b = BigInt(total ?? 0);
    if (b <= 0n) return 0;
    return Math.max(0, Math.min(100, Number((a * 10000n) / b) / 100));
  } catch {
    const a = toNumber(part);
    const b = toNumber(total);
    if (b <= 0) return 0;
    return Math.max(0, Math.min(100, (a / b) * 100));
  }
}

function duration(ms) {
  const total = Math.max(0, toNumber(ms));
  const seconds = Math.floor(total / 1000);
  if (seconds < 60) return `${seconds} giây`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) return restMinutes ? `${hours} giờ ${restMinutes} phút` : `${hours} giờ`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} ngày ${restHours} giờ` : `${days} ngày`;
}

function timeAgo(timestamp) {
  const ts = toNumber(timestamp);
  if (!ts) return '—';
  const diff = Date.now() - ts;
  if (diff < 0) return 'vừa xong';
  const seconds = Math.floor(diff / 1000);
  if (seconds < 8) return 'vừa xong';
  if (seconds < 60) return `${seconds} giây trước`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

function until(timestamp) {
  const diff = toNumber(timestamp) - Date.now();
  if (diff <= 0) return 'đã đến';
  return duration(diff);
}

function clock(timestamp) {
  const ts = toNumber(timestamp);
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function dateTime(timestamp) {
  const ts = toNumber(timestamp);
  if (!ts) return '—';
  return new Date(ts).toLocaleString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  });
}

function state() {
  return app.snapshot?.state || null;
}

function character() {
  return state()?.character || null;
}

function isTyping() {
  const el = document.activeElement;
  return !!el && ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);
}

function fallbackChar(name) {
  return String(name || '?').trim().charAt(0) || '?';
}

function iconUrl(kind, iconId) {
  if (!iconId) return '';
  const dir = kind === 'equip' ? 'equip' : kind === 'skill' ? 'skills' : 'items';
  return `/game-assets/icons/${dir}/${encodeURIComponent(iconId)}.png`;
}

function portraitUrl(gender) {
  return `/game-assets/portraits/portrait_hero_${gender === 'female' ? 'female' : 'male'}_01.png`;
}

function imgTag(url, className = '') {
  if (!url) return '';
  return `<img${className ? ` class="${className}"` : ''} src="${esc(url)}" alt="" loading="lazy" onload="this.parentElement.classList.add('has-img')" onerror="this.remove()">`;
}

function iconBox(iconId, kind, rarity, name) {
  return `<div class="icon-box${rarity ? ` rarity-${esc(rarity)}` : ''}">${imgTag(iconUrl(kind, iconId))}<span>${esc(fallbackChar(name))}</span></div>`;
}

function summaryIcon(iconId, kind, tone, name, glyph = '') {
  const art = iconId
    ? imgTag(iconUrl(kind, iconId))
    : glyph
      ? `<svg><use href="#${glyph}"/></svg>`
      : '';
  const fallback = glyph ? '' : `<span>${esc(fallbackChar(name))}</span>`;
  return `<div class="summary-icon ${tone || ''}">${art}${fallback}</div>`;
}

function gearIcon(iconId, name) {
  return `<div class="gear-icon">${imgTag(iconUrl('equip', iconId))}<span>${esc(fallbackChar(name))}</span></div>`;
}

function skillIcon(iconId, name) {
  return `<div class="skill-icon">${imgTag(iconUrl('skill', iconId))}<span>${esc(fallbackChar(name))}</span></div>`;
}

function portraitFrame(gender, name) {
  return `<div class="portrait-frame"><span class="portrait-fallback">${esc(fallbackChar(name))}</span>${imgTag(portraitUrl(gender))}</div>`;
}

function itemInfo(id) {
  return app.meta?.items?.[id] || {
    id,
    name: prettify(id),
    desc: '',
    kind: 'material',
    icon: '',
  };
}

function recipeInfo(id) {
  return app.meta?.recipes?.[id] || null;
}

function isPillRecipe(recipe) {
  if (!recipe || recipe.output?.kind !== 'item') return false;
  const item = app.meta?.items?.[recipe.output.itemId];
  if (!item) return false;
  if (['cultivation_buff', 'cultivation_exp'].includes(item.use?.type)) return true;
  if (item.kind === 'breakthrough') return true;
  return item.kind === 'consumable' && /đan|pill/i.test(`${item.name} ${item.id}`);
}

function isUsablePillRecipe(recipe) {
  const item = app.meta?.items?.[recipe?.output?.itemId];
  return ['cultivation_buff', 'cultivation_exp'].includes(item?.use?.type);
}

function pillRecipes() {
  return Object.values(app.meta?.recipes || {})
    .filter(isPillRecipe)
    .sort((a, b) => a.reqLevel - b.reqLevel || a.name.localeCompare(b.name, 'vi'));
}

function pillCount(id) {
  return toNumber(state()?.materials?.[id]);
}

function craftWeekRemaining(recipe) {
  if (!recipe?.weekLimit) return Infinity;
  const used = toNumber(state()?.crafting?.weekUsed?.[recipe.id]);
  return Math.max(0, toNumber(recipe.weekLimit) - used);
}

function recipeCraftable(recipe) {
  const st = state();
  if (!recipe || !st || !isPillRecipe(recipe)) return false;
  if (toNumber(st.character?.level) < toNumber(recipe.reqLevel)) return false;
  if (craftWeekRemaining(recipe) < 1) return false;
  try {
    if (BigInt(st.wallet?.spirit_stone ?? '0') < BigInt(toNumber(recipe.stones))) return false;
  } catch {
    if (toNumber(st.wallet?.spirit_stone) < toNumber(recipe.stones)) return false;
  }
  return (recipe.inputs || []).every((input) => pillCount(input.itemId) >= toNumber(input.qty));
}

function recipePriority(recipe) {
  const item = itemInfo(recipe?.output?.itemId);
  const use = item.use || {};
  if (use.type === 'cultivation_buff') return 2e15 + toNumber(use.ratePct) * 1e9 + toNumber(recipe.reqLevel);
  if (use.type === 'cultivation_exp') return 1e15 + toNumber(use.exp);
  return toNumber(recipe?.reqLevel);
}

function bestCraftRecipe() {
  return pillRecipes()
    .filter((recipe) => isUsablePillRecipe(recipe) && recipeCraftable(recipe))
    .sort((a, b) => recipePriority(b) - recipePriority(a))[0] || null;
}

function buffRemainingMs(itemId) {
  const buff = (state()?.buffs || []).find((entry) => entry.id === `buff:${itemId}`);
  if (!buff) return 0;
  const now = toNumber(state()?.serverNow) || Date.now();
  return Math.max(0, toNumber(buff.expiresAt) - now);
}

function bossInfo(id) {
  return app.meta?.bosses?.[id] || null;
}

function bossCooldownRemaining(region) {
  if (!region?.bossCooldownUntil) return 0;
  const now = toNumber(state()?.serverNow) || Date.now();
  return Math.max(0, toNumber(region.bossCooldownUntil) - now);
}

function clearedBossEntries() {
  const entries = [];
  for (const region of state()?.regions || []) {
    if (!region.unlocked || !region.bossCleared) continue;
    const regionMeta = app.meta?.regions?.[region.id];
    const boss = bossInfo(regionMeta?.bossId);
    if (!boss) continue;
    entries.push({ region, regionMeta, boss });
  }
  return entries.sort((a, b) => toNumber(a.boss.reqLevel) - toNumber(b.boss.reqLevel)
    || String(a.boss.id).localeCompare(String(b.boss.id)));
}

function bossEntryReady(entry) {
  if (!entry) return false;
  const readyIds = app.snapshot?.boss?.readyIds;
  if (Array.isArray(readyIds)) return readyIds.includes(entry.boss.id);
  if (toNumber(state()?.character?.level) < toNumber(entry.boss.reqLevel)) return false;
  return bossCooldownRemaining(entry.region) <= 0;
}

function nextBossEntry() {
  const entries = clearedBossEntries();
  const nextId = app.snapshot?.boss?.nextId;
  if (nextId) {
    const found = entries.find((entry) => entry.boss.id === nextId);
    if (found) return found;
  }
  return entries.filter(bossEntryReady)[0] || null;
}

function equipInfo(id) {
  return app.meta?.equipment?.[id] || null;
}

function skillInfo(id) {
  return app.meta?.skills?.[id] || null;
}

function spotInfo(id) {
  return app.meta?.spots?.[id] || null;
}

function questInfo(id) {
  return app.meta?.quests?.[id] || null;
}

function realmInfo(char) {
  if (!char?.realm) return { name: '—', stage: '', full: '—' };
  const realm = app.meta?.realms?.[char.realm.realmId];
  const name = realm?.name || prettify(char.realm.realmId);
  const stageNumber = Number(char.realm.stage || 0);
  let stage = '';
  if (realm?.stageModel === 'layers') stage = `Tầng ${stageNumber}`;
  else if (realm?.stageModel === 'four_stage') {
    stage = ['Sơ kỳ', 'Trung kỳ', 'Hậu kỳ', 'Viên mãn'][stageNumber - 1] || `Tầng ${stageNumber}`;
  } else if (realm?.stageModel === 'gate') stage = `Cửa ${stageNumber}`;
  return { name, stage, full: stage ? `${name} · ${stage}` : name };
}

function currentActivity() {
  const st = state();
  const type = st?.activity?.type || 'seclusion';
  const act = app.meta?.activities?.[type] || { id: type, name: prettify(type), desc: '' };
  const spot = st?.activity?.targetId ? spotInfo(st.activity.targetId) : null;
  return { type, act, spot };
}

function availableSpots() {
  const st = state();
  if (!st || !app.meta?.spots) return [];
  const unlocked = new Set((st.regions || []).filter((r) => r.unlocked).map((r) => r.id));
  const level = Number(st.character?.level || 1);
  return Object.values(app.meta.spots)
    .filter((spot) => Number(spot.reqLevel || 0) <= level && unlocked.has(spot.regionId))
    .sort((a, b) => Number(b.reqLevel || 0) - Number(a.reqLevel || 0) || Number(b.expPerCycle || 0) - Number(a.expPerCycle || 0));
}

function bestSpotId() {
  return availableSpots()[0]?.id || '';
}

function kindLabel(kind) {
  return {
    consumable: 'Đan dược',
    material: 'Vật liệu',
    breakthrough: 'Đột phá',
    active: 'Chủ động',
    passive: 'Bị động',
    basic: 'Cơ bản',
  }[kind] || prettify(kind || 'Vật phẩm');
}

function statusLabel(status) {
  return {
    active: 'Đang làm',
    claimable: 'Có thể nhận',
    claimed: 'Đã nhận',
    locked: 'Chưa mở',
  }[status] || prettify(status);
}

function statusTagClass(status) {
  return {
    active: 'jade',
    claimable: 'gold',
    claimed: 'jade',
    locked: '',
  }[status] || '';
}

/* ------------------------------------------------------------------ */
/* Boot + snapshot                                                     */
/* ------------------------------------------------------------------ */

async function boot() {
  try {
    const [meta, session] = await Promise.all([
      api('/api/meta?v=2026-11-04-boss-sequential'),
      api('/api/session'),
    ]);
    app.meta = meta;
    app.dailyMap = Object.fromEntries((meta.daily || []).map((task) => [task.id, task]));
    app.weeklyMap = Object.fromEntries((meta.weekly || []).map((task) => [task.id, task]));
    app.achvMap = meta.achievements || {};
    applySnapshot(session, { initial: true });
    connectSSE();
    startTicker();
  } catch (err) {
    const bootView = $('#boot-view');
    if (bootView) {
      bootView.innerHTML = `
        <div class="boot-mark">道</div>
        <p style="color:var(--red)">Không tải được mini client: ${esc(err.message)}</p>
        <button class="btn primary" data-action="retry-boot">Thử lại</button>
      `;
    }
  }
}

function applySnapshot(snapshot, { initial = false } = {}) {
  if (!snapshot || typeof snapshot !== 'object') return;
  const previous = app.snapshot;
  app.snapshot = {
    ...(previous || {}),
    ...snapshot,
    logs: Array.isArray(snapshot.logs) ? snapshot.logs : (previous?.logs || []),
  };
  if (snapshot.state) app.stateAt = Date.now();
  if (snapshot.config && (!app.autoDirty || !app.autoDraft)) {
    app.autoDraft = { ...snapshot.config };
    if (!app.autoDirty) app.autoDirty = false;
  }
  if (initial) {
    app.booted = true;
    app.online = true;
  }
  renderChrome();
  if (app.snapshot.authenticated) {
    if (!isTyping()) rerenderPreservingFocus();
    else renderChrome();
  }
}

function onStateEvent(data) {
  if (!data || !app.snapshot) return;
  app.snapshot = {
    ...app.snapshot,
    ...data,
    logs: Array.isArray(data.logs) ? data.logs : app.snapshot.logs,
  };
  if (data.state) app.stateAt = Date.now();
  if (data.config && !app.autoDirty) app.autoDraft = { ...data.config };
  if (!app.snapshot.authenticated) {
    renderChrome();
    return;
  }
  if (isTyping()) renderChrome();
  else rerenderPreservingFocus();
}

function onConfigEvent(config) {
  if (!config || !app.snapshot) return;
  app.snapshot.config = config;
  if (!app.autoDirty) app.autoDraft = { ...config };
  if (app.view === 'auto' && !isTyping()) rerenderPreservingFocus();
  else renderChrome();
}

function onLogEvent(log) {
  if (!log || !app.snapshot) return;
  const logs = app.snapshot.logs || [];
  if (!logs.some((entry) => entry.id === log.id)) logs.push(log);
  app.snapshot.logs = logs.slice(-300);
  if (app.view === 'logs' && !isTyping()) renderView();
  const level = log.level === 'warn' ? 'warn' : log.level === 'error' ? 'error' : log.level === 'success' ? 'success' : 'info';
  if (level === 'error' || level === 'warn') {
    toast(level, log.message, log.detail);
  } else if (level === 'success' && Date.now() - app.lastAutoToastAt > 4000) {
    app.lastAutoToastAt = Date.now();
    toast('success', log.message, log.detail);
  }
}

/* ------------------------------------------------------------------ */
/* SSE                                                                 */
/* ------------------------------------------------------------------ */

function connectSSE() {
  disconnectSSE();
  try {
    const es = new EventSource('/api/events');
    app.sse = es;
    es.onopen = () => {
      app.online = true;
      updateConnection();
    };
    es.onerror = () => {
      app.online = false;
      updateConnection();
    };
    es.addEventListener('hello', (event) => {
      try { applySnapshot(JSON.parse(event.data)); } catch { /* ignore */ }
    });
    es.addEventListener('state', (event) => {
      try { onStateEvent(JSON.parse(event.data)); } catch { /* ignore */ }
    });
    es.addEventListener('config', (event) => {
      try { onConfigEvent(JSON.parse(event.data)); } catch { /* ignore */ }
    });
    es.addEventListener('log', (event) => {
      try { onLogEvent(JSON.parse(event.data)); } catch { /* ignore */ }
    });
  } catch {
    app.online = false;
    updateConnection();
  }
}

function disconnectSSE() {
  if (app.sse) {
    app.sse.close();
    app.sse = null;
  }
}

/* ------------------------------------------------------------------ */
/* Chrome                                                              */
/* ------------------------------------------------------------------ */

function renderChrome() {
  const authenticated = !!app.snapshot?.authenticated;
  const bootView = $('#boot-view');
  const loginView = $('#login-view');
  const mainView = $('#main-view');
  if (!bootView || !loginView || !mainView) return;

  bootView.hidden = app.booted;
  loginView.hidden = !app.booted || authenticated;
  mainView.hidden = !app.booted || !authenticated;

  if (!authenticated) {
    document.title = 'Vấn Đạo · Mini Client';
    updateConnection();
    return;
  }

  const char = character();
  const realm = realmInfo(char);
  const name = char?.name || app.snapshot?.user?.username || '—';
  const topName = $('#top-name');
  const topRealm = $('#top-realm');
  const topPortrait = $('#top-portrait');
  if (topName) topName.textContent = name;
  if (topRealm) topRealm.textContent = realm.full;
  if (topPortrait) {
    topPortrait.src = portraitUrl(char?.gender);
    topPortrait.alt = name;
    topPortrait.style.visibility = char ? 'visible' : 'hidden';
  }

  const meta = VIEW_META[app.view] || VIEW_META.overview;
  const pageKicker = $('#page-kicker');
  const pageTitle = $('#page-title');
  if (pageKicker) pageKicker.textContent = meta.kicker;
  if (pageTitle) pageTitle.textContent = meta.title;
  document.title = `${meta.title} · Vấn Đạo Mini Client`;

  $$('.nav-btn[data-action="nav"]').forEach((button) => {
    button.classList.toggle('on', button.dataset.view === app.view);
  });
  const autoDot = $('#auto-dot');
  if (autoDot) autoDot.hidden = !app.snapshot?.config?.enabled;
  updateConnection();
}

function updateConnection() {
  const dot = $('#conn-dot');
  const text = $('#conn-text');
  if (dot) dot.className = `dot ${app.online ? 'online' : 'offline'}`;
  if (text) text.textContent = app.online ? 'Trực tuyến' : 'Mất kết nối';
}

function renderView() {
  if (!app.snapshot?.authenticated) return;
  const content = $('#content');
  if (!content) return;
  let html = '';
  try {
    if (app.view === 'items') html = renderItems();
    else if (app.view === 'auto') html = renderAuto();
    else if (app.view === 'logs') html = renderLogs();
    else html = renderOverview();
  } catch (err) {
    html = `<section class="card"><div class="empty"><b>Không dựng được giao diện</b><p>${esc(err.message)}</p></div></section>`;
  }
  content.innerHTML = html;
  if (app.view === 'items') renderItemList();
  renderChrome();
  updateLiveBits();
}

/* ------------------------------------------------------------------ */
/* Overview                                                            */
/* ------------------------------------------------------------------ */

function renderOverview() {
  return `<div class="dash">
    ${renderHero()}
    ${renderStatsCard()}
    ${renderActivityCard()}
    ${renderQuestsCard()}
    ${renderDailyCard()}
    ${renderGearCard()}
    ${renderSkillsCard()}
    ${renderAttrsCard()}
  </div>`;
}

function renderHero() {
  const st = state();
  const char = st?.character;
  if (!char) return '';
  const realm = realmInfo(char);
  const origin = app.meta?.origins?.[char.originId];
  const expPct = ratioPct(char.exp, char.expNeed);
  const activity = currentActivity();
  const power = fmt(st.power);
  return `<section class="card hero span-3">
    <div class="hero-left">
      ${portraitFrame(char.gender, char.name)}
      <div class="hero-copy">
        <div class="hero-title">
          <h2>${esc(char.name)}</h2>
          <span class="tag jade">${esc(realm.full)}</span>
          <span class="tag gold">Cấp ${fmt(char.level)}</span>
        </div>
        <p class="hero-origin">${esc(origin?.desc || '')}</p>
        <div class="hero-meta">
          <span><b>${power}</b> chiến lực</span>
          <span><b>${esc(origin?.name || prettify(char.originId))}</b> xuất thân</span>
          <span><b>${esc(fmtRate(char.rateMilli))}</b> tu vi/giây</span>
          <span><b>${esc(activity.act.name)}</b> hoạt động</span>
        </div>
        <div class="exp-wrap">
          <div class="exp-head">
            <span>Tu vi · ${esc(realm.name)}</span>
            <span><b>${fmt(char.exp)}</b> / ${fmt(char.expNeed)} <span class="exp-pct">${expPct.toFixed(1)}%</span></span>
          </div>
          <div class="bar gold"><i style="width:${expPct}%"></i></div>
        </div>
      </div>
    </div>
    <div class="hero-right">
      <div class="power-ring"><div><b>${power}</b><span>chiến lực</span></div></div>
      <div class="hero-facts">
        <div><span>Đã kết toán</span><b>${esc(timeAgo(char.lastSettledAt))}</b></div>
        <div><span>Giới hạn tích lũy</span><b>${esc(duration(char.idleCapMs))}</b></div>
        <div><span>Tự lên tầng</span><b>${char.autoMinor ? 'Đang bật' : 'Đang tắt'}</b></div>
        <div><span>Cập nhật</span><b data-live="state-age">${esc(timeAgo(app.stateAt))}</b></div>
      </div>
    </div>
  </section>`;
}

function statCell(key) {
  const st = state();
  const def = app.meta?.stats?.[key];
  const value = st?.stats?.[key];
  const zero = Number(value) === 0;
  return `<span>${esc(def?.label || prettify(key))}</span><b class="${zero ? 'zero' : ''}">${fmtStat(key, value)}</b>`;
}

function renderStatsCard() {
  const st = state();
  const keys = STAT_ORDER.filter((key) => app.meta?.stats?.[key]);
  const rows = [];
  for (let index = 0; index < keys.length; index += 2) {
    const left = keys[index];
    const right = keys[index + 1];
    rows.push(`<div class="stat-row">${statCell(left)}${right ? statCell(right) : '<span></span><b></b>'}</div>`);
  }
  return `<section class="card span-2">
    <div class="card-head">
      <div><span class="eyebrow">Bảng stat</span><h3>Thuộc tính chiến đấu</h3></div>
      <span class="tag ghost">${keys.length} chỉ số</span>
    </div>
    <div class="stat-table">
      <div class="stat-head"><span>Chỉ số</span><span>Giá trị</span><span>Chỉ số</span><span>Giá trị</span></div>
      ${rows.join('')}
    </div>
    <div class="stat-foot">
      <div class="mini-stat"><span>Chiến lực</span><b>${fmt(st?.power)}</b></div>
      <div class="mini-stat"><span>Sinh lực</span><b>${fmt(st?.stats?.hp)}</b></div>
      <div class="mini-stat"><span>Tốc độ tu vi</span><b>${esc(fmtRate(st?.character?.rateMilli))}/giây</b></div>
    </div>
  </section>`;
}

function renderActivityCard() {
  const st = state();
  const activity = st?.activity || {};
  const info = currentActivity();
  const cycleMs = toNumber(activity.cycleMs);
  const progress = cycleMs > 0 ? Math.min(100, (toNumber(activity.cycleProgressMs) / cycleMs) * 100) : 0;
  const winTag = activity.win === true
    ? '<span class="tag jade">Thắng</span>'
    : activity.win === false
      ? '<span class="tag red">Thua</span>'
      : '<span class="tag">Chờ</span>';
  return `<section class="card">
    <div class="activity-head">
      <div><span class="eyebrow">Hoạt động</span><h3>${esc(info.act.name)}</h3></div>
      ${winTag}
    </div>
    <p class="activity-desc">${esc(info.act.desc || '')}</p>
    ${info.spot ? `<div class="activity-spot"><svg><use href="#i-map"/></svg><b>${esc(info.spot.name)}</b><span class="tag ghost">${esc(app.meta?.regions?.[info.spot.regionId]?.name || '')}</span></div>` : ''}
    <div class="cycle">
      <div class="cycle-top"><span>Tiến độ chu kỳ</span><b id="cycle-text">${progress.toFixed(0)}%</b></div>
      <div class="bar jade"><i id="cycle-bar" style="width:${progress}%"></i></div>
    </div>
    <div class="kv-list">
      <div><span>Điểm săn</span><b>${esc(info.spot?.name || 'Không có')}</b></div>
      <div><span>Tu vi mỗi chu kỳ</span><b>${fmt(activity.expPerCycle)}</b></div>
      <div><span>Tốc độ hiện tại</span><b>${esc(fmtRate(st?.character?.rateMilli))}/giây</b></div>
      <div><span>Chu kỳ</span><b>${cycleMs > 0 ? esc(duration(cycleMs)) : '—'}</b></div>
    </div>
    <button class="btn ghost wide" data-action="goto-auto" style="margin-top:14px">
      <svg><use href="#i-auto"/></svg><span>Đổi hoạt động &amp; cấu hình</span>
    </button>
  </section>`;
}

function questRewardText(info) {
  const rewards = info?.rewards || {};
  const bits = [];
  if (rewards.stones) bits.push(`+${fmt(rewards.stones)} linh thạch`);
  for (const id of rewards.equipDefIds || []) {
    const equip = equipInfo(id);
    if (equip) bits.push(equip.name);
  }
  return bits.join(' · ');
}

function renderQuestsCard() {
  const st = state();
  const all = (st?.quests || []).map((quest) => ({ ...quest, info: questInfo(quest.id) }));
  const claimable = all.filter((quest) => quest.status === 'claimable');
  const active = all.filter((quest) => quest.status === 'active');
  const locked = all.filter((quest) => quest.status === 'locked');
  const shown = [...claimable, ...active, ...locked.slice(0, 1)].slice(0, 5);
  const headTag = claimable.length
    ? `<span class="tag gold">${claimable.length} có thể nhận</span>`
    : `<span class="tag jade">${active.length} đang làm</span>`;
  return `<section class="card span-2">
    <div class="card-head">
      <div><span class="eyebrow">Lộ trình</span><h3>Nhiệm vụ</h3></div>
      ${headTag}
    </div>
    ${shown.length ? `<div class="quest-list">${shown.map((quest) => {
      const info = quest.info;
      const pct = ratioPct(quest.current, quest.target);
      const reward = questRewardText(info);
      return `<div class="quest-row ${quest.status === 'claimable' ? 'claimable' : ''}">
        <div class="quest-top">
          <div>
            <b>${esc(info?.name || prettify(quest.id))}</b>
            <div class="quest-desc">${esc(info?.desc || '')}</div>
          </div>
          <span class="tag ${statusTagClass(quest.status)}">${esc(statusLabel(quest.status))}</span>
        </div>
        <div class="quest-progress">
          <div class="bar ${quest.status === 'claimable' ? 'gold' : ''}"><i style="width:${pct}%"></i></div>
          <span>${fmt(quest.current)} / ${fmt(quest.target)}</span>
        </div>
        <div class="quest-bottom">
          <span class="quest-reward">${esc(reward)}</span>
          ${quest.status === 'claimable' ? `<button class="btn primary small" data-action="claim-quest" data-id="${esc(quest.id)}">Nhận</button>` : ''}
        </div>
      </div>`;
    }).join('')}</div>` : `<div class="empty"><svg><use href="#i-star"/></svg><b>Chưa có nhiệm vụ</b><p>Tiến trình nhiệm vụ sẽ xuất hiện khi nhân vật bắt đầu hành trình.</p></div>`}
  </section>`;
}

function periodicRow(task, name, action, tagClass) {
  const claimed = !!task.claimed;
  const ready = !claimed && toNumber(task.current) >= toNumber(task.target);
  const pct = ratioPct(task.current, task.target);
  const actionButton = action === 'daily'
    ? `<button class="btn primary small" data-action="claim-daily" data-id="${esc(task.id)}">Nhận</button>`
    : action === 'weekly'
      ? `<button class="btn primary small" data-action="claim-weekly" data-id="${esc(task.id)}">Nhận</button>`
      : `<button class="btn primary small" data-action="claim-achievement" data-id="${esc(task.id)}">Nhận</button>`;
  return `<div class="periodic-row">
    <div class="periodic-main">
      <b>${esc(name || prettify(task.id))}</b>
      <small>${claimed ? 'Đã nhận' : `${fmt(task.current)} / ${fmt(task.target)}`}</small>
      <div class="bar ${ready ? 'gold' : ''}"><i style="width:${pct}%"></i></div>
    </div>
    ${claimed ? `<span class="tag jade">Đã nhận</span>` : ready ? actionButton : `<span class="tag ${tagClass || ''}">Chờ</span>`}
  </div>`;
}

function renderDailyCard() {
  const st = state();
  const periodic = st?.periodic || {};
  const daily = periodic.daily || [];
  const weekly = periodic.weekly || [];
  const achievements = periodic.achievements || [];
  const dailyReady = daily.filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target));
  const weeklyReady = weekly.filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target));
  const achvReady = achievements.filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target));
  const totalReady = dailyReady.length + weeklyReady.length + achvReady.length;
  return `<section class="card">
    <div class="card-head">
      <div><span class="eyebrow">Chu kỳ</span><h3>Thưởng chờ nhận</h3></div>
      <span class="tag ${totalReady ? 'gold' : ''}">${totalReady ? `${totalReady} mốc` : 'Chưa có'}</span>
    </div>
    <div class="periodic-list">
      ${daily.slice(0, 4).map((task) => periodicRow(task, app.dailyMap[task.id]?.name, 'daily')).join('')}
      <div class="periodic-row">
        <div class="periodic-main">
          <b>Nhiệm vụ tuần</b>
          <small>${weeklyReady.length}/${weekly.length} mốc · làm mới sau ${until(periodic.weeklyResetAt)}</small>
        </div>
        ${weeklyReady.length
          ? `<button class="btn primary small" data-action="claim-weekly-ready">Nhận ${weeklyReady.length}</button>`
          : `<span class="tag">Chờ</span>`}
      </div>
      <div class="periodic-row">
        <div class="periodic-main">
          <b>Thành tựu</b>
          <small>${achvReady.length}/${achievements.length} mốc · tích lũy dài hạn</small>
        </div>
        ${achvReady.length
          ? `<button class="btn primary small" data-action="claim-achv-ready">Nhận ${achvReady.length}</button>`
          : `<span class="tag">Chờ</span>`}
      </div>
    </div>
    <div class="auto-save-note" style="margin-top:12px">
      <i class="dot"></i>
      <span>Ngày làm mới sau ${esc(until(periodic.dailyResetAt))} · đã nhận ${fmt(periodic.dailyClaims)}/4</span>
    </div>
  </section>`;
}

function renderGearCard() {
  const st = state();
  const equipped = (st?.equipment || []).filter((item) => item.location === 'equipped');
  const bySlot = new Map();
  for (const item of equipped) {
    const def = equipInfo(item.defId);
    if (def?.slot) bySlot.set(def.slot, { item, def });
  }
  const slots = app.meta?.slots || {};
  const order = Object.keys(slots);
  const rows = order.map((slot) => {
    const entry = bySlot.get(slot);
    if (!entry) {
      return `<div class="gear-slot">
        <div class="gear-icon">${esc((slots[slot] || slot).charAt(0))}</div>
        <div><b>${esc(slots[slot] || slot)}</b><small>Trống</small></div>
        <span class="tag">—</span>
      </div>`;
    }
    const { item, def } = entry;
    const rarity = app.meta?.rarities?.[def.rarity]?.label || def.rarity;
    return `<div class="gear-slot">
      ${gearIcon(def.icon, def.name)}
      <div><b>${esc(def.name)}${item.enhance ? ` +${fmt(item.enhance)}` : ''}</b><small>${esc(rarity)} · ${esc(slots[def.slot] || def.slot)}</small></div>
      <span class="tag ${RARITY_TAG[def.rarity] || ''}">${esc(rarity)}</span>
    </div>`;
  }).join('');
  return `<section class="card">
    <div class="card-head">
      <div><span class="eyebrow">Trang bị</span><h3>Đang mặc</h3></div>
      <span class="tag ghost">${equipped.length}/${order.length}</span>
    </div>
    <div class="gear-list">${rows}</div>
  </section>`;
}

function renderSkillsCard() {
  const st = state();
  const learned = st?.learnedSkills || [];
  const skills = learned.map((id) => skillInfo(id)).filter(Boolean);
  const shown = skills.slice(0, 4);
  return `<section class="card">
    <div class="card-head">
      <div><span class="eyebrow">Chiêu thức</span><h3>Kỹ năng</h3></div>
      <span class="tag ghost">${skills.length} đã học</span>
    </div>
    ${shown.length ? `<div class="skill-list">${shown.map((skill) => `<div class="skill-row">
      ${skillIcon(skill.icon, skill.name)}
      <div><b>${esc(skill.name)}</b><small>${esc(kindLabel(skill.kind))}${skill.mpCost ? ` · ${fmt(skill.mpCost)} linh lực` : ''}${skill.cooldownMs ? ` · ${duration(skill.cooldownMs)}` : ''}</small></div>
      <span class="tag ${skill.kind === 'passive' ? 'blue' : 'jade'}">${esc(kindLabel(skill.kind))}</span>
    </div>`).join('')}</div>` : `<div class="empty"><svg><use href="#i-sword"/></svg><b>Chưa học kỹ năng</b><p>Kỹ năng đầu tiên sẽ xuất hiện sau khi nhân vật nhập môn.</p></div>`}
    ${skills.length > shown.length ? `<p class="small muted" style="margin-top:9px">+${skills.length - shown.length} kỹ năng khác trong bảng kỹ năng.</p>` : ''}
  </section>`;
}

function renderAttrsCard() {
  const st = state();
  const char = st?.character;
  if (!char) return '';
  const origin = app.meta?.origins?.[char.originId];
  const attrs = char.attrs || {};
  const keys = ['can_cot', 'dao_tam', 'co_duyen', 'ngo_tinh'];
  return `<section class="card">
    <div class="card-head">
      <div><span class="eyebrow">Căn cơ</span><h3>Xuất thân &amp; tư chất</h3></div>
      <span class="tag gold">${esc(origin?.name || prettify(char.originId))}</span>
    </div>
    <div class="attr-grid">
      ${keys.map((key) => {
        const def = app.meta?.attrs?.[key];
        return `<div class="attr-tile">
          <span>${esc(def?.label || prettify(key))}</span>
          <b>${fmt(attrs[key])}</b>
          <small>${esc(def?.desc || '')}</small>
        </div>`;
      }).join('')}
    </div>
    <p class="small muted" style="margin-top:11px;line-height:1.55">${esc(origin?.desc || '')}</p>
  </section>`;
}

/* ------------------------------------------------------------------ */
/* Items                                                               */
/* ------------------------------------------------------------------ */

function collectItemRows() {
  const st = state();
  if (!st) return [];
  const rows = [];

  for (const [id, qty] of Object.entries(st.wallet || {})) {
    if (toNumber(qty) <= 0) continue;
    const currency = app.meta?.currencies?.[id];
    rows.push({
      type: 'currency',
      id,
      qty,
      name: currency?.name || prettify(id),
      desc: 'Tiền tệ',
      icon: currency?.icon || '',
      kind: 'item',
      sort: 0,
    });
  }

  for (const [id, qty] of Object.entries(st.materials || {})) {
    if (toNumber(qty) <= 0) continue;
    const info = itemInfo(id);
    rows.push({
      type: 'material',
      id,
      qty,
      name: info.name,
      desc: info.desc,
      icon: info.icon,
      kind: 'item',
      itemKind: info.kind,
      sort: 1,
    });
  }

  for (const item of st.equipment || []) {
    const def = equipInfo(item.defId);
    rows.push({
      type: 'equipment',
      id: item.id,
      defId: item.defId,
      qty: 1,
      name: def?.name || prettify(item.defId),
      desc: def
        ? `Trang bị ${(app.meta?.slots?.[def.slot] || def.slot).toLowerCase()}`
        : 'Trang bị chưa rõ phẩm cấp',
      icon: def?.icon || '',
      kind: 'equip',
      rarity: def?.rarity || '',
      enhance: item.enhance || 0,
      location: item.location || 'bag',
      def,
      sort: 2,
    });
  }

  return rows.sort((a, b) => {
    if (a.sort !== b.sort) return a.sort - b.sort;
    return String(a.name).localeCompare(String(b.name), 'vi');
  });
}

function filteredItemRows() {
  const query = app.itemQuery.trim().toLowerCase();
  return collectItemRows().filter((row) => {
    if (app.itemFilter !== 'all' && row.type !== app.itemFilter) return false;
    if (!query) return true;
    return `${row.name} ${row.desc} ${row.id} ${row.defId || ''}`.toLowerCase().includes(query);
  });
}

function itemRow(row) {
  const typeLabel = row.type === 'currency' ? 'Tiền tệ' : row.type === 'equipment' ? 'Trang bị' : 'Vật liệu';
  const rarityLabel = row.rarity ? (app.meta?.rarities?.[row.rarity]?.label || row.rarity) : '';
  const subBits = [];
  if (row.type === 'material') subBits.push(kindLabel(row.itemKind));
  if (row.type === 'equipment') {
    subBits.push(`Cấp ${row.def?.reqLevel ?? '—'}`);
    const setInfo = row.def?.setId ? app.meta?.sets?.[row.def.setId] : null;
    if (setInfo?.name) subBits.push(setInfo.name);
  }
  if (row.type === 'currency') subBits.push('Tài nguyên');
  return `<div class="item-row">
    ${iconBox(row.icon, row.kind, row.rarity, row.name)}
    <div class="item-main">
      <div class="item-name">
        ${esc(row.name)}
        ${row.enhance ? `<span class="tag gold">+${fmt(row.enhance)}</span>` : ''}
        ${rarityLabel ? `<span class="tag ${RARITY_TAG[row.rarity] || ''}">${esc(rarityLabel)}</span>` : ''}
        ${row.type === 'equipment' ? `<span class="tag ${row.location === 'equipped' ? 'jade' : ''}">${row.location === 'equipped' ? 'Đang mặc' : 'Trong túi'}</span>` : ''}
      </div>
      <div class="item-desc">${esc(row.desc || '')}</div>
      <div class="item-sub">${subBits.map((bit) => `<span>${esc(bit)}</span>`).join('')}</div>
    </div>
    <div class="item-side">
      <b>${row.type === 'equipment' ? '1' : `x${fmt(row.qty)}`}</b>
      <span>${esc(typeLabel)}</span>
    </div>
  </div>`;
}

function renderItemList() {
  const list = $('#item-list');
  if (!list) return;
  const rows = filteredItemRows();
  if (!rows.length) {
    const query = app.itemQuery.trim();
    list.innerHTML = `<div class="empty">
      <svg><use href="#i-bag"/></svg>
      <b>${query ? 'Không tìm thấy vật phẩm' : 'Túi đồ đang trống'}</b>
      <p>${query ? `Không có món nào khớp “${esc(query)}”.` : 'Bật săn yêu thú hoặc thu thập ở tab Tự động để nhận vật liệu, trang bị và tiền tệ.'}</p>
    </div>`;
    return;
  }
  list.innerHTML = rows.map(itemRow).join('');
}

function renderItems() {
  const st = state();
  const wallet = st?.wallet || {};
  const materials = Object.entries(st?.materials || {}).filter(([, qty]) => toNumber(qty) > 0);
  const equipment = st?.equipment || [];
  const equipped = equipment.filter((item) => item.location === 'equipped');
  const materialTotal = materials.reduce((sum, [, qty]) => sum + toNumber(qty), 0);
  const spirit = toNumber(wallet.spirit_stone);
  const rows = collectItemRows();
  const counts = {
    all: rows.length,
    currency: rows.filter((row) => row.type === 'currency').length,
    material: rows.filter((row) => row.type === 'material').length,
    equipment: rows.filter((row) => row.type === 'equipment').length,
  };
  const filters = [
    ['all', 'Tất cả', counts.all],
    ['currency', 'Tiền tệ', counts.currency],
    ['material', 'Vật liệu', counts.material],
    ['equipment', 'Trang bị', counts.equipment],
  ];
  return `<div class="items-view">
    <div class="summary-row">
      <div class="summary-card">
        ${summaryIcon(app.meta?.currencies?.spirit_stone?.icon || 'item_spirit_stone_low_01', 'item', '', 'Linh')}
        <div class="summary-main"><span>Linh thạch</span><b>${fmt(spirit)}</b><small>Tiền tệ chính</small></div>
      </div>
      <div class="summary-card">
        ${summaryIcon('item_spirit_herb_01', 'item', 'jade', 'Vật')}
        <div class="summary-main"><span>Vật liệu</span><b>${fmt(materialTotal)}</b><small>${materials.length} loại trong túi</small></div>
      </div>
      <div class="summary-card">
        ${summaryIcon('', 'item', 'blue', 'Trang', 'i-shield')}
        <div class="summary-main"><span>Trang bị</span><b>${equipment.length}/${fmt(st?.bagCapacity)}</b><small>${equipped.length} món đang mặc</small></div>
      </div>
      <div class="summary-card">
        ${summaryIcon('', 'item', 'neutral', 'Kho', 'i-bag')}
        <div class="summary-main"><span>Kho đồ</span><b>${fmt(st?.vaultEquip?.count)}/${fmt(st?.vaultEquip?.capacity)}</b><small>Trang bị dự phòng</small></div>
      </div>
    </div>

    <section class="card">
      <div class="card-head">
        <div><span class="eyebrow">Tóm tắt vật phẩm</span><h3>Túi đồ &amp; tài nguyên</h3></div>
        <div class="item-tools">
          <div class="search-box">
            <svg><use href="#i-search"/></svg>
            <input id="item-search" type="text" value="${esc(app.itemQuery)}" placeholder="Tìm vật phẩm…" autocomplete="off" spellcheck="false" />
          </div>
        </div>
      </div>
      <div class="filter-row" style="margin-bottom:14px">
        ${filters.map(([value, label, count]) => `<button class="chip ${app.itemFilter === value ? 'on' : ''}" data-action="item-filter" data-filter="${value}">${label} <span style="opacity:.55">${count}</span></button>`).join('')}
      </div>
      <div id="item-list" class="item-list"></div>
    </section>
  </div>`;
}

/* ------------------------------------------------------------------ */
/* Auto                                                               */
/* ------------------------------------------------------------------ */

function ensureAutoDraft() {
  if (!app.autoDraft) app.autoDraft = { ...(app.snapshot?.config || {}) };
  return app.autoDraft;
}

function selectOptions(options, selected) {
  return options.map(([value, label]) => `<option value="${esc(value)}" ${String(selected) === String(value) ? 'selected' : ''}>${esc(label)}</option>`).join('');
}

function switchRow(key, title, description, checked, disabled = false) {
  return `<label class="switch-row">
    <div><b>${esc(title)}</b><small>${esc(description)}</small></div>
    <span class="switch">
      <input type="checkbox" data-config="${key}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''} />
      <span class="track"></span>
    </span>
  </label>`;
}

function renderAuto() {
  const cfg = ensureAutoDraft();
  const st = state();
  const enabled = !!cfg.enabled;
  const interval = Math.max(5000, toNumber(cfg.intervalMs) || 15000);
  const activityInfo = app.meta?.activities?.[cfg.activityType] || app.meta?.activities?.seclusion;
  const spots = availableSpots();
  const spotMap = new Map(spots.map((spot) => [spot.id, spot]));
  const currentSpot = cfg.huntSpotId ? spotInfo(cfg.huntSpotId) : null;
  if (currentSpot && !spotMap.has(currentSpot.id)) spotMap.set(currentSpot.id, currentSpot);
  const spotOptions = [['', 'Tự động chọn điểm tốt nhất'], ...[...spotMap.values()].map((spot) => [spot.id, `${spot.name} · cấp ${spot.reqLevel}`])];
  const intervalOptions = [
    [5000, '5 giây'], [10000, '10 giây'], [15000, '15 giây'], [30000, '30 giây'],
    [60000, '1 phút'], [120000, '2 phút'], [300000, '5 phút'],
  ];
  const activityOptions = ACTIVITY_ORDER
    .filter((id) => app.meta?.activities?.[id])
    .map((id) => [id, app.meta.activities[id].name]);
  const salvageTierOptions = [
    [0, 'Tắt xử lý tự động'],
    [-1, 'Tự theo cảnh giới'],
    [1, 'Chỉ phẩm Phàm'],
    [2, 'Phàm và Linh'],
    [3, 'Từ Huyền trở xuống'],
    [4, 'Từ Địa trở xuống'],
    [5, 'Từ Thiên trở xuống'],
  ];
  const modeOptions = [['salvage', 'Phân giải lấy thiết khoáng'], ['sell', 'Bán lấy linh thạch']];
  const saveText = app.autoDirty
    ? 'Đang lưu thay đổi…'
    : app.lastSavedAt
      ? `Đã lưu lúc ${clock(app.lastSavedAt)}`
      : 'Thay đổi được lưu tự động';
  const readyDaily = (st?.periodic?.daily || []).filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target)).length;
  const readyWeekly = (st?.periodic?.weekly || []).filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target)).length;
  const readyAchv = (st?.periodic?.achievements || []).filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target)).length;

  const recipeChoices = pillRecipes();
  const recipeOptions = [
    ['', 'Tự chọn đan tốt nhất có thể luyện'],
    ...recipeChoices.map((recipe) => [
      recipe.id,
      `${itemInfo(recipe.output.itemId).name} · cấp ${recipe.reqLevel} · ${duration(recipe.durationMs)}`,
    ]),
  ];
  const selectedRecipe = cfg.craftRecipeId ? recipeInfo(cfg.craftRecipeId) : null;
  const autoBestRecipe = bestCraftRecipe();
  const previewRecipe = selectedRecipe || autoBestRecipe;
  const crafting = st?.crafting || {};
  const freeSlots = Math.max(0, toNumber(crafting.slots) - (crafting.jobs?.length || 0));
  const previewItem = previewRecipe ? itemInfo(previewRecipe.output.itemId) : null;
  const previewHave = previewItem ? pillCount(previewItem.id) : 0;
  const previewInputs = (previewRecipe?.inputs || []).map((input) => {
    const item = itemInfo(input.itemId);
    const have = pillCount(input.itemId);
    const need = toNumber(input.qty);
    return { item, have, need, ok: have >= need };
  });
  const buffPills = Object.values(app.meta?.items || {})
    .filter((item) => item.use?.type === 'cultivation_buff' && pillCount(item.id) > 0)
    .sort((a, b) => toNumber(b.use.ratePct) - toNumber(a.use.ratePct));
  const expPills = Object.values(app.meta?.items || {})
    .filter((item) => item.use?.type === 'cultivation_exp' && pillCount(item.id) > 0)
    .sort((a, b) => toNumber(b.use.exp) - toNumber(a.use.exp));
  const pillSummary = buffPills.length
    ? `<ul class="pill-list">${buffPills.map((item, index) => {
      const remaining = buffRemainingMs(item.id);
      return `<li class="${index === 0 ? 'best' : ''}">
        <span class="pill-name"><b>${esc(item.name)}</b><i>×${fmt(pillCount(item.id))}</i></span>
        <span class="pill-effect">+${fmt(item.use.ratePct)}% tốc độ · ${remaining > 0 ? `còn ${duration(remaining)}` : 'chưa kích hoạt'}</span>
      </li>`;
    }).join('')}</ul>`
    : '<p class="small muted">Chưa có đan tăng tốc tu vi trong túi.</p>';
  const expSummary = expPills.length
    ? `<p class="small muted">Đan tu vi trực tiếp: <b>${esc(expPills[0].name)}</b> ×${fmt(pillCount(expPills[0].id))} (+${fmt(expPills[0].use.exp)} tu vi mỗi đan).</p>`
    : '';
  const craftInputSummary = previewInputs.length
    ? previewInputs.map((input) => `<span class="pill-mat ${input.ok ? 'ok' : 'missing'}">${esc(input.item.name)} ${fmt(input.have)}/${fmt(input.need)}</span>`).join('')
    : '<span class="pill-mat ok">Không cần nguyên liệu</span>';

  const bossEntries = clearedBossEntries();
  const bossOptions = [
    ['', 'Đánh tuần tự tất cả boss đã vượt'],
    ...bossEntries.map((entry) => [
      entry.region.id,
      `${entry.boss.name} · ${entry.regionMeta?.name || entry.region.id} · cấp ${entry.boss.reqLevel}`,
    ]),
  ];
  const selectedBossEntry = cfg.bossRegionId
    ? bossEntries.find((entry) => entry.region.id === cfg.bossRegionId) || null
    : null;
  const bossTarget = selectedBossEntry || nextBossEntry();
  const bossStatusRows = bossEntries.length
    ? bossEntries.map((entry) => {
      const remaining = bossCooldownRemaining(entry.region);
      const levelOk = toNumber(st?.character?.level) >= toNumber(entry.boss.reqLevel);
      const ready = bossEntryReady(entry);
      const isNext = !!bossTarget && bossTarget.boss.id === entry.boss.id;
      const label = !levelOk
        ? `Cần cấp ${fmt(entry.boss.reqLevel)}`
        : remaining > 0
          ? `Hồi chiêu còn ${duration(remaining)}`
          : ready
            ? (isNext ? 'Kế tiếp' : 'Sẵn sàng')
            : 'Chờ nhịp cục bộ';
      return `<li class="${ready ? 'best' : ''}">
        <span class="pill-name"><b>${esc(entry.boss.name)}</b><i>${esc(entry.regionMeta?.name || entry.region.id)}</i></span>
        <span class="pill-effect">${esc(label)}</span>
      </li>`;
    }).join('')
    : '<p class="small muted">Chưa có boss khu vực nào đã hạ. Hãy khiêu chiến boss lần đầu trong game.</p>';

  return `<div class="auto-view">
    <section class="card auto-banner ${enabled ? 'on' : ''}">
      <div class="auto-banner-main">
        <div class="pulse-orb"><svg><use href="#i-spark"/></svg></div>
        <div>
          <span class="eyebrow">Trợ lý tự động</span>
          <h2>${enabled ? 'Đang chạy' : 'Đang tắt'}</h2>
          <p>${enabled
            ? `Mỗi ${duration(interval)} máy chủ cục bộ sẽ kết toán tu vi, đồng bộ thiết lập, giữ hoạt động, nhận các mốc thưởng đã đạt${cfg.autoCraft ? ', tự luyện đan' : ''}${cfg.autoUse ? ', tự dùng đan' : ''}${cfg.autoBoss ? ', tự đánh boss' : ''}.`
            : 'Bật trợ lý để tự động kết toán, giữ hoạt động và nhận thưởng theo cấu hình bên dưới.'}</p>
          <div class="auto-status-line">
            <span>Nhịp <b>${esc(duration(interval))}</b></span>
            <span>Hoạt động <b>${esc(activityInfo?.name || '—')}</b></span>
            <span>Cập nhật <b data-live="state-age">${esc(timeAgo(app.stateAt))}</b></span>
            <span>Chờ nhận <b>${readyDaily + readyWeekly + readyAchv}</b></span>
          </div>
        </div>
      </div>
      <label class="switch big">
        <input type="checkbox" data-config="enabled" ${enabled ? 'checked' : ''} />
        <span class="track"></span>
        <span class="switch-text">${enabled ? 'Bật' : 'Tắt'}</span>
      </label>
    </section>

    <div class="auto-grid">
      <section class="card span-2">
        <div class="card-head">
          <div><span class="eyebrow">Cấu hình</span><h3>Nhịp chạy &amp; tu luyện</h3></div>
          <span class="tag ${enabled ? 'jade' : ''}">${enabled ? 'Đang hoạt động' : 'Đang tạm dừng'}</span>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>Chu kỳ tự động</span>
            <select data-config="intervalMs">${selectOptions(intervalOptions, interval)}</select>
            <small>Tối thiểu 5 giây. Nhịp ngắn hơn sẽ gửi lệnh thường xuyên hơn tới máy chủ game.</small>
          </label>
          <label class="field">
            <span>Hoạt động chính</span>
            <select data-config="activityType">${selectOptions(activityOptions, cfg.activityType)}</select>
            <small>${esc(activityInfo?.desc || '')}</small>
          </label>
          <label class="field">
            <span>Điểm săn</span>
            <select data-config="huntSpotId">${selectOptions(spotOptions, cfg.huntSpotId || '')}</select>
            <small>${spots.length ? `${spots.length} điểm săn đã mở phù hợp cấp hiện tại.` : 'Chưa có điểm săn nào đã mở ở cấp hiện tại.'}</small>
          </label>
          <label class="field">
            <span>Chế độ dọn trang bị</span>
            <select data-config="autoSalvageTier">${selectOptions(salvageTierOptions, cfg.autoSalvageTier)}</select>
            <small>Chọn phẩm tối đa được tự xử lý khi túi đầy.</small>
          </label>
        </div>
        <div class="switch-list">
          ${switchRow('autoMinor', 'Tự lên tiểu tầng', 'Tự động lên tầng khi đủ tu vi, kể cả khi không mở tab. Đại cảnh giới vẫn cần xác nhận thủ công.', cfg.autoMinor)}
          ${switchRow('autoActivity', 'Giữ hoạt động đã chọn', 'Tự chuyển về hoạt động và điểm săn đã cấu hình nếu game thay đổi trạng thái.', cfg.autoActivity)}
          ${switchRow('autoFallbackHunt', 'Lùi điểm săn khi thua', 'Nếu chu kỳ săn hiện tại thua, tự chuyển sang điểm thấp hơn hoặc về bế quan.', cfg.autoFallbackHunt)}
        </div>
      </section>

      <section class="card span-3">
        <div class="card-head">
          <div><span class="eyebrow">Đan dược</span><h3>Tự luyện &amp; tự dùng</h3></div>
          <span class="tag ${cfg.autoCraft || cfg.autoUse ? 'gold' : ''}">${cfg.autoCraft || cfg.autoUse ? 'Bật' : 'Tắt'}</span>
        </div>
        <div class="pill-grid">
          <div class="pill-block">
            <div class="pill-block-head">
              <div><b>Tự chế tạo</b><small>Chỉ dùng lệnh <code>craft.start</code> chính thức, tôn trọng nguyên liệu, linh thạch và giới hạn tuần.</small></div>
              <span class="tag ${cfg.autoCraft ? 'jade' : ''}">${cfg.autoCraft ? 'Đang bật' : 'Đang tắt'}</span>
            </div>
            ${switchRow('autoCraft', 'Tự luyện đan', 'Tự xếp mẻ vào lò trống khi đủ nguyên liệu. Chọn một công thức cụ thể hoặc để hệ thống tự chọn đan tốt nhất.', cfg.autoCraft)}
            <div class="form-grid" style="margin-top:12px">
              <label class="field">
                <span>Công thức</span>
                <select data-config="craftRecipeId">${selectOptions(recipeOptions, cfg.craftRecipeId || '')}</select>
                <small>${recipeChoices.length} công thức đan dược. “Tự chọn” ưu tiên đan tăng tốc tu vi cao nhất có thể luyện.</small>
              </label>
              <label class="field">
                <span>Số lượng muốn giữ</span>
                <input type="number" min="0" max="9999" step="1" data-config="craftKeepQty" value="${esc(cfg.craftKeepQty ?? 10)}" />
                <small>Không luyện thêm khi trong túi đã có đủ số này. Đặt 0 để lấp đầy lò đang trống.</small>
              </label>
            </div>
            <div class="pill-status">
              <div class="pill-status-line">
                <span>Lò trống <b>${fmt(freeSlots)}</b>/${fmt(crafting.slots)}</span>
                <span>Đang chạy <b>${fmt(crafting.jobs?.length || 0)}</b></span>
                <span>Đã có <b>${previewItem ? `${fmt(previewHave)} ${esc(previewItem.name)}` : '—'}</b></span>
              </div>
              ${previewRecipe ? `<div class="pill-preview">
                <span class="pill-preview-title">${selectedRecipe ? 'Công thức đang chọn' : 'Tự chọn hiện tại'}: <b>${esc(previewRecipe.name)}</b></span>
                <span class="pill-preview-meta">${esc(previewItem?.name || '')} · ${duration(previewRecipe.durationMs)} · ${fmt(previewRecipe.stones)} linh thạch</span>
                <div class="pill-mats">${craftInputSummary}</div>
              </div>` : '<p class="small muted">Chưa có công thức đan nào đủ điều kiện để luyện.</p>'}
            </div>
          </div>

          <div class="pill-block">
            <div class="pill-block-head">
              <div><b>Tự sử dụng</b><small>Chỉ dùng lệnh <code>item.use</code> chính thức. Mặc định ưu tiên đan tăng tốc tu vi tốt nhất đang có.</small></div>
              <span class="tag ${cfg.autoUse ? 'jade' : ''}">${cfg.autoUse ? 'Đang bật' : 'Đang tắt'}</span>
            </div>
            ${switchRow('autoUse', 'Tự dùng đan', 'Tự dùng đan khi buff sắp hết hoặc khi có đan tu vi trực tiếp nếu bật bên dưới.', cfg.autoUse)}
            <div class="switch-list" style="margin-top:6px">
              ${switchRow('autoUseBuffs', 'Đan tăng tốc tu vi', 'Dùng đan cultivation_buff theo thứ tự tốt nhất trước, không vượt quá thời lượng tối đa của game.', cfg.autoUseBuffs)}
              ${switchRow('autoUseExp', 'Đan tu vi trực tiếp', 'Dùng đan cultivation_exp, ưu tiên đan cho nhiều tu vi nhất. Mặc định tắt để tránh tiêu đan sự kiện quý.', cfg.autoUseExp)}
              ${switchRow('autoUseOnlyBest', 'Chỉ dùng loại tốt nhất', 'Khi loại tốt nhất còn hiệu lực, không tiêu các đan thấp hơn. Tắt để dùng lần lượt mọi loại đang có.', cfg.autoUseOnlyBest)}
            </div>
            <div class="form-grid" style="margin-top:12px">
              <label class="field">
                <span>Dùng khi buff còn dưới</span>
                <input type="number" min="0" max="240" step="1" data-config="useThresholdMin" value="${esc(cfg.useThresholdMin ?? 15)}" />
                <small>Phút. Đặt 0 để chỉ dùng khi buff đã hết hẳn.</small>
              </label>
            </div>
            <div class="pill-status">
              ${pillSummary}
              ${expSummary}
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div><span class="eyebrow">Túi đồ</span><h3>Dọn trang bị</h3></div>
          <span class="tag ${cfg.autoSalvage ? 'gold' : ''}">${cfg.autoSalvage ? 'Bật' : 'Tắt'}</span>
        </div>
        ${switchRow('autoSalvage', 'Tự xử lý trang bị rơi', 'Phân giải hoặc bán trang bị dưới ngưỡng phẩm cấp để tránh đầy túi.', cfg.autoSalvage)}
        <div class="form-grid" style="margin-top:12px">
          <label class="field">
            <span>Ngưỡng phẩm</span>
            <select data-config="autoSalvageTier">${selectOptions(salvageTierOptions, cfg.autoSalvageTier)}</select>
          </label>
          <label class="field">
            <span>Cách xử lý</span>
            <select data-config="autoSalvageMode" ${cfg.autoSalvage ? '' : 'disabled'}>${selectOptions(modeOptions, cfg.autoSalvageMode)}</select>
          </label>
        </div>
        <p class="small muted" style="margin-top:10px;line-height:1.55">Tắt tự dọn nếu bạn muốn giữ toàn bộ trang bị rơi để tự đánh giá.</p>
      </section>

      <section class="card span-2">
        <div class="card-head">
          <div><span class="eyebrow">Phần thưởng</span><h3>Tự nhận mốc đã đạt</h3></div>
          <span class="tag gold">${readyDaily + readyWeekly + readyAchv} mốc sẵn sàng</span>
        </div>
        <div class="switch-list" style="margin-top:0">
          ${switchRow('autoQuests', 'Nhiệm vụ chính', 'Nhận thưởng ngay khi nhiệm vụ chuyển sang trạng thái có thể nhận.', cfg.autoQuests)}
          ${switchRow('autoDaily', 'Nhiệm vụ ngày', `Nhận tối đa 4 mốc mỗi ngày. Hiện có ${readyDaily} mốc đã đạt.`, cfg.autoDaily)}
          ${switchRow('autoWeekly', 'Nhiệm vụ tuần', `Nhận các mốc tuần đã đạt. Hiện có ${readyWeekly} mốc.`, cfg.autoWeekly)}
          ${switchRow('autoAchievements', 'Thành tựu', `Nhận thành tựu tích lũy đã đạt. Hiện có ${readyAchv} mốc.`, cfg.autoAchievements)}
          ${switchRow('autoMail', 'Thư có quà', 'Tự nhận tất cả thư còn quà trong hộp thư.', cfg.autoMail)}
          ${switchRow('autoX2Daily', 'Phần mở rộng ngày', 'Nhận gói tài nguyên mở rộng một lần mỗi ngày.', cfg.autoX2Daily)}
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div><span class="eyebrow">Thủ công</span><h3>Chạy ngay</h3></div>
        </div>
        <div class="auto-actions">
          <button class="btn primary wide" data-action="auto-tick">
            <svg><use href="#i-play"/></svg><span>Chạy một vòng tự động</span>
          </button>
          <button class="btn wide" data-action="settle">
            <svg><use href="#i-refresh"/></svg><span>Kết toán tu vi</span>
          </button>
          <button class="btn wide" data-action="apply-activity">
            <svg><use href="#i-map"/></svg><span>Áp dụng hoạt động</span>
          </button>
          <button class="btn ghost wide" data-action="save-auto">
            <svg><use href="#i-save"/></svg><span>Lưu cấu hình</span>
          </button>
          <button class="btn ghost wide" data-action="sync-game-settings">
            <svg><use href="#i-refresh"/></svg><span>Đồng bộ thiết lập từ game</span>
          </button>
        </div>
        <div class="auto-save-note ${app.autoDirty ? 'dirty' : ''}">
          <i class="dot"></i><span>${esc(saveText)}</span>
        </div>
        <p class="small muted" style="margin-top:10px;line-height:1.55">“Chạy một vòng” dùng đúng cấu hình đang lưu; các thay đổi chưa lưu sẽ được lưu trước khi chạy.</p>
      </section>

      <section class="card span-3">
        <div class="card-head">
          <div><span class="eyebrow">Boss khu vực</span><h3>Tự đánh boss đã vượt</h3></div>
          <span class="tag ${cfg.autoBoss ? 'jade' : ''}">${cfg.autoBoss ? 'Đang bật' : 'Đang tắt'}</span>
        </div>
        <div class="pill-block">
          <div class="pill-block-head">
            <div><b>Khiêu chiến tuần tự</b><small>Chỉ dùng lệnh <code>boss.fight</code> chính thức. Đánh lần lượt từng boss của vùng đã hạ lần đầu khi hồi chiêu kết thúc; thua không mất gì.</small></div>
            <span class="tag ${cfg.autoBoss ? 'jade' : ''}">${cfg.autoBoss ? 'Đang bật' : 'Đang tắt'}</span>
          </div>
          ${switchRow('autoBoss', 'Tự đánh boss khu vực', 'Tự khiêu chiến lần lượt các boss đã vượt khi hết hồi chiêu. Có thể ghim một boss nếu muốn tập trung.', cfg.autoBoss)}
          <div class="form-grid" style="margin-top:12px">
            <label class="field">
              <span>Nhịp đánh mỗi boss</span>
              <input type="number" min="0" max="240" step="1" data-config="bossIntervalMin" value="${esc(cfg.bossIntervalMin ?? 10)}" />
              <small>Phút. Đặt 0 để chỉ dựa vào hồi chiêu của game; mặc định 10 phút cho mỗi boss.</small>
            </label>
            <label class="field">
              <span>Chế độ</span>
              <select data-config="bossRegionId">${selectOptions(bossOptions, cfg.bossRegionId || '')}</select>
              <small>${bossEntries.length} boss khu vực đã hạ. Chế độ tuần tự đánh lần lượt tất cả boss đang sẵn sàng.</small>
            </label>
          </div>
          <div class="pill-status">
            <div class="pill-status-line">
              <span>Đã hạ <b>${fmt(bossEntries.length)}</b> boss</span>
              <span>Sẵn sàng <b>${fmt(bossEntries.filter(bossEntryReady).length)}</b></span>
              <span>Kế tiếp <b>${bossTarget ? esc(bossTarget.boss.name) : '—'}</b></span>
            </div>
            ${bossEntries.length
              ? `<ul class="pill-list scroll">${bossStatusRows}</ul>`
              : bossStatusRows}
          </div>
        </div>
      </section>

      <div class="note-card span-3">
        <b>Nguyên tắc an toàn:</b> mini client chỉ gửi các lệnh chính thức như <code>settle</code>, <code>settings.set</code>, <code>activity.set</code>, <code>quest.claim</code>, <code>daily.claim</code>, <code>mail.claimAll</code>, <code>craft.start</code>, <code>item.use</code> và <code>boss.fight</code> tới máy chủ game. Không can thiệp dữ liệu, không gửi mật khẩu đi nơi khác. Vòng tự động chạy trên server Node cục bộ, nên đóng tab trình duyệt vẫn tiếp tục nếu server còn mở. Hãy giữ nhịp hợp lý để không tạo tải bất thường.
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ */
/* Logs                                                               */
/* ------------------------------------------------------------------ */

function renderLogs() {
  const all = [...(app.snapshot?.logs || [])].reverse();
  const filters = [
    ['all', 'Tất cả'],
    ['info', 'Thông tin'],
    ['success', 'Thành công'],
    ['warn', 'Cảnh báo'],
    ['error', 'Lỗi'],
  ];
  const filtered = app.logFilter === 'all' ? all : all.filter((log) => log.level === app.logFilter);
  const count = (level) => level === 'all' ? all.length : all.filter((log) => log.level === level).length;
  return `<div class="logs-view">
    <section class="card">
      <div class="card-head">
        <div><span class="eyebrow">Nhật ký</span><h3>Hoạt động gần đây</h3></div>
        <div class="filter-row">
          ${filters.map(([value, label]) => `<button class="chip ${app.logFilter === value ? 'on' : ''}" data-action="log-filter" data-filter="${value}">${label} <span style="opacity:.55">${count(value)}</span></button>`).join('')}
        </div>
      </div>
      ${filtered.length ? `<div class="log-list">${filtered.map((log) => {
        const level = ['success', 'warn', 'error'].includes(log.level) ? log.level : 'info';
        return `<div class="log-row ${level}">
          <time>${esc(clock(log.at))}</time>
          <i class="log-dot"></i>
          <div class="log-body">
            <b>${esc(log.message)}</b>
            ${log.detail ? `<p>${esc(log.detail)}</p>` : ''}
          </div>
        </div>`;
      }).join('')}</div>` : `<div class="empty log-empty"><svg><use href="#i-logs"/></svg><b>Chưa có hoạt động</b><p>Nhật ký sẽ ghi lại các lần kết toán, đổi hoạt động và nhận thưởng.</p></div>`}
    </section>
  </div>`;
}

/* ------------------------------------------------------------------ */
/* Live bits                                                          */
/* ------------------------------------------------------------------ */

function startTicker() {
  setInterval(updateLiveBits, 1000);
}

function updateLiveBits() {
  $$('[data-live="state-age"]').forEach((el) => {
    el.textContent = timeAgo(app.stateAt);
  });
  const st = state();
  const activity = st?.activity;
  const bar = $('#cycle-bar');
  const text = $('#cycle-text');
  if (!bar || !text || !activity) return;
  const cycleMs = toNumber(activity.cycleMs);
  if (cycleMs <= 0) return;
  const elapsed = Date.now() - app.stateAt;
  const progress = ((toNumber(activity.cycleProgressMs) + elapsed) % cycleMs) / cycleMs * 100;
  bar.style.width = `${progress.toFixed(1)}%`;
  text.textContent = `${progress.toFixed(0)}%`;
}

/* ------------------------------------------------------------------ */
/* Actions                                                            */
/* ------------------------------------------------------------------ */

async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch(path, {
    method,
    headers: body !== undefined ? { 'content-type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await response.json(); } catch { /* ignore */ }
  if (!response.ok || data?.ok === false) {
    const err = new Error(data?.message || data?.errorCode || `HTTP ${response.status}`);
    err.code = data?.errorCode;
    err.status = response.status;
    err.details = data?.details;
    throw err;
  }
  return data || {};
}

async function withBusy(element, fn) {
  if (element?.disabled) return undefined;
  if (element) {
    element.disabled = true;
    element.classList.add('is-busy');
  }
  try {
    return await fn();
  } finally {
    if (element) {
      element.disabled = false;
      element.classList.remove('is-busy');
    }
  }
}

async function command(cmd, payload = {}) {
  const data = await api('/api/command', { method: 'POST', body: { cmd, payload } });
  if (data.state) {
    app.snapshot.state = data.state;
    app.stateAt = Date.now();
  }
  if (data.settle) showSettle(data.settle);
  renderChrome();
  renderView();
  return data;
}

function showSettle(settle) {
  const bits = [];
  const exp = toNumber(settle.expGained);
  if (exp > 0) bits.push(`+${fmt(exp)} tu vi`);
  if (settle.cycles) bits.push(`${fmt(settle.cycles)} chu kỳ`);
  if (settle.layerUps?.length) bits.push(`lên ${settle.layerUps.length} tầng`);
  if (settle.equipment?.length) bits.push(`${settle.equipment.length} trang bị`);
  if (settle.autoSalvaged) bits.push(`tự xử lý ${settle.autoSalvaged} món`);
  if (settle.stopReason) bits.push(`dừng: ${settle.stopReason}`);
  if (bits.length) toast('success', 'Kết toán tu vi', bits.join(' · '));
}

async function refreshState(element) {
  return withBusy(element, async () => {
    const data = await api('/api/state');
    app.snapshot.state = data.state;
    if (data.config) app.snapshot.config = data.config;
    app.stateAt = Date.now();
    if (!app.autoDirty && data.config) app.autoDraft = { ...data.config };
    renderChrome();
    renderView();
    toast('info', 'Đã làm mới trạng thái');
  });
}

async function runTick(element) {
  return withBusy(element, async () => {
    if (app.autoDirty) await saveAuto({ notify: false });
    const data = await api('/api/tick', { method: 'POST' });
    if (data.state) {
      app.snapshot.state = data.state;
      app.stateAt = Date.now();
    }
    if (data.config) {
      app.snapshot.config = data.config;
      if (!app.autoDirty) app.autoDraft = { ...data.config };
    }
    renderChrome();
    renderView();
    toast('success', 'Đã chạy một vòng tự động', 'Kết toán, đồng bộ thiết lập và nhận thưởng theo cấu hình.');
  });
}

async function settleNow(element) {
  return withBusy(element, async () => {
    const data = await command('settle', {});
    if (!data?.settle?.expGained) toast('info', 'Đã kết toán', 'Chưa có tiến độ mới để cộng thêm.');
  });
}

async function applyActivity(element) {
  return withBusy(element, async () => {
    const cfg = ensureAutoDraft();
    const type = cfg.activityType || 'seclusion';
    const payload = { type };
    if (type === 'farm') {
      const targetId = cfg.huntSpotId || bestSpotId();
      if (!targetId) throw new Error('Chưa có điểm săn phù hợp. Hãy mở thêm vùng hoặc chọn điểm khác.');
      payload.targetId = targetId;
    }
    await command('activity.set', payload);
    const spot = payload.targetId ? spotInfo(payload.targetId) : null;
    toast('success', 'Đã đổi hoạt động', spot ? `Săn tại ${spot.name}` : app.meta?.activities?.[type]?.name || type);
  });
}

async function claimOne(cmd, payload, element, successMessage) {
  return withBusy(element, async () => {
    await command(cmd, payload);
    toast('success', successMessage);
  });
}

async function claimReady(kind, element) {
  return withBusy(element, async () => {
    const st = state();
    const periodic = st?.periodic || {};
    const tasks = kind === 'weekly' ? (periodic.weekly || []) : (periodic.achievements || []);
    const ready = tasks.filter((task) => !task.claimed && toNumber(task.current) >= toNumber(task.target));
    if (!ready.length) {
      toast('info', 'Không có mốc nào đạt', 'Hãy tiếp tục tu luyện rồi thử lại.');
      return;
    }
    for (const task of ready) {
      const cmd = kind === 'weekly' ? 'weekly.claim' : 'achievement.claim';
      const payload = kind === 'weekly' ? { taskId: task.id } : { achievementId: task.id };
      await command(cmd, payload);
    }
    toast('success', `Đã nhận ${ready.length} mốc`, kind === 'weekly' ? 'Nhiệm vụ tuần' : 'Thành tựu');
  });
}

async function claimX2(element) {
  return withBusy(element, async () => {
    await command('x2.daily.claim', {});
    toast('success', 'Đã nhận phần mở rộng ngày');
  });
}

async function syncGameSettings(element) {
  return withBusy(element, async () => {
    const data = await api('/api/config/sync', { method: 'POST' });
    app.snapshot.config = data.config;
    app.autoDraft = { ...data.config };
    app.autoDirty = false;
    app.lastSavedAt = Date.now();
    renderChrome();
    renderView();
    toast('success', 'Đã đồng bộ thiết lập từ game', 'Tự lên tầng, dọn trang bị và hoạt động hiện tại đã được đưa vào cấu hình.');
  });
}

async function saveAuto({ notify = false } = {}) {
  clearTimeout(app.autoSaveTimer);
  const cfg = ensureAutoDraft();
  if (cfg.autoSalvage && Number(cfg.autoSalvageTier) === 0) cfg.autoSalvageTier = 1;
  if (Number(cfg.autoSalvageTier) === 0) cfg.autoSalvage = false;
  const seq = app.saveSeq;
  try {
    const data = await api('/api/config', { method: 'POST', body: cfg });
    if (seq === app.saveSeq) {
      app.snapshot.config = data.config;
      app.autoDraft = { ...data.config };
      app.autoDirty = false;
      app.lastSavedAt = Date.now();
    }
    if (notify) toast('success', 'Đã lưu cấu hình tự động', `Nhịp ${duration(data.config.intervalMs)}`);
    renderChrome();
    if (app.view === 'auto') renderView();
  } catch (err) {
    app.autoDirty = true;
    toast('error', 'Không lưu được cấu hình', err.message);
    if (app.view === 'auto') renderView();
  }
}

function scheduleSave() {
  clearTimeout(app.autoSaveTimer);
  app.autoSaveTimer = setTimeout(() => {
    saveAuto({ notify: false });
  }, 650);
}

async function handleLogin(event) {
  event.preventDefault();
  const username = $('#username')?.value.trim() || '';
  const password = $('#password')?.value || '';
  const remember = !!$('#remember')?.checked;
  const errorEl = $('#login-error');
  const button = $('#login-btn');
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  if (!username || password.length < 8) {
    if (errorEl) {
      errorEl.textContent = !username ? 'Nhập tên đăng nhập game.' : 'Mật khẩu cần ít nhất 8 ký tự.';
      errorEl.hidden = false;
    }
    return;
  }
  await withBusy(button, async () => {
    const label = button?.querySelector('span');
    const oldLabel = label?.textContent;
    if (label) label.textContent = 'Đang đăng nhập…';
    try {
      const data = await api('/api/login', { method: 'POST', body: { username, password, remember } });
      app.snapshot = {
        authenticated: true,
        user: data.user,
        state: data.state,
        config: data.config,
        logs: data.logs || [],
        serverTime: Date.now(),
      };
      app.autoDraft = { ...(data.config || {}) };
      app.autoDirty = false;
      app.stateAt = Date.now();
      app.booted = true;
      app.view = 'overview';
      const passwordInput = $('#password');
      if (passwordInput) passwordInput.value = '';
      disconnectSSE();
      connectSSE();
      renderChrome();
      renderView();
      toast('success', 'Đăng nhập thành công', data.user?.username || username);
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Đăng nhập thất bại.';
        errorEl.hidden = false;
      }
    } finally {
      if (label && oldLabel) label.textContent = oldLabel;
    }
  });
}

async function logout() {
  if (!window.confirm('Đăng xuất khỏi phiên game trên máy này?')) return;
  try {
    await api('/api/logout', { method: 'POST', body: {} });
  } catch { /* vẫn xoá phiên cục bộ */ }
  disconnectSSE();
  app.snapshot = {
    authenticated: false,
    user: null,
    state: null,
    config: app.snapshot?.config || null,
    logs: [],
    serverTime: Date.now(),
  };
  app.autoDraft = null;
  app.autoDirty = false;
  app.view = 'overview';
  renderChrome();
  toast('info', 'Đã đăng xuất');
}

function setView(view) {
  if (!VIEW_META[view]) return;
  app.view = view;
  renderView();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

async function handleAction(action, element) {
  switch (action) {
    case 'nav':
      setView(element.dataset.view);
      break;
    case 'refresh':
      await refreshState(element);
      break;
    case 'logout':
      await logout();
      break;
    case 'goto-auto':
      setView('auto');
      break;
    case 'goto-items':
      setView('items');
      break;
    case 'item-filter':
      app.itemFilter = element.dataset.filter || 'all';
      renderView();
      break;
    case 'log-filter':
      app.logFilter = element.dataset.filter || 'all';
      renderView();
      break;
    case 'claim-quest':
      await claimOne('quest.claim', { questId: element.dataset.id }, element, 'Đã nhận thưởng nhiệm vụ');
      break;
    case 'claim-daily':
      await claimOne('daily.claim', { taskId: element.dataset.id }, element, 'Đã nhận nhiệm vụ ngày');
      break;
    case 'claim-weekly':
      await claimOne('weekly.claim', { taskId: element.dataset.id }, element, 'Đã nhận nhiệm vụ tuần');
      break;
    case 'claim-achievement':
      await claimOne('achievement.claim', { achievementId: element.dataset.id }, element, 'Đã nhận thành tựu');
      break;
    case 'claim-weekly-ready':
      await claimReady('weekly', element);
      break;
    case 'claim-achv-ready':
      await claimReady('achievements', element);
      break;
    case 'claim-x2':
      await claimX2(element);
      break;
    case 'save-auto':
      await saveAuto({ notify: true });
      break;
    case 'sync-game-settings':
      await syncGameSettings(element);
      break;
    case 'auto-tick':
      await runTick(element);
      break;
    case 'settle':
      await settleNow(element);
      break;
    case 'apply-activity':
      await applyActivity(element);
      break;
    case 'close-toast': {
      const toastEl = element.closest('.toast');
      if (toastEl) removeToast(toastEl);
      break;
    }
    case 'retry-boot':
      window.location.reload();
      break;
    default:
      break;
  }
}

function captureFocusState() {
  const el = document.activeElement;
  if (!el || !(el instanceof HTMLElement)) return null;
  const selector = el.dataset?.config
    ? `[data-config="${el.dataset.config}"]`
    : el.id
      ? `#${el.id}`
      : null;
  if (!selector) return null;
  let start = null;
  let end = null;
  try {
    start = el.selectionStart;
    end = el.selectionEnd;
  } catch { /* not a text field */ }
  return { selector, start, end, scrollY: window.scrollY };
}

function restoreFocusState(snapshot) {
  if (!snapshot) return;
  const el = document.querySelector(snapshot.selector);
  if (el && typeof el.focus === 'function') {
    el.focus({ preventScroll: true });
    if (snapshot.start != null && typeof el.setSelectionRange === 'function') {
      try { el.setSelectionRange(snapshot.start, snapshot.end ?? snapshot.start); } catch { /* ignore */ }
    }
  }
  if (Math.abs(window.scrollY - snapshot.scrollY) > 2) window.scrollTo(0, snapshot.scrollY);
}

function rerenderPreservingFocus() {
  const snapshot = captureFocusState();
  renderView();
  restoreFocusState(snapshot);
}

const CONFIG_NUMBER_KEYS = new Set([
  'intervalMs', 'autoSalvageTier', 'craftKeepQty', 'useThresholdMin', 'bossIntervalMin',
]);

const AUTO_LAYOUT_KEYS = new Set([
  'enabled', 'intervalMs', 'autoSalvage', 'autoSalvageTier', 'activityType', 'huntSpotId',
  'autoCraft', 'craftRecipeId', 'autoUse', 'autoUseBuffs', 'autoUseExp', 'autoBoss', 'bossRegionId',
]);

function handleConfigChange(element) {
  const key = element.dataset.config;
  if (!key) return;
  const cfg = ensureAutoDraft();
  let value = element.type === 'checkbox' ? element.checked : element.value;
  if (CONFIG_NUMBER_KEYS.has(key)) value = Number(value);
  cfg[key] = value;
  if (key === 'autoSalvage' && value && Number(cfg.autoSalvageTier) === 0) cfg.autoSalvageTier = 1;
  if (key === 'autoSalvageTier') cfg.autoSalvage = Number(value) !== 0;
  app.autoDirty = true;
  app.saveSeq += 1;
  if (app.view === 'auto' && AUTO_LAYOUT_KEYS.has(key)) rerenderPreservingFocus();
  else renderChrome();
  scheduleSave();
}

/* ------------------------------------------------------------------ */
/* Toasts                                                             */
/* ------------------------------------------------------------------ */

let lastToast = { signature: '', at: 0 };

function toast(level, message, detail) {
  const container = $('#toasts');
  if (!container) return;
  const normalized = ['success', 'warn', 'error'].includes(level) ? level : 'info';
  const signature = `${normalized}|${message}|${detail || ''}`;
  const now = Date.now();
  if (signature === lastToast.signature && now - lastToast.at < 5000) return;
  lastToast = { signature, at: now };
  const icon = normalized === 'error' || normalized === 'warn' ? 'i-alert' : normalized === 'success' ? 'i-check' : 'i-spark';
  const el = document.createElement('div');
  el.className = `toast ${normalized}`;
  el.innerHTML = `<span class="toast-icon"><svg><use href="#${icon}"/></svg></span>
    <div class="toast-body"><b>${esc(message)}</b>${detail ? `<span>${esc(detail)}</span>` : ''}</div>
    <button class="toast-close" data-action="close-toast" aria-label="Đóng">×</button>`;
  container.appendChild(el);
  while (container.children.length > 4) container.firstElementChild.remove();
  setTimeout(() => removeToast(el), 4800);
}

function removeToast(element) {
  if (!element || !element.isConnected) return;
  element.classList.add('out');
  setTimeout(() => element.remove(), 230);
}

/* ------------------------------------------------------------------ */
/* Event wiring                                                       */
/* ------------------------------------------------------------------ */

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  event.preventDefault();
  handleAction(target.dataset.action, target).catch((err) => {
    toast('error', 'Thao tác thất bại', err.message);
  });
});

document.addEventListener('change', (event) => {
  const target = event.target.closest('[data-config]');
  if (!target) return;
  handleConfigChange(target);
});

document.addEventListener('input', (event) => {
  if (event.target.id === 'item-search') {
    app.itemQuery = event.target.value;
    renderItemList();
  }
});

const loginForm = $('#login-form');
if (loginForm) loginForm.addEventListener('submit', handleLogin);

boot();
