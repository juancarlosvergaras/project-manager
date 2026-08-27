"""Modelo de dominio: estados del agente, efectos de luz y decisiones."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional


class EstadoIA(IntEnum):
    """Momento del ciclo de vida de un agente de IA.

    El valor numerico es el que entiende el firmware en el comando 0x90; no se
    puede cambiar sin romper la compatibilidad con el teclado.
    """

    NOTIFICACION = 0
    ESPERANDO_APROBACION = 1
    HERRAMIENTA_TERMINADA = 2
    HERRAMIENTA_EN_CURSO = 3
    SESION_INICIADA = 4
    DETENIDO = 5
    TAREA_COMPLETADA = 6
    PETICION_ENVIADA = 7
    SESION_FINALIZADA = 8

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_ESTADO[self]

    @property
    def descripcion(self) -> str:
        return _DESCRIPCIONES_ESTADO[self]

    @classmethod
    def desde_codigo(cls, codigo: int) -> "EstadoIA":
        try:
            return cls(int(codigo))
        except ValueError:
            return cls.NOTIFICACION


_ETIQUETAS_ESTADO = {
    EstadoIA.NOTIFICACION: "Aviso",
    EstadoIA.ESPERANDO_APROBACION: "Esperando aprobación",
    EstadoIA.HERRAMIENTA_TERMINADA: "Herramienta terminada",
    EstadoIA.HERRAMIENTA_EN_CURSO: "Herramienta en curso",
    EstadoIA.SESION_INICIADA: "Sesión iniciada",
    EstadoIA.DETENIDO: "Detenido",
    EstadoIA.TAREA_COMPLETADA: "Tarea completada",
    EstadoIA.PETICION_ENVIADA: "Petición enviada",
    EstadoIA.SESION_FINALIZADA: "Sesión finalizada",
}

_DESCRIPCIONES_ESTADO = {
    EstadoIA.NOTIFICACION: "Aviso o cambio de estado sin acción pendiente.",
    EstadoIA.ESPERANDO_APROBACION: "El agente necesita tu confirmación para continuar.",
    EstadoIA.HERRAMIENTA_TERMINADA: "Terminó una llamada a herramienta.",
    EstadoIA.HERRAMIENTA_EN_CURSO: "El agente está ejecutando una herramienta.",
    EstadoIA.SESION_INICIADA: "Acaba de arrancar una sesión del agente.",
    EstadoIA.DETENIDO: "El agente dejó de responder y espera instrucciones.",
    EstadoIA.TAREA_COMPLETADA: "La tarea en curso terminó.",
    EstadoIA.PETICION_ENVIADA: "Enviaste una petición al agente.",
    EstadoIA.SESION_FINALIZADA: "La sesión se cerró.",
}


class EfectoLuz(IntEnum):
    """Efectos de la barra LED (comando 0x91)."""

    APAGADO = 0x00
    PUNTO_MOVIL = 0x01
    ARCOIRIS_MOVIL = 0x02
    ONDA_ARCOIRIS = 0x03
    ONDA_ARCOIRIS_LENTA = 0x04
    RESPIRACION = 0x05
    CENTRO_FIJO = 0x06
    ONDA_AL_ESCRIBIR = 0x07
    COMETA = 0x08
    BARRIDO = 0x09
    PULSO_CENTRAL = 0x0A
    PARPADEO_AVISO = 0x0B
    BARRIDO_DE_EXITO = 0x0C
    PENSAMIENTO_AZUL = 0x0D
    BATERIA_BAJA = 0x0E
    CARGANDO = 0x0F
    ESPERA_DE_APROBACION = 0x10

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_EFECTO[self]

    @property
    def color(self) -> str:
        """El color que enseña, cuando se sabe.

        El firmware no deja elegirlo: solo viaja un byte con el número del
        efecto y el color va cocido dentro. Así que «elegir color» se reduce a
        elegir el efecto que lo tiene, y para eso hay que saber cuál es cuál.
        De los que el fabricante no nombra por su color no se dice nada, antes
        que inventarlo.
        """
        return _COLORES_EFECTO.get(self, "")


_ETIQUETAS_EFECTO = {
    EfectoLuz.APAGADO: "Apagado",
    EfectoLuz.PUNTO_MOVIL: "Punto en movimiento",
    EfectoLuz.ARCOIRIS_MOVIL: "Arcoíris en movimiento",
    EfectoLuz.ONDA_ARCOIRIS: "Onda de arcoíris",
    EfectoLuz.ONDA_ARCOIRIS_LENTA: "Onda de arcoíris lenta",
    EfectoLuz.RESPIRACION: "Respiración",
    EfectoLuz.CENTRO_FIJO: "Centro fijo",
    EfectoLuz.ONDA_AL_ESCRIBIR: "Onda al escribir",
    EfectoLuz.COMETA: "Cometa",
    EfectoLuz.BARRIDO: "Barrido",
    EfectoLuz.PULSO_CENTRAL: "Pulso central",
    EfectoLuz.PARPADEO_AVISO: "Parpadeo de aviso",
    EfectoLuz.BARRIDO_DE_EXITO: "Barrido de éxito",
    EfectoLuz.PENSAMIENTO_AZUL: "Pensamiento azul",
    EfectoLuz.BATERIA_BAJA: "Batería baja",
    EfectoLuz.CARGANDO: "Cargando",
    EfectoLuz.ESPERA_DE_APROBACION: "Espera de aprobación",
}

#: Lo poco que se sabe con certeza del color de cada efecto.
_COLORES_EFECTO: dict["EfectoLuz", str] = {}


#: Efecto que se enciende por defecto en cada estado del agente.
EFECTO_POR_ESTADO: dict[EstadoIA, EfectoLuz] = {
    EstadoIA.NOTIFICACION: EfectoLuz.PARPADEO_AVISO,
    EstadoIA.ESPERANDO_APROBACION: EfectoLuz.ESPERA_DE_APROBACION,
    EstadoIA.HERRAMIENTA_TERMINADA: EfectoLuz.PUNTO_MOVIL,
    EstadoIA.HERRAMIENTA_EN_CURSO: EfectoLuz.PENSAMIENTO_AZUL,
    EstadoIA.SESION_INICIADA: EfectoLuz.BARRIDO,
    EstadoIA.DETENIDO: EfectoLuz.CENTRO_FIJO,
    EstadoIA.TAREA_COMPLETADA: EfectoLuz.BARRIDO_DE_EXITO,
    EstadoIA.PETICION_ENVIADA: EfectoLuz.ONDA_AL_ESCRIBIR,
    EstadoIA.SESION_FINALIZADA: EfectoLuz.APAGADO,
}


class Decision(str, Enum):
    """Resultado del motor de aprobacion."""

    PERMITIR = "permitir"
    PREGUNTAR = "preguntar"
    DENEGAR = "denegar"


class MotivoDecision(str, Enum):
    """Por que se tomo la decision. Se guarda en la bitacora de auditoria."""

    PALANCA_AUTOMATICA = "palanca_automatica"
    PALANCA_MANUAL = "palanca_manual"
    SIN_LECTURA_DE_PALANCA = "sin_lectura_de_palanca"
    SIN_CONEXION = "sin_conexion"
    REGLA_PERMITIR = "regla_permitir"
    REGLA_PREGUNTAR = "regla_preguntar"
    REGLA_DENEGAR = "regla_denegar"
    MODO_FORZADO = "modo_forzado"
    APROBADA_EN_LA_WEB = "aprobada_en_la_web"
    DENEGADA_EN_LA_WEB = "denegada_en_la_web"
    SIN_RESPUESTA_EN_LA_WEB = "sin_respuesta_en_la_web"

    @property
    def explicacion(self) -> str:
        return _EXPLICACIONES_MOTIVO[self]


_EXPLICACIONES_MOTIVO = {
    MotivoDecision.PALANCA_AUTOMATICA: "La palanca está en automático.",
    MotivoDecision.PALANCA_MANUAL: "La palanca está en manual: decides tú.",
    MotivoDecision.SIN_LECTURA_DE_PALANCA: (
        "No se pudo leer la palanca, así que se devuelve el control a la persona."
    ),
    MotivoDecision.SIN_CONEXION: (
        "El teclado no está conectado, así que se devuelve el control a la persona."
    ),
    MotivoDecision.REGLA_PERMITIR: "Una regla de la configuración permite esta acción.",
    MotivoDecision.REGLA_PREGUNTAR: "Una regla de la configuración exige confirmación.",
    MotivoDecision.REGLA_DENEGAR: "Una regla de la configuración bloquea esta acción.",
    MotivoDecision.MODO_FORZADO: "El modo de aprobación está fijado desde la configuración.",
    MotivoDecision.APROBADA_EN_LA_WEB: "Alguien lo aprobó desde el panel web.",
    MotivoDecision.DENEGADA_EN_LA_WEB: "Alguien lo denegó desde el panel web.",
    MotivoDecision.SIN_RESPUESTA_EN_LA_WEB: (
        "Nadie contestó en el panel dentro del plazo, así que decides tú."
    ),
}


@dataclass(frozen=True)
class Veredicto:
    """Decision tomada para una peticion concreta, con su justificacion."""

    decision: Decision
    motivo: MotivoDecision
    palanca: Optional[int] = None
    regla: Optional[str] = None

    @property
    def automatica(self) -> bool:
        return self.decision is Decision.PERMITIR

    @property
    def explicacion(self) -> str:
        base = self.motivo.explicacion
        return f"{base} (regla: {self.regla})" if self.regla else base


@dataclass
class Contexto:
    """Datos que el agente de IA envia junto con el evento."""

    agente: str = "desconocido"
    evento: str = ""
    herramienta: Optional[str] = None
    comando: Optional[str] = None
    ruta: Optional[str] = None
    sesion: Optional[str] = None

    def resumen(self) -> str:
        piezas = [self.agente, self.evento]
        if self.herramienta:
            piezas.append(self.herramienta)
        if self.comando:
            piezas.append(self.comando[:80])
        return " · ".join(p for p in piezas if p)


@dataclass
class Tecla:
    """Una de las cuatro teclas programables de un modo."""

    atajo: str = ""
    descripcion: str = ""
    macro: list[tuple[int, int]] = field(default_factory=list)

    def esta_vacia(self) -> bool:
        return not self.atajo and not self.macro


@dataclass
class Modo:
    """Uno de los cuatro modos de trabajo del teclado.

    Cada modo es un puesto de trabajo independiente: sus cuatro teclas, su
    pantalla, su dueño y sus luces. Que tenga dueño es lo que permite que el
    teclado no mezcle: si estás en el modo de ChatGPT, lo que haga Claude Code
    por detrás no debe encenderte la barra, porque no es lo que estás mirando.
    """

    nombre: str = ""
    #: Qué programa manda en este modo: «claude», «chatgpt», «cursor», «codex»…
    #: Vacío significa que el modo es libre y lo mueve cualquiera.
    agente: str = ""
    teclas: list[Tecla] = field(default_factory=lambda: [Tecla() for _ in range(4)])
    #: Efecto por cada momento del agente, solo para este modo. Vacío = se usa
    #: la tabla general de los ajustes.
    luces: dict[str, int] = field(default_factory=dict)
    #: Nombre del programa que hay que traer al frente al pulsar el micrófono.
    programa: str = ""
    #: Cómo abrirlo si no está corriendo. En Windows, lo normal es
    #: «shell:appsFolder\...» para las aplicaciones de la Tienda.
    lanzar: str = ""
