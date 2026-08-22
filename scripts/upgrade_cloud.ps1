# =============================================================================
#  Quesillos Lo Nuestro - Actualizar la base de datos EN LA NUBE (Railway)
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\upgrade_cloud.ps1
#
#  Aplica bd/02_cloud_upgrade.sql usando las credenciales DB_REMOTE_* del .env.
#  El script SQL es idempotente: solo agrega lo que falta, no borra datos.
# =============================================================================

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host ""
Write-Host "=== Actualizacion de la base en la NUBE ===" -ForegroundColor Yellow
Write-Host ""

# --- Leer el .env -----------------------------------------------------------
$envPath = Join-Path $raiz ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "No existe .env. Copia .env.example y completa DB_REMOTE_*." -ForegroundColor Red
    exit 1
}

$conf = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
        $conf[$Matches[1]] = $Matches[2].Trim()
    }
}

foreach ($k in @("DB_REMOTE_HOST", "DB_REMOTE_USER", "DB_REMOTE_NAME")) {
    if (-not $conf[$k]) {
        Write-Host "Falta $k en el .env" -ForegroundColor Red
        exit 1
    }
}

$puerto = if ($conf["DB_REMOTE_PORT"]) { $conf["DB_REMOTE_PORT"] } else { "3306" }

Write-Host ("Servidor : " + $conf["DB_REMOTE_HOST"] + ":" + $puerto) -ForegroundColor Gray
Write-Host ("Base     : " + $conf["DB_REMOTE_NAME"]) -ForegroundColor Gray
Write-Host ""
Write-Host "Se agregaran: recetas, receta_ingredientes, sync_queue, conflict_log," -ForegroundColor White
Write-Host "sync_metadata, columnas de sincronizacion, roles y unidades de medida." -ForegroundColor White
Write-Host "No se elimina ningun dato existente." -ForegroundColor White
Write-Host ""

$respuesta = Read-Host "Escribe SI para continuar"
if ($respuesta -ne "SI") {
    Write-Host "Cancelado." -ForegroundColor Yellow
    exit 0
}

# --- Localizar mysql.exe ----------------------------------------------------
$mysql = $null
foreach ($c in @(
    "C:\Program Files\MySQL\MySQL Server 9.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    "C:\xampp\mysql\bin\mysql.exe")) {
    if (Test-Path $c) { $mysql = $c; break }
}
if (-not $mysql) {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd) { $mysql = $cmd.Source }
}
if (-not $mysql) {
    Write-Host "No se encontro mysql.exe." -ForegroundColor Red
    exit 1
}

# --- Aplicar ----------------------------------------------------------------
$env:MYSQL_PWD = $conf["DB_REMOTE_PASSWORD"]
Write-Host "Aplicando bd/02_cloud_upgrade.sql ..." -ForegroundColor Cyan

& $mysql -h $conf["DB_REMOTE_HOST"] -P $puerto -u $conf["DB_REMOTE_USER"] `
         $conf["DB_REMOTE_NAME"] -e "source bd/02_cloud_upgrade.sql"

$codigo = $LASTEXITCODE
$env:MYSQL_PWD = $null

if ($codigo -eq 0) {
    Write-Host "Nube actualizada correctamente." -ForegroundColor Green
    Write-Host "Verifica con: venv\Scripts\python.exe -m flask sync-status" -ForegroundColor Gray
} else {
    Write-Host "La actualizacion fallo (codigo $codigo)." -ForegroundColor Red
}
