// Plantillas HTML del portal. Sin dependencias externas.
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Number(n || 0).toLocaleString('es-CO');

const CSS = `
:root{color-scheme:light;--bg:#f3f5f4;--panel:#fff;--panel2:#f7f9f8;--line:#d5dbd8;--line2:#e4e9e6;--ink:#152029;--ink2:#4a5761;--ink3:#7b8790;--brand:#0e4f6e;--brand2:#0b3f58;--soft:#dbe9f0;--accent:#b9741c;--good:#0ca30c;--crit:#d03b3b;--warn:#8a5a00;--s1:#2a78d6}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#0f1519;--panel:#1a2329;--panel2:#1f2a31;--line:#2c3940;--line2:#243038;--ink:#e8edef;--ink2:#b4c0c7;--ink3:#7f8d95;--brand:#3d8fb5;--brand2:#2f7a9d;--soft:#173442;--accent:#d99a3a;--warn:#fab219;--s1:#3987e5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--brand)}h1,h2,h3{margin:0;line-height:1.2;font-family:Archivo,"IBM Plex Sans",system-ui,sans-serif}h1{font-size:24px}h2{font-size:17px}h3{font-size:14.5px}
.top{display:flex;gap:16px;align-items:center;padding:12px 28px;background:var(--panel);border-bottom:1px solid var(--line)}
.logo{display:flex;gap:10px;align-items:center;text-decoration:none;color:inherit}.mark{width:32px;height:32px;border-radius:8px;background:var(--brand);color:#fff;display:grid;place-items:center;font-weight:700;font-size:12px}
.logo b{display:block;font-size:13.5px}.logo span{display:block;font-size:11.5px;color:var(--ink3)}
nav{display:flex;gap:4px;margin-left:24px}nav a{padding:7px 12px;border-radius:6px;color:var(--ink2);text-decoration:none;font-weight:500}nav a.on{background:var(--soft);color:var(--brand)}nav a:hover{background:var(--panel2)}
.user{margin-left:auto;display:flex;gap:10px;align-items:center;font-size:13px}.user span{color:var(--ink3)}
main{max-width:1180px;margin:0 auto;padding:28px}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:20px}.head p{color:var(--ink2);margin:6px 0 0;max-width:70ch}
.eyebrow{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);font-weight:600}
.grid{display:grid;gap:16px}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.g3{grid-template-columns:repeat(3,minmax(0,1fr))}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media(max-width:900px){.g2,.g3,.g4{grid-template-columns:1fr}nav{display:none}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px}.panel h3{margin-bottom:10px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 18px}.tile .l{font-size:12.5px;color:var(--ink2)}.tile .v{font-size:28px;font-weight:600;font-variant-numeric:tabular-nums}.tile .d{font-size:12px;color:var(--ink3)}
.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--panel);color:inherit;border-radius:6px;padding:8px 14px;font:inherit;font-weight:500;cursor:pointer;text-decoration:none}.btn:hover{background:var(--panel2)}
.btn.p{background:var(--brand);border-color:var(--brand);color:#fff}.btn.p:hover{background:var(--brand2)}.btn.sm{padding:5px 10px;font-size:12.5px}
input{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:9px 11px;width:100%}label{display:block;font-size:12.5px;font-weight:600;color:var(--ink2);margin:14px 0 5px}
.chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:600}.chip::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.ok{color:var(--good);background:color-mix(in srgb,var(--good) 12%,transparent)}.crit{color:var(--crit);background:color-mix(in srgb,var(--crit) 12%,transparent)}.warn{color:var(--warn);background:color-mix(in srgb,#fab219 22%,transparent)}.neu{color:var(--ink2);background:var(--line2)}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3);padding:8px 10px;border-bottom:1px solid var(--line)}td{padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}
.tw{overflow-x:auto}.mono{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:12px}
.login{min-height:100vh;display:grid;grid-template-columns:1.1fr 1fr}.side{background:var(--brand2);color:#fff;padding:56px 64px}.side h1{font-size:34px;color:#fff;max-width:18ch;margin-top:10px}.side p{color:rgba(255,255,255,.82);max-width:50ch;font-size:15px}
.form{display:flex;align-items:center;justify-content:center;padding:40px 24px}.card{width:min(420px,100%);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:32px}
.err{border-left:3px solid var(--crit);background:color-mix(in srgb,var(--crit) 10%,transparent);padding:10px 12px;border-radius:0 6px 6px 0;margin-top:14px;font-size:13px}
.note{border-left:3px solid var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent);padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.launch{display:flex;flex-direction:column;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;text-decoration:none;color:inherit;min-height:140px}.launch:hover{border-color:var(--brand)}.launch b{font-size:15px;font-family:Archivo,system-ui,sans-serif}.launch span{color:var(--ink2);font-size:12.5px}.launch .f{margin-top:auto;display:flex;justify-content:space-between;font-size:11.5px;color:var(--ink3)}
@media(max-width:820px){.login{grid-template-columns:1fr}.side{padding:32px 24px}}
svg.ch text{fill:var(--ink2);font-size:11px}svg.ch .g{stroke:var(--line2)}
`;

