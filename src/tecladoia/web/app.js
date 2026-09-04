/* TecladoIA — guion del panel.
   Sin bibliotecas. La pantalla principal imita a la aplicación oficial: el
   teclado dibujado a la izquierda y, al pulsar una pieza, su editor a la
   derecha. Los cambios del servicio llegan por un canal de eventos. */

"use strict";

const $  = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => Array.from(raiz.querySelectorAll(s));

const estado = {
  opciones: null,
  panorama: null,
  modos: [],
  reglas: [],
  modo: 0,
  seleccion: {pieza: "tecla", indice: 0},
  pendientes: new Map(),
};

/* ------------------------------ utilidades ------------------------------ */

function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function pedir(ruta, cuerpo, metodo) {
  const opciones = {method: metodo || (cuerpo === undefined ? "GET" : "POST")};
  if (cuerpo !== undefined) {
    opciones.headers = {"Content-Type": "application/json"};
    opciones.body = JSON.stringify(cuerpo);
  }
  let respuesta;
  try {
    respuesta = await fetch(ruta, opciones);
  } catch (error) {
    avisar("No se pudo hablar con el servicio. ¿Sigue en marcha?", "mal");
    throw error;
  }
  let datos = {};
  try { datos = await respuesta.json(); } catch (_) {}
  if (!respuesta.ok) {
    avisar(datos.error || `Error ${respuesta.status}`, "mal");
    throw new Error(datos.error || respuesta.status);
  }
  return datos;
}

let relojAviso;
function avisar(texto, tipo) {
  const caja = $("#aviso");
  $("#aviso-texto").textContent = texto;
  caja.classList.remove("bien", "mal");
  if (tipo) caja.classList.add(tipo);
  caja.classList.add("visible");
  clearTimeout(relojAviso);
  relojAviso = setTimeout(() => caja.classList.remove("visible"), 4000);
}

const hora = (t) => t ? String(t).replace("T", " ").slice(0, 19) : "—";
const palancaEnPalabras = (v) =>
  v === null || v === undefined ? "sin lectura" : (v === 0 ? "Automático" : "Manual");

function bytes(texto) {
  return new TextEncoder().encode(texto || "").length;
}

/* --------------------------------- tema --------------------------------- */
/* Tres opciones: seguir al sistema, claro u oscuro. La elección se guarda en
   este navegador; «sistema» quita la marca y deja mandar a prefers-color-scheme. */

function aplicarTema(tema) {
  if (tema === "claro" || tema === "oscuro") {
    document.documentElement.setAttribute("data-tema", tema);
  } else {
    document.documentElement.removeAttribute("data-tema");
    tema = "sistema";
  }
  try { localStorage.setItem("tecladoia_tema", tema); } catch (_) {}
  $$(".tema [data-tema]").forEach((b) =>
    b.setAttribute("aria-pressed", b.dataset.tema === tema ? "true" : "false"));
}

function temaGuardado() {
  try { return localStorage.getItem("tecladoia_tema") || "sistema"; } catch (_) { return "sistema"; }
}

/* ------------------------------ navegación ------------------------------ */

function irA(nombre) {
  $$(".tab").forEach((b) => b.classList.toggle("activa", b.dataset.seccion === nombre));
  $$(".seccion").forEach((s) => s.classList.toggle("activa", s.id === `seccion-${nombre}`));
  if (location.hash !== `#${nombre}`) history.replaceState(null, "", `#${nombre}`);
  if (nombre === "bitacora") cargarBitacora();
}
$$(".tab").forEach((b) => b.addEventListener("click", () => irA(b.dataset.seccion)));

/* ------------------------- estado y encabezado -------------------------- */

function pintarEstado(panorama) {
  estado.panorama = panorama;
  const e = panorama.estado || {};
  const s = panorama.servicio || {};
  const conectado = !!e.conectado;
  const simulado = String(e.transporte || "").toLowerCase().includes("simulad");

  const indConexion = $("#ind-conexion");
  indConexion.className = "indicador " + (conectado ? (simulado ? "info" : "bien") : "aviso");
  $("#ind-conexion-valor").textContent = conectado
    ? (simulado ? "Simulado" : "Conectado")
    : "Esperando teclado";

  // Sin teclado, lo ultimo que se leyo ya no es noticia: es historia. Ensenarlo
  // como si fuera de ahora es lo que hacia que el panel dijera «no hay teclado»
  // y a la vez mostrara bateria y modo tan tranquilo, que no hay forma de
  // entenderlo mirandolo.
  $("#ind-bateria-valor").textContent =
    !conectado || e.bateria == null ? "—" : `${e.bateria} %`;
  $("#ind-bateria").className =
    "indicador" + (conectado && e.bateria != null && e.bateria < 20 ? " aviso" : "");

  const palanca = conectado ? palancaEnPalabras(e.palanca) : "Sin lectura";
  $("#ind-palanca-valor").textContent =
    palanca + (conectado && e.palanca_forzada ? " (virtual)" : "");
  $("#ind-palanca").className =
    "indicador " + (!conectado ? "aviso" : e.palanca === 0 ? "bien" : "aviso");

  $("#btn-conectar").textContent = conectado ? "Desconectar" : "Conectar dispositivo";
  $("#btn-conectar").className = "btn " + (conectado ? "btn-claro" : "btn-verde");
  $("#btn-buscar").disabled = !s.hay_bluetooth;

  // Aviso honesto sobre lo que esta copia puede o no puede hacer.
  const banda = $("#aviso-sin-teclado");
  if (!conectado) {
    banda.hidden = false;
    banda.className = "banda atencion";
    // Si sabemos por qué no entra, se dice. Repetir «enciéndelo y acércalo»
    // con el teclado encendido delante no ayuda a nadie: manda a hacer algo
    // que ya está hecho y deja a la persona mirando el aparato sin más pistas.
    const motivo = (e.motivo_sin_teclado || "").trim();
    const dormido = /dormid/i.test(motivo);
    banda.innerHTML = dormido
      ? `<b>El teclado está dormido.</b> Responde, pero su parte de
         configuración no despierta hasta que se le toca:
         <b>pulsa cualquiera de sus teclas</b> y el servicio entra solo en unos
         segundos. Mientras tanto la palanca no se puede leer, así que nada se
         aprueba solo.`
      : `<b>Todavía no hay teclado.</b> Enciéndelo y acércalo; el servicio lo
         conecta solo en cuanto aparezca. Si tienes abierta la aplicación oficial de AhaKey,
         ciérrala: solo un programa puede hablar con el teclado a la vez.
         Mientras tanto la palanca no se puede leer, así que nada se aprueba solo.
         ${motivo ? `<br><span class="nota">Lo último que dijo Windows: ${esc(motivo)}</span>` : ""}`;
  } else if (simulado) {
    banda.hidden = false;
    banda.className = "banda";
    banda.innerHTML = `<b>Teclado simulado.</b> Esta copia no tiene un AhaKey cerca.
      Sirve para preparar reglas y teclas; para gobernar el teclado de verdad,
      <button type="button" class="btn btn-claro" data-ir="descargar">descarga la aplicación</button>
      e instálala donde esté emparejado.`;
  } else {
    banda.hidden = true;
  }

  // Mientras escribe la pantalla, el teclado no atiende otra cosa. Decirlo
  // evita el desconcierto de ver la barra congelada y creer que está rota.
  const subida = s.subida;
  if (subida) {
    banda.hidden = false;
    banda.className = "banda";
    banda.innerHTML = `<b>Enviando la pantalla del modo ${subida.modo + 1}:
      ${subida.hecho} de ${subida.total} fotogramas.</b> Mientras dura, el teclado no
      cambia de luz ni de modo — su memoria se escribe en exclusiva.
      <button type="button" class="btn btn-claro" id="btn-cancelar-subida">Cancelar</button>`;
    const cancelar = $("#btn-cancelar-subida");
    if (cancelar) cancelar.addEventListener("click", async () => {
      const r = await pedir("/api/pantalla/cancelar", {});
      avisar(r.ok ? "Subida cancelada." : r.aviso, r.ok ? "bien" : "mal");
    });
  }

  // Barra de luz encendida solo si hay teclado de verdad.
  $(".barra-luz").classList.toggle("encendida", conectado);

  // La palanca dibujada.
  const enAuto = e.palanca === 0;
  $(".palanca").classList.toggle("manual", !enAuto);
  $("#palanca-pie").textContent = !conectado || e.palanca == null ? "Sin lectura" : palanca;

  // El teclado manda... salvo justo después de elegir un modo aquí. Sin esta
  // tregua, el sondeo de cada dos segundos devolvía la web al modo del aparato
  // y lo que subieras acababa en otro modo distinto del que estabas viendo.
  const eligioHacePoco = Date.now() - (estado.modoElegidoEn || 0) < 6000;
  // El modo tambien: sin teclado no se sabe en cual esta, y ensenar el ultimo
  // como si siguiera puesto hacia creer que se habia cambiado solo.
  document.body.classList.toggle("sin-lectura", !conectado);
  if (conectado && e.modo_trabajo != null && e.modo_trabajo !== estado.modo && !eligioHacePoco) {
    estado.modo = e.modo_trabajo;
    pintarModos();
    pintarTeclas();
  }

  pintarHistorial(panorama.historial || []);
  pintarAgentes(panorama.agentes || []);
  if (panorama.pendientes) sincronizarPendientes(panorama.pendientes);
  pintarEditor();
}

