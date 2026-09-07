// Aplicacion simulada que representa a una aplicacion existente (Solucion Automatizada o Catalogo de IA).
// Tiene su propio ingreso, sus propias sesiones y monta el conector de referencia. Solo para pruebas.
import http from 'node:http';
import crypto from 'node:crypto';
import { crearConector } from '../../conectores/referencia-node/observatorio-conector.js';

const [, , puerto = '8101', nombre = 'Aplicación simulada', secreto = 'secreto-de-prueba'] = process.argv;

// Usuarios de la aplicacion, con clave guardada como hash (como haria la aplicacion real).
const hash = (c, s) => crypto.scryptSync(c, s, 32).toString('hex');
const usuarios = [
  { id: 1, usuario: 'jmartinez', correo: 'jmartinez@cartagena.gov.co', nombre: 'Julián Martínez', rol: 'funcionario', sal: 'a1', clave_hash: hash('Clave.2026', 'a1'), fecha: '2026-03-04' },
  { id: 2, usuario: 'jvergaras', correo: 'jvergaras@unicartagena.edu.co', nombre: 'Juan Carlos Vergara', rol: 'administrador', sal: 'b2', clave_hash: hash('Admin.2026', 'b2'), fecha: '2026-01-12' },
  { id: 3, usuario: 'analista', correo: 'analista@entidad.gov.co', nombre: 'Ana Núñez', rol: 'analista', sal: 'c3', clave_hash: hash('Ana.2026', 'c3'), fecha: '2026-05-21' },
];
const registros = Array.from({ length: 37 }, (_, i) => ({ id: i + 1, entidad: ['Alcaldía de Cartagena', 'Gobernación de Bolívar', 'Ministerio de Salud', 'Alcaldía de Montería'][i % 4], estado: i % 3 ? 'completo' : 'en_curso', fecha: `2026-0${1 + (i % 8)}-${String(1 + (i % 27)).padStart(2, '0')}`, puntaje: Math.round(15 + (i * 7) % 35) / 10 }));
const sesiones = new Map();

const conector = crearConector({
  activo: process.env.OBS_CONECTOR_ACTIVO === '1',
  secreto,
  buscarUsuario: async (u) => usuarios.find((x) => x.usuario === u.toLowerCase() || x.correo === u.toLowerCase()) || null,
  verificarClave: async (r, clave) => crypto.timingSafeEqual(Buffer.from(hash(clave, r.sal)), Buffer.from(r.clave_hash)),
  buscarPorIdentidad: async ({ id_externo, correo }) => usuarios.find((x) => String(x.id) === String(id_externo)) || usuarios.find((x) => x.correo === correo) || null,
  iniciarSesion: async (req, res, r) => { const sid = crypto.randomBytes(16).toString('hex'); sesiones.set(sid, r.id); res.setHeader('Set-Cookie', `app_sesion=${sid}; Path=/; HttpOnly`); },
  urlInicio: '/',
  conjuntos: {
    usuarios: { descripcion: 'Usuarios registrados', consultar: async () => usuarios.map(({ id, entidad, rol, fecha }) => ({ id, rol, fecha })) },
    registros: { descripcion: nombre.includes('Catálogo') ? 'Fichas del catálogo' : 'Diagnósticos realizados', consultar: async () => registros },
  },
});

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://local');
  if (url.pathname === '/observatorio-conector') return conector(req, res);
  const sid = /app_sesion=([a-f0-9]+)/.exec(req.headers.cookie || '')?.[1];
  const uid = sid && sesiones.get(sid);
  const u = usuarios.find((x) => x.id === uid);
  if (url.pathname === '/login' && req.method === 'POST') {
    let d = ''; for await (const c of req) d += c; const f = new URLSearchParams(d);
    const r = usuarios.find((x) => x.usuario === f.get('usuario'));
    if (r && hash(f.get('clave') || '', r.sal) === r.clave_hash) { const s = crypto.randomBytes(16).toString('hex'); sesiones.set(s, r.id); res.writeHead(303, { Location: '/', 'Set-Cookie': `app_sesion=${s}; Path=/; HttpOnly` }); return res.end(); }
    res.writeHead(401, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end('<h1>Clave incorrecta</h1>');
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  if (u) return res.end(`<!doctype html><title>${nombre}</title><h1>${nombre}</h1><p>Sesión de: ${u.nombre} (${u.usuario})</p><p>Esta es la aplicación existente funcionando de forma independiente.</p>`);
  res.end(`<!doctype html><title>${nombre}</title><h1>${nombre}</h1><p>Sin sesión.</p><form method="post" action="/login"><input name="usuario"><input name="clave" type="password"><button>Ingresar</button></form>`);
}).listen(Number(puerto), () => console.log(`${nombre} en http://127.0.0.1:${puerto} (conector ${process.env.OBS_CONECTOR_ACTIVO === '1' ? 'activo' : 'apagado'})`));
