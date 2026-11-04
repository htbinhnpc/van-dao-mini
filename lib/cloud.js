import crypto from 'node:crypto';

const env = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`Thiếu biến môi trường ${name}.`);
  return value;
};

function supabaseHeaders(extra = {}) {
  const serviceKey = env('SUPABASE_SERVICE_ROLE_KEY');
  return {
    apikey: serviceKey,
    authorization: `Bearer ${serviceKey}`,
    'content-type': 'application/json',
    ...extra,
  };
}

export async function supabaseRest(table, { method = 'GET', query = '', body, prefer } = {}) {
  const base = env('SUPABASE_URL').replace(/\/$/, '');
  const headers = supabaseHeaders(prefer ? { prefer } : {});
  const response = await fetch(`${base}/rest/v1/${table}${query ? `?${query}` : ''}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(20000),
  });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const error = new Error(data?.message || data?.hint || `Supabase trả HTTP ${response.status}.`);
    error.status = response.status;
    throw error;
  }
  return data;
}

export async function requireUser(req) {
  const token = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '').trim();
  if (!token) throw Object.assign(new Error('Cần đăng nhập.'), { status: 401 });
  const response = await fetch(`${env('SUPABASE_URL').replace(/\/$/, '')}/auth/v1/user`, {
    headers: {
      apikey: env('SUPABASE_ANON_KEY'),
      authorization: `Bearer ${token}`,
    },
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw Object.assign(new Error('Phiên đăng nhập đã hết hạn.'), { status: 401 });
  return response.json();
}

function encryptionKey() {
  const key = Buffer.from(env('APP_ENCRYPTION_KEY'), 'hex');
  if (key.length !== 32) throw new Error('APP_ENCRYPTION_KEY phải là 64 ký tự hex (32 byte).');
  return key;
}

export function encryptSecret(value) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(String(value), 'utf8'), cipher.final()]);
  return {
    session_iv: iv.toString('base64url'),
    session_ciphertext: ciphertext.toString('base64url'),
    session_tag: cipher.getAuthTag().toString('base64url'),
  };
}

export function decryptSecret(row) {
  const decipher = crypto.createDecipheriv(
    'aes-256-gcm',
    encryptionKey(),
    Buffer.from(row.session_iv, 'base64url'),
  );
  decipher.setAuthTag(Buffer.from(row.session_tag, 'base64url'));
  return Buffer.concat([
    decipher.update(Buffer.from(row.session_ciphertext, 'base64url')),
    decipher.final(),
  ]).toString('utf8');
}

export async function getOwnedAccount(ownerId, accountId) {
  const rows = await supabaseRest('game_accounts', {
    query: `id=eq.${encodeURIComponent(accountId)}&owner_id=eq.${encodeURIComponent(ownerId)}&select=*`,
  });
  if (!rows?.length) throw Object.assign(new Error('Không tìm thấy tài khoản game.'), { status: 404 });
  return rows[0];
}

export function sendJson(res, status, data) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('cache-control', 'no-store');
  res.end(JSON.stringify(data));
}

export function methodNotAllowed(res, methods) {
  res.setHeader('allow', methods.join(', '));
  sendJson(res, 405, { ok: false, message: 'Phương thức không được hỗ trợ.' });
}

export function readJsonBody(req) {
  if (req.body && typeof req.body === 'object') return Promise.resolve(req.body);
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 100_000) reject(Object.assign(new Error('Yêu cầu quá lớn.'), { status: 413 }));
    });
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); }
      catch { reject(Object.assign(new Error('JSON không hợp lệ.'), { status: 400 })); }
    });
    req.on('error', reject);
  });
}