document.addEventListener("click", (e) => {
  const destino = e.target.closest("[data-ir]");
  if (destino) irA(destino.dataset.ir);
});

/* --------------------------- el teclado dibujado --------------------------- */

function pintarModos() {
  $("#modos").innerHTML = estado.modos.map((m, i) =>
    `<button type="button" role="tab" data-modo="${i}"
       aria-selected="${i === estado.modo}">${esc(m.nombre || `Modo ${i + 1}`)}</button>`).join("");
  $$("#modos button").forEach((b) => b.addEventListener("click", async () => {
    estado.modo = Number(b.dataset.modo);
    estado.modoElegidoEn = Date.now();
    pintarModos();
    pintarTeclas();
    pintarEditor();
    // Si hay teclado, se cambia también el modo activo del aparato.
    if (estado.panorama?.estado?.conectado) {
      const r = await pedir("/api/modo-trabajo", {modo: estado.modo});
      if (!r.ok) avisar("El teclado no aceptó el cambio de modo.", "mal");
    }
  }));

  const modo = estado.modos[estado.modo] || {};
  $("#oled-titulo").textContent = modo.nombre || `Modo ${estado.modo + 1}`;
  $("#oled-sub").textContent = `Modo ${estado.modo + 1}`;
  $("#numero-modo").textContent = estado.modo + 1;
}

function pintarTeclas() {
  const modo = estado.modos[estado.modo] || {teclas: []};
  $("#teclas").innerHTML = (modo.teclas || []).map((t, i) => {
    const valor = t.descripcion || t.atajo || ((t.macro || []).length ? "Macro" : "N/A");
    return `<button type="button" class="tecla ${t.vacia && !t.descripcion ? "vacia" : ""}"
        data-pieza="tecla" data-indice="${i}">
      <span class="tecla-nombre">K${i + 1}</span>
      <span class="tecla-valor">${esc(valor)}</span>
    </button>`;
  }).join("");
  marcarSeleccion();
}

function marcarSeleccion() {
  const s = estado.seleccion;
  $$(".tecla").forEach((b) =>
    b.classList.toggle("elegida", s.pieza === "tecla" && Number(b.dataset.indice) === s.indice));
  $$(".pieza").forEach((b) => b.classList.toggle("elegida", b.dataset.pieza === s.pieza));
}

document.addEventListener("click", (e) => {
  const pieza = e.target.closest("[data-pieza]");
  if (!pieza) return;
  estado.seleccion = {pieza: pieza.dataset.pieza, indice: Number(pieza.dataset.indice || 0)};
  marcarSeleccion();
  pintarEditor();
});

/* ------------------------------- el editor ------------------------------- */

const ICONOS = {
  tecla: '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M7 10h.01M12 10h.01M17 10h.01M8 14h8"/></svg>',
  luz: '<svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-3.5 10.9c.5.4.8 1 .8 1.6h5.4c0-.6.3-1.2.8-1.6A6 6 0 0012 3z"/></svg>',
  pantalla: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="14" rx="2.5"/><path d="M8 21h8M12 18v3"/></svg>',
  palanca: '<svg viewBox="0 0 24 24"><rect x="8" y="3" width="8" height="18" rx="4"/><circle cx="12" cy="8" r="2.4"/></svg>',
};

function pintarEditor() {
  const s = estado.seleccion;
  const caja = $("#editor");
  const nombreModo = estado.modos[estado.modo]?.nombre || `Modo ${estado.modo + 1}`;

  if (s.pieza === "tecla") caja.innerHTML = editorTecla(s.indice, nombreModo);
  else if (s.pieza === "luz") caja.innerHTML = editorLuz();
  else if (s.pieza === "pantalla") caja.innerHTML = editorPantalla(nombreModo);
  else if (s.pieza === "palanca") caja.innerHTML = editorPalanca();
  else caja.innerHTML = '<p class="vacio-editor">Elige una pieza del teclado.</p>';

  conectarEditor();
}

function cabecera(icono, titulo, sub) {
  return `<h2 class="editor-titulo">${ICONOS[icono]} ${esc(titulo)}</h2>
          <p class="editor-sub">${esc(sub)}</p>`;
}

/* ---- tecla ---- */
function editorTecla(indice, nombreModo) {
  const t = estado.modos[estado.modo]?.teclas?.[indice] || {};
  const esMacro = (t.macro || []).length > 0;
  const codigos = t.atajo ? t.atajo.split("+").filter(Boolean) : [];
  const mods = estado.opciones?.modificadores || [];
  const teclas = estado.opciones?.teclas || [];

  return cabecera("tecla", `Tecla ${indice + 1} · ${esMacro ? "Macro" : "Atajo"}`,
                  `${nombreModo} · se escribe en la memoria del teclado`) + `
  <div class="bloque">
    <p class="bloque-titulo">Lo que se escribirá en el teclado</p>

    <div class="campo">
      <label for="ed-tipo">Tipo de tecla</label>
      <select id="ed-tipo">
        <option value="atajo" ${esMacro ? "" : "selected"}>Atajo</option>
        <option value="macro" ${esMacro ? "selected" : ""}>Macro de texto</option>
      </select>
    </div>

    <div id="ed-zona-atajo" ${esMacro ? "hidden" : ""}>
      <div class="campo">
        <label for="ed-codigos">Lista de códigos (modificadores primero, teclas normales después)</label>
        <select id="ed-codigos" multiple size="5">
          ${codigos.map((c) => `<option value="${esc(c)}">${esc(etiquetaCodigo(c))}</option>`).join("")}
        </select>
      </div>
      <div class="linea-controles">
        <select id="ed-mod"><option value="">— Modificador —</option>
          ${mods.map((m) => `<option value="${esc(m.nombre)}">${esc(m.nombre)}</option>`).join("")}
        </select>
        <select id="ed-tecla"><option value="">— Tecla —</option>
          ${teclas.map((k) => `<option value="${esc(k.nombre)}">${esc(k.nombre)} (0x${k.codigo.toString(16).toUpperCase().padStart(2,"0")})</option>`).join("")}
        </select>
      </div>
      <div class="acciones">
        <button type="button" class="btn btn-claro" id="ed-anadir">Añadir</button>
        <button type="button" class="btn btn-claro" id="ed-quitar">Quitar</button>
        <button type="button" class="btn btn-claro" id="ed-capturar">Capturar pulsación</button>
      </div>
    </div>

    <div id="ed-zona-macro" ${esMacro ? "" : "hidden"}>
      <div class="campo">
        <label for="ed-macro">Texto que debe teclear</label>
        <textarea id="ed-macro" placeholder="Escribe aquí lo que la tecla debe escribir"></textarea>
      </div>
      <p class="nota">
        ${esMacro ? "Esta tecla ya tiene una macro guardada en el teclado. Escribe otra vez el texto para reemplazarla." : "Las tildes y la eñe se escriben con la distribución española."}
      </p>
    </div>
  </div>

  <div class="bloque">
    <p class="bloque-titulo">Descripción de la tecla</p>
    <div class="campo">
      <input id="ed-desc" maxlength="20" value="${esc(t.descripcion || "")}" placeholder="Yes">
    </div>
    <p class="nota">Es lo que se ve en la pantalla del teclado. Máximo 20 caracteres;
       lo que la pantalla no sabe dibujar se translitera.</p>
    <p class="nota" id="ed-desc-cuenta"></p>
  </div>

  <div class="acciones">
    <button type="button" class="btn btn-azul" id="ed-guardar">Guardar en el teclado</button>
    <button type="button" class="btn btn-claro" id="ed-vaciar">Vaciar tecla</button>
  </div>
  <p class="nota" id="ed-resultado"></p>`;
}

