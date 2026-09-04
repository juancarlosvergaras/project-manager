"""Protocolo del SiKai mini (chip Jieli 514C:8850), encima del de MiniMic.

Es el mismo firmware de la casa LQ que lleva el MiniMic —paquete de 64 bytes
``03 <orden> <capa> <arg> <len> <carga…>`` con XOR en el byte 63, acuse
``03 06``, rechazo ``03 07``—, comprobado el 4 de septiembre de 2026 contra el
aparato y espiando ``LQ_Keyboard.exe`` con Frida. Lo que cambia:

- **Seis registros en una sola capa.** Índices 0-2 son las tres teclas (No,
  Sí y micrófono) y 3-5 la perilla: los dos sentidos de giro y la pulsación.
  Leer las capas 1 y 2 devuelve rechazo: este modelo no tiene grupos.
- **Dos tipos de registro más.** Además del simple (``0x00``) y la
  combinación (``0x04``) del MiniMic, la perilla y las teclas admiten
  **multimedia** (``0x02``: un uso de la página *Consumer* en dos bytes,
  byte bajo primero) y **ratón** (``0x03``: un código de un byte). La tabla
  de ratón se sacó pulsando uno a uno los botones de la pestaña «Mouse» del
  programa del fabricante.
- **Luces.** ``0x0A`` las lee y ``0x09`` las escribe, las dos con arg
  ``0xFE`` y una carga de 52 bytes: ``[modo][R][G][B]`` y una paleta de
  dieciséis colores. El programa del fabricante esconde la pestaña de luces
  para este modelo, así que qué hace cada modo se averigua mirando el teclado.

Este módulo no toca el hardware: arma y desarma bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from minimic.protocolo import (  # noqa: F401 - se reexportan
    ACUSE, CODIGOS, INFORME, MICROFONO_MANTENER, MICROFONO_PULSAR, MODIFICADORES, NOMBRES,
    ORDEN_ESCRIBIR_AJUSTES, ORDEN_ESCRIBIR_TECLA, ORDEN_INFORMACION, ORDEN_LEER_AJUSTES,
    ORDEN_LEER_CAPA, ORDEN_LEER_LUCES, ORDEN_REGISTRO_DE_TECLA, RECHAZO, TAMANO, TIPO_COMBINACION,
    TIPO_SIMPLE, TODAS_LAS_TECLAS, Ajustes, ErrorProtocolo, Informacion, Respuesta, _ALIAS, analizar,
    escribir_ajustes, informacion, leer_ajustes, paquete, suma_de_control,
)

NUMERO_DE_TECLAS = 6
NUMERO_DE_CAPAS = 1

#: Qué es cada índice, para hablar de ellos por su nombre.
TECLA_NO, TECLA_SI, TECLA_MICROFONO, PERILLA_GIRO_A, PERILLA_GIRO_B, PERILLA_PULSAR = range(6)
NOMBRES_DE_LAS_PIEZAS = (
    "tecla No", "tecla Sí", "tecla del micrófono",
    "perilla, giro A", "perilla, giro B", "perilla, pulsación",
)

TIPO_CONSUMO = 0x02
TIPO_RATON = 0x03

ORDEN_ESCRIBIR_LUCES = 0x09
ARG_LUCES = 0xFE
LARGO_LUCES = 52
COLORES_DE_PALETA = 16

#: Página de uso *Consumer* (USB HID Usage Tables, capítulo 15).
CONSUMO: dict[str, int] = {
    "vol+": 0xE9, "vol-": 0xEA, "silencio": 0xE2,
    "siguiente": 0xB5, "anterior": 0xB6, "parar": 0xB7, "reproducir": 0xCD,
    "brillo+": 0x6F, "brillo-": 0x70,
    "calculadora": 0x192, "equipo": 0x194, "navegador": 0x223, "correo": 0x18A, "reproductor": 0x183,
    "actualizar": 0x227, "adelante": 0x225, "atras": 0x224,
}
_CONSUMO_INV = {v: k for k, v in CONSUMO.items()}

#: Códigos de ratón del firmware, en el orden en que los enseña el programa
#: del fabricante (capturados uno a uno el 4/9/2026).
RATON: dict[str, int] = {
    "clic": 0x00, "clic-derecho": 0x01, "clic-central": 0x02,
    "rueda-arriba": 0x03, "rueda-abajo": 0x04,
    "ctrl-rueda-arriba": 0x05, "ctrl-rueda-abajo": 0x06,
    "mayus-rueda-arriba": 0x07, "mayus-rueda-abajo": 0x08,
    "alt-rueda-arriba": 0x09, "alt-rueda-abajo": 0x0A,
    "gesto-izquierda": 0x0B, "gesto-derecha": 0x0C, "gesto-arriba": 0x0D, "gesto-abajo": 0x0E,
    "me-gusta": 0x0F,
}
_RATON_INV = {v: k for k, v in RATON.items()}
_ALIAS_PROPIOS = {"wheel-up": "rueda-arriba", "wheel-down": "rueda-abajo", "mute": "silencio", "click": "clic"}


# --- paquetes -----------------------------------------------------------------

def leer_capa(capa: int = 0) -> bytes:
    _comprobar_capa(capa)
    return paquete(ORDEN_LEER_CAPA, capa, TODAS_LAS_TECLAS)


def escribir_tecla(capa: int, tecla: int, registro: bytes) -> bytes:
    _comprobar_capa(capa)
    if not 0 <= tecla < NUMERO_DE_TECLAS:
        raise ErrorProtocolo(f"pieza {tecla}: hay {NUMERO_DE_TECLAS}, contadas desde 0")
    return paquete(ORDEN_ESCRIBIR_TECLA, capa, tecla, registro)


def leer_luces() -> bytes:
    return paquete(ORDEN_LEER_LUCES, 0, 0)


def escribir_luces(luces: "Luces") -> bytes:
    return paquete(ORDEN_ESCRIBIR_LUCES, 0, ARG_LUCES, luces.a_carga())


def _comprobar_capa(capa: int) -> None:
    if not 0 <= capa < NUMERO_DE_CAPAS:
        raise ErrorProtocolo(f"capa {capa}: este teclado solo tiene una")


# --- el registro de una pieza ---------------------------------------------------

@dataclass(frozen=True)
class Atajo:
    """Lo que hace una tecla o un gesto de la perilla.

    Tres familias, por el primer byte del registro: teclado (simple o
    combinación), multimedia y ratón. En texto se escriben como en MiniMic
    (``ctrl-a``, ``retroceso``, ``ctrl-win``) o con los nombres de
    :data:`CONSUMO` y :data:`RATON` (``vol+``, ``rueda-abajo``, ``clic-central``).
    """

    tipo: int = TIPO_SIMPLE
    modificadores: int = 0
    codigos: tuple[int, ...] = field(default_factory=tuple)

    @property
    def vacio(self) -> bool:
        return self.tipo in (TIPO_SIMPLE, TIPO_COMBINACION) and self.modificadores == 0 and not self.codigos

    @property
    def familia(self) -> str:
        return {TIPO_CONSUMO: "multimedia", TIPO_RATON: "raton"}.get(self.tipo, "teclado")

    def __str__(self) -> str:
        if self.tipo == TIPO_RATON:
            return _RATON_INV.get(self.codigos[0], f"raton<{self.codigos[0]:#04x}>") if self.codigos else "nada"
        if self.tipo == TIPO_CONSUMO:
            return _CONSUMO_INV.get(self.codigos[0], f"multimedia<{self.codigos[0]:#05x}>") if self.codigos else "nada"
        partes = [nombre for nombre, bit in MODIFICADORES.items() if self.modificadores & bit]
        partes += [NOMBRES.get(c, f"<{c:#04x}>") for c in self.codigos]
        return "-".join(partes) if partes else "nada"

    @classmethod
    def desde_texto(cls, texto: str) -> "Atajo":
        texto = texto.strip().lower()
        texto = _ALIAS_PROPIOS.get(texto, texto)
        if texto in ("", "nada", "-"):
            return cls()
        if texto in RATON:
            return cls(TIPO_RATON, 0, (RATON[texto],))
        if texto in CONSUMO:
            return cls(TIPO_CONSUMO, 0, (CONSUMO[texto],))
        if texto.startswith("raton<") and texto.endswith(">"):
            return cls(TIPO_RATON, 0, (int(texto[6:-1], 0),))
        if texto.startswith("multimedia<") and texto.endswith(">"):
            return cls(TIPO_CONSUMO, 0, (int(texto[11:-1], 0),))
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
        if modificadores == 0 and len(codigos) == 1:
            return cls(TIPO_SIMPLE, 0, tuple(codigos))
        return cls(TIPO_COMBINACION, modificadores, tuple(codigos))

    def a_registro(self) -> bytes:
        cabecera = [0, 0, 0, 0, 0, 0]
        if self.tipo == TIPO_RATON:
            return bytes([TIPO_RATON, *cabecera, 1, 0, self.codigos[0] & 0xFF])
        if self.tipo == TIPO_CONSUMO:
            uso = self.codigos[0]
            return bytes([TIPO_CONSUMO, *cabecera, 2, 0, uso & 0xFF, (uso >> 8) & 0xFF])
        if self.modificadores == 0 and len(self.codigos) == 1:
            return bytes([TIPO_SIMPLE, *cabecera, 1, 0, self.codigos[0]])
        cuerpo = bytes([self.modificadores, len(self.codigos), *self.codigos])
        return bytes([TIPO_COMBINACION, *cabecera, len(cuerpo), 0]) + cuerpo

    @classmethod
    def desde_registro(cls, registro: bytes) -> "Atajo":
        if len(registro) < 9:
            raise ErrorProtocolo(f"registro de {len(registro)} bytes: demasiado corto")
        tipo, n, cuerpo = registro[0], registro[7], registro[9:]
        if tipo == TIPO_SIMPLE:
            return cls(TIPO_SIMPLE, 0, (cuerpo[0],)) if n and cuerpo else cls()
        if tipo == TIPO_COMBINACION:
            if len(cuerpo) < 2:
                raise ErrorProtocolo("combinación sin cuerpo")
            if cuerpo[0] == 0 and cuerpo[1] == 0:
                return cls()  # «nada» se escribe como combinación vacía y se lee como nada
            return cls(TIPO_COMBINACION, cuerpo[0], tuple(cuerpo[2:2 + cuerpo[1]]))
        if tipo == TIPO_CONSUMO:
            if len(cuerpo) < 2:
                raise ErrorProtocolo("registro multimedia sin uso")
            return cls(TIPO_CONSUMO, 0, (cuerpo[0] | (cuerpo[1] << 8),))
        if tipo == TIPO_RATON:
            if not cuerpo:
                raise ErrorProtocolo("registro de ratón sin código")
            return cls(TIPO_RATON, 0, (cuerpo[0],))
        raise ErrorProtocolo(f"tipo de registro desconocido: {tipo:#04x}")


# --- las luces -------------------------------------------------------------------

Color = tuple[int, int, int]


def color_desde_texto(texto: str) -> Color:
    t = texto.strip().lstrip("#")
    if len(t) != 6:
        raise ErrorProtocolo(f"color «{texto}»: se espera #RRGGBB")
    try:
        return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
    except ValueError as e:
        raise ErrorProtocolo(f"color «{texto}»: se espera #RRGGBB") from e


def color_a_texto(color: Color) -> str:
    return "#%02x%02x%02x" % tuple(c & 0xFF for c in color)


@dataclass(frozen=True)
class Luces:
    """Lo que el teclado guarda de sus luces: un modo, un color y una paleta."""

    modo: int = 0
    color: Color = (0, 0, 0)
    paleta: tuple[Color, ...] = field(default_factory=tuple)

    @classmethod
    def desde_carga(cls, carga: bytes) -> "Luces":
        if len(carga) < LARGO_LUCES:
            raise ErrorProtocolo(f"luces de {len(carga)} bytes: esperaba {LARGO_LUCES}")
        paleta = tuple((carga[i], carga[i + 1], carga[i + 2]) for i in range(4, 4 + 3 * COLORES_DE_PALETA, 3))
        return cls(carga[0], (carga[1], carga[2], carga[3]), paleta)

    def a_carga(self) -> bytes:
        paleta = list(self.paleta)[:COLORES_DE_PALETA]
        paleta += [(0, 0, 0)] * (COLORES_DE_PALETA - len(paleta))
        cuerpo = bytes([self.modo & 0xFF, *(c & 0xFF for c in self.color)])
        for color in paleta:
            cuerpo += bytes(c & 0xFF for c in color)
        return cuerpo

    def con(self, modo: int | None = None, color: Color | None = None) -> "Luces":
        return Luces(self.modo if modo is None else modo, self.color if color is None else color, self.paleta)

    def como_dict(self) -> dict:
        return {"modo": self.modo, "color": color_a_texto(self.color), "paleta": [color_a_texto(c) for c in self.paleta]}
