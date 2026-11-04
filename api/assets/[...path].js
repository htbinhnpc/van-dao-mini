const GAME_ORIGIN = process.env.GAME_ORIGIN || 'https://vandaonghichmenh.hongvan.net:60010';

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('allow', 'GET, HEAD');
    res.statusCode = 405;
    return res.end('Method not allowed');
  }
  const segments = Array.isArray(req.query?.path) ? req.query.path : [req.query?.path || ''];
  const assetPath = segments.join('/');
  if (!assetPath || assetPath.includes('..') || assetPath.includes('\\')) {
    res.statusCode = 400;
    return res.end('Bad request');
  }
  try {
    const upstream = await fetch(`${GAME_ORIGIN}/assets/${assetPath}`, {
      headers: { referer: `${GAME_ORIGIN}/`, 'user-agent': 'VanDaoMiniClient/1.0' },
      signal: AbortSignal.timeout(20000),
    });
    if (!upstream.ok) {
      res.statusCode = upstream.status;
      return res.end('Asset not found');
    }
    res.statusCode = 200;
    res.setHeader('content-type', upstream.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('cache-control', 'public, max-age=86400, s-maxage=604800');
    if (req.method === 'HEAD') return res.end();
    res.end(Buffer.from(await upstream.arrayBuffer()));
  } catch {
    res.statusCode = 502;
    res.end('Asset proxy error');
  }
}