function etiquetaCodigo(nombre) {
  const buscar = (lista) => (lista || []).find((x) => x.nombre === nombre);
  const encontrado = buscar(estado.opciones?.modificadores) || buscar(estado.opciones?.teclas);
  return encontrado
    ? `${nombre} (0x${encontrado.codigo.toString(16).toUpperCase().padStart(2, "0")})`
    : nombre;
}

/* ---- barra de luz ---- */
function editorLuz() {
  const efectos = estado.opciones?.efectos || [];
  const luces = estado.luces || [];
  const brillo = estado.panorama?.ajustes?.brillo ?? 35;

  const filas = luces.map((l) => `
    <div class="fila-luz">
      <div>
        <b>${esc(l.etiqueta)}</b>
        <div class="nota">${esc(l.descripcion)}</div>
      </div>
      <select data-luz="${l.estado}">
        ${efectos.map((f) => `<option value="${f.codigo}" ${f.codigo === l.efecto ? "selected" : ""}>${esc(f.etiqueta)}${f.color ? " · " + esc(f.color) : ""}</option>`).join("")}
      </select>
      <button type="button" class="btn btn-claro" data-probar-luz="${l.estado}" title="Enciéndelo ahora en el teclado">Ver</button>
    </div>`).join("");

  return cabecera("luz", "Barra de luz", "Un efecto para cada momento del agente") + `
  <div class="bloque">
    <p class="bloque-titulo">Qué enciende cada momento</p>
    <p class="nota" style="margin-top:0">
      La barra no es un adorno: es lo que te dice, sin mirar la pantalla, si el agente
      está pensando, si terminó o si te está esperando. Por eso el efecto va atado al
      estado, no elegido a mano una vez.
    </p>
    <div class="luces">${filas}</div>
    <div class="acciones">
      <button type="button" class="btn btn-azul" id="ed-guardar-luces">Guardar en el teclado</button>
      <button type="button" class="btn btn-claro" id="ed-colores">Anotar colores</button>
    </div>
    <p class="nota" id="ed-luces-resultado"></p>
  </div>

  <div class="bloque">
    <p class="bloque-titulo">Brillo</p>
    <div class="campo">
      <label for="ed-brillo">Nivel <b id="ed-brillo-valor">${brillo} %</b></label>
      <input type="range" id="ed-brillo" min="0" max="100" step="5" value="${brillo}">
    </div>
    <div class="acciones">
      <button type="button" class="btn btn-claro" id="ed-aplicar-brillo">Aplicar brillo</button>
    </div>
  </div>`;
}

/* ---- pantalla ---- */
function editorPantalla(nombreModo) {
  return cabecera("pantalla", "Pantalla del teclado", `${nombreModo} · 160 × 80 puntos`) + `
  <div class="bloque">
    <p class="bloque-titulo">Nombre del modo</p>
    <div class="campo">
      <input id="ed-nombre-modo" maxlength="20" value="${esc(nombreModo)}">
    </div>
    <div class="acciones">
      <button type="button" class="btn btn-claro" id="ed-guardar-modo">Guardar nombre</button>
    </div>
  </div>

  <div class="bloque">
    <p class="bloque-titulo">Imagen o GIF</p>
    <div class="campo">
      <input type="file" id="ed-archivo" accept="image/png,image/jpeg,image/gif,image/webp">
    </div>
    <div id="ed-vista" hidden>
      <img id="ed-vista-img" alt="Lo que se verá en la pantalla del teclado">
      <p class="nota" id="ed-vista-datos"></p>
    </div>
    <div class="campo">
      <label for="ed-retardo">Milisegundos entre fotogramas (solo para GIF)</label>
      <input type="number" id="ed-retardo" min="20" max="2000" step="10" value="100">
    </div>
    <div class="acciones">
      <button type="button" class="btn btn-azul" id="ed-subir" disabled>
        Enviar al modo ${esc(nombreModo)}
      </button>
    </div>
    <p class="nota"><b>Va al modo ${esc(nombreModo)}</b> y solo a ese: cada modo
       tiene su propio tramo de memoria, así que no toca los otros tres.</p>
    <p class="nota">
      PNG, JPG, GIF o WebP, hasta 2 MB. La imagen se recorta y se ajusta sola a
      160 × 80; de un GIF se toman hasta 70 fotogramas. Cada modo guarda la suya,
      así que cambiar esta no toca las de los demás.
    </p>
    <p class="nota" id="ed-subir-resultado"></p>
  </div>`;
}

/* ---- palanca ---- */
/* La palanca es física y no se toca desde aquí: mandarla a distancia sería
   contradecir el interruptor que tienes en la mano. Esta pantalla solo cuenta
   en qué posición está y qué hace cada una. */
