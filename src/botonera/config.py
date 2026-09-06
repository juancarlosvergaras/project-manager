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

from minimic.config import (  # noqa: F401 - se reexportan: mismos programas, mismo dictado
    ATAJOS_DE_FABRICA, PROGRAMAS, aplicar_atajos_de_dictado, programa_por_proceso,
)

from . import protocolo
from .protocolo import Accion, ErrorProtocolo, Luces

NOMBRE = "Botonera"

#: Combinación privada de la tecla de dictado. Windows solo deja reservar cada
#: combinación a un proceso: el AhaKey tiene F13, el MiniMic F14 y el SiKai
#: F15. Aquí NO puede ser F16: por Bluetooth este teclado solo declara teclas
#: hasta el código 0x65 y las F13-F24 no llegan (comprobado el 6/9/2026: la
#: tecla llegaba por cable y por Bluetooth solo se veía el Alt). F12 con los
#: tres modificadores está libre y pasa por los dos caminos.
ATAJO_MICROFONO = "ctrl-mayus-alt-f12"
_ATAJO_ANTERIOR = "ctrl-mayus-alt-f16"  # se migra solo al cargar

#: Con lo que se estrena cada perfil, todo apto para cable y Bluetooth: la
#: fila de arriba es la del agente (dictado, aceptar, cancelar, borrar, como
#: el AhaKey), la segunda el portapapeles y la tercera ventanas y deshacer.
#: Volumen en la primera perilla, desplazamiento en la segunda, música en la tercera.
TECLAS_INICIALES: tuple[str, ...] = (
    ATAJO_MICROFONO, "intro", "esc", "retroceso",
    "ctrl-c", "ctrl-v", "ctrl-x", "ctrl-a",
    "alt-tab", "win-d", "ctrl-z", "ctrl-y",
)
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
            base.teclas = [ATAJO_MICROFONO if t == _ATAJO_ANTERIOR else t for t in teclas]
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
        solo_cable: list[int] = []
        for i in range(protocolo.NUMERO_DE_PIEZAS):
            try:
                if not Accion.desde_texto(self.texto_de_pieza(i)).funciona_por_bluetooth:
                    solo_cable.append(i)
            except ErrorProtocolo:
                pass
        datos["solo_cable"] = solo_cable
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

    # --- la tecla de dictado (a quién se le habla, igual que en MiniMic) ---
    programa: str = "activo"  #: uno de PROGRAMAS por su id; «activo» sigue a la ventana que tengas delante
    alto_cuadro: int = 0
    pinchar_cuadro: bool = True
    enviar_al_cerrar: bool = False
    usar_microfono_propio: bool = True
    pitido_al_abrir: bool = False
    atajos_dictado: dict[str, str] = field(default_factory=lambda: dict(ATAJOS_DE_FABRICA))

    # --- teclas que abren aplicaciones: hueco "1".."11" -> {nombre, destino} ---
    #: El hueco N es la combinación ctrl-mayus-alt-fN; el destino es el AppID
    #: del menú Inicio (o una ruta). Ver ``lanzador.py``.
    lanzadores: dict[str, dict] = field(default_factory=dict)

    # --- el portero del Mac mini (ledblanco.proyectoia.org) ---
    #: A quién se presenta el servicio para que la dirección pública pase a
    #: este PC. Es la dirección de Tailscale del Mac mini; vacío = no
    #: presentarse. Solo con clave puesta: sin clave, el panel no se publica.
    portero: str = "100.65.52.65:8029"
    usar_portero: bool = True

    def programa_elegido(self, proceso_al_frente: str = "") -> dict[str, str]:
        if self.programa == "activo":
            return programa_por_proceso(proceso_al_frente)
        for p in PROGRAMAS:
            if p["id"] == self.programa:
                return p
        return PROGRAMAS[-1]

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
            if nombre == "lanzadores":
                if not isinstance(valor, dict):
                    continue
                valor = {
                    str(k): {"nombre": str(v.get("nombre", "")), "destino": str(v.get("destino", ""))}
                    for k, v in valor.items()
                    if isinstance(v, dict) and v.get("destino") and str(k).isdigit() and 1 <= int(k) <= 11
                }
            if nombre == "atajos_dictado":
                if not isinstance(valor, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in valor.items()):
                    continue
                valor = {**ATAJOS_DE_FABRICA, **{k: v for k, v in valor.items() if k in ATAJOS_DE_FABRICA}}
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
