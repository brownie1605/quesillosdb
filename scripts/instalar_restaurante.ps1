# =============================================================================
#  Quesillos Lo Nuestro - Instalacion del servidor del RESTAURANTE
#
#  Se corre UNA vez, en la PC del restaurante, como administrador:
#     1. Clic derecho en el menu Inicio -> "Terminal (Administrador)" o
#        "Windows PowerShell (Administrador)".
#     2. powershell -ExecutionPolicy Bypass -File C:\QuesillosPOS\scripts\instalar_restaurante.ps1
#
#  Deja la PC lista para trabajar con o sin internet:
#     1. Entorno de Python con lo que necesita el sistema.
#     2. Base de datos local "quesillos_local".
#     3. Archivo .env de ESTE equipo (modo local, nodo 2).
#     4. Copia completa de la nube en la base local.
#     5. El sistema arranca solo al encender la PC (sin ventana negra).
#     6. Permiso en el firewall para que los celulares entren por Wi-Fi.
#     7. Icono "Quesillos POS" en el escritorio que abre el sistema como app.
#
#  Las contrasenas nunca se muestran en pantalla ni quedan en el historial.
#  Si ya habia un .env, se guarda una copia en bd\respaldos\ antes de
#  reemplazarlo (esa carpeta no se sube a git).
# =============================================================================

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$NOMBRE_TAREA = "Quesillos POS - Servidor"
$NOMBRE_BASE = "quesillos_local"
$PUERTO = "5000"

function Paso($texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }
function Bien($texto) { Write-Host "   $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "   $texto" -ForegroundColor Yellow }
function Falla($texto) { Write-Host ""; Write-Host "   $texto" -ForegroundColor Red; exit 1 }

function TextoPlano($seguro) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Nativo([scriptblock]$bloque) {
    # En Windows PowerShell 5.1, con ErrorActionPreference=Stop, lo que un
    # programa externo escribe en stderr (aunque sea un aviso) detiene el
    # script si se redirige. Aqui se juzga por el codigo de salida.
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $bloque } finally { $ErrorActionPreference = $anterior }
}

function ValorEnv($valor) {
    # python-dotenv: un valor con espacios, # o comillas va entre comillas.
    if ($valor -notmatch "[\s#'""]") { return $valor }
    if ($valor -notmatch "'") { return "'" + $valor + "'" }
    return '"' + ($valor -replace '\\', '\\' -replace '"', '\"') + '"'
}

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Falla "Abre PowerShell como administrador (clic derecho -> Ejecutar como administrador) y vuelve a correr este script."
}

Write-Host ""
Write-Host "=== Quesillos Lo Nuestro - Servidor del restaurante ===" -ForegroundColor Yellow
Write-Host "Carpeta del sistema: $raiz"

# -----------------------------------------------------------------------------
Paso "1/7 Python"
$python = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("-3.12", "-3.13", "-3.11")) {
        Nativo { & py $v --version *> $null }
        if ($LASTEXITCODE -eq 0) { $python = "py"; $pyArgs = @($v); break }
    }
}
if (-not $python -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if (@("3.11", "3.12", "3.13") -contains $ver) { $python = "python" }
}
if (-not $python) {
    Falla "Falta Python 3.12. Instalalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH') y vuelve a correr este script."
}
Bien ("Python encontrado: " + (& $python @pyArgs --version))

# -----------------------------------------------------------------------------
Paso "2/7 Entorno del sistema (puede tardar unos minutos)"
$venvPy = Join-Path $raiz "venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    Nativo { & $venvPy --version *> $null }
    if ($LASTEXITCODE -ne 0) {
        Aviso "El entorno que habia no sirve en esta PC (venia de otra computadora); se crea de nuevo."
        Remove-Item -Recurse -Force (Join-Path $raiz "venv")
    }
}
if (-not (Test-Path $venvPy)) {
    Nativo { & $python @pyArgs -m venv venv }
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo crear el entorno de Python (venv)." }
}
Nativo { & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check }
Nativo { & $venvPy -m pip install -r requirements.txt --quiet --disable-pip-version-check }
if ($LASTEXITCODE -ne 0) { Falla "No se pudieron instalar las dependencias. Revisa el internet y vuelve a correr." }
Bien "Dependencias instaladas."

# -----------------------------------------------------------------------------
Paso "3/7 MySQL"
$mysql = $null
$candidatos = @(
    "C:\Program Files\MySQL\MySQL Server 9.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 9.3\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    "C:\xampp\mysql\bin\mysql.exe"
)
foreach ($c in $candidatos) { if (Test-Path $c) { $mysql = $c; break } }
if (-not $mysql) {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($cmd) { $mysql = $cmd.Source }
}
if (-not $mysql) {
    Falla "No se encontro MySQL. Instala 'MySQL Server 8.4 LTS' (https://dev.mysql.com/downloads/installer/), dejalo como servicio automatico y vuelve a correr."
}
Bien "MySQL: $mysql"

