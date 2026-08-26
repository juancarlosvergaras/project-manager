"""Tabla de codigos HID con nombres en espanol.

El teclado guarda codigos HID *Usage ID*, que describen la posicion fisica de
la tecla y no el simbolo impreso. En una distribucion espanola o latinoamericana
esa diferencia importa: la tecla de la enye es la misma que en un teclado
estadounidense produce el punto y coma. Aqui se resuelven ambos mundos:

* ``NOMBRES_HID`` acepta nombres en espanol ("intro", "mayus", "flecha arriba").
* ``atajo_a_codigos`` traduce combinaciones escritas como ``"ctrl+may+p"``.
* ``DISTRIBUCION_ES`` mapea los caracteres propios del espanol a su tecla fisica.
"""

from __future__ import annotations

from typing import Iterable

# --- Modificadores ------------------------------------------------------------
MODIFICADORES: dict[str, int] = {
    "ctrl": 0xE0,
    "control": 0xE0,
    "ctrl_izq": 0xE0,
    "may": 0xE1,
    "mayus": 0xE1,
    "shift": 0xE1,
    "alt": 0xE2,
    "opcion": 0xE2,
    "cmd": 0xE3,
    "super": 0xE3,
    "win": 0xE3,
    "meta": 0xE3,
    "ctrl_der": 0xE4,
    "may_der": 0xE5,
    "altgr": 0xE6,
    "alt_der": 0xE6,
    "cmd_der": 0xE7,
}

# --- Teclas base --------------------------------------------------------------
_BASICAS: dict[str, int] = {
    "intro": 0x28,
    "enter": 0x28,
    "esc": 0x29,
    "escape": 0x29,
    "retroceso": 0x2A,
    "borrar": 0x2A,
    "tab": 0x2B,
    "tabulador": 0x2B,
    "espacio": 0x2C,
    "guion": 0x2D,
    "igual": 0x2E,
    "corchete_izq": 0x2F,
    "corchete_der": 0x30,
    "barra_invertida": 0x31,
    "enye": 0x33,
    "ñ": 0x33,
    "tilde": 0x34,
    "acento": 0x34,
    "apostrofe": 0x34,
    "abrellave": 0x2F,
    "bloq_mayus": 0x39,
    "impr_pant": 0x46,
    "bloq_despl": 0x47,
    "pausa": 0x48,
    "insertar": 0x49,
    "inicio": 0x4A,
    "re_pag": 0x4B,
    "suprimir": 0x4C,
    "supr": 0x4C,
    "fin": 0x4D,
    "av_pag": 0x4E,
    "flecha_derecha": 0x4F,
    "flecha_izquierda": 0x50,
    "flecha_abajo": 0x51,
    "flecha_arriba": 0x52,
    "derecha": 0x4F,
    "izquierda": 0x50,
    "abajo": 0x51,
    "arriba": 0x52,
    "menor": 0x64,
    "aplicacion": 0x65,
    "menu": 0x65,
    "coma": 0x36,
    "punto": 0x37,
    "barra": 0x38,
    "punto_y_coma": 0x33,
}

# --- Distribucion espanola / latinoamericana ----------------------------------
# Caracter impreso -> (codigos HID que hay que pulsar). Las combinaciones con
# AltGr se expresan con el modificador incluido.
DISTRIBUCION_ES: dict[str, tuple[int, ...]] = {
    "ñ": (0x33,),
    "Ñ": (0xE1, 0x33),
    "´": (0x34,),
    "¨": (0xE1, 0x34),
    "ç": (0x31,),
    "¿": (0xE1, 0x2D),
    "¡": (0x2E,),
    "º": (0x35,),
    "ª": (0xE1, 0x35),
    "€": (0xE6, 0x08),
    "@": (0xE6, 0x1F),
    "#": (0xE6, 0x20),
    "[": (0xE6, 0x2F),
    "]": (0xE6, 0x30),
    "{": (0xE6, 0x34),
    "}": (0xE6, 0x31),
    "\\": (0xE6, 0x35),
    "|": (0xE6, 0x1E),
}