function editorPalanca() {
  const e = estado.panorama?.estado || {};
  const modo = estado.panorama?.ajustes?.modo_aprobacion || "palanca";
  const arriba = e.palanca === 0;
  const sinLectura = e.palanca === null || e.palanca === undefined;

  const posicion = sinLectura ? "sin lectura" : (arriba ? "arriba" : "abajo");
  const clase = sinLectura ? "aviso" : (arriba ? "bien" : "info");

  return cabecera("palanca", "Palanca",
                  "El interruptor físico del teclado") + `
  <div class="bloque">
    <p class="bloque-titulo">Ahora está <b>${esc(posicion)}</b></p>
    <div class="posiciones">
      <div class="posicion ${arriba && !sinLectura ? "activa" : ""}">
        <span class="posicion-donde">Arriba</span>
        <span class="posicion-que">Al cerrar el micrófono, <b>el texto se envía solo</b>.</span>
        <span class="posicion-que">El agente ejecuta sus herramientas sin preguntarte.</span>
      </div>
      <div class="posicion ${!arriba && !sinLectura ? "activa" : ""}">
        <span class="posicion-donde">Abajo</span>
        <span class="posicion-que">Al cerrar el micrófono, <b>revisas y envías tú</b>.</span>
        <span class="posicion-que">Cada acción del agente vuelve a tus manos.</span>
      </div>
    </div>
    ${sinLectura && !e.palanca_forzada ? `<p class="nota atencion">No se puede leer la
       palanca. Mientras tanto no se aprueba nada solo: no saber equivale a
       preguntar.</p>` : ""}
    <p class="nota">La palanca no escribe nada en el ordenador. Cambia dos cosas:
       si lo dictado se manda solo, y qué hace el servicio con las peticiones de
       permiso de los agentes.</p>
  </div>

  <div class="bloque">
    <p class="bloque-titulo">Fijarla desde aquí</p>
    <p class="nota">Lo normal es moverla con la mano y que esto solo la mire: un
       interruptor que se cambia a distancia deja de ser un interruptor. Pero una
       palanca se puede romper, y entonces el teclado no dice nada — y como no
       saber equivale a preguntar, te quedarías aprobando todo a mano para
       siempre. Para eso está esto.</p>
    <div class="opciones-palanca">
      <button type="button" class="btn ${!e.palanca_forzada ? "btn-azul" : "btn-claro"}"
              data-fijar-palanca="">Hacer caso al teclado</button>
      <button type="button" class="btn ${e.palanca_forzada && e.palanca === 0 ? "btn-azul" : "btn-claro"}"
              data-fijar-palanca="0">Fijar arriba</button>
      <button type="button" class="btn ${e.palanca_forzada && e.palanca === 1 ? "btn-azul" : "btn-claro"}"
              data-fijar-palanca="1">Fijar abajo</button>
    </div>
    ${e.palanca_forzada ? `<p class="nota atencion">Fijada <b>${arriba ? "arriba" : "abajo"}</b>
       desde aquí. El teclado ya no manda sobre esto, y se recuerda al reiniciar.</p>` : ""}
    <p class="nota">Ojo: fijarla arriba es decirle al servicio que apruebe solo.
       Las reglas de <b>denegar</b> y <b>preguntar</b> siguen ganando siempre —ahí
       viven <code>rm -rf</code> y compañía—, pero todo lo demás pasa sin
       consultarte.</p>
  </div>`;
}

/* ---- conexiones del editor ---- */
function conectarEditor() {
  const s = estado.seleccion;

  // Fijar la palanca a mano. Existe porque una palanca se puede romper.
  $$("[data-fijar-palanca]").forEach((boton) => {
    boton.addEventListener("click", async () => {
      const crudo = boton.dataset.fijarPalanca;
      const valor = crudo === "" ? null : Number(crudo);
      const r = await pedir("/api/palanca", { valor });
      if (r && r.estado) pintarEstado(r);
      pintarEditor();
      avisar(valor === null
        ? "La palanca vuelve a mandarla el teclado."
        : `Palanca fijada ${valor === 0 ? "arriba" : "abajo"}.`, "bien");
    });
  });

  if (s.pieza === "tecla") {
    const tipo = $("#ed-tipo");
    tipo.addEventListener("change", () => {
      $("#ed-zona-atajo").hidden = tipo.value !== "atajo";
      $("#ed-zona-macro").hidden = tipo.value !== "macro";
    });

    const lista = $("#ed-codigos");
    const anadir = (nombre) => {
      if (!nombre) return;
      if (Array.from(lista.options).some((o) => o.value === nombre)) return;
      lista.add(new Option(etiquetaCodigo(nombre), nombre));
    };
    $("#ed-anadir").addEventListener("click", () => {
      anadir($("#ed-mod").value);
      anadir($("#ed-tecla").value);
      $("#ed-mod").value = ""; $("#ed-tecla").value = "";
    });
    $("#ed-quitar").addEventListener("click", () => {
      Array.from(lista.selectedOptions).forEach((o) => o.remove());
    });

    $("#ed-capturar").addEventListener("click", (evento) => {
      const boton = evento.currentTarget;
      boton.textContent = "Pulsa la combinación…";
      lista.classList.add("capturando");
      const alPulsar = (ev) => {
        ev.preventDefault();
        const partes = atajoDesdeEvento(ev);
        if (!partes) return;
        lista.innerHTML = "";
        partes.forEach(anadir);
        terminar();
      };
      const terminar = () => {
        document.removeEventListener("keydown", alPulsar, true);
        lista.classList.remove("capturando");
        boton.textContent = "Capturar pulsación";
      };
      document.addEventListener("keydown", alPulsar, true);
      setTimeout(() => { if (lista.classList.contains("capturando")) terminar(); }, 8000);
    });

    const desc = $("#ed-desc");
    const contar = () => {
      const n = bytes(desc.value);
      $("#ed-desc-cuenta").textContent =
        `El teclado escribirá: ${desc.value || "(nada)"} — ${n} de 20 bytes`;
    };
    desc.addEventListener("input", contar);
    contar();

    $("#ed-guardar").addEventListener("click", () => guardarTecla(false));
    $("#ed-vaciar").addEventListener("click", () => guardarTecla(true));
  }

  if (s.pieza === "luz") {
    $("#ed-brillo").addEventListener("input", (e) =>
      $("#ed-brillo-valor").textContent = `${e.target.value} %`);
    $("#ed-aplicar-brillo").addEventListener("click", async () => {
      const r = await pedir("/api/brillo", {valor: Number($("#ed-brillo").value)});
      avisar(r.ok ? `Brillo al ${r.valor} %.` : "El teclado no está conectado.", r.ok ? "bien" : "mal");
    });

    $$("[data-probar-luz]").forEach((b) => b.addEventListener("click", async () => {
      const r = await pedir("/api/luces/probar", {estado: Number(b.dataset.probarLuz)});
      avisar(r.ok ? `Encendido: ${r.estado}` : "El teclado no está conectado.",
             r.ok ? "bien" : "mal");
    }));

    // El firmware no deja elegir el color: solo viaja el número del efecto y el
    // color va dentro de cada uno. Lo que sí se puede es anotar cuál es cuál,
    // mirando el teclado, y a partir de ahí elegir por color.
    $("#ed-colores").addEventListener("click", async () => {
      const efectos = (estado.opciones?.efectos || []).filter((f) => f.codigo !== 0);
      const caja = $("#ed-luces-resultado");
      for (const efecto of efectos) {
        await pedir("/api/luces/probar", {efecto: efecto.codigo});
        caja.innerHTML = `Encendido <b>${esc(efecto.etiqueta)}</b> — mira el teclado.`;
        const visto = prompt(
          "¿De qué color se ve «" + efecto.etiqueta + "»?  " +
          "Escríbelo (verde, rojo, azul, multicolor…), deja vacío para saltarlo, " +
          "o pulsa Cancelar para terminar el recorrido.",
          efecto.color || ""
        );
        if (visto === null) break;
        if (visto.trim()) {
          const r = await pedir("/api/colores", {colores: {[efecto.codigo]: visto.trim()}});
          estado.opciones.efectos = r.efectos;
        }
      }
      caja.textContent = "Colores anotados. Ya salen en la lista de cada momento.";
      await pedir("/api/luces/probar", {efecto: 0});
      pintarEditor();
    });

    $("#ed-guardar-luces").addEventListener("click", async () => {
      const luces = {};
      $$("[data-luz]").forEach((sel) => (luces[sel.dataset.luz] = Number(sel.value)));
      const r = await pedir("/api/luces", {luces, aplicar: true});
      estado.luces = r.luces;
      $("#ed-luces-resultado").textContent = r.guardado_en_el_teclado
        ? "Guardado en la memoria del teclado."
        : (r.aviso || "Guardado aquí; se escribirá cuando el teclado esté conectado.");
      avisar("Luces guardadas.", "bien");
    });
  }

  if (s.pieza === "pantalla") {
    let archivoEnBase64 = null;
    const entrada = $("#ed-archivo");
    entrada.addEventListener("change", () => {
      const archivo = entrada.files?.[0];
      if (!archivo) return;
      if (archivo.size > 2 * 1024 * 1024) {
        avisar("El archivo pesa más de 2 MB.", "mal");
        entrada.value = "";
        return;
      }
      const lector = new FileReader();
      lector.onload = () => {
        archivoEnBase64 = String(lector.result);
        $("#ed-vista-img").src = archivoEnBase64;
        $("#ed-vista-datos").textContent =
          `${archivo.name} · ${(archivo.size / 1024).toFixed(0)} KB`;
        $("#ed-vista").hidden = false;
        $("#ed-subir").disabled = false;
      };
      lector.readAsDataURL(archivo);
    });

    const modoDestino = estado.modo;  // el que se ve ahora, pase lo que pase luego
    $("#ed-subir").addEventListener("click", async (e) => {
      if (!archivoEnBase64) return;
      const boton = e.currentTarget;
      boton.disabled = true;
      estado.modoElegidoEn = Date.now();
      $("#ed-subir-resultado").textContent = "Enviando… puede tardar un minuto si es un GIF.";
      try {
        const r = await pedir("/api/pantalla", {
          modo: modoDestino,
          datos: archivoEnBase64,
          retardo_ms: Number($("#ed-retardo").value) || 100,
        });
        $("#ed-subir-resultado").textContent = r.ok
          ? `Enviados ${r.fotogramas} fotogramas a ${r.retardo_ms} ms.`
          : r.error;
        avisar(r.ok ? "Pantalla actualizada." : r.error, r.ok ? "bien" : "mal");
      } finally {
        boton.disabled = false;
      }
    });

    $("#ed-guardar-modo").addEventListener("click", async () => {
      const t = estado.modos[estado.modo].teclas[0] || {};
      const r = await pedir("/api/teclas", {
        modo: estado.modo, indice: 0,
        atajo: t.atajo || "", descripcion: t.descripcion || "",
        nombre_modo: $("#ed-nombre-modo").value.trim(),
      });
      estado.modos = r.modos;
      pintarModos(); pintarTeclas(); pintarEditor();
      avisar("Nombre del modo guardado.", "bien");
    });
  }


}

