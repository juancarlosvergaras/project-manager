# TecladoIA — léeme antes de tocar nada

Aplicación en español para el teclado **AhaKey X1**. Sustituye a «AhaKey Studio»,
que está en inglés y en chino. Vive en `C:\Teclado Ahakey`.

---

## Arrancar el servicio (lo primero de cada sesión)

```bash
python -m tecladoia servicio --host 100.79.52.120
```

Con eso el panel queda en <http://100.79.52.120:8770> y, por el túnel del Mac
mini, en <https://ahakey.proyectoia.org>. **Clave: `Unicartagena1`.**

Antes de arrancar, mata lo que haya quedado de sesiones anteriores: si hay dos
servicios vivos se pelean por el teclado y por el puerto, y el síntoma es una
barra de luz congelada.

```bash
python -c "import subprocess; subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \"*tecladoia*\" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'])"
```

Comprobar que respondió, con la cabecera que toca:

```bash
curl -s -H "X-TecladoIA-Clave: Unicartagena1" http://100.79.52.120:8770/api/estado
```

---

## Lo que hay que saber sí o sí

**El teclado no se encuentra rastreando.** El AhaKey se empareja como teclado y
entonces **deja de anunciarse**; además su dirección va rotando. `bleak` no lo
encuentra nunca en ese estado. El único camino que funciona en Windows es
`transporte/windows_emparejado.py`, que lo abre por la lista de dispositivos
emparejados del sistema (WinRT). El transporte `auto` lo prueba primero.

> Si alguien «simplifica» `transporte/__init__.py` para que `auto` devuelva
> `TransporteBLE`, el teclado deja de conectarse. Ya pasó una vez.

**ChatGPT no tiene enganches y no puede tenerlos.** Es una aplicación cerrada:
no hay archivo donde declarar un comando ni evento al que apuntarse. Por eso el
modo 2 se quedaba a oscuras mientras el 1 encendía luces — no era un fallo. Su
estado se lee **mirándole la ventana** por la capa de accesibilidad de Windows
(`vigia_chatgpt.py`): el botón «Detener» solo existe mientras genera. De ahí
salen los dos momentos que se pueden sostener —está respondiendo y ha
terminado— y no más: desde fuera no se distingue «pensando» de «ejecutando», ni
se ve cuándo te pide permiso. Si ChatGPT renombra sus botones, el vigía se
calla en vez de inventarse un estado.

> **Codex CLI ya no se ofrece.** Su adaptador sigue en el código y quien lo
> tenga puesto sigue funcionando, pero no aparece en la lista: quien usa la
> aplicación de ChatGPT no tiene Codex, y ver un programa que no existe en el
> equipo solo confunde. Está en `agentes.CONOCIDOS`, no en `agentes.AGENTES`.

**No fiarse de lo que Windows dice sobre la conexión.** Un teclado Bluetooth
dormido aparece como «desconectado» aunque despierte a la primera escritura.
Creérselo montaba un círculo vicioso que costó una mañana: la web decía «todavía
no hay teclado» con el teclado delante, el gestor dejaba de escribirle, y como
el contacto solo se refresca escribiendo, no se refrescaba nunca. Peor aún,
`consultar_estado()` devolvía `None`, así que **el micrófono no sabía en qué
modo estaba** y dictaba donde hubiera el foco — de ahí «pulso el micrófono en el
modo 1 y se va a ChatGPT». Ahora manda la escritura: mientras el canal esté
abierto se le escribe, y si falla dos veces seguidas se suelta y se reabre solo.

**Solo un programa a la vez.** Si está abierta la aplicación oficial de AhaKey o
su `BLE_tcp_driver.exe`, tienen el teclado tomado y nosotros no entramos.
Ciérralos. (Si prefieres convivir con ellos: `--transporte puente`, que habla con
su puente por el puerto 9000.)

**Subir una imagen bloquea el teclado varios minutos.** La memoria flash se
escribe en exclusiva: ~4 s por fotograma, o sea 4-5 minutos para 60-70. Mientras
dura, las luces y los modos no responden — no está roto. La web lo avisa y deja
cancelar. No lances una subida y te olvides.

---

## Instalar en otro PC

```powershell
powershell -ExecutionPolicy Bypass -File instalar.ps1 -Host 0.0.0.0 -Clave "la-que-quieras"
```

Hace todo lo automatizable: comprueba Python, instala con soporte Bluetooth,
pone los enganches, abre el cortafuegos si va como administrador, crea la tarea
programada y arranca. Lo único manual es emparejar el teclado en Configuración ›
Bluetooth, y el script avisa si falta.

## El reparto de modos (del usuario, no el de fábrica)

| Modo | Para | Pantalla | Ranuras |
|---|---|---|---|
| 1 | Claude | `claude_0.gif`, 70 fotogramas | 10 |
| 2 | ChatGPT | | 80 |
| 3 | Cursor | `cursor.gif` | 150 |
| 4 | libre | | 220 |

**El seguimiento de la aplicación activa viene APAGADO** (`seguir_aplicacion`).
La idea es buena pero peleaba con quien elige un modo a mano: pulsabas el
micrófono en el modo de ChatGPT, volvías a la ventana de Claude para seguir
trabajando, y el teclado se iba al modo de Claude. Desde fuera parecía que el
micrófono cambiaba de modo solo. Se enciende desde Ajustes si se quiere.

