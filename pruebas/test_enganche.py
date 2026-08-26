"""Pruebas del cliente de enganche: lo ejecuta el agente en cada evento."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import threading
import unittest

import sys

from pruebas.base import PruebaAislada
from tecladoia import enganche
from tecladoia.config import Ajustes
from tecladoia.dispositivo import GestorTeclado
from tecladoia.servidor import ServidorEnganches
from tecladoia.transporte.simulado import TransporteSimulado


class PruebaContexto(unittest.TestCase):
    def test_lee_el_formato_de_claude(self):
        contexto = enganche.extraer_contexto(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "cwd": "/casa/proyecto",
                "session_id": "abc",
            }
        )
        self.assertEqual(contexto["herramienta"], "Bash")
        self.assertEqual(contexto["comando"], "git status")
        self.assertEqual(contexto["ruta"], "/casa/proyecto")

    def test_lee_una_ruta_de_fichero_como_comando(self):
        contexto = enganche.extraer_contexto(
            {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}}
        )
        self.assertEqual(contexto["comando"], "/etc/passwd")

    def test_admite_un_comando_troceado_en_lista(self):
        contexto = enganche.extraer_contexto({"tool_input": {"command": ["rm", "-rf", "/"]}})
        self.assertEqual(contexto["comando"], "rm -rf /")

    def test_una_entrada_vacia_no_rompe_nada(self):
        self.assertEqual(enganche.extraer_contexto({}), {})


class SinEntrada:
    """Deja la entrada estándar vacía y cerrada, como haría un agente mudo."""

    def setUp(self) -> None:  # type: ignore[override]
        super().setUp()
        previo = sys.stdin
        sys.stdin = io.StringIO("")
        self.addCleanup(lambda: setattr(sys, "stdin", previo))


class PruebaSinServicio(SinEntrada, PruebaAislada):
    def test_sin_servicio_se_contesta_lo_neutro_y_sin_error(self):
        ajustes = Ajustes(puerto_hooks=8931)
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = enganche.ejecutar("claude", "PermissionRequest", ajustes=ajustes)
        self.assertEqual(codigo, 0)
        # Sin decisión: Claude sigue su flujo normal y pregunta a la persona.
        self.assertEqual(json.loads(salida.getvalue()), {})
        self.assertIn("no responde", error.getvalue())

    def test_agente_o_evento_desconocido(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(enganche.ejecutar("nadie", "X", ajustes=Ajustes()), 2)
            self.assertEqual(enganche.ejecutar("claude", "X", ajustes=Ajustes()), 2)


class PruebaConServicio(SinEntrada, PruebaAislada):
    def _llamar(self, ajustes, agente, evento, contexto=None) -> str:
        """Ejecuta el cliente (síncrono) en un hilo aparte."""
        resultado: list[str] = []

        def trabajo() -> None:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
                enganche.ejecutar(agente, evento, contexto, ajustes)
            resultado.append(buffer.getvalue())

        hilo = threading.Thread(target=trabajo)
        hilo.start()
        return hilo, resultado

    def test_ida_y_vuelta_completa_por_el_socket(self):
        async def caso():
            ajustes = Ajustes(sincronizar_config_agentes=False, puerto_hooks=8933)
            simulado = TransporteSimulado(palanca=0)
            gestor = GestorTeclado(ajustes, simulado)
            await gestor.conectar()
            servidor = ServidorEnganches(gestor, ajustes)
            await servidor.arrancar(con_tcp=False)
            try:
                hilo, resultado = self._llamar(
                    ajustes, "claude", "PermissionRequest", {"comando": "git status"}
                )
                while hilo.is_alive():
                    await asyncio.sleep(0.01)
                salida = json.loads(resultado[0])
                self.assertEqual(salida["hookSpecificOutput"]["decision"], "allow")

                simulado.mover_palanca(1)
                hilo, resultado = self._llamar(
                    ajustes, "claude", "PermissionRequest", {"comando": "git status"}
                )
                while hilo.is_alive():
                    await asyncio.sleep(0.01)
                salida = json.loads(resultado[0])
                self.assertEqual(salida["hookSpecificOutput"]["decision"], "escalate")
            finally:
                await servidor.detener()
        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()