$usuarioDb = Read-Host "   Usuario de MySQL de esta PC (Enter = root)"
if ([string]::IsNullOrWhiteSpace($usuarioDb)) { $usuarioDb = "root" }
$claveDb = TextoPlano (Read-Host "   Contrasena de MySQL para '$usuarioDb'" -AsSecureString)

$env:MYSQL_PWD = $claveDb
try {
    Nativo { & $mysql -u $usuarioDb -e "SELECT 1" *> $null }
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo entrar a MySQL con ese usuario y contrasena." }

    $existe = Nativo { & $mysql -u $usuarioDb -N -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$NOMBRE_BASE'" }
    if ("$existe".Trim() -eq "1") {
        $sinSubir = Nativo { & $mysql -u $usuarioDb -N -e "SELECT COUNT(*) FROM $NOMBRE_BASE.sync_queue WHERE estado_sync IN ('pendiente','error')" 2>$null }
        Aviso "Ya existe la base '$NOMBRE_BASE' en esta PC."
        if ("$sinSubir".Trim() -match '^[1-9]') {
            Aviso "ATENCION: tiene $("$sinSubir".Trim()) cambio(s) que todavia NO han subido a la nube. Si la borras se pierden."
            Aviso "Primero deja el sistema encendido con internet un rato para que suban."
        }
        $resp = Read-Host "   Se BORRARA y se copiara de nuevo desde la nube. Escribe SI para continuar"
        if ($resp -ne "SI") { Falla "Instalacion cancelada. No se toco nada." }
        Nativo { & $mysql -u $usuarioDb -e "DROP DATABASE $NOMBRE_BASE" }
    }
    Nativo { & $mysql -u $usuarioDb -e "CREATE DATABASE $NOMBRE_BASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" }
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo crear la base '$NOMBRE_BASE'." }
}
finally { $env:MYSQL_PWD = $null }
Bien "Base '$NOMBRE_BASE' lista."

# -----------------------------------------------------------------------------
Paso "4/7 Configuracion de este equipo (.env)"
$envPath = Join-Path $raiz ".env"
$previo = @{}
if (Test-Path $envPath) {
    $carpeta = Join-Path $raiz "bd\respaldos"
    New-Item -ItemType Directory -Force $carpeta | Out-Null
    Copy-Item $envPath (Join-Path $carpeta ("env-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".env"))
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$') {
            $previo[$matches[1]] = $matches[2].Trim("'").Trim('"')
        }
    }
    Bien "Se guardo una copia del .env anterior en bd\respaldos\"
}

function Dato($clave, $texto, $porDefecto = "", [switch]$secreto) {
    if ($previo.ContainsKey($clave) -and $previo[$clave]) { return $previo[$clave] }
    if ($secreto) { return TextoPlano (Read-Host "   $texto" -AsSecureString) }
    $v = Read-Host ("   $texto" + $(if ($porDefecto) { " (Enter = $porDefecto)" } else { "" }))
    if ([string]::IsNullOrWhiteSpace($v)) { return $porDefecto }
    return $v
}

Write-Host "   Datos de la base en la NUBE (Railway). Si copiaste el .env de la laptop, se toman de ahi."
$remoto = [ordered]@{
    DB_REMOTE_HOST = (Dato "DB_REMOTE_HOST" "Servidor de la nube (ej. xxxx.proxy.rlwy.net)")
    DB_REMOTE_PORT = (Dato "DB_REMOTE_PORT" "Puerto de la nube" "3306")
    DB_REMOTE_USER = (Dato "DB_REMOTE_USER" "Usuario de la nube" "root")
    DB_REMOTE_PASSWORD = (Dato "DB_REMOTE_PASSWORD" "Contrasena de la nube" -secreto)
    DB_REMOTE_NAME = (Dato "DB_REMOTE_NAME" "Nombre de la base en la nube" "pos_inventario_cloud")
}

$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$claveSecreta = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""

$cfg = [ordered]@{
    FLASK_APP = "run.py"
    FLASK_ENV = "production"
    SECRET_KEY = $claveSecreta
    HOST = "0.0.0.0"
    PORT = $PUERTO
    SESSION_COOKIE_SECURE = "false"
    DB_LOCAL_HOST = "localhost"
    DB_LOCAL_PORT = "3306"
    DB_LOCAL_USER = $usuarioDb
    DB_LOCAL_PASSWORD = $claveDb
    DB_LOCAL_NAME = $NOMBRE_BASE
}
foreach ($k in $remoto.Keys) { $cfg[$k] = $remoto[$k] }
$cfg["SYNC_ENABLED"] = "true"
$cfg["MODO_NODO"] = "local"
$cfg["ID_NODO"] = "2"
$cfg["DEVICE_ID"] = "restaurante-01"
# Correo de recuperacion y respaldo en Cloudflare R2: se conservan si ya estaban.
foreach ($k in $previo.Keys) {
    if (($k -like "SMTP_*" -or $k -like "MAIL_*" -or $k -like "R2_*" -or $k -like "BACKUP_*") -and -not $cfg.Contains($k)) {
        $cfg[$k] = $previo[$k]
    }
}

$lineas = @(
    "# Generado por scripts\instalar_restaurante.ps1 el $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    "# PC del restaurante: base local + sincronizacion con la nube. NO subir a git."
)
foreach ($k in $cfg.Keys) { $lineas += ($k + "=" + (ValorEnv $cfg[$k])) }
[System.IO.File]::WriteAllLines($envPath, $lineas, (New-Object System.Text.UTF8Encoding($false)))
$claveDb = $null
$remoto = $null
Bien ".env de este equipo listo (modo local, nodo 2, dispositivo 'restaurante-01')."

# -----------------------------------------------------------------------------
Paso "5/7 Copiando todo desde la nube (puede tardar unos minutos)"
$env:FLASK_APP = "run.py"
$env:SYNC_ENABLED = "false"
try {
    Nativo { & $venvPy -m flask init-local }
    if ($LASTEXITCODE -ne 0) { Falla "No se pudieron crear las tablas." }
    Nativo { & $venvPy -m flask bootstrap-nube }
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo copiar desde la nube. Revisa el internet y los datos de la nube." }
}
finally { Remove-Item Env:SYNC_ENABLED -ErrorAction SilentlyContinue }
Bien "Base local copiada desde la nube."

# -----------------------------------------------------------------------------
Paso "6/7 Arranque automatico al encender la PC"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"" + (Join-Path $raiz "scripts\servidor.ps1") + "`"") `
    -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $NOMBRE_TAREA -Action $accion -Trigger $disparador `
    -Principal $principal -Settings $ajustes -Force | Out-Null
Stop-ScheduledTask -TaskName $NOMBRE_TAREA -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $NOMBRE_TAREA
Bien "Tarea '$NOMBRE_TAREA' creada y en marcha."

# -----------------------------------------------------------------------------
Paso "7/7 Red, firewall e icono"
if (-not (Get-NetFirewallRule -DisplayName "Quesillos POS" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Quesillos POS" -Direction Inbound -Protocol TCP `
        -LocalPort $PUERTO -Action Allow -Profile Private, Domain | Out-Null
}
Bien "Firewall: puerto $PUERTO abierto para la red privada del local."

