/* MiniMic — guion del panel. Sin librerías. */
"use strict";

const estado = {
  panorama: null,
  opciones: null,
  ajustes: null,
  teclaElegida: null,
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

function nombreBonito(combo) {
  if (!combo || combo === "nada") return "nada";
  const nombres = { ctrl: "Ctrl", mayus: "Mayús", alt: "Alt", win: "Win", rctrl: "Ctrl der.", rmayus: "Mayús der.", ralt: "Alt der.", rwin: "Win der.",
    intro: "Intro", retroceso: "Retroceso", espacio: "Espacio", esc: "Esc", supr: "Supr", tab: "Tab" };
  return combo.split("-").map(p => nombres[p] || p.toUpperCase()).join(" + ");
}

// --- tema y pestañas --------------------------------------------------------------

function aplicarTema(tema) {
  if (tema === "sistema") delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
  try { localStorage.setItem("minimic-tema", tema); } catch (e) { /* sin memoria */ }
  $$(".tema button").forEach(b => b.classList.toggle("activo", b.dataset.tema === tema));
}

function irA(nombre) {
  $$(".tab").forEach(t => t.classList.toggle("activa", t.dataset.seccion === nombre));
  $$(".seccion").forEach(s => s.classList.toggle("activa", s.id === "seccion-" + nombre));
  history.replaceState(null, "", "#" + nombre);
}

// --- pintar ---------------------------------------------------------------------

function pintar(p) {
  estado.panorama = p;
  const c = p.conexion;
  $("#ind-conexion").textContent = c.descripcion;
  $("#ind-microfono").textContent = p.microfono.nombre ? (p.microfono.es_el_del_sistema ? "el del teclado" : "hay otro puesto") : "no está";
  $("#ind-dictado").textContent = p.dictado.abierto ? "abierto en " + p.dictado.programa : "cerrado";
  $("#atajo-texto").textContent = p.dictado.atajo.replace(/\+/g, " + ").replace("may", "Mayús").replace("ctrl", "Ctrl").replace("alt", "Alt").replace("f14", "F14");

  const banda = $("#banda-teclado");
  if (!c.conectado) {
    banda.hidden = false;
    banda.textContent = "No veo el teclado. Conéctalo por cable para configurarlo, o enchufa su receptor de 2,4 GHz para usarlo.";
  } else if (!c.configurable) {
    banda.hidden = false;
    banda.textContent = "El teclado va por el receptor de 2,4 GHz: funciona, pero para cambiarle las teclas hay que conectarlo por cable. Lo que ves es lo último que se le leyó.";
  } else {
    banda.hidden = true;
  }

  const mapa = p.mapa || [];
  const deseadas = p.teclas_deseadas || [];
  $$(".tecla-mm").forEach(b => {
    const i = Number(b.dataset.tecla);
    const que = mapa[i] || "?";
    $(".que", b).textContent = nombreBonito(que);
    const quiere = $(".quiere", b);
    quiere.textContent = (deseadas[i] && deseadas[i] !== que) ? "→ " + nombreBonito(deseadas[i]) + " (pendiente)" : "";
    b.classList.toggle("elegida", estado.teclaElegida === i);
  });
  $("#micro").classList.toggle("activo", !!p.dictado.abierto);

  // micrófono
  const punto = $("#punto-mic");
  punto.className = "estado-punto " + (p.microfono.nombre ? (p.microfono.es_el_del_sistema ? "si" : "no") : "");
  $("#texto-mic").textContent = p.microfono.nombre
    ? (p.microfono.es_el_del_sistema ? "El micrófono del teclado es el del sistema." : "El teclado está, pero el micrófono del sistema es otro.")
    : "No hay micrófono del teclado a la vista.";
  $$("#modo-mic button").forEach(b => b.classList.toggle("activo", Number(b.dataset.modo) === p.modo_microfono));
  $("#nota-dictado").textContent = p.dictado.atajo_reservado === false
    ? "La combinación de la tecla blanca no se pudo reservar: ¿hay otra copia del servicio viva?"
    : "";
  $("#texto-servicio").textContent = `MiniMic ${p.version}. Teclado ${c.descripcion}.`;
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
  const sel = $("#tecla-base");
  sel.innerHTML = "<option value=''>(solo modificadores)</option>" + o.teclas.map(t => `<option value="${t}">${nombreBonito(t)}</option>`).join("");
  $("#programa").innerHTML = o.programas.map(p => `<option value="${p.id}">${p.nombre}</option>`).join("");
  $("#host_panel").innerHTML = (o.direcciones || ["127.0.0.1"]).map(d =>
    `<option value="${d}">${d === "127.0.0.1" ? "Solo este equipo (127.0.0.1)" : d + (d.startsWith("100.") ? " (Tailscale)" : "")}</option>`).join("");
  $("#host_panel").value = o.escuchando_en || "127.0.0.1";
}

// --- editor de tecla ---------------------------------------------------------------

function elegirTecla(i) {
  estado.teclaElegida = i;
  const p = estado.panorama || {};
  const actual = (p.teclas_deseadas || [])[i] || (p.mapa || [])[i] || "";
  $("#editor-cuerpo").hidden = false;
  $(".editor-titulo", $("#editor")).textContent = i === 4 ? "Tecla 5 · la blanca" : `Tecla ${i + 1}`;
  $(".editor-sub", $("#editor")).textContent = i === 4
    ? "Normalmente es la del micrófono. Se le puede poner otra cosa, pero entonces no abre el dictado."
    : "Elige modificadores y una tecla, o escribe la combinación a mano.";
  $("#combo").value = actual;
  desmontarCombo(actual);
  $("#btn-tecla-mic").hidden = false;
  $("#nota-tecla").textContent = "";
  pintar(p);
}

function desmontarCombo(combo) {
  const partes = combo ? combo.split("-") : [];
  $$("#mods input").forEach(c => { c.checked = partes.includes(c.value); });
  const base = partes.find(x => !["ctrl", "mayus", "alt", "win", "rctrl", "rmayus", "ralt", "rwin"].includes(x)) || "";
  $("#tecla-base").value = base;
}

function montarCombo() {
  const mods = $$("#mods input").filter(c => c.checked).map(c => c.value);
  const base = $("#tecla-base").value;
  const partes = base ? [...mods, base] : mods;
  $("#combo").value = partes.join("-") || "nada";
}

async function guardarTecla(combo) {
  if (estado.teclaElegida === null) return;
  const teclas = [...(estado.panorama.teclas_deseadas || [])];
  teclas[estado.teclaElegida] = combo;
  const r = await pedir("/api/teclas", { teclas });
  avisar(r.escrito ? "Grabado en el teclado" : (r.aviso || "Guardado"));
  await refrescar();
}

// --- acciones ---------------------------------------------------------------------

function conectar() {
  $$(".tab").forEach(t => t.addEventListener("click", () => irA(t.dataset.seccion)));
  $$(".tema button").forEach(b => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  $$(".tecla-mm").forEach(b => b.addEventListener("click", () => elegirTecla(Number(b.dataset.tecla))));
  $$("#mods input").forEach(c => c.addEventListener("change", montarCombo));
  $("#tecla-base").addEventListener("change", montarCombo);
  $("#combo").addEventListener("input", () => desmontarCombo($("#combo").value.trim().toLowerCase()));
  $("#btn-guardar-tecla").addEventListener("click", () => guardarTecla($("#combo").value.trim().toLowerCase() || "nada").catch(() => {}));
  $("#btn-tecla-mic").addEventListener("click", () => guardarTecla("ctrl-mayus-alt-f14").catch(() => {}));
  $("#btn-releer").addEventListener("click", async () => { await pedir("/api/teclas/leer", {}); avisar("Leído del teclado"); await refrescar(); });
  $("#btn-fabrica").addEventListener("click", async () => {
    if (!confirm("¿Devolver las cinco teclas a como venían de fábrica? La blanca dejará de abrir el dictado.")) return;
    const r = await pedir("/api/teclas/fabrica", {}); avisar(r.escrito ? "Teclado como venía" : (r.aviso || "Guardado")); await refrescar();
  });
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
      avisar(`El panel se está moviendo a http://${host}:8771. Si esta pestaña deja de responder, ábrelo ahí.`);
    } else {
      avisar("Guardado");
    }
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
    const b = $(`.tecla-mm[data-tecla="${(d.tecla || 5) - 1}"]`);
    if (b) { b.classList.add("pulsada"); setTimeout(() => b.classList.remove("pulsada"), 350); }
    avisar(`Tecla del micrófono: ${d.accion} (${d.programa}, ${d.con_el_propio ? "micrófono propio" : "Win+H"})`);
  });
  fuente.onerror = () => { $("#chip-vivo").hidden = true; };
}

(async function arrancar() {
  let tema = "sistema";
  try { tema = localStorage.getItem("minimic-tema") || "sistema"; } catch (e) { /* nada */ }
  aplicarTema(tema);
  conectar();
  if (location.hash.length > 1) irA(location.hash.slice(1));
  try {
    pintarPaquete(await pedir("/api/paquete"));
    pintarOpciones(await pedir("/api/opciones"));
    pintarAjustes(await pedir("/api/ajustes"));
    await refrescar();
  } catch (e) { /* ya se avisó */ }
  escuchar();
})();
