' =============================================================================
'  Quesillos POS - abre el sistema en su propia ventana, como una app.
'
'  Lo usa el icono "Quesillos POS" del escritorio. Justo al encender la PC el
'  servidor tarda unos segundos en estar listo: se espera a que responda
'  (hasta 2 minutos) antes de abrir la ventana.
' =============================================================================
Option Explicit

Const URL = "http://localhost:5000"

Dim http, intento, listo, shell, fso, edge
listo = False
For intento = 1 To 60
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 2000, 2000, 2000, 2000
    http.open "GET", URL & "/healthz", False
    http.send
    If Err.Number = 0 Then
        If http.status = 200 Then listo = True
    End If
    Err.Clear
    On Error GoTo 0
    If listo Then Exit For
    WScript.Sleep 2000
Next

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
edge = shell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"
If Not fso.FileExists(edge) Then
    edge = shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe"
End If

If Not listo Then
    MsgBox "El sistema todavia esta arrancando o no esta corriendo." & vbCrLf & _
           "Espera un momento y vuelve a abrirlo. Si sigue igual, reinicia la computadora.", _
           48, "Quesillos POS"
End If

If fso.FileExists(edge) Then
    shell.Run """" & edge & """ --app=" & URL, 1, False
Else
    shell.Run URL, 1, False
End If
