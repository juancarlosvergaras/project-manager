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

> **Ojo con «Detener dictado».** El vigía busca botones que empiecen por
> «detener», y al hablarle al micrófono aparece justo uno así. Sin excluirlo
> (`NO_SON_DETENER`), dictar encendía el azul de «está respondiendo» en el
> mismo segundo en que arrancaba el dictado, y desde fuera parecía que ChatGPT
> contestaba solo. Claude hace lo mismo con su botón.

> **Codex CLI ya no se ofrece.** Su adaptador sigue en el código y quien lo
> tenga puesto sigue funcionando, pero no aparece en la lista: quien usa la
> aplicación de ChatGPT no tiene Codex, y ver un programa que no existe en el
> equipo solo confunde. Está en `agentes.CONOCIDOS`, no en `agentes.AGENTES`.

**El teclado entra en el modo que recuerda, no en el 1.** Eso es firmware suyo:
al encenderse vuelve al último modo que tuvo. Si quieres empezar siempre en uno
concreto, `modo_al_conectar` en la configuración (0-3, o `null` para respetar el
que traiga).

**La señal para reponerlo es una escritura fallida, no una lectura.** Cuesta
llegar a esto y costó varias vueltas. Lo obvio —esperar a que la conexión pase
de «no» a «sí»— **no sirve**, porque un teclado cuenta como vivo durante
`VIGENCIA_DEL_CONTACTO_S` (45 s) desde el último contacto: si lo apagas y lo
enciendes deprisa, esa transición nunca ocurre. Y nadie espera tres cuartos de
minuto entre una cosa y otra, así que el caso que se escapaba era el único que
pasa de verdad. Preguntarle al teclado tampoco vale. Lo que sí delata el corte
es la escritura que falla al apagarlo (`WinError -2147023673`, «El usuario ha
cancelado la operación»): se anota en `_hubo_corte` y en cuanto vuelve a
contestar se le repone el modo. Del apagado a la reposición van dos segundos.

**Y el mismo camino le apaga la barra, con el reposo que toca.** Ojo aquí: el
teclado **enciende con el último efecto que tuvo**, lo guarda en su memoria
igual que el modo. Se le manda `ESTADO_EN_REPOSO` (Detenido → «Centro fijo») a
través de `servidor.reponer_la_barra()`, forzado, porque lo que nosotros
creamos que hay puesto no vale de nada. **No mandar `SESION_FINALIZADA` para
esto**: está mapeado al barrido de éxito, que es verde, así que el mensaje que
debía apagar la barra era justo el que la encendía — de ahí el «arranca en
verde» que despistó una tarde. Que haya un solo camino para dejar la barra en
reposo no es limpieza: tener dos fue lo que permitió que uno de ellos la
encendiera sin que nadie lo notara.

**No fiarse de lo que Windows dice sobre la conexión.** Un teclado Bluetooth
dormido aparece como «desconectado» aunque despierte a la primera escritura.
Creérselo montaba un círculo vicioso que costó una mañana: la web decía «todavía
no hay teclado» con el teclado delante, el gestor dejaba de escribirle, y como
el contacto solo se refresca escribiendo, no se refrescaba nunca. Peor aún,
`consultar_estado()` devolvía `None`, así que **el micrófono no sabía en qué
modo estaba** y dictaba donde hubiera el foco — de ahí «pulso el micrófono en el
modo 1 y se va a ChatGPT». Ahora manda la escritura: mientras el canal esté
abierto se le escribe, y si falla dos veces seguidas se suelta y se reabre solo.
La distinción está en `canal_abierto` («¿merece la pena intentarlo?») frente a
`conectado` («¿consta vivo?»): **el latido se gobierna con el primero**. Con el
segundo se moría solo.

**COM tiene que pedirse en MTA, y antes de importar nada.** Está en la primera
línea de `tecladoia/__init__.py` (`sys.coinit_flags = 0`) y **no se toca**. Era
la causa raíz de toda la saga de conexiones, y se disfrazaba de cinco fallos
distintos: «todavía no hay teclado» con el teclado delante, la barra clavada en
verde, el modo sin volver al 1, el micrófono dictando en la ventana equivocada,
y apagar el teclado una vez para perderlo hasta reiniciar.

