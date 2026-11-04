import {
  encryptSecret, methodNotAllowed, readJsonBody, requireUser, sendJson, supabaseRest,
} from '../lib/cloud.js';

const GAME_ORIGIN = process.env.GAME_ORIGIN || 'https://vandaonghichmenh.hongvan.net:60010';

export default async function handler(req, res) {
  try {
    const user = await requireUser(req);
    if (req.method === 'GET') {
      const rows = await supabaseRest('game_accounts', {
        query: `owner_id=eq.${encodeURIComponent(user.id)}&select=id,label,game_username,config,enabled,next_run_at,state_snapshot,last_tick_at,last_error,created_at&order=created_at.asc`,
      });
      return sendJson(res, 200, { ok: true, accounts: rows || [] });
    }
    if (req.method !== 'POST') return methodNotAllowed(res, ['GET', 'POST']);

    const body = await readJsonBody(req);
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    const label = String(body.label || username).trim().slice(0, 48);
    if (!/^[a-zA-Z0-9_]{3,24}$/.test(username)) {
      return sendJson(res, 400, { ok: false, message: 'Tên tài khoản game không hợp lệ.' });
    }
    if (password.length < 8) return sendJson(res, 400, { ok: false, message: 'Mật khẩu game không hợp lệ.' });

    const response = await fetch(`${GAME_ORIGIN}/api/auth/login`, {
      method: 'POST',
      headers: {
        origin: GAME_ORIGIN,
        referer: `${GAME_ORIGIN}/`,
        'content-type': 'application/json',
        'user-agent': 'VanDaoMiniClient/1.0',
      },
      body: JSON.stringify({ username, password, remember: true }),
      signal: AbortSignal.timeout(25000),
    });
    const text = await response.text();
    let result;
    try { result = JSON.parse(text); } catch { result = {}; }
    if (!response.ok || result?.ok === false) {
      return sendJson(res, response.status || 400, {
        ok: false,
        message: result?.message || result?.errorCode || 'Không đăng nhập được vào game.',
      });
    }
    const setCookies = typeof response.headers.getSetCookie === 'function'
      ? response.headers.getSetCookie()
      : [response.headers.get('set-cookie')].filter(Boolean);
    const cookie = setCookies.map((value) => String(value).split(';')[0]).find((value) => value.startsWith('vd_sid='));
    if (!cookie) return sendJson(res, 502, { ok: false, message: 'Máy chủ game không cấp phiên đăng nhập.' });

    const stateResponse = await fetch(`${GAME_ORIGIN}/api/state`, {
      headers: { origin: GAME_ORIGIN, referer: `${GAME_ORIGIN}/`, cookie, 'user-agent': 'VanDaoMiniClient/1.0' },
      signal: AbortSignal.timeout(20000),
    });
    const statePayload = await stateResponse.json().catch(() => ({}));
    if (!stateResponse.ok || !statePayload.state) {
      return sendJson(res, 502, { ok: false, message: statePayload.message || 'Không tải được trạng thái game sau đăng nhập.' });
    }

    const encrypted = encryptSecret(cookie);
    const defaultConfig = {
      enabled: false, intervalMs: 60000, autoMinor: !!statePayload.state.character?.autoMinor,
      autoSalvage: Number(statePayload.state.settings?.autoSalvageTier || 0) > 0,
      autoSalvageTier: Number(statePayload.state.settings?.autoSalvageTier || 0),
      autoSalvageMode: statePayload.state.settings?.autoSalvageMode || 'salvage',
      autoActivity: false, activityType: statePayload.state.activity?.type || 'seclusion',
      huntSpotId: statePayload.state.activity?.targetId || '', autoQuests: true, autoDaily: true,
      autoWeekly: false, autoAchievements: false, autoMail: true, autoX2Daily: false,
      autoFallbackHunt: true, autoCraft: false, craftRecipeId: '', craftKeepQty: 10,
      autoUse: false, autoUseBuffs: true, autoUseExp: false, autoUseOnlyBest: true,
      useThresholdMin: 15, autoBoss: false, bossIntervalMin: 10, bossRegionId: '',
      autoFarm: false, farmHarvest: true, farmPlant: true, farmIncludeHabitats: true,
      farmSeedMode: 'best', farmSeedId: '', farmReserveStones: 0,
    };
    const existing = await supabaseRest('game_accounts', {
      query: `owner_id=eq.${encodeURIComponent(user.id)}&game_username=eq.${encodeURIComponent(username)}&select=id&limit=1`,
    });
    const rows = existing?.length
      ? await supabaseRest('game_accounts', {
        method: 'PATCH',
        query: `owner_id=eq.${encodeURIComponent(user.id)}&game_username=eq.${encodeURIComponent(username)}&select=id,label,game_username,config,enabled`,
        prefer: 'return=representation',
        body: { label: label || username, state_snapshot: statePayload.state, ...encrypted, last_error: null, updated_at: new Date().toISOString() },
      })
      : await supabaseRest('game_accounts', {
        method: 'POST',
        query: 'select=id,label,game_username,config,enabled',
        prefer: 'return=representation',
        body: {
          owner_id: user.id,
          label: label || username,
          game_username: username,
          config: defaultConfig,
          state_snapshot: statePayload.state,
          ...encrypted,
        },
      });
    return sendJson(res, 201, { ok: true, account: rows?.[0] || null });
  } catch (error) {
    return sendJson(res, error.status || 500, { ok: false, message: error.message || 'Lỗi máy chủ.' });
  }
}