async function guardarTecla(vaciar) {
  const indice = estado.seleccion.indice;
  const cuerpo = {modo: estado.modo, indice};
  if (!vaciar) {
    if ($("#ed-tipo").value === "atajo") {
      cuerpo.atajo = Array.from($("#ed-codigos").options).map((o) => o.value).join("+");
    } else {
      cuerpo.texto_macro = $("#ed-macro").value;
    }
    cuerpo.descripcion = $("#ed-desc").value.trim();
  }
  const r = await pedir("/api/teclas", cuerpo);
  estado.modos = r.modos;
  pintarTeclas();
  // El editor también, o se queda enseñando lo de antes y el siguiente guardado
  // reescribe esos valores viejos encima de lo que acabas de guardar.
  pintarEditor();
  $("#ed-resultado").textContent = r.escrita_en_el_teclado
    ? "Escrita en el teclado."
    : (r.aviso || "Guardada aquí. Se escribirá cuando el teclado esté conectado.");
  avisar(vaciar ? `Tecla ${indice + 1} vaciada.` : `Tecla ${indice + 1} guardada.`, "bien");
}

const TECLAS_ESPECIALES = {
  Enter:"intro", Escape:"esc", Backspace:"retroceso", Tab:"tab", " ":"espacio",
  Delete:"supr", Insert:"insertar", Home:"inicio", End:"fin",
  PageUp:"re_pag", PageDown:"av_pag",
  ArrowUp:"flecha_arriba", ArrowDown:"flecha_abajo",
  ArrowLeft:"flecha_izquierda", ArrowRight:"flecha_derecha",
};

function atajoDesdeEvento(ev) {
  const partes = [];
  if (ev.ctrlKey) partes.push("ctrl");
  if (ev.shiftKey) partes.push("may");
  if (ev.altKey) partes.push("alt");
  if (ev.metaKey) partes.push("cmd");
  const k = ev.key;
  let base = null;
  if (TECLAS_ESPECIALES[k]) base = TECLAS_ESPECIALES[k];
  else if (/^F\d{1,2}$/.test(k)) base = k.toLowerCase();
  else if (k && k.length === 1 && /[a-z0-9ñ]/i.test(k)) base = k.toLowerCase();
  if (!base) return null;
  partes.push(base);
  return partes;
}

/* ----------------------------- aprobaciones ----------------------------- */

function sincronizarPendientes(lista) {
  estado.pendientes.clear();
  lista.forEach((p) => estado.pendientes.set(p.id,
    {...p, vence: Date.now() + p.segundos_restantes * 1000}));
  pintarPendientes();
}
function anadirPendiente(p) {
  estado.pendientes.set(p.id, {...p, vence: Date.now() + (p.segundos_restantes || 25) * 1000});
  pintarPendientes();
  if (!document.hasFocus()) avisar("Un agente pide permiso", "mal");
}
function quitarPendiente(id) { estado.pendientes.delete(id); pintarPendientes(); }

function pintarPendientes() {
  const zona = $("#zona-pendientes");
  if (!estado.pendientes.size) { zona.innerHTML = ""; return; }
  zona.innerHTML = Array.from(estado.pendientes.values()).map((p) => {
    const orden = [p.herramienta, p.comando].filter(Boolean).join("  ") || "(sin detalle)";
    return `<div class="pendiente" data-id="${esc(p.id)}">
      <h3>${esc(p.agente)} pide permiso</h3>
      <p class="nota">${esc(p.explicacion || "")}</p>
      <code class="orden">${esc(orden)}</code>
      ${p.ruta ? `<p class="nota">En ${esc(p.ruta)}</p>` : ""}
      <div class="acciones">
        <button type="button" class="btn btn-verde" data-aprobar="permitir">Permitir</button>
        <button type="button" class="btn btn-claro peligro" data-aprobar="denegar">Denegar</button>
        <span class="nota">Quedan <b class="cuenta-atras">—</b> s para que decidas en la terminal.</span>
      </div>
    </div>`;
  }).join("");

  $$(".pendiente").forEach((caja) => {
    const id = caja.dataset.id;
    $$("[data-aprobar]", caja).forEach((b) => b.addEventListener("click", async () => {
      $$("[data-aprobar]", caja).forEach((o) => (o.disabled = true));
      const r = await pedir("/api/aprobar", {id, respuesta: b.dataset.aprobar});
      avisar(r.ok ? `Contestado: ${b.dataset.aprobar}` : (r.aviso || "Ya no estaba a tiempo"),
             r.ok ? "bien" : "mal");
      quitarPendiente(id);
    }));
  });
}

setInterval(() => {
  const ahora = Date.now();
  estado.pendientes.forEach((p, id) => {
    const quedan = Math.max(0, Math.round((p.vence - ahora) / 1000));
    const caja = document.querySelector(`.pendiente[data-id="${CSS.escape(id)}"] .cuenta-atras`);
    if (caja) caja.textContent = quedan;
    if (quedan <= 0) quitarPendiente(id);
  });
}, 1000);

/* -------------------------- historial y bitácora -------------------------- */

function filaDecision(h) {
  const accion = [h.herramienta, h.comando].filter(Boolean).join(" · ") || "—";
  const motivo = h.regla ? `regla: ${h.regla}` : String(h.motivo || "").replace(/_/g, " ");
  return `<tr><td>${esc(hora(h.instante))}</td><td>${esc(h.agente || "")}</td>
    <td>${esc(accion)}</td>
    <td><span class="etiqueta ${esc(h.decision)}">${esc(h.decision)}</span></td>
    <td>${esc(motivo)}</td></tr>`;
}

function pintarHistorial(filas) {
  $("#historial").innerHTML = filas.length
    ? filas.slice().reverse().map(filaDecision).join("")
    : '<tr><td colspan="5" class="vacio">Todavía no hay decisiones registradas.</td></tr>';
}

