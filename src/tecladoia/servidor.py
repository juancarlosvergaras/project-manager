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
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import agentes
from .agentes.base import AgenteIA, EventoEnganche
from .config import Ajustes, ruta_socket
from .dispositivo import GestorTeclado
from .modelo import Contexto, Decision, EfectoLuz, EstadoIA, Veredicto
from .aprobaciones import ColaAprobaciones
from .politica import decidir
from .sucesos import Bus
from .registro import anotar, obtener

_log = obtener("servidor")

#: Lo que hace que merezca la pena avisar al panel de una lectura nueva.
_CAMPOS_QUE_IMPORTAN = (
    "conectado", "bateria", "firmware", "modo_trabajo", "palanca", "palanca_forzada",
)

#: Nombres de evento del proyecto original que se aceptan tal cual, para que
#: quien ya tenga sus enganches instalados no tenga que rehacerlos.
#: Estado al que vuelve la barra cuando no hay nada que contar.
ESTADO_EN_REPOSO = EstadoIA.DETENIDO

#: Momentos que duran un instante: se muestran y la barra vuelve al reposo.
ESTADOS_BREVES = frozenset(
    {
        EstadoIA.NOTIFICACION,
        EstadoIA.HERRAMIENTA_TERMINADA,
        EstadoIA.TAREA_COMPLETADA,
        EstadoIA.PETICION_ENVIADA,
    }
)