**Las diez primeras ranuras son de fábrica: no escribir ahí.** Cada modo tiene 70
a partir de la 10. Está en `protocolo.ranura_inicial(modo)`.

Cada modo tiene **dueño**: el programa que manda en él. Un evento de Claude Code
no enciende la barra si el teclado está en el modo de ChatGPT — enseñaría algo
que no estás mirando. El modo 4 no tiene dueño, así que lo mueve cualquiera.

Las cuatro teclas, iguales en los cuatro modos:

| Tecla | Manda | Hace |
|---|---|---|
| K1 | `ctrl+alt+may+f13` | **dictado**: trae al frente el programa del modo y abre Win+H |
| K2 | `intro` | aceptar |
| K3 | `esc` | cancelar |
| K4 | `retroceso` | borrar |

**Si el clic no cae en el cuadro de texto de algún programa**, se ajusta por modo
en `%APPDATA%\TecladoIA\config.json`: `"alto_cuadro": 140` en ese modo son los
píxeles desde el borde inferior. Con `0` se calcula como el 10 % del alto de la
ventana, que funciona en cualquier resolución.

**El escalado de pantalla era el fallo gordo aquí.** Con Windows al 150 %,
`GetWindowRect` devuelve coordenadas virtuales y `SetCursorPos` las usa físicas:
el clic caía 325 px más arriba. `dictado.py` se declara consciente del DPI por
monitor al importarse; **no quitar esa llamada**.

**K1 no manda Win+H a secas, y es a propósito.** El dictado escribe donde esté
el foco, así que si la ventana no era la correcta lo dictado se va a cualquier
parte; y Win+H es un interruptor, de modo que si el dictado ya estaba abierto la
pulsación lo cierra —de ahí el «a veces no se activa el micrófono»—. En su lugar
manda una combinación que solo entiende TecladoIA (`dictado.py`), que enfoca el
programa del modo —abriéndolo si está cerrado— y solo entonces abre el dictado.

---

## Cómo decide (el corazón del asunto)

La palanca física del teclado gobierna a los agentes de IA. Los enganches están
puestos en `~/.claude/settings.json` (que comparten Claude Code **y** Claude
Cowork), `~/.codex/hooks.json` y compañía.

1. Un modo fijado en la configuración manda sobre todo.
2. Las reglas de `denegar` y `preguntar` ganan **siempre**, incluso con la
   palanca en automático. Ahí viven `rm -rf`, `mkfs`, `dd if=`…
3. La palanca: `0` es automático, cualquier otra cosa devuelve el control.
4. **Si la palanca no se puede leer, nunca se aprueba solo.** No saber equivale a
   preguntar. Esta regla no se toca.

---

## Trampas que ya costaron tiempo

- **`DataReader.read_bytes(x)` rellena el búfer que le pasas**; no devuelve uno
  del tamaño que pidas. Con la firma equivocada lanza `TypeError` y las
  notificaciones del teclado se pierden sin dejar rastro.
- **La característica de comando `0x7343` solo admite escritura CON respuesta.**
  Mandarle una sin respuesta no da error: simplemente no llega.
- **Hay que apuntarse al acuse ANTES de enviar el comando.** El teclado contesta
  en ~50 ms; si te apuntas después, el acuse llega sin nadie escuchando.
- **RGB565 va en big-endian.** El codificador del fabricante se llama
  `toRgb565BigEndian`. Al revés, la pantalla sale con los colores cambiados.
- **No se puede elegir el color de la luz.** El firmware solo acepta un byte con
  el número de efecto (`0x00`–`0x10`); el color va cocido dentro de cada uno.
  Comprobado en los cuatro clientes del fabricante. No prometerlo.
- **Editando archivos del Mac mini desde Windows**, `Path.write_text` mete CRLF y
  `bash` revienta. Editar en binario y validar con `bash -n` antes de subir.

---

## Dónde está todo

- **Código maestro**: `C:\Teclado Ahakey` (rama `claude/keyboard-app-spanish-pc5t9p`
  del repo `juancarlosvergaras/project-manager`).
- **Configuración**: `%APPDATA%\TecladoIA\config.json`. Ojo: los campos son
  `clave_panel` y `host_panel` (se llamaron `panel_clave`/`panel_escuchar`).
- **Código del fabricante**: `github.com/AhakeyAI/desktop`, Apache 2.0. **Mirar ahí
  antes de adivinar cualquier cosa del protocolo.** Los GIF por omisión están en
  `ahakeyconfig-mac/Resources/DefaultOLED/`.
- **Servidor**: `ssh juancarlosvergaraschmalbach@macmini`, manual en
  `~/Servidor/CLAUDE.md`. `ahakey.proyectoia.org` apunta al PC por Tailscale
  (`rutas.conf`, cuarto campo). `teclado.proyectoia.org` es la portada estática.

## Semáforo en otro aparato

`SEMAFORO.md` es autosuficiente: qué evento dispara cada momento del agente, qué
color le pega y las trampas conocidas. Dáselo a Claude en otro proyecto y podrá
montar lo mismo en otro teclado sin leer este código.

## Pruebas

```bash
python -m unittest discover -s pruebas -t .
```

123, todas verdes, sin dependencias externas. Si algo se rompe, empieza por ahí.