La explicación: `comtypes` —la capa de accesibilidad, que es como se encuentra
el cuadro de escribir de Claude o ChatGPT— inicializa COM en apartamento **STA**
si nadie dice lo contrario. Y desde ese momento **las operaciones asíncronas de
WinRT no vuelven jamás en ese hilo**: no fallan, no dan error, simplemente no
terminan. Como el Bluetooth va por WinRT, el servicio perdía el teclado en
cuanto le tocaba usar accesibilidad una vez —o sea, en cuanto pulsabas el
micrófono—. De ahí el síntoma que despistaba: un proceso recién arrancado abría
el teclado en tres décimas y el servicio no lo conseguía en veinte minutos.

Si `comtypes` se importa antes de fijar la bandera, ya no hay nada que hacer.
Lo cubre `pruebas/test_conexion.py`, que además comprueba el orden.

**Y ningún paso de WinRT tiene plazo propio.** `from_id_async` y la lectura de
servicios se quedan esperando para siempre con el teclado apagado. Eso dejó el
servicio mudo una tarde entera: al apagarlo se soltó el canal —correcto— y el
intento de reabrirlo se colgó dentro de WinRT, así que el bucle de reconexión no
volvió a dar una vuelta. Sin los plazos, apagar el teclado **una sola vez**
obliga a reiniciar el servicio. Están en `PLAZO_DE_BUSQUEDA_S`,
`PLAZO_DE_APERTURA_S` y `PLAZO_DE_RECONEXION_S`; no quitarlos. Lo cubre
`pruebas/test_conexion.py`.

**Solo un programa a la vez.** Si está abierta la aplicación oficial de AhaKey o
su `BLE_tcp_driver.exe`, tienen el teclado tomado y nosotros no entramos.
Ciérralos. (Si prefieres convivir con ellos: `--transporte puente`, que habla con
su puente por el puerto 9000.)

**Subir una imagen bloquea el teclado varios minutos.** La memoria flash se
escribe en exclusiva: ~4 s por fotograma, o sea 4-5 minutos para 60-70. Mientras
dura, las luces y los modos no responden — no está roto. La web lo avisa y deja
cancelar. No lances una subida y te olvides.

---

## MiniMic — el segundo teclado (misma carpeta, paquete `src/minimic`)

Teclado de voz de cinco teclas con micrófono dentro (chip Jieli, «Teclado de
Entrada de Voz» de AliExpress). Aplicación hermana de TecladoIA: reutiliza
`tecladoia.dictado`, `cuadro_de_texto`, `sonido` y `sucesos` tal cual, y pone
debajo su propio teclado. Panel en <http://100.79.52.120:8771> y, por el
portero del Mac mini (puerto 8025, `com.jcvs.minimic-portero`), en
<https://minimic.proyectoia.org>. Tarea programada **MiniMic**.

```bash
python -m minimic servicio --host 100.79.52.120      # arrancar
python -m minimic estado                              # ¿está? ¿por dónde va el teclado?
python -m minimic teclas                              # leer el mapa (solo por cable)
python -m unittest pruebas.test_minimic_protocolo pruebas.test_minimic_servicio
```

**Dos aparatos USB, uno solo se configura.** Por cable es `514C:8850`, con la
interfaz de fabricante (página 0xFF00) por la que se leen y escriben las
teclas. Por el receptor de 2,4 GHz es `4C4A:4155`: teclas y micrófono
funcionan, configurar no. La aplicación detecta los dos (`dispositivo.presencia`)
y solo escribe cuando hay cable. Por Bluetooth («MINI_KEYBOARD») no se usa.

