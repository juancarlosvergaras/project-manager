"""Rutas, ajustes persistentes y preferencias de accesibilidad."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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
    reglas: list[Regla] = field(default_factory=_reglas_iniciales)

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
        conocidos = {c for c in cls.__dataclass_fields__ if c != "reglas"}
        ajustes = cls(**{k: v for k, v in crudo.items() if k in conocidos})
        if reglas:
            ajustes.reglas = reglas
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
