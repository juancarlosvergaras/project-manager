# Reglas del semáforo — cómo hacer que cualquier teclado siga a un agente de IA

Este archivo es autosuficiente: dáselo a Claude en otro proyecto y podrá montar
el mismo semáforo en otro aparato —un macropad, una tira LED, un Cardputer, un
ESP32— sin necesidad de leer el código de TecladoIA.

La idea es sencilla. Los programas de IA de línea de órdenes avisan de lo que
van haciendo a través de sus **enganches** (*hooks*): antes de usar una
herramienta, al terminarla, cuando necesitan permiso, cuando acaban. Si alguien
escucha esos avisos, puede encender una luz que diga en qué anda el agente sin
tener que mirar la pantalla.

---

## Los nueve momentos

Son los estados que hay que representar. El número importa solo si vas a hablar
con un AhaKey; para cualquier otro aparato, usa los que quieras.

| Nº | Momento | Qué significa | Color sugerido |
|---|---|---|---|
| 0 | Aviso | Algo reclama tu atención | ámbar parpadeando |
| 1 | Esperando aprobación | **Te está esperando a ti** | ámbar fijo o pulso |
| 2 | Herramienta terminada | Acabó una orden, sigue trabajando | verde breve |
| 3 | Herramienta en curso | Está ejecutando algo | azul en movimiento |
| 4 | Sesión iniciada | Acaba de empezar | barrido de bienvenida |
| 5 | Detenido | Se paró y espera instrucciones | blanco fijo |
| 6 | Tarea completada | **Terminó del todo** | verde |
| 7 | Petición enviada | Acabas de mandarle algo | onda al escribir |
| 8 | Sesión finalizada | Se cerró | apagado |

Los dos que de verdad importan son el **1** y el **6**: «te estoy esperando» y
«he terminado». Si solo puedes representar dos colores, que sean esos.

---

## Qué evento dispara cada momento

Aquí está la parte que cuesta averiguar. Los nombres no son intuitivos y varían
entre programas.

### Claude Code (y Claude Cowork, que comparten `~/.claude/settings.json`)

| Evento del enganche | Momento |
|---|---|
| `SessionStart` | 4 · Sesión iniciada |
| `UserPromptSubmit` | 7 · Petición enviada |
| `PreToolUse` | 3 · Herramienta en curso |
| `PostToolUse` | 2 · Herramienta terminada |
| `PermissionRequest` | 1 · Esperando aprobación |
| `Notification` | 0 · Aviso |
| `Stop` | **6 · Tarea completada** |
| `SessionEnd` | 8 · Sesión finalizada |

> **La trampa que cuesta una tarde:** no existe ningún evento «TaskCompleted».
> Claude Code dispara **`Stop`** cuando termina su turno —incluso cuando termina
> porque te está preguntando algo—. Si mapeas `Stop` a «detenido», el verde de
> «he terminado» no se enciende nunca.

### Codex CLI
`~/.codex/hooks.json`. Eventos `CodexSessionStart`, `CodexPreToolUse`,
`CodexPostToolUse`, `CodexStop`, con el mismo reparto.

### Cursor y Gemini CLI
`~/.cursor/hooks.json` y `~/.gemini/settings.json`. Cursor usa `beforeShellExecution`
y Gemini `BeforeTool`, ambos equivalentes a `PreToolUse`.

### Los que NO avisan: hay que mirarlos

**Las aplicaciones de escritorio —ChatGPT, Claude en su ventana propia— no
tienen enganches ni forma de tenerlos.** No esperes eventos que no van a llegar.

Pero no todo está perdido: se les puede **mirar**. Windows publica una capa de
accesibilidad —la de los lectores de pantalla— y estas aplicaciones, que son
Chromium por dentro, exponen ahí sus botones con su nombre. Basta encontrar uno
que solo exista en un estado. En ChatGPT es **«Detener»**, que aparece mientras
genera la respuesta y desaparece al terminar:

```
hay boton «Detener»      -> 3 · Herramienta en curso
lo habia y ya no         -> 6 · Tarea completada
no se reconoce ninguno   -> callarse
```

Tres cosas que hacen que esto sea sostenible y no un truco frágil:

1. **Margen antes de dar por terminado.** El botón parpadea entre bloques de
   texto; sin un par de segundos de gracia cantarías «terminado» cada dos
   frases.
2. **Callarse cuando no se reconoce nada.** Si un día renombran los botones,
   más vale una luz apagada que una que miente.
3. **Confirmar que estás leyendo lo que crees.** Busca también el botón de
   enviar: si no ves ni uno ni otro, la ventana no está donde crees.

Y lo que esta vía **no** da, para no prometerlo: no distingue «pensando» de
«ejecutando una herramienta», y no ve cuándo te piden permiso —eso vive dentro
de la conversación, no en un botón—. Es la mitad del semáforo, pero es la mitad
que se puede sostener.

---

## Cómo enganchar (Claude Code)

En `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "tu-programa avisar Stop" } ] }
    ],
    "PreToolUse": [
      { "hooks": [ { "type": "command", "command": "tu-programa avisar PreToolUse" } ] }
    ]
  }
}
```

Tres reglas que no son opcionales:

1. **Fusiona, no sobrescribas.** Ese archivo puede tener enganches de otras
   cosas. Léelo, añade los tuyos y guarda; y haz copia antes.
2. **Termina rápido y siempre.** El enganche bloquea al agente mientras corre.
   Si tu programa tarda o se cuelga, cuelgas al agente. Pon un plazo y ríndete.
3. **No leas la entrada estándar sin comprobar que hay algo.** Si te quedas
   esperando un fin de fichero que no llega, bloqueas al agente para siempre.

Para permisos, el enganche debe **imprimir** su respuesta en la salida estándar:

```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                        "decision": "allow",
                        "permissionDecisionReason": "por qué"}}
```

`decision` admite `allow`, `escalate` (pregúntale a la persona) y `deny`.

---

## La regla de oro

**Si no puedes saber si algo es seguro, pregunta.** Ante la duda, `escalate`.

En TecladoIA esto se concreta así, y conviene copiarlo:

1. Un modo fijado en la configuración manda sobre todo.
2. Las reglas de **denegar** y **preguntar** ganan siempre, incluso en
   automático: `rm -rf`, `mkfs`, `dd if=`, `git push --force`, `sudo`…
3. Después decide el interruptor físico.
4. **Si el interruptor no se puede leer** —el aparato está apagado, lejos o sin
   batería— **nunca se aprueba solo.** No saber equivale a preguntar.

El cuarto punto es el que hace que todo esto sea defendible. Sin él, quedarse
sin batería equivaldría a dar permiso para todo.

---

## Dos cosas que se ven feas si no las haces

**Vuelve al reposo.** La luz refleja el último evento, y si nadie apaga nada se
queda encendida para siempre. Acabas una tarea, se pone verde, te vas a otro
programa, y una hora después sigue verde diciendo algo que ya no es verdad. Pon
un plazo —veinte o treinta segundos sin noticias— y apágala.

**No mezcles programas.** Si el aparato tiene modos y cada uno es para un
programa distinto, un evento de Claude no debe encender la luz mientras estás
mirando el modo de ChatGPT. Filtra por el dueño del modo activo.

---

## Lo mínimo que funciona

Si solo quieres empezar:

```
Stop              -> verde        (terminó)
PermissionRequest -> ámbar        (te espera)
PreToolUse        -> azul         (trabajando)
sin eventos 25 s  -> apagado
```

Con eso ya se entiende de un vistazo qué pasa, y es la mitad del valor con una
décima parte del trabajo.