#: Momentos que ya son de reposo: no hace falta programar nada tras ellos.
ESTADOS_TRANQUILOS = frozenset({EstadoIA.DETENIDO, EstadoIA.SESION_FINALIZADA})

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
        #: Qué agente movió la barra por última vez, y cuándo.
        self.agente_activo: Optional[str] = None
        #: Se llama cuando el agente que manda en el modo puesto termina su
        #: turno. Lo usa el modo manos libres para abrir el micrófono. Lo
        #: instala la línea de órdenes; aquí no se sabe dictar.
        self.al_terminar_el_dueno: Optional[Callable[[str], None]] = None
        self.ultimo_evento_en: float = 0.0
        self._bucle: Optional[asyncio.AbstractEventLoop] = None
        self._reposo: Optional[asyncio.Task] = None
        self._vigilante: Optional[asyncio.Task] = None
        self._ultimo_estado_registrado: Optional[EstadoIA] = None
        #: Canal por el que el panel se entera de todo sin ir preguntando.
        self.bus = Bus()
        #: Peticiones esperando que alguien conteste desde el navegador.
        self.aprobaciones = ColaAprobaciones(self.bus)
        #: Los últimos avisos recibidos. Sin esto, cuando la barra hace algo
        #: raro no hay forma de saber qué programa lo pidió ni por qué.
        self.avisos: list[dict[str, Any]] = []
        #: Lo último que se le vio al teclado, para avisar solo de lo que cambia.
        self._ultimo_resumen: dict[str, Any] = {}
        self.gestor.observar(self._al_cambiar_el_teclado)

    # --- ciclo de vida --------------------------------------------------
    async def arrancar(self, con_tcp: bool = True) -> None:
        # Se guarda el bucle para que el vigía de ChatGPT, que vive en su
        # propio hilo, pueda cruzar hasta aquí sin tocar asyncio desde fuera.
        self._bucle = asyncio.get_running_loop()
        if os.name != "nt":
            self.ruta_socket = ruta_socket()
            with contextlib.suppress(FileNotFoundError):
                self.ruta_socket.unlink()
            self.ruta_socket.parent.mkdir(parents=True, exist_ok=True)
            servidor = await asyncio.start_unix_server(self._atender, path=str(self.ruta_socket))
            self.ruta_socket.chmod(0o600)  # solo quien lo ejecuta puede aprobar
            self._servidores.append(servidor)
            _log.info("Escuchando en %s", self.ruta_socket)

        if not con_tcp and os.name == "nt":
            _log.warning(
                "En Windows no hay sockets Unix: se abre el puerto TCP de todos "
                "modos, porque si no el servicio se quedaria sin escuchar."
            )
            con_tcp = True

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

        if self.ajustes.segundos_hasta_reposo > 0:
            self._vigilante = asyncio.create_task(self._vigilar_inactividad())

    async def detener(self) -> None:
        for tarea in (self._vigilante, self._reposo):
            if tarea is not None:
                tarea.cancel()
        self._vigilante = self._reposo = None
        for servidor in self._servidores:
            servidor.close()
            with contextlib.suppress(Exception):
                await servidor.wait_closed()
        self._servidores.clear()
        self.aprobaciones.cancelar_todo()
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

    def resumen_actividad(self) -> dict[str, Any]:
        """Quién movió la barra por última vez y hace cuánto."""
        return {
            "agente_activo": self.agente_activo,
            "segundos_sin_eventos": (
                round(time.monotonic() - self.ultimo_evento_en, 1)
                if self.ultimo_evento_en
                else None
            ),
        }

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
            return {"ok": True, **self.gestor.resumen(), **self.resumen_actividad()}
        if orden == "palanca":
            valor = peticion.get("valor")
            self.gestor.palanca_forzada = None if valor is None else int(valor)
            return {"ok": True, **self.gestor.resumen()}
        if orden == "luz":
            estado = EstadoIA.desde_codigo(int(peticion.get("valor", 0)))
            enviado = await self.gestor.enviar_estado_ia(estado)
            return {"ok": enviado, "estado": int(estado)}
        if orden == "efecto":
            # Solo un proceso puede tener el enlace BLE abierto, así que las
            # órdenes de luz de la línea de órdenes pasan por aquí en lugar de
            # abrir una segunda conexión que chocaría con esta.
            try:
                efecto = EfectoLuz(int(peticion.get("valor", 0)))
            except ValueError:
                return {"ok": False, "error": "Efecto desconocido"}
            enviado = await self.gestor.aplicar_efecto(efecto)
            return {"ok": enviado, "efecto": int(efecto), "etiqueta": efecto.etiqueta}
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
            self._anotar_actividad("heredado", estado)
            return {"ok": True, "evento": nombre, "estado": int(estado)}

        assert agente is not None
        contexto = self._contexto(peticion, agente.id, evento)

        # La luz no debe retrasar la respuesta: se actualiza en paralelo.
        self._marcar_actividad(agente.id, evento)

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
        # Lo que queda en «preguntar» puede contestarse desde el navegador, si
        # se activó. Lo que una regla deniega no llega hasta aquí: la red de
        # seguridad no se puede saltar contestando en la web.
        if veredicto.decision is Decision.PREGUNTAR and getattr(
            self.ajustes, "aprobacion_remota", False
        ):
            veredicto = await self.aprobaciones.preguntar(
                contexto, veredicto, getattr(self.ajustes, "espera_aprobacion_s", 25.0)
            )
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
        self.bus.publicar("decision", entrada)
        del self.historial[:-100]
        if veredicto.decision is not Decision.PERMITIR:
            _log.info(
                "%s · %s → %s (%s)",
                agente.nombre,
                contexto.resumen(),
                veredicto.decision.value,
                veredicto.explicacion,
            )

    # --- la barra de luz -------------------------------------------------
    def _marcar_actividad(self, agente_id: str, evento: EventoEnganche) -> None:
        """Refleja el momento del agente y decide cuánto debe durar en pantalla.

        Sin esto la barra se queda con la última animación para siempre: el
        teclado no sabe qué programa tienes delante ni cuándo se cerró, así que
        si un agente termina sin avisar -o simplemente cambias de ventana- las
        luces seguirían moviéndose como si aún estuviera trabajando.
        """
        self._anotar_actividad(agente_id, evento.estado)
        # Se lleva la cuenta pase lo que pase —quién habló y cuándo— pero la
        # barra solo la toca el programa que manda en el modo puesto. Si estás
        # en el modo de ChatGPT, lo que haga Claude Code por detrás no debe
        # encenderte la luz: enseñaría algo que no estás mirando.
        le_toca = self._le_toca_a_este_modo(agente_id)
        self._anotar_aviso(agente_id, evento.interno, evento.estado, atendido=le_toca)
        if le_toca:
            self._en_segundo_plano(self.gestor.enviar_estado_ia(evento.estado))
            # Manos libres: el agente del modo ha terminado, así que se avisa
            # a quien sepa abrir el micrófono. Se pide el mismo permiso que
            # para encender la luz —tiene que ser el dueño del modo puesto—,
            # porque abrirte el dictado sobre una ventana que no estás mirando
            # sería peor que no abrirlo.
            if evento.estado is EstadoIA.TAREA_COMPLETADA and self.al_terminar_el_dueno:
                try:
                    self.al_terminar_el_dueno(agente_id)
                except Exception:  # noqa: BLE001 - esto nunca tumba un evento
                    _log.debug("Falló el aviso de manos libres", exc_info=True)

        if self._reposo is not None:
            self._reposo.cancel()
            self._reposo = None

        if evento.estado in ESTADOS_TRANQUILOS:
            self.agente_activo = None
        elif evento.estado in ESTADOS_BREVES:
            self._reposo = asyncio.create_task(
                self._volver_al_reposo(self.ajustes.milisegundos_estado_breve / 1000)
            )

    def _anotar_actividad(self, agente_id: str, estado: EstadoIA) -> None:
        self.agente_activo = agente_id
        self.ultimo_evento_en = time.monotonic()
        # Solo se registra el cambio: un agente activo dispara muchos eventos
        # seguidos y repetirlos todos ahogaría lo que sí importa.
        if estado is not self._ultimo_estado_registrado:
            self._ultimo_estado_registrado = estado
            _log.info("%s → %s", agente_id, estado.etiqueta)

    async def _volver_al_reposo(self, espera_s: float) -> None:
        try:
            await asyncio.sleep(espera_s)
        except asyncio.CancelledError:
            return
        await self._apagar_la_barra("el momento era pasajero")

    async def _vigilar_inactividad(self) -> None:
        """Devuelve la barra al reposo cuando nadie dice nada durante un rato.

        Es la red que recoge lo que los enganches no cuentan: un agente cerrado
        de golpe, una terminal que desaparece o una sesión que acaba sin emitir
        su evento de cierre.
        """
        limite = max(5, self.ajustes.segundos_hasta_reposo)
        paso = max(0.1, min(1.0, limite / 10))
        try:
            while True:
                await asyncio.sleep(paso)
                if self.agente_activo is None or not self.ultimo_evento_en:
                    continue
                if time.monotonic() - self.ultimo_evento_en >= limite:
                    await self._apagar_la_barra(f"{limite} s sin noticias de {self.agente_activo}")
        except asyncio.CancelledError:
            return

    async def _apagar_la_barra(self, motivo: str) -> None:
        if self.agente_activo is None and self._ultimo_estado_registrado in (
            None,
            ESTADO_EN_REPOSO,
        ):
            return
        _log.info("Barra en reposo: %s", motivo)
        self.agente_activo = None
        self._ultimo_estado_registrado = ESTADO_EN_REPOSO
        await self.gestor.enviar_estado_ia(ESTADO_EN_REPOSO)

    def _le_toca_a_este_modo(self, agente_id: str) -> bool:
        """¿Manda este programa en el modo que tiene puesto el teclado?

        Cada modo tiene dueño. Si el teclado está en el modo de ChatGPT y quien
        habla es Claude Code por detrás, la barra no se toca: enseñaría algo que
        no estás mirando. Un modo sin dueño —el libre— lo mueve cualquiera, y si
        no se sabe en qué modo está el teclado, tampoco se filtra: más vale
        avisar de más que quedarse callado.
        """
        estado = self.gestor.estado
        if estado is None or estado.modo_trabajo is None:
            return True
        modos = getattr(self.ajustes, "modos", [])
        if not 0 <= estado.modo_trabajo < len(modos):
            return True
        dueno = (getattr(modos[estado.modo_trabajo], "agente", "") or "").strip().lower()
        if not dueno:
            return True
        return dueno == (agente_id or "").strip().lower()

    def le_toca_al_modo(self, agente_id: str) -> bool:
        """¿Manda este programa en el modo que tiene puesto el teclado?

        Pública porque el vigía de ChatGPT la consulta desde su hilo para saber
        si merece la pena mirar la ventana. Solo lee, así que se puede llamar
        desde donde sea.
        """
        return self._le_toca_a_este_modo(agente_id)

    # --- lo que pasa en el teclado, en vivo -------------------------------
    def avisar_de_chatgpt(self, que: str) -> None:
        """Refleja lo que hace ChatGPT, que no tiene enganches con que avisar.

        Llega desde el hilo del vigía, así que hay que cruzar al bucle de
        sucesos antes de tocar nada: ``_marcar_actividad`` crea tareas y no se
        puede llamar desde otro hilo.
        """
        estado = {
            "trabajando": EstadoIA.HERRAMIENTA_EN_CURSO,
            "terminado": EstadoIA.TAREA_COMPLETADA,
        }.get(que)
        if estado is None or self._bucle is None or self._bucle.is_closed():
            return
        evento = EventoEnganche(f"ChatGPT{que.capitalize()}", que, estado)
        self._bucle.call_soon_threadsafe(self._marcar_actividad, "chatgpt", evento)

    def avisar_de_pulsacion(self, pieza: str, detalle: dict[str, Any]) -> None:
        """Cuenta al panel que algo se ha tocado, para que lo señale.

        De las cuatro teclas solo se ve la del micrófono: las otras tres mandan
        sus pulsaciones directamente a Windows sin pasar por aquí, que es
        exactamente lo que se busca de ellas.
        """
        self.bus.publicar("pulsacion", {"pieza": pieza, **detalle})

    def _al_cambiar_el_teclado(self, _estado) -> None:
        """Cada lectura del teclado llega al panel, pero solo si cambia algo.

        Se sondea cada dos segundos; avisar de cada lectura llenaría el canal de
        mensajes idénticos y haría trabajar al navegador para nada.
        """
        resumen = self.gestor.resumen()
        interesa = {c: resumen.get(c) for c in _CAMPOS_QUE_IMPORTAN}
        if interesa == self._ultimo_resumen:
            return
        anterior = dict(self._ultimo_resumen)
        self._ultimo_resumen = interesa

        if anterior:
            if anterior.get("palanca") != interesa.get("palanca"):
                self.avisar_de_pulsacion("palanca", {"valor": interesa.get("palanca")})
            if anterior.get("modo_trabajo") != interesa.get("modo_trabajo"):
                self.avisar_de_pulsacion("modo", {"valor": interesa.get("modo_trabajo")})
        self.bus.publicar("estado", resumen)

    def _anotar_aviso(
        self, agente: str, evento: str, estado: EstadoIA, atendido: bool = True
    ) -> None:
        """Deja constancia de qué llegó y qué luz encendió."""
        from datetime import datetime

        efecto = self.gestor.efecto_de(estado)
        entrada = {
            "instante": datetime.now().astimezone().isoformat(timespec="seconds"),
            "agente": agente,
            "evento": evento,
            "estado": estado.etiqueta,
            "efecto": efecto.etiqueta if efecto is not None else "—",
            "atendido": atendido,
        }
        self.avisos.append(entrada)
        del self.avisos[:-40]
        self.bus.publicar("aviso", entrada)

    def _en_segundo_plano(self, corrutina) -> None:
        tarea = asyncio.create_task(corrutina)
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)
