"""Transporte para Windows a través del teclado ya emparejado.

Es el que resuelve el caso normal en Windows, y hace falta por una razón
concreta: el AhaKey se empareja como teclado, y en cuanto el sistema lo toma
**deja de anunciarse**. A partir de ahí ningún rastreo lo encuentra, y su
dirección tampoco vale de nada porque además va rotando —es un dispositivo con
privacidad, cambia de dirección cada tantos minutos—. Con eso, la vía habitual
de ``bleak``, que es rastrear y conectar a lo que aparezca, se queda sin
teclado justo cuando el teclado está delante y funcionando.

Windows sí sabe llegar: guarda los dispositivos emparejados y permite abrirles
el GATT sin verlos anunciarse. Es exactamente lo que hace el puente del
fabricante. Aquí se usa la misma puerta, sin intermediarios: se busca entre los
emparejados el que se llame AhaKey, se le abre el servicio ``0x7340`` y se
escriben y leen sus características.

Solo existe en Windows. En macOS y en Linux el camino bueno sigue siendo
``bleak``, donde este problema no se da.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

from .. import protocolo
from ..registro import obtener
from .base import ErrorTransporte, Transporte

_log = obtener("windows")

#: Cuánto vale la última conversación con el teclado antes de fiarse de lo que
#: diga Windows. Un teclado que contestó hace diez segundos sigue estando ahí.
VIGENCIA_DEL_CONTACTO_S = 45.0

#: Escrituras fallidas seguidas que hacen soltar el canal y reabrirlo.
FALLOS_PARA_SOLTAR = 2

#: Plazos de reconexión. WinRT no trae ninguno y con el teclado apagado se
#: queda esperando indefinidamente, colgando el bucle que debía reintentarlo.
PLAZO_DE_BUSQUEDA_S = 10.0
PLAZO_DE_APERTURA_S = 12.0

#: Nombres con los que el teclado aparece en la lista de emparejados.
NOMBRES_CONOCIDOS = ("ahakey", "vibecoding", "x1")


def hay_winrt() -> bool:
    """¿Estamos en Windows y con la proyección de sus API disponible?"""
    if os.name != "nt":
        return False
    try:
        import winrt.windows.devices.bluetooth  # noqa: F401
        import winrt.windows.devices.enumeration  # noqa: F401
        import winrt.windows.storage.streams  # noqa: F401
    except ImportError:
        return False
    return True


def _cerrar(objeto: Any) -> None:
    """Cierra un objeto de WinRT sin hacer ruido si ya no está.

    Los objetos GATT de Windows toman el acceso en exclusiva mientras viven, y
    abandonarlos sin cerrar deja al propio proceso incapaz de volver a abrir el
    aparato. No se puede confiar en que el recolector de basura lo haga a
    tiempo, porque «a tiempo» aquí significa antes del siguiente intento.
    """
    if objeto is None:
        return
    try:
        objeto.close()
    except Exception:  # noqa: BLE001 - si ya estaba cerrado, mejor
        pass


class TransporteWindowsEmparejado(Transporte):
    """Habla con el teclado que Windows ya tiene emparejado."""

    nombre_legible = "Bluetooth de Windows"

    def __init__(self, nombre: str = "") -> None:
        super().__init__()
        self.nombre = nombre
        self._dispositivo: Any = None
        self._comando: Any = None
        self._datos: Any = None
        self._notifica: Any = None
        self._testigo: Any = None
        self._memoria = bytearray()
        self._bucle: Optional[asyncio.AbstractEventLoop] = None
        self._descripcion = ""
        #: Cuándo se habló con el teclado por última vez, de verdad.
        self._ultimo_contacto: float = 0.0
        #: Escrituras fallidas seguidas; a partir de un tope se suelta el canal.
        self._fallos: int = 0
        #: Identificador del emparejamiento que funcionó la última vez.
        self._ultimo_bueno: str = ""
        #: El servicio GATT abierto. Se guarda para poder cerrarlo: mientras
        #: viva, tiene el teclado tomado en exclusiva.
        self._servicio: Any = None
        #: Aparato de un intento en curso, para cerrarlo si el intento falla.
        self._a_medias: Any = None

    # --- estado -----------------------------------------------------------
    @property
    def conectado(self) -> bool:
        """¿Se puede hablar con el teclado ahora mismo?

        No basta con preguntárselo a Windows. Un teclado Bluetooth de bajo
        consumo se duerme entre pulsación y pulsación, y mientras duerme el
        sistema lo da por **desconectado** aunque siga emparejado y despierte al
        primer intento de escribirle. Creerse esa respuesta tenía dos efectos
        feos: la web decía «todavía no hay teclado» con el teclado delante y
        contestando, y la barra de luz se quedaba congelada, porque las órdenes
        ni se intentaban.

        Así que también cuenta la experiencia: si hace poco que hablamos con él,
        está ahí. Cuando de verdad se va, deja de contestar y el plazo vence.
        """
        return self.canal_abierto and (
            time.monotonic() - self._ultimo_contacto < VIGENCIA_DEL_CONTACTO_S
        )

    @property
    def canal_abierto(self) -> bool:
        """¿Tenemos un canal por el que merezca la pena intentarlo?

        Distinto de ``conectado``, y la diferencia es el arreglo del círculo
        vicioso que dejaba la web diciendo «todavía no hay teclado» con el
        teclado encendido delante:

        * ``conectado`` responde «¿está vivo?» y se contesta con hechos: hemos
          hablado con él hace poco. Es lo que se le enseña a la persona.
        * ``canal_abierto`` responde «¿tiene sentido intentarlo?». Con esto se
          gobierna el latido, **que no pide permiso a ``conectado``**.

        Antes el latido sí lo pedía, y ahí estaba la trampa: el contacto solo se
        refresca escribiendo, así que en cuanto ``conectado`` se ponía en falso
        nadie volvía a escribir, y por tanto nunca volvía a ser cierto. Un
        teclado dormido se quedaba muerto hasta reiniciar el servicio.
        """
        return self._dispositivo is not None and self._comando is not None

    # --- búsqueda ---------------------------------------------------------
    async def buscar(self) -> list[tuple[str, str]]:
        """Los teclados AhaKey emparejados con este equipo."""
        if not hay_winrt():
            raise ErrorTransporte("Esta vía solo existe en Windows.")
        from winrt.windows.devices.bluetooth import BluetoothLEDevice
        from winrt.windows.devices.enumeration import DeviceInformation

        selector = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
        emparejados = await DeviceInformation.find_all_async_aqs_filter(selector)

        encontrados: list[tuple[str, str]] = []
        for info in emparejados:
            etiqueta = (info.name or "").lower()
            if self.nombre:
                if self.nombre.lower() not in etiqueta:
                    continue
            elif not any(clave in etiqueta for clave in NOMBRES_CONOCIDOS):
                continue
            encontrados.append((info.id, info.name or ""))
        return encontrados

    # --- conexión ---------------------------------------------------------
    async def conectar(self) -> None:
        """Abre el teclado, con plazo.

        **Ningún paso de WinRT tiene plazo propio**, y con el teclado apagado
        `from_id_async` o la lectura de servicios se quedan esperando para
        siempre. Eso fue lo que dejó el servicio mudo una tarde entera: al
        apagar el teclado se soltó el canal —correcto— y el intento de
        reabrirlo se colgó dentro de WinRT, así que el bucle de reconexión no
        volvió a dar una vuelta nunca más. Sin este plazo, apagar el teclado
        una vez obliga a reiniciar el servicio.
        """
        if not hay_winrt():
            raise ErrorTransporte("Esta vía solo existe en Windows.")

        try:
            candidatos = await asyncio.wait_for(self.buscar(), PLAZO_DE_BUSQUEDA_S)
        except asyncio.TimeoutError as error:
            raise ErrorTransporte(
                "Windows tardó demasiado en listar los teclados emparejados"
            ) from error
        if not candidatos:
            raise ErrorTransporte(
                "Windows no tiene ningún teclado AhaKey emparejado. Empareja el "
                "teclado en Configuración › Bluetooth y vuelve a intentarlo."
            )

        self._bucle = asyncio.get_running_loop()
        motivos: list[str] = []
        # El que funcionó la última vez, primero. Cada emparejamiento deja su
        # entrada y las viejas no se borran solas: este equipo tiene dos, y la
        # muerta se comía el plazo antes de que llegara el turno de la buena.
        if self._ultimo_bueno:
            candidatos.sort(key=lambda c: c[0] != self._ultimo_bueno)
        # Puede haber varias entradas del mismo teclado, porque cada
        # emparejamiento deja la suya; solo una está viva. Se prueban todas y
        # se deja la que conteste.
        for identificador, nombre in candidatos:
            try:
                await asyncio.wait_for(self._abrir(identificador, nombre), PLAZO_DE_APERTURA_S)
                self._ultimo_bueno = identificador
                return
            except asyncio.TimeoutError:
                motivos.append(f"{nombre or identificador}: no contestó a tiempo")
            except ErrorTransporte as error:
                motivos.append(f"{nombre or identificador}: {error}")
        raise ErrorTransporte("No se pudo abrir el teclado. " + " · ".join(motivos))

    async def _abrir(self, identificador: str, nombre: str) -> None:
        """Abre el teclado, y si no puede **no deja nada abierto detrás**.

        Esto ultimo es la mitad del trabajo. Cada objeto GATT de Windows toma
        el acceso en exclusiva mientras vive, asi que un intento fallido que
        abandona el aparato sin cerrarlo deja un candado puesto. Reintentando
        cada quince segundos, los candados se acumulan hasta que ni un proceso
        recien arrancado consigue entrar, y Windows lo cuenta como un servicio
        sin caracteristicas —que desde fuera parece un teclado dormido—.

        Ese era el fallo que obligaba a reiniciar el servicio para recuperar el
        teclado, y el que hacia que el sintoma empeorase solo con el tiempo.
        """
        try:
            await self._intentar_abrir(identificador, nombre)
        except BaseException:
            # Lo abierto a medias se cierra aqui, pase lo que pase.
            _cerrar(self._servicio)
            self._servicio = None
            if self._dispositivo is None:
                _cerrar(getattr(self, "_a_medias", None))
            self._a_medias = None
            raise

    async def _intentar_abrir(self, identificador: str, nombre: str) -> None:
        from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothLEDevice
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattClientCharacteristicConfigurationDescriptorValue as Aviso,
        )

        dispositivo = await BluetoothLEDevice.from_id_async(identificador)
        if dispositivo is None:
            raise ErrorTransporte("Windows no pudo abrirlo")
        # Se anota mientras el intento esta en el aire, para poder cerrarlo si
        # algo falla antes de que llegue a ser el aparato bueno.
        self._a_medias = dispositivo

        servicios = await self._servicios(dispositivo, BluetoothCacheMode.UNCACHED)
        servicio = next(
            (s for s in servicios if str(s.uuid).lower() == protocolo.SERVICIO_PRINCIPAL),
            None,
        )
        # **Los servicios que no se usan se cierran, y esto no es cortesía.**
        #
        # Cada `GattDeviceService` que Windows entrega toma el acceso en
        # exclusiva mientras viva. Si se abandonan sin cerrar, el propio
        # proceso se queda bloqueado a sí mismo: el siguiente intento de
        # abrir el teclado recibe «acceso denegado» y Windows lo cuenta como
        # un servicio sin características, que desde fuera parece un teclado
        # dormido o averiado.
        #
        # Ese era el fallo que hacía imposible reconectar sin reiniciar el
        # servicio, y despistaba porque desde un proceso limpio todo iba bien.
        for otro in servicios:
            if otro is not servicio:
                _cerrar(otro)
        if servicio is None:
            raise ErrorTransporte("no expone el servicio de configuración")

        caracteristicas = await self._caracteristicas(servicio, BluetoothCacheMode.UNCACHED)
        por_uuid = {str(c.uuid).lower(): c for c in caracteristicas}
        comando = por_uuid.get(protocolo.CARACTERISTICA_COMANDO)
        notifica = por_uuid.get(protocolo.CARACTERISTICA_NOTIFICA)
        if comando is None or notifica is None:
            # Windows lo ve y contesta, pero no enseña los canales de
            # configuración. Es el teclado dormido: sigue emparejado y
            # encendido —por eso la barra sigue con su último color— pero su
            # parte de configuración no despierta hasta que se le toca.
            # Decirlo asi importa: el mensaje generico manda a encender un
            # teclado que ya esta encendido, y uno se queda mirandolo.
            _cerrar(servicio)
            raise ErrorTransporte(
                "no expone sus canales de configuración (acceso denegado o dormido)"
            )

        estado = await notifica.write_client_characteristic_configuration_descriptor_async(
            Aviso.NOTIFY
        )
        if int(estado) != 0:
            raise ErrorTransporte(f"no aceptó las notificaciones (estado {int(estado)})")

        self._testigo = notifica.add_value_changed(self._al_notificar)
        self._servicio = servicio
        self._dispositivo = dispositivo
        self._a_medias = None
        self._comando = comando
        self._datos = por_uuid.get(protocolo.CARACTERISTICA_DATOS)
        self._notifica = notifica
        self._descripcion = nombre or identificador
        self._ultimo_contacto = time.monotonic()
        _log.info("Teclado «%s» abierto por el Bluetooth de Windows", self._descripcion)

    @staticmethod
    async def _servicios(dispositivo: Any, modo: Any) -> list[Any]:
        try:
            resultado = await dispositivo.get_gatt_services_with_cache_mode_async(modo)
        except TypeError:
            resultado = await dispositivo.get_gatt_services_async()
        return list(resultado.services)

    @staticmethod
    async def _caracteristicas(servicio: Any, modo: Any) -> list[Any]:
        try:
            resultado = await servicio.get_characteristics_with_cache_mode_async(modo)
        except TypeError:
            resultado = await servicio.get_characteristics_async()
        return list(resultado.characteristics)

    async def desconectar(self) -> None:
        # Un solo camino para soltar el teclado. Antes había dos y solo uno
        # cerraba el aparato; el que no lo cerraba era justo el que se usa
        # cuando deja de responder, o sea el que más falta hacía que lo hiciera.
        self._soltar_el_canal()
        self._memoria.clear()

    # --- notificaciones ---------------------------------------------------
    def _al_notificar(self, _remitente: Any, argumentos: Any) -> None:
        """Windows avisa desde otro hilo; hay que volver al bucle de asyncio."""
        try:
            from winrt.windows.storage.streams import DataReader

            crudo = argumentos.characteristic_value
            lector = DataReader.from_buffer(crudo)
            # Ojo con la firma: aquí read_bytes RELLENA un búfer que se le pasa,
            # no devuelve uno del tamaño que le pidas. Con la firma equivocada
            # lanza TypeError y la notificación se perdía sin dejar rastro.
            hueco = bytearray(crudo.length)
            lector.read_bytes(hueco)
            datos = bytes(hueco)
        except Exception:  # noqa: BLE001 - una notificación rota no tumba nada
            _log.warning("No se pudo leer una notificación del teclado", exc_info=True)
            return
        if self._bucle is None or self._bucle.is_closed():
            return
        self._ultimo_contacto = time.monotonic()
        self._bucle.call_soon_threadsafe(self._procesar, datos)

    def _procesar(self, datos: bytes) -> None:
        self._memoria.extend(datos)
        for trama in protocolo.separar_tramas(self._memoria):
            self._entregar(trama)

    # --- escritura --------------------------------------------------------
    async def enviar_comando(self, trama: bytes) -> None:
        await self._escribir(self._comando, trama, "comando")

    async def enviar_datos(self, bloque: bytes) -> None:
        await self._escribir(self._datos, bloque, "datos")

    async def _escribir(self, caracteristica: Any, carga: bytes, que: str) -> None:
        if caracteristica is None:
            raise ErrorTransporte(f"El teclado no está conectado (canal de {que})")
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattWriteOption
        from winrt.windows.storage.streams import DataWriter

        escritor = DataWriter()
        escritor.write_bytes(bytes(carga))
        # Cada característica dice cómo quiere que le escriban. La de comandos
        # de este teclado solo admite escritura CON respuesta; mandarle una sin
        # respuesta no da error, simplemente no llega y el teclado nunca contesta.
        opcion = (
            GattWriteOption.WRITE_WITHOUT_RESPONSE
            if int(caracteristica.characteristic_properties) & 0x04
            else GattWriteOption.WRITE_WITH_RESPONSE
        )
        try:
            estado = await caracteristica.write_value_with_option_async(
                escritor.detach_buffer(), opcion
            )
        except Exception as error:  # noqa: BLE001 - WinRT lanza sus propias excepciones
            self._fallo_de_escritura()
            raise ErrorTransporte(f"Fallo al escribir en el teclado: {error}") from error
        if int(estado) != 0:
            self._fallo_de_escritura()
            raise ErrorTransporte(f"El teclado rechazó la escritura (estado {int(estado)})")
        self._ultimo_contacto = time.monotonic()
        self._fallos = 0

    def _fallo_de_escritura(self) -> None:
        """Tira el canal cuando el teclado deja de contestar de verdad.

        Una escritura suelta puede fallar porque el teclado estaba despertando,
        así que no se tira a la primera: eso provocaría reconexiones constantes.
        A la segunda seguida se suelta el canal, y entonces ``mantener_conexion``
        lo vuelve a abrir por su cuenta. Es lo que devuelve el teclado a la vida
        sin tener que reiniciar el servicio.
        """
        self._fallos += 1
        if self._fallos < FALLOS_PARA_SOLTAR:
            return
        _log.info("El teclado dejó de responder; se suelta para volver a abrirlo")
        self._soltar_el_canal()

    def _soltar_el_canal(self) -> None:
        """Suelta el teclado del todo, **cerrándolo**.

        Lo de cerrarlo no es una cortesía: es la diferencia entre poder volver
        a abrirlo o no. Un ``BluetoothLEDevice`` que se abandona sin
        ``close()`` deja la sesión viva dentro de este proceso, y Windows no
        deja abrir una segunda sobre el mismo aparato. Desde fuera se veía como
        un teclado embrujado — un proceso recién arrancado lo abría a la
        primera y el servicio, con el aparato encendido delante, no lo
        conseguía ni en veinte minutos de reintentos.

        Esa era la última pieza de «apagar el teclado obliga a reiniciar el
        servicio»: no se reconectaba porque nunca se había soltado de verdad.
        """
        if self._notifica is not None and self._testigo is not None:
            try:
                self._notifica.remove_value_changed(self._testigo)
            except Exception:  # noqa: BLE001 - ya podía estar suelto
                pass
        # El servicio antes que el aparato: es el que tiene el acceso en
        # exclusiva, y dejarlo abierto bloquea al siguiente intento.
        _cerrar(self._servicio)
        _cerrar(self._dispositivo)
        self._servicio = None
        self._testigo = None
        self._notifica = None
        self._comando = None
        self._datos = None
        self._dispositivo = None
        self._ultimo_contacto = 0.0
        self._fallos = 0

    async def descripcion(self) -> str:
        if self._descripcion:
            return f"Bluetooth de Windows ({self._descripcion})"
        return self.nombre_legible


async def buscar_emparejados(nombre: str = "") -> list[tuple[str, str]]:
    """Atajo para la interfaz: los AhaKey que Windows tiene emparejados."""
    return await TransporteWindowsEmparejado(nombre).buscar()


__all__ = ["TransporteWindowsEmparejado", "hay_winrt", "buscar_emparejados"]
