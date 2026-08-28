"""Rutas, ajustes persistentes y preferencias de accesibilidad."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

NOMBRE_APP = "tecladoia"

#: Puerto TCP del servidor de enganches (respaldo en Windows y en redes locales).
PUERTO_PREDETERMINADO = 8765
#: Puerto del panel web en español.
PUERTO_PANEL = 8770


def directorio_base() -> Path:
    """Carpeta donde viven configuración, bitácoras y enganches generados."""
    if entorno := os.environ.get("TECLADOIA_INICIO"):
        return Path(entorno).expanduser()
    if os.name == "nt":
        raiz = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return raiz / "TecladoIA"
    return Path.home() / ".tecladoia"


def ruta_config() -> Path:
    return directorio_base() / "config.json"


def ruta_bitacora() -> Path:
    return directorio_base() / "bitacora.jsonl"


def ruta_enganches() -> Path:
    return directorio_base() / "enganches"


def ruta_socket() -> Path:
    """Socket de dominio Unix que atienden los enganches.

    En Windows no existen los sockets Unix, así que el servidor se queda solo
    con el puerto TCP; esta ruta se sigue devolviendo para los mensajes de
    diagnóstico.
    """
    if entorno := os.environ.get("TECLADOIA_SOCKET"):
        return Path(entorno)
    return Path(os.environ.get("TMPDIR", "/tmp")) / "tecladoia.sock"


@dataclass
class Regla:
    """Regla que decide antes de mirar la palanca.

    ``patron`` se compara -sin distinguir mayúsculas- contra el nombre de la
    herramienta y contra el comando que el agente quiere ejecutar.
    """

    patron: str
    decision: str = "preguntar"  # permitir | preguntar | denegar
    nota: str = ""
    agente: str = "*"


def _reglas_iniciales() -> list[Regla]:
    """Reglas de arranque: rápidas para lo inocuo, prudentes con lo destructivo."""
    return [
        Regla("rm -rf", "denegar", "Borrado recursivo forzado."),
        Regla("mkfs", "denegar", "Formateo de disco."),
        Regla("dd if=", "denegar", "Escritura directa sobre un dispositivo."),
        Regla(":(){", "denegar", "Bomba de bifurcación."),
        Regla("git push --force", "preguntar", "Reescribe historia remota."),
        Regla("git reset --hard", "preguntar", "Descarta cambios sin copia."),
        Regla("sudo ", "preguntar", "Eleva privilegios."),
        Regla("curl ", "preguntar", "Descarga desde la red."),
        Regla("npm publish", "preguntar", "Publica un paquete."),
    ]


#: Los cuatro modos del teclado con el nombre que les da el usuario. El
#: fabricante trae Claude/Cursor/Codex; este reparto es el de esta casa.
NOMBRES_DE_MODO = ("Claude", "ChatGPT", "Cursor", "Modo 4")

#: Qué programa manda en cada modo. El cuarto queda libre a propósito.
DUENOS_DE_MODO = ("claude", "chatgpt", "cursor", "")

#: Programa que se trae al frente al pulsar el micrófono, y cómo abrirlo si no
#: está. Los nombres son los del ejecutable, sin «.exe».
PROGRAMAS_DE_MODO = (
    ("claude", r"shell:appsFolder\Claude_pzs8sxrjxfjjc!Claude"),
    ("ChatGPT", r"shell:appsFolder\OpenAI.Codex_2p2nqsd0c76g0!App"),
    ("Cursor", ""),
    ("", ""),
)


def _modos_iniciales() -> list["Modo"]:
    """Los cuatro modos vacíos, con su nombre."""
    from .modelo import Modo, Tecla

    return [
        Modo(
            nombre=nombre,
            agente=dueno,
            programa=programa,
            lanzar=lanzar,
            teclas=[Tecla() for _ in range(4)],
        )
        for nombre, dueno, (programa, lanzar) in zip(
            NOMBRES_DE_MODO, DUENOS_DE_MODO, PROGRAMAS_DE_MODO
        )
    ]


def _luces_iniciales() -> dict[str, int]:
    """Qué efecto enciende cada momento del agente.

    La barra no es un adorno que se elige una vez: es lo que te dice, sin mirar
    la pantalla, si el agente piensa, si terminó o si te está esperando. Por eso
    el efecto va atado al estado, no al gusto del día.
    """
    from .modelo import EFECTO_POR_ESTADO

    return {str(int(estado)): int(efecto) for estado, efecto in EFECTO_POR_ESTADO.items()}


def _aplicaciones_iniciales() -> list[dict]:
    """Qué modo del teclado le toca a cada programa.

    Gana la primera regla que coincida. El patrón se busca en el nombre del
    programa; mirar además el título hay que pedirlo con ``en``, porque los
    títulos cambian solos y disparan cambios de modo que nadie pidió.
    """
    return [
        {"patron": "chatgpt", "modo": 1, "en": "proceso"},
        {"patron": "cursor", "modo": 2, "en": "proceso"},
        {"patron": "claude", "modo": 0, "en": "proceso"},
    ]


@dataclass
class Ajustes:
    """Configuración completa de la aplicación."""

    idioma: str = "es"
    accesible: bool = False
    modo_aprobacion: str = "palanca"  # palanca | siempre_preguntar | siempre_permitir
    transporte: str = "auto"  # auto | ble | puente | simulado
    nombre_dispositivo: str = ""
    #: Dirección Bluetooth del teclado. Cuando está puesta se usa
    #: directamente, sin rastrear: un teclado ya emparejado deja de
    #: anunciarse y una búsqueda no lo encontraría.
    direccion_dispositivo: str = ""
    puerto_hooks: int = PUERTO_PREDETERMINADO
    puerto_panel: int = PUERTO_PANEL
    #: Interfaz donde escucha el panel. Fuera de la máquina local exige clave.
    host_panel: str = "127.0.0.1"
    #: Clave del panel. Vacía solo es aceptable escuchando en local.
    clave_panel: str = ""
    puente_host: str = "127.0.0.1"
    puente_puerto: int = 9000
    vigencia_cache_ms: int = 1500
    #: Segundos sin recibir eventos tras los cuales la barra vuelve al reposo.
    #: Evita que la última animación se quede encendida para siempre cuando el
    #: agente se cierra sin avisar o cambias de ventana.
    segundos_hasta_reposo: int = 45
    #: Cuánto dura en pantalla un estado momentáneo antes de volver al reposo.
    milisegundos_estado_breve: int = 1500
    espera_palanca_s: float = 1.2
    #: Si es cierto, las reglas de tipo «permitir» pueden adelantar una acción
    #: con la palanca en manual. Viene apagado: la palanca manda.
    reglas_permisivas: bool = False
    sincronizar_config_agentes: bool = True
    avisar_en_escritorio: bool = True
    brillo: int = 35
    #: Si es cierto, lo que quede en «preguntar» se publica en el panel y se
    #: puede contestar desde el navegador. Si nadie contesta a tiempo, se
    #: responde «preguntar»: activarlo no permite nada por sí solo.
    aprobacion_remota: bool = False
    espera_aprobacion_s: float = 25.0
    #: Cada cuánto se le pregunta al teclado por su estado. Es lo que hace que
    #: mover la palanca con la mano se note al momento.
    intervalo_sondeo_s: float = 2.0
    #: El teclado cambia de modo al cambiar tú de aplicación.
    #:
    #: Viene APAGADO a propósito. La idea es buena —los programas de escritorio
    #: no avisan de nada, así que mirar cuál tienes delante es la única pista—
    #: pero en la práctica pelea con quien elige un modo a mano: pulsas el
    #: micrófono en el modo de ChatGPT, vuelves a la ventana de Claude para
    #: seguir trabajando, y el teclado se va al modo de Claude. Desde fuera
    #: parece que el micrófono cambia de modo solo.
    #:
    #: Se enciende desde Ajustes cuando se quiere ese automatismo.
    seguir_aplicacion: bool = False
    #: Leerle a ChatGPT el estado por la capa de accesibilidad. Es la única vía
    #: que hay: ChatGPT no tiene enganches. Se puede apagar si molesta.
    vigilar_chatgpt: bool = True
    #: Modo en el que dejar el teclado cada vez que se conecta (0-3), o
    #: ``None`` para respetar el que traiga.
    #:
    #: El teclado recuerda por su cuenta el último modo que tuvo y vuelve a él
    #: al encenderse, que no siempre es el que uno quiere empezar. Esto lo
    #: corrige desde fuera: en cuanto se engancha, se le pone el modo elegido.
    modo_al_conectar: Optional[int] = None
    #: Segundos sin noticias tras los que la barra vuelve al reposo. Sin esto se
    #: queda encendida con lo último que pasó aunque hayas cambiado de programa.
    segundos_reposo: float = 25.0
    efecto_reposo: int = 0
    #: La tecla del micrófono trae al frente el programa del modo y abre el
    #: dictado dentro de él. Apagarlo la deja mandando la combinación a secas.
    dictado_asistido: bool = True
    #: Antes de abrir el dictado se hace clic en el cuadro de escribir. Sin eso,
    #: el dictado se abre pero lo hablado no aterriza en ninguna parte. Se puede
    #: apagar si en algún programa el clic cae donde no debe.
    pinchar_cuadro_al_dictar: bool = True
    #: De qué color se ve cada efecto, según lo que veas tú.
    #:
    #: El firmware NO deja elegir el color: solo viaja un byte con el número del
    #: efecto y el color va cocido dentro de cada uno —comprobado en los cuatro
    #: clientes del fabricante—. Pero elegir «el verde» sigue siendo lo natural,
    #: así que se anota qué color tiene cada efecto y la interfaz deja buscar por
    #: ahí. Vienen puestos los que el fabricante nombra por su color; el resto se
    #: rellena mirando el teclado, con el recorrido de la propia página.
    colores_efecto: dict[str, str] = field(default_factory=lambda: {
        "0": "apagado",
        "2": "multicolor",
        "3": "multicolor",
        "4": "multicolor",
        "13": "azul",
    })
    reglas: list[Regla] = field(default_factory=_reglas_iniciales)
    modos: list["Modo"] = field(default_factory=_modos_iniciales)
    luces_por_estado: dict[str, int] = field(default_factory=_luces_iniciales)
    aplicaciones: list[dict] = field(default_factory=_aplicaciones_iniciales)

    @classmethod
    def cargar(cls, ruta: Path | None = None) -> "Ajustes":
        ruta = ruta or ruta_config()
        if not ruta.exists():
            return cls()
        try:
            crudo: dict[str, Any] = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        reglas = [
            Regla(**r) for r in crudo.pop("reglas", []) if isinstance(r, dict) and "patron" in r
        ]
        modos = _leer_modos(crudo.pop("modos", []))
        luces = _leer_luces(crudo.pop("luces_por_estado", {}))
        aplicaciones = _leer_aplicaciones(crudo.pop("aplicaciones", []))
        colores = {
            str(int(k)): str(v)
            for k, v in (crudo.pop("colores_efecto", {}) or {}).items()
            if str(v).strip()
        } if isinstance(crudo.get("colores_efecto", {}), dict) else {}
        aparte = {"reglas", "modos", "luces_por_estado", "aplicaciones", "colores_efecto"}
        conocidos = {c for c in cls.__dataclass_fields__ if c not in aparte}
        ajustes = cls(**{k: v for k, v in crudo.items() if k in conocidos})
        if reglas:
            ajustes.reglas = reglas
        if modos:
            ajustes.modos = modos
        if luces:
            ajustes.luces_por_estado = {**ajustes.luces_por_estado, **luces}
        if aplicaciones:
            ajustes.aplicaciones = aplicaciones
        if colores:
            ajustes.colores_efecto = {**ajustes.colores_efecto, **colores}
        return ajustes

    def guardar(self, ruta: Path | None = None) -> Path:
        ruta = ruta or ruta_config()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(ruta.suffix + ".tmp")
        temporal.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        temporal.replace(ruta)
        return ruta

    def es_accesible(self) -> bool:
        """Modo sin color ni emojis, pensado para lectores de pantalla."""
        return self.accesible or os.environ.get("TECLADOIA_ACCESIBLE") == "1"


# --- lectores tolerantes -----------------------------------------------------
# Un fichero editado a mano no debe dejar la aplicación sin arrancar: lo que no
# se entiende se descarta y se sigue con lo demás.

def _leer_modos(crudo: Any) -> list["Modo"]:
    from .modelo import Modo, Tecla

    if not isinstance(crudo, list):
        return []
    modos: list[Modo] = []
    for entrada in crudo[:4]:
        if not isinstance(entrada, dict):
            continue
        teclas: list[Tecla] = []
        for tecla in (entrada.get("teclas") or [])[:4]:
            if not isinstance(tecla, dict):
                teclas.append(Tecla())
                continue
            pasos = [
                (int(x[0]), int(x[1]))
                for x in (tecla.get("macro") or [])
                if isinstance(x, (list, tuple)) and len(x) == 2
            ]
            teclas.append(
                Tecla(
                    atajo=str(tecla.get("atajo") or ""),
                    descripcion=str(tecla.get("descripcion") or ""),
                    macro=pasos,
                )
            )
        while len(teclas) < 4:
            teclas.append(Tecla())
        modos.append(Modo(
            nombre=str(entrada.get("nombre") or ""),
            agente=str(entrada.get("agente") or "").strip().lower(),
            teclas=teclas,
            luces=_leer_luces(entrada.get("luces") or {}),
            programa=str(entrada.get("programa") or ""),
            lanzar=str(entrada.get("lanzar") or ""),
            alto_cuadro=int(entrada.get("alto_cuadro") or 0),
        ))
    return modos


def _leer_luces(crudo: Any) -> dict[str, int]:
    if not isinstance(crudo, dict):
        return {}
    limpio: dict[str, int] = {}
    for clave, valor in crudo.items():
        try:
            limpio[str(int(clave))] = int(valor) & 0xFF
        except (TypeError, ValueError):
            continue
    return limpio


def _leer_aplicaciones(crudo: Any) -> list[dict]:
    if not isinstance(crudo, list):
        return []
    limpio: list[dict] = []
    for entrada in crudo:
        if not isinstance(entrada, dict) or not entrada.get("patron"):
            continue
        try:
            modo = int(entrada.get("modo", 0))
        except (TypeError, ValueError):
            continue
        limpio.append({
            "patron": str(entrada["patron"]),
            "modo": modo,
            "en": str(entrada.get("en") or "proceso"),
        })
    return limpio
