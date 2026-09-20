# Arranca los MCP del host que el contenedor necesita (F0.4 (proxy)).
#
# Hoy hay uno: el puente a PrusaSlicer. PrusaSlicer se queda en este PC a
# proposito, porque es el programa con el que se comprueba que va a salir de
# la impresora; el contenedor se lo pide por aqui.
#
# FreeCAD NO esta aqui y no hace falta: va dentro del contenedor, donde es
# una herramienta interna que construye sin que nadie la mire.
#
# Este archivo lo prometia scripts/README.md desde el primer dia y no
# existia. Durante meses "el puente del host" fue una linea en un documento.
#
#     powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1

param(
    [int]$Puerto = 8102,
    [switch]$EnPrimerPlano
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# El entorno de Python del repo. En Windows los ejecutables del venv estan
# en Scripts\, no en bin\: dar por hecho bin\ es el error que convierte un
# script en "solo funciona en la maquina de quien lo escribio".
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = Join-Path $repo ".venv/bin/python"
}
if (-not (Test-Path $python)) {
    throw "no encuentro el entorno de Python en $repo\.venv — crealo con: python -m venv .venv"
}

# El puente ejecuta PrusaSlicer, asi que necesita saber donde esta. Sale del
# .env, que es donde viven las rutas de esta maquina.
$env:PRUSASLICER_BRIDGE_PORT = $Puerto
$envFile = Join-Path $repo ".env"
if (Test-Path $envFile) {
    foreach ($linea in Get-Content $envFile) {
        $linea = $linea.Trim()
        if ($linea -eq "" -or $linea.StartsWith("#") -or -not $linea.Contains("=")) { continue }
        $i = $linea.IndexOf("=")
        $clave = $linea.Substring(0, $i).Trim()
        $valor = $linea.Substring($i + 1).Trim().Trim('"', "'")
        # Solo lo que el puente usa. Cargar el .env entero meteria la clave
        # de DeepSeek y el token del bot en un proceso que no los necesita.
        if ($clave -in @("PRUSASLICER", "INTELLIPRINT_WORKSPACE")) {
            Set-Item -Path "env:$clave" -Value $valor
        }
    }
}

if (-not $env:PRUSASLICER) {
    $porDefecto = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
    if (Test-Path $porDefecto) {
        $env:PRUSASLICER = $porDefecto
    } else {
        throw "no se donde esta PrusaSlicer: pon PRUSASLICER en .env"
    }
}

Write-Host "PrusaSlicer:  $env:PRUSASLICER"
Write-Host "Puente MCP:   http://localhost:$Puerto/mcp  (el contenedor lo ve como host.docker.internal)"
Write-Host ""

if ($EnPrimerPlano) {
    & $python -m scripts.host_bridge
} else {
    $registro = Join-Path $repo "workspace\host_bridge.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $registro) | Out-Null
    Start-Process -FilePath $python -ArgumentList "-m", "scripts.host_bridge" `
        -WorkingDirectory $repo -RedirectStandardOutput $registro `
        -RedirectStandardError "$registro.err" -WindowStyle Hidden
    Write-Host "puente lanzado en segundo plano; registro en $registro"
    Write-Host "para pararlo:  Get-Process python | Where-Object { `$_.Path -eq '$python' } | Stop-Process"
}
