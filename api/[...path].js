import {
  getOwnedAccount, methodNotAllowed, readJsonBody, requireUser, sendJson, supabaseRest,
} from '../lib/cloud.js';
import { loadGameState, META, persistAccountState, runAccountTick, sendGameCommand } from '../lib/game.js';

const DEFAULT_CONFIG = {
  enabled: false, intervalMs: 60000, autoMinor: true, autoSalvage: false, autoSalvageTier: 0,
  autoSalvageMode: 'salvage', autoActivity: false, activityType: 'seclusion', huntSpotId: '',
  autoQuests: true, autoDaily: true, autoWeekly: false, autoAchievements: false, autoMail: true,
  autoX2Daily: false, autoFallbackHunt: true, autoCraft: false, craftRecipeId: '', craftKeepQty: 10,
  autoUse: false, autoUseBuffs: true, autoUseExp: false, autoUseOnlyBest: true, useThresholdMin: 15,
  autoBoss: false, bossIntervalMin: 10, bossRegionId: '', autoFarm: false, farmHarvest: true,
  farmPlant: true, farmIncludeHabitats: true, farmSeedMode: 'best', farmSeedId: '', farmReserveStones: 0,
};

const COMMANDS = new Set([
  'settle', 'settings.set', 'activity.set', 'quest.claim', 'daily.claim', 'weekly.claim',
  'achievement.claim', 'mail.claimAll', 'x2.daily.claim', 'craft.start', 'item.use',
  'boss.fight', 'field.plant', 'field.harvest', 'field.rush',
]);

function queryValue(req, key) {
  const raw = req.query?.[key];
  return Array.isArray(raw) ? raw[0] : raw;
}

function normalizeLogs(rows) {
  return (rows || []).map((log) => ({ ...log, at: log.at || log.created_at }));
}

async function getAccount(req, user, body = {}) {
  const accountId = body.accountId || queryValue(req, 'accountId') || req.headers['x-game-account'];
  if (!accountId) throw Object.assign(new Error('Chưa chọn tài khoản game.'), { status: 400 });
  return getOwnedAccount(user.id, String(accountId));
}

async function saveConfig(account, ownerId, config) {
  const normalized = { ...DEFAULT_CONFIG, ...(account.config || {}), ...config };
  normalized.intervalMs = Math.max(60000, Math.min(300000, Number(normalized.intervalMs) || 60000));
  normalized.enabled = !!normalized.enabled;
  await supabaseRest('game_accounts', {
    method: 'PATCH', query: `id=eq.${encodeURIComponent(account.id)}&owner_id=eq.${encodeURIComponent(ownerId)}`,
    prefer: 'return=minimal',
    body: {
      config: normalized,
      enabled: normalized.enabled,
      next_run_at: normalized.enabled ? new Date(Date.now() + 60000).toISOString() : null,
      updated_at: new Date().toISOString(),
    },
  });
  return normalized;
}

async function sessionResponse(req, user) {
  const accounts = await supabaseRest('game_accounts', {
    query: `owner_id=eq.${encodeURIComponent(user.id)}&select=id,owner_id,label,game_username,session_ciphertext,session_iv,session_tag,config,automation_data,enabled,next_run_at,last_tick_at,last_error,state_snapshot&order=created_at.asc`,
  });
  const accountId = queryValue(req, 'accountId');
  const selected = accounts?.find((item) => item.id === accountId) || accounts?.[0] || null;
  let state = selected?.state_snapshot || null;
  if (selected) {
    try {
      const loaded = await loadGameState(selected);
      state = loaded.state;
      await persistAccountState(selected.id, state);
    } catch (error) {
      await supabaseRest('game_accounts', {
        method: 'PATCH', query: `id=eq.${encodeURIComponent(selected.id)}`,
        prefer: 'return=minimal', body: { last_error: error.message },
      });
    }
  }
  return {
    authenticated: true,
    user: { id: user.id, email: user.email },
    accounts: (accounts || []).map(({ state_snapshot, session_ciphertext, session_iv, session_tag, owner_id, automation_data, ...item }) => ({
      ...item,
      progress: state_snapshot ? {
        character: state_snapshot.character || null,
        activity: state_snapshot.activity || null,
        cave: state_snapshot.cave ? {
          unlocked: !!state_snapshot.cave.unlocked,
          plots: Number(state_snapshot.cave.plots || 0),
          fields: (state_snapshot.cave.fields || []).map((field) => ({ plot: field.plot, finishAt: field.finishAt })),
        } : null,
        serverNow: state_snapshot.serverNow || null,
      } : null,
    })),
    selectedAccountId: selected?.id || null,
    state,
    config: selected ? { ...DEFAULT_CONFIG, ...(selected.config || {}) } : { ...DEFAULT_CONFIG },
    logs: selected ? normalizeLogs(await supabaseRest('automation_logs', {
      query: `account_id=eq.${encodeURIComponent(selected.id)}&owner_id=eq.${encodeURIComponent(user.id)}&select=id,level,message,detail,created_at&order=created_at.desc&limit=80`,
    })) : [],
    serverTime: Date.now(),
  };
}