async function cargarBitacora() {
  const parametros = new URLSearchParams({
    n: $("#filtro-numero").value,
    agente: $("#filtro-agente").value,
    decision: $("#filtro-decision").value,
    texto: $("#filtro-texto").value.trim(),
  });
  const r = await pedir(`/api/bitacora?${parametros}`);
  $("#bitacora").innerHTML = r.entradas.length
    ? r.entradas.slice().reverse().map(filaDecision).join("")
    : '<tr><td colspan="5" class="vacio">Nada que coincida con ese filtro.</td></tr>';
  $("#btn-csv").href = `/api/bitacora.csv?${parametros}`;
}

/* -------------------------------- reglas -------------------------------- */

function pintarReglas() {
  const cuerpo = $("#reglas");
  if (!estado.reglas.length) {
    cuerpo.innerHTML = '<tr><td colspan="5" class="vacio">No hay reglas. Sin ellas manda solo la palanca.</td></tr>';
    return;
  }
  const agentes = ["*"].concat((estado.panorama?.agentes || []).map((a) => a.id));
  cuerpo.innerHTML = estado.reglas.map((r, i) => `<tr data-fila="${i}">
    <td><input data-campo="patron" value="${esc(r.patron)}" style="min-width:11rem"></td>
    <td><select data-campo="decision">
      ${["permitir","preguntar","denegar"].map((d) =>
        `<option value="${d}" ${d === r.decision ? "selected" : ""}>${d}</option>`).join("")}
    </select></td>
    <td><select data-campo="agente">
      ${agentes.map((a) => `<option value="${esc(a)}" ${a === r.agente ? "selected" : ""}>${a === "*" ? "todos" : esc(a)}</option>`).join("")}
    </select></td>
    <td><input data-campo="nota" value="${esc(r.nota || "")}" style="min-width:12rem"></td>
    <td><button type="button" class="quitar" data-quitar aria-label="Quitar la regla ${esc(r.patron)}">×</button></td>
  </tr>`).join("");

  $$("[data-quitar]").forEach((b) => b.addEventListener("click", () => {
    const fila = Number(b.closest("tr").dataset.fila);
    recogerReglas();
    estado.reglas.splice(fila, 1);
    pintarReglas();
  }));
}

function recogerReglas() {
  estado.reglas = $$("#reglas tr[data-fila]").map((fila) => {
    const leer = (c) => $(`[data-campo="${c}"]`, fila)?.value ?? "";
    return {patron: leer("patron").trim(), decision: leer("decision"),
            agente: leer("agente") || "*", nota: leer("nota")};
  }).filter((r) => r.patron);
}

const REGLAS_DE_FABRICA = [
  {patron:"rm -rf", decision:"denegar", nota:"Borrado recursivo forzado.", agente:"*"},
  {patron:"mkfs", decision:"denegar", nota:"Formateo de disco.", agente:"*"},
  {patron:"dd if=", decision:"denegar", nota:"Escritura directa sobre un dispositivo.", agente:"*"},
  {patron:":(){", decision:"denegar", nota:"Bomba de bifurcación.", agente:"*"},
  {patron:"git push --force", decision:"preguntar", nota:"Reescribe historia remota.", agente:"*"},
  {patron:"git reset --hard", decision:"preguntar", nota:"Descarta cambios sin copia.", agente:"*"},
  {patron:"sudo ", decision:"preguntar", nota:"Eleva privilegios.", agente:"*"},
  {patron:"curl ", decision:"preguntar", nota:"Descarga desde la red.", agente:"*"},
  {patron:"npm publish", decision:"preguntar", nota:"Publica un paquete.", agente:"*"},
];

/* -------------------------------- agentes -------------------------------- */

function pintarAgentes(lista) {
  $("#agentes").innerHTML = lista.map((a) => {
    // ChatGPT no tiene enganches y no puede tenerlos, asi que su ficha se
    // cuenta distinta: ni ruta de configuracion ni «reinstalar», que darian a
    // entender que se escribe algo en alguna parte. Lo que se enciende y se
    // apaga ahi es el vigia que le lee la ventana.
    if (a.sin_enganches) {
      return `<div class="agente" data-agente="${esc(a.id)}">
        <h3>${esc(a.nombre)}</h3>
        <div class="nota">${a.instalado ? "Vigilado · se le lee la ventana" : "Sin vigilar · el modo se queda a oscuras"}</div>
        <div class="ruta">${esc(a.nota || "")}</div>
        <div class="acciones">
          <button type="button" class="btn ${a.instalado ? "btn-claro" : "btn-azul"}"
            data-${a.instalado ? "desinstalar" : "instalar"}>
            ${a.instalado ? "Dejar de vigilar" : "Vigilar"}</button>
        </div></div>`;
    }
    return `<div class="agente" data-agente="${esc(a.id)}">
    <h3>${esc(a.nombre)}</h3>
    <div class="nota">${a.instalado ? `Enganches puestos · ${a.eventos} eventos` : "Sin enganches"}
      ${a.existe_config ? "" : " · no parece instalado en este equipo"}</div>
    <div class="ruta">${esc(a.config)}</div>
    <div class="acciones">
      <button type="button" class="btn ${a.instalado ? "btn-claro" : "btn-azul"}" data-instalar>
        ${a.instalado ? "Reinstalar" : "Instalar"}</button>
      ${a.instalado ? '<button type="button" class="btn btn-claro peligro" data-desinstalar>Quitar</button>' : ""}
    </div></div>`;
  }).join("");

  $$("#agentes [data-instalar]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.closest("[data-agente]").dataset.agente;
    const r = await pedir("/api/agentes/instalar", {agentes: [id]});
    avisar(Object.values(r.resultado).flat().join(" · ") || "Listo", "bien");
    refrescar();
  }));
  $$("#agentes [data-desinstalar]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.closest("[data-agente]").dataset.agente;
    const r = await pedir("/api/agentes/desinstalar", {agentes: [id]});
    avisar(Object.values(r.resultado).flat().join(" · ") || "Retirado", "bien");
    refrescar();
  }));

  const filtro = $("#filtro-agente");
  if (filtro && filtro.options.length <= 1) lista.forEach((a) => filtro.add(new Option(a.nombre, a.id)));
  const prueba = $("#prueba-agente");
  if (prueba && !prueba.options.length) lista.forEach((a) => prueba.add(new Option(a.nombre, a.id)));
}

/* ----------------------------- aplicaciones ----------------------------- */

function pintarAplicaciones() {
  const cuerpo = $("#aplicaciones");
  const apps = estado.aplicaciones || [];
  if (!apps.length) {
    cuerpo.innerHTML = '<tr><td colspan="4" class="vacio">Sin reglas: el teclado no cambia de modo solo.</td></tr>';
    return;
  }
  cuerpo.innerHTML = apps.map((a, i) => `<tr data-fila="${i}">
    <td><input data-campo="patron" value="${esc(a.patron)}" style="min-width:10rem"></td>
    <td><select data-campo="en">
      ${[["proceso","el programa"],["titulo","el título"],["cualquiera","cualquiera de los dos"]]
        .map(([v, texto]) => `<option value="${v}" ${v === (a.en || "proceso") ? "selected" : ""}>${texto}</option>`).join("")}
    </select></td>
    <td><select data-campo="modo">
      ${estado.modos.map((m, j) =>
        `<option value="${j}" ${j === a.modo ? "selected" : ""}>${esc(m.nombre || `Modo ${j+1}`)}</option>`).join("")}
    </select></td>
    <td><button type="button" class="quitar" data-quitar-app aria-label="Quitar ${esc(a.patron)}">×</button></td>
  </tr>`).join("");

  $$("[data-quitar-app]").forEach((b) => b.addEventListener("click", () => {
    const fila = Number(b.closest("tr").dataset.fila);
    recogerAplicaciones();
    estado.aplicaciones.splice(fila, 1);
    pintarAplicaciones();
  }));
}

