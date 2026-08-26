"""Servidor de enganches.

Escucha en un socket de dominio Unix (y, si se pide, también en un puerto TCP)
las llamadas que hacen los programas de IA a través de ``tecladoia enganche``.
Por cada evento refleja el momento del agente en la barra LED y, cuando toca
decidir, resuelve el permiso con la palanca y las reglas.

Sobre la velocidad de respuesta: la actualización de la luz se lanza en segundo
plano y la decisión se contesta con la caché de la palanca si sigue vigente. El
enganche bloquea al agente de IA mientras espera, así que cada milisegundo aquí
se nota al escribir.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from . import agentes
from .agentes.base import AgenteIA, EventoEnganche
from .config import Ajustes, ruta_socket
from .dispositivo import GestorTeclado
from .modelo import Contexto, Decision, EstadoIA, Veredicto
from .politica import decidir
from .registro import anotar, obtener

_log = obtener("servidor")

#: Nombres de evento del proyecto original que se aceptan tal cual, para que
#: quien ya tenga sus enganches instalados no tenga que rehacerlos.
_ESTADOS_HEREDADOS = {
    "SessionStart": EstadoIA.SESION_INICIADA,
    "SessionEnd": EstadoIA.SESION_FINALIZADA,
    "PreToolUse": EstadoIA.HERRAMIENTA_EN_CURSO,
    "PostToolUse": EstadoIA.HERRAMIENTA_TERMINADA,
    "Notification": EstadoIA.NOTIFICACION,
    "TaskCompleted": EstadoIA.TAREA_COMPLETADA,
    "Stop": EstadoIA.DETENIDO,
    "UserPromptSubmit": EstadoIA.PETICION_ENVIADA,
    "PermissionRequest": EstadoIA.ESPERANDO_APROBACION,
}


class ServidorEnganches:
    """Atiende a los enganches de los programas de IA."""

    def __init__(self, gestor: GestorTeclado, ajustes: Optional[Ajustes] = None) -> None:
        self.gestor = gestor
        self.ajustes = ajustes or gestor.ajustes
        self._servidores: list[asyncio.AbstractServer] = []
        self._tareas: set[asyncio.Task] = set()
        self.ruta_socket: Optional[Path] = None
        self.puerto: Optional[int] = None
        #: Últimas decisiones, para el panel web.
        self.historial: list[dict[str, Any]] = []

    # --- ciclo de vida --------------------------------------------------
    async def arrancar(self, con_tcp: bool = True) -> None:
        if os.name != "nt":
            self.ruta_socket = ruta_socket()
            with contextlib.suppress(FileNotFoundError):
                self.ruta_socket.unlink()
            self.ruta_socket.parent.mkdir(parents=True, exist_ok=True)
            servidor = await asyncio.start_unix_server(self._atender, path=str(self.ruta_socket))
            self.ruta_socket.chmod(0o600)  # solo quien lo ejecuta puede aprobar
            self._servidores.append(servidor)
            _log.info("Escuchando en %s", self.ruta_socket)

        if con_tcp:
            puerto = self.ajustes.puerto_hooks
            for intento in range(10):
                try:
                    servidor = await asyncio.start_server(
                        self._atender, "127.0.0.1", puerto + intento
                    )
                except OSError:
                    continue
                self._servidores.append(servidor)
                self.puerto = puerto + intento
                _log.info("Escuchando en 127.0.0.1:%s", self.puerto)
                break
            else:
                _log.error(
                    "No se pudo abrir ningún puerto entre %s y %s", puerto, puerto + 9
                )

    async def detener(self) -> None:
        for servidor in self._servidores:
            servidor.close()
            with contextlib.suppress(Exception):
                await servidor.wait_closed()
        self._servidores.clear()
        for tarea in list(self._tareas):
            tarea.cancel()
        self._tareas.clear()
        if self.ruta_socket is not None:
            with contextlib.suppress(FileNotFoundError):
                self.ruta_socket.unlink()

    async def servir_para_siempre(self) -> None:
        if not self._servidores:
            raise RuntimeError("El servidor no está arrancado")
        await asyncio.gather(*(s.serve_forever() for s in self._servidores))

    # --- atención de clientes -------------------------------------------
    async def _atender(self, lector: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        try:
            linea = await asyncio.wait_for(lector.readline(), timeout=5)
        except (asyncio.TimeoutError, ConnectionError):
            escritor.close()
            return
        texto = linea.decode("utf-8", "replace").strip()
        respuesta = await self.procesar(texto) if texto else {"ok": False, "error": "vacío"}
        try:
            escritor.write((json.dumps(respuesta, ensure_ascii=False) + "\n").encode("utf-8"))
            await escritor.drain()
        except (ConnectionError, RuntimeError):
            pass
        finally:
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    async def procesar(self, texto: str) -> dict[str, Any]:
        """Resuelve una petición ya recibida. Es el punto que prueban los tests."""
        peticion = self._interpretar(texto)
        orden = peticion.get("orden", "evento")

        if orden == "estado":
            return {"ok": True, **self.gestor.resumen()}
        if orden == "palanca":
            valor = peticion.get("valor")
            self.gestor.palanca_forzada = None if valor is None else int(valor)
            return {"ok": True, **self.gestor.resumen()}
        if orden == "luz":
            estado = EstadoIA.desde_codigo(int(peticion.get("valor", 0)))
            enviado = await self.gestor.enviar_estado_ia(estado)
            return {"ok": enviado, "estado": int(estado)}
        if orden != "evento":
            return {"ok": False, "error": f"Orden desconocida: {orden}"}

        return await self._procesar_evento(peticion)

    def _interpretar(self, texto: str) -> dict[str, Any]:
        """Acepta el formato propio, el del proyecto original y texto plano."""
        if texto.startswith("{"):
            try:
                datos = json.loads(texto)
            except json.JSONDecodeError:
                return {"orden": "evento", "evento": texto}
            if not isinstance(datos, dict):
                return {"orden": "evento", "evento": texto}
            if "cmd" in datos and "orden" not in datos:
                return self._traducir_heredado(datos)
            return datos
        return {"orden": "evento", "evento": texto}

    @staticmethod
    def _traducir_heredado(datos: dict[str, Any]) -> dict[str, Any]:
        cmd = str(datos.get("cmd", ""))
        if cmd == "status":
            return {"orden": "estado"}
        if cmd == "state":
            return {"orden": "luz", "valor": datos.get("value", 0)}
        if cmd == "permission":
            return {"orden": "evento", "evento": "PermissionRequest"}
        return {"orden": "evento", "evento": cmd}

    async def _procesar_evento(self, peticion: dict[str, Any]) -> dict[str, Any]:
        nombre = str(peticion.get("evento", "")).strip()
        agente_id = str(peticion.get("agente", "")).strip().lower()

        agente: Optional[type[AgenteIA]] = agentes.obtener(agente_id) if agente_id else None
        evento: Optional[EventoEnganche] = agente.evento(nombre) if agente else None
        if evento is None:
            encontrado = agentes.buscar_evento(nombre)
            if encontrado is not None:
                agente, evento = encontrado

        if evento is None:
            estado = _ESTADOS_HEREDADOS.get(nombre)
            if estado is None:
                return {"ok": False, "error": f"Evento desconocido: {nombre}"}
            # Enganche del proyecto original: solo se refleja la luz.
            await self.gestor.enviar_estado_ia(estado)
            return {"ok": True, "evento": nombre, "estado": int(estado)}

        assert agente is not None
        contexto = self._contexto(peticion, agente.id, evento)

        # La luz no debe retrasar la respuesta: se actualiza en paralelo.
        self._en_segundo_plano(self.gestor.enviar_estado_ia(evento.estado))

        veredicto: Optional[Veredicto] = None
        if evento.permiso:
            veredicto = await self._decidir(contexto)
            self._registrar(agente, evento, contexto, veredicto)

        return {
            "ok": True,
            "agente": agente.id,
            "evento": evento.interno,
            "estado": int(evento.estado),
            "decision": veredicto.decision.value if veredicto else None,
            "palanca": veredicto.palanca if veredicto else None,
            "explicacion": veredicto.explicacion if veredicto else None,
            "respuesta": agente.respuesta(evento, veredicto),
        }

    @staticmethod
    def _contexto(peticion: dict[str, Any], agente_id: str, evento: EventoEnganche) -> Contexto:
        crudo = peticion.get("contexto")
        crudo = crudo if isinstance(crudo, dict) else {}
        return Contexto(
            agente=agente_id,
            evento=evento.interno,
            herramienta=crudo.get("herramienta") or crudo.get("tool_name"),
            comando=crudo.get("comando") or crudo.get("command"),
            ruta=crudo.get("ruta") or crudo.get("cwd"),
            sesion=crudo.get("sesion") or crudo.get("session_id"),
        )

    async def _decidir(self, contexto: Contexto) -> Veredicto:
        palanca = await self.gestor.palanca()
        veredicto = decidir(self.ajustes, palanca, contexto, conectado=self.gestor.conectado)
        if self.ajustes.sincronizar_config_agentes:
            self._sincronizar(veredicto)
        return veredicto

    def _sincronizar(self, veredicto: Veredicto) -> None:
        """Alinea la configuración propia de cada agente con la palanca.

        Se hace para todos los agentes instalados, no solo para el que preguntó:
        así una sesión de Codex abierta en otra terminal también se entera.
        """
        if veredicto.palanca is None:
            return
        automatica = veredicto.palanca == 0
        for agente in agentes.AGENTES:
            try:
                if not agente.instalado():
                    continue
                if cambio := agente.sincronizar_palanca(automatica):
                    _log.info("%s: %s", agente.nombre, cambio)
            except Exception:  # noqa: BLE001 - un agente roto no debe frenar la decisión
                _log.exception("No se pudo sincronizar %s", agente.nombre)

    def _registrar(
        self,
        agente: type[AgenteIA],
        evento: EventoEnganche,
        contexto: Contexto,
        veredicto: Veredicto,
    ) -> None:
        entrada = {
            "agente": agente.id,
            "evento": evento.interno,
            "decision": veredicto.decision.value,
            "motivo": veredicto.motivo.value,
            "palanca": veredicto.palanca,
            "regla": veredicto.regla,
            "herramienta": contexto.herramienta,
            "comando": (contexto.comando or "")[:200] or None,
        }
        anotar(entrada)
        self.historial.append(entrada)
        del self.historial[:-100]
        if veredicto.decision is not Decision.PERMITIR:
            _log.info(
                "%s · %s → %s (%s)",
                agente.nombre,
                contexto.resumen(),
                veredicto.decision.value,
                veredicto.explicacion,
            )

    def _en_segundo_plano(self, corrutina) -> None:
        tarea = asyncio.create_task(corrutina)
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)
