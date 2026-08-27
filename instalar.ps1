# =====================================================================
#  TecladoIA — instalación en un PC con Windows
#
#  Pulsa el botón derecho sobre este archivo y elige «Ejecutar con
#  PowerShell», o desde una terminal:
#
#      powershell -ExecutionPolicy Bypass -File instalar.ps1
#
#  Hace todo lo que se puede hacer solo: comprueba Python, instala la
#  aplicación, pone los enganches en los programas de IA que encuentre,
#  elige la clave del panel, abre el cortafuegos si hace falta y deja el
#  servicio arrancando con el equipo.
#
#  Lo único que no puede hacer por ti es emparejar el teclado: eso se hace
#  una vez en Configuración › Bluetooth, y el script te avisa si falta.
# =====================================================================

param(
    [string]$Clave = "",
    [string]$Host  = "",
    [switch]$SinTareaProgramada,
    [switch]$SinEnganches
)

$ErrorActionPreference = "Stop"
$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path

function Paso($texto)  { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Bien($texto)  { Write-Host "    [ok] $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "    [!]  $texto" -ForegroundColor Yellow }
function Mal($texto)   { Write-Host "    [x]  $texto" -ForegroundColor Red }

Write-Host ""
Write-Host "  TecladoIA — instalación" -ForegroundColor White
Write-Host "  ------------------------"

# --- 1. Python -------------------------------------------------------
Paso "Buscando Python"
$python = $null
foreach ($candidato in @("python", "py -3", "python3")) {
    try {
        $partes = $candidato.Split(" ")
        $version = & $partes[0] $partes[1..($partes.Length-1)] --version 2>&1
        if ($version -match "Python (\d+)\.(\d+)") {
            if ([int]$Matches[1] -gt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 10)) {
                $python = $candidato
                Bien "$version"
                break
            }
        }
    } catch { }
}
if (-not $python) {
    Mal "Hace falta Python 3.10 o posterior."
    Write-Host "    Descárgalo de https://www.python.org/downloads/ y marca"
    Write-Host "    la casilla «Add Python to PATH» durante la instalación."
    exit 1
}

# --- 2. La aplicación ------------------------------------------------
Paso "Instalando TecladoIA"
Push-Location $carpeta
try {
    # «[ble]» trae la pila Bluetooth. En Windows además hace falta winrt,
    # que viene con bleak, para hablar con teclados ya emparejados.
    & cmd /c "$python -m pip install --upgrade pip --quiet" 2>&1 | Out-Null
    & cmd /c "$python -m pip install -e `".[ble]`" --quiet"
    if ($LASTEXITCODE -ne 0) { throw "pip devolvió $LASTEXITCODE" }
    Bien "Instalada junto con el soporte Bluetooth"
} catch {
    Mal "No se pudo instalar: $_"
    exit 1
} finally {
    Pop-Location
}

# --- 3. El teclado ---------------------------------------------------
Paso "Buscando el teclado"
$emparejado = Get-PnpDevice -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -like "*AhaKey*" } |
    Select-Object -First 1
if ($emparejado) {
    Bien "Encontrado: $($emparejado.FriendlyName)"
} else {
    Aviso "No aparece ningún AhaKey emparejado en este equipo."
    Write-Host "    Empareja el teclado en Configuración > Bluetooth y vuelve"
    Write-Host "    a ejecutar esto. La instalación continúa igualmente."
}

# --- 4. La clave del panel -------------------------------------------
Paso "Clave del panel"
if (-not $Clave) {
    Write-Host "    El panel decide qué puede ejecutar un agente sin preguntar,"
    Write-Host "    así que fuera de este equipo no se abre sin clave."
    $Clave = Read-Host "    Escribe una clave (Intro para dejarlo solo en este PC)"
}
if ($Clave) {
    & cmd /c "$python -m tecladoia config --clave-panel `"$Clave`"" | Out-Null
    Bien "Clave guardada"
} else {
    Aviso "Sin clave: el panel solo se abrirá en este equipo (127.0.0.1)"
}

# --- 5. Los enganches ------------------------------------------------
if (-not $SinEnganches) {
    Paso "Poniendo los enganches en los programas de IA"
    & cmd /c "$python -m tecladoia instalar"
    Bien "Listo (se hizo copia de seguridad de cada configuración)"
}

# --- 6. Dónde escucha ------------------------------------------------
if ($Host) {
    Paso "Publicando el panel en $Host"
    if (-not $Clave) {
        Mal "Para escuchar fuera de este equipo hace falta clave. Se omite."
        $Host = ""
    } else {
        & cmd /c "$python -c `"from tecladoia.config import Ajustes; a=Ajustes.cargar(); a.host_panel='$Host'; a.guardar()`""
        Bien "El panel escuchará en $Host"

        # El cortafuegos solo se toca si podemos: pedir permisos de
        # administrador a mitad de la instalación es peor que avisar.
        $administrador = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($administrador) {
            netsh advfirewall firewall delete rule name="TecladoIA" 2>&1 | Out-Null
            netsh advfirewall firewall add rule name="TecladoIA" dir=in action=allow `
                protocol=TCP localport=8770 2>&1 | Out-Null
            Bien "Cortafuegos abierto en el puerto 8770"
        } else {
            Aviso "Sin permisos de administrador: si desde otro equipo no entra,"
            Write-Host "    abre el puerto 8770 o vuelve a ejecutar esto como administrador."
        }
    }
}

# --- 7. Que arranque solo --------------------------------------------
if (-not $SinTareaProgramada) {
    Paso "Dejando el servicio arrancando con el equipo"
    $orden = if ($Host) { "servicio --host $Host" } else { "servicio" }
    try {
        $accion = New-ScheduledTaskAction -Execute "cmd.exe" `
            -Argument "/c start /min `"`" $python -m tecladoia $orden" `
            -WorkingDirectory $carpeta
        $disparador = New-ScheduledTaskTrigger -AtLogOn
        $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName "TecladoIA" -Action $accion `
            -Trigger $disparador -Settings $ajustes -Force | Out-Null
        Bien "Arrancará al iniciar sesión (tarea «TecladoIA»)"
    } catch {
        Aviso "No se pudo crear la tarea: $_"
        Write-Host "    Puedes arrancarlo a mano con: $python -m tecladoia $orden"
    }
}

# --- 8. En marcha ----------------------------------------------------
Paso "Arrancando"
$orden = if ($Host) { "servicio --host $Host" } else { "servicio" }
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c start /min `"`" $python -m tecladoia $orden" `
    -WorkingDirectory $carpeta
Start-Sleep -Seconds 8

$direccion = if ($Host) { "http://${Host}:8770" } else { "http://127.0.0.1:8770" }
try {
    $respuesta = Invoke-WebRequest -Uri "$direccion/" -TimeoutSec 10 -UseBasicParsing `
        -ErrorAction SilentlyContinue
    Bien "El panel responde"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 401) {
        Bien "El panel responde y pide clave, como debe"
    } else {
        Aviso "Todavía no responde; dale unos segundos más."
    }
}

Write-Host ""
Write-Host "  Listo." -ForegroundColor Green
Write-Host "  Abre  $direccion" -ForegroundColor White
if ($Clave) { Write-Host "  y entra con la clave que elegiste." }
Write-Host ""
Write-Host "  Si el teclado no aparece: enciéndelo y espera unos segundos; el"
Write-Host "  servicio lo engancha solo. Cierra la aplicación oficial de AhaKey"
Write-Host "  si la tienes abierta — solo un programa puede hablar con él."
Write-Host ""
