#!/usr/bin/env python3
"""Portero de sikaimini.proyectoia.org: pasa al PC que tenga el teclado.

Dos maneras de encontrar ese PC, y la primera es la buena:

1. **El PC se presenta solo.** El servicio SikaiMini de cada equipo abre por
   Tailscale una conexión de control a este portero (puerto 8027, solo en la
   dirección de Tailscale del Mac mini) y le va diciendo si tiene el teclado.
   Cuando llega un navegador, el portero le pide a ese PC que abra otra
   conexión y empalma las dos. El PC no necesita publicar nada, ni abrir el
   cortafuegos, ni que nadie sepa su dirección: la conexión la inicia él.
2. **Si ningún PC se ha presentado**, se pregunta a una lista fija de
   direcciones por Tailscale (`/api/salud`, sin clave), como antes.

Si no hay nadie, una página que explica que los equipos están apagados, en
vez del «Bad gateway» de Cloudflare. Proxy de nivel TCP: solo se interpreta
HTTP para la pregunta de salud; el resto se empalma tal cual, así que las
descargas y el canal de sucesos en vivo funcionan sin tratarlos aparte.

Corre con el Python 3.9 del sistema del Mac mini. Sin dependencias.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time

APP = os.environ.get('PORTERO_APP', 'sikaimini')
ESCUCHA = ('127.0.0.1', int(os.environ.get('PORTERO_PUERTO', '8026')))
#: Donde se presentan los PC: la dirección de Tailscale del Mac mini, para que
#: solo entren equipos de la red propia.
ESCUCHA_AGENTES = (
    os.environ.get('PORTERO_AGENTES_IP', '100.65.52.65'),
    int(os.environ.get('PORTERO_AGENTES_PUERTO', '8027')),
)
#: Los PC candidatos del camino viejo, en orden de preferencia.
DESTINOS = [
    (h.strip(), int(p)) for h, p in (
        d.split(':') for d in os.environ.get(
            'PORTERO_PCS', '100.79.52.120:8772,100.125.175.45:8772,100.66.117.114:8772'
        ).split(',')
    )
]
PLAZO_S = 3.0
PLAZO_DE_APERTURA_S = 6.0   # cuánto se espera a que el PC abra la conexión de datos
VIGENCIA_DEL_LATIDO_S = 45.0
MEMORIA_S = 4.0  # cuánto vale la última elección del camino viejo

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
tenga SikaiMini en marcha y conectado a Tailscale.</p>
<p><b>El teclado no viaja por Internet</b>: la aplicacion corre en el equipo que
lo tiene enchufado, y ese equipo se presenta aqui solo, sin configurar nada.
Esta direccion pasa al que tenga el teclado en ese momento.</p>
<p>Enciende ese equipo, comprueba que Tailscale esta conectado y que SikaiMini
tiene clave (pestana Ajustes de su panel, http://127.0.0.1:8772): sin clave no
se publica.</p>
</div></body></html>'''


class Agente:
    def __init__(self, identificador, equipo, escritor):
        self.identificador = identificador
        self.equipo = equipo
        self.escritor = escritor
        self.teclado = False
        self.ultimo = time.monotonic()

    @property
    def vivo(self):
        return time.monotonic() - self.ultimo < VIGENCIA_DEL_LATIDO_S


AGENTES = {}     # identificador -> Agente
PENDIENTES = {}  # token -> Future[(lector, escritor)]
_ultima = {'cuando': 0.0, 'destino': None}


def anota(texto):
    print(time.strftime('%H:%M:%S') + ' ' + texto, flush=True)


def respuesta_de_cortesia():
    cuerpo = PAGINA.encode('utf-8')
    return ('HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html; charset=utf-8\r\n'
            f'Content-Length: {len(cuerpo)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
            ).encode('ascii') + cuerpo


# --- los PC que se presentan -------------------------------------------------

async def atender_agente(lector, escritor):
    """Una conexión de un PC: o es de control (se queda) o es de datos (se entrega)."""
    try:
        linea = await asyncio.wait_for(lector.readline(), 10)
        mensaje = json.loads(linea.decode('utf-8'))
    except (asyncio.TimeoutError, ValueError, OSError, UnicodeDecodeError):
        escritor.close()
        return
    if not isinstance(mensaje, dict):
        escritor.close()
        return

    if 'datos' in mensaje:
        futuro = PENDIENTES.pop(str(mensaje['datos']), None)
        if futuro is None or futuro.done():
            escritor.close()
            return
        futuro.set_result((lector, escritor))
        return  # de este par se encarga quien lo pidió

    if mensaje.get('app') != APP:
        escritor.close()
        return
    identificador = secrets.token_hex(4)
    agente = Agente(identificador, str(mensaje.get('equipo') or '?'), escritor)
    agente.teclado = bool(mensaje.get('teclado'))
    AGENTES[identificador] = agente
    anota(f'se presenta {agente.equipo} ({identificador}), teclado={agente.teclado}')
    try:
        while True:
            linea = await asyncio.wait_for(lector.readline(), VIGENCIA_DEL_LATIDO_S)
            if not linea:
                break
            try:
                latido = json.loads(linea.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(latido, dict):
                tenia = agente.teclado
                agente.teclado = bool(latido.get('teclado'))
                if latido.get('equipo'):
                    agente.equipo = str(latido['equipo'])
                if tenia != agente.teclado:
                    anota(f'{agente.equipo}: teclado={agente.teclado}')
            agente.ultimo = time.monotonic()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        AGENTES.pop(identificador, None)
        anota(f'se va {agente.equipo} ({identificador})')
        try:
            escritor.close()
        except Exception:
            pass


def agente_elegido():
    vivos = [a for a in AGENTES.values() if a.vivo]
    if not vivos:
        return None
    con_teclado = [a for a in vivos if a.teclado]
    candidatos = con_teclado or vivos
    return max(candidatos, key=lambda a: a.ultimo)


async def abrir_por_agente(agente):
    """Le pide al PC una conexión de datos y la devuelve, o None si no llega."""
    token = secrets.token_hex(8)
    futuro = asyncio.get_running_loop().create_future()
    PENDIENTES[token] = futuro
    try:
        agente.escritor.write((json.dumps({'abrir': token}) + '\n').encode('utf-8'))
        await agente.escritor.drain()
        return await asyncio.wait_for(futuro, PLAZO_DE_APERTURA_S)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        PENDIENTES.pop(token, None)
        return None


# --- el camino viejo: preguntar a direcciones fijas ---------------------------

async def salud(destino):
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
    if not isinstance(datos, dict) or datos.get('app') != APP:
        return None
    return bool(datos.get('teclado')), destino


async def elegir_por_direccion():
    ahora = time.monotonic()
    if _ultima['destino'] is not None and ahora - _ultima['cuando'] < MEMORIA_S:
        return _ultima['destino']
    if not DESTINOS:
        return None
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


# --- empalmar ------------------------------------------------------------------

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
    par = None
    agente = agente_elegido()
    if agente is not None:
        par = await abrir_por_agente(agente)
        if par is None:
            anota(f'{agente.equipo} no abrió la conexión de datos; se descarta')
            AGENTES.pop(agente.identificador, None)
    if par is None:
        destino = await elegir_por_direccion()
        if destino is not None:
            try:
                par = await asyncio.wait_for(asyncio.open_connection(*destino), PLAZO_S)
            except (OSError, asyncio.TimeoutError):
                _ultima['destino'] = None
    if par is None:
        try:
            escritor_cliente.write(respuesta_de_cortesia())
            await escritor_cliente.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            escritor_cliente.close()
        return
    lector_pc, escritor_pc = par
    await asyncio.gather(empalmar(lector_cliente, escritor_pc), empalmar(lector_pc, escritor_cliente))


async def principal():
    servidor = await asyncio.start_server(atender, *ESCUCHA)
    agentes = await asyncio.start_server(atender_agente, *ESCUCHA_AGENTES)
    anota(f'Portero de {APP} en {ESCUCHA[0]}:{ESCUCHA[1]}; los PC se presentan en '
          f'{ESCUCHA_AGENTES[0]}:{ESCUCHA_AGENTES[1]}; de respaldo {DESTINOS}')
    async with servidor, agentes:
        await asyncio.gather(servidor.serve_forever(), agentes.serve_forever())


if __name__ == '__main__':
    asyncio.run(principal())
