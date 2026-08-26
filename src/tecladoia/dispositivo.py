"""Gestor del teclado: conexión, caché de estado y órdenes de alto nivel.

La palanca se mantiene en una caché con fecha de caducidad. Es la pieza que
hace que un enganche responda rápido: mientras la lectura sea reciente se
contesta de memoria, y solo se pregunta al teclado cuando ha caducado. El
firmware además avisa por notificación cada vez que la palanca cambia, así que
la caché se refresca sola en la práctica.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from . import protocolo, teclas
from .config import Ajustes
from .modelo import EfectoLuz, EstadoIA, Modo, EFECTO_POR_ESTADO
from .registro import obtener
from .transporte import crear as crear_transporte
from .transporte.base import ErrorTransporte, Transporte

_log = obtener("dispositivo")


class GestorTeclado:
    """Punto único de acceso al teclado."""

    def __init__(self, ajustes: Ajustes, transporte: Optional[Transporte] = None) -> None:
        self.ajustes = ajustes
        self.transporte = transporte or crear_transporte(ajustes)
        self.transporte.escuchar(self._al_recibir)
        self.estado: Optional[protocolo.EstadoDispositivo] = None
        self.estado_ia: Optional[EstadoIA] = None
        self._leido_en: float = 0.0
        self._esperas: list[asyncio.Future] = []
        self._candado = asyncio.Lock()
        self._observadores: list[Callable[[protocolo.EstadoDispositivo], None]] = []
        self.palanca_forzada: Optional[int] = None

    # --- conexión -------------------------------------------------------
    @property
    def conectado(self) -> bool:
        return self.transporte.conectado

    async def conectar(self) -> None:
        await self.transporte.conectar()
        await self.consultar_estado(espera_s=self.ajustes.espera_palanca_s)

    async def desconectar(self) -> None:
        await self.transporte.desconectar()
        self.estado = None
        self._leido_en = 0.0

    async def descripcion_transporte(self) -> str:
        return await self.transporte.descripcion()

    # --- estado ---------------------------------------------------------
    def observar(self, callback: Callable[[protocolo.EstadoDispositivo], None]) -> None:
        """Registra a quien quiera enterarse de cada lectura de estado."""
        self._observadores.append(callback)

    def _al_recibir(self, trama: bytes) -> None:
        estado = protocolo.analizar_estado(trama)
        if estado is None:
            return
        self.estado = estado
        self._leido_en = time.monotonic()
        for espera in self._esperas:
            if not espera.done():
                espera.set_result(estado)
        self._esperas.clear()
        for observador in self._observadores:
            try:
                observador(estado)
            except Exception:  # noqa: BLE001 - un observador roto no tumba la lectura
                _log.exception("Un observador de estado falló")

    @property
    def cache_vigente(self) -> bool:
        if self.estado is None:
            return False
        vigencia = max(0, self.ajustes.vigencia_cache_ms) / 1000
        return (time.monotonic() - self._leido_en) <= vigencia

    async def consultar_estado(
        self, espera_s: Optional[float] = None
    ) -> Optional[protocolo.EstadoDispositivo]:
        """Pide el estado al teclado y espera la notificación de respuesta."""
        if not self.conectado:
            return None
        espera_s = self.ajustes.espera_palanca_s if espera_s is None else espera_s
        futuro: asyncio.Future = asyncio.get_running_loop().create_future()
        self._esperas.append(futuro)
        try:
            async with self._candado:
                await self.transporte.enviar_comando(protocolo.consultar_estado())
            return await asyncio.wait_for(futuro, timeout=espera_s)
        except asyncio.TimeoutError:
            _log.warning("El teclado no contestó a la consulta de estado en %.1f s", espera_s)
            return None
        except ErrorTransporte as error:
            _log.warning("No se pudo consultar el estado: %s", error)
            return None
        finally:
            if futuro in self._esperas:
                self._esperas.remove(futuro)

    async def palanca(self, forzar_lectura: bool = False) -> Optional[int]:
        """Posición actual de la palanca, o ``None`` si no se puede saber.

        Devolver ``None`` -en vez de un valor inventado- es lo que mantiene el
        sistema a prueba de fallos: quien no sabe, pregunta a la persona.
        """
        if self.palanca_forzada is not None:
            return self.palanca_forzada
        if not forzar_lectura and self.cache_vigente and self.estado is not None:
            return self.estado.palanca
        estado = await self.consultar_estado()
        if estado is not None:
            return estado.palanca
        # Una lectura vieja sirve de pista, pero no para aprobar sola.
        return None

    # --- órdenes --------------------------------------------------------
    async def enviar_estado_ia(self, estado: EstadoIA) -> bool:
        """Refleja en la barra LED el momento en el que está el agente."""
        if not self.conectado:
            return False
        try:
            async with self._candado:
                await self.transporte.enviar_comando(protocolo.actualizar_estado(int(estado)))
                efecto = EFECTO_POR_ESTADO.get(estado)
                if efecto is not None:
                    await self.transporte.enviar_comando(protocolo.efecto_luz(int(efecto)))
        except ErrorTransporte as error:
            _log.warning("No se pudo actualizar la luz: %s", error)
            return False
        self.estado_ia = estado
        return True

    async def aplicar_efecto(self, efecto: EfectoLuz) -> bool:
        return await self._orden(protocolo.efecto_luz(int(efecto)))

    async def ajustar_brillo(self, valor: int) -> bool:
        return await self._orden(protocolo.brillo_luz(valor))

    async def cambiar_modo_trabajo(self, modo: int) -> bool:
        return await self._orden(protocolo.modo_trabajo(modo))

    async def renombrar(self, nombre: str) -> bool:
        return await self._orden(protocolo.cambiar_nombre(nombre), guardar=True)

    async def _orden(self, trama: bytes, guardar: bool = False) -> bool:
        if not self.conectado:
            return False
        try:
            async with self._candado:
                await self.transporte.enviar_comando(trama)
                if guardar:
                    await self.transporte.enviar_comando(protocolo.guardar_config())
        except ErrorTransporte as error:
            _log.warning("No se pudo enviar la orden: %s", error)
            return False
        return True

    async def programar_tecla(
        self,
        modo: int,
        indice: int,
        atajo: str = "",
        descripcion: str = "",
        macro: Optional[list[tuple[int, int]]] = None,
    ) -> bool:
        """Programa una tecla y guarda el resultado en la memoria del teclado."""
        if not self.conectado:
            return False
        tramas: list[bytes] = []
        if macro:
            tramas.append(protocolo.asignar_macro(modo, indice, macro))
        elif atajo:
            tramas.append(protocolo.asignar_atajo(modo, indice, teclas.atajo_a_codigos(atajo)))
        if descripcion:
            tramas.append(protocolo.asignar_descripcion(modo, indice, descripcion))
        if not tramas:
            return False
        tramas.append(protocolo.guardar_config())
        try:
            async with self._candado:
                for trama in tramas:
                    await self.transporte.enviar_comando(trama)
                    await asyncio.sleep(0.03)  # el firmware necesita respirar entre escrituras
        except ErrorTransporte as error:
            _log.warning("No se pudo programar la tecla: %s", error)
            return False
        return True

    async def aplicar_modo(self, indice_modo: int, modo: Modo) -> int:
        """Programa de una vez las cuatro teclas de un modo. Devuelve cuántas se escribieron."""
        escritas = 0
        for indice, tecla in enumerate(modo.teclas[: protocolo.TECLAS_POR_MODO]):
            if tecla.esta_vacia() and not tecla.descripcion:
                continue
            if await self.programar_tecla(
                indice_modo, indice, tecla.atajo, tecla.descripcion, tecla.macro
            ):
                escritas += 1
        return escritas

    # --- resumen para la interfaz ---------------------------------------
    def resumen(self) -> dict:
        estado = self.estado
        return {
            "conectado": self.conectado,
            "transporte": self.transporte.nombre_legible,
            "bateria": estado.bateria if estado else None,
            "firmware": estado.firmware if estado else None,
            "modo_trabajo": estado.modo_trabajo if estado else None,
            "palanca": self.palanca_forzada if self.palanca_forzada is not None else (
                estado.palanca if estado else None
            ),
            "palanca_forzada": self.palanca_forzada is not None,
            "cache_vigente": self.cache_vigente,
            "estado_ia": int(self.estado_ia) if self.estado_ia is not None else None,
            "estado_ia_etiqueta": self.estado_ia.etiqueta if self.estado_ia is not None else None,
        }