def _tabla_completa() -> dict[str, int]:
    tabla: dict[str, int] = dict(_BASICAS)
    for indice, letra in enumerate("abcdefghijklmnopqrstuvwxyz"):
        tabla[letra] = 0x04 + indice
    for indice, digito in enumerate("1234567890"):
        tabla[digito] = 0x1E + indice
    for numero in range(1, 13):  # F1..F12
        tabla[f"f{numero}"] = 0x3A + numero - 1
    for numero in range(13, 25):  # F13..F24
        tabla[f"f{numero}"] = 0x68 + numero - 13
    tabla["bloq_num"] = 0x53
    tabla["num_dividir"] = 0x54
    tabla["num_multiplicar"] = 0x55
    tabla["num_restar"] = 0x56
    tabla["num_sumar"] = 0x57
    tabla["num_intro"] = 0x58
    for numero in range(1, 10):
        tabla[f"num_{numero}"] = 0x59 + numero - 1
    tabla["num_0"] = 0x62
    tabla["num_punto"] = 0x63
    return tabla


NOMBRES_HID: dict[str, int] = _tabla_completa()

#: Codigo HID -> nombre preferido en espanol (para mostrar en la interfaz).
ETIQUETAS_HID: dict[int, str] = {}
for _nombre, _codigo in list(NOMBRES_HID.items()) + list(MODIFICADORES.items()):
    ETIQUETAS_HID.setdefault(_codigo, _nombre)


class ErrorTecla(ValueError):
    """Nombre de tecla o atajo que no se reconoce."""


def codigo_de(nombre: str) -> int:
    """Traduce el nombre de una tecla a su codigo HID."""
    clave = nombre.strip().lower().replace(" ", "_")
    if clave in MODIFICADORES:
        return MODIFICADORES[clave]
    if clave in NOMBRES_HID:
        return NOMBRES_HID[clave]
    if nombre in DISTRIBUCION_ES and len(DISTRIBUCION_ES[nombre]) == 1:
        return DISTRIBUCION_ES[nombre][0]
    raise ErrorTecla(f"Tecla desconocida: {nombre!r}")


def atajo_a_codigos(atajo: str) -> list[int]:
    """Convierte ``"ctrl+may+p"`` en la lista de codigos HID a enviar.

    Los modificadores van siempre delante, tal y como espera el firmware.
    """
    partes = [p for p in atajo.replace(" ", "").split("+") if p]
    if not partes:
        raise ErrorTecla("El atajo esta vacio")
    modificadores: list[int] = []
    normales: list[int] = []
    for parte in partes:
        clave = parte.lower()
        if clave in MODIFICADORES:
            codigo = MODIFICADORES[clave]
            if codigo not in modificadores:
                modificadores.append(codigo)
        else:
            normales.append(codigo_de(parte))
    if not normales:
        raise ErrorTecla(f"El atajo {atajo!r} solo tiene modificadores")
    return modificadores + normales


def describir(codigos: Iterable[int]) -> str:
    """Texto legible de una combinacion, para la interfaz y los registros."""
    piezas = [ETIQUETAS_HID.get(int(c), f"0x{int(c):02X}") for c in codigos]
    return "+".join(piezas)


def texto_a_macro(texto: str) -> list[tuple[int, int]]:
    """Convierte texto en pasos de macro ``(accion, parametro)``.

    Se apoya en ``DISTRIBUCION_ES`` para que las tildes y la enye se escriban
    igual que en un teclado espanol o latinoamericano en lugar de perderse.
    """
    from .protocolo import AccionMacro

    pasos: list[tuple[int, int]] = []
    for caracter in texto:
        if caracter in DISTRIBUCION_ES:
            codigos = DISTRIBUCION_ES[caracter]
        elif caracter == " ":
            codigos = (NOMBRES_HID["espacio"],)
        elif caracter == "\n":
            codigos = (NOMBRES_HID["intro"],)
        elif caracter.isupper() and caracter.lower() in NOMBRES_HID:
            codigos = (MODIFICADORES["may"], NOMBRES_HID[caracter.lower()])
        elif caracter.lower() in NOMBRES_HID:
            codigos = (NOMBRES_HID[caracter.lower()],)
        else:
            continue
        for codigo in codigos:
            pasos.append((AccionMacro.PULSAR, codigo))
        pasos.append((AccionMacro.SOLTAR_TODO, 0))
    return pasos