**El protocolo es propio y lleva suma de control.** Se sacó con Frida del
programa del fabricante (`LQ_Keyboard.exe`, en `Windows/`, en chino; con
`Language=en` en su `Config.ini` sale en inglés). Paquete de 64 bytes
`03 <orden> <capa> <arg> <len> <carga…>` y **XOR de los bytes 1..62 en el
byte 63**; sin él contesta `03 07` (rechazo) a todo. El acuse es `03 06` y
**ni el acuse ni el rechazo llevan longitud**: traen un eco. Está todo en
`minimic/protocolo.py`, con las capturas reales como pruebas. Los protocolos
del `ch57x-keyboard-tool` **no valen** aunque el PID coincida: se probaron
todos antes de encontrar el bueno.

**La tecla blanca manda `Ctrl+Mayús+Alt+F14`**, no F13: el AhaKey ya tiene
F13 y Windows solo deja reservar cada combinación a un proceso. Al ver el
teclado por cable, el servicio compara lo grabado con `ajustes.teclas` y
escribe la diferencia (`servicio.asegurar_teclado`); así la blanca queda con
esa combinación y el modo del micrófono en «pulsar para empezar y parar».
`EscuchaDictado` de TecladoIA ganó dos parámetros (`tecla_virtual`, `nombre`)
para esto; por defecto sigue igual.

**El micrófono del teclado se pone como micrófono del sistema** cuando
aparece (`adoptar_microfono`), porque el dictado de Windows escucha por el
predeterminado y sin eso se habla al portátil. Se identifica por el
**identificador de contenedor**, que Windows da igual al aparato USB (en el
registro, `Enum\USB\VID…\<serie>\ContainerID`) y a su punto de audio
(propiedad `{8c7ed206-…},2`, tipo VT_CLSID: `pycaw` no la desempaqueta y se
lee el puntero a mano en `dispositivo._guid_de`). Cambiarlo usa la interfaz no
documentada `IPolicyConfig`, la misma que usa el propio panel de sonido.

**El micrófono propio del programa también manda aquí** (`usar_microfono_propio`,
encendido de fábrica): la tecla blanca pasa por `Dictado.usar_el_propio`, así que
con Claude o ChatGPT pulsa su botón de dictado y solo cae a Win+H si no lo hay. El
micrófono de este teclado falla mucho con Win+H; con el botón del programa no.

**Config en `%APPDATA%\MiniMic\config.json`** (`MINIMIC_INICIO` la cambia;
las pruebas la aíslan). Misma trampa del AppData redirigido que TecladoIA:
desde una sesión de Claude no se escribe la de verdad. La clave del panel se
pone desde el propio panel abierto en local, que la guarda el servicio.

## SikaiMini — el tercer teclado (misma carpeta, paquete `src/sikaimini`)

Mini teclado blanco de **SiKai** (sikaiglobal.com): tres teclas —No ✗, Sí ✓ y
micrófono—, una **perilla** con giro y pulsación, micrófono dentro, luz bajo
la base translúcida, interruptor de encendido y receptor de 2,4 GHz. Panel en
<http://100.79.52.120:8772> y, por el portero del Mac mini (puerto 8026,
`com.jcvs.sikaimini-portero`), en <https://sikaimini.proyectoia.org>. Tarea
programada **SikaiMini**. Clave `Unicartagena1`, cabecera `X-SikaiMini-Clave`.

```bash
python -m sikaimini servicio --host 100.79.52.120   # arrancar
python -m sikaimini estado                           # ¿está? ¿por dónde va?
python -m sikaimini teclas                           # piezas y luces (solo por cable)
python construir_sikaimini.py                        # dist/SikaiMini.zip
python -m unittest pruebas.test_sikaimini_protocolo pruebas.test_sikaimini_servicio
```

**Es el mismo chip Jieli que el MiniMic, con el mismo VID/PID** (514C:8850 por
cable, 4C4A:4155 por el receptor) **y el mismo protocolo LQ**. Por eso
`sikaimini` importa de `minimic` el protocolo, el canal HID, la presencia y el
manejo del micrófono, y pone encima lo suyo. Lo que cambia, comprobado el
4/9/2026 contra el aparato y espiando `LQ_Keyboard.exe` con Frida:

- **Seis registros en una sola capa**: 0-2 las teclas, 3-5 la perilla (giro A,
  giro B, pulsación). Las capas 1 y 2 devuelven rechazo.