export function pagina({ titulo, cuerpo, usuario = null, ruta = '' }) {
  const nav = usuario ? `<nav>
      <a href="/escritorio" class="${ruta === 'escritorio' ? 'on' : ''}">Escritorio</a>
      <a href="/tablero" class="${ruta === 'tablero' ? 'on' : ''}">Cuadro de mando</a>
      <a href="/cuenta" class="${ruta === 'cuenta' ? 'on' : ''}">Mi cuenta</a>
      ${usuario.rol === 'administrador' ? `<a href="/admin" class="${ruta === 'admin' ? 'on' : ''}">Administración</a>` : ''}
    </nav>
    <div class="user"><div><b>${esc(usuario.nombre || usuario.correo)}</b><br><span>${esc(usuario.correo)}</span></div><form method="post" action="/salir" style="margin:0"><button class="btn sm">Salir</button></form></div>` : '';
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(titulo)} · Portal del Observatorio</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono&display=swap"><style>${CSS}</style></head><body>
${usuario ? `<header class="top"><a class="logo" href="/escritorio"><div class="mark">ONIA</div><div><b>Portal del Observatorio</b><span>Inteligencia Artificial</span></div></a>${nav}</header>` : ''}
${cuerpo}</body></html>`;
}

export function vistaIngreso({ error = '', apps, usuarioPrevio = '' }) {
  return pagina({ titulo: 'Ingresar', cuerpo: `<section class="login"><div class="side"><div class="eyebrow" style="color:rgba(255,255,255,.65)">Proyecto IA para el Estado · Universidad de Cartagena</div><h1>Observatorio Nacional de Inteligencia Artificial</h1><p>Ingrese con el usuario y la clave que ya utiliza en ${apps.map((a) => esc(a.nombre)).join(' o en ')}. Con una sola sesión tendrá acceso a todas las aplicaciones del portal.</p></div>
<div class="form"><form class="card" method="post" action="/ingresar"><div class="logo" style="margin-bottom:18px"><div class="mark">ONIA</div><div><b>Portal del Observatorio</b><span>Acceso a los servicios</span></div></div><h2>Ingresar</h2>
<label for="u">Usuario o correo</label><input id="u" name="usuario" autocomplete="username" required value="${esc(usuarioPrevio)}">
<label for="p">Clave</label><input id="p" name="clave" type="password" autocomplete="current-password" required>
${error ? `<div class="err">${esc(error)}</div>` : ''}
<div style="margin-top:20px"><button class="btn p" style="width:100%;justify-content:center">Ingresar al portal</button></div>
<p style="font-size:12.5px;color:var(--ink3);margin-top:16px">Su clave se verifica en la aplicación donde ya está registrada y no se guarda en el portal.</p></form></div></section>` });
}

export function vistaEscritorio({ usuario, apps, ids, resumen }) {
  const tarjetas = apps.map((a) => {
    const v = ids.find((i) => i.app === a.clave);
    const r = resumen.find((x) => x.app.clave === a.clave);
    const filas = r ? r.conjuntos.reduce((s, c) => s + c.filas, 0) : 0;
    return `<a class="launch" href="/abrir/${esc(a.clave)}"><b>${esc(a.nombre)}</b><span>${v ? `Se abre con su sesión ya iniciada (usuario ${esc(v.usuario_externo || v.id_externo)}).` : 'Aún no tiene una cuenta vinculada en esta aplicación. Se abrirá su pantalla de ingreso.'}</span><div class="f"><span>${r && r.conjuntos.length ? `${fmt(filas)} registros recolectados` : 'Sin datos recolectados'}</span><span class="chip ${v ? 'ok' : 'neu'}">${v ? 'Vinculada' : 'Sin vincular'}</span></div></a>`;
  }).join('');
  return pagina({ usuario, ruta: 'escritorio', titulo: 'Escritorio', cuerpo: `<main><div class="head"><div><div class="eyebrow">Escritorio</div><h1>${saludo()}, ${esc((usuario.nombre || usuario.correo).split(' ')[0])}</h1><p>Abra las aplicaciones con su sesión ya iniciada y consulte el cuadro de mando del Observatorio.</p></div></div>
