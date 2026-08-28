"""TecladoIA — la aplicación en español para el teclado AhaKey X1."""

import sys as _sys

# COM en apartamento MTA, y esto hay que hacerlo **antes de importar nada**.
#
# Es el arreglo de un fallo que costó dos días y que parecía cinco fallos
# distintos: la web decía «todavía no hay teclado» con el teclado delante, la
# barra se quedaba clavada en verde, el modo no volvía al 1 al encender, y
# apagar el teclado una sola vez obligaba a reiniciar el servicio. Todo era
# esto.
#
# La capa de accesibilidad de Windows (``comtypes``, que es como se encuentra
# el cuadro de escribir de Claude o ChatGPT) inicializa COM en apartamento STA
# si nadie dice lo contrario. Y a partir de ese momento **las operaciones
# asíncronas de WinRT no vuelven jamás en ese hilo**: no fallan, no dan error,
# simplemente no terminan. Como la conexión Bluetooth va por WinRT, el
# servicio perdía el teclado en cuanto le tocaba usar accesibilidad una vez
# —o sea, en cuanto pulsabas el micrófono— y ya no lo recuperaba.
#
# De ahí el síntoma que despistaba: un proceso recién arrancado abría el
# teclado en tres décimas, y el servicio, con el aparato encendido delante, no
# lo conseguía en veinte minutos de reintentos. La diferencia no era el
# teclado; era que al servicio ya le había tocado usar accesibilidad.
#
# ``coinit_flags = 0`` es COINIT_MULTITHREADED, que es lo que WinRT necesita.
# La accesibilidad funciona igual de bien en MTA: está comprobado que sigue
# encontrando el cuadro de escribir. **No quitar esta línea, y que no baje de
# aquí**: si ``comtypes`` se importa antes, ya no hay nada que hacer.
_sys.coinit_flags = 0

__version__ = "1.2.0"
__all__ = ["__version__"]
