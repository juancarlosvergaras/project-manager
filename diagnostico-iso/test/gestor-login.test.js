// Validación delegada: un gestor simulado con /api/login y /api/sesion.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 4600 + Math.floor(Math.random() * 300);
const GPORT = PORT + 1;
const base = `http://127.0.0.1:${PORT}`;
let proc, gestor, cookie = '';

async function call(path, { method = 'GET', body } = {}) {
  const r = await fetch(base + path, { method, headers: { 'Content-Type': 'application/json', Cookie: cookie }, body: body ? JSON.stringify(body) : undefined });
  const sc = r.headers.get('set-cookie'); if (sc) cookie = sc.split(';')[0];
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

before(async () => {
  // Gestor simulado al estilo de gestor.proyectoia.org: campos "correo"/"clave", cookie de sesión y perfil en /api/sesion
  gestor = createServer((req, res) => {
    let data = ''; req.on('data', c => data += c); req.on('end', () => {
      if (req.method === 'POST' && req.url === '/api/login') {
        const b = JSON.parse(data || '{}');
        if (b.correo === 'admin@mintic1519.local' && b.clave === 'clave-gestor') {
          res.writeHead(200, { 'Content-Type': 'application/json', 'Set-Cookie': 'sesion_gestor=abc123; Path=/; HttpOnly' });
          return res.end(JSON.stringify({ ok: true }));
        }
        res.writeHead(401, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ error: 'Credenciales inválidas' }));
      }
      if (req.url === '/api/usuarios') {
        if (!(req.headers.cookie || '').includes('sesion_gestor=abc123')) { res.writeHead(401); return res.end(); }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ usuarios: [
          { id: 7, usuario: 'admin@mintic1519.local', nombre: 'Juan Carlos Vergara', rol: 'admin', cargo: 'Dirección' },
          { id: 8, usuario: 'ana@mintic1519.local', nombre: 'Ana Pérez', rol: 'consulta', cargo: 'Calidad', activo: true },
          { id: 9, usuario: 'luis@mintic1519.local', nombre: 'Luis Gómez', rol: 'gestor', activo: false },
        ] }));
      }
      if (req.url === '/api/sesion') {
        if ((req.headers.cookie || '').includes('sesion_gestor=abc123')) {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          return res.end(JSON.stringify({ usuario: { id: 7, correo: 'admin@mintic1519.local', nombre: 'Juan Carlos Vergara', rol: 'admin' } }));
        }
        res.writeHead(401); return res.end();
      }
      res.writeHead(404); res.end();
    });
  }).listen(GPORT);
  proc = spawn(process.execPath, ['--no-warnings=ExperimentalWarning', 'server/index.js'], { cwd: root, env: { ...process.env, PORT: String(PORT), AUTH_MODE: 'mixto', DB_PATH: ':memory:', SESSION_SECRET: 'prueba', ADMIN_PASSWORD: 'clave-prueba-123', GESTOR_LOGIN_API: `http://127.0.0.1:${GPORT}/api/login`, GESTOR_SESION_API: `http://127.0.0.1:${GPORT}/api/sesion`, GESTOR_USUARIOS_API: `http://127.0.0.1:${GPORT}/api/usuarios` }, stdio: ['ignore', 'pipe', 'pipe'] });
  await new Promise((res, rej) => { proc.stdout.on('data', d => { if (String(d).includes('escuchando')) res(); }); proc.stderr.on('data', d => process.stderr.write(d)); proc.on('exit', c => rej(new Error('servidor terminó ' + c))); });
});
after(() => { proc.kill(); gestor.close(); });

test('un usuario del gestor entra con su correo y contraseña y hereda su rol', async () => {
  const cfg = await call('/api/config');
  assert.equal(cfg.data.auth.credenciales_gestor, true);
  const mal = await call('/api/auth/local/login', { method: 'POST', body: { email: 'admin@mintic1519.local', password: 'otra' } });
  assert.equal(mal.status, 401);
  const ok = await call('/api/auth/local/login', { method: 'POST', body: { email: 'admin@mintic1519.local', password: 'clave-gestor' } });
  assert.equal(ok.status, 200);
  assert.equal(ok.data.usuario.origen, 'gestor');
  assert.equal(ok.data.usuario.rol, 'admin');
  assert.equal(ok.data.usuario.nombre, 'Juan Carlos Vergara');
  const orgs = await call('/api/organizaciones');
  assert.equal(orgs.status, 200);
  assert.ok(orgs.data.organizaciones.some(o => o.sigla === 'HUC'));
});

test('trae el listado de usuarios del gestor con la sesión del administrador', async () => {
  const r = await call('/api/usuarios/sincronizar', { method: 'POST' });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.equal(r.data.total, 3); assert.equal(r.data.creados, 2); assert.equal(r.data.actualizados, 1);
  const { data } = await call('/api/usuarios');
  const ana = data.usuarios.find(u => u.email === 'ana@mintic1519.local');
  assert.ok(ana); assert.equal(ana.rol, 'usuario'); assert.equal(ana.cargo, 'Calidad'); assert.equal(ana.origen, 'gestor');
  const luis = data.usuarios.find(u => u.email === 'luis@mintic1519.local');
  assert.equal(luis.rol, 'consultor'); assert.equal(luis.activo, 0);
  assert.equal(data.puede_sincronizar, true);
});

test('el administrador local sigue funcionando junto al gestor', async () => {
  cookie = '';
  const ok = await call('/api/auth/local/login', { method: 'POST', body: { email: 'admin@proyectoia.org', password: 'clave-prueba-123' } });
  assert.equal(ok.status, 200); assert.equal(ok.data.usuario.origen, 'local');
});
