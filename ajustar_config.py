"""Escribe en la configuración de verdad, la que ve el servicio.

Hace falta porque la aplicación de Claude está empaquetada y Windows le
redirige `AppData` a una carpeta propia. Todo lo que Claude guarde en la
configuración se queda en esa copia y el servicio —que arranca desde el
programador de tareas, sin redirigir— nunca lo ve. Los dos leen la misma ruta y
son archivos distintos, que es de las cosas más desconcertantes que puede hacer
un ordenador.

Este script se ejecuta a través de una tarea programada, que sí escribe donde
toca. Se le pasan pares `campo=valor`:

    python ajustar_config.py clave_panel=Unicartagena1 modo_al_conectar=0

Los valores se interpretan como JSON cuando se puede (`true`, `0`, `null`) y
como texto cuando no.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def ruta_config() -> Path:
    raiz = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return raiz / "TecladoIA" / "config.json"


def interpretar(texto: str):
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def main(argumentos: list[str]) -> int:
    ruta = ruta_config()
    informe = [f"config: {ruta}", f"existe: {ruta.exists()}"]

    datos: dict = {}
    if ruta.exists():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            informe.append(f"no se pudo leer: {error}")
            datos = {}

    for pareja in argumentos:
        campo, _, crudo = pareja.partition("=")
        if not campo or not _:
            informe.append(f"se ignora «{pareja}»: falta el signo igual")
            continue
        datos[campo] = interpretar(crudo)
        informe.append(f"  {campo} = {datos[campo]!r}")

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    informe.append(f"guardado: {ruta.stat().st_size} bytes")

    salida = Path(__file__).with_name("ajustar_config.txt")
    salida.write_text("\n".join(informe), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
