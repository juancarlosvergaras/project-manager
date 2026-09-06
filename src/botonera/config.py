"""Configuración de la Botonera: dónde vive y qué guarda.

Va en ``%APPDATA%\\Botonera\\config.json`` (o en ``$BOTONERA_INICIO``, que es
lo que usan las pruebas). Misma trampa que en las otras tres aplicaciones: la
aplicación de Claude está empaquetada y Windows le redirige ``AppData``, así
que lo que se guarde desde una sesión de Claude no lo ve el servicio de la
tarea programada. Para eso está ``ajustar_config.py --app Botonera``.

Aquí la configuración **es la verdad**: el teclado no se puede leer, así que
lo que hay grabado es lo último que se le escribió desde este archivo.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from . import protocolo
from .protocolo import Accion, ErrorProtocolo, Luces

NOMBRE = "Botonera"

#: Con lo que se estrena cada perfil: F13-F24 en las teclas (no chocan con
#: nada y TecladoIA, MiniMic y SikaiMini ya entienden las suyas), volumen en la
#: primera perilla, desplazamiento en la segunda y música en la tercera.
TECLAS_INICIALES: tuple[str, ...] = tuple(f"f{13 + i}" for i in range(protocolo.NUMERO_DE_TECLAS))
PERILLAS_INICIALES: tuple[tuple[str, str, str], ...] = (
    ("vol-", "silencio", "vol+"),
    ("rueda-abajo", "clic-central", "rueda-arriba"),
    ("anterior", "reproducir", "siguiente"),
)
COLORES_INICIALES = ("#2563eb", "#16a34a", "#dc2626")
NOMBRES_INICIALES = ("Perfil 1", "Perfil 2", "Perfil 3")


def directorio_base() -> Path:
    propio = os.environ.get("BOTONERA_INICIO")
    if propio:
        return Path(propio)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / NOMBRE
    return Path.home() / ".botonera"


def ruta_config() -> Path:
    return directorio_base() / "config.json"


def ruta_registro() -> Path:
    return directorio_base() / "servicio.log"


@dataclass
class Perfil:
    """Uno de los tres perfiles del teclado: sus 21 piezas y sus luces."""

    nombre: str = "Perfil"
    teclas: list[str] = field(default_factory=lambda: list(TECLAS_INICIALES))
    perillas: list[list[str]] = field(default_factory=lambda: [list(p) for p in PERILLAS_INICIALES])
    luces_modo: int = 1
    luces_color: str = "#ffffff"

    @classmethod
    def inicial(cls, indice: int) -> "Perfil":
        return cls(nombre=NOMBRES_INICIALES[indice], luces_color=COLORES_INICIALES[indice])

    @classmethod
    def desde_dict(cls, crudo: Any, indice: int) -> "Perfil":
        """Lo que haya en el archivo, saneado: lo que no vale vuelve a lo inicial."""
        base = cls.inicial(indice)
        if not isinstance(crudo, dict):
            return base
        if isinstance(crudo.get("nombre"), str) and crudo["nombre"].strip():
            base.nombre = crudo["nombre"].strip()[:40]
        teclas = crudo.get("teclas")
        if isinstance(teclas, list) and len(teclas) == protocolo.NUMERO_DE_TECLAS and all(isinstance(t, str) for t in teclas):
            base.teclas = list(teclas)
        perillas = crudo.get("perillas")
        if (isinstance(perillas, list) and len(perillas) == protocolo.NUMERO_DE_PERILLAS
                and all(isinstance(p, list) and len(p) == len(protocolo.GESTOS) and all(isinstance(g, str) for g in p) for p in perillas)):
            base.perillas = [list(p) for p in perillas]
        modo = crudo.get("luces_modo")
        if isinstance(modo, int) and not isinstance(modo, bool) and 0 <= modo <= 255:
            base.luces_modo = modo
        color = crudo.get("luces_color")
        if isinstance(color, str):
            try:
                base.luces_color = protocolo.color_a_texto(protocolo.color_desde_texto(color))
            except ErrorProtocolo:
                pass
        return base

    # --- lo que se le manda al teclado ---

    def acciones(self) -> list[Accion]:
        """Las 21 acciones en el orden de las piezas. Lanza ErrorProtocolo si algo está mal escrito."""
        salida: list[Accion] = []
        for i, t in enumerate(self.teclas):
            try:
                salida.append(Accion.desde_texto(t))
            except ErrorProtocolo as e:
                raise ErrorProtocolo(f"{protocolo.NOMBRES_DE_LAS_PIEZAS[i]}: {e}") from e
        for n, perilla in enumerate(self.perillas):
            for g, t in enumerate(perilla):
                try:
                    salida.append(Accion.desde_texto(t))
                except ErrorProtocolo as e:
                    raise ErrorProtocolo(f"{protocolo.NOMBRES_DE_LAS_PIEZAS[protocolo.pieza_de_perilla(n, g)]}: {e}") from e
        return salida

    def luces(self) -> Luces:
        return Luces(self.luces_modo, self.luces_color)

    def texto_de_pieza(self, pieza: int) -> str:
        if pieza < protocolo.NUMERO_DE_TECLAS:
            return self.teclas[pieza]
        n, g = divmod(pieza - protocolo.NUMERO_DE_TECLAS, len(protocolo.GESTOS))
        return self.perillas[n][g]

    def poner_pieza(self, pieza: int, texto: str) -> Accion:
        """Guarda la acción (normalizada) en la pieza; devuelve la acción. Valida antes."""
        accion = Accion.desde_texto(texto)
        if not 0 <= pieza < protocolo.NUMERO_DE_PIEZAS:
            raise ErrorProtocolo(f"pieza {pieza}: hay {protocolo.NUMERO_DE_PIEZAS}")
        if pieza < protocolo.NUMERO_DE_TECLAS:
            self.teclas[pieza] = str(accion)
        else:
            n, g = divmod(pieza - protocolo.NUMERO_DE_TECLAS, len(protocolo.GESTOS))
            self.perillas[n][g] = str(accion)
        return accion

    def normalizar(self) -> None:
        """Reescribe cada pieza con la forma canónica; lanza ErrorProtocolo si alguna no vale."""
        acciones = self.acciones()
        self.teclas = [str(a) for a in acciones[:protocolo.NUMERO_DE_TECLAS]]
        resto = acciones[protocolo.NUMERO_DE_TECLAS:]
        self.perillas = [[str(resto[3 * n + g]) for g in range(3)] for n in range(protocolo.NUMERO_DE_PERILLAS)]
        self.luces()  # valida modo y color

    def como_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["luces_nombre"] = protocolo.MODOS_DE_LUZ.get(self.luces_modo, f"modo {self.luces_modo}")
        return datos


@dataclass
class Ajustes:
    # --- panel ---
    puerto_panel: int = 8773
    host_panel: str = "127.0.0.1"
    clave_panel: str = ""

    # --- el teclado ---
    perfiles: list[dict] = field(default_factory=lambda: [asdict(Perfil.inicial(i)) for i in range(protocolo.NUMERO_DE_PERFILES)])
    #: Al verlo por cable, grabarle los tres perfiles enteros. Como no se le
    #: puede preguntar qué tiene, es la única forma de estar seguro.
    escribir_al_conectar: bool = True
    #: Cuándo se le escribió por última vez (ISO) y a qué serie.
    ultima_escritura: str = ""
    serie_del_teclado: str = ""

    # --- el portero del Mac mini (ledblanco.proyectoia.org) ---
    #: A quién se presenta el servicio para que la dirección pública pase a
    #: este PC. Es la dirección de Tailscale del Mac mini; vacío = no
    #: presentarse. Solo con clave puesta: sin clave, el panel no se publica.
    portero: str = "100.65.52.65:8029"
    usar_portero: bool = True

    def perfil(self, indice: int) -> Perfil:
        if not 0 <= indice < protocolo.NUMERO_DE_PERFILES:
            raise ErrorProtocolo(f"perfil {indice}: hay {protocolo.NUMERO_DE_PERFILES}, contados desde 0")
        return Perfil.desde_dict(self.perfiles[indice], indice)

    def guardar_perfil(self, indice: int, perfil: Perfil) -> None:
        perfil.normalizar()
        self.perfiles[indice] = asdict(perfil)

    def todos_los_perfiles(self) -> list[Perfil]:
        return [self.perfil(i) for i in range(protocolo.NUMERO_DE_PERFILES)]

    # --- disco ---
    @classmethod
    def cargar(cls, ruta: Path | None = None) -> "Ajustes":
        ruta = ruta or ruta_config()
        try:
            crudo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(crudo, dict):
            return cls()
        conocidos = {f.name: f for f in fields(cls)}
        limpio: dict[str, Any] = {}
        for nombre, valor in crudo.items():
            if nombre not in conocidos:
                continue
            tipo = conocidos[nombre].type
            if tipo in ("int", int) and (not isinstance(valor, int) or isinstance(valor, bool)):
                continue
            if tipo in ("bool", bool) and not isinstance(valor, bool):
                continue
            if tipo in ("str", str) and not isinstance(valor, str):
                continue
            if nombre == "perfiles":
                if not isinstance(valor, list):
                    continue
                valor = [asdict(Perfil.desde_dict(valor[i] if i < len(valor) else None, i)) for i in range(protocolo.NUMERO_DE_PERFILES)]
            limpio[nombre] = valor
        return cls(**limpio)

    def guardar(self, ruta: Path | None = None) -> Path:
        ruta = ruta or ruta_config()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(ruta)
        return ruta

    def como_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["clave_panel"] = bool(self.clave_panel)  # nunca se devuelve la clave
        datos["perfiles"] = [p.como_dict() for p in self.todos_los_perfiles()]
        return datos
