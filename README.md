# TecladoIA

**Tu teclado decide qué puede hacer solo un agente de IA.**

TecladoIA es una réplica en español —escrita desde cero en Python— del cliente
de escritorio de [AhaKey](https://github.com/AhakeyAI/desktop), el teclado
AhaKey-X1 que sirve de mando para programar con inteligencia artificial. La
palanca física del teclado hace de interruptor: hacia un lado, el agente ejecuta
sus herramientas sin preguntar; hacia el otro, cada acción vuelve a tus manos.

El proyecto original está en inglés y en chino, cubre cuatro programas de IA y
reparte su código entre Swift, Java, C# y Python. Esta versión está
íntegramente en español, cubre seis programas, funciona igual en Windows, macOS
y Linux con un único código base, y no necesita ninguna dependencia para
arrancar.

```
   Codex · Claude Code · Cursor · Kimi · Gemini · el tuyo
                        │
                 enganche (hook)
                        │
            ┌───────────▼────────────┐
            │  servicio TecladoIA    │   reglas + palanca → permitir/preguntar/denegar
            │  socket · panel web    │
            └───────────┬────────────┘
                        │ BLE
                  AhaKey-X1  ⌨  palanca · barra de luz · pantalla OLED
```

---

## Qué mejora respecto al original

| | Proyecto original | TecladoIA |
|---|---|---|
| Idioma | inglés y chino | español, de la interfaz a los mensajes de error |
| Programas de IA | Claude Code, Codex, Cursor, Kimi | los cuatro, más Gemini CLI y un adaptador genérico |
| Plataformas | Swift (macOS), Java (Windows/Linux), C# (puente) | un solo código Python para los tres sistemas |
| Instalación de enganches | reescribe el bloque `hooks` entero | fusiona con los que ya tenías y hace copia de seguridad |
| Esquema de permiso de Claude | `decision: {behavior: "allow"}`, formato antiguo | `decision: "allow" \| "escalate" \| "deny"`, el vigente |
| Órdenes peligrosas | solo decide la palanca | reglas que bloquean `rm -rf`, `mkfs`, `dd if=`… aunque la palanca esté en automático |
| Trazabilidad | registros de diagnóstico sueltos | bitácora en JSONL: qué se aprobó, cuándo y por qué |
| Sin teclado a mano | no se puede usar | modo simulado completo |
| Enganches | scripts de Bash con `/dev/tcp` | una orden de Python, igual en las tres plataformas |
| Pruebas | una clase de pruebas | 97 pruebas sin dependencias externas |

Dos detalles del original que aquí están corregidos y cubiertos por pruebas: el
acuse del comando `0x90` no se confunde con una lectura de la palanca, y el
cliente de enganche nunca se queda esperando una entrada estándar que no llega
(bloquearía al agente de IA que lo invocó).

---

## Programas de IA admitidos

| Programa | Configuración | Eventos | Cómo se le impone la palanca |
|---|---|---|---|
| **Codex CLI** | `~/.codex/hooks.json` | 6 | `approval_policy` = `never` / `untrusted` en `config.toml` |
| **Claude Code** | `~/.claude/settings.json` | 9 | respuesta al enganche `PermissionRequest` |
| **Cursor** | `~/.cursor/hooks.json` | 5 | respuesta al enganche y `terminalAllowlist` |
| **Kimi CLI** | `~/.kimi/config.toml` | 7 | `default_yolo` = `true` / `false` |
| **Gemini CLI** | `~/.gemini/settings.json` | 5 | respuesta al enganche `BeforeTool` |
| **Genérico** | ninguna | 8 | lo invocas tú desde tu propio script |

Codex y Kimi leen su política de aprobación al empezar la sesión, así que
contestar al enganche no basta: TecladoIA alinea también su fichero de
configuración cada vez que la palanca cambia de posición.

---

## Instalación

Hace falta Python 3.10 o posterior. Nada más.

```bash
git clone https://github.com/juancarlosvergaras/project-manager.git
cd project-manager
pip install -e .          # o: pip install -e ".[ble]" para hablar con el teclado
```

`bleak` solo es necesario para conectarse al teclado real por Bluetooth. Sin él
todo lo demás funciona, incluido el modo simulado.

---

## Puesta en marcha

```bash
tecladoia probar          # ve cómo decide, sin teclado y sin tocar nada
tecladoia buscar          # busca tu AhaKey-X1 por Bluetooth
tecladoia instalar        # pone los enganches en los programas que tengas
tecladoia servicio        # arranca el servicio y el panel web
```

Con el servicio en marcha, abre <http://127.0.0.1:8770> y tendrás el estado del
teclado, la palanca virtual, el efecto de la barra de luz y el historial de
decisiones.

Así se ve la demo:

```
$ tecladoia probar

Con la palanca en MANUAL
  codex    ls -la         → preguntar  (La palanca está en manual: decides tú.)
  claude   rm -rf /       → denegar    (Una regla de la configuración bloquea esta acción.)
  gemini   git status     → preguntar  (La palanca está en manual: decides tú.)

Con la palanca en AUTOMÁTICO
  codex    ls -la         → permitir   (La palanca está en automático.)
  claude   rm -rf /       → denegar    (Una regla de la configuración bloquea esta acción.)
  gemini   git status     → permitir   (La palanca está en automático.)
```

---

## Cómo decide

Cada vez que un agente pide permiso, TecladoIA resuelve en este orden:

1. **Modo fijado.** Si en la configuración pusiste `siempre_preguntar` o
   `siempre_permitir`, eso manda y no se mira nada más.
2. **Reglas restrictivas.** `denegar` y `preguntar` ganan siempre, incluso con
   la palanca en automático. Aquí viven `rm -rf`, `mkfs`, `dd if=`,
   `git push --force`, `sudo`…
3. **Reglas permisivas.** Solo actúan si las activas a propósito
   (`reglas_permisivas: true`). Por omisión están apagadas: la palanca manda.
4. **La palanca.** `0` es automático; cualquier otra posición devuelve la
   decisión a la persona.

El cuarto punto guarda la regla más importante del diseño: **si la palanca no se
puede leer —porque el teclado está apagado, lejos o sin batería— nunca se
aprueba solo.** No saber equivale a preguntar. Y si el servicio no está en
marcha, el enganche imprime una respuesta neutra y el agente sigue con su propio
aviso de permiso, así que nada se queda colgado.

Las reglas se editan en `~/.tecladoia/config.json`:

```json
{
  "reglas": [
    { "patron": "rm -rf",        "decision": "denegar",   "nota": "Borrado recursivo forzado." },
    { "patron": "git push",      "decision": "preguntar", "agente": "codex" },
    { "patron": "pytest",        "decision": "permitir",  "nota": "Ejecutar pruebas es inocuo." }
  ]
}
```

El patrón se busca dentro del nombre de la herramienta, del comando y de la ruta,
sin distinguir mayúsculas. `agente` limita la regla a un solo programa.

---

## Órdenes disponibles

| Orden | Para qué |
|---|---|
| `tecladoia servicio` | arranca el servicio, el socket de enganches y el panel web |
| `tecladoia estado` | batería, firmware, transporte y posición de la palanca |
| `tecladoia buscar` | busca teclados AhaKey por Bluetooth |
| `tecladoia palanca auto\|manual\|fisica` | mueve la palanca virtual del servicio |
| `tecladoia instalar [programas]` | registra los enganches |
| `tecladoia desinstalar [programas]` | los retira sin tocar los tuyos |
| `tecladoia agentes` | qué programas hay y si tienen los enganches puestos |
| `tecladoia tecla <modo> <tecla> --atajo ctrl+may+p --texto "Paleta"` | programa una tecla |
| `tecladoia luz respiracion` | cambia el efecto de la barra de luz |
| `tecladoia bitacora -n 20` | últimas decisiones de aprobación |
| `tecladoia config [--crear]` | muestra o escribe la configuración |
| `tecladoia probar` | recorre el flujo completo con un teclado simulado |
| `tecladoia enganche <programa> <evento>` | lo llaman los programas de IA, no tú |

Añade `--sin-color` a cualquiera de ellas para una salida limpia, sin secuencias
de escape. Es lo mismo que exportar `TECLADOIA_ACCESIBLE=1` o poner
`"accesible": true` en la configuración.

---

## El teclado

TecladoIA habla el protocolo del AhaKey-X1 tal y como está documentado en el
proyecto original: tramas `AA BB [comando] [datos] CC DD` sobre el servicio BLE
`0x7340`.

- **Cuatro teclas por tres modos.** Atajos (`ctrl+may+p`), macros y una etiqueta
  de hasta 20 caracteres para la pantalla OLED. Los nombres de tecla están en
  español (`intro`, `mayus`, `supr`, `flecha_arriba`) y la distribución incluye
  la eñe, las tildes y los signos de apertura; lo que el OLED no puede dibujar se
  translitera en vez de perderse.
- **Barra de luz.** Diecisiete efectos, uno asignado por omisión a cada momento
  del agente: pensamiento azul mientras trabaja, espera de aprobación cuando
  pregunta, barrido de éxito al terminar.
- **Tres transportes.** BLE nativo con `bleak`, el puente BLE↔TCP del proyecto
  original y el teclado simulado. Con `transporte: "auto"` se elige el mejor
  disponible.

---

## Sin teclado

El modo simulado no es un juguete de pruebas: es una forma legítima de usar el
sistema. Reproduce las respuestas del firmware, la palanca se mueve desde el
panel web o con `tecladoia palanca`, y las reglas y la bitácora funcionan igual.
Sirve para probar la configuración antes de comprar el teclado, para seguir
trabajando cuando se queda sin batería y para que las 97 pruebas corran en
cualquier máquina.

```bash
tecladoia servicio --sin-teclado
```

---

## Desarrollo

```bash
python -m unittest discover -s pruebas -t .
```

Las pruebas no necesitan dependencias externas y cada una corre con su propio
`HOME`, así que nunca tocan la configuración real.

```
src/tecladoia/
├── protocolo.py      tramas y comandos del teclado
├── teclas.py         tabla HID y distribución española
├── modelo.py         estados, efectos, decisiones
├── politica.py       motor de aprobación
├── dispositivo.py    conexión y caché de la palanca
├── servidor.py       servicio de enganches
├── enganche.py       cliente que ejecutan los agentes
├── panel.py          panel web local
├── instalador.py     alta y baja de enganches
├── cli.py            línea de órdenes
├── config.py         ajustes y reglas
├── registro.py       bitácora de auditoría
├── transporte/       BLE, puente TCP y simulador
└── agentes/          un adaptador por programa de IA
```

Para añadir un programa de IA nuevo basta con crear un adaptador en `agentes/`:
declarar sus eventos, decir qué JSON espera de vuelta y dónde vive su
configuración. Lo demás ya está hecho.

---

## Licencia y créditos

Apache 2.0, la misma del proyecto original. Los detalles de la atribución están
en [`NOTICE`](NOTICE): de `AhakeyAI/desktop` proceden el protocolo BLE del
teclado, los códigos de estado de la barra de luz y la idea de usar una palanca
física como puerta de las herramientas de un agente. El código de este
repositorio es propio.

AhaKey y AhaKey-X1 son marcas de sus titulares. Este proyecto no está afiliado a
ellos ni respaldado por ellos.
