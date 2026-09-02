"""Protocolo HID del teclado de voz (chip Jieli, VID 514C, PID 8850).

Sacado con Frida del programa del fabricante (``LQ_Keyboard.exe``) el 1 de
septiembre de 2026, y comprobado escribiendo y releyendo el teclado.

Todo viaja en informes HID de 64 bytes por la interfaz de fabricante (página
de uso 0xFF00, informe 3)::

    03 <orden> <capa> <arg> <len> <carga…> ……… <XOR de los bytes 1..62>

El último byte es la suma de control: XOR de todos los bytes salvo el
identificador de informe y él mismo. **Sin ella el teclado rechaza el
paquete** con ``03 07``; eso era lo que contestaba a todo lo que no fuera
suyo. El acuse bueno es ``03 06``.

Órdenes conocidas:

=====  ==================================================================
0x0C   información del aparato
0x04   leer una capa (arg 0xFF = todas las teclas); contesta un informe
       ``03 03 <capa> <tecla> <len> <registro>`` por tecla y luego el acuse
0x01   escribir una tecla: ``03 01 <capa> <tecla> <len> <registro>``
0x0D   leer ajustes (arg 1, carga ``01``); contesta ``01 01 <modo del mic>``
0x0E   escribir ajustes: carga ``01 01 <modo del mic>``
0x0A   leer luces (este modelo no tiene, pero contesta)
=====  ==================================================================

El registro de una tecla es ``[tipo][6×00][n][00][cuerpo…]``:

- tipo ``0x00``: una tecla sin modificadores; cuerpo = ``[código HID]``.
- tipo ``0x04``: combinación; cuerpo = ``[máscara de modificadores HID]
  [nº de teclas][códigos…]``. La máscara es la del informe de teclado USB:
  1 ctrl, 2 mayús, 4 alt, 8 win, y ×16 para los derechos.

Capas 0-2 y teclas 0-4, contadas desde cero en el cable; en la interfaz se
enseñan desde uno. Este módulo no toca el hardware: solo arma y desarma
bytes, para que se pueda probar sin teclado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TAMANO = 64
INFORME = 0x03

ORDEN_ESCRIBIR_TECLA = 0x01
ORDEN_REGISTRO_DE_TECLA = 0x03  # lo que contesta el teclado al leer
ORDEN_LEER_CAPA = 0x04
ACUSE = 0x06
RECHAZO = 0x07
ORDEN_LEER_LUCES = 0x0A
ORDEN_INFORMACION = 0x0C
ORDEN_LEER_AJUSTES = 0x0D
ORDEN_ESCRIBIR_AJUSTES = 0x0E

TODAS_LAS_TECLAS = 0xFF
NUMERO_DE_TECLAS = 5
NUMERO_DE_CAPAS = 3

TIPO_SIMPLE = 0x00
TIPO_COMBINACION = 0x04

#: Modo del micrófono, tal como lo guarda el teclado.
MICROFONO_MANTENER = 0  #: capta mientras la tecla está pulsada
MICROFONO_PULSAR = 1  #: una pulsación empieza, la siguiente para

MODIFICADORES = {
    "ctrl": 0x01, "mayus": 0x02, "alt": 0x04, "win": 0x08,
    "rctrl": 0x10, "rmayus": 0x20, "ralt": 0x40, "rwin": 0x80,
}
_ALIAS = {
    "shift": "mayus", "may": "mayus", "control": "ctrl", "cmd": "win",
    "windows": "win", "rshift": "rmayus",
}

#: Nombres en español de los códigos HID que interesan. Cualquier otro se
#: puede dar como ``<0x68>``.
NOMBRES: dict[int, str] = {0x04 + i: chr(ord("a") + i) for i in range(26)}
NOMBRES.update({0x1E + i: str(i + 1) for i in range(9)})
NOMBRES[0x27] = "0"
NOMBRES.update({
    0x28: "intro", 0x29: "esc", 0x2A: "retroceso", 0x2B: "tab", 0x2C: "espacio",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x33: ";", 0x34: "'",
    0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/", 0x39: "bloqmayus",
    0x46: "impr", 0x47: "bloqdespl", 0x48: "pausa", 0x49: "insert", 0x4A: "inicio",
    0x4B: "repag", 0x4C: "supr", 0x4D: "fin", 0x4E: "avpag",
    0x4F: "derecha", 0x50: "izquierda", 0x51: "abajo", 0x52: "arriba",
})
NOMBRES.update({0x3A + i: f"f{i + 1}" for i in range(12)})
NOMBRES.update({0x68 + i: f"f{i + 13}" for i in range(12)})
CODIGOS: dict[str, int] = {nombre: codigo for codigo, nombre in NOMBRES.items()}
CODIGOS.update({"enter": 0x28, "backspace": 0x2A, "space": 0x2C, "delete": 0x4C, "escape": 0x29})


class ErrorProtocolo(ValueError):
    """Bytes que no encajan con lo que el teclado dice o entiende."""


# --- armar paquetes ---------------------------------------------------------

def suma_de_control(paquete: bytes | bytearray) -> int:
    x = 0
    for b in paquete[1:63]:
        x ^= b
    return x


def paquete(orden: int, capa: int = 0, arg: int = 0, carga: bytes = b"") -> bytes:
    if not 0 <= len(carga) <= TAMANO - 6:
        raise ErrorProtocolo(f"carga de {len(carga)} bytes: no cabe")
    p = bytearray(TAMANO)
    p[0], p[1], p[2], p[3], p[4] = INFORME, orden, capa, arg, len(carga)
    p[5:5 + len(carga)] = carga
    p[63] = suma_de_control(p)
    return bytes(p)


def informacion() -> bytes:
    return paquete(ORDEN_INFORMACION)


def leer_capa(capa: int) -> bytes:
    _comprobar_capa(capa)
    return paquete(ORDEN_LEER_CAPA, capa, TODAS_LAS_TECLAS)


def leer_ajustes() -> bytes:
    return paquete(ORDEN_LEER_AJUSTES, 0, 1, b"\x01")


def escribir_ajustes(modo_microfono: int) -> bytes:
    if modo_microfono not in (MICROFONO_MANTENER, MICROFONO_PULSAR):
        raise ErrorProtocolo(f"modo de micrófono desconocido: {modo_microfono}")
    return paquete(ORDEN_ESCRIBIR_AJUSTES, 0, 1, bytes([1, 1, modo_microfono]))


def escribir_tecla(capa: int, tecla: int, registro: bytes) -> bytes:
    _comprobar_capa(capa)
    if not 0 <= tecla < NUMERO_DE_TECLAS:
        raise ErrorProtocolo(f"tecla {tecla}: hay {NUMERO_DE_TECLAS}, contadas desde 0")
    return paquete(ORDEN_ESCRIBIR_TECLA, capa, tecla, registro)


def _comprobar_capa(capa: int) -> None:
    if not 0 <= capa < NUMERO_DE_CAPAS:
        raise ErrorProtocolo(f"capa {capa}: hay {NUMERO_DE_CAPAS}, contadas desde 0")


# --- el registro de una tecla ------------------------------------------------

@dataclass(frozen=True)
class Atajo:
    """Lo que hace una tecla: modificadores más códigos HID, o nada."""

    modificadores: int = 0
    codigos: tuple[int, ...] = field(default_factory=tuple)

    @property
    def vacio(self) -> bool:
        return self.modificadores == 0 and not self.codigos

    def __str__(self) -> str:
        partes = [nombre for nombre, bit in MODIFICADORES.items() if self.modificadores & bit]
        partes += [NOMBRES.get(c, f"<{c:#04x}>") for c in self.codigos]
        return "-".join(partes) if partes else "nada"

    @classmethod
    def desde_texto(cls, texto: str) -> "Atajo":
        """``ctrl-a``, ``win-h``, ``retroceso``, ``ctrl-win`` (solo modificadores), ``nada``."""
        texto = texto.strip().lower()
        if texto in ("", "nada", "-"):
            return cls()
        modificadores = 0
        codigos: list[int] = []
        for parte in texto.split("-"):
            parte = _ALIAS.get(parte, parte)
            if parte in MODIFICADORES:
                modificadores |= MODIFICADORES[parte]
            elif parte in CODIGOS:
                codigos.append(CODIGOS[parte])
            elif parte.startswith("<") and parte.endswith(">"):
                codigos.append(int(parte[1:-1], 0))
            else:
                raise ErrorProtocolo(f"no sé qué tecla es «{parte}»")
        return cls(modificadores, tuple(codigos))

    def a_registro(self) -> bytes:
        if self.modificadores == 0 and len(self.codigos) == 1:
            return bytes([TIPO_SIMPLE, 0, 0, 0, 0, 0, 0, 1, 0, self.codigos[0]])
        cuerpo = bytes([self.modificadores, len(self.codigos), *self.codigos])
        return bytes([TIPO_COMBINACION, 0, 0, 0, 0, 0, 0, len(cuerpo), 0]) + cuerpo

    @classmethod
    def desde_registro(cls, registro: bytes) -> "Atajo":
        if len(registro) < 9:
            raise ErrorProtocolo(f"registro de {len(registro)} bytes: demasiado corto")
        tipo, n, cuerpo = registro[0], registro[7], registro[9:]
        if tipo == TIPO_SIMPLE:
            return cls(0, (cuerpo[0],)) if n and cuerpo else cls()
        if tipo == TIPO_COMBINACION:
            if len(cuerpo) < 2:
                raise ErrorProtocolo("combinación sin cuerpo")
            cuantas = cuerpo[1]
            return cls(cuerpo[0], tuple(cuerpo[2:2 + cuantas]))
        raise ErrorProtocolo(f"tipo de registro desconocido: {tipo:#04x}")


# --- desarmar respuestas -----------------------------------------------------

@dataclass(frozen=True)
class Respuesta:
    orden: int
    capa: int
    arg: int
    carga: bytes

    @property
    def es_acuse(self) -> bool:
        return self.orden == ACUSE

    @property
    def es_rechazo(self) -> bool:
        return self.orden == RECHAZO


def analizar(informe: bytes) -> Respuesta:
    if len(informe) < 5 or informe[0] != INFORME:
        raise ErrorProtocolo(f"no es un informe del teclado: {bytes(informe[:5]).hex(' ')}")
    if informe[1] in (ACUSE, RECHAZO):
        # Ni el acuse ni el rechazo llevan longitud: devuelven un eco del
        # paquete al que contestan (``ff`` tras leer una capa, la tecla tras
        # escribirla) y una suma de control. Se guarda tal cual, para el registro.
        return Respuesta(informe[1], informe[2], informe[3], bytes(informe[4:9]))
    n = informe[4]
    if 5 + n > len(informe):
        raise ErrorProtocolo(f"el informe dice {n} bytes de carga y no los trae")
    return Respuesta(informe[1], informe[2], informe[3], bytes(informe[5:5 + n]))


@dataclass(frozen=True)
class Informacion:
    """Lo poco que se entiende de la respuesta a 0x0C: ``a5 01 08 00 01 00 00 00``."""

    cruda: bytes

    @property
    def modelo(self) -> str:
        return self.cruda[:2].hex() if len(self.cruda) >= 2 else "?"


@dataclass(frozen=True)
class Ajustes:
    modo_microfono: int

    @classmethod
    def desde_carga(cls, carga: bytes) -> "Ajustes":
        if len(carga) < 3:
            raise ErrorProtocolo(f"ajustes de {len(carga)} bytes: esperaba 3")
        return cls(carga[2])