function recogerAplicaciones() {
  estado.aplicaciones = $$("#aplicaciones tr[data-fila]").map((fila) => ({
    patron: $('[data-campo="patron"]', fila)?.value.trim() ?? "",
    en: $('[data-campo="en"]', fila)?.value ?? "proceso",
    modo: Number($('[data-campo="modo"]', fila)?.value ?? 0),
  })).filter((a) => a.patron);
}

async function cargarAplicaciones() {
  const r = await pedir("/api/aplicaciones");
  estado.aplicaciones = r.aplicaciones;
  pintarAplicaciones();
  const v = r.ventana || {};
  $("#ventana-actual").textContent = v.soporte
    ? `Ahora mismo tienes delante: ${v.proceso || "?"}${v.titulo ? ` — «${v.titulo}»` : ""}`
    : "Seguir a la aplicación activa solo funciona en Windows.";
  return v;
}

/* -------------------------------- ajustes -------------------------------- */

const ETIQUETAS_AJUSTES = {
  modo_aprobacion:"Modo de aprobación", transporte:"Transporte",
  nombre_dispositivo:"Filtrar por nombre al buscar", puerto_hooks:"Puerto de los enganches",
  puerto_panel:"Puerto del panel", puente_host:"Puente TCP · equipo",
  puente_puerto:"Puente TCP · puerto", vigencia_cache_ms:"Vigencia de la lectura (ms)",
  espera_palanca_s:"Espera de la palanca (s)",
  reglas_permisivas:"Dejar que las reglas «permitir» adelanten a la palanca",
  sincronizar_config_agentes:"Alinear la configuración de cada programa con la palanca",
  avisar_en_escritorio:"Avisar en el escritorio", brillo:"Brillo de la barra (%)",
  accesible:"Modo accesible (sin color en la terminal)",
  aprobacion_remota:"Permitir aprobar desde esta web",
  espera_aprobacion_s:"Cuánto espera una aprobación web (s)",
  seguir_aplicacion:"Cambiar de modo al cambiar de aplicación",
  segundos_reposo:"Apagar la barra tras (s) sin noticias · 0 lo desactiva",
  efecto_reposo:"Efecto de reposo (código)",
  intervalo_sondeo_s:"Cada cuánto se pregunta al teclado (s)",
  manos_libres:"Manos libres · abrir el micrófono cuando la IA termine",
  pitidos_manos_libres:"Avisar con dos pitidos al abrirse el micrófono",
  manos_libres_espera_s:"Espera antes de abrir el micrófono (s)",
  milisegundos_estado_breve:"Cuánto dura un momento pasajero (ms)",
  milisegundos_tarea_completada:"Cuánto dura el verde de tarea completada (ms)",
  usar_microfono_propio:"Usar el micrófono del propio programa (Claude, ChatGPT)",
};
const OPCIONES_FIJAS = {
  modo_aprobacion:["palanca","siempre_preguntar","siempre_permitir"],
  transporte:["auto","ble","puente","simulado"],
};

function pintarAjustes(ajustes) {
  $("#ajustes").innerHTML = Object.entries(ajustes).map(([campo, valor]) => {
    const etiqueta = esc(ETIQUETAS_AJUSTES[campo] || campo);
    if (typeof valor === "boolean") {
      return `<div class="campo interruptor ancho">
        <input type="checkbox" id="aj-${campo}" data-ajuste="${campo}" ${valor ? "checked" : ""}>
        <label for="aj-${campo}">${etiqueta}</label></div>`;
    }
    if (OPCIONES_FIJAS[campo]) {
      return `<div class="campo"><label for="aj-${campo}">${etiqueta}</label>
        <select id="aj-${campo}" data-ajuste="${campo}">
          ${OPCIONES_FIJAS[campo].map((o) => `<option ${o === valor ? "selected" : ""}>${o}</option>`).join("")}
        </select></div>`;
    }
    const tipo = typeof valor === "number" ? "number" : "text";
    const paso = Number.isInteger(valor) ? "1" : "0.1";
    return `<div class="campo"><label for="aj-${campo}">${etiqueta}</label>
      <input id="aj-${campo}" data-ajuste="${campo}" type="${tipo}" step="${paso}" value="${esc(valor)}"></div>`;
  }).join("");
}


/* ------------------------- pulsaciones en vivo -------------------------- */
/* Sirve para comprobar de un vistazo que el teclado responde. De las cuatro
   teclas solo se ve la del micrófono: las otras tres mandan sus pulsaciones
   directamente a Windows sin pasar por el servicio, que es lo que se busca de
   ellas. La palanca y el cambio de modo sí se ven, porque se leen del aparato. */

const NOMBRES_DE_PIEZA = {
  palanca: "Palanca",
  modo: "Modo",
  microfono: "Micrófono",
  luz: "Barra de luz",
  pantalla: "Pantalla",
};

function _horaCorta() {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" +
         String(d.getMinutes()).padStart(2, "0") + ":" +
         String(d.getSeconds()).padStart(2, "0");
}

function destellar(selector) {
  const pieza = document.querySelector(selector);
  if (!pieza) return;
  pieza.classList.remove("pulsada");
  void pieza.offsetWidth;   // reinicia la animación si ya estaba puesta
  pieza.classList.add("pulsada");
  setTimeout(() => pieza.classList.remove("pulsada"), 700);
}

function anotarActividad(texto) {
  const tira = document.querySelector("#actividad");
  if (!tira) return;
  const marca = document.createElement("span");
  marca.className = "marca";
  marca.innerHTML = `${esc(texto)} <span class="hora">${_horaCorta()}</span>`;
  tira.prepend(marca);
  // Solo las últimas: esto es un vistazo, no un registro. Para eso está la bitácora.
  while (tira.children.length > 4) tira.lastChild.remove();
  setTimeout(() => marca.remove(), 12000);
}

function mostrarPulsacion(datos) {
  const pieza = datos.pieza;
  if (pieza === "palanca") {
    const donde = datos.valor === 0 ? "arriba · envío automático"
                : datos.valor === null || datos.valor === undefined ? "sin lectura"
                : "abajo · manual";
    destellar(".pieza-palanca");
    anotarActividad(`Palanca ${donde}`);
  } else if (pieza === "modo") {
    const nombre = estado.modos[datos.valor]?.nombre || `Modo ${(datos.valor ?? 0) + 1}`;
    destellar("#modos");
    anotarActividad(`Modo ${nombre}`);
  } else if (pieza === "microfono") {
    destellar('.tecla[data-indice="0"]');
    const que = datos.accion === "abierto"
      ? `Micrófono abierto${datos.programa ? " en " + datos.programa : ""}`
      : `Micrófono cerrado${datos.enviado ? " · texto enviado" : ""}`;
    anotarActividad(que);
  } else {
    destellar(`.pieza-${pieza}`);
    anotarActividad(NOMBRES_DE_PIEZA[pieza] || pieza);
  }
}

/* --------------------------- canal de sucesos --------------------------- */

function escuchar() {
  const canal = new EventSource("/api/sucesos");
  canal.addEventListener("open", () => $("#chip-vivo").hidden = false);
  canal.addEventListener("error", () => $("#chip-vivo").hidden = true);
  canal.addEventListener("bienvenida", () => { $("#chip-vivo").hidden = false; refrescar(); });
  canal.addEventListener("estado", () => refrescar());
  canal.addEventListener("ajustes", () => refrescar());
  canal.addEventListener("decision", (e) => {
    const entrada = JSON.parse(e.data);
    const p = estado.panorama || {historial: []};
    p.historial = (p.historial || []).concat(entrada).slice(-25);
    pintarHistorial(p.historial);
  });
  canal.addEventListener("subida", (e) => {
    const s = JSON.parse(e.data);
    const banda = $("#aviso-sin-teclado");
    const marca = banda?.querySelector("b");
    if (marca) marca.textContent =
      `Enviando la pantalla del modo ${s.modo + 1}: ${s.hecho} de ${s.total} fotogramas.`;
  });
  canal.addEventListener("pulsacion", (e) => mostrarPulsacion(JSON.parse(e.data)));
  canal.addEventListener("aprobacion_pendiente", (e) => anadirPendiente(JSON.parse(e.data)));
  canal.addEventListener("aprobacion_resuelta", (e) => quitarPendiente(JSON.parse(e.data).id));
  canal.addEventListener("aprobacion_caducada", (e) => quitarPendiente(JSON.parse(e.data).id));
}

