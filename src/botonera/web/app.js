/* Botonera — guion del panel. Sin librerías. */
"use strict";

const MODIFICADORES = ["ctrl", "mayus", "alt", "win", "rctrl", "rmayus", "ralt", "rwin"];
const TECLAS = 12, PERILLAS = 3;
const COLORES_RAPIDOS = ["#2563eb", "#16a34a", "#dc2626", "#f97316", "#eab308", "#a855f7", "#06b6d4", "#ec4899", "#ffffff", "#94a3b8"];

const estado = {
  panorama: null,
  opciones: null,
  ajustes: null,
  perfil: 0,
  pieza: null,
  familia: "teclado",
};

const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => Array.from(raiz.querySelectorAll(s));

// --- utilidades ---------------------------------------------------------------

async function pedir(ruta, cuerpo, metodo) {
  const opciones = { method: metodo || (cuerpo ? "POST" : "GET"), headers: {} };
  if (cuerpo) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch(ruta, opciones);
  let datos = {};
  try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
  if (!r.ok) {
    avisar(datos.error || `Error ${r.status}`);
    throw new Error(datos.error || r.status);
  }
  return datos;
}

let relojAviso;
function avisar(texto) {
  const aviso = $("#aviso");
  $("#aviso-texto").textContent = texto;
  aviso.classList.add("visible");
  clearTimeout(relojAviso);
  relojAviso = setTimeout(() => aviso.classList.remove("visible"), 3400);
}

const NOMBRES = {
  ctrl: "Ctrl", mayus: "Mayús", alt: "Alt", win: "Win", rctrl: "Ctrl der.", rmayus: "Mayús der.", ralt: "Alt der.", rwin: "Win der.",
  intro: "Intro", retroceso: "Retroceso", espacio: "Espacio", esc: "Esc", supr: "Supr", tab: "Tab", insert: "Insert",
  inicio: "Inicio", fin: "Fin", repag: "Re Pág", avpag: "Av Pág", arriba: "↑", abajo: "↓", izquierda: "←", derecha: "→",
  impr: "Impr Pant", pausa: "Pausa", bloqmayus: "Bloq Mayús", bloqdespl: "Bloq Despl",
  "rueda-arriba": "Rueda ↑", "rueda-abajo": "Rueda ↓", clic: "Clic", "clic-derecho": "Clic derecho", "clic-central": "Clic central",
  "ctrl-rueda-arriba": "Ctrl + rueda ↑", "ctrl-rueda-abajo": "Ctrl + rueda ↓",
  "mayus-rueda-arriba": "Mayús + rueda ↑", "mayus-rueda-abajo": "Mayús + rueda ↓",
  "alt-rueda-arriba": "Alt + rueda ↑", "alt-rueda-abajo": "Alt + rueda ↓",
  "ctrl-clic": "Ctrl + clic", "mayus-clic": "Mayús + clic", "alt-clic": "Alt + clic",
  "vol+": "Volumen +", "vol-": "Volumen −", silencio: "Silencio", siguiente: "Pista siguiente", anterior: "Pista anterior",
  parar: "Parar", reproducir: "Reproducir / pausa", "brillo+": "Brillo +", "brillo-": "Brillo −", calculadora: "Calculadora",
  equipo: "Este equipo", navegador: "Navegador", correo: "Correo", reproductor: "Reproductor", actualizar: "Actualizar", adelante: "Adelante", atras: "Atrás",
  "ctrl-mayus-alt-f16": "Dictado", "ctrl-mayus-alt-f13": "Dictado TecladoIA", "ctrl-mayus-alt-f14": "Dictado MiniMic", "ctrl-mayus-alt-f15": "Dictado SikaiMini",
};

function familiaDe(texto) {
  const o = estado.opciones || { raton: [], multimedia: [], atajos_de_dictado: [] };
  if (o.raton.includes(texto)) return "raton";
  if (o.multimedia.includes(texto)) return "multimedia";
  if ((o.atajos_de_dictado || []).some(a => a.accion === texto)) return "dictado";
  if (texto.includes(",")) return "secuencia";
  return "teclado";
}

