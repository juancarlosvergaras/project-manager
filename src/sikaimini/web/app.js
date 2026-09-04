/* SikaiMini — guion del panel. Sin librerías. */
"use strict";

const ATAJO_MICROFONO = "ctrl-mayus-alt-f15";
const MODIFICADORES = ["ctrl", "mayus", "alt", "win", "rctrl", "rmayus", "ralt", "rwin"];

const estado = {
  panorama: null,
  opciones: null,
  ajustes: null,
  piezaElegida: null,
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
  relojAviso = setTimeout(() => aviso.classList.remove("visible"), 3200);
}

const NOMBRES = {
  ctrl: "Ctrl", mayus: "Mayús", alt: "Alt", win: "Win", rctrl: "Ctrl der.", rmayus: "Mayús der.", ralt: "Alt der.", rwin: "Win der.",
  intro: "Intro", retroceso: "Retroceso", espacio: "Espacio", esc: "Esc", supr: "Supr", tab: "Tab",
  "rueda-arriba": "Rueda arriba", "rueda-abajo": "Rueda abajo", clic: "Clic", "clic-derecho": "Clic derecho", "clic-central": "Clic central",
  "ctrl-rueda-arriba": "Ctrl + rueda arriba", "ctrl-rueda-abajo": "Ctrl + rueda abajo",
  "mayus-rueda-arriba": "Mayús + rueda arriba", "mayus-rueda-abajo": "Mayús + rueda abajo",
  "alt-rueda-arriba": "Alt + rueda arriba", "alt-rueda-abajo": "Alt + rueda abajo",
  "gesto-izquierda": "Gesto a la izquierda", "gesto-derecha": "Gesto a la derecha", "gesto-arriba": "Gesto arriba", "gesto-abajo": "Gesto abajo",
  "me-gusta": "Me gusta",
  "vol+": "Volumen +", "vol-": "Volumen −", silencio: "Silencio", siguiente: "Pista siguiente", anterior: "Pista anterior",
  parar: "Parar", reproducir: "Reproducir / pausa", "brillo+": "Brillo +", "brillo-": "Brillo −", calculadora: "Calculadora",
  equipo: "Este equipo", navegador: "Navegador", correo: "Correo", reproductor: "Reproductor", actualizar: "Actualizar", adelante: "Adelante", atras: "Atrás",
};

function familiaDe(combo) {
  const o = estado.opciones || { raton: [], multimedia: [] };
  if (o.raton.includes(combo)) return "raton";
  if (o.multimedia.includes(combo)) return "multimedia";
  return "teclado";
}

function nombreBonito(combo) {
  if (!combo || combo === "nada") return "nada";
  if (NOMBRES[combo]) return NOMBRES[combo];
  return combo.split("-").map(p => NOMBRES[p] || p.toUpperCase()).join(" + ");
}

// --- tema y pestañas --------------------------------------------------------------

function aplicarTema(tema) {
  if (tema === "sistema") delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
  try { localStorage.setItem("sikaimini-tema", tema); } catch (e) { /* sin memoria */ }
  $$(".tema button").forEach(b => b.classList.toggle("activo", b.dataset.tema === tema));
}

function irA(nombre) {
  $$(".tab").forEach(t => t.classList.toggle("activa", t.dataset.seccion === nombre));
  $$(".seccion").forEach(s => s.classList.toggle("activa", s.id === "seccion-" + nombre));
  history.replaceState(null, "", "#" + nombre);
}

// --- pintar ---------------------------------------------------------------------

function pintar(p) {
  try { pintarDeVerdad(p); } catch (e) {
    // Que un dato que falte no deje la página muda: se dice qué pasó.
    $("#ind-conexion").textContent = "error al pintar: " + (e && e.message ? e.message : e);
    console.error(e);
  }
}