/* -------------------------------- arranque -------------------------------- */

async function refrescar() { pintarEstado(await pedir("/api/estado")); }

function conectarBotones() {
  $("#btn-conectar").addEventListener("click", async (e) => {
    const conectado = estado.panorama?.estado?.conectado;
    e.currentTarget.disabled = true;
    try {
      const r = await pedir("/api/conexion", {accion: conectado ? "desconectar" : "conectar"});
      avisar(r.ok ? (conectado ? "Teclado desconectado." : "Teclado conectado.") : r.error,
             r.ok ? "bien" : "mal");
      refrescar();
    } finally { e.currentTarget.disabled = false; }
  });

  $("#btn-buscar").addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    avisar("Buscando teclados…");
    try {
      const r = await pedir("/api/buscar", {segundos: 8});
      avisar(r.ok
        ? (r.encontrados.length
            ? "Encontrados: " + r.encontrados.map((d) => `${d.nombre || "sin nombre"} (${d.direccion})`).join(", ")
            : "No apareció ningún teclado. Si la aplicación oficial está abierta, ciérrala.")
        : r.error, r.ok && r.encontrados.length ? "bien" : "mal");
    } finally { e.currentTarget.disabled = false; }
  });

  $("#btn-regla-nueva").addEventListener("click", () => {
    recogerReglas();
    estado.reglas.push({patron:"", decision:"preguntar", agente:"*", nota:""});
    pintarReglas();
    $("#reglas tr:last-child input")?.focus();
  });
  $("#btn-reglas-guardar").addEventListener("click", async () => {
    recogerReglas();
    const r = await pedir("/api/reglas", {reglas: estado.reglas});
    estado.reglas = r.reglas; pintarReglas();
    avisar(`Guardadas ${r.reglas.length} reglas.`, "bien");
  });
  $("#btn-reglas-restaurar").addEventListener("click", async () => {
    if (!confirm("Se reemplazan todas las reglas por las de fábrica. ¿Seguimos?")) return;
    const r = await pedir("/api/reglas", {reglas: REGLAS_DE_FABRICA});
    estado.reglas = r.reglas; pintarReglas();
    avisar("Reglas de fábrica restauradas.", "bien");
  });
  $("#btn-probar").addEventListener("click", async () => {
    const r = await pedir("/api/reglas/probar", {
      agente: $("#prueba-agente").value,
      herramienta: $("#prueba-herramienta").value,
      comando: $("#prueba-comando").value,
      palanca: $("#prueba-palanca").value,
    });
    const caja = $("#resultado-prueba");
    caja.hidden = false;
    caja.className = `resultado ${r.decision}`;
    caja.innerHTML = `<b>${esc(r.decision)}</b> — ${esc(r.explicacion)}
      ${r.regla ? `<div class="nota">Coincidió la regla «${esc(r.regla.patron)}» (${esc(r.regla.decision)}).</div>` : ""}`;
  });

  $("#btn-instalar-todos").addEventListener("click", async () => {
    const r = await pedir("/api/agentes/instalar", {});
    $("#nota-agentes").textContent = Object.entries(r.resultado)
      .map(([n, l]) => `${n}: ${l.join(", ")}`).join(" · ");
    refrescar();
  });

  $("#btn-bitacora").addEventListener("click", cargarBitacora);
  $("#filtro-texto").addEventListener("keydown", (e) => { if (e.key === "Enter") cargarBitacora(); });

  $("#btn-ajustes").addEventListener("click", async () => {
    const cuerpo = {};
    $$("[data-ajuste]").forEach((c) => {
      cuerpo[c.dataset.ajuste] = c.type === "checkbox" ? c.checked
        : (c.type === "number" ? Number(c.value) : c.value);
    });
    const r = await pedir("/api/ajustes", cuerpo);
    pintarAjustes(r.ajustes);
    avisar(r.cambios.length ? `Guardado: ${r.cambios.join(", ")}.` : "No había nada que cambiar.", "bien");
    refrescar();
  });

  $("#btn-app-nueva").addEventListener("click", () => {
    recogerAplicaciones();
    estado.aplicaciones.push({patron: "", en: "proceso", modo: estado.modo});
    pintarAplicaciones();
    $("#aplicaciones tr:last-child input")?.focus();
  });
  $("#btn-app-actual").addEventListener("click", async () => {
    const v = await cargarAplicaciones();
    if (!v.soporte) return avisar("Esto solo funciona en Windows.", "mal");
    recogerAplicaciones();
    estado.aplicaciones.unshift({
      patron: v.proceso || v.titulo,
      en: v.proceso ? "proceso" : "titulo",
      modo: estado.modo,
    });
    pintarAplicaciones();
    avisar(`Añadida «${v.proceso || v.titulo}». Recuerda guardar.`, "bien");
  });
  $("#btn-apps-guardar").addEventListener("click", async () => {
    recogerAplicaciones();
    const r = await pedir("/api/aplicaciones", {aplicaciones: estado.aplicaciones});
    estado.aplicaciones = r.aplicaciones;
    pintarAplicaciones();
    avisar(`Guardadas ${r.aplicaciones.length} reglas. Reinicia el servicio para que tomen efecto.`, "bien");
  });

  $("#btn-nombre").addEventListener("click", async () => {
    const nombre = $("#nombre-teclado").value.trim();
    if (!nombre) return avisar("Escribe un nombre.", "mal");
    const r = await pedir("/api/nombre", {nombre});
    avisar(r.ok ? "Nombre cambiado en el teclado." : "El teclado no está conectado.", r.ok ? "bien" : "mal");
  });
}

(async function arrancar() {
  aplicarTema(temaGuardado());
  $$(".tema [data-tema]").forEach((b) =>
    b.addEventListener("click", () => aplicarTema(b.dataset.tema)));

  conectarBotones();
  estado.opciones = await pedir("/api/opciones");
  estado.modos = (await pedir("/api/teclas")).modos;
  await refrescar();

  pintarAjustes(estado.panorama.ajustes || {});
  pintarModos();
  pintarTeclas();
  pintarEditor();

  estado.reglas = (await pedir("/api/reglas")).reglas;
  pintarReglas();

  estado.luces = (await pedir("/api/luces")).luces;
  pintarEditor();

  await cargarAplicaciones();

  try {
    const paquete = await pedir("/api/paquete");
    $("#nota-paquete").textContent =
      `${paquete.archivos} archivos · ${(paquete.bytes / 1024).toFixed(0)} KB · ${paquete.nombre}`;
    // El ejecutable es opcional: quien trabaja desde el código no lo construye.
    // Si no está, se dice por qué en vez de dejar un botón que da error.
    const exe = paquete.ejecutable || {};
    const botonExe = $("#btn-exe");
    if (exe.hay) {
      $("#nota-exe").textContent =
        `${(exe.bytes / 1048576).toFixed(1)} MB · ${exe.nombre} · lleva Python dentro`;
    } else if (botonExe) {
      botonExe.classList.add("desactivado");
      botonExe.removeAttribute("href");
      $("#nota-exe").textContent =
        "Todavía no está construido en este equipo. Se hace con «python construir_exe.py».";
    }
  } catch (_) {}

  escuchar();

  const inicial = location.hash.replace("#", "");
  if (inicial && $(`#seccion-${inicial}`)) irA(inicial);
})();