function nombreBonito(texto) {
  if (!texto || texto === "nada") return "nada";
  if (NOMBRES[texto]) return NOMBRES[texto];
  if (texto.includes(",")) return texto.split(",").map(p => nombreBonito(p.trim())).join(" · ");
  return texto.split("-").map(p => NOMBRES[p] || p.toUpperCase()).join("+");
}

function perfilActual() {
  const p = estado.panorama;
  return p && p.perfiles ? p.perfiles[estado.perfil] : null;
}

function textoDePieza(perfil, i) {
  if (!perfil) return "?";
  if (i < TECLAS) return perfil.teclas[i] || "nada";
  const n = Math.floor((i - TECLAS) / 3), g = (i - TECLAS) % 3;
  return (perfil.perillas[n] || [])[g] || "nada";
}

// --- tema y pestañas --------------------------------------------------------------

function aplicarTema(tema) {
  if (tema === "sistema") delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
  try { localStorage.setItem("botonera-tema", tema); } catch (e) { /* sin memoria */ }
  $$(".tema button").forEach(b => b.classList.toggle("activo", b.dataset.tema === tema));
}

function irA(nombre) {
  $$(".tab").forEach(t => t.classList.toggle("activa", t.dataset.seccion === nombre));
  $$(".seccion").forEach(s => s.classList.toggle("activa", s.id === "seccion-" + nombre));
  history.replaceState(null, "", "#" + nombre);
}

// --- el dibujo ----------------------------------------------------------------------

function construirAparato() {
  const perillas = $("#fila-perillas");
  perillas.innerHTML = "";
  for (let n = 0; n < PERILLAS; n++) {
    const base = TECLAS + 3 * n;
    const div = document.createElement("div");
    div.className = "perilla";
    div.innerHTML = `
      <span class="rotulo">Perilla ${n + 1}</span>
      <button type="button" class="disco" data-pieza="${base + 1}" title="Pulsar la perilla ${n + 1}"><span class="que">…</span></button>
      <button type="button" class="giro a" data-pieza="${base}" title="Giro a la izquierda"><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0114-5M4 4v4h4"/></svg> <span class="que">…</span></button>
      <button type="button" class="giro b" data-pieza="${base + 2}" title="Giro a la derecha"><svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 00-14-5M20 4v4h-4"/></svg> <span class="que">…</span></button>`;
    perillas.appendChild(div);
  }
  const teclas = $("#rejilla-teclas");
  teclas.innerHTML = "";
  for (let i = 0; i < TECLAS; i++) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tecla-bt";
    b.dataset.pieza = String(i);
    b.innerHTML = `<span class="numero">${i + 1}</span><span class="que">…</span>`;
    teclas.appendChild(b);
  }
  $$("[data-pieza]").forEach(b => b.addEventListener("click", () => elegirPieza(Number(b.dataset.pieza))));
}

function pintarPerfiles(contenedor, alElegir) {
  const p = estado.panorama;
  const perfiles = (p && p.perfiles) || [];
  contenedor.innerHTML = perfiles.map((perfil, i) =>
    `<button type="button" role="tab" data-perfil="${i}" class="${i === estado.perfil ? "activo" : ""}" style="--luz:${perfil.luces_modo === 0 ? "#999" : perfil.luces_color}"><i></i>${perfil.nombre}</button>`).join("");
  $$("button", contenedor).forEach(b => b.addEventListener("click", () => alElegir(Number(b.dataset.perfil))));
}

function elegirPerfil(i) {
  estado.perfil = i;
  if (estado.panorama) pintar(estado.panorama);
  if (estado.pieza !== null) elegirPieza(estado.pieza);
}

// --- pintar ---------------------------------------------------------------------

function pintar(p) {
  try { pintarDeVerdad(p); } catch (e) {
    $("#ind-conexion").textContent = "error al pintar: " + (e && e.message ? e.message : e);
    console.error(e);
  }
}