function pintarDeVerdad(p) {
  estado.panorama = p;
  const c = p.conexion;
  $("#ind-conexion").textContent = c.descripcion;
  $("#ind-microfono").textContent = p.microfono.nombre ? (p.microfono.es_el_del_sistema ? "el del teclado" : "hay otro puesto") : "no está";
  $("#ind-dictado").textContent = p.dictado.abierto ? "abierto en " + p.dictado.programa : "cerrado";

  const banda = $("#banda-teclado");
  if (!c.conectado) {
    banda.hidden = false;
    banda.textContent = "No veo el teclado. Conéctalo por cable para configurarlo, o enchufa su receptor de 2,4 GHz para usarlo.";
  } else if (!c.configurable) {
    banda.hidden = false;
    banda.textContent = "El teclado va por el receptor de 2,4 GHz: funciona, pero para cambiarle las teclas o la perilla hay que conectarlo por cable. Lo que ves es lo último que se le leyó.";
  } else {
    banda.hidden = true;
  }

  const mapa = p.mapa || [];
  const deseadas = p.teclas_deseadas || [];
  $$("[data-tecla]").forEach(b => {
    const i = Number(b.dataset.tecla);
    const que = mapa[i] || "?";
    const etiqueta = $(".que", b);
    if (etiqueta) etiqueta.textContent = nombreBonito(que);
    const quiere = $(".quiere", b);
    if (quiere) quiere.textContent = (deseadas[i] && deseadas[i] !== que) ? "→ " + nombreBonito(deseadas[i]) + " (pendiente)" : "";
    if (b.classList.contains("disco")) b.title = "Pulsar la perilla: " + nombreBonito(que);
    b.classList.toggle("elegida", estado.piezaElegida === i);
  });
  const piezas = p.piezas || [];
  $("#leyenda").innerHTML = piezas.map((nombre, i) => {
    const que = mapa[i] || "?";
    const pendiente = deseadas[i] && deseadas[i] !== que ? ` <i>(pendiente: ${nombreBonito(deseadas[i])})</i>` : "";
    return `<li><b>${nombre}</b>: ${nombreBonito(que)}${pendiente}</li>`;
  }).join("");
  $("#tecla-mic").classList.toggle("grabando", !!p.dictado.abierto);

  // luces
  const luces = p.luces;
  if (luces) {
    $("#luces-actual").textContent = `Modo ${luces.modo}, color ${luces.color}.`;
    $("#aparato").style.setProperty("--luz-color", luces.modo === 0 ? "#F2F5F9" : luces.color);
    $("#paleta").innerHTML = (luces.paleta || []).map(col => `<button type="button" style="background:${col}" title="${col}" data-color="${col}"></button>`).join("");
  } else {
    $("#luces-actual").textContent = c.configurable ? "Todavía no se han leído." : "Se leen cuando el teclado está por cable.";
  }
  const deseo = p.luces_deseadas || { modo: -1, color: "#ffffff" };
  if (document.activeElement !== $("#luces-modo")) $("#luces-modo").value = deseo.modo;
  if (document.activeElement !== $("#luces-color")) $("#luces-color").value = deseo.color;
  $("#nota-luces").textContent = deseo.modo === -1
    ? "Ahora mismo SikaiMini no toca las luces."
    : `Se graba modo ${deseo.modo} con el color ${deseo.color} cada vez que el teclado se conecta por cable.`;

  // micrófono
  const punto = $("#punto-mic");
  punto.className = "estado-punto " + (p.microfono.nombre ? (p.microfono.es_el_del_sistema ? "si" : "no") : "");
  $("#texto-mic").textContent = p.microfono.nombre
    ? (p.microfono.es_el_del_sistema ? "El micrófono del teclado es el del sistema." : "El teclado está, pero el micrófono del sistema es otro.")
    : "No hay micrófono del teclado a la vista.";
  $$("#modo-mic button").forEach(b => b.classList.toggle("activo", Number(b.dataset.modo) === p.modo_microfono));
  $("#nota-dictado").textContent = p.dictado.atajo_reservado === false
    ? "La combinación de la tecla del micrófono no se pudo reservar: ¿hay otra copia del servicio viva?"
    : "";
  $("#texto-servicio").textContent = `SikaiMini ${p.version}. Teclado ${c.descripcion}.`;
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
  $("#programa").value = a.programa;
  $("#adoptar_microfono").checked = !!a.adoptar_microfono;
  $("#usar_microfono_propio").checked = a.usar_microfono_propio !== false;
  $("#pinchar_cuadro").checked = !!a.pinchar_cuadro;
  $("#enviar_al_cerrar").checked = !!a.enviar_al_cerrar;
  $("#pitido_al_abrir").checked = !!a.pitido_al_abrir;
  $("#alto_cuadro").value = a.alto_cuadro || 0;
  const atajos = a.atajos_dictado || {};
  $("#usar_portero").checked = a.usar_portero !== false;
  $("#portero").value = a.portero || "";
  $("#atajo_chatgpt").value = atajos.chatgpt || "";
  $("#atajo_claude").value = atajos.claude || "";
}