- **Dos tipos de registro más**: multimedia (`0x02`, uso *Consumer* de dos
  bytes, bajo primero: `e9 00` es Vol+) y **ratón** (`0x03`, un byte). La tabla
  de ratón se sacó pulsando uno a uno los botones de la pestaña «Mouse» del
  programa del fabricante con `pywinauto`: `00` clic, `01` derecho, `02`
  central, `03` rueda arriba, `04` rueda abajo, `05-0a` rueda con Ctrl, Mayús y
  Alt, `0b-0e` gestos, `0f` «me gusta». Está en `protocolo.RATON`.
- **Luces**: `0x0A` lee y **`0x09` escribe**, con arg `0xFE` y 52 bytes:
  `[modo][R][G][B]` y una paleta de 16 colores. El teclado acusa y devuelve lo
  escrito al releer. El programa del fabricante esconde la pestaña de luces para
  este modelo, así que **qué hace cada modo se descubre mirando el teclado**; la
  pestaña «Luces» del panel es para eso. Con `luces_modo = -1` no se tocan.

**Cómo se distinguen los dos teclados**: solo leyéndolos. El MiniMic contesta
cinco registros y el SiKai seis. `leer_capa` de cada aplicación exige su número
y se niega con el otro, así que **ninguna le escribe al teclado de la otra**
(probado en `test_sikaimini_servicio`). Por el receptor no se puede leer; lo
que hacen las dos con un receptor —adoptar el micrófono, esperar su tecla— es
inofensivo por duplicado.

**La tecla del micrófono manda `Ctrl+Mayús+Alt+F15`** (F13 es del AhaKey, F14
del MiniMic). **La perilla queda como rueda del ratón**: giro A → rueda abajo,
giro B → rueda arriba, pulsación → clic central. Si desplaza al revés, se
cambian los dos giros entre sí desde el panel. De fábrica traía Vol+, Vol− y
Alt derecho.

**El PC se presenta solo al portero (túnel de salida).** Desde el 4/9/2026 por
la tarde, `sikaimini.proyectoia.org` no va a buscar el PC: el servicio abre por
Tailscale una conexión de control a `100.65.52.65:8027` (la dirección de
Tailscale del Mac mini), dice qué equipo es y si tiene el teclado, y cuando
llega un navegador el portero le pide una conexión de datos y las empalma.
Nada que configurar en el PC: ni publicar el panel, ni cortafuegos, ni que el
Mac mini sepa su dirección. Está en `minimic/tunel.py` (genérico, para que
MiniMic lo use también) y en `despliegue/sikaimini/portero.py`; el camino
viejo de preguntar a direcciones fijas queda de respaldo. **Dos condiciones**:
Tailscale conectado y **clave puesta en el panel** —sin clave el servicio no se
presenta, porque lo que entra por el túnel viene de Internet—. Y una trampa
resuelta: las conexiones de datos hacia el panel salen **desde `127.0.0.2`**,
porque el panel deja pasar sin clave lo que llega de `127.0.0.1`, y por el
túnel llegaría Internet entera como si fuera local. Lo cubre
`pruebas/test_tunel.py`, que levanta el portero de verdad en local.

**El panel local no pide clave y escucha siempre en `127.0.0.1`**, aunque esté
publicado en Tailscale (los tres teclados). La clave es para quien entra desde
fuera. El instalador deja un acceso directo al panel en el escritorio y lo abre.

**La misma trampa de `AppData`** que TecladoIA y MiniMic, con una vuelta más:
la carpeta real `AppData\Roaming\SikaiMini` no existe hasta que algo la crea
**fuera** de la sesión de Claude, y la tarea programada redirige su registro a
esa carpeta, así que sin ella `cmd` no puede abrir el archivo y el servicio
muere sin dejar rastro. La primera vez se crea con
`python ajustar_config.py --app SikaiMini clave_panel=… host_panel=…` a través
de una tarea. Y **`schtasks /Run` desde Git Bash no funciona**: convierte
`/Run` en una ruta. Usar PowerShell.

---

## Que arranque con Windows

