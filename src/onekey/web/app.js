/* OneKey — guion del panel. Sin librerías. */
"use strict";

const estado = { panorama: null, opciones: null, ajustes: null };

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

// --- tema y pestañas --------------------------------------------------------------

function aplicarTema(tema) {
  if (tema === "sistema") delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
  try { localStorage.setItem("onekey-tema", tema); } catch (e) { /* sin memoria */ }
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
    $("#ind-conexion").textContent = "error al pintar: " + (e && e.message ? e.message : e);
    console.error(e);
  }
}

function pintarDeVerdad(p) {
  estado.panorama = p;
  const b = p.boton || {};
  const mic = p.microfono || {};
  $("#ind-conexion").textContent = !b.buscado ? "sin nombre" : (b.conectado ? "conectado" : "no está");
  $("#ind-microfono").textContent = mic.nombre ? (mic.es_el_del_sistema ? "el del botón" : "hay otro puesto") : "no está";
  $("#ind-dictado").textContent = p.dictado.abierto ? "abierto en " + p.dictado.programa : "cerrado";

  const banda = $("#banda-boton");
  if (!b.buscado) {
    banda.hidden = false;
    banda.textContent = "No se busca ningún botón: pon su nombre Bluetooth a la derecha.";
  } else if (!b.conectado) {
    banda.hidden = false;
    banda.textContent = `No veo el botón «${b.nombre}». Enciéndelo (luz azul fija) y emparéjalo en Configuración › Bluetooth.`;
  } else if (!b.oyendo) {
    banda.hidden = false;
    banda.textContent = "El botón está, pero el servicio no consiguió apuntarse a Raw Input: mira el registro en Ajustes.";
  } else {
    banda.hidden = true;
  }

  const luz = $("#luz");
  luz.className = "luz " + (b.conectado ? "azul" : (b.buscado ? "roja" : ""));
  $("#luz-texto").textContent = b.conectado ? "azul: conectado" : (b.buscado ? "roja: esperando" : "apagado");
  $("#boton-dibujo").classList.toggle("grabando", !!p.dictado.abierto);

  const punto = $("#punto-boton");
  punto.className = "estado-punto " + (b.conectado ? "si" : (b.buscado ? "no" : ""));
  $("#texto-boton").textContent = b.conectado
    ? `«${b.nombre}» conectado (${b.direccion}). ${b.pulsaciones ? `${b.pulsaciones} pulsación(es) desde que arrancó el servicio.` : "Todavía no lo has pulsado."}`
    : (b.buscado ? `Buscando «${b.nombre}» cada tres segundos.` : "Sin botón que buscar.");
  $("#nota-boton").textContent = p.dictado.atajo_reservado === false
    ? "El gancho del Intro no se pudo poner: ¿hay otra copia del servicio viva?"
    : `Para probar sin el botón: ${p.dictado.atajo.replace(/\+/g, " + ").replace("may", "Mayús").replace("ctrl", "Ctrl").replace("alt", "Alt").replace("f17", "F17")}.`;

  const puntoMic = $("#punto-mic");
  puntoMic.className = "estado-punto " + (mic.nombre ? (mic.es_el_del_sistema ? "si" : "no") : "");
  $("#texto-mic").textContent = mic.nombre
    ? (mic.es_el_del_sistema ? `${mic.nombre} es el micrófono del sistema.` : `${mic.nombre} está, pero el micrófono del sistema es otro; se pondrá al pulsar.`)
    : "No hay micrófono del botón a la vista.";
  $("#nota-dictado").textContent = "";
  $("#texto-servicio").textContent = `OneKey ${p.version}. Botón ${b.conectado ? "conectado" : "no está"}.`;
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
  if (document.activeElement !== $("#boton_bluetooth")) $("#boton_bluetooth").value = a.boton_bluetooth || "";
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
    boton.href = "/descargar/" + p.nombre;
    boton.textContent = "Descargar " + p.nombre;
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
  $("#programa").innerHTML = o.programas.map(p => `<option value="${p.id}">${p.nombre}</option>`).join("");
  $("#host_panel").innerHTML = (o.direcciones || ["127.0.0.1"]).map(d =>
    `<option value="${d}">${d === "127.0.0.1" ? "Solo este equipo (127.0.0.1)" : d + (d.startsWith("100.") ? " (Tailscale)" : "")}</option>`).join("");
  $("#host_panel").value = o.escuchando_en || "127.0.0.1";
}

// --- acciones ---------------------------------------------------------------------

function conectar() {
  $$(".tab").forEach(t => t.addEventListener("click", () => irA(t.dataset.seccion)));
  $$(".tema button").forEach(b => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  $("#btn-buscar").addEventListener("click", async () => { const r = await pedir("/api/boton/buscar", {}); avisar(r.conectado ? `Botón «${r.nombre}» conectado` : `No veo «${r.nombre}»`); await refrescar(); });
  $("#btn-guardar-boton").addEventListener("click", async () => { await pedir("/api/ajustes", { boton_bluetooth: $("#boton_bluetooth").value.trim() }); avisar("Guardado; se busca con el nombre nuevo"); await refrescar(); });
  $("#btn-adoptar").addEventListener("click", async () => { const r = await pedir("/api/microfono/adoptar", {}); avisar(r.es_el_del_sistema ? "El micrófono del botón ya es el del sistema" : "No encuentro el micrófono del botón"); await refrescar(); });
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
    if (r.reabriendo && host !== "127.0.0.1") avisar(`El panel se está moviendo a http://${host}:8774. Si esta pestaña deja de responder, ábrelo ahí.`);
    else avisar("Guardado");
  });
  $("#btn-guardar-atajos").addEventListener("click", async () => {
    await pedir("/api/ajustes", { atajos_dictado: { chatgpt: $("#atajo_chatgpt").value.trim(), claude: $("#atajo_claude").value.trim() } });
    avisar("Atajos guardados; ya se usan");
  });
  $("#btn-registro").addEventListener("click", async () => {
    const r = await pedir("/api/registro");
    const pre = $("#registro");
    pre.hidden = false;
    pre.textContent = (r.lineas && r.lineas.length) ? r.lineas.join("\n") : `Sin registro en ${r.ruta}`;
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
    const b = $("#boton-dibujo");
    b.classList.add("pulsado"); setTimeout(() => b.classList.remove("pulsado"), 350);
    avisar(`${d.tecla === "intro" ? "Intro" : "Botón"}: ${d.accion} (${d.programa}${d.con_el_propio === undefined ? "" : (d.con_el_propio ? ", micrófono propio" : ", Win+H")})`);
  });
  fuente.onerror = () => {
    $("#chip-vivo").hidden = true;
    if ($("#ind-conexion").textContent === "Esperando…") $("#ind-conexion").textContent = "sin canal en vivo; reintentando";
  };
}

(async function arrancar() {
  let tema = "sistema";
  try { tema = localStorage.getItem("onekey-tema") || "sistema"; } catch (e) { /* nada */ }
  aplicarTema(tema);
  conectar();
  if (location.hash.length > 1) irA(location.hash.slice(1));
  try {
    await refrescar();
  } catch (e) {
    $("#ind-conexion").textContent = "el servicio no contesta (" + (e && e.message ? e.message : e) + ")";
  }
  escuchar();
  try {
    pintarOpciones(await pedir("/api/opciones"));
    pintarAjustes(await pedir("/api/ajustes"));
    pintarPaquete(await pedir("/api/paquete"));
  } catch (e) { /* ya se avisó */ }
  setInterval(() => { if ($("#chip-vivo").hidden) refrescar().catch(() => {}); }, 5000);
})();
