# =============================================================================
#  Quesillos POS - arranca el servidor del restaurante y lo mantiene vivo.
#
#  Lo ejecuta la tarea programada "Quesillos POS - Servidor" al encender la
#  PC (sin ventana). Si el servidor se detiene por cualquier motivo, se
#  vuelve a levantar a los 5 segundos. La salida queda en logs\servidor.log
#  (cuando pasa de 10 MB se renombra a servidor.log.anterior).
# =============================================================================

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$logs = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs "servidor.log"
$py = Join-Path $raiz "venv\Scripts\python.exe"
$env:PYTHONUNBUFFERED = "1"

function Anotar($texto) {
    Add-Content -Path $log -Value ("==== " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " " + $texto)
}

# Al encender la PC, MySQL arranca casi al mismo tiempo: se espera hasta 2 min.
for ($i = 0; $i -lt 60; $i++) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", 3306)
        $c.Close()
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

while ($true) {
    if ((Test-Path $log) -and ((Get-Item $log).Length -gt 10MB)) {
        Move-Item $log ($log + ".anterior") -Force
    }
    Anotar "arrancando el servidor"
    & cmd /c "`"$py`" run.py >> `"$log`" 2>&1"
    Anotar ("el servidor se detuvo (codigo " + $LASTEXITCODE + "); se reinicia en 5 s")
    Start-Sleep -Seconds 5
}