function pintarDeVerdad(p) {
  estado.panorama = p;
  const c = p.conexion;
  $("#ind-conexion").textContent = c.descripcion + (p.escribiendo ? " · grabando…" : "");
  $("#ind-grabacion").textContent = p.ultima_escritura ? p.ultima_escritura.replace("T", " ") : "nunca";
  const dictado = p.dictado || {};
  $("#ind-dictado").textContent = dictado.abierto ? "abierto en " + dictado.programa : "cerrado";
  $("#nota-dictado").textContent = dictado.atajo_reservado === false
    ? "La combinación de la tecla de dictado no se pudo reservar: ¿hay otra copia del servicio viva?"
    : (dictado.sigue_a_la_activa ? "Ahora mismo seguiría a la ventana activa." : `Ahora mismo le hablarías a ${dictado.programa}.`);

  const banda = $("#banda-teclado");
  if (c.otro_jieli && !c.cable) {
    banda.hidden = false;
    banda.textContent = "El teclado Jieli que hay por cable es otro (MiniMic o SiKai mini): la Botonera no le escribe. Conecta la Botonera para grabarla.";
  } else if (!c.conectado) {
    banda.hidden = false;
    banda.textContent = "No veo el teclado. Conéctalo por cable para grabarle lo que cambies; lo que guardes aquí se le escribirá al conectarlo.";
  } else if (!c.configurable) {
    banda.hidden = false;
    banda.textContent = "El teclado va por Bluetooth: funciona, pero para grabarle cambios hay que conectarlo por cable. Lo que guardes se le escribirá entonces.";
  } else {
    banda.hidden = true;
  }

  pintarPerfiles($("#perfiles"), elegirPerfil);
  pintarPerfiles($("#perfiles-luces"), elegirPerfil);
  const perfil = perfilActual();
  if (perfil) {
    if (document.activeElement !== $("#nombre-perfil")) $("#nombre-perfil").value = perfil.nombre;
    $("#aparato").style.setProperty("--luz-color", perfil.luces_modo === 0 ? "#1a2029" : perfil.luces_color);
    $$("[data-pieza]").forEach(b => {
      const i = Number(b.dataset.pieza);
      const que = textoDePieza(perfil, i);
      const etiqueta = $(".que", b);
      if (etiqueta) etiqueta.textContent = nombreBonito(que);
      b.title = `${p.piezas[i]}: ${nombreBonito(que)}`;
      b.classList.toggle("elegida", estado.pieza === i);
    });
    // luces
    $("#luces-perfil-nombre").textContent = `«${perfil.nombre}»`;
    if (document.activeElement !== $("#luces-modo")) $("#luces-modo").value = String(perfil.luces_modo);
    if (document.activeElement !== $("#luces-color")) $("#luces-color").value = perfil.luces_color;
    $("#nota-luces").textContent = `Guardado: ${perfil.luces_nombre}${perfil.luces_modo === 0 || perfil.luces_modo >= 4 ? "" : ", " + perfil.luces_color}.`;
  }
  $("#escribir_al_conectar").checked = p.escribir_al_conectar !== false;
  $("#texto-servicio").textContent = `Botonera ${p.version}. Teclado ${c.descripcion}. ${p.mensajes_escritos ? p.mensajes_escritos + " mensajes grabados desde que arrancó." : ""}`;
  const tunel = p.tunel || {};
  $("#punto-tunel").className = "estado-punto " + (tunel.conectado ? "si" : (tunel.motivo ? "" : "no"));
  $("#texto-tunel").textContent = tunel.conectado
    ? `Presentado al portero ${tunel.portero}${tunel.conexiones ? ` (${tunel.conexiones} conexión(es) abiertas)` : ""}.`
    : (tunel.motivo ? `No se presenta: ${tunel.motivo}.` : `Sin conexión con el portero ${tunel.portero}${tunel.ultimo_error ? ` (${tunel.ultimo_error})` : ""}; se reintenta cada 15 s.`);
  const lista = $("#avisos");
  lista.innerHTML = "";
  (p.avisos || []).forEach(a => { const li = document.createElement("li"); li.textContent = a; lista.appendChild(li); });
}