<div class="grid g3">${tarjetas}<a class="launch" href="/tablero"><b>Cuadro de mando</b><span>Indicadores construidos con los datos recolectados de las aplicaciones.</span><div class="f"><span>Portal</span><span class="chip ok">Disponible</span></div></a></div></main>` });
}

function saludo() { const h = new Date().getHours(); return h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'; }

export function vistaTablero({ usuario, resumen }) {
  const totalFilas = resumen.reduce((s, r) => s + r.conjuntos.reduce((t, c) => t + c.filas, 0), 0);
  const conjuntos = resumen.reduce((s, r) => s + r.conjuntos.length, 0);
  const ultima = resumen.flatMap((r) => r.conjuntos.map((c) => c.fecha)).sort().pop();
  const bloques = resumen.map((r) => `<div class="panel"><div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px"><h3>${esc(r.app.nombre)}</h3>${r.ultimoError && (!r.conjuntos.length || r.ultimoError.recolectado_en > (r.conjuntos[0] || {}).fecha) ? `<span class="chip crit">Última recolección con error</span>` : r.conjuntos.length ? `<span class="chip ok">Datos al día</span>` : `<span class="chip neu">Sin datos</span>`}</div>
    ${r.conjuntos.length ? r.conjuntos.map((c) => `<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line2)"><div style="display:flex;justify-content:space-between;gap:10px"><b>${esc(c.descripcion || c.conjunto)}</b><span class="mono" style="color:var(--ink3)">${fmt(c.filas)} filas · ${esc(c.fecha)} UTC</span></div>
      ${c.series ? grafico(c.series) : ''}
      ${c.muestra.length ? `<div class="tw" style="margin-top:8px"><table><thead><tr>${c.columnas.slice(0, 6).map((k) => `<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${c.muestra.map((f) => `<tr>${c.columnas.slice(0, 6).map((k) => `<td>${esc(typeof f[k] === 'object' ? JSON.stringify(f[k]) : f[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : ''}</div>`).join('') : `<p style="color:var(--ink2);margin:8px 0 0">Todavía no se han recolectado datos de esta aplicación.${r.ultimoError ? ` Último error. <span class="mono">${esc(r.ultimoError.detalle)}</span>` : ''}</p>`}</div>`).join('');
  return pagina({ usuario, ruta: 'tablero', titulo: 'Cuadro de mando', cuerpo: `<main><div class="head"><div><div class="eyebrow">Observatorio</div><h1>Cuadro de mando</h1><p>Datos recolectados en solo lectura desde las aplicaciones conectadas. Los indicadores del Observatorio se construirán sobre estos conjuntos.</p></div>${usuario.rol === 'administrador' ? `<form method="post" action="/admin/recolectar"><button class="btn">Recolectar ahora</button></form>` : ''}</div>
<div class="grid g4" style="margin-bottom:18px"><div class="tile"><div class="l">Aplicaciones conectadas</div><div class="v">${resumen.length}</div><div class="d">${resumen.filter((r) => r.conjuntos.length).length} con datos</div></div><div class="tile"><div class="l">Conjuntos de datos</div><div class="v">${conjuntos}</div><div class="d">definidos por los conectores</div></div><div class="tile"><div class="l">Registros recolectados</div><div class="v">${fmt(totalFilas)}</div><div class="d">última recolección exitosa</div></div><div class="tile"><div class="l">Última actualización</div><div class="v" style="font-size:16px;margin-top:8px">${ultima ? esc(ultima) + ' UTC' : 'Nunca'}</div><div class="d">horario del servidor</div></div></div>
<div class="grid g2">${bloques}</div></main>` });
}

function grafico(serie) {
  const W = 520, H = 150, pl = 34, pb = 26, pt = 10, max = Math.max(...serie.map((s) => s.n), 1);
  const bw = Math.min(24, (W - pl - 10) / serie.length - 6);
  const sx = (i) => pl + (i + 0.5) * ((W - pl - 10) / serie.length), sy = (v) => pt + (1 - v / max) * (H - pb - pt);
  let out = `<svg class="ch" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;margin-top:8px" role="img" aria-label="Registros por mes">`;
  for (let t = 0; t <= 4; t++) { const v = Math.round((max * t) / 4); const y = sy(v); out += `<line class="g" x1="${pl}" x2="${W - 6}" y1="${y}" y2="${y}"/><text x="${pl - 6}" y="${y + 3}" text-anchor="end">${v}</text>`; }
  serie.forEach((s, i) => { const x = sx(i) - bw / 2, y = sy(s.n), h = sy(0) - y; out += `<path d="M${x},${sy(0)} v-${Math.max(h - 4, 0)} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 v${Math.max(h - 4, 0)} z" fill="var(--s1)"><title>${s.mes}: ${s.n}</title></path><text x="${sx(i)}" y="${H - 8}" text-anchor="middle">${s.mes.slice(2).replace('-', '/')}</text>`; });
  return out + '</svg>';
}

export function vistaCuenta({ usuario, ids, apps, sesiones }) {
  return pagina({ usuario, ruta: 'cuenta', titulo: 'Mi cuenta', cuerpo: `<main><div class="head"><div><div class="eyebrow">Mi cuenta</div><h1>Cuenta y aplicaciones vinculadas</h1><p>Su cuenta del portal se creó a partir de la aplicación donde verificó su clave por primera vez. Puede vincular las demás ingresando en ellas desde el escritorio.</p></div></div>
<div class="grid g2"><div class="panel"><h3>Datos</h3><table><tr><td style="color:var(--ink3)">Nombre</td><td>${esc(usuario.nombre || '')}</td></tr><tr><td style="color:var(--ink3)">Correo</td><td>${esc(usuario.correo)}</td></tr><tr><td style="color:var(--ink3)">Rol en el portal</td><td>${esc(usuario.rol)}</td></tr></table></div>
<div class="panel"><h3>Aplicaciones</h3><table>${apps.map((a) => { const v = ids.find((i) => i.app === a.clave); return `<tr><td><b>${esc(a.nombre)}</b><br><span style="color:var(--ink3);font-size:12px">${v ? `usuario ${esc(v.usuario_externo || v.id_externo)} · verificado ${esc(v.verificado_en)}` : 'sin vincular'}</span></td><td class="num">${v ? '<span class="chip ok">Vinculada</span>' : `<a class="btn sm" href="/vincular/${esc(a.clave)}">Vincular</a>`}</td></tr>`; }).join('')}</table></div>
<div class="panel" style="grid-column:1/-1"><h3>Sesiones activas</h3><div class="tw"><table><thead><tr><th>Inicio</th><th>Expira</th><th>Dirección</th><th>Navegador</th></tr></thead><tbody>${sesiones.map((s) => `<tr><td>${esc(s.creada_en)}</td><td>${esc(s.expira_en.slice(0, 19).replace('T', ' '))}</td><td class="mono">${esc(s.ip || '')}</td><td style="font-size:12px;color:var(--ink2)">${esc((s.agente || '').slice(0, 80))}</td></tr>`).join('')}</tbody></table></div></div></div></main>` });
}

export function vistaVincular({ usuario, app, error = '' }) {
  return pagina({ usuario, ruta: 'cuenta', titulo: 'Vincular', cuerpo: `<main><div class="head"><div><div class="eyebrow">Mi cuenta</div><h1>Vincular ${esc(app.nombre)}</h1><p>Escriba una sola vez el usuario y la clave que usa en ${esc(app.nombre)}. A partir de entonces se abrirá con su sesión del portal.</p></div></div>
<form class="card" method="post" action="/vincular/${esc(app.clave)}" style="max-width:420px"><label for="u">Usuario en ${esc(app.nombre)}</label><input id="u" name="usuario" required><label for="p">Clave en ${esc(app.nombre)}</label><input id="p" name="clave" type="password" required>${error ? `<div class="err">${esc(error)}</div>` : ''}<div style="margin-top:18px;display:flex;gap:8px"><button class="btn p">Vincular</button><a class="btn" href="/cuenta">Cancelar</a></div></form></main>` });
}

export function vistaAdmin({ usuario, apps, estados, auditoria, usuarios, mensaje = '' }) {
  return pagina({ usuario, ruta: 'admin', titulo: 'Administración', cuerpo: `<main><div class="head"><div><div class="eyebrow">Administración</div><h1>Estado de la plataforma</h1><p>Conectores, recolección de datos, usuarios del portal y auditoría.</p></div><form method="post" action="/admin/recolectar"><button class="btn p">Recolectar ahora</button></form></div>
${mensaje ? `<div class="note" style="margin-bottom:16px">${esc(mensaje)}</div>` : ''}
<div class="panel" style="margin-bottom:16px"><h3>Conectores</h3><div class="tw"><table><thead><tr><th>Aplicación</th><th>Dirección del conector</th><th>Estado</th><th>Conjuntos</th><th>Versión</th></tr></thead><tbody>${estados.map((e) => `<tr><td><b>${esc(e.app.nombre)}</b></td><td class="mono">${esc(e.app.conector)}</td><td>${e.ok ? '<span class="chip ok">Activo</span>' : `<span class="chip crit">Sin respuesta</span><div style="font-size:12px;color:var(--ink3)">${esc(e.error)}</div>`}</td><td>${e.ok ? esc((e.conjuntos || []).join(', ')) : ''}</td><td class="mono">${e.ok ? esc(e.version || '') : ''}</td></tr>`).join('')}</tbody></table></div></div>
<div class="grid g2"><div class="panel"><h3>Usuarios del portal</h3><div class="tw"><table><thead><tr><th>Correo</th><th>Rol</th><th>Último ingreso</th><th class="num">Vínculos</th></tr></thead><tbody>${usuarios.map((u) => `<tr><td>${esc(u.correo)}</td><td>${esc(u.rol)}</td><td>${esc(u.ultimo_ingreso || '')}</td><td class="num">${u.vinculos}</td></tr>`).join('')}</tbody></table></div></div>
<div class="panel"><h3>Auditoría reciente</h3><div class="tw"><table><thead><tr><th>Fecha</th><th>Evento</th><th>App</th><th>Detalle</th></tr></thead><tbody>${auditoria.map((a) => `<tr><td class="mono">${esc(a.ocurrido_en)}</td><td>${esc(a.evento)}</td><td>${esc(a.app || '')}</td><td style="font-size:12px;color:var(--ink2)">${esc(a.detalle || '')}</td></tr>`).join('')}</tbody></table></div></div></div></main>` });
}

export function vistaMensaje({ usuario, titulo, texto, enlace = '/escritorio', textoEnlace = 'Volver al escritorio' }) {
  return pagina({ usuario, titulo, cuerpo: `<main><div class="panel" style="max-width:560px;margin:40px auto"><h2>${esc(titulo)}</h2><p style="color:var(--ink2);margin:10px 0 18px">${esc(texto)}</p><a class="btn p" href="${esc(enlace)}">${esc(textoEnlace)}</a></div></main>` });
}
