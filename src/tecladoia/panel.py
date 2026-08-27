"""Panel web local, en español.

Es la cara visible del servicio: se abre en el navegador, no necesita ninguna
dependencia extra y funciona igual en Windows, macOS y Linux. Sirve para ver el
estado del teclado, mover la palanca virtual y repasar qué se aprobó y por qué.

La página está pensada también para quien navega con teclado o con lector de
pantalla: estructura semántica, contraste alto en ambos temas y ningún control
que dependa solo del color.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from pathlib import Path

from . import instalador
from .config import Ajustes
from .dispositivo import GestorTeclado
from .modelo import EfectoLuz, EstadoIA
from .registro import obtener
from .protocolo import MODOS_DISPONIBLES, TECLAS_POR_MODO
from .servidor import ServidorEnganches
from .transporte.base import ErrorTransporte

_log = obtener("panel")

#: Carpeta con la página, el estilo y el guion del navegador.
CARPETA_WEB = Path(__file__).resolve().parent / "web"

#: Cada cuánto se manda un latido por el canal de sucesos.
LATIDO_S = 20.0


def _dictado_listo() -> bool:
    """¿Tiene Windows el dictado activado? Fuera de Windows, no aplica."""
    try:
        from .dictado import dictado_configurado

        return dictado_configurado()
    except Exception:  # noqa: BLE001
        return False

#: Fin de línea de las cabeceras HTTP y salto de las tramas del canal.
_FIN = chr(13) + chr(10)
_SALTO = bytes([10])


def _suceso(tipo: str, carga: str, identificador: Optional[int] = None) -> bytes:
    """Arma una trama del canal de sucesos, con sus saltos de línea."""
    salto = chr(10)
    cabeza = f"id: {identificador}{salto}" if identificador is not None else ""
    return f"{cabeza}event: {tipo}{salto}data: {carga}{salto}{salto}".encode("utf-8")

_PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TecladoIA · panel</title>
<style>
  :root {
    color-scheme: light dark;
    --fondo: #f6f7f9; --tarjeta: #ffffff; --texto: #14161a; --tenue: #5b6270;
    --borde: #d8dce3; --acento: #2c5cff; --si: #0a7c42; --no: #a3341c;
  }
  @media (prefers-color-scheme: dark) {
    :root { --fondo:#111318; --tarjeta:#1a1d24; --texto:#eef1f6; --tenue:#a2abbb;
            --borde:#2c313b; --acento:#7aa0ff; --si:#4ade80; --no:#ff8f6b; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:1.5rem; background:var(--fondo); color:var(--texto);
         font:16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 60rem; margin: 0 auto; }
  h1 { font-size:1.5rem; margin:0 0 .25rem; }
  p.lema { margin:0 0 1.5rem; color:var(--tenue); }
  section { background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px;
            padding:1rem 1.25rem; margin-bottom:1rem; }
  h2 { font-size:1.05rem; margin:0 0 .75rem; }
  dl.datos { display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr)); gap:.75rem; margin:0; }
  dt { font-size:.8rem; color:var(--tenue); text-transform:uppercase; letter-spacing:.04em; }
  dd { margin:.15rem 0 0; font-size:1.1rem; font-weight:600; }
  .fila { display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; }
  button, select { font:inherit; padding:.45rem .9rem; border-radius:8px;
                   border:1px solid var(--borde); background:var(--fondo); color:var(--texto); cursor:pointer; }
  button:hover { border-color:var(--acento); }
  button[aria-pressed="true"] { background:var(--acento); color:#fff; border-color:var(--acento); }
  table { width:100%; border-collapse:collapse; font-size:.92rem; }
  th, td { text-align:left; padding:.45rem .5rem; border-bottom:1px solid var(--borde); vertical-align:top; }
  th { color:var(--tenue); font-weight:600; font-size:.8rem; text-transform:uppercase; }
  .permitir { color:var(--si); font-weight:600; }
  .denegar, .preguntar { color:var(--no); font-weight:600; }
  code { background:color-mix(in srgb, var(--texto) 8%, transparent); padding:.1rem .35rem; border-radius:4px; }
  .aviso { color:var(--tenue); font-size:.9rem; }
</style>
</head>
<body>
<main>
  <h1>TecladoIA</h1>
  <p class="lema">Tu teclado decide qué puede hacer solo un agente de IA.</p>

  <section aria-labelledby="t-estado">
    <h2 id="t-estado">Estado del teclado</h2>
    <dl class="datos" id="estado"><dt>Cargando</dt><dd>…</dd></dl>
  </section>

  <section aria-labelledby="t-palanca">
    <h2 id="t-palanca">Palanca de aprobación</h2>
    <div class="fila" role="group" aria-label="Modo de aprobación">
      <button type="button" data-palanca="0">Automático</button>
      <button type="button" data-palanca="1">Manual</button>
      <button type="button" data-palanca="">Seguir la palanca física</button>
    </div>
    <p class="aviso" id="nota-palanca"></p>
  </section>

  <section aria-labelledby="t-luz">
    <h2 id="t-luz">Barra de luz</h2>
    <div class="fila">
      <label for="efecto">Efecto</label>
      <select id="efecto"></select>
      <button type="button" id="aplicar-efecto">Aplicar</button>
    </div>
  </section>

  <section aria-labelledby="t-agentes">
    <h2 id="t-agentes">Programas de IA</h2>
    <table><thead><tr><th>Programa</th><th>Enganches</th><th>Configuración</th></tr></thead>
    <tbody id="agentes"></tbody></table>
  </section>

  <section aria-labelledby="t-historial">
    <h2 id="t-historial">Últimas decisiones</h2>
    <table><thead><tr><th>Hora</th><th>Programa</th><th>Acción</th><th>Decisión</th><th>Motivo</th></tr></thead>
    <tbody id="historial"><tr><td colspan="5">Todavía no hay decisiones registradas.</td></tr></tbody></table>
  </section>
</main>
<script>
const $ = (s) => document.querySelector(s);

async function pedir(ruta, cuerpo) {
  const opciones = cuerpo ? {method:"POST", headers:{"Content-Type":"application/json"},
                             body: JSON.stringify(cuerpo)} : {};
  const respuesta = await fetch(ruta, opciones);
  return respuesta.json();
}

function pinta(datos) {
  const e = datos.estado || {};
  const palanca = e.palanca === null || e.palanca === undefined
    ? "sin lectura" : (e.palanca === 0 ? "automático" : "manual");
  $("#estado").innerHTML = [
    ["Conexión", e.conectado ? "conectado" : "sin conexión"],
    ["Transporte", e.transporte || "—"],
    ["Batería", e.bateria === null || e.bateria === undefined ? "—" : e.bateria + " %"],
    ["Firmware", e.firmware || "—"],
    ["Palanca", palanca],
    ["Momento del agente", e.estado_ia_etiqueta || "—"],
    ["Programa activo", e.agente_activo || "ninguno"],
  ].map(([t, v]) => `<dt>${t}</dt><dd>${v}</dd>`).join("");

  $("#nota-palanca").textContent = e.palanca_forzada
    ? "Ahora manda la palanca virtual de esta página; la física queda ignorada."
    : "Manda la palanca física del teclado.";
  document.querySelectorAll("[data-palanca]").forEach((boton) => {
    const valor = boton.dataset.palanca;
    const activo = valor === "" ? !e.palanca_forzada
                                : (e.palanca_forzada && String(e.palanca) === valor);
    boton.setAttribute("aria-pressed", activo ? "true" : "false");
  });

  $("#agentes").innerHTML = (datos.agentes || []).map((a) => `<tr>
      <td>${a.nombre}</td>
      <td>${a.instalado ? "instalados (" + a.eventos + ")" : "no instalados"}</td>
      <td><code>${a.config}</code></td></tr>`).join("");

  const filas = datos.historial || [];
  $("#historial").innerHTML = filas.length ? filas.slice().reverse().map((h) => `<tr>
      <td>${(h.instante || "").replace("T", " ").slice(0, 19)}</td>
      <td>${h.agente || ""}</td>
      <td>${[h.herramienta, h.comando].filter(Boolean).join(" · ") || "—"}</td>
      <td class="${h.decision}">${h.decision}</td>
      <td>${h.regla ? "regla: " + h.regla : (h.motivo || "").replace(/_/g, " ")}</td>
    </tr>`).join("") : `<tr><td colspan="5">Todavía no hay decisiones registradas.</td></tr>`;
}

async function refrescar() { pinta(await pedir("/api/estado")); }

document.querySelectorAll("[data-palanca]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const valor = boton.dataset.palanca;
    pinta(await pedir("/api/palanca", {valor: valor === "" ? null : Number(valor)}));
  });
});

$("#aplicar-efecto").addEventListener("click", async () => {
  await pedir("/api/luz", {efecto: Number($("#efecto").value)});
});

(async () => {
  const efectos = await pedir("/api/efectos");
  $("#efecto").innerHTML = efectos.efectos
    .map((f) => `<option value="${f.codigo}">${f.etiqueta}</option>`).join("");
  await refrescar();
  setInterval(refrescar, 3000);
})();
</script>
</body>
</html>
"""