function pintarPaquete(p) {
  const boton = $("#btn-descargar");
  if (p.disponible) {
    boton.classList.remove("btn-claro"); boton.classList.add("btn-verde");
    $("#nota-descarga").textContent = `${p.megas} MB, con Python dentro.`;
  } else {
    boton.classList.remove("btn-verde"); boton.classList.add("btn-claro");
    boton.removeAttribute("href");
    boton.setAttribute("aria-disabled", "true");
    $("#nota-descarga").textContent = `No está construido en este equipo: ${p.como}`;
  }
}

function pintarOpciones(o) {
  estado.opciones = o;
  $("#tecla-base").innerHTML = "<option value=''>(solo modificadores)</option>" + o.teclas.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#raton").innerHTML = o.raton.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#multimedia").innerHTML = o.multimedia.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#programa").innerHTML = o.programas.map(p => `<option value="${p.id}">${p.nombre}</option>`).join("");
  $("#host_panel").innerHTML = (o.direcciones || ["127.0.0.1"]).map(d =>
    `<option value="${d}">${d === "127.0.0.1" ? "Solo este equipo (127.0.0.1)" : d + (d.startsWith("100.") ? " (Tailscale)" : "")}</option>`).join("");
  $("#host_panel").value = o.escuchando_en || "127.0.0.1";
}

// --- editor de pieza ---------------------------------------------------------------

function elegirPieza(i) {
  estado.piezaElegida = i;
  const p = estado.panorama || {};
  const actual = (p.teclas_deseadas || [])[i] || (p.mapa || [])[i] || "";
  const nombres = p.piezas || [];
  $("#editor-cuerpo").hidden = false;
  $(".editor-titulo", $("#editor")).textContent = (nombres[i] || `Pieza ${i + 1}`).replace(/^./, c => c.toUpperCase());
  $(".editor-sub", $("#editor")).textContent = i === 2
    ? "Normalmente es la del micrófono. Se le puede poner otra cosa, pero entonces no abre el dictado."
    : (i >= 3 ? "La perilla admite lo mismo que una tecla: ratón, multimedia o cualquier combinación." : "Elige una familia y lo que quieres que haga.");
  elegirFamilia(familiaDe(actual));
  if (estado.familia === "raton") $("#raton").value = actual;
  else if (estado.familia === "multimedia") $("#multimedia").value = actual;
  else { $("#combo").value = actual; desmontarCombo(actual); }
  $("#btn-tecla-mic").hidden = i !== 2;
  $("#nota-tecla").textContent = "";
  pintar(p);
}

function elegirFamilia(familia) {
  estado.familia = familia;
  $$("#familias button").forEach(b => b.classList.toggle("activo", b.dataset.familia === familia));
  ["teclado", "raton", "multimedia"].forEach(f => { $("#familia-" + f).hidden = f !== familia; });
}

function desmontarCombo(combo) {
  const partes = combo ? combo.split("-") : [];
  $$("#mods input").forEach(c => { c.checked = partes.includes(c.value); });
  const base = partes.find(x => !MODIFICADORES.includes(x)) || "";
  $("#tecla-base").value = base;
}

