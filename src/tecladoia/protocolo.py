"""Protocolo binario del teclado AhaKey-X1.

Todas las tramas viajan con el formato::

    [0xAA 0xBB] [comando:1] [datos:N] [0xCC 0xDD]

Este modulo no habla con el hardware: solo construye y analiza bytes, de modo
que se puede probar por completo sin tener el teclado conectado.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Optional

CABECERA = b"\xAA\xBB"
COLA = b"\xCC\xDD"

# --- Servicios y caracteristicas BLE -----------------------------------------
SERVICIO_PRINCIPAL = "00007340-0000-1000-8000-00805f9b34fb"
CARACTERISTICA_DATOS = "00007341-0000-1000-8000-00805f9b34fb"
CARACTERISTICA_INFO = "00007342-0000-1000-8000-00805f9b34fb"
CARACTERISTICA_COMANDO = "00007343-0000-1000-8000-00805f9b34fb"
CARACTERISTICA_NOTIFICA = "00007344-0000-1000-8000-00805f9b34fb"

SERVICIO_BATERIA = "0000180f-0000-1000-8000-00805f9b34fb"
CARACTERISTICA_BATERIA = "00002a19-0000-1000-8000-00805f9b34fb"

# --- Pantalla OLED ------------------------------------------------------------
OLED_ANCHO = 160
OLED_ALTO = 80
OLED_BYTES_POR_FOTOGRAMA = OLED_ANCHO * OLED_ALTO * 2  # RGB565
OLED_TAMANO_RANURA = 28_672
OLED_MAXIMO_FOTOGRAMAS = 292
OLED_TAMANO_BLOQUE = 4096
OLED_TAMANO_PAQUETE = 180

#: Ranuras de imagen que el firmware se reserva. Son las que trae el teclado de
#: serie y escribir ahí se lleva por delante sus pantallas de fábrica.
OLED_RANURAS_DE_FABRICA = 10

MODOS_DISPONIBLES = 4
TECLAS_POR_MODO = 4
MAXIMO_BYTES_DESCRIPCION = 20
MAXIMO_BYTES_NOMBRE = 21

#: Fotogramas que le tocan a cada modo: lo que queda tras las de fábrica,
#: repartido a partes iguales. Con 292 en total y cuatro modos, salen 70.
RANURAS_POR_MODO = (OLED_MAXIMO_FOTOGRAMAS - OLED_RANURAS_DE_FABRICA) // MODOS_DISPONIBLES


def ranura_inicial(modo: int) -> int:
    """Primera ranura de imagen que le corresponde a un modo."""
    return OLED_RANURAS_DE_FABRICA + int(modo) * RANURAS_POR_MODO


class Comando(IntEnum):
    """Codigos de comando aceptados por el firmware."""

    CONSULTAR_ESTADO = 0x00
    CAMBIAR_NOMBRE = 0x01
    CAMBIAR_APARIENCIA = 0x02
    GUARDAR_CONFIG = 0x04
    ACTUALIZAR_TECLA = 0x73
    PREPARAR_ESCRITURA = 0x80
    RESULTADO_ESCRITURA = 0x81
    ACTUALIZAR_IMAGEN = 0x82
    LEER_ESTADO_IMAGEN = 0x83
    CONFIG_LUZ_IA = 0x84
    BRILLO_LUZ = 0x85
    ACTUALIZAR_ESTADO = 0x90
    EFECTO_LUZ = 0x91
    MODO_TRABAJO = 0x92


class SubTipoTecla(IntEnum):
    """Sub-tipo del comando ``ACTUALIZAR_TECLA``."""

    ATAJO = 0x73
    MACRO = 0x74
    DESCRIPCION = 0x75


class AccionMacro(IntEnum):
    """Acciones admitidas dentro de una macro."""

    NADA = 0
    PULSAR = 1
    SOLTAR = 2
    ESPERAR = 3
    SOLTAR_TODO = 4


class ErrorProtocolo(ValueError):
    """Se lanza cuando una trama no cumple el formato esperado."""


@dataclass(frozen=True)
class EstadoDispositivo:
    """Respuesta de ``CONSULTAR_ESTADO`` ya interpretada."""

    bateria: int
    senal: int
    firmware_mayor: int
    firmware_menor: int
    modo_trabajo: int
    modo_luz: int
    palanca: int
    brillo: Optional[int] = None

    @property
    def firmware(self) -> str:
        return f"{self.firmware_mayor}.{self.firmware_menor}"

    @property
    def aprobacion_automatica(self) -> bool:
        """La palanca en 0 (reposo) es el unico valor que aprueba solo.

        Cualquier otro valor -y tambien la ausencia de lectura- deja la
        decision en manos de la persona. Es la misma regla a prueba de fallos
        del proyecto original.
        """
        return self.palanca == 0


def construir_trama(comando: int, datos: bytes = b"") -> bytes:
    """Envuelve ``datos`` con la cabecera, el comando y la cola."""
    if not 0 <= int(comando) <= 0xFF:
        raise ErrorProtocolo(f"Comando fuera de rango: {comando!r}")
    return CABECERA + bytes([int(comando)]) + bytes(datos) + COLA


def es_trama_valida(datos: bytes) -> bool:
    """Comprueba cabecera, cola y longitud minima."""
    return (
        len(datos) >= 5
        and datos[:2] == CABECERA
        and datos[-2:] == COLA
    )


def carga_util(datos: bytes) -> bytes:
    """Devuelve los bytes de datos de una trama (sin comando ni delimitadores)."""
    if not es_trama_valida(datos):
        raise ErrorProtocolo("Trama invalida: no coincide la cabecera o la cola")
    return datos[3:-2]


def comando_de(datos: bytes) -> int:
    if not es_trama_valida(datos):
        raise ErrorProtocolo("Trama invalida: no coincide la cabecera o la cola")
    return datos[2]


# --- Constructores de comandos ------------------------------------------------

def consultar_estado() -> bytes:
    return construir_trama(Comando.CONSULTAR_ESTADO)


def guardar_config() -> bytes:
    return construir_trama(Comando.GUARDAR_CONFIG)


def actualizar_estado(estado: int) -> bytes:
    """Empuja el estado del agente de IA a la barra LED (comando 0x90)."""
    return construir_trama(Comando.ACTUALIZAR_ESTADO, bytes([int(estado) & 0xFF]))


def efecto_luz(codigo: int) -> bytes:
    return construir_trama(Comando.EFECTO_LUZ, bytes([int(codigo) & 0xFF]))


def brillo_luz(valor: int) -> bytes:
    return construir_trama(Comando.BRILLO_LUZ, bytes([max(1, min(100, int(valor)))]))


def modo_trabajo(modo: int) -> bytes:
    return construir_trama(Comando.MODO_TRABAJO, bytes([max(0, min(3, int(modo)))]))


def config_luz_ia(modo: int, codigos: Iterable[int]) -> bytes:
    cuerpo = bytes([int(modo) & 0xFF]) + bytes(int(c) & 0xFF for c in codigos)
    return construir_trama(Comando.CONFIG_LUZ_IA, cuerpo)


def cambiar_nombre(nombre: str) -> bytes:
    crudo = nombre.encode("utf-8")[:MAXIMO_BYTES_NOMBRE]
    return construir_trama(Comando.CAMBIAR_NOMBRE, crudo)


def cambiar_apariencia(apariencia: int) -> bytes:
    return construir_trama(Comando.CAMBIAR_APARIENCIA, bytes([int(apariencia) & 0xFF]))


def _validar_ranura(modo: int, indice_tecla: int) -> None:
    if not 0 <= modo < MODOS_DISPONIBLES:
        raise ErrorProtocolo(f"Modo fuera de rango (0-{MODOS_DISPONIBLES - 1}): {modo}")
    if not 0 <= indice_tecla < TECLAS_POR_MODO:
        raise ErrorProtocolo(
            f"Tecla fuera de rango (0-{TECLAS_POR_MODO - 1}): {indice_tecla}"
        )


def asignar_atajo(modo: int, indice_tecla: int, codigos_hid: Iterable[int]) -> bytes:
    """Asigna una combinacion de teclas HID (modificadores primero)."""
    _validar_ranura(modo, indice_tecla)
    cuerpo = bytes(int(c) & 0xFF for c in codigos_hid)
    if len(cuerpo) > 98:
        raise ErrorProtocolo("Un atajo admite como maximo 98 codigos HID")
    return construir_trama(
        Comando.ACTUALIZAR_TECLA,
        bytes([SubTipoTecla.ATAJO, modo, indice_tecla]) + cuerpo,
    )


def asignar_macro(modo: int, indice_tecla: int, pasos: Iterable[tuple[int, int]]) -> bytes:
    """Asigna una macro como lista de pares ``(accion, parametro)``."""
    _validar_ranura(modo, indice_tecla)
    cuerpo = bytearray()
    for accion, parametro in pasos:
        cuerpo.append(int(accion) & 0xFF)
        cuerpo.append(int(parametro) & 0xFF)
    if len(cuerpo) > 98:
        raise ErrorProtocolo("Una macro admite como maximo 49 pasos")
    return construir_trama(
        Comando.ACTUALIZAR_TECLA,
        bytes([SubTipoTecla.MACRO, modo, indice_tecla]) + bytes(cuerpo),
    )


def normalizar_descripcion(texto: str, maximo: int = MAXIMO_BYTES_DESCRIPCION) -> str:
    """Deja el texto en ASCII imprimible, que es lo unico que dibuja el OLED.

    Las tildes y la enye se transliteran en lugar de perderse, para que una
    descripcion en espanol siga siendo legible en la pantalla del teclado.
    """
    equivalencias = str.maketrans(
        "áéíóúÁÉÍÓÚàèìòùÀÈÌÒÙäëïöüÄËÏÖÜñÑçÇ¿¡ºª",
        "aeiouAEIOUaeiouAEIOUaeiouAEIOUnNcC?!oa",
    )
    limpio = texto.translate(equivalencias)
    return "".join(c for c in limpio if 0x20 <= ord(c) <= 0x7E)[:maximo]


def asignar_descripcion(modo: int, indice_tecla: int, texto: str) -> bytes:
    """Escribe la etiqueta que el teclado muestra en su pantalla OLED."""
    _validar_ranura(modo, indice_tecla)
    crudo = normalizar_descripcion(texto).encode("ascii")
    return construir_trama(
        Comando.ACTUALIZAR_TECLA,
        bytes([SubTipoTecla.DESCRIPCION, modo, indice_tecla]) + crudo,
    )


def preparar_escritura(longitud_bloque: int, direccion: int) -> bytes:
    """Prepara una escritura masiva en la memoria flash (imagenes OLED)."""
    if direccion % 4096:
        raise ErrorProtocolo("La direccion debe estar alineada a 4 KiB")
    cuerpo = bytes([0]) + int(longitud_bloque).to_bytes(2, "little") + int(direccion).to_bytes(4, "little")
    return construir_trama(Comando.PREPARAR_ESCRITURA, cuerpo)


def actualizar_imagen(modo: int, indice_inicial: int, fotogramas: int, retardo_ms: int) -> bytes:
    cuerpo = (
        bytes([int(modo) & 0xFF])
        + int(indice_inicial).to_bytes(2, "little")
        + int(fotogramas).to_bytes(2, "little")
        + int(retardo_ms).to_bytes(2, "little")
    )
    return construir_trama(Comando.ACTUALIZAR_IMAGEN, cuerpo)


def leer_estado_imagen(modo: int) -> bytes:
    return construir_trama(Comando.LEER_ESTADO_IMAGEN, bytes([int(modo) & 0xFF]))


# --- Analisis de respuestas ---------------------------------------------------

def analizar_estado(datos: bytes) -> Optional[EstadoDispositivo]:
    """Interpreta la respuesta de ``CONSULTAR_ESTADO``.

    Devuelve ``None`` -en lugar de fallar- cuando la trama es un aviso de otro
    comando: el firmware reenvia acuses de ``ACTUALIZAR_ESTADO`` por el mismo
    canal y su segundo byte no es la posicion de la palanca. Tomarlos por buenos
    sobrescribiria la palanca con un valor inventado, que es justo el fallo que
    el codigo original documenta.
    """
    if not es_trama_valida(datos):
        return None
    if datos[2] != Comando.CONSULTAR_ESTADO:
        return None
    # La consulta de estado es la excepcion del formato general: tras el eco
    # del comando ya empiezan los datos, sin byte de estado intermedio.
    cuerpo = datos[3:-2]
    if len(cuerpo) < 7:
        return None
    return EstadoDispositivo(
        bateria=cuerpo[0],
        senal=cuerpo[1],
        firmware_mayor=cuerpo[2],
        firmware_menor=cuerpo[3],
        modo_trabajo=cuerpo[4],
        modo_luz=cuerpo[5],
        palanca=cuerpo[6],
        brillo=cuerpo[7] if len(cuerpo) > 7 else None,
    )


def analizar_estado_imagen(datos: bytes) -> Optional[dict]:
    """Interpreta la respuesta de ``LEER_ESTADO_IMAGEN``."""
    if not es_trama_valida(datos) or datos[2] != Comando.LEER_ESTADO_IMAGEN:
        return None
    cuerpo = datos[4:-2]
    if len(cuerpo) < 9:
        return None
    return {
        "modo": cuerpo[0],
        "indice_inicial": int.from_bytes(cuerpo[1:3], "little"),
        "fotogramas": int.from_bytes(cuerpo[3:5], "little"),
        "intervalo_ms": int.from_bytes(cuerpo[5:7], "little"),
        "maximo_global": int.from_bytes(cuerpo[7:9], "little"),
    }


def separar_tramas(memoria: bytearray) -> list[bytes]:
    """Extrae de ``memoria`` todas las tramas completas y consume esos bytes.

    El transporte BLE entrega notificaciones sueltas que pueden partir o unir
    tramas; este separador las reconstruye y descarta la basura anterior a la
    primera cabecera valida.
    """
    tramas: list[bytes] = []
    while True:
        inicio = memoria.find(CABECERA)
        if inicio < 0:
            memoria.clear()
            return tramas
        if inicio:
            del memoria[:inicio]
        fin = memoria.find(COLA, 3)
        if fin < 0:
            return tramas
        tramas.append(bytes(memoria[: fin + 2]))
        del memoria[: fin + 2]
