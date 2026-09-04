#!/usr/bin/env python3
"""Portero de sikaimini.proyectoia.org: pasa al PC que tenga el teclado.

El mini teclado se lleva de un PC a otro, y en cada uno corre su propio
SikaiMini. La direccion web es una sola, asi que el portero pregunta a cada PC
(por Tailscale, en /api/salud, que no pide clave) si tiene el teclado
enchufado y empalma con ese. Si ninguno lo tiene, con el primero que
conteste; si ninguno contesta, una pagina que explica que estan apagados.

Proxy de nivel TCP como el de ahakey: solo se interpreta HTTP para la
pregunta de salud; el resto se empalma tal cual. Sin dependencias.
"""

import asyncio
import json
import os
import time

ESCUCHA = ('127.0.0.1', int(os.environ.get('PORTERO_PUERTO', '8026')))
#: Los PC candidatos, en orden de preferencia si ninguno tiene el teclado.
DESTINOS = [
    (h.strip(), int(p)) for h, p in (
        d.split(':') for d in os.environ.get(
            'PORTERO_PCS', '100.79.52.120:8772,100.125.175.45:8772,100.66.117.114:8772'
        ).split(',')
    )
]
PLAZO_S = 3.0
MEMORIA_S = 4.0  # cuanto vale la ultima eleccion, para no preguntar en cada imagen de la pagina

PAGINA = '''<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SikaiMini - ningun equipo del teclado esta encendido</title>
<style>
 :root{color-scheme:light dark;--fondo:#F2F5F9;--tarjeta:#fff;--texto:#0F172A;--tenue:#64748B;--borde:#E3E8EF}
 @media (prefers-color-scheme:dark){:root{--fondo:#0B0F16;--tarjeta:#151A23;--texto:#E7ECF3;--tenue:#94A3B8;--borde:#232A36}}
 body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--fondo);
      color:var(--texto);font:16px/1.6 -apple-system,Segoe UI,system-ui,sans-serif;padding:1.5rem}
 .caja{max-width:34rem;background:var(--tarjeta);border:1px solid var(--borde);border-radius:16px;padding:2rem}
 h1{margin:0 0 .75rem;font-size:1.4rem} p{margin:.75rem 0;color:var(--tenue)} b{color:var(--texto)}
</style></head><body><div class="caja">
<h1>Ningun equipo con SikaiMini esta encendido</h1>
<p>Esta pagina esta bien; el servidor tambien. Lo que falta es un ordenador que
tenga SikaiMini en marcha y publicado por Tailscale.</p>
<p><b>El teclado no viaja por Internet</b>: la aplicacion corre en el equipo que
lo tiene enchufado. Esta direccion pasa al que lo tenga en ese momento.</p>
<p>Enciende ese equipo, o en su panel local (http://127.0.0.1:8772, pestana
Ajustes) elige «Escuchar en» la direccion de Tailscale.</p>
</div></body></html>'''

_ultima = {'cuando': 0.0, 'destino': None}


def respuesta_de_cortesia() -> bytes:
    cuerpo = PAGINA.encode('utf-8')
    return ('HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html; charset=utf-8\r\n'
            f'Content-Length: {len(cuerpo)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
            ).encode('ascii') + cuerpo


async def salud(destino):
    """(tiene_teclado, destino) o None si no contesta."""
    try:
        lector, escritor = await asyncio.wait_for(asyncio.open_connection(*destino), PLAZO_S)
        escritor.write(f'GET /api/salud HTTP/1.1\r\nHost: {destino[0]}\r\nConnection: close\r\n\r\n'.encode())
        await escritor.drain()
        crudo = await asyncio.wait_for(lector.read(4096), PLAZO_S)
        escritor.close()
    except (OSError, asyncio.TimeoutError):
        return None
    _, _, cuerpo = crudo.partition(b'\r\n\r\n')
    try:
        datos = json.loads(cuerpo.decode('utf-8', 'replace'))
    except ValueError:
        return None
    if not isinstance(datos, dict) or datos.get('app') != 'sikaimini':
        return None
    return bool(datos.get('teclado')), destino


async def elegir():
    ahora = time.monotonic()
    if _ultima['destino'] is not None and ahora - _ultima['cuando'] < MEMORIA_S:
        return _ultima['destino']
    resultados = await asyncio.gather(*(salud(d) for d in DESTINOS))
    vivos = [r for r in resultados if r is not None]
    elegido = None
    for tiene, destino in vivos:
        if tiene:
            elegido = destino
            break
    if elegido is None and vivos:
        elegido = vivos[0][1]
    _ultima['cuando'] = ahora
    _ultima['destino'] = elegido
    return elegido


async def empalmar(lector, escritor):
    try:
        while True:
            trozo = await lector.read(65536)
            if not trozo:
                break
            escritor.write(trozo)
            await escritor.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            escritor.close()
        except Exception:
            pass


async def atender(lector_cliente, escritor_cliente):
    destino = await elegir()
    if destino is not None:
        try:
            lector_pc, escritor_pc = await asyncio.wait_for(asyncio.open_connection(*destino), PLAZO_S)
        except (OSError, asyncio.TimeoutError):
            destino = None
            _ultima['destino'] = None
    if destino is None:
        try:
            escritor_cliente.write(respuesta_de_cortesia())
            await escritor_cliente.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            escritor_cliente.close()
        return
    await asyncio.gather(empalmar(lector_cliente, escritor_pc), empalmar(lector_pc, escritor_cliente))


async def principal():
    servidor = await asyncio.start_server(atender, *ESCUCHA)
    print(f'Portero de sikaimini en {ESCUCHA[0]}:{ESCUCHA[1]} -> {DESTINOS}', flush=True)
    async with servidor:
        await servidor.serve_forever()


if __name__ == '__main__':
    asyncio.run(principal())
