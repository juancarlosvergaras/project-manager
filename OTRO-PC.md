# Llevar el teclado a otro ordenador

Son cuatro pasos y solo el primero es manual de verdad. Unos diez minutos, casi
todo esperando a que se instale.

---

## 1. Emparejar el teclado (a mano, una vez)

En el ordenador nuevo:

1. Enciende el AhaKey y déjalo cerca.
2. **Configuración › Bluetooth y dispositivos › Agregar dispositivo › Bluetooth**.
3. Elige el que aparezca como **AhaKey** seguido de cuatro caracteres.

Esto no lo puede hacer ningún programa por ti: emparejar exige confirmar en el
sistema. Todo lo demás sí está automatizado.

> El teclado recuerda varios ordenadores a la vez, así que emparejarlo aquí no
> lo desempareja del otro. Se cambia de uno a otro con su propio selector.

---

## 2. Instalar TecladoIA

**Lo más sencillo: el ejecutable.** En la pestaña **Descargar** del panel hay un
`TecladoIA.exe` de unos 27 MB que **lleva Python dentro**, así que en el
ordenador nuevo no hay que instalar nada antes. Lo abres y él se encarga: pone
los enganches en los programas de IA que encuentre, te pregunta la clave del
panel, deja el servicio arrancando con el equipo y lo pone en marcha.

Si prefieres trabajar desde el código, sigue leyendo.

### Desde el código

Copia la carpeta del proyecto al ordenador nuevo —o descárgala desde la pestaña
**Descargar** del panel, que arma el paquete al vuelo— y desde ahí:

```powershell
powershell -ExecutionPolicy Bypass -File instalar.ps1
```

El instalador comprueba Python, instala la aplicación con soporte Bluetooth,
pone los enganches en los programas de IA que encuentre, te pregunta la clave
del panel, deja el servicio arrancando con el equipo y lo pone en marcha.

Si además quieres abrirlo desde el móvil o desde otro sitio:

```powershell
powershell -ExecutionPolicy Bypass -File instalar.ps1 -Host 0.0.0.0 -Clave "la-que-elijas"
```

Con `-Host` conviene ejecutarlo **como administrador**, para que pueda abrir el
puerto en el cortafuegos. Si no, lo dice y sigue.

**Falta Python?** Descárgalo de <https://www.python.org/downloads/> y marca la
casilla «Add Python to PATH» durante la instalación. Nada más.

---

## 3. Llevarte tu configuración (opcional)

Los modos, las teclas, las reglas y los colores viven en un solo archivo:

```
%APPDATA%\TecladoIA\config.json
```

Cópialo al mismo sitio en el ordenador nuevo y tendrás exactamente lo que tenías.
Si no lo copias, arranca con los valores de fábrica y funciona igual.

Lo que **no** hace falta copiar: las teclas y las imágenes de la pantalla están
guardadas en la memoria del propio teclado, así que viajan con él.

---

## 4. Comprobar

Abre <http://127.0.0.1:8770> —o la dirección que te diera el instalador—. Deberías
ver el teclado conectado, su batería y su firmware.

Si dice que no hay teclado: enciéndelo y espera unos segundos, que el servicio lo
engancha solo. Y **cierra la aplicación oficial de AhaKey si la tienes abierta**:
solo un programa puede hablar con el teclado a la vez.

---

## Publicarlo en Internet como aquí

Solo si lo quieres accesible desde fuera. En el Mac mini, añade el renglón a
`~/Servidor/rutas.conf` con la IP de Tailscale del ordenador nuevo:

```
ahakey       8770   publico   100.79.52.120
```

—cambiando esa IP por la del equipo, que se ve con `tailscale status`— y aplica:

```bash
bash ~/Servidor/scripts/tunel.sh
```

El cuarto campo es el destino. Sin él, la ruta iría al propio Mac mini.

---

## Qué se lleva el teclado y qué se queda

| Viaja en el teclado | Se queda en el ordenador |
|---|---|
| Las cuatro teclas de cada modo | Las reglas de aprobación |
| Las imágenes de la pantalla | Los enganches de los programas de IA |
| Los efectos de luz por estado | La bitácora de decisiones |
| El emparejamiento con cada equipo | La clave del panel |

Por eso el teclado funciona igual nada más emparejarlo: lo suyo lo lleva dentro.
Lo que se instala en cada ordenador es quien lo escucha.
