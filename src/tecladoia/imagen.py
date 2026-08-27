"""Convierte una imagen o un GIF a lo que entiende la pantalla del teclado.

La pantalla es de 160 × 80 puntos y guarda cada punto en dos bytes con el
formato RGB565: cinco bits de rojo, seis de verde y cinco de azul. Un fotograma
ocupa 25 600 bytes, y el firmware le reserva una ranura de 28 672 —siete bloques
de 4 KiB— porque las escrituras en su memoria flash van alineadas a 4 KiB.

Aquí solo se prepara el material: recortar, ajustar y convertir. Quien lo envía
es :mod:`tecladoia.dispositivo`, que sabe trocearlo y hablar con el aparato.

Hace falta *Pillow* (``pip install "tecladoia[imagenes]"``). Sin él, todo lo
demás sigue funcionando: lo único que se pierde es poder cambiar la pantalla.
"""

from __future__ import annotations

import importlib.util
import io
from typing import Iterator

from .protocolo import (
    OLED_ALTO,
    OLED_ANCHO,
    OLED_BYTES_POR_FOTOGRAMA,
    OLED_MAXIMO_FOTOGRAMAS,
    OLED_TAMANO_RANURA,
)

#: Tamaño máximo del archivo que se acepta, para no llenar la memoria del equipo.
MAXIMO_BYTES_ARCHIVO = 2 * 1024 * 1024

#: Fotogramas que se aceptan de un GIF. El firmware admite más en total, pero
#: repartidos entre los cuatro modos; setenta por modo es un reparto sensato.
MAXIMO_FOTOGRAMAS_POR_MODO = 70


class ErrorImagen(ValueError):
    """El archivo no se puede convertir para la pantalla."""


def hay_pillow() -> bool:
    return importlib.util.find_spec("PIL") is not None


def _exigir_pillow():
    if not hay_pillow():
        raise ErrorImagen(
            "Para cambiar la pantalla hace falta la biblioteca Pillow. "
            'Instálala con: pip install "tecladoia[imagenes]"'
        )
    from PIL import Image, ImageSequence

    return Image, ImageSequence