Hay una tarea programada llamada **TecladoIA** que lo lanza al iniciar sesión,
con veinte segundos de margen, y escribe todo en
`%APPDATA%\TecladoIA\servicio.log`. Para manejarla:

```bash
schtasks /Run /TN TecladoIA     # arrancar ahora
schtasks /End /TN TecladoIA     # parar
```

Dos disparadores, y los dos hacen falta: **al iniciar sesión** y **cada diez
minutos**. El de sesión se pierde a veces —arranques rápidos, sesiones que se
restauran en vez de abrirse— y te encuentras el panel caído sin saber por qué.
Repetir es inofensivo porque **el servicio se niega a arrancar si ya hay otro
vivo** (se le pregunta al que hubiera; mirar si el puerto está ocupado no
distingue entre otro TecladoIA y cualquier otro programa). Sin esa
comprobación, el disparador repetido crearía copias sin parar — y dos copias se
pelean por el teclado, la segunda no consigue la tecla del micrófono, y el
panel que abres no es el que manda.

**Arranca con `pythonw.exe`, sin consola.** El servicio se moría con un `^C` en
el registro cada pocas horas: vivía en una ventana de consola minimizada y algo
—o alguien— le mandaba una interrupción. Sin consola no hay a quién
interrumpir. La salida sigue yendo al registro porque la redirección la hace
`cmd`, no la consola.

**Y ojo con las comillas del comando de la tarea**: van tal cual, sin barras.
`cmd` no entiende `\"` como comilla escapada, y con ellas el comando entero
queda inválido. La tarea disparaba puntual y no arrancaba nada, que desde fuera
es indistinguible de un disparador averiado.

**El servicio no debe depender de una sesión de Claude abierta.** Y ojo con
esto, que costó una tarde: **la aplicación de Claude está empaquetada, así que
Windows le redirige `AppData` a su propia carpeta**
(`AppData\Local\Packages\Claude_…\LocalCache\Roaming`). Lo que Claude guarde
en la configuración se queda ahí y el servicio arrancado por la tarea —que no
está redirigido— **nunca lo ve**. Los dos leen la misma ruta y son archivos
distintos, y ni desactivando el aislamiento de la herramienta se ve el de
verdad: la redirección la hace Windows, no la herramienta.

El síntoma era desconcertante: el panel rechazaba la clave correcta, con el
registro diciendo «clave puesta» y señalando el archivo bueno. Se destapó
apuntando la **huella** de la clave —longitud y dos últimos caracteres— y el
tamaño del archivo: 5579 bytes de un lado, 1896 del otro, misma ruta.

Para escribir en la configuración de verdad desde Claude está
`ajustar_config.py`, que **se ejecuta a través de la tarea programada** (esa sí
escribe donde toca):

```bash
python ajustar_config.py clave_panel=Unicartagena1 modo_al_conectar=0
```

La carpeta del proyecto **no** está redirigida, así que los cambios de código sí
llegan con normalidad. Solo `AppData` engaña.

## El ejecutable

```bash
python construir_exe.py
```

Deja `dist/TecladoIA.exe`, unos 27 MB, **con Python dentro**: en el ordenador
nuevo no hace falta instalar nada antes. Esa es su razón de ser — `instalar.ps1`
funciona, pero empieza comprobando que hay Python y esa comprobación falla justo
en los equipos donde más falta hace la ayuda.

Abierto sin argumentos hace la instalación guiada (`asistente`); con argumentos
se comporta como la orden `tecladoia`, así que la tarea programada lo lanza con
`TecladoIA.exe servicio --host …`. El panel lo ofrece en la pestaña
**Descargar**, y si no está construido enseña el botón apagado explicando cómo
hacerlo, en vez de dar un error al pulsarlo.

Dos cosas de la receta que **no se pueden quitar** (`construir_exe.py`):

- **La carpeta `web` viaja dentro**, en la misma ruta relativa. Sin eso el
  ejecutable arranca y sirve un panel en blanco.
