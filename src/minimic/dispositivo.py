"""El teclado de voz visto desde Windows: por dónde está conectado y cómo se le habla.

Se presenta como dos aparatos USB distintos según el camino:

- **por cable**, ``514C:8850``: teclado, ratón, control de consumo, micrófono
  y, además, la interfaz de fabricante (página de uso 0xFF00) por la que se
  configura. **Solo por aquí se puede leer o escribir el mapa de teclas.**
- **por el receptor de 2,4 GHz**, ``4C4A:4155``: lo mismo sin la interfaz de
  configuración. Las teclas y el micrófono funcionan; configurar, no.

Por Bluetooth aparece como «MINI_KEYBOARD», con teclas pero sin micrófono
que Windows entienda, así que la aplicación no lo usa.

El micrófono viaja con el teclado: cada aparato USB expone un «Micrófono
(USBAudio1.0)». Para saber cuál de los micrófonos del sistema es el del
teclado no vale el nombre —lo comparte con cualquier chip Jieli—, sino el
**identificador de contenedor**, que Windows asigna igual al aparato USB y a
sus puntos de audio. El del USB está en el registro; el del audio, en las
propiedades del punto.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from . import protocolo
from .protocolo import Atajo

registro = logging.getLogger("minimic.dispositivo")

VID_CABLE, PID_CABLE = 0x514C, 0x8850
VID_RECEPTOR, PID_RECEPTOR = 0x4C4A, 0x4155
PAGINA_DE_FABRICANTE = 0xFF00

PLAZO_DE_RESPUESTA_S = 0.6
PLAZO_ENTRE_INFORMES_S = 0.25


class ErrorDispositivo(RuntimeError):
    """El teclado no está, no contesta o rechazó lo que se le pidió."""


# --- presencia ----------------------------------------------------------------

@dataclass(frozen=True)
class Presencia:
    cable: bool = False
    receptor: bool = False
    ruta_configuracion: bytes | None = None

    @property
    def conectado(self) -> bool:
        return self.cable or self.receptor

    @property
    def configurable(self) -> bool:
        return self.ruta_configuracion is not None

    @property
    def descripcion(self) -> str:
        if self.cable and self.receptor:
            return "por cable y por el receptor de 2,4 GHz"
        if self.cable:
            return "por cable"
        if self.receptor:
            return "por el receptor de 2,4 GHz (solo se configura por cable)"
        return "no está"


def _hid() -> Any:
    try:
        import hid  # hidapi
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise ErrorDispositivo("falta el paquete «hidapi» (pip install hidapi)") from e
    return hid


def presencia() -> Presencia:
    """Qué hay enchufado ahora mismo, según la lista HID de Windows."""
    try:
        aparatos = _hid().enumerate()
    except ErrorDispositivo:
        raise
    except Exception as e:  # noqa: BLE001 - hidapi da errores variopintos
        raise ErrorDispositivo(f"no se pudo enumerar los aparatos HID: {e}") from e
    cable = receptor = False
    ruta = None
    for a in aparatos:
        par = (a["vendor_id"], a["product_id"])
        if par == (VID_CABLE, PID_CABLE):
            cable = True
            if a["usage_page"] == PAGINA_DE_FABRICANTE:
                ruta = a["path"]
        elif par == (VID_RECEPTOR, PID_RECEPTOR):
            receptor = True
    return Presencia(cable, receptor, ruta)


# --- el canal de configuración -------------------------------------------------

class CanalHID:
    """Un informe de 64 bytes de ida y los que vengan de vuelta. Envuelve hidapi."""

    def __init__(self, ruta: bytes) -> None:
        self._h = _hid().device()
        self._h.open_path(ruta)

    def escribir(self, datos: bytes) -> None:
        if self._h.write(datos) != len(datos):
            raise ErrorDispositivo("el teclado no aceptó el informe completo")

    def leer(self, plazo_s: float) -> bytes | None:
        r = self._h.read(protocolo.TAMANO, timeout_ms=int(plazo_s * 1000))
        return bytes(r) if r else None

    def cerrar(self) -> None:
        try:
            self._h.close()
        except Exception:  # noqa: BLE001
            pass


@dataclass
class Mapa:
    """Una capa entera: qué hace cada tecla, contadas desde 0."""

    capa: int
    teclas: dict[int, Atajo] = field(default_factory=dict)

    def como_texto(self) -> dict[int, str]:
        return {t: str(a) for t, a in sorted(self.teclas.items())}


class Teclado:
    """Habla con el teclado por el cable. Una llamada, una conversación; el canal se
    cierra al terminar para no dejar el aparato tomado (el programa del fabricante
    lo abre a la vez y conviven porque hidapi abre en modo compartido)."""

    def __init__(self, abrir_canal: Callable[[], Any] | None = None) -> None:
        self._abrir = abrir_canal or self._abrir_por_cable
        self._cerrojo = threading.Lock()

    @staticmethod
    def _abrir_por_cable() -> CanalHID:
        p = presencia()
        if not p.configurable:
            raise ErrorDispositivo(
                "el teclado no está por cable: "
                + ("solo por el receptor, y por ahí no se configura" if p.receptor else "conéctalo por USB")
            )
        return CanalHID(p.ruta_configuracion)  # type: ignore[arg-type]

    # -- conversación básica --

    def _conversar(self, paquete: bytes) -> list[protocolo.Respuesta]:
        with self._cerrojo:
            canal = self._abrir()
            try:
                canal.escribir(paquete)
                respuestas: list[protocolo.Respuesta] = []
                plazo = PLAZO_DE_RESPUESTA_S
                while True:
                    crudo = canal.leer(plazo)
                    if crudo is None:
                        break
                    try:
                        r = protocolo.analizar(crudo)
                    except protocolo.ErrorProtocolo as e:
                        registro.warning("informe raro del teclado: %s", e)
                        continue
                    respuestas.append(r)
                    if r.es_acuse or r.es_rechazo:
                        break
                    plazo = PLAZO_ENTRE_INFORMES_S
                return respuestas
            finally:
                canal.cerrar()

    def _exigir_acuse(self, paquete: bytes, que: str) -> list[protocolo.Respuesta]:
        respuestas = self._conversar(paquete)
        if not respuestas:
            raise ErrorDispositivo(f"el teclado no contestó al {que}")
        if respuestas[-1].es_rechazo:
            raise ErrorDispositivo(f"el teclado rechazó el {que}: {respuestas[-1].carga.hex(' ')}")
        return respuestas

    # -- lo que se le puede pedir --

    def informacion(self) -> protocolo.Informacion:
        r = self._conversar(protocolo.informacion())
        if not r or r[0].orden != protocolo.ORDEN_INFORMACION:
            raise ErrorDispositivo("el teclado no dio su información")
        return protocolo.Informacion(r[0].carga)

    def ajustes(self) -> protocolo.Ajustes:
        r = self._conversar(protocolo.leer_ajustes())
        if not r or r[0].orden != protocolo.ORDEN_LEER_AJUSTES:
            raise ErrorDispositivo("el teclado no dio sus ajustes")
        return protocolo.Ajustes.desde_carga(r[0].carga)

    def leer_capa(self, capa: int = 0) -> Mapa:
        mapa = Mapa(capa)
        for r in self._exigir_acuse(protocolo.leer_capa(capa), "leer la capa"):
            if r.orden == protocolo.ORDEN_REGISTRO_DE_TECLA:
                try:
                    mapa.teclas[r.arg] = Atajo.desde_registro(r.carga)
                except protocolo.ErrorProtocolo as e:
                    registro.warning("tecla %d de la capa %d ilegible: %s", r.arg + 1, capa + 1, e)
        if len(mapa.teclas) < protocolo.NUMERO_DE_TECLAS:
            raise ErrorDispositivo(f"la capa {capa + 1} vino incompleta: {sorted(mapa.teclas)}")
        return mapa

    def escribir_tecla(self, capa: int, tecla: int, atajo: Atajo) -> None:
        self._exigir_acuse(protocolo.escribir_tecla(capa, tecla, atajo.a_registro()), f"cambio de la tecla {tecla + 1}")

    def modo_microfono(self, modo: int) -> None:
        self._exigir_acuse(protocolo.escribir_ajustes(modo), "cambio del modo del micrófono")


# --- el micrófono del teclado como micrófono del sistema ----------------------

def contenedores_del_teclado() -> set[str]:
    """Identificadores de contenedor de cada aparato USB del teclado, del registro.

    No hace falta que estén enchufados: Windows recuerda los que ha visto. Se
    devuelven en mayúsculas y con llaves, que es como los da MMDevice.
    """
    import winreg

    contenedores: set[str] = set()
    for vid, pid in ((VID_CABLE, PID_CABLE), (VID_RECEPTOR, PID_RECEPTOR)):
        ruta = rf"SYSTEM\CurrentControlSet\Enum\USB\VID_{vid:04X}&PID_{pid:04X}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
                for i in range(winreg.QueryInfoKey(clave)[0]):
                    serie = winreg.EnumKey(clave, i)
                    try:
                        with winreg.OpenKey(clave, serie) as sub:
                            valor, _ = winreg.QueryValueEx(sub, "ContainerID")
                            contenedores.add(str(valor).upper())
                    except OSError:
                        continue
        except OSError:
            continue
    return contenedores


def _guid_de(propvariant: Any) -> str:
    """Saca el GUID de un PROPVARIANT de tipo VT_CLSID (72).

    ``pycaw`` declara ``puuid`` como un GUID por valor, pero en el PROPVARIANT
    de verdad es un **puntero** a GUID: leerlo como valor da basura y
    ``GetValue()`` devuelve None. Aquí se lee el puntero a mano.
    """
    import ctypes
    from comtypes import GUID

    if getattr(propvariant, "vt", None) != 72:  # VT_CLSID
        return ""
    puntero = ctypes.cast(ctypes.addressof(propvariant.union), ctypes.POINTER(ctypes.POINTER(GUID)))
    if not puntero.contents:
        return ""
    return str(puntero.contents.contents).upper()


@dataclass(frozen=True)
class Microfono:
    identificador: str
    nombre: str
    activo: bool


def microfonos_del_teclado() -> list[Microfono]:
    """Los puntos de captura de audio que pertenecen al teclado (cable o receptor)."""
    try:
        import comtypes  # noqa: F401
        from pycaw.utils import AudioUtilities
        from pycaw.constants import EDataFlow, DEVICE_STATE
    except ImportError as e:  # pragma: no cover
        raise ErrorDispositivo("faltan «pycaw» y «comtypes» para manejar el micrófono") from e
    from comtypes import GUID
    from comtypes.automation import VT_LPWSTR  # noqa: F401
    from pycaw.api.mmdeviceapi import PROPERTYKEY

    contenedores = contenedores_del_teclado()
    if not contenedores:
        return []
    clave_contenedor = PROPERTYKEY()
    clave_contenedor.fmtid = GUID("{8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c}")
    clave_contenedor.pid = 2
    enumerador = AudioUtilities.GetDeviceEnumerator()
    coleccion = enumerador.EnumAudioEndpoints(EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value | DEVICE_STATE.UNPLUGGED.value)
    resultado: list[Microfono] = []
    for i in range(coleccion.GetCount()):
        punto = coleccion.Item(i)
        propiedades = punto.OpenPropertyStore(0)
        try:
            contenedor = _guid_de(propiedades.GetValue(clave_contenedor))
        except Exception:  # noqa: BLE001 - puntos sin contenedor
            continue
        if not contenedor:
            continue
        if contenedor not in contenedores:
            continue
        nombre = "Micrófono del teclado"
        try:
            nombre = AudioUtilities.CreateDevice(punto).FriendlyName or nombre
        except Exception:  # noqa: BLE001
            pass
        resultado.append(Microfono(punto.GetId(), nombre, punto.GetState() == DEVICE_STATE.ACTIVE.value))
    return resultado


def microfono_predeterminado() -> str | None:
    try:
        from pycaw.utils import AudioUtilities
        return AudioUtilities.GetMicrophone().GetId()
    except Exception:  # noqa: BLE001
        return None


def hacer_predeterminado(identificador: str) -> None:
    """Pone ese punto de captura como micrófono del sistema, en los tres papeles."""
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.api.policyconfig import IPolicyConfig
    from pycaw.constants import CLSID_CPolicyConfigClient

    politica = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, IPolicyConfig, CLSCTX_ALL)
    for papel in (0, 1, 2):  # consola, multimedia, comunicaciones
        politica.SetDefaultEndpoint(identificador, papel)


def adoptar_microfono_del_teclado() -> Microfono | None:
    """Si el teclado tiene un micrófono activo y no es ya el del sistema, lo pone.

    Devuelve el micrófono adoptado, o None si no había nada que hacer.
    """
    activos = [m for m in microfonos_del_teclado() if m.activo]
    if not activos:
        return None
    actual = microfono_predeterminado()
    if any(m.identificador == actual for m in activos):
        return None
    elegido = activos[0]
    hacer_predeterminado(elegido.identificador)
    registro.info("micrófono del sistema: %s", elegido.nombre)
    return elegido


def vigilar_presencia(al_cambiar: Callable[[Presencia], None], cada_s: float = 2.0, parar: threading.Event | None = None) -> threading.Thread:
    """Hilo que avisa cuando el teclado aparece o desaparece por cualquier camino."""
    parar = parar or threading.Event()

    def bucle() -> None:
        ultima: Presencia | None = None
        while not parar.is_set():
            try:
                ahora = presencia()
            except ErrorDispositivo as e:
                registro.debug("presencia: %s", e)
                ahora = Presencia()
            if ultima is None or (ahora.cable, ahora.receptor) != (ultima.cable, ultima.receptor):
                ultima = ahora
                try:
                    al_cambiar(ahora)
                except Exception:  # noqa: BLE001 - que un aviso roto no mate el vigía
                    registro.exception("al avisar del cambio de presencia")
            parar.wait(cada_s)

    hilo = threading.Thread(target=bucle, name="minimic-presencia", daemon=True)
    hilo.start()
    return hilo