function montarCombo() {
  const mods = $$("#mods input").filter(c => c.checked).map(c => c.value);
  const base = $("#tecla-base").value;
  const partes = base ? [...mods, base] : mods;
  $("#combo").value = partes.join("-") || "nada";
}

function comboElegido() {
  if (estado.familia === "raton") return $("#raton").value;
  if (estado.familia === "multimedia") return $("#multimedia").value;
  return $("#combo").value.trim().toLowerCase() || "nada";
}

async function guardarPieza(combo) {
  if (estado.piezaElegida === null) return;
  const teclas = [...(estado.panorama.teclas_deseadas || [])];
  teclas[estado.piezaElegida] = combo;
  const r = await pedir("/api/teclas", { teclas });
  avisar(r.escrito ? "Grabado en el teclado" : (r.aviso || "Guardado"));
  await refrescar();
}

// --- acciones ---------------------------------------------------------------------

function conectar() {
  $$(".tab").forEach(t => t.addEventListener("click", () => irA(t.dataset.seccion)));
  $$(".tema button").forEach(b => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  $$("[data-tecla]").forEach(b => b.addEventListener("click", () => elegirPieza(Number(b.dataset.tecla))));
  $$("#familias button").forEach(b => b.addEventListener("click", () => elegirFamilia(b.dataset.familia)));
  $$("#mods input").forEach(c => c.addEventListener("change", montarCombo));
  $("#tecla-base").addEventListener("change", montarCombo);
  $("#combo").addEventListener("input", () => desmontarCombo($("#combo").value.trim().toLowerCase()));
  $("#btn-guardar-tecla").addEventListener("click", () => guardarPieza(comboElegido()).catch(() => {}));
  $("#btn-tecla-mic").addEventListener("click", () => guardarPieza(ATAJO_MICROFONO).catch(() => {}));
  $("#btn-releer").addEventListener("click", async () => { await pedir("/api/teclas/leer", {}); avisar("Leído del teclado"); await refrescar(); });
  $("#btn-recomendado").addEventListener("click", async () => {
    const r = await pedir("/api/teclas/recomendado", {}); avisar(r.escrito ? "Teclado como recomienda SikaiMini" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-fabrica").addEventListener("click", async () => {
    if (!confirm("¿Devolver las teclas y la perilla a como venían de fábrica? La tecla del micrófono dejará de abrir el dictado y la perilla volverá a ser el volumen.")) return;
    const r = await pedir("/api/teclas/fabrica", {}); avisar(r.escrito ? "Teclado como venía" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-luces").addEventListener("click", async () => {
    const r = await pedir("/api/luces", { modo: Number($("#luces-modo").value), color: $("#luces-color").value });
    avisar(r.escrito ? "Luces grabadas en el teclado" : (r.aviso || "Guardado")); await refrescar();
  });
  $("#btn-luces-leer").addEventListener("click", async () => { await pedir("/api/luces/leer", {}); avisar("Luces leídas"); await refrescar(); });
  $("#paleta").addEventListener("click", e => { const b = e.target.closest("[data-color]"); if (b) $("#luces-color").value = b.dataset.color; });
  $$("#modo-mic button").forEach(b => b.addEventListener("click", async () => {
    const r = await pedir("/api/microfono", { modo: Number(b.dataset.modo) });
    avisar(r.escrito ? "Modo grabado en el teclado" : (r.aviso || "Guardado")); await refrescar();
  }));
  $("#btn-adoptar").addEventListener("click", async () => { const r = await pedir("/api/microfono/adoptar", {}); avisar(r.es_el_del_sistema ? "El micrófono del teclado ya es el del sistema" : "No encuentro el micrófono del teclado"); await refrescar(); });
  $("#btn-probar-dictado").addEventListener("click", async () => { const r = await pedir("/api/dictado/probar", {}); avisar("Dictado: " + (r.accion || "?")); });
  $("#programa").addEventListener("change", async () => { await pedir("/api/ajustes", { programa: $("#programa").value }); avisar("Ahora le hablas a " + $("#programa option:checked").textContent); await refrescar(); });
  $("#adoptar_microfono").addEventListener("change", async () => { await pedir("/api/ajustes", { adoptar_microfono: $("#adoptar_microfono").checked }); });
  $("#btn-guardar-dictado").addEventListener("click", async () => {
    await pedir("/api/ajustes", {
      usar_microfono_propio: $("#usar_microfono_propio").checked,
      pinchar_cuadro: $("#pinchar_cuadro").checked, enviar_al_cerrar: $("#enviar_al_cerrar").checked,
      pitido_al_abrir: $("#pitido_al_abrir").checked, alto_cuadro: Number($("#alto_cuadro").value) || 0,
    });
    avisar("Guardado");
  });
  $("#btn-guardar-host").addEventListener("click", async () => {
    const host = $("#host_panel").value;
    const r = await pedir("/api/ajustes", { host_panel: host });
    if (r.reabriendo && host !== "127.0.0.1") {
      avisar(`El panel se está moviendo a http://${host}:8772. Si esta pestaña deja de responder, ábrelo ahí.`);
    } else {
      avisar("Guardado");
    }
  });
  $("#btn-guardar-atajos").addEventListener("click", async () => {
    await pedir("/api/ajustes", { atajos_dictado: { chatgpt: $("#atajo_chatgpt").value.trim(), claude: $("#atajo_claude").value.trim() } });
    avisar("Atajos guardados; ya se usan");
  });
  $("#btn-registro").addEventListener("click", async () => {
    const r = await pedir("/api/registro");
    const pre = $("#registro");
    pre.hidden = false;
    pre.textContent = (r.lineas && r.lineas.length) ? r.lineas.join("
") : `Sin registro en ${r.ruta}`;
    pre.scrollTop = pre.scrollHeight;
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
    avisar("Clave cambiada. La próxima visita la pedirá.");
  });
}

async function refrescar() {
  pintar(await pedir("/api/estado"));
}

function escuchar() {
  const fuente = new EventSource("/api/sucesos");
  fuente.addEventListener("bienvenida", e => { $("#chip-vivo").hidden = false; pintar(JSON.parse(e.data)); });
  fuente.addEventListener("estado", e => pintar(JSON.parse(e.data)));
  fuente.addEventListener("pulsacion", e => {
    const d = JSON.parse(e.data);
    const b = $(`[data-tecla="${(d.tecla || 3) - 1}"]`);
    if (b) { b.classList.add("pulsada"); setTimeout(() => b.classList.remove("pulsada"), 350); }
    avisar(`Tecla del micrófono: ${d.accion} (${d.programa}, ${d.con_el_propio ? "micrófono propio" : "Win+H"})`);
  });
  fuente.onerror = () => {
    $("#chip-vivo").hidden = true;
    if ($("#ind-conexion").textContent === "Esperando…") $("#ind-conexion").textContent = "sin canal en vivo; reintentando";
  };
}

(async function arrancar() {
  let tema = "sistema";
  try { tema = localStorage.getItem("sikaimini-tema") || "sistema"; } catch (e) { /* nada */ }
  aplicarTema(tema);
  conectar();
  if (location.hash.length > 1) irA(location.hash.slice(1));
  try {
    pintarPaquete(await pedir("/api/paquete"));
    pintarOpciones(await pedir("/api/opciones"));
    pintarAjustes(await pedir("/api/ajustes"));
    await refrescar();
  } catch (e) {
    $("#ind-conexion").textContent = "el servicio no contesta (" + (e && e.message ? e.message : e) + ")";
  }
  escuchar();
  // Si el canal en vivo no llega, se sigue preguntando cada pocos segundos.
  setInterval(() => { if ($("#chip-vivo").hidden) refrescar().catch(() => {}); }, 5000);
})();
