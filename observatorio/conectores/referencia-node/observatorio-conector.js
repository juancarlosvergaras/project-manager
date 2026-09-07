// Conector del Observatorio para aplicaciones Node.js. Archivo unico, opcional y apagado por defecto.
// La aplicacion sigue funcionando igual con o sin este archivo. Para retirarlo basta con dejar de montarlo.
//
// Uso (Express o http nativo):
//   import { crearConector } from './observatorio-conector.js';
//   const conector = crearConector({
//     activo: process.env.OBS_CONECTOR_ACTIVO === '1',
//     secreto: process.env.OBS_CONECTOR_SECRETO,
//     buscarUsuario: async (usuario) => ({ id, usuario, correo, nombre, rol, clave_hash }) | null,
//     verificarClave: async (registro, clave) => true | false,
//     buscarPorIdentidad: async ({ id_externo, correo }) => registro | null,
//     iniciarSesion: async (req, res, registro) => { /* crea la sesion local como lo hace el login normal */ },
//     urlInicio: '/',
//     conjuntos: { usuarios: { descripcion: 'Usuarios registrados', consultar: async () => [ {...} ] } },
//   });
//   app.all('/observatorio-conector', conector);       // Express
//   // o en http nativo: if (url.pathname === '/observatorio-conector') return conector(req, res);
import crypto from 'node:crypto';

const VERSION = '1.0';
const TOLERANCIA_SEG = 300;

export function crearConector(op) {
  const noncesVistos = new Map();
  const jtiVistos = new Map();
  const limpiar = (m) => { const ahora = Date.now(); for (const [k, t] of m) if (ahora - t > 15 * 60 * 1000) m.delete(k); };

  const firmar = (partes) => crypto.createHmac('sha256', op.secreto).update(partes.join('\n')).digest('hex');
  const iguales = (a, b) => a && b && a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
  const json = (res, estado, obj) => { res.writeHead(estado, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(obj)); };

  function leerCuerpo(req) {
    if (req.body && typeof req.body === 'object') return Promise.resolve(JSON.stringify(req.body));
    return new Promise((ok, fallo) => { let d = ''; req.on('data', (c) => { d += c; if (d.length > 1e6) req.destroy(); }); req.on('end', () => ok(d)); req.on('error', fallo); });
  }

  return async function conector(req, res) {
    if (!op.activo || !op.secreto) return json(res, 404, { error: 'Conector no disponible' });
    const url = new URL(req.url, 'http://local');

    // --- Apertura de sesion desde el portal (GET con token de un solo uso) ---
    if (req.method === 'GET' && url.searchParams.get('accion') === 'sso') {
      const token = url.searchParams.get('token') || '';
      const i = token.lastIndexOf('.');
      if (i < 0) return json(res, 400, { error: 'Token mal formado' });
      const datos = token.slice(0, i), firma = token.slice(i + 1);
      if (!iguales(firma, firmar(['SSO', datos]))) return json(res, 401, { error: 'Firma no válida' });
      let p; try { p = JSON.parse(Buffer.from(datos, 'base64url').toString('utf8')); } catch { return json(res, 400, { error: 'Token mal formado' }); }
      if (!p.exp || p.exp < Math.floor(Date.now() / 1000)) return json(res, 401, { error: 'Token vencido' });
      limpiar(jtiVistos); if (jtiVistos.has(p.jti)) return json(res, 401, { error: 'Token ya utilizado' }); jtiVistos.set(p.jti, Date.now());
      const registro = await op.buscarPorIdentidad({ id_externo: p.id_externo, correo: p.correo, usuario: p.usuario_externo });
      if (!registro) return json(res, 404, { error: 'Usuario no encontrado en esta aplicación' });
      await op.iniciarSesion(req, res, registro);
      if (!res.headersSent) { res.writeHead(303, { Location: op.urlInicio || '/' }); res.end(); }
      return;
    }

    // --- Llamadas firmadas del portal (POST JSON) ---
    if (req.method !== 'POST') return json(res, 405, { error: 'Método no permitido' });
    const ts = req.headers['x-obs-timestamp'], nonce = req.headers['x-obs-nonce'], firma = req.headers['x-obs-signature'];
    if (!ts || !nonce || !firma) return json(res, 401, { error: 'Falta la firma' });
    if (Math.abs(Math.floor(Date.now() / 1000) - Number(ts)) > TOLERANCIA_SEG) return json(res, 401, { error: 'Marca de tiempo fuera de rango' });
    limpiar(noncesVistos); if (noncesVistos.has(nonce)) return json(res, 401, { error: 'Petición repetida' });
    const cuerpo = await leerCuerpo(req);
    let datos; try { datos = JSON.parse(cuerpo || '{}'); } catch { return json(res, 400, { error: 'JSON no válido' }); }
    const accion = datos.accion;
    if (!iguales(firma, firmar(['POST', accion, ts, nonce, cuerpo]))) return json(res, 401, { error: 'Firma no válida' });
    noncesVistos.set(nonce, Date.now());

    if (accion === 'estado') return json(res, 200, { ok: true, version: VERSION, conjuntos: Object.keys(op.conjuntos || {}), hora: new Date().toISOString() });

    if (accion === 'verificar') {
      const registro = await op.buscarUsuario(String(datos.usuario || ''));
      if (!registro) return json(res, 200, { ok: false });
      const bien = await op.verificarClave(registro, String(datos.clave || ''));
      if (!bien) return json(res, 200, { ok: false });
      return json(res, 200, { ok: true, id: String(registro.id), usuario: registro.usuario, correo: registro.correo, nombre: registro.nombre, rol: registro.rol });
    }

    if (accion === 'exportar') {
      const c = (op.conjuntos || {})[datos.conjunto];
      if (!c) return json(res, 404, { error: 'Conjunto no definido' });
      const filas = await c.consultar({ desde: datos.desde || null });
      return json(res, 200, { ok: true, conjunto: datos.conjunto, descripcion: c.descripcion, filas });
    }

    return json(res, 400, { error: 'Acción no reconocida' });
  };
}