export default async function handler(req, res) {
  const routeParts = req.query?.path || [];
  const route = Array.isArray(routeParts) ? routeParts.join('/') : String(routeParts);
  try {
    if (route === 'meta') {
      res.setHeader('cache-control', 'no-cache');
      return sendJson(res, 200, META);
    }
    if (route === 'health') return sendJson(res, 200, { ok: true, platform: 'vercel', time: new Date().toISOString() });

    const user = await requireUser(req);
    if (route === 'session' && req.method === 'GET') return sendJson(res, 200, await sessionResponse(req, user));
    if (route === 'login' && req.method === 'POST') {
      const body = await readJsonBody(req);
      const response = await fetch(`${req.headers['x-forwarded-proto'] || 'https'}://${req.headers.host}/api/accounts`, {
        method: 'POST', headers: { authorization: req.headers.authorization, 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      return sendJson(res, response.status, data);
    }
    if (route === 'logout' && req.method === 'POST') return sendJson(res, 200, { ok: true });
    if (route === 'progress' && req.method === 'GET') {
      const account = await getAccount(req, user);
      const logs = await supabaseRest('automation_logs', {
        query: `account_id=eq.${encodeURIComponent(account.id)}&owner_id=eq.${encodeURIComponent(user.id)}&select=id,level,message,detail,created_at&order=created_at.desc&limit=100`,
      });
      return sendJson(res, 200, { ok: true, logs: normalizeLogs(logs) });
    }

    const body = req.method === 'GET' ? {} : await readJsonBody(req);
    const account = await getAccount(req, user, body);
    if (route === 'state' && req.method === 'GET') {
      const loaded = await loadGameState(account);
      await persistAccountState(account.id, loaded.state, { last_error: null });
      return sendJson(res, 200, { ok: true, state: loaded.state, config: { ...DEFAULT_CONFIG, ...(account.config || {}) } });
    }
    if (route === 'config' && req.method === 'GET') return sendJson(res, 200, { ok: true, config: { ...DEFAULT_CONFIG, ...(account.config || {}) } });
    if (route === 'config' && req.method === 'POST') {
      const config = await saveConfig(account, user.id, body);
      return sendJson(res, 200, { ok: true, config });
    }
    if (route === 'config/sync' && req.method === 'POST') {
      const { state } = await loadGameState(account);
      const config = await saveConfig(account, user.id, {
        autoMinor: !!state.character?.autoMinor,
        autoSalvageTier: Number(state.settings?.autoSalvageTier || 0),
        autoSalvage: Number(state.settings?.autoSalvageTier || 0) > 0,
        autoSalvageMode: state.settings?.autoSalvageMode || 'salvage',
        activityType: state.activity?.type || 'seclusion',
        huntSpotId: state.activity?.targetId || '',
      });
      return sendJson(res, 200, { ok: true, config });
    }
    if (route === 'command' && req.method === 'POST') {
      const command = String(body.cmd || '');
      if (!COMMANDS.has(command)) return sendJson(res, 400, { ok: false, message: 'Lệnh không nằm trong danh sách cho phép.' });
      const { state } = await loadGameState(account);
      const result = await sendGameCommand(account, state, command, body.payload || {});
      const next = result.state || state;
      await persistAccountState(account.id, next);
      return sendJson(res, 200, { ok: true, result: result.result, settle: result.settle, state: next });
    }
    if (route === 'tick' && req.method === 'POST') {
      const result = await runAccountTick(account, { manual: true });
      return sendJson(res, 200, { ok: true, ...result, config: account.config });
    }
    if (route === 'account' && req.method === 'DELETE') {
      await supabaseRest('game_accounts', {
        method: 'DELETE', query: `id=eq.${encodeURIComponent(account.id)}&owner_id=eq.${encodeURIComponent(user.id)}`,
      });
      return sendJson(res, 200, { ok: true });
    }
    if (route === 'account' && req.method === 'PATCH') {
      const label = String(body.label || '').trim().slice(0, 48);
      if (!label) return sendJson(res, 400, { ok: false, message: 'Tên hiển thị không được để trống.' });
      await supabaseRest('game_accounts', {
        method: 'PATCH', query: `id=eq.${encodeURIComponent(account.id)}&owner_id=eq.${encodeURIComponent(user.id)}`,
        prefer: 'return=minimal', body: { label, updated_at: new Date().toISOString() },
      });
      return sendJson(res, 200, { ok: true, label });
    }
    return sendJson(res, 404, { ok: false, message: 'Không tìm thấy API.' });
  } catch (error) {
    return sendJson(res, error.status || 500, { ok: false, errorCode: error.code || 'CLOUD_API_ERROR', message: error.message || 'Lỗi máy chủ.' });
  }
}
