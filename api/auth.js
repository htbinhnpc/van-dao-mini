import { methodNotAllowed, readJsonBody, sendJson } from '../lib/cloud.js';

export default async function handler(req, res) {
  if (req.method === 'DELETE') {
    try {
      const token = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '').trim();
      if (token) await fetch(`${process.env.SUPABASE_URL.replace(/\/$/, '')}/auth/v1/logout`, {
        method: 'POST',
        headers: { apikey: process.env.SUPABASE_ANON_KEY, authorization: `Bearer ${token}` },
      });
      return sendJson(res, 200, { ok: true });
    } catch (error) {
      return sendJson(res, 500, { ok: false, message: error.message || 'Không đăng xuất được.' });
    }
  }
  if (req.method !== 'POST') return methodNotAllowed(res, ['POST']);
  try {
    const body = await readJsonBody(req);
    const action = body.action === 'signup' ? 'signup'
      : body.action === 'refresh' ? 'token?grant_type=refresh_token'
        : 'token?grant_type=password';
    const url = `${process.env.SUPABASE_URL.replace(/\/$/, '')}/auth/v1/${action === 'signup' ? 'signup' : action}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { apikey: process.env.SUPABASE_ANON_KEY, 'content-type': 'application/json' },
      body: JSON.stringify(body.action === 'refresh'
        ? { refresh_token: body.refresh_token }
        : { email: body.email, password: body.password }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) return sendJson(res, response.status, { ok: false, message: data.msg || data.message || data.error_description || data.error || 'Không đăng nhập được.' });
    return sendJson(res, 200, { ok: true, session: data });
  } catch (error) {
    return sendJson(res, error.status || 500, { ok: false, message: error.message || 'Lỗi máy chủ.' });
  }
}