foreach ($red in (Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq "Public" })) {
    Aviso "La red '$($red.Name)' esta marcada como PUBLICA: los celulares no podran entrar."
    $resp = Read-Host "   Cambiarla a PRIVADA (la red del local)? Escribe SI para cambiarla"
    if ($resp -eq "SI") {
        Set-NetConnectionProfile -InterfaceIndex $red.InterfaceIndex -NetworkCategory Private
        Bien "Red '$($red.Name)' ahora es privada."
    }
}

$ws = New-Object -ComObject WScript.Shell
foreach ($carpeta in @([Environment]::GetFolderPath("CommonDesktopDirectory"),
                       [Environment]::GetFolderPath("CommonStartup"))) {
    $acceso = $ws.CreateShortcut((Join-Path $carpeta "Quesillos POS.lnk"))
    $acceso.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
    $acceso.Arguments = "`"" + (Join-Path $raiz "scripts\abrir_pos.vbs") + "`""
    $acceso.IconLocation = Join-Path $raiz "scripts\quesillos.ico"
    $acceso.WorkingDirectory = $raiz
    $acceso.Description = "Abrir Quesillos POS"
    $acceso.Save()
}
Bien "Icono 'Quesillos POS' en el escritorio (y se abre solo al iniciar sesion)."

# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "Esperando a que el sistema responda..." -ForegroundColor Cyan
$listo = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:$PUERTO/healthz"
        if ($r.StatusCode -eq 200) { $listo = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor Yellow
if ($listo) { Bien "El sistema ya esta corriendo en esta PC." }
else { Aviso "El sistema todavia no responde. Revisa logs\servidor.log o reinicia la PC." }
Write-Host ""
Write-Host "  En esta PC: icono 'Quesillos POS' del escritorio." -ForegroundColor White
Write-Host "  Celulares y tablets (conectados al Wi-Fi del local):" -ForegroundColor White
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress
foreach ($ip in $ips) { Write-Host "      http://$($ip):$PUERTO" -ForegroundColor Green }
Write-Host ""
Write-Host "  Recomendado: en el router, reserva esa IP para esta PC (que no cambie)," -ForegroundColor Gray
Write-Host "  y conecta la PC y el router a un UPS (no-break)." -ForegroundColor Gray
Write-Host "  Funciona sin internet; al volver la senal se sincroniza solo con la nube." -ForegroundColor Gray
Write-Host ""