- **`winrt` se incluye a mano.** Sus módulos se importan por nombre en tiempo de
  ejecución, así que PyInstaller no los ve al analizar el código. Sin ellos el
  ejecutable arranca, funciona todo... y no encuentra el teclado nunca, sin
  decir por qué.

`dist/` y `build/` están fuera del repositorio: 27 MB de binario no van en git.

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

**Entre herramienta y herramienta la barra no se apaga.** El agente sigue
trabajando, así que «herramienta terminada» vuelve a «en curso» y no a reposo.
Antes parpadeaba azul-apagado veinte veces por turno —de unos cincuenta y cinco
eventos de una sesión real, cuarenta y siete eran esos dos— y tanto movimiento
para no decir nada ahogaba los dos momentos que sí importan: te espera, y ha
terminado. El reposo de verdad lo pone `Stop` o el vigilante de inactividad.

**Manos libres** (`manos_libres`, apagado de fábrica): cuando el agente que
manda en el modo puesto **termina su turno**, el micrófono se abre solo y avisa
con dos pitidos. Con la palanca arriba —que envía al cerrar— eso cierra el
círculo: hablas, trabaja, termina, y te vuelve a escuchar sin que toques nada.

Tres reglas lo hacen usable en vez de molesto, y las tres están probadas en
`pruebas/test_manos_libres.py`:

1. Solo lo dispara **el dueño del modo puesto**, la misma regla que la barra de
   luz. Que Claude termine no te abre el dictado sobre ChatGPT: lo que dictaras
   se iría a la conversación equivocada.
2. Solo al **terminar del todo** (`Stop`), no en cada herramienta.
3. **Abre, nunca alterna.** Si ya estabas hablando, no toca nada: quien llama no
   es tu dedo sino un agente, y alternar te cerraría el micrófono a media frase.

Los pitidos se silencian aparte (`pitidos_manos_libres`) — hay quien quiere el
micrófono automático y no quiere el ruido. Suenan **antes** de abrir, porque
abrir tarda, y avisarte después sería avisarte de algo que lleva un segundo
grabando sin ti.

**Si el clic no cae en el cuadro de texto de algún programa**, se ajusta por modo
en `%APPDATA%\TecladoIA\config.json`: `"alto_cuadro": 140` en ese modo son los
píxeles desde el borde inferior. Con `0` se calcula como el 10 % del alto de la
ventana, que funciona en cualquier resolución.

**El escalado de pantalla era el fallo gordo aquí.** Con Windows al 150 %,
`GetWindowRect` devuelve coordenadas virtuales y `SetCursorPos` las usa físicas:
el clic caía 325 px más arriba. `dictado.py` se declara consciente del DPI por
monitor al importarse; **no quitar esa llamada**.

**La primera pulsación tras arrancar parte de cero a propósito.** El dictado de
Windows sobrevive a nuestros reinicios y nuestra memoria no: si el servicio se
reinicia con el panel abierto, arranca creyéndolo cerrado y esa primera Win+H
lo cierra en vez de abrirlo. De ahí el «la primera vez que lo pulso no se
activa», que después ya iba bien porque las cuentas volvían a cuadrar. Se
resuelve imponiendo la posición en vez de averiguarla: un Escape antes de la
primera apertura, que cierra si estaba abierto y no hace nada si no.

**Y los primeros intentos de conexión van seguidos** (`INTENTOS_IMPACIENTES`,
`INTERVALO_IMPACIENTE_S`). Mientras no hay teclado, la barra sigue con el color
que el aparato recordaba y el modo es el suyo, no el que pediste — y esperar
doce segundos entre intentos convertía un enganche de tres segundos en uno de
catorce. En ese hueco parece que el teclado va por libre. Pasados los primeros,
se vuelve al ritmo tranquilo: si está apagado de verdad, insistir toda la noche
no lo enciende.

**Se prefiere el micrófono del propio programa** (`usar_microfono_propio`, de
fábrica encendido). Claude y ChatGPT traen dictado dentro y publican su botón en
la capa de accesibilidad con el patrón `Toggle`, así que **se le puede preguntar
si está grabando** además de pulsarlo. Ahí está la diferencia de fondo: Win+H es
un interruptor a ciegas —el panel de Windows no es una ventana ni se asoma a la
accesibilidad— y casi todos los males del micrófono venían de tener que adivinar
su posición. Con el botón propio no se adivina: se pregunta, y su estado manda
sobre nuestras cuentas.

