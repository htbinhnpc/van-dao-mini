import { sendJson, supabaseRest } from '../lib/cloud.js';
import { runAccountTick } from '../lib/game.js';

function authorized(req) {
  const expected = process.env.CRON_SECRET;
  if (!expected) return false;
  const bearer = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const vercelCron = req.headers['x-vercel-cron'] === '1';
  return bearer === expected || (vercelCron && req.headers['x-cron-secret'] === expected);
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'POST') {
    res.setHeader('allow', 'GET, POST');
    return sendJson(res, 405, { ok: false, message: 'Phương thức không hỗ trợ.' });
  }
  if (!authorized(req)) return sendJson(res, 401, { ok: false, message: 'Cron secret không hợp lệ.' });

  const now = new Date();
  const nowIso = now.toISOString();
  try {
    const due = await supabaseRest('game_accounts', {
      query: `enabled=eq.true&next_run_at=lte.${encodeURIComponent(nowIso)}&select=id,owner_id,label,game_username,session_ciphertext,session_iv,session_tag,config,automation_data,enabled,next_run_at,lease_until,state_snapshot&order=next_run_at.asc&limit=30`,
    });
    const processed = [];
    const startedAt = Date.now();

    for (const candidate of due || []) {
      // Stop before Vercel's function deadline. Unprocessed rows remain due for
      // the next minute's cron invocation.
      if (Date.now() - startedAt > 45000) break;
      const leaseFilter = candidate.lease_until
        ? `lease_until=lt.${encodeURIComponent(nowIso)}`
        : 'lease_until=is.null';
      const leased = await supabaseRest('game_accounts', {
        method: 'PATCH',
        query: `id=eq.${encodeURIComponent(candidate.id)}&enabled=eq.true&${leaseFilter}&select=id`,
        prefer: 'return=representation',
        body: { lease_until: new Date(Date.now() + 55000).toISOString() },
      });
      if (!leased?.length) continue;

      try {
        await runAccountTick(candidate);
        const nextRun = new Date(Date.now() + Math.max(60000, Number(candidate.config?.intervalMs) || 60000));
        await supabaseRest('game_accounts', {
          method: 'PATCH', query: `id=eq.${encodeURIComponent(candidate.id)}`,
          prefer: 'return=minimal',
          body: {
            next_run_at: nextRun.toISOString(), lease_until: null,
            last_tick_at: new Date().toISOString(), last_error: null,
            updated_at: new Date().toISOString(),
          },
        });
        processed.push({ accountId: candidate.id, ok: true });
      } catch (error) {
        await supabaseRest('game_accounts', {
          method: 'PATCH', query: `id=eq.${encodeURIComponent(candidate.id)}`,
          prefer: 'return=minimal',
          body: {
            next_run_at: new Date(Date.now() + 60000).toISOString(),
            lease_until: null, last_error: String(error.message || error).slice(0, 500),
            updated_at: new Date().toISOString(),
          },
        });
        try {
          await supabaseRest('automation_logs', {
            method: 'POST', prefer: 'return=minimal',
            body: {
              owner_id: candidate.owner_id, account_id: candidate.id,
              level: 'error', message: 'Vòng tự động lỗi', detail: String(error.message || error).slice(0, 500),
            },
          });
        } catch { /* preserve the per-account failure result */ }
        processed.push({ accountId: candidate.id, ok: false, error: String(error.message || error) });
      }
    }

    return sendJson(res, 200, {
      ok: true,
      scanned: due?.length || 0,
      processed,
      elapsedMs: Date.now() - startedAt,
      at: new Date().toISOString(),
    });
  } catch (error) {
    return sendJson(res, 500, { ok: false, message: error.message || 'Không chạy được cron.' });
  }
}
