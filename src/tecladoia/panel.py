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
from typing import Any, Optional
from urllib.parse import urlparse

from . import instalador
from .config import Ajustes
from .dispositivo import GestorTeclado
from .modelo import EfectoLuz, EstadoIA
from .registro import obtener
from .servidor import ServidorEnganches

_log = obtener("panel")

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

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}/" if self.puerto else ""

    async def arrancar(self) -> None:
        base = self.ajustes.puerto_panel
        for intento in range(10):
            try:
                self._http = await asyncio.start_server(
                    self._atender, "127.0.0.1", base + intento
                )
            except OSError:
                continue
            self.puerto = base + intento
            _log.info("Panel disponible en %s", self.url)
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
            metodo, ruta, _ = peticion.decode("latin-1").split(" ", 2)
            longitud = 0
            while True:
                linea = await asyncio.wait_for(lector.readline(), timeout=5)
                if linea in (b"\r\n", b"\n", b""):
                    break
                nombre, _, valor = linea.decode("latin-1").partition(":")
                if nombre.strip().lower() == "content-length":
                    longitud = int(valor.strip() or 0)
            cuerpo = await lector.readexactly(longitud) if longitud else b""
            estado, tipo, datos = await self._responder(metodo, urlparse(ruta).path, cuerpo)
            escritor.write(self._envolver(estado, tipo, datos))
            await escritor.drain()
        except (asyncio.TimeoutError, ValueError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    @staticmethod
    def _envolver(estado: str, tipo: str, cuerpo: bytes) -> bytes:
        cabeceras = (
            f"HTTP/1.1 {estado}\r\n"
            f"Content-Type: {tipo}\r\n"
            f"Content-Length: {len(cuerpo)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        )
        return cabeceras.encode("latin-1") + cuerpo

    async def _responder(self, metodo: str, ruta: str, cuerpo: bytes) -> tuple[str, str, bytes]:
        if ruta == "/" and metodo == "GET":
            return "200 OK", "text/html; charset=utf-8", _PAGINA.encode("utf-8")

        datos = self._json(cuerpo)
        resultado: Any
        if ruta == "/api/estado":
            resultado = {
                "estado": self.gestor.resumen(),
                "historial": self.servidor.historial[-25:],
                "agentes": instalador.revisar(),
            }
        elif ruta == "/api/efectos":
            resultado = {
                "efectos": [{"codigo": int(f), "etiqueta": f.etiqueta} for f in EfectoLuz],
                "estados": [{"codigo": int(e), "etiqueta": e.etiqueta} for e in EstadoIA],
            }
        elif ruta == "/api/palanca" and metodo == "POST":
            valor = datos.get("valor")
            self.gestor.palanca_forzada = None if valor is None else int(valor)
            resultado = {
                "estado": self.gestor.resumen(),
                "historial": self.servidor.historial[-25:],
                "agentes": instalador.revisar(),
            }
        elif ruta == "/api/luz" and metodo == "POST":
            efecto = EfectoLuz(int(datos.get("efecto", 0)))
            resultado = {"ok": await self.gestor.aplicar_efecto(efecto)}
        elif ruta == "/api/agentes":
            resultado = {"agentes": instalador.revisar()}
        else:
            return (
                "404 Not Found",
                "application/json; charset=utf-8",
                json.dumps({"error": "No existe esa ruta"}, ensure_ascii=False).encode("utf-8"),
            )

        return (
            "200 OK",
            "application/json; charset=utf-8",
            json.dumps(resultado, ensure_ascii=False).encode("utf-8"),
        )

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
