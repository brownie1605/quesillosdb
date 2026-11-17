@echo off
rem Agente de impresion Quesillos POS - arranque automatico.
rem Copiar este archivo a la carpeta de Inicio de Windows (Win+R, escribir shell:startup).
rem Se abre minimizado y, si el agente se cierra por error, lo vuelve a levantar.
rem Para detenerlo: abrir la ventana "Agente de impresion" en la barra de tareas y cerrarla con la X.

if not "%1"=="min" (
    start "Agente de impresion" /min cmd /c ""%~f0" min"
    exit /b
)

cd /d C:\print_agent

set PYEXE=python
if exist "C:\Users\usuario\AppData\Local\Programs\Python\Python38\python.exe" set PYEXE=C:\Users\usuario\AppData\Local\Programs\Python\Python38\python.exe

:bucle
"%PYEXE%" agente.py
rem Espera 5 segundos y vuelve a intentar
ping 127.0.0.1 -n 6 >nul
goto bucle