function pintarAjustes(a) {
  estado.ajustes = a;
  $("#escribir_al_conectar").checked = a.escribir_al_conectar !== false;
  $("#usar_portero").checked = a.usar_portero !== false;
  $("#portero").value = a.portero || "";
  if (a.programa) $("#programa").value = a.programa;
  $("#usar_microfono_propio").checked = a.usar_microfono_propio !== false;
  $("#pinchar_cuadro").checked = !!a.pinchar_cuadro;
  $("#enviar_al_cerrar").checked = !!a.enviar_al_cerrar;
  $("#pitido_al_abrir").checked = !!a.pitido_al_abrir;
  $("#alto_cuadro").value = a.alto_cuadro || 0;
  const atajos = a.atajos_dictado || {};
  $("#atajo_chatgpt").value = atajos.chatgpt || "";
  $("#atajo_claude").value = atajos.claude || "";
}

function pintarOpciones(o) {
  estado.opciones = o;
  $("#tecla-base").innerHTML = "<option value=''>(solo modificadores)</option>" + o.teclas.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#raton").innerHTML = o.raton.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#multimedia").innerHTML = o.multimedia.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#luces-modo").innerHTML = o.modos_de_luz.map(m => `<option value="${m.valor}">${m.nombre.replace(/^./, c => c.toUpperCase())}</option>`).join("");
  $("#atajos-dictado").innerHTML = (o.atajos_de_dictado || []).map(a =>
    `<button type="button" class="btn btn-claro" data-accion="${a.accion}">${a.nombre} <kbd>${a.accion}</kbd></button>`).join("");
  $$("#atajos-dictado button").forEach(b => b.addEventListener("click", () => guardarPieza(b.dataset.accion).catch(() => {})));
  $("#programa").innerHTML = (o.programas || []).map(p => `<option value="${p.id}">${p.nombre}</option>`).join("");
  if (estado.ajustes && estado.ajustes.programa) $("#programa").value = estado.ajustes.programa;
  $("#paleta").innerHTML = COLORES_RAPIDOS.map(col => `<button type="button" style="background:${col}" title="${col}" data-color="${col}"></button>`).join("");
  $("#host_panel").innerHTML = (o.direcciones || ["127.0.0.1"]).map(d =>
    `<option value="${d}">${d === "127.0.0.1" ? "Solo este equipo (127.0.0.1)" : d + (d.startsWith("100.") ? " (Tailscale)" : "")}</option>`).join("");
  $("#host_panel").value = o.escuchando_en || "127.0.0.1";
  if (estado.panorama) pintar(estado.panorama);
}

// --- editor de pieza ---------------------------------------------------------------

function elegirPieza(i) {
  estado.pieza = i;
  const p = estado.panorama || {};
  const perfil = perfilActual();
  const actual = textoDePieza(perfil, i);
  const nombres = p.piezas || [];
  $("#editor-cuerpo").hidden = false;
  $(".editor-titulo", $("#editor")).textContent = (nombres[i] || `Pieza ${i + 1}`).replace(/^./, c => c.toUpperCase());
  $(".editor-sub", $("#editor")).textContent = perfil
    ? `En el perfil «${perfil.nombre}» hace: ${nombreBonito(actual)}.`
    : "";
  elegirFamilia(familiaDe(actual));
  if (estado.familia === "raton") $("#raton").value = actual;
  else if (estado.familia === "multimedia") $("#multimedia").value = actual;
  else if (estado.familia === "secuencia") $("#secuencia").value = actual;
  else if (estado.familia === "teclado") { $("#combo").value = actual === "nada" ? "" : actual; desmontarCombo(actual); }
  $("#nota-pieza").textContent = i >= TECLAS
    ? "Si el giro va al revés de lo que esperas, cambia entre sí lo de los dos giros."
    : "";
  pintar(p);
}