def a_rgb565(imagen, orden_bytes: str = "big") -> bytes:
    """Pasa una imagen ya del tamaño correcto a RGB565.

    El byte alto va primero. No es un capricho: el codificador del fabricante se
    llama literalmente ``toRgb565BigEndian``, y con el orden contrario la pantalla
    enseña los colores cambiados —el rojo sale azulado— aunque la imagen se vea
    por lo demás bien.
    """
    puntos = imagen.convert("RGB").tobytes()
    salida = bytearray(len(puntos) // 3 * 2)
    for indice in range(0, len(puntos), 3):
        rojo, verde, azul = puntos[indice], puntos[indice + 1], puntos[indice + 2]
        valor = ((rojo & 0xF8) << 8) | ((verde & 0xFC) << 3) | (azul >> 3)
        destino = indice // 3 * 2
        if orden_bytes == "little":
            salida[destino] = valor & 0xFF
            salida[destino + 1] = valor >> 8
        else:
            salida[destino] = valor >> 8
            salida[destino + 1] = valor & 0xFF
    return bytes(salida)


def _encajar(imagen, Image) -> "Image.Image":
    """Recorta y escala hasta 160 × 80 sin deformar lo que se ve.

    Se prefiere recortar antes que estirar: una cara achatada se nota mucho más
    que unos bordes de menos.
    """
    ancho, alto = imagen.size
    if ancho == OLED_ANCHO and alto == OLED_ALTO:
        return imagen.convert("RGB")

    proporcion_destino = OLED_ANCHO / OLED_ALTO
    proporcion = ancho / alto
    if proporcion > proporcion_destino:  # demasiado ancha: se recortan los lados
        nuevo_ancho = int(alto * proporcion_destino)
        margen = (ancho - nuevo_ancho) // 2
        imagen = imagen.crop((margen, 0, margen + nuevo_ancho, alto))
    elif proporcion < proporcion_destino:  # demasiado alta: se recorta arriba y abajo
        nuevo_alto = int(ancho / proporcion_destino)
        margen = (alto - nuevo_alto) // 2
        imagen = imagen.crop((0, margen, ancho, margen + nuevo_alto))
    return imagen.convert("RGB").resize((OLED_ANCHO, OLED_ALTO), Image.LANCZOS)


def fotogramas(
    datos: bytes,
    maximo: int = MAXIMO_FOTOGRAMAS_POR_MODO,
    orden_bytes: str = "big",
) -> tuple[list[bytes], int]:
    """Convierte el archivo en fotogramas listos para el teclado.

    Devuelve la lista de fotogramas en RGB565 y el retardo entre ellos en
    milisegundos, tomado del propio GIF cuando lo trae.
    """
    if not datos:
        raise ErrorImagen("El archivo está vacío.")
    if len(datos) > MAXIMO_BYTES_ARCHIVO:
        raise ErrorImagen(
            f"El archivo pesa {len(datos) // 1024} KB y el máximo son "
            f"{MAXIMO_BYTES_ARCHIVO // 1024} KB."
        )

    Image, ImageSequence = _exigir_pillow()
    try:
        original = Image.open(io.BytesIO(datos))
    except Exception as error:  # noqa: BLE001 - Pillow lanza de todo
        raise ErrorImagen(f"No se pudo leer la imagen: {error}") from error

    maximo = max(1, min(int(maximo), OLED_MAXIMO_FOTOGRAMAS))

    crudos = []
    retardo = 0
    for cuadro in ImageSequence.Iterator(original):
        retardo = retardo or int(cuadro.info.get("duration", 0) or 0)
        crudos.append(cuadro.copy())

    # Si el GIF trae más fotogramas de los que caben, se reparten en vez de
    # cortarlo por la mitad: se toman a intervalos regulares y se alarga el
    # retardo, así la animación se ve entera aunque con menos detalle.
    if len(crudos) > maximo:
        paso = len(crudos) / maximo
        indices = [int(i * paso) for i in range(maximo)]
        retardo = int(retardo * paso) if retardo else 0
        crudos = [crudos[i] for i in indices]

    convertidos = [a_rgb565(_encajar(c, Image), orden_bytes) for c in crudos]

    if not convertidos:
        raise ErrorImagen("El archivo no tiene ningún fotograma utilizable.")
    for cuadro in convertidos:
        if len(cuadro) != OLED_BYTES_POR_FOTOGRAMA:
            raise ErrorImagen("Un fotograma no salió del tamaño esperado.")
    return convertidos, retardo or 100


def bloques(fotograma: bytes, tamano: int = 4096) -> Iterator[bytes]:
    """Trocea un fotograma en bloques para la memoria flash.

    Se manda exactamente lo que ocupa el fotograma, sin rellenar: el último
    bloque sale más corto —1 024 bytes— y el firmware lo espera así. La ranura
    reservada es mayor, pero el resto no se escribe.
    """
    for inicio in range(0, len(fotograma), tamano):
        yield fotograma[inicio:inicio + tamano]


def resumen(datos: bytes) -> dict:
    """Datos del archivo para enseñarlos antes de enviarlo."""
    cuadros, retardo = fotogramas(datos)
    return {
        "fotogramas": len(cuadros),
        "retardo_ms": retardo,
        "bytes_origen": len(datos),
        "bytes_en_teclado": len(cuadros) * OLED_TAMANO_RANURA,
    }


__all__ = [
    "ErrorImagen",
    "MAXIMO_BYTES_ARCHIVO",
    "MAXIMO_FOTOGRAMAS_POR_MODO",
    "a_rgb565",
    "bloques",
    "fotogramas",
    "hay_pillow",
    "resumen",
]
