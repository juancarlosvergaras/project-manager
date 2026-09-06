"""Protocolo de la Botonera: 12 teclas, 3 perillas, luces RGB y 3 perfiles.

Es el cuarto teclado de la casa y lleva el mismo chip Jieli que el MiniMic y
el SiKai mini (``514C:8850`` por cable, «MINI_KEYBOARD» por Bluetooth), pero
**otro firmware**: el que atiende el ``ch57x-keyboard-tool`` con su módulo
``k8850`` (PR 175, incidencias 136 y 153). Se descifró el 6/9/2026 contra el
aparato. Lo que cambia respecto a los otros dos, y que costó una tarde:

- **Informes de 64 bytes de datos**, no 63: el paquete va en **65 bytes** con
  el identificador ``0x03`` delante. Con 64 el teclado lo tira sin decir nada.
- **No contesta nunca.** Ni acuse ni rechazo, ni se puede leer lo que tiene
  grabado. El silencio no significa que la orden fuera mal: significa que es
  este teclado. Por eso la configuración vive en nuestro archivo y se le
  vuelve a grabar entera cuando hace falta; y para comprobar lo grabado hay
  que escuchar sus pulsaciones (``escucha.py``).
- **Sin suma de control.** Las órdenes LQ (``03 <orden> <capa>…`` con XOR en
  el último byte) no le dicen nada.

Órdenes:

- Tecla: ``03 FD <id> <perfil+1> <tipo> <carga…>`` y detrás, siempre, el
  cierre ``03 FD FE FF``. Tipo 1 teclado: ``00 <n> [00 00 <código>]×n`` con
  los modificadores como pasos (``F1`` Ctrl, ``F2`` Mayús, ``F3`` Alt, ``F4``
  Win, ``F5``-``F8`` los derechos), hasta 18 pasos. Tipo 2 multimedia:
  ``00 02 00 00 <bajo> 00 00 <alto>``. Tipo 3 ratón: 17 bytes
  ``01 04 00 00 <mod> 00 00 <botones> 00 00 <dx> 00 00 <dy> 00 00 <rueda>``.
- Luces: ``03 FE B0 <perfil> <modo> R G B`` más dieciséis ternas RGB (una por
  tecla, según el fabricante; el firmware con doce teclas solo mira las que
  tiene). El perfil aquí va **desde 0**, al revés que en la orden de tecla.
  Modos: 0 apagado, 1 fijo, 2 reactivo, 3 onda, 4 arcoíris por filas,
  5 arcoíris por columnas.

Numeración de piezas, comprobada grabando un mapa conocido y escuchándolo:
teclas ``1``-``12`` por filas de cuatro (arriba izquierda es la 1), y las
perillas desde el ``16``, tres ids cada una: ``16+3n`` giro a un lado,
``17+3n`` pulsación, ``18+3n`` giro al otro lado. Qué giro es cuál se deja
como dice la herramienta (antihorario, pulsar, horario); si va al revés, se
cambian los dos giros entre sí desde el panel.

Este módulo no toca el hardware: arma bytes y traduce textos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from minimic.protocolo import CODIGOS, NOMBRES, ErrorProtocolo, _ALIAS  # noqa: F401 - se reexportan
from sikaimini.protocolo import CONSUMO

INFORME = 0x03
TAMANO = 65
ORDEN_TECLA = 0xFD
ORDEN_LUCES = 0xFE
SUB_LUCES = 0xB0
FIN_DE_TECLA = bytes([INFORME, ORDEN_TECLA, 0xFE, 0xFF])

TIPO_TECLADO, TIPO_MULTIMEDIA, TIPO_RATON = 0x01, 0x02, 0x03
MAX_PASOS = 18
RETARDO_DEL_PASO = 0x00  # los dos primeros bytes de cada paso; la herramienta manda ceros

FILAS, COLUMNAS = 3, 4
NUMERO_DE_TECLAS = FILAS * COLUMNAS
NUMERO_DE_PERILLAS = 3
GESTOS = ("giro-izquierda", "pulsar", "giro-derecha")
NUMERO_DE_PIEZAS = NUMERO_DE_TECLAS + NUMERO_DE_PERILLAS * len(GESTOS)  # 21
NUMERO_DE_PERFILES = 3
PRIMER_ID_DE_PERILLA = 16

#: Qué es cada índice de pieza (0..20), para hablar de ellas por su nombre.
NOMBRES_DE_LAS_PIEZAS: tuple[str, ...] = tuple(
    [f"tecla {i + 1}" for i in range(NUMERO_DE_TECLAS)]
    + [f"perilla {n + 1}, {g}" for n in range(NUMERO_DE_PERILLAS) for g in ("giro a la izquierda", "pulsación", "giro a la derecha")]
)

MODOS_DE_LUZ: dict[int, str] = {
    0: "apagado", 1: "fijo", 2: "reactivo (se enciende al pulsar)", 3: "onda",
    4: "arcoíris por filas", 5: "arcoíris por columnas",
}
COLORES_EN_LA_ORDEN = 16

#: Modificadores como los quiere este firmware: pasos de la secuencia, no una máscara.
MODIFICADORES: dict[str, int] = {
    "ctrl": 0xF1, "mayus": 0xF2, "alt": 0xF3, "win": 0xF4,
    "rctrl": 0xF5, "rmayus": 0xF6, "ralt": 0xF7, "rwin": 0xF8,
}
_MODIFICADORES_INV = {v: k for k, v in MODIFICADORES.items()}

#: Ratón: nombre -> (botones, rueda, modificador). Botones: 1 izquierdo,
#: 2 derecho, 4 central. Rueda: +1 arriba, -1 abajo.
RATON: dict[str, tuple[int, int, int]] = {
    "clic": (1, 0, 0), "clic-derecho": (2, 0, 0), "clic-central": (4, 0, 0),
    "rueda-arriba": (0, 1, 0), "rueda-abajo": (0, -1, 0),
    "ctrl-rueda-arriba": (0, 1, 0xF1), "ctrl-rueda-abajo": (0, -1, 0xF1),
    "mayus-rueda-arriba": (0, 1, 0xF2), "mayus-rueda-abajo": (0, -1, 0xF2),
    "alt-rueda-arriba": (0, 1, 0xF3), "alt-rueda-abajo": (0, -1, 0xF3),
    "ctrl-clic": (1, 0, 0xF1), "mayus-clic": (1, 0, 0xF2), "alt-clic": (1, 0, 0xF3),
}
_ALIAS_PROPIOS = {
    "wheel-up": "rueda-arriba", "wheel-down": "rueda-abajo", "mute": "silencio", "click": "clic",
    "right-click": "clic-derecho", "middle-click": "clic-central", "": "nada",
}


# --- piezas ------------------------------------------------------------------

def id_de_pieza(pieza: int) -> int:
    """El id que usa el firmware para la pieza (0..20). Teclas 1-12, perillas desde 16."""
    if not 0 <= pieza < NUMERO_DE_PIEZAS:
        raise ErrorProtocolo(f"pieza {pieza}: hay {NUMERO_DE_PIEZAS}, contadas desde 0")
    if pieza < NUMERO_DE_TECLAS:
        return pieza + 1
    perilla, gesto = divmod(pieza - NUMERO_DE_TECLAS, len(GESTOS))
    return PRIMER_ID_DE_PERILLA + 3 * perilla + gesto


def pieza_de_perilla(perilla: int, gesto: int) -> int:
    if not 0 <= perilla < NUMERO_DE_PERILLAS or not 0 <= gesto < len(GESTOS):
        raise ErrorProtocolo(f"perilla {perilla}, gesto {gesto}: no existe")
    return NUMERO_DE_TECLAS + 3 * perilla + gesto


def _comprobar_perfil(perfil: int) -> None:
    if not 0 <= perfil < NUMERO_DE_PERFILES:
        raise ErrorProtocolo(f"perfil {perfil}: hay {NUMERO_DE_PERFILES}, contados desde 0")


# --- paquetes ----------------------------------------------------------------

def mensaje(*cuerpo: int | bytes) -> bytes:
    """Rellena hasta los 65 bytes que pide el informe de salida."""
    datos = bytearray()
    for parte in cuerpo:
        datos += bytes([parte]) if isinstance(parte, int) else bytes(parte)
    if len(datos) > TAMANO:
        raise ErrorProtocolo(f"mensaje de {len(datos)} bytes: no cabe en {TAMANO}")
    return bytes(datos) + bytes(TAMANO - len(datos))


def mensajes_de_pieza(perfil: int, pieza: int, accion: "Accion") -> list[bytes]:
    """La orden de grabar una pieza y su cierre, tal como se le mandan."""
    _comprobar_perfil(perfil)
    return [
        mensaje(INFORME, ORDEN_TECLA, id_de_pieza(pieza), perfil + 1, accion.tipo, accion.a_carga()),
        mensaje(FIN_DE_TECLA),
    ]


def mensaje_de_luces(perfil: int, luces: "Luces") -> bytes:
    _comprobar_perfil(perfil)
    r, g, b = luces.rgb
    return mensaje(INFORME, ORDEN_LUCES, SUB_LUCES, perfil, luces.modo, r, g, b, bytes([r, g, b]) * COLORES_EN_LA_ORDEN)


def mensajes_de_perfil(perfil: int, acciones: Iterable["Accion"], luces: "Luces | None" = None) -> list[bytes]:
    """Todo lo de un perfil: las 21 piezas y, si se dan, las luces."""
    acciones = list(acciones)
    if len(acciones) != NUMERO_DE_PIEZAS:
        raise ErrorProtocolo(f"hacen falta {NUMERO_DE_PIEZAS} acciones, una por pieza; llegaron {len(acciones)}")
    salida: list[bytes] = []
    for pieza, accion in enumerate(acciones):
        salida.extend(mensajes_de_pieza(perfil, pieza, accion))
    if luces is not None:
        salida.append(mensaje_de_luces(perfil, luces))
    return salida


# --- lo que hace una pieza ---------------------------------------------------

@dataclass(frozen=True)
class Accion:
    """Lo que hace una tecla o un gesto de la perilla, en texto y en bytes.

    Tres familias: ``teclado`` (una tecla, una combinación o una secuencia de
    hasta 18 pasos: ``ctrl-c``, ``ctrl-c, ctrl-v``, ``win-h``), ``multimedia``
    (``vol+``, ``silencio``, ``reproducir``…) y ``raton`` (``clic``,
    ``rueda-arriba``, ``ctrl-rueda-abajo``…). ``nada`` deja la pieza muda.
    """

    familia: str
    pasos: tuple[tuple[str, ...], ...] = ()  # solo teclado: cada paso son sus modificadores y, al final, la tecla
    nombre: str = ""  # multimedia y ratón

    @property
    def tipo(self) -> int:
        return {"teclado": TIPO_TECLADO, "multimedia": TIPO_MULTIMEDIA, "raton": TIPO_RATON}[self.familia]

    @classmethod
    def nada(cls) -> "Accion":
        return cls("teclado", ())

    @classmethod
    def desde_texto(cls, texto: str) -> "Accion":
        limpio = " ".join(str(texto).strip().lower().split())
        limpio = _ALIAS_PROPIOS.get(limpio, limpio)
        if limpio == "nada":
            return cls.nada()
        if limpio in RATON:
            return cls("raton", nombre=limpio)
        if limpio in CONSUMO:
            return cls("multimedia", nombre=limpio)
        pasos: list[tuple[str, ...]] = []
        for trozo in limpio.split(","):
            trozo = trozo.strip()
            if not trozo:
                raise ErrorProtocolo(f"«{texto}»: hay un paso vacío entre comas")
            pasos.append(_analizar_paso(trozo, texto))
        cuantos = sum(len(p) for p in pasos)
        if cuantos > MAX_PASOS:
            raise ErrorProtocolo(f"«{texto}»: {cuantos} pulsaciones; el teclado admite {MAX_PASOS}")
        return cls("teclado", tuple(pasos))

    def __str__(self) -> str:
        if self.familia != "teclado":
            return self.nombre
        if not self.pasos:
            return "nada"
        return ", ".join("-".join(p) for p in self.pasos)

    def a_carga(self) -> bytes:
        if self.familia == "multimedia":
            codigo = CONSUMO[self.nombre]
            return bytes([0x00, 0x02, 0x00, 0x00, codigo & 0xFF, 0x00, 0x00, codigo >> 8])
        if self.familia == "raton":
            botones, rueda, modificador = RATON[self.nombre]
            carga = bytearray(17)
            carga[0], carga[1], carga[4], carga[7], carga[16] = 0x01, 0x04, modificador, botones, rueda & 0xFF
            return bytes(carga)
        codigos: list[int] = []
        for paso in self.pasos:
            for parte in paso:
                codigos.append(MODIFICADORES.get(parte, CODIGOS.get(parte, 0)))
        salida = bytearray([0x00, len(codigos)])
        for c in codigos:
            salida += bytes([RETARDO_DEL_PASO, RETARDO_DEL_PASO, c])
        return bytes(salida)


def _analizar_paso(trozo: str, original: str) -> tuple[str, ...]:
    partes = trozo.split("-")
    # La tecla «-» se escribe como último trozo vacío: «ctrl--» es Ctrl y guion.
    if len(partes) >= 2 and partes[-1] == "" and partes[-2] == "":
        partes = partes[:-2] + ["-"]
    elif partes[-1] == "" and len(partes) >= 2:
        partes = partes[:-1] + ["-"]
    modificadores: list[str] = []
    tecla: str | None = None
    for parte in partes:
        parte = _ALIAS.get(parte, parte)
        if parte in MODIFICADORES:
            if parte in modificadores:
                raise ErrorProtocolo(f"«{original}»: {parte} repetido")
            modificadores.append(parte)
        elif parte in CODIGOS:
            if tecla is not None:
                raise ErrorProtocolo(f"«{original}»: dos teclas en un paso ({tecla} y {parte}); sepáralas con coma")
            tecla = NOMBRES[CODIGOS[parte]]
        elif parte.startswith("<0x") and parte.endswith(">"):
            try:
                codigo = int(parte[1:-1], 16)
            except ValueError as e:
                raise ErrorProtocolo(f"«{original}»: código {parte} ilegible") from e
            if not 0 < codigo < 0xF0:
                raise ErrorProtocolo(f"«{original}»: código {parte} fuera de rango")
            tecla = NOMBRES.get(codigo, parte)
            if tecla == parte:
                CODIGOS.setdefault(parte, codigo)
        else:
            raise ErrorProtocolo(f"no conozco la tecla «{parte}» (en «{original}»)")
    if tecla is None and not modificadores:
        raise ErrorProtocolo(f"«{original}»: paso vacío")
    return tuple(modificadores + ([tecla] if tecla else []))


# --- luces -------------------------------------------------------------------

def color_desde_texto(texto: str) -> tuple[int, int, int]:
    t = str(texto).strip().lstrip("#")
    if len(t) != 6:
        raise ErrorProtocolo(f"color «{texto}»: tiene que ser #RRGGBB")
    try:
        return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
    except ValueError as e:
        raise ErrorProtocolo(f"color «{texto}»: tiene que ser #RRGGBB") from e


def color_a_texto(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


@dataclass(frozen=True)
class Luces:
    modo: int = 1
    color: str = "#ffffff"

    def __post_init__(self) -> None:
        if not isinstance(self.modo, int) or isinstance(self.modo, bool) or not 0 <= self.modo <= 255:
            raise ErrorProtocolo(f"modo de luz {self.modo!r}: va de 0 a 255")
        object.__setattr__(self, "color", color_a_texto(color_desde_texto(self.color)))

    @property
    def rgb(self) -> tuple[int, int, int]:
        return color_desde_texto(self.color)

    @property
    def nombre_del_modo(self) -> str:
        return MODOS_DE_LUZ.get(self.modo, f"modo {self.modo}")

    def como_dict(self) -> dict:
        return {"modo": self.modo, "color": self.color, "nombre": self.nombre_del_modo}
