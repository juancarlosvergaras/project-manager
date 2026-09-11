// Servidor HTTP de diagnosticoiso.proyectoia.org (sin dependencias externas).
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { join, extname, normalize, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDb } from './db.js';
import { api } from './routes.js';
import { HttpError } from './router.js';
import * as auth from './auth.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, '..', 'public');
const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || '0.0.0.0';
const BASE_URL = process.env.BASE_URL || `http://localhost:${PORT}`;

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2' };

// Versión desplegada (visible en el menú y en /api/config) para verificar qué código está corriendo.
import { execSync } from 'node:child_process';
export const VERSION = (() => {
  let v = '1.2.0';
  try { v = JSON.parse(readFileSync(join(__dirname, '..', 'package.json'), 'utf8')).version; } catch { }
  let commit = process.env.APP_COMMIT || '';
  if (!commit) { try { commit = execSync('git rev-parse --short HEAD', { cwd: __dirname, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch { } }
  return v + (commit ? ' · ' + commit : '');
})();
process.env.APP_VERSION = VERSION;
openDb();
auth.asegurarAdminInicial();
auth.programarSincronizacion();

function sendJson(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(obj));
}

async function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', c => { data += c; if (data.length > 2_000_000) { reject(new HttpError(413, 'Cuerpo demasiado grande')); req.destroy(); } });
    req.on('end', () => { try { resolve(data ? JSON.parse(data) : {}); } catch { reject(new HttpError(400, 'JSON inválido')); } });
    req.on('error', reject);
  });
}

async function serveStatic(res, path, req) {
  res.req = req;
  let rel = normalize(decodeURIComponent(path)).replace(/^(\.\.[\/\\])+/, '');
  if (rel === '/' || rel === '') rel = '/index.html';
  const file = join(PUBLIC_DIR, rel);
  if (!file.startsWith(PUBLIC_DIR)) { res.writeHead(403); return res.end(); }
  try {
    const s = await stat(file);
    if (!s.isFile()) throw new Error('nofile');
    const ext = extname(file);
    // HTML, JS y CSS se revalidan siempre (Last-Modified + 304) para que cada despliegue llegue al celular sin vaciar caché.
    const revalidar = ['.html', '.js', '.css', '.webmanifest'].includes(ext);
    const lastMod = s.mtime.toUTCString();
    if (revalidar && res.req?.headers['if-modified-since'] === lastMod) { res.writeHead(304); return res.end(); }
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Last-Modified': lastMod, 'Cache-Control': revalidar ? 'no-cache' : 'public, max-age=86400' });
    res.end(await readFile(file));
  } catch {
    // SPA: cualquier ruta desconocida devuelve index.html
    res.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-cache' });
    res.end(await readFile(join(PUBLIC_DIR, 'index.html')));
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, BASE_URL);
  const path = url.pathname;
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'same-origin');
  try {
    // Flujo SSO con gestor.proyectoia.org
    if (path === '/auth/gestor/login') {
      const retorno = new URL('/auth/gestor/callback', BASE_URL);
      if (url.searchParams.get('next')) retorno.searchParams.set('next', url.searchParams.get('next'));
      res.writeHead(302, { Location: auth.urlLoginGestor(retorno.toString()) }); return res.end();
    }
    if (path === '/auth/gestor/callback') {
      const token = url.searchParams.get(process.env.GESTOR_TOKEN_PARAM || 'token') || url.searchParams.get('access_token') || url.searchParams.get('jwt');
      let u;
      if (token) u = await auth.autenticarConGestor({ token });
      else u = await auth.intentarSsoPorCookie(req);
      if (!u) throw new HttpError(401, 'No se recibió una credencial válida de ' + auth.authConfig.gestorNombre);
      auth.crearSesion(res, req, u.id);
      const next = url.searchParams.get('next');
      res.writeHead(302, { Location: next && next.startsWith('/') ? next : '/#/' }); return res.end();
    }

    if (path.startsWith('/api/')) {
      const m = api.match(req.method, path);
      if (!m) return sendJson(res, 404, { error: 'Ruta no encontrada' });
      let usuario = auth.usuarioActual(req);
      if (!usuario) { usuario = await auth.intentarSsoPorCookie(req); if (usuario) { auth.crearSesion(res, req, usuario.id); const { password_hash, ...u } = usuario; usuario = u; } }
      const ctx = {
        req, res, params: m.params, query: Object.fromEntries(url.searchParams), usuario,
        body: () => readBody(req),
        json: (obj, status = 200) => sendJson(res, status, obj),
      };
      for (const h of m.handlers) { await h(ctx); if (res.writableEnded) break; }
      if (!res.writableEnded) sendJson(res, 204, {});
      return;
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); return res.end(); }
    await serveStatic(res, path, req);
  } catch (e) {
    if (e instanceof HttpError) {
      if (path.startsWith('/api/')) return sendJson(res, e.status, { error: e.message, ...e.extra });
      res.writeHead(e.status, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(`<!doctype html><meta charset="utf-8"><title>Error</title><p style="font-family:sans-serif;padding:2rem">${e.message}. <a href="/">Volver</a></p>`);
    }
    console.error(e);
    if (!res.headersSent) sendJson(res, 500, { error: 'Error interno del servidor' });
    else res.end();
  }
});

server.listen(PORT, HOST, () => console.log(`Diagnóstico ISO 9001 ${VERSION} escuchando en http://${HOST}:${PORT} (modo de autenticación: ${auth.authConfig.mode})`));

// Limpieza periódica de sesiones vencidas
setInterval(() => { try { openDb().prepare("DELETE FROM sesiones WHERE expira_en < datetime('now')").run(); } catch {} }, 3600_000).unref();