Una trampa al leerlo: cuando un elemento **no** admite un patrón,
`GetCurrentPattern` no devuelve `None` sino un **puntero nulo**, que en Python
pasa cualquier comprobación ingenua y revienta después con «NULL COM pointer
access» sin decir de dónde viene. Hay que pedir el interruptor de verdad. Y tras
pulsarlo, el estado tarda un momento en reflejarse (`ESPERA_DEL_ESTADO_S`):
preguntarle enseguida devuelve el valor viejo y parece que no obedeció.

**Cada programa lo cuenta a su manera** y hay que hablar los dos idiomas
(`microfono_propio.PERFILES`):

- **Claude**: un solo botón con patrón `Toggle`, que además **se renombra**. En
  reposo es «Mantén presionado para grabar»; grabando pasa a «Detener dictado».
  Buscando solo el primer nombre, en cuanto empieza deja de encontrarse y
  parece que el programa se quedó sin dictado. **Y hay otro Claude** (visto el
  4/9/2026 por el túnel en el PC del usuario): sin interruptor, con un botón
  «Dictar» normal que al grabar se cambia por «Detener dictado», como ChatGPT.
  El perfil prueba primero el interruptor y, si no está, cae a botón y
  presencia. «Entrada de voz» es el modo de voz, no el dictado: no tocarlo.
  Para ver cómo se llaman los botones de un PC lejano: `GET /api/botones`
  del panel de SikaiMini (con clave), por el túnel.
- **ChatGPT**: no publica `Toggle`; **cambia de botones**. Parado enseña
  «Dictar»; grabando salen «Detener dictado», «Transcribir y enviar» y
  «Cancelar dictado». El estado se lee por presencia. Y su «Transcribir y
  enviar» es justo lo de la palanca arriba, hecho por él, que sabe cuándo ha
  terminado de transcribir — mejor que nuestro medio segundo y un Intro a ver.

**El botón antes que el atajo, y parece al revés.** ChatGPT tiene su propio
`Ctrl+Mayús+D` —lo enseña en su globito—, pero va de respaldo: pulsar un botón
por accesibilidad **no necesita la ventana al frente** y un atajo de teclado sí.
Nosotros enfocamos el cuadro de escribir por accesibilidad, que no siempre trae
la ventana adelante, así que el atajo se iba a cualquier otra parte y en el
registro quedaba «se le pidió arrancar y siguió parado». Con el botón va
directo al programa. Claude no tiene este problema porque su camino ya era el
botón.

Se pregunta **dos veces** (`estado(intentos=2)`): son Chromium por dentro y su
árbol tarda un instante en reasentarse justo después de arrancar o parar, que
es cuando más falta hace leerlo.

Si el programa no lo tiene, o le cambia el nombre al botón, queda Win+H, que
funciona en cualquier sitio aunque sea a ciegas.

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

**La palanca física de este teclado se rompió** (agosto de 2026), así que se
fija desde la pestaña Palanca del panel. Se guarda en `palanca_fija` (0 arriba,
1 abajo, `null` para hacer caso al teclado) y **se aplica al arrancar**: en
memoria se perdía en cada reinicio, que es justo cuando más duele si no tienes
otra forma de moverla.

Que se pueda fijar a distancia no contradice el punto 4, lo complementa: la
regla dice que no se apruebe solo cuando **no se sabe**, y aquí sí se sabe —lo
has dicho tú—. Lo que no cambia es que `denegar` y `preguntar` siguen ganando
siempre, con la palanca donde sea.

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
- **Los botones se buscan por palabra entera, no por subcadena.** El botón
  de dictado de Claude es «Mantén presionado para grabar» / «Hold to record»,
  y `record` está dentro de «**Record**ado una memoria…», que es como Claude
  resume una sesión en su barra lateral. Ese botón sale antes, no tiene
  interruptor, y con él elegido el dictado caía a Win+H en Claude sin decir
  por qué (4/9/2026, con los tres teclados a la vez). `microfono_propio` ya
  exige palabra entera y, para el interruptor, el primer botón que lo tenga.