function elegirFamilia(familia) {
  estado.familia = familia;
  $$("#familias button").forEach(b => b.classList.toggle("activo", b.dataset.familia === familia));
  ["teclado", "secuencia", "raton", "multimedia", "dictado"].forEach(f => { $("#familia-" + f).hidden = f !== familia; });
}

function desmontarCombo(combo) {
  const partes = combo && combo !== "nada" ? combo.split("-") : [];
  $$("#mods input").forEach(c => { c.checked = partes.includes(c.value); });
  const base = partes.find(x => !MODIFICADORES.includes(x)) || "";
  $("#tecla-base").value = base;
}

function montarCombo() {
  const mods = $$("#mods input").filter(c => c.checked).map(c => c.value);
  const base = $("#tecla-base").value;
  const partes = base ? [...mods, base] : mods;
  $("#combo").value = partes.join("-");
}

function accionElegida() {
  if (estado.familia === "raton") return $("#raton").value;
  if (estado.familia === "multimedia") return $("#multimedia").value;
  if (estado.familia === "secuencia") return $("#secuencia").value.trim().toLowerCase() || "nada";
  if (estado.familia === "dictado") return null;
  return $("#combo").value.trim().toLowerCase() || "nada";
}

async function guardarPieza(accion) {
  if (estado.pieza === null) return;
  if (accion === null) { avisar("Elige uno de los tres dictados"); return; }
  const r = await pedir("/api/pieza", { perfil: estado.perfil, pieza: estado.pieza, accion });
  avisar(r.escrito ? `Grabado: ${nombreBonito(r.accion)}` : (r.aviso || "Guardado"));
  await refrescar();
  elegirPieza(estado.pieza);
}

// --- acciones ---------------------------------------------------------------------

