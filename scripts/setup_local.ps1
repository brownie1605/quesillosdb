# =============================================================================
#  Quesillos Lo Nuestro - Preparacion de la base de datos LOCAL
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
#
#  Pide la contrasena de root de MySQL, crea la base "quesillos_local",
#  la guarda en el .env, crea las tablas y siembra los datos iniciales.
#  La contrasena nunca se muestra en pantalla ni queda en el historial.
# =============================================================================

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host ""
Write-Host "=== Quesillos Lo Nuestro - Base de datos local ===" -ForegroundColor Yellow
Write-Host ""

# --- 1. Localizar mysql.exe -------------------------------------------------
$mysql = $null
$candidatos = @(
    "C:\Program Files\MySQL\MySQL Server 9.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    "C:\xampp\mysql\bin\mysql.exe",
    "C:\laragon\bin\mysql\mysql-8.0.30-winx64\bin\mysql.exe"
)
foreach ($c in $candidatos) { if (Test-Path $c) { $mysql = $c; break } }
if (-not $mysql) {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd) { $mysql = $cmd.Source }
}
if (-not $mysql) {
    Write-Host "No se encontro mysql.exe. Instala MySQL o agregalo al PATH." -ForegroundColor Red
    exit 1
}
Write-Host "MySQL encontrado: $mysql" -ForegroundColor Green

# --- 2. Credenciales --------------------------------------------------------
$usuario = Read-Host "Usuario de MySQL (Enter = root)"
if ([string]::IsNullOrWhiteSpace($usuario)) { $usuario = "root" }

$segura = Read-Host "Contrasena de MySQL para '$usuario'" -AsSecureString
$clave = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))

$baseDatos = "quesillos_local"

# --- 3. Crear la base -------------------------------------------------------
Write-Host ""
Write-Host "Creando la base '$baseDatos'..." -ForegroundColor Cyan
$env:MYSQL_PWD = $clave
$sql = "CREATE DATABASE IF NOT EXISTS $baseDatos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
& $mysql -u $usuario -e $sql
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo conectar a MySQL. Revisa el usuario y la contrasena." -ForegroundColor Red
    $env:MYSQL_PWD = $null
    exit 1
}
Write-Host "Base de datos lista." -ForegroundColor Green

# --- 4. Guardar en el .env --------------------------------------------------
$envPath = Join-Path $raiz ".env"
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $raiz ".env.example") $envPath }

$lineas = Get-Content $envPath
$lineas = $lineas | ForEach-Object {
    if ($_ -match "^DB_LOCAL_USER=")     { "DB_LOCAL_USER=$usuario" }
    elseif ($_ -match "^DB_LOCAL_PASSWORD=") { "DB_LOCAL_PASSWORD=$clave" }
    elseif ($_ -match "^DB_LOCAL_NAME=") { "DB_LOCAL_NAME=$baseDatos" }
    else { $_ }
}
$lineas | Out-File -FilePath $envPath -Encoding utf8
Write-Host "Credenciales guardadas en .env (este archivo NO se sube a git)." -ForegroundColor Green

# --- 5. Tablas y datos iniciales -------------------------------------------
$python = Join-Path $raiz "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$env:FLASK_APP = "run.py"
$env:SYNC_ENABLED = "false"

Write-Host ""
Write-Host "Creando las tablas..." -ForegroundColor Cyan
& $python -m flask init-local

Write-Host "Sembrando empresa, sucursal, roles y unidades..." -ForegroundColor Cyan
& $python -m flask seed

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor Yellow
Write-Host "Ahora crea el usuario administrador:" -ForegroundColor White
Write-Host "    venv\Scripts\python.exe -m flask crear-admin" -ForegroundColor Gray
Write-Host "Y para cargar el ejemplo del quesillo con sus insumos:" -ForegroundColor White
Write-Host "    venv\Scripts\python.exe -m flask demo-quesillo" -ForegroundColor Gray
Write-Host "Finalmente arranca el sistema:" -ForegroundColor White
Write-Host "    venv\Scripts\python.exe run.py" -ForegroundColor Gray
Write-Host ""

$env:MYSQL_PWD = $null
$clave = $null