- **Ni un solo `\\` dentro de un heredoc de la consola de Claude.** La
  herramienta Bash convierte `\\` en `\` antes de ejecutar, así que un
  script de Python pegado por heredoc que escribe `"\\n"` en un archivo acaba
  escribiendo un salto de línea real. Así llegó un error de sintaxis a los tres
  instaladores (4/9/2026): `SikaiMini.exe` moría al abrirse, el servicio viejo
  seguía vivo y la «actualización» no cambiaba nada. Los scripts con barras se
  escriben a un archivo con la herramienta Write y se ejecutan desde ahí.
  `pruebas/test_importa_todo.py` importa todos los módulos para cazar esto.
- **Reinstalar encima tiene que parar el servicio viejo.** El nuevo se niega a
  arrancar si ya hay otro vivo (a propósito, por el disparador repetido), así
  que sin pararlo antes uno se queda con el código anterior creyendo que
  actualizó. Los asistentes de SikaiMini y MiniMic lo hacen
  (`detener_servicios_anteriores`); el de TecladoIA todavía no.
- **Cloudflare guarda en caché los `.zip` y `.exe` de `teclado.proyectoia.org`**
  (`cf-cache-status: HIT`): subir un archivo nuevo con el mismo nombre no
  cambia lo que la gente baja hasta que caduque. Por eso el nombre con versión
  no es capricho, y los enlaces a `MiniMic.zip` y `TecladoIA.exe` llevan `?v=`
  en la portada. Comprobar siempre con `curl -D -` que el tamaño servido es el
  del archivo subido.
- **Los zips llevan la versión en el nombre** (`SikaiMini-0.1.2.zip`, con copia
  `SikaiMini.zip` para los enlaces fijos): hubo cuatro zips iguales en un día y
  no había forma de saber cuál tenía instalado el usuario. La versión sale
  también en Ajustes › «El servicio».
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

## El portero del Mac mini

`ahakey.proyectoia.org` **no lleva directamente a este PC**: pasa antes por un
portero en el Mac mini (`~/Servidor/apps/ahakey/portero.py`, puerto 8024, con
launchd `com.jcvs.ahakey-portero`). Si el PC contesta, se aparta y deja pasar
todo tal cual; si no, sirve una página que explica que el ordenador del teclado
está apagado, en vez del «Bad gateway» de Cloudflare, que parece un servidor
roto.

Es un proxy de nivel TCP a propósito: no interpreta HTTP, solo empalma los dos
extremos, así que las descargas grandes y el canal de sucesos en vivo funcionan
sin tratarlos aparte.

En `rutas.conf` la línea es `ahakey 8024 publico` —sin cuarto campo, porque
ahora el destino es el propio Mac mini—. La copia previa está en
`rutas.conf.antes-del-portero`.

Esto hace que la **página** responda siempre; el **teclado** sigue necesitando
el PC encendido. El Bluetooth no viaja por Internet.

El portero de **sikaimini** (8026) es distinto: además del camino de
preguntar a direcciones fijas, escucha en `100.65.52.65:8027` a los PC que se
presentan solos (ver la sección de SikaiMini). Los instaladores de los tres
teclados se sirven estáticos desde `teclado.proyectoia.org/descargas/`
(carpeta `apps/teclado/public/descargas` del Mac mini): bajar por el PC del
teclado tardaba 47 s y exigía tenerlo encendido.

## Semáforo en otro aparato

`SEMAFORO.md` es autosuficiente: qué evento dispara cada momento del agente, qué
color le pega y las trampas conocidas. Dáselo a Claude en otro proyecto y podrá
montar lo mismo en otro teclado sin leer este código.

## Pruebas

```bash
python -m unittest discover -s pruebas -t .
```

265, todas verdes, sin dependencias externas. Si algo se rompe, empieza por ahí.