function conectar() {
  $$(".tab").forEach(t => t.addEventListener("click", () => irA(t.dataset.seccion)));
  $$(".tema button").forEach(b => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  $$("#familias button").forEach(b => b.addEventListener("click", () => elegirFamilia(b.dataset.familia)));
  $$("#mods input").forEach(c => c.addEventListener("change", montarCombo));
  $("#tecla-base").addEventListener("change", montarCombo);
  $("#combo").addEventListener("input", () => desmontarCombo($("#combo").value.trim().toLowerCase()));
  $("#btn-guardar-pieza").addEventListener("click", () => guardarPieza(accionElegida()).catch(() => {}));
  $("#btn-pieza-nada").addEventListener("click", () => guardarPieza("nada").catch(() => {}));
  $("#btn-nombre").addEventListener("click", async () => {
    const nombre = $("#nombre-perfil").value.trim();
    if (!nombre) { avisar("Ponle un nombre"); return; }
    await pedir("/api/perfil", { perfil: estado.perfil, nombre });
    avisar("Nombre cambiado"); await refrescar();
  });
  $("#btn-grabar-perfil").addEventListener("click", async () => {
    const r = await pedir("/api/aplicar", { perfil: estado.perfil });
    avisar(r.escrito ? `Perfil grabado (${r.mensajes} mensajes)` : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-grabar-todo").addEventListener("click", aplicarTodo);
  $("#btn-aplicar-todo").addEventListener("click", aplicarTodo);
  $("#btn-inicial").addEventListener("click", async () => {
    if (!confirm("¿Devolver este perfil a como lo deja la Botonera de inicio (F13-F24, volumen, rueda y música en las perillas)?")) return;
    const r = await pedir("/api/restablecer", { perfil: estado.perfil });
    avisar(r.escrito ? "Perfil vuelto a lo inicial y grabado" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-restablecer-todo").addEventListener("click", async () => {
    if (!confirm("¿Devolver los TRES perfiles a lo inicial? Se pierde lo que tengas puesto.")) return;
    const r = await pedir("/api/restablecer", {});
    avisar(r.escrito ? "Los tres perfiles, a lo inicial" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-luces").addEventListener("click", async () => {
    const r = await pedir("/api/luces", { perfil: estado.perfil, modo: Number($("#luces-modo").value), color: $("#luces-color").value });
    avisar(r.escrito ? "Luces grabadas" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-luces-probar").addEventListener("click", async () => {
    const r = await pedir("/api/luces", { perfil: estado.perfil, modo: Number($("#luces-modo").value), color: $("#luces-color").value, probar: true });
    avisar(r.escrito ? "Mandado al teclado, sin guardar" : (r.aviso || "Sin teclado por cable"));
  });
  $("#paleta").addEventListener("click", e => { const b = e.target.closest("[data-color]"); if (b) $("#luces-color").value = b.dataset.color; });
  $("#escribir_al_conectar").addEventListener("change", async () => {
    await pedir("/api/ajustes", { escribir_al_conectar: $("#escribir_al_conectar").checked });
    avisar($("#escribir_al_conectar").checked ? "Se grabará al conectar" : "Ya no se graba solo al conectar");
  });
  $("#btn-escuchar").addEventListener("click", escuchar);
  $("#programa").addEventListener("change", async () => { await pedir("/api/ajustes", { programa: $("#programa").value }); avisar("Ahora le hablas a: " + $("#programa option:checked").textContent); await refrescar(); });
  $("#btn-probar-dictado").addEventListener("click", async () => { const r = await pedir("/api/dictado/probar", {}); avisar("Dictado: " + (r.accion || "?")); });
  $("#btn-ir-tecla").addEventListener("click", () => { irA("teclado"); if (estado.pieza === null) elegirPieza(0); elegirFamilia("dictado"); });
  $("#btn-guardar-dictado").addEventListener("click", async () => {
    await pedir("/api/ajustes", {
      usar_microfono_propio: $("#usar_microfono_propio").checked, pinchar_cuadro: $("#pinchar_cuadro").checked,
      enviar_al_cerrar: $("#enviar_al_cerrar").checked, pitido_al_abrir: $("#pitido_al_abrir").checked,
      alto_cuadro: Number($("#alto_cuadro").value) || 0,
    });
    avisar("Guardado");
  });
  $("#btn-guardar-atajos").addEventListener("click", async () => {
    await pedir("/api/ajustes", { atajos_dictado: { chatgpt: $("#atajo_chatgpt").value.trim(), claude: $("#atajo_claude").value.trim() } });
    avisar("Atajos guardados; ya se usan");
  });
  $("#btn-guardar-host").addEventListener("click", async () => {
    const host = $("#host_panel").value;
    const r = await pedir("/api/ajustes", { host_panel: host });
    avisar(r.reabriendo && host !== "127.0.0.1" ? `El panel se está moviendo a http://${host}:8773. Si esta pestaña deja de responder, ábrelo ahí.` : "Guardado");
  });
  $("#btn-guardar-portero").addEventListener("click", async () => {
    await pedir("/api/ajustes", { usar_portero: $("#usar_portero").checked, portero: $("#portero").value.trim() });
    avisar("Guardado; el túnel se ajusta solo"); await refrescar();
  });
  $("#btn-guardar-clave").addEventListener("click", async () => {
    const clave = $("#clave_panel").value;
    if (clave.length < 6) { avisar("La clave necesita seis caracteres o más"); return; }
    await pedir("/api/ajustes", { clave_panel: clave });
    $("#clave_panel").value = "";
    avisar("Clave cambiada. La próxima visita desde fuera la pedirá.");
  });
  $("#btn-registro").addEventListener("click", async () => {
    const r = await pedir("/api/registro");
    const pre = $("#registro");
    pre.hidden = false;
    pre.textContent = (r.lineas && r.lineas.length) ? r.lineas.join("\n") : `Sin registro en ${r.ruta}`;
    pre.scrollTop = pre.scrollHeight;
  });
}

async function aplicarTodo() {
  $("#nota-aplicar").textContent = "Grabando…";
  try {
    const r = await pedir("/api/aplicar", {});
    avisar(r.escrito ? `Grabados los tres perfiles (${r.mensajes} mensajes)` : (r.aviso || "Guardado"));
    $("#nota-aplicar").textContent = r.escrito ? `Grabados a las ${r.ultima_escritura.replace("T", " ")}.` : (r.aviso || "");
  } catch (e) { $("#nota-aplicar").textContent = ""; }
  await refrescar();
}

async function escuchar() {
  const segundos = Math.max(3, Math.min(60, Number($("#segundos").value) || 12));
  const boton = $("#btn-escuchar");
  boton.disabled = true;
  const lista = $("#pulsaciones");
  lista.innerHTML = "";
  let quedan = segundos;
  const cuenta = $("#cuenta");
  cuenta.textContent = `${quedan} s… pulsa el teclado`;
  const reloj = setInterval(() => { quedan -= 1; cuenta.textContent = quedan > 0 ? `${quedan} s… pulsa el teclado` : "recogiendo…"; }, 1000);
  try {
    const r = await pedir("/api/escuchar", { segundos });
    const pulsaciones = r.pulsaciones || [];
    if (!pulsaciones.length) {
      lista.innerHTML = "<li>No llegó nada del teclado. ¿Está conectado y pulsaste sus teclas?</li>";
    } else {
      lista.innerHTML = pulsaciones.map(p => `<li><b>${nombreBonito(p.tecla)}</b><small>${p.t}s · ${p.origen}</small></li>`).join("");
      // se ilumina en el dibujo lo que coincida con alguna pieza del perfil elegido
      const perfil = perfilActual();
      pulsaciones.forEach((p, k) => {
        for (let i = 0; i < TECLAS + 3 * PERILLAS; i++) {
          if (perfil && textoDePieza(perfil, i) === p.tecla) {
            const b = $(`[data-pieza="${i}"]`);
            if (b) setTimeout(() => { b.classList.add("pulsada"); setTimeout(() => b.classList.remove("pulsada"), 350); }, 120 * k);
          }
        }
      });
    }
    cuenta.textContent = `${pulsaciones.length} pulsación(es)`;
  } catch (e) {
    cuenta.textContent = "";
  } finally {
    clearInterval(reloj);
    boton.disabled = false;
  }
}

async function refrescar() {
  pintar(await pedir("/api/estado"));
}

function escuchando() {
  const fuente = new EventSource("/api/sucesos");
  fuente.addEventListener("bienvenida", e => { $("#chip-vivo").hidden = false; pintar(JSON.parse(e.data)); });
  fuente.addEventListener("estado", e => pintar(JSON.parse(e.data)));
  fuente.addEventListener("pulsacion", e => {
    const d = JSON.parse(e.data);
    avisar(`Tecla de dictado: ${d.accion} (${d.programa}, ${d.con_el_propio ? "micrófono propio" : "Win+H"})`);
  });
  fuente.onerror = () => {
    $("#chip-vivo").hidden = true;
    if ($("#ind-conexion").textContent === "Esperando…") $("#ind-conexion").textContent = "sin canal en vivo; reintentando";
  };
}

(async function arrancar() {
  let tema = "sistema";
  try { tema = localStorage.getItem("botonera-tema") || "sistema"; } catch (e) { /* nada */ }
  aplicarTema(tema);
  construirAparato();
  conectar();
  if (location.hash.length > 1) irA(location.hash.slice(1));
  try {
    pintarOpciones(await pedir("/api/opciones"));
  } catch (e) { /* ya se avisó */ }
  try {
    await refrescar();
  } catch (e) {
    $("#ind-conexion").textContent = "el servicio no contesta (" + (e && e.message ? e.message : e) + ")";
  }
  escuchando();
  try {
    pintarAjustes(await pedir("/api/ajustes"));
  } catch (e) { /* ya se avisó */ }
  setInterval(() => { if ($("#chip-vivo").hidden) refrescar().catch(() => {}); }, 5000);
})();
