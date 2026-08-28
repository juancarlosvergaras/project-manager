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

#: Cuánto se respeta un modo elegido a mano antes de volver a seguir a la
#: aplicación activa. Sin esta tregua, elegir un modo en el teclado duraba lo
#: que tardabas en mirar otra ventana.
TREGUA_DE_MODO_S = 45.0


#: Plazo para un intento completo de reconexión. Ver ``mantener_conexion``.
PLAZO_DE_RECONEXION_S = 30.0

#: En qué intentos fallidos se avisa por el registro. Se avisa del primero y
#: luego de tarde en tarde: un teclado apagado toda la noche no debe llenar el
#: registro, pero tampoco debe fallar en silencio.
AVISOS_DE_RECONEXION = (1, 5, 30, 120)


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
        #: Esperas por el acuse de un comando concreto.
        self._acuses: dict[int, list[asyncio.Future]] = {}
        #: Subida de pantalla en curso, si la hay. Mientras dura, el teclado no
        #: atiende otra cosa: escribir su memoria flash es exclusivo.
        self.subida: Optional[dict] = None
        self._cancelar_subida = asyncio.Event()
        #: El último modo que pedimos nosotros. Sirve para distinguir un cambio
        #: nuestro de uno que hizo la persona con el botón del teclado.
        self._modo_pedido: Optional[int] = None
        #: Hasta cuándo se respeta un cambio hecho a mano.
        self.tregua_de_modo_hasta: float = 0.0

    # --- conexión -------------------------------------------------------
    @property
    def conectado(self) -> bool:
        return self.transporte.conectado

    @property
    def puede_intentarse(self) -> bool:
        """¿Hay canal por el que probar, aunque no conste que esté vivo?

        El latido se gobierna con esto y **no** con ``conectado``. Si se
        gobernara con ``conectado``, en cuanto el teclado se durmiera nadie
        volvería a escribirle; y como solo una escritura acertada demuestra que
        sigue ahí, no volvería a constar vivo nunca. Ese era el círculo que
        dejaba la web diciendo «todavía no hay teclado» con el teclado delante
        y el micrófono sin saber en qué modo estaba.
        """
        return bool(getattr(self.transporte, "canal_abierto", self.transporte.conectado))

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
        # Cada trama puede ser la respuesta que alguien espera. El firmware
        # acusa recibo de las escrituras masivas y sin escuchar esos acuses no
        # hay forma de saber cuándo mandar el bloque siguiente.
        if protocolo.es_trama_valida(trama):
            for espera in self._acuses.pop(protocolo.comando_de(trama), []):
                if not espera.done():
                    espera.set_result(trama)

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
        if vigencia <= 0:
            return False  # se pidió no cachear: siempre se vuelve a preguntar
        return (time.monotonic() - self._leido_en) <= vigencia

    async def consultar_estado(
        self, espera_s: Optional[float] = None
    ) -> Optional[protocolo.EstadoDispositivo]:
        """Pide el estado al teclado y espera la notificación de respuesta.

        Se intenta siempre que haya canal, aunque no conste que el teclado esté
        vivo: esta consulta **es** la forma de averiguarlo. Si de verdad se fue,
        la escritura falla, el transporte suelta el canal y la reconexión se
        pone en marcha sola.
        """
        if not self.puede_intentarse:
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
    def apuntarse_al_acuse(self, comando: int) -> asyncio.Future:
        """Se apunta a la respuesta de un comando ANTES de mandarlo.

        El orden importa: el teclado contesta en unos cincuenta milisegundos,
        así que quien manda primero y se apunta después se pierde el acuse y ve
        fallar la subida al azar.
        """
        futuro: asyncio.Future = asyncio.get_running_loop().create_future()
        self._acuses.setdefault(comando, []).append(futuro)
        return futuro

    async def esperar_acuse(
        self, comando: int, espera_s: float = 4.0, futuro: Optional[asyncio.Future] = None
    ) -> Optional[bytes]:
        """Espera el acuse de un comando. ``None`` si no llega a tiempo."""
        futuro = futuro if futuro is not None else self.apuntarse_al_acuse(comando)
        try:
            return await asyncio.wait_for(futuro, timeout=espera_s)
        except asyncio.TimeoutError:
            return None
        finally:
            pendientes = self._acuses.get(comando, [])
            if futuro in pendientes:
                pendientes.remove(futuro)

    async def mantener_conexion(
        self,
        intervalo_s: float = 12.0,
        al_cambiar: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """Reconecta cada vez que el teclado se va, y espera si no está.

        Un teclado Bluetooth se duerme, se aleja o se queda sin batería. Sin
        esto, el servicio solo arrancaba si el teclado estaba encendido en ese
        preciso instante y se quedaba sordo en cuanto se iba.
        """
        anterior = self.conectado
        quejas = 0
        while True:
            if not self.puede_intentarse:
                try:
                    # Con plazo, siempre. Ningún paso de la pila Bluetooth de
                    # Windows trae uno propio, y con el teclado apagado se
                    # quedan esperando indefinidamente: el bucle no daba otra
                    # vuelta y el servicio se quedaba mudo hasta reiniciarlo.
                    # Apagar el teclado una vez bastaba para perderlo del todo.
                    await asyncio.wait_for(self.conectar(), PLAZO_DE_RECONEXION_S)
                    _log.info("Teclado recuperado")
                    quejas = 0
                except asyncio.TimeoutError:
                    quejas += 1
                    if quejas in AVISOS_DE_RECONEXION:
                        _log.info("El teclado no contesta; se sigue intentando")
                except ErrorTransporte as error:
                    quejas += 1
                    if quejas in AVISOS_DE_RECONEXION:
                        _log.info("El teclado sigue sin aparecer: %s", error)
                except Exception:  # noqa: BLE001 - la pila BLE lanza de todo
                    quejas += 1
                    _log.debug("Fallo al reintentar la conexión", exc_info=True)
            if self.conectado != anterior:
                anterior = self.conectado
                if al_cambiar is not None:
                    try:
                        al_cambiar(anterior)
                    except Exception:  # noqa: BLE001
                        _log.exception("Un aviso de conexión falló")
            await asyncio.sleep(intervalo_s)

    async def vigilar_estado(self, intervalo_s: Optional[float] = None) -> None:
        """Pregunta al teclado por su estado mientras esté conectado.

        Sin el sondeo, mover la palanca con la mano no se notaba hasta que un
        agente pedía permiso: el firmware avisa de algunos cambios, pero no de
        todos, y una lectura vieja no vale para decidir.
        """
        intervalo_s = intervalo_s or getattr(self.ajustes, "intervalo_sondeo_s", 2.0)
        if intervalo_s <= 0:
            return
        while True:
            await asyncio.sleep(intervalo_s)
            # A propósito no se mira ``conectado``: este sondeo es justo lo que
            # lo mantiene al día. Mirarlo sería preguntarle al enfermo si está
            # vivo antes de tomarle el pulso.
            if not self.puede_intentarse:
                continue
            try:
                await self.consultar_estado()
            except Exception:  # noqa: BLE001 - un sondeo fallido no es noticia
                _log.debug("Sondeo de estado fallido", exc_info=True)

    async def enviar_estado_ia(self, estado: EstadoIA) -> bool:
        """Refleja en la barra LED el momento en el que está el agente."""
        if not self.puede_intentarse:
            return False
        try:
            async with self._candado:
                await self.transporte.enviar_comando(protocolo.actualizar_estado(int(estado)))
                efecto = self.efecto_de(estado)
                if efecto is not None:
                    await self.transporte.enviar_comando(protocolo.efecto_luz(int(efecto)))
        except ErrorTransporte as error:
            _log.warning("No se pudo actualizar la luz: %s", error)
            return False
        self.estado_ia = estado
        return True

    def efecto_de(self, estado: EstadoIA, modo: Optional[int] = None) -> Optional[EfectoLuz]:
        """El efecto elegido para ese momento del agente.

        Manda la tabla del modo, si la tiene puesta; si no, la general. Así cada
        modo puede reaccionar a su manera sin obligar a configurarlos todos.
        """
        clave = str(int(estado))
        if modo is None:
            estado_teclado = self.estado
            modo = estado_teclado.modo_trabajo if estado_teclado else None
        propias: dict = {}
        if modo is not None and 0 <= modo < len(getattr(self.ajustes, "modos", [])):
            propias = getattr(self.ajustes.modos[modo], "luces", {}) or {}
        crudo = propias.get(clave)
        if crudo is None:
            crudo = getattr(self.ajustes, "luces_por_estado", {}).get(clave)
        if crudo is None:
            return EFECTO_POR_ESTADO.get(estado)
        try:
            return EfectoLuz(int(crudo))
        except ValueError:
            return EFECTO_POR_ESTADO.get(estado)

    async def guardar_luces_de_ia(self, modo: Optional[int] = None) -> bool:
        """Deja la tabla de efectos por estado en la memoria del teclado."""
        codigos = [int(self.efecto_de(e) or 0) for e in sorted(EstadoIA, key=int)]
        modos = range(protocolo.MODOS_DISPONIBLES) if modo is None else [modo]
        for indice in modos:
            if not await self._orden(protocolo.config_luz_ia(indice, codigos)):
                return False
        return await self._orden(protocolo.guardar_config())

    async def aplicar_efecto(self, efecto: EfectoLuz) -> bool:
        return await self._orden(protocolo.efecto_luz(int(efecto)))

    async def ajustar_brillo(self, valor: int) -> bool:
        return await self._orden(protocolo.brillo_luz(valor))

    async def cambiar_modo_trabajo(self, modo: int) -> bool:
        # Se anota siempre: si el modo salta solo, aquí queda quién lo movió.
        _log.info("Se pide al teclado el modo %s", modo + 1)
        hecho = await self._orden(protocolo.modo_trabajo(modo))
        if hecho:
            self._modo_pedido = modo
        return hecho

    def modo_cambiado_a_mano(self) -> bool:
        """¿El modo que tiene el teclado lo puso la persona, no nosotros?

        Si el aparato está en un modo que no pedimos, lo cambió alguien con el
        botón. Eso vale más que cualquier automatismo: quien acaba de elegir un
        modo con la mano no quiere que se lo cambien dos segundos después.
        """
        if self.estado is None or self.estado.modo_trabajo is None:
            return False
        if self._modo_pedido is None:
            self._modo_pedido = self.estado.modo_trabajo
            return False
        if self.estado.modo_trabajo != self._modo_pedido:
            self._modo_pedido = self.estado.modo_trabajo
            self.tregua_de_modo_hasta = time.monotonic() + TREGUA_DE_MODO_S
            _log.info(
                "Modo cambiado a mano (%s): no se toca en %s s",
                self.estado.modo_trabajo + 1, int(TREGUA_DE_MODO_S),
            )
            return True
        return False

    def hay_tregua_de_modo(self) -> bool:
        self.modo_cambiado_a_mano()
        return time.monotonic() < self.tregua_de_modo_hasta

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

    # --- pantalla del teclado -------------------------------------------
    async def enviar_imagen(
        self,
        modo: int,
        cuadros: list[bytes],
        retardo_ms: int = 100,
        indice_inicial: Optional[int] = None,
        al_avanzar=None,
    ) -> dict:
        """Escribe una imagen o un GIF en la pantalla del teclado.

        El reparto de la memoria no es libre: las diez primeras ranuras son de
        fábrica y a partir de ahí cada modo tiene su tramo. Así, cambiar la
        pantalla de un modo no se lleva por delante la de los otros.

        Cada bloque se anuncia, se espera su acuse, se mandan los bytes en
        paquetes y se espera el acuse de la escritura. Ir a ciegas con pausas
        fijas parece funcionar y luego deja fotogramas a medias: el firmware
        borra un sector antes de aceptar el siguiente y eso tarda lo que tarda.
        """
        if not self.conectado:
            raise ErrorTransporte("El teclado no está conectado")
        if not cuadros:
            raise ValueError("No hay ningún fotograma que enviar")
        if self.subida is not None:
            raise ValueError(
                f"Ya se está enviando una imagen al modo {self.subida['modo'] + 1} "
                f"({self.subida['hecho']} de {self.subida['total']}). Espera o cancélala."
            )

        if indice_inicial is None:
            indice_inicial = protocolo.ranura_inicial(modo)
        if len(cuadros) > protocolo.RANURAS_POR_MODO:
            raise ValueError(
                f"Este modo admite {protocolo.RANURAS_POR_MODO} fotogramas y "
                f"llegaron {len(cuadros)}."
            )

        self._cancelar_subida.clear()
        self.subida = {"modo": modo, "hecho": 0, "total": len(cuadros)}
        limite = time.monotonic() + max(120.0, 12.0 * len(cuadros))
        try:
            await self._escribir_cuadros(
                modo, cuadros, indice_inicial, retardo_ms, limite, al_avanzar
            )
        finally:
            self.subida = None

        _log.info(
            "Pantalla del modo %s actualizada: %s fotogramas desde la ranura %s",
            modo, len(cuadros), indice_inicial,
        )
        return {
            "fotogramas": len(cuadros),
            "indice_inicial": indice_inicial,
            "retardo_ms": max(1, int(retardo_ms)),
        }

    def cancelar_subida(self) -> bool:
        """Corta la subida en curso. Cierto si había alguna."""
        if self.subida is None:
            return False
        self._cancelar_subida.set()
        return True

    async def _escribir_cuadros(
        self,
        modo: int,
        cuadros: list[bytes],
        indice_inicial: int,
        retardo_ms: int,
        limite: float,
        al_avanzar=None,
    ) -> None:
        from .imagen import bloques

        async with self._candado:
            for numero, cuadro in enumerate(cuadros):
                if self._cancelar_subida.is_set():
                    raise ErrorTransporte(
                        f"Subida cancelada tras {numero} de {len(cuadros)} fotogramas."
                    )
                if time.monotonic() > limite:
                    raise ErrorTransporte(
                        f"La subida se pasó de tiempo en el fotograma {numero + 1}. "
                        "Se corta para no dejar el teclado ocupado indefinidamente."
                    )
                base = (indice_inicial + numero) * protocolo.OLED_TAMANO_RANURA
                for salto, bloque in enumerate(bloques(cuadro)):
                    direccion = base + salto * 4096

                    aviso = self.apuntarse_al_acuse(protocolo.Comando.PREPARAR_ESCRITURA)
                    await self.transporte.enviar_comando(
                        protocolo.preparar_escritura(len(bloque), direccion)
                    )
                    if await self.esperar_acuse(
                        protocolo.Comando.PREPARAR_ESCRITURA, 6.0, aviso
                    ) is None:
                        raise ErrorTransporte(
                            f"El teclado no acusó la preparación del bloque en {direccion}."
                        )

                    hecho = self.apuntarse_al_acuse(protocolo.Comando.RESULTADO_ESCRITURA)
                    for trozo in range(0, len(bloque), protocolo.OLED_TAMANO_PAQUETE):
                        await self.transporte.enviar_datos(
                            bloque[trozo:trozo + protocolo.OLED_TAMANO_PAQUETE]
                        )
                    if await self.esperar_acuse(
                        protocolo.Comando.RESULTADO_ESCRITURA, 10.0, hecho
                    ) is None:
                        raise ErrorTransporte(
                            f"El teclado no confirmó la escritura del bloque en {direccion}."
                        )

                self.subida["hecho"] = numero + 1
                if al_avanzar is not None:
                    al_avanzar(numero + 1, len(cuadros))

            await self.transporte.enviar_comando(
                protocolo.actualizar_imagen(
                    modo, indice_inicial, len(cuadros), max(1, int(retardo_ms))
                )
            )
            await asyncio.sleep(0.1)
            await self.transporte.enviar_comando(protocolo.guardar_config())

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
            "subida": self.subida,
            "estado_ia": int(self.estado_ia) if self.estado_ia is not None else None,
            "estado_ia_etiqueta": self.estado_ia.etiqueta if self.estado_ia is not None else None,
        }