class PanelWeb:
    """Servidor HTTP mínimo para el panel."""

    def __init__(
        self,
        gestor: GestorTeclado,
        servidor: ServidorEnganches,
        ajustes: Optional[Ajustes] = None,
    ) -> None:
        self.gestor = gestor
        self.servidor = servidor
        self.ajustes = ajustes or gestor.ajustes
        self.puerto: Optional[int] = None
        self._http: Optional[asyncio.AbstractServer] = None
        self._adjunto: Optional[str] = None

    @property
    def url(self) -> str:
        if not self.puerto:
            return ""
        anfitrion = "127.0.0.1" if self.ajustes.host_panel == "0.0.0.0" else self.ajustes.host_panel
        return f"http://{anfitrion}:{self.puerto}/"

    @property
    def solo_local(self) -> bool:
        return self.ajustes.host_panel in ("127.0.0.1", "::1", "localhost")

    async def arrancar(self) -> None:
        # El panel mueve la palanca de aprobación: publicarlo sin clave sería
        # dejar que cualquiera que lo alcance ponga los agentes en «aprobar
        # todo». Escuchar fuera de la máquina local exige clave, sin excepción.
        if not self.solo_local and not self.ajustes.clave_panel:
            _log.error(
                "El panel iba a escuchar en %s sin clave y no se ha abierto. "
                "Pon una con «tecladoia config --clave-panel generar».",
                self.ajustes.host_panel,
            )
            return

        base = self.ajustes.puerto_panel
        for intento in range(10):
            try:
                self._http = await asyncio.start_server(
                    self._atender, self.ajustes.host_panel, base + intento
                )
            except OSError:
                continue
            self.puerto = base + intento
            _log.info(
                "Panel disponible en %s%s",
                self.url,
                "" if self.solo_local else " (con clave)",
            )
            return
        _log.error("No se pudo abrir el panel entre los puertos %s y %s", base, base + 9)

    async def detener(self) -> None:
        if self._http is None:
            return
        self._http.close()
        with contextlib.suppress(Exception):
            await self._http.wait_closed()
        self._http = None

    # --- HTTP -----------------------------------------------------------
    async def _atender(self, lector: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        try:
            peticion = await asyncio.wait_for(lector.readline(), timeout=5)
            if not peticion:
                return
            metodo, destino, _ = peticion.decode("latin-1").split(" ", 2)
            cabeceras: dict[str, str] = {}
            while True:
                linea = await asyncio.wait_for(lector.readline(), timeout=5)
                if linea in (b"\r\n", b"\n", b""):
                    break
                nombre, _, valor = linea.decode("latin-1").partition(":")
                cabeceras[nombre.strip().lower()] = valor.strip()
            longitud = int(cabeceras.get("content-length") or 0)
            cuerpo = await lector.readexactly(longitud) if longitud else b""

            partes = urlparse(destino)
            consulta = parse_qs(partes.query)
            extras: list[str] = []
            if not self._autorizado(cabeceras, consulta):
                estado, tipo, datos = self._sin_permiso()
            else:
                if consulta.get("clave"):
                    # Se recuerda la clave en una cookie y se reenvía a la misma
                    # página sin ella. Así no se queda escrita en la barra de
                    # direcciones, ni en el historial, ni en los registros de
                    # ningún intermediario por los que pase la petición.
                    extras.append(
                        f"Set-Cookie: tecladoia={self.ajustes.clave_panel}; "
                        "Path=/; HttpOnly; SameSite=Strict"
                    )
                    extras.append(f"Location: {partes.path or '/'}")
                    estado, tipo, datos = "303 See Other", "text/plain; charset=utf-8", b""
                elif partes.path == "/api/sucesos" and metodo == "GET":
                    # Conexión larga: se queda abierta escribiendo lo que pasa.
                    await self._transmitir_sucesos(escritor)
                    return
                else:
                    estado, tipo, datos = await self._responder(
                        metodo, partes.path, cuerpo, consulta
                    )
            if self._adjunto:
                extras.append(
                    f'Content-Disposition: attachment; filename="{self._adjunto}"'
                )
                self._adjunto = None
            escritor.write(self._envolver(estado, tipo, datos, extras))
            await escritor.drain()
        except (asyncio.TimeoutError, ValueError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    def _autorizado(self, cabeceras: dict[str, str], consulta: dict[str, list[str]]) -> bool:
        """Comprueba la clave del panel, si la hay.

        Se acepta por cabecera ``Authorization: Bearer``, por ``?clave=`` y por
        la cookie que deja la primera visita. La comparación es de tiempo
        constante para no filtrar la clave a base de medir respuestas.
        """
        esperada = self.ajustes.clave_panel
        if not esperada:
            return True

        candidatas: list[str] = []
        autorizacion = cabeceras.get("authorization", "")
        if autorizacion.lower().startswith("bearer "):
            candidatas.append(autorizacion[7:].strip())
        if cabecera := cabeceras.get("x-tecladoia-clave"):
            candidatas.append(cabecera.strip())
        for trozo in cabeceras.get("cookie", "").split(";"):
            nombre, _, valor = trozo.strip().partition("=")
            if nombre == "tecladoia":
                candidatas.append(valor.strip())
        candidatas.extend(consulta.get("clave", []))
        return any(secrets.compare_digest(c, esperada) for c in candidatas)

    @staticmethod
    def _sin_permiso() -> tuple[str, str, bytes]:
        """La puerta: un formulario, no una instrucción.

        Antes esta página pedía añadir «?clave=…» a la dirección a mano. Además
        de incómodo, deja la clave escrita en el historial del navegador y en los
        registros de cualquier intermediario. Con el formulario, la clave viaja
        una vez y se queda en una cookie de sesión.
        """
        pagina = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TecladoIA · entrar</title>
<style>
  :root{color-scheme:light dark;--fondo:#F2F5F9;--tarjeta:#fff;--texto:#0F172A;
        --tenue:#64748B;--borde:#E3E8EF;--azul:#2563EB}
  @media (prefers-color-scheme:dark){:root{--fondo:#0B0F16;--tarjeta:#151A23;
        --texto:#E8EDF5;--tenue:#97A3B6;--borde:#242B37;--azul:#7DA2FF}}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--fondo);
       color:var(--texto);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  form{background:var(--tarjeta);border:1px solid var(--borde);border-radius:14px;
       padding:2rem;width:min(25rem,92vw);display:grid;gap:.9rem;
       box-shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(15,23,42,.08)}
  .marca{display:flex;align-items:center;gap:.6rem;font-weight:800;letter-spacing:-.02em}
  .logo{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;
        background:linear-gradient(135deg,#2563EB,#0B2C6B)}
  .logo svg{width:18px;height:18px;stroke:#fff;fill:none;stroke-width:1.9;stroke-linecap:round}
  h1{font-size:1.1rem;margin:.3rem 0 0}
  p{margin:0;color:var(--tenue);font-size:.9rem}
  input,button{font:inherit;padding:.6rem .8rem;border-radius:9px;border:1px solid var(--borde)}
  input{background:var(--fondo);color:var(--texto);width:100%}
  input:focus{outline:2px solid var(--azul);outline-offset:1px}
  button{background:var(--azul);color:#fff;border-color:var(--azul);cursor:pointer;font-weight:600}
  .error{color:#c0392b;font-size:.88rem;min-height:1.2em}
</style>
</head>
<body>
<form id="acceso">
  <div class="marca">
    <span class="logo"><svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/></svg></span>
    TecladoIA
  </div>
  <h1>Hace falta la clave</h1>
  <p>Este panel decide qué puede ejecutar un agente de IA sin preguntar,
     así que no se abre sin identificarse.</p>
  <input id="clave" type="password" placeholder="Clave del panel"
         autocomplete="current-password" autofocus>
  <button type="submit">Entrar</button>
  <div class="error" id="error" role="alert"></div>
  <p>Si no la recuerdas: <code>tecladoia config</code> en el equipo donde corre.</p>
</form>
<script>
document.getElementById("acceso").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const clave = document.getElementById("clave").value;
  if (!clave) return;
  // Se manda una vez por la dirección; el servicio contesta con la cookie y
  // acto seguido se limpia la barra para no dejarla escrita ahí.
  location.replace("/?clave=" + encodeURIComponent(clave));
});
if (location.search.includes("clave=")) {
  document.getElementById("error").textContent = "Esa clave no es la del panel.";
  history.replaceState(null, "", "/");
}
</script>
</body>
</html>
"""
        return "401 Unauthorized", "text/html; charset=utf-8", pagina.encode("utf-8")

    @staticmethod
    def _envolver(
        estado: str, tipo: str, cuerpo: bytes, extras: Optional[list[str]] = None
    ) -> bytes:
        cabeceras = [
            f"HTTP/1.1 {estado}",
            f"Content-Type: {tipo}",
            f"Content-Length: {len(cuerpo)}",
            "Cache-Control: no-store",
            "X-Content-Type-Options: nosniff",
            "Referrer-Policy: no-referrer",
            "Connection: close",
        ]
        cabeceras.extend(extras or [])
        return ("\r\n".join(cabeceras) + "\r\n\r\n").encode("latin-1") + cuerpo

    # --- canal de sucesos -------------------------------------------------
    async def _transmitir_sucesos(self, escritor: asyncio.StreamWriter) -> None:
        """Deja la conexión abierta y va escribiendo lo que ocurre.

        Es lo que evita que la página pregunte «¿ha cambiado algo?» cada pocos
        segundos: se queda escuchando y el servicio le cuenta.
        """
        cabeceras = (
            "HTTP/1.1 200 OK" + _FIN +
            "Content-Type: text/event-stream; charset=utf-8" + _FIN +
            "Cache-Control: no-store" + _FIN +
            "Connection: keep-alive" + _FIN +
            "X-Accel-Buffering: no" + _FIN + _FIN
        )
        escritor.write(cabeceras.encode("latin-1"))
        await escritor.drain()

        cola = self.servidor.bus.suscribir()
        try:
            saludo = json.dumps(
                {"estado": self.gestor.resumen()}, ensure_ascii=False, default=str
            )
            escritor.write(_suceso("bienvenida", saludo))
            await escritor.drain()
            while True:
                try:
                    suceso = await asyncio.wait_for(cola.get(), timeout=LATIDO_S)
                except asyncio.TimeoutError:
                    # Un latido de vez en cuando: sin él, cualquier intermediario
                    # da la conexión por muerta y la corta.
                    escritor.write(b": latido" + _SALTO + _SALTO)
                    await escritor.drain()
                    continue
                carga = json.dumps(suceso["datos"], ensure_ascii=False, default=str)
                escritor.write(_suceso(suceso["tipo"], carga, suceso["id"]))
                await escritor.drain()
        except (ConnectionError, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self.servidor.bus.cancelar(cola)
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    # --- enrutado ---------------------------------------------------------
    async def _responder(
        self,
        metodo: str,
        ruta: str,
        cuerpo: bytes,
        consulta: Optional[dict[str, list[str]]] = None,
    ) -> tuple[str, str, bytes]:
        if ruta.startswith("/api/") or ruta.startswith("/descargar"):
            try:
                return await self._api(metodo, ruta, self._json(cuerpo), consulta or {})
            except (ValueError, KeyError) as error:
                return self._error("400 Bad Request", str(error))
            except ErrorTransporte as error:
                return self._error("503 Service Unavailable", str(error))
        return self._estatico(ruta)

    def _adjuntar(self, nombre: str) -> None:
        """Marca la respuesta para que el navegador la guarde con ese nombre.

        Sin esto, un CSV o un zip se abren dentro de la página en vez de
        descargarse, que es justo lo contrario de lo que quiere quien pulsa.
        """
        self._adjunto = nombre

    def _error(self, estado: str, mensaje: str) -> tuple[str, str, bytes]:
        cuerpo = json.dumps({"error": mensaje}, ensure_ascii=False).encode("utf-8")
        return estado, "application/json; charset=utf-8", cuerpo

    def _estatico(self, ruta: str) -> tuple[str, str, bytes]:
        """Sirve la página desde disco, sin dejar salir de su carpeta."""
        import mimetypes

        nombre = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
        raiz = CARPETA_WEB.resolve()
        destino = (raiz / nombre).resolve()
        try:
            destino.relative_to(raiz)
        except ValueError:
            destino = raiz / "index.html"
        if not destino.is_file():
            return "404 Not Found", "text/plain; charset=utf-8", b"No existe esa pagina."
        tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "image/svg+xml"):
            tipo = f"{tipo}; charset=utf-8"
        return "200 OK", tipo, destino.read_bytes()

    # --- la API -----------------------------------------------------------
    async def _api(
        self,
        metodo: str,
        ruta: str,
        datos: dict[str, Any],
        consulta: dict[str, list[str]],
    ) -> tuple[str, str, bytes]:
        tipo = "application/json; charset=utf-8"

        if ruta == "/descargar/tecladoia.zip":
            from .empaquetado import construir_zip

            self._adjuntar("tecladoia.zip")
            return "200 OK", "application/zip", construir_zip()
        if ruta == "/api/bitacora.csv":
            self._adjuntar("bitacora.csv")
            return "200 OK", "text/csv; charset=utf-8", self._bitacora_csv(consulta)
        if ruta == "/api/bitacora":
            return (
                "200 OK",
                tipo,
                json.dumps(
                    {"entradas": self._bitacora(consulta)}, ensure_ascii=False, default=str
                ).encode("utf-8"),
            )

        resultado = await self._resolver(metodo, ruta, datos)
        if resultado is None:
            return self._error("404 Not Found", "No existe esa ruta")
        cuerpo = json.dumps(resultado, ensure_ascii=False, default=str).encode("utf-8")
        return "200 OK", tipo, cuerpo

    def _panorama(self) -> dict[str, Any]:
        """Todo lo que la página necesita para pintarse de cero."""
        from .transporte.base import hay_bleak

        return {
            "estado": {**self.gestor.resumen(), **self.servidor.resumen_actividad()},
            "historial": self.servidor.historial[-25:],
            "avisos": self.servidor.avisos[-20:],
            "agentes": instalador.revisar(),
            "pendientes": self.servidor.aprobaciones.listar(),
            "ajustes": self._ajustes_json(),
            "servicio": {
                "puerto_enganches": self.servidor.puerto,
                "hay_bluetooth": hay_bleak(),
                "subida": self.gestor.subida,
                "solo_local": self.solo_local,
                "dictado_listo": _dictado_listo(),
            },
        }

    async def _resolver(self, metodo: str, ruta: str, datos: dict[str, Any]) -> Optional[Any]:
        # ---- lectura -----------------------------------------------------
        if ruta == "/api/estado":
            return self._panorama()
        if ruta == "/api/opciones":
            return self._opciones()
        if ruta == "/api/agentes":
            return {"agentes": instalador.revisar()}
        if ruta == "/api/paquete":
            from .empaquetado import resumen as resumen_paquete

            return resumen_paquete()
        if ruta == "/api/reglas":
            if metodo == "POST":
                return self._guardar_reglas(datos)
            return {"reglas": [vars(r) for r in self.ajustes.reglas]}
        if ruta == "/api/teclas":
            if metodo == "POST":
                return await self._guardar_tecla(datos)
            return {"modos": self._modos_json()}
        if ruta == "/api/ajustes":
            if metodo == "POST":
                return self._guardar_ajustes(datos)
            return {"ajustes": self._ajustes_json()}
        if ruta == "/api/luces":
            if metodo == "POST":
                return await self._guardar_luces(datos)
            return self._luces()
        if ruta == "/api/colores":
            if metodo == "POST":
                crudos = datos.get("colores")
                if not isinstance(crudos, dict):
                    raise ValueError("Se esperaba una tabla de efecto a color.")
                nuevos = dict(getattr(self.ajustes, "colores_efecto", {}))
                for clave, valor in crudos.items():
                    texto = str(valor or "").strip()
                    if texto:
                        nuevos[str(int(clave))] = texto[:24]
                    else:
                        nuevos.pop(str(int(clave)), None)
                self.ajustes.colores_efecto = nuevos
                self.ajustes.guardar()
            return {"ok": True, "efectos": self._efectos_json()}
        if ruta == "/api/aplicaciones":
            if metodo == "POST":
                return self._guardar_aplicaciones(datos)
            return {"aplicaciones": list(self.ajustes.aplicaciones)}

        # ---- acciones ----------------------------------------------------
        if metodo != "POST":
            return None

        if ruta == "/api/palanca":
            valor = datos.get("valor")
            self.gestor.palanca_forzada = None if valor is None else int(valor)
            self.servidor.bus.publicar("estado", self.gestor.resumen())
            return self._panorama()
        if ruta == "/api/modo-aprobacion":
            modo = str(datos.get("modo") or "palanca")
            if modo not in ("palanca", "siempre_preguntar", "siempre_permitir"):
                raise ValueError(f"Modo de aprobación desconocido: {modo}")
            self.ajustes.modo_aprobacion = modo
            self.ajustes.guardar()
            return self._panorama()
        if ruta == "/api/luz":
            efecto = EfectoLuz(int(datos.get("efecto", 0)))
            return {"ok": await self.gestor.aplicar_efecto(efecto), "efecto": int(efecto)}
        if ruta == "/api/luces/probar":
            # Llega el momento del agente, no el efecto: se enciende lo que ese
            # momento tenga asignado ahora mismo, que es lo que se quiere ver.
            if "estado" in datos:
                momento = EstadoIA.desde_codigo(int(datos["estado"]))
                efecto = self.gestor.efecto_de(momento) or EfectoLuz.APAGADO
                encendido = await self.gestor.aplicar_efecto(efecto)
                return {
                    "ok": encendido,
                    "estado": momento.etiqueta,
                    "efecto": efecto.etiqueta,
                }
            efecto = EfectoLuz(int(datos.get("efecto", 0)))
            return {"ok": await self.gestor.aplicar_efecto(efecto), "efecto": efecto.etiqueta}
        if ruta == "/api/brillo":
            valor = max(0, min(100, int(datos.get("valor", 35))))
            hecho = await self.gestor.ajustar_brillo(valor)
            if hecho:
                self.ajustes.brillo = valor
                self.ajustes.guardar()
            return {"ok": hecho, "valor": valor}
        if ruta == "/api/modo-trabajo":
            modo = int(datos.get("modo", 0))
            if not 0 <= modo < MODOS_DISPONIBLES:
                raise ValueError(f"El teclado solo tiene {MODOS_DISPONIBLES} modos.")
            return {"ok": await self.gestor.cambiar_modo_trabajo(modo), "modo": modo}
        if ruta == "/api/nombre":
            nombre = str(datos.get("nombre") or "").strip()
            if not nombre:
                raise ValueError("Escribe un nombre para el teclado.")
            return {"ok": await self.gestor.renombrar(nombre), "nombre": nombre}
        if ruta == "/api/conexion":
            return await self._conexion(str(datos.get("accion") or "conectar"))
        if ruta == "/api/buscar":
            return await self._buscar(float(datos.get("segundos", 6)))
        if ruta == "/api/aprobar":
            return self._aprobar(datos)
        if ruta == "/api/reglas/probar":
            return self._probar_regla(datos)
        if ruta == "/api/pantalla":
            return await self._pantalla(datos)
        if ruta == "/api/pantalla/cancelar":
            cortada = self.gestor.cancelar_subida()
            return {
                "ok": cortada,
                "aviso": None if cortada else "No había ninguna subida en marcha.",
            }
        if ruta == "/api/agentes/instalar":
            return {"resultado": instalador.instalar(datos.get("agentes") or None)}
        if ruta == "/api/agentes/desinstalar":
            return {"resultado": instalador.desinstalar(datos.get("agentes") or None)}
        return None

    # --- piezas -----------------------------------------------------------
    def _opciones(self) -> dict[str, Any]:
        from . import teclas as tabla_teclas
        from .modelo import Decision, MotivoDecision

        return {
            "efectos": self._efectos_json(),
            "estados": [
                {"codigo": int(e), "etiqueta": e.etiqueta, "descripcion": e.descripcion}
                for e in EstadoIA
            ],
            "decisiones": [d.value for d in Decision],
            "motivos": {m.value: m.explicacion for m in MotivoDecision},
            # Nombre y código de cada una: la página los enseña juntos para
            # que se vea qué se le va a escribir al teclado.
            "modificadores": [
                {"nombre": n, "codigo": c}
                for n, c in sorted(tabla_teclas.MODIFICADORES.items())
            ],
            "teclas": [
                {"nombre": n, "codigo": c}
                for n, c in sorted(tabla_teclas.NOMBRES_HID.items())
            ],
            "modos_disponibles": MODOS_DISPONIBLES,
            "teclas_por_modo": TECLAS_POR_MODO,
        }

    _CAMPOS_AJUSTES = (
        "modo_aprobacion", "transporte", "nombre_dispositivo", "puerto_hooks",
        "puerto_panel", "puente_host", "puente_puerto", "vigencia_cache_ms",
        "espera_palanca_s", "intervalo_sondeo_s", "reglas_permisivas",
        "sincronizar_config_agentes", "avisar_en_escritorio", "brillo", "accesible",
        "aprobacion_remota", "espera_aprobacion_s", "seguir_aplicacion",
        "segundos_reposo", "efecto_reposo",
    )

    def _ajustes_json(self) -> dict[str, Any]:
        return {
            campo: getattr(self.ajustes, campo)
            for campo in self._CAMPOS_AJUSTES
            if hasattr(self.ajustes, campo)
        }

    def _guardar_ajustes(self, datos: dict[str, Any]) -> dict[str, Any]:
        """Solo se tocan los campos conocidos, y con el tipo que les toca."""
        cambios: list[str] = []
        for campo, actual in self._ajustes_json().items():
            if campo not in datos:
                continue
            crudo = datos[campo]
            try:
                if isinstance(actual, bool):
                    valor: Any = bool(crudo)
                elif isinstance(actual, int):
                    valor = int(crudo)
                elif isinstance(actual, float):
                    valor = float(crudo)
                else:
                    valor = str(crudo)
            except (TypeError, ValueError):
                raise ValueError(f"El valor de «{campo}» no tiene el formato esperado.")
            if valor != actual:
                setattr(self.ajustes, campo, valor)
                cambios.append(campo)
        if cambios:
            self.ajustes.guardar()
        return {"ok": True, "cambios": cambios, "ajustes": self._ajustes_json()}

    def _guardar_reglas(self, datos: dict[str, Any]) -> dict[str, Any]:
        from .config import Regla

        crudas = datos.get("reglas")
        if not isinstance(crudas, list):
            raise ValueError("Se esperaba una lista de reglas.")
        nuevas: list[Regla] = []
        for entrada in crudas:
            if not isinstance(entrada, dict):
                continue
            patron = str(entrada.get("patron") or "").strip()
            if not patron:
                continue
            decision = str(entrada.get("decision") or "preguntar").strip().lower()
            if decision not in ("permitir", "preguntar", "denegar"):
                raise ValueError(
                    f"«{decision}» no es una decisión válida. "
                    "Usa permitir, preguntar o denegar."
                )
            nuevas.append(Regla(
                patron=patron,
                decision=decision,
                nota=str(entrada.get("nota") or ""),
                agente=str(entrada.get("agente") or "*").strip().lower() or "*",
            ))
        self.ajustes.reglas = nuevas
        self.ajustes.guardar()
        return {"ok": True, "reglas": [vars(r) for r in nuevas]}

    def _probar_regla(self, datos: dict[str, Any]) -> dict[str, Any]:
        """Enseña qué pasaría con una orden concreta, sin ejecutar nada."""
        from .modelo import Contexto
        from .politica import decidir, regla_aplicable

        contexto = Contexto(
            agente=str(datos.get("agente") or "claude").lower(),
            evento="prueba",
            herramienta=str(datos.get("herramienta") or "") or None,
            comando=str(datos.get("comando") or "") or None,
            ruta=str(datos.get("ruta") or "") or None,
        )
        crudo = datos.get("palanca", "actual")
        if crudo in (None, "", "ninguna"):
            palanca: Optional[int] = None
        elif crudo == "actual":
            palanca = self.gestor.resumen().get("palanca")
        else:
            palanca = int(crudo)
        veredicto = decidir(self.ajustes, palanca, contexto, conectado=self.gestor.conectado)
        coincide = regla_aplicable(self.ajustes.reglas, contexto)
        return {
            "decision": veredicto.decision.value,
            "motivo": veredicto.motivo.value,
            "explicacion": veredicto.explicacion,
            "palanca": palanca,
            "regla": vars(coincide) if coincide else None,
        }

    def _aprobar(self, datos: dict[str, Any]) -> dict[str, Any]:
        from .aprobaciones import RESPUESTAS

        respuesta = str(datos.get("respuesta") or "").strip().lower()
        if respuesta not in RESPUESTAS:
            raise ValueError("Contesta «permitir» o «denegar».")
        identificador = datos.get("id")
        if identificador in (None, "", "todas"):
            atendidas = self.servidor.aprobaciones.responder_todas(respuesta)
            return {"ok": atendidas > 0, "atendidas": atendidas}
        atendida = self.servidor.aprobaciones.responder(str(identificador), respuesta)
        return {
            "ok": atendida,
            "aviso": None if atendida else "Esa petición ya se resolvió o caducó.",
        }

    def _efectos_json(self) -> list[dict[str, Any]]:
        """Los efectos con el color que se les haya anotado.

        Manda lo que la persona haya visto en su teclado sobre lo que digamos
        nosotros: el color no se puede consultar al aparato, así que la única
        fuente fiable son sus ojos.
        """
        anotados = getattr(self.ajustes, "colores_efecto", {}) or {}
        return [
            {
                "codigo": int(f),
                "etiqueta": f.etiqueta,
                "color": anotados.get(str(int(f)), f.color),
            }
            for f in EfectoLuz
        ]

    def _luces(self) -> dict[str, Any]:
        return {
            "luces": [
                {
                    "estado": int(e),
                    "etiqueta": e.etiqueta,
                    "descripcion": e.descripcion,
                    "efecto": int(self.gestor.efecto_de(e) or 0),
                }
                for e in sorted(EstadoIA, key=int)
            ],
            "efectos": self._efectos_json(),
        }

    async def _guardar_luces(self, datos: dict[str, Any]) -> dict[str, Any]:
        crudas = datos.get("luces")
        if not isinstance(crudas, dict):
            raise ValueError("Se esperaba una tabla de estado a efecto.")
        nuevas = dict(self.ajustes.luces_por_estado)
        for clave, valor in crudas.items():
            try:
                nuevas[str(int(clave))] = int(EfectoLuz(int(valor)))
            except (TypeError, ValueError):
                raise ValueError(f"«{valor}» no es un efecto conocido.")
        self.ajustes.luces_por_estado = nuevas
        self.ajustes.guardar()
        escrito = False
        if datos.get("aplicar") and self.gestor.conectado:
            escrito = await self.gestor.guardar_luces_de_ia()
        return {
            "ok": True,
            "guardado_en_el_teclado": escrito,
            "aviso": None if escrito or not self.gestor.conectado else (
                "Se guardó aquí, pero el teclado no aceptó la escritura."
            ),
            **self._luces(),
        }

    def _guardar_aplicaciones(self, datos: dict[str, Any]) -> dict[str, Any]:
        crudas = datos.get("aplicaciones")
        if not isinstance(crudas, list):
            raise ValueError("Se esperaba una lista de aplicaciones.")
        nuevas: list[dict] = []
        for entrada in crudas:
            if not isinstance(entrada, dict):
                continue
            patron = str(entrada.get("patron") or "").strip()
            if not patron:
                continue
            modo = int(entrada.get("modo", 0))
            if not 0 <= modo < MODOS_DISPONIBLES:
                raise ValueError(f"El modo {modo + 1} no existe.")
            donde = str(entrada.get("en") or "proceso")
            if donde not in ("proceso", "titulo", "cualquiera"):
                raise ValueError(f"«{donde}» no es un sitio donde buscar.")
            nuevas.append({"patron": patron, "modo": modo, "en": donde})
        self.ajustes.aplicaciones = nuevas
        self.ajustes.guardar()
        return {"ok": True, "aplicaciones": nuevas}

    async def _conexion(self, accion: str) -> dict[str, Any]:
        if accion == "desconectar":
            await self.gestor.desconectar()
            return {"ok": True, "estado": self.gestor.resumen()}
        if accion != "conectar":
            raise ValueError("La acción debe ser «conectar» o «desconectar».")
        try:
            await self.gestor.conectar()
        except ErrorTransporte as error:
            return {"ok": False, "error": str(error), "estado": self.gestor.resumen()}
        return {"ok": True, "estado": self.gestor.resumen()}

    async def _buscar(self, segundos: float) -> dict[str, Any]:
        """Busca teclados: primero entre los emparejados, luego por el aire."""
        encontrados: list[dict[str, str]] = []
        try:
            from .transporte.windows_emparejado import buscar_emparejados, hay_winrt

            if hay_winrt():
                encontrados += [
                    {"direccion": d, "nombre": n, "origen": "emparejado"}
                    for d, n in await buscar_emparejados()
                ]
        except Exception:  # noqa: BLE001 - fuera de Windows esto no existe
            pass

        from .transporte.base import hay_bleak

        if hay_bleak() and not encontrados:
            from .transporte.ble import buscar_teclados

            encontrados += [
                {"direccion": d, "nombre": n, "origen": "anunciándose"}
                for d, n in await buscar_teclados(max(1.0, min(30.0, segundos)))
            ]
        return {
            "ok": True,
            "encontrados": encontrados,
            "error": None if encontrados else (
                "No apareció ninguno. Si el teclado está emparejado y encendido, "
                "comprueba que ninguna otra aplicación lo tenga ocupado."
            ),
        }

    # ---- teclas ----------------------------------------------------------
    def _modos_json(self) -> list[dict[str, Any]]:
        return [
            {
                "nombre": modo.nombre,
                "teclas": [
                    {
                        "atajo": t.atajo,
                        "descripcion": t.descripcion,
                        "macro": [list(p) for p in t.macro],
                        "vacia": t.esta_vacia(),
                    }
                    for t in modo.teclas
                ],
            }
            for modo in self.ajustes.modos
        ]

    async def _guardar_tecla(self, datos: dict[str, Any]) -> dict[str, Any]:
        """Guarda la tecla en la configuración y, si hay teclado, la escribe."""
        from . import teclas as tabla_teclas
        from .modelo import Modo, Tecla

        modo = int(datos.get("modo", 0))
        indice = int(datos.get("indice", 0))
        if not 0 <= modo < MODOS_DISPONIBLES:
            raise ValueError(f"El teclado tiene {MODOS_DISPONIBLES} modos.")
        if not 0 <= indice < TECLAS_POR_MODO:
            raise ValueError(f"Cada modo tiene {TECLAS_POR_MODO} teclas.")
        while len(self.ajustes.modos) <= modo:
            self.ajustes.modos.append(Modo(nombre=f"Modo {len(self.ajustes.modos) + 1}"))
        destino = self.ajustes.modos[modo]
        while len(destino.teclas) <= indice:
            destino.teclas.append(Tecla())
        tecla = destino.teclas[indice]

        atajo = str(datos.get("atajo") or "").strip()
        descripcion = str(datos.get("descripcion") or "").strip()
        texto_macro = str(datos.get("texto_macro") or "")

        if atajo:
            # Se valida antes de guardar: mejor un error claro aquí que una
            # tecla que no hace nada cuando la pulsas.
            tabla_teclas.atajo_a_codigos(atajo)
        macro = tabla_teclas.texto_a_macro(texto_macro) if texto_macro else []
        if atajo and macro:
            raise ValueError("Una tecla lleva atajo o macro, no las dos cosas.")

        tecla.atajo = atajo
        tecla.descripcion = descripcion
        tecla.macro = macro
        if nombre := str(datos.get("nombre_modo") or "").strip():
            destino.nombre = nombre
        self.ajustes.guardar()

        escrita = False
        if self.gestor.conectado and (atajo or macro or descripcion):
            escrita = await self.gestor.programar_tecla(
                modo, indice, atajo, descripcion, macro
            )
        return {
            "ok": True,
            "escrita_en_el_teclado": escrita,
            "aviso": None if escrita or not self.gestor.conectado else (
                "Se guardó aquí, pero el teclado no aceptó la escritura."
            ),
            "modos": self._modos_json(),
        }

    # ---- bitácora --------------------------------------------------------
    def _bitacora(self, consulta: dict[str, list[str]]) -> list[dict[str, Any]]:
        """Las decisiones guardadas, filtradas como pida la página."""
        from .registro import leer_bitacora

        def uno(nombre: str, por_defecto: str = "") -> str:
            return (consulta.get(nombre) or [por_defecto])[0]

        try:
            limite = max(1, min(2000, int(uno("n", "100"))))
        except ValueError:
            limite = 100
        entradas = leer_bitacora(limite)
        if agente := uno("agente").lower():
            entradas = [e for e in entradas if str(e.get("agente", "")).lower() == agente]
        if decision := uno("decision").lower():
            entradas = [e for e in entradas if str(e.get("decision", "")).lower() == decision]
        if texto := uno("texto").lower():
            campos = ("herramienta", "comando", "regla", "motivo")
            entradas = [
                e for e in entradas
                if texto in " ".join(str(e.get(c) or "") for c in campos).lower()
            ]
        return entradas

    def _bitacora_csv(self, consulta: dict[str, list[str]]) -> bytes:
        import csv
        import io

        columnas = [
            "instante", "agente", "evento", "decision", "motivo",
            "regla", "palanca", "herramienta", "comando",
        ]
        papel = io.StringIO(newline="")
        escritor = csv.DictWriter(papel, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        for entrada in self._bitacora(consulta):
            escritor.writerow({c: entrada.get(c, "") for c in columnas})
        # El BOM hace que Excel en español abra bien las tildes.
        return bytes([0xEF, 0xBB, 0xBF]) + papel.getvalue().encode("utf-8")

    # ---- pantalla --------------------------------------------------------
    async def _pantalla(self, datos: dict[str, Any]) -> dict[str, Any]:
        """Recibe una imagen o un GIF en base64 y lo escribe en la pantalla."""
        import base64

        from .imagen import ErrorImagen, fotogramas

        modo = int(datos.get("modo", 0))
        if not 0 <= modo < MODOS_DISPONIBLES:
            raise ValueError(f"El teclado tiene {MODOS_DISPONIBLES} modos.")
        crudo = str(datos.get("datos") or "")
        if not crudo:
            raise ValueError("No llegó ninguna imagen.")
        if "," in crudo[:64]:  # viene como data:image/gif;base64,....
            crudo = crudo.split(",", 1)[1]
        try:
            archivo = base64.b64decode(crudo, validate=False)
        except Exception as error:  # noqa: BLE001
            raise ValueError(f"La imagen no se pudo descifrar: {error}") from error

        try:
            cuadros, retardo = fotogramas(archivo)
        except ErrorImagen as error:
            raise ValueError(str(error)) from error

        resultado = await self.gestor.enviar_imagen(
            modo,
            cuadros,
            retardo,
            al_avanzar=lambda hecho, total: self.servidor.bus.publicar(
                "subida", {"modo": modo, "hecho": hecho, "total": total}
            ),
        )
        return {"ok": True, **resultado}

    @staticmethod
    def _json(cuerpo: bytes) -> dict[str, Any]:
        if not cuerpo:
            return {}
        try:
            datos = json.loads(cuerpo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return datos if isinstance(datos, dict) else {}


__all__ = ["PanelWeb"]
