"""Agente de impresion - Quesillos POS.

Que hace: se conecta al sistema y, cada vez que un mesero envia un pedido,
imprime la comanda en la impresora que le corresponde (Quesillo / Cocina /
Bebidas). Tambien imprime la PRECUENTA y la FACTURA en la impresora de CAJA.

Por que existe este archivo aparte de la app principal: el sistema puede
vivir en la nube, pero las impresoras estan conectadas a la PC del local --
la nube no tiene forma de "verlas" directamente. Este agente SI corre dentro
del local (en la PC central, la misma del servidor) y hace de puente.

Los telefonos NO se conectan a las impresoras: mandan el pedido al sistema
(la PC central) y esta PC imprime.

===========================================================================
CONFIGURACION -- esto es lo UNICO que hay que tocar.
===========================================================================
"""

# Direccion del sistema. Con la PC central como servidor, el agente corre en
# esa misma PC y usa localhost: asi imprime aunque no haya internet.
SERVIDOR_URL = "http://localhost:5000"

# Las 4 impresoras. Para cada una pon el TIPO de conexion y sus datos; deja
# None la que todavia no tengas (se ignora).
#
#   "tipo": "usb"        -> impresora de cable (USB, serial o paralelo) YA
#                           INSTALADA en Windows con su driver.
#                           "nombre" = el nombre EXACTO que sale en
#                           Windows (Configuracion -> Impresoras).
#   "tipo": "serial"     -> impresora serial por puerto COM directo
#                           ("puerto": "COM1", "baudios": 38400).
#   "tipo": "bluetooth"  -> impresora Bluetooth ya EMPAREJADA con esta PC.
#                           "puerto" = el COM que le asigna Windows (COM5...).
#   "tipo": "red"        -> impresora de red (Wi-Fi o cable de red).
#                           "ip" = su direccion IP.
#
#   "ancho": caracteres por linea. Papel de 80 mm = 48, papel de 58 mm = 32.
#
# Para saber los nombres y los COM:  python probar_impresoras.py listar
IMPRESORAS = {
    "quesillo": None,   # ej. {"tipo": "usb", "nombre": "POS-80C", "ancho": 48}
    "cocina": None,     # ej. {"tipo": "bluetooth", "puerto": "COM5", "ancho": 32}
    "bebidas": None,    # ej. {"tipo": "red", "ip": "192.168.1.52", "ancho": 48}
    "caja": None,       # la de la factura y la precuenta
}

# Puerto estandar de impresion ESC/POS por red (RAW / JetDirect).
PUERTO_IMPRESORA_RED = 9100

# ===========================================================================
# De aqui para abajo no hace falta tocar nada.
# ===========================================================================

import os
import socket
import sys
import textwrap
import threading
import time
import unicodedata

try:
    import socketio
except ImportError:
    socketio = None


# ---------------------------------------------------------------- clave
def _leer_env():
    """Lee ../.env (el del sistema) sin depender de otras librerias."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    valores = {}
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return valores


_ENV = _leer_env()
# La clave que el sistema exige al agente para recibir los pedidos. Debe ser
# la MISMA PRINT_AGENT_TOKEN en el .env del sistema y aqui (se lee de ahi).
TOKEN = os.environ.get("PRINT_AGENT_TOKEN") or _ENV.get("PRINT_AGENT_TOKEN", "")
SERVIDOR_URL = os.environ.get("SERVIDOR_URL") or SERVIDOR_URL


# ---------------------------------------------------------------- ESC/POS
ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
NEGRITA_ON = ESC + b"E\x01"
NEGRITA_OFF = ESC + b"E\x00"
DOBLE_ALTO_ON = GS + b"!\x11"
DOBLE_ALTO_OFF = GS + b"!\x00"
CENTRO = ESC + b"a\x01"
IZQUIERDA = ESC + b"a\x00"
CORTE = GS + b"V\x01"
FEED = b"\n"


def _txt(s):
    """Texto -> bytes CP437 (lo que casi toda impresora termica entiende).
    Los acentos que CP437 no tiene se quitan (Á -> A) y lo que no se puede
    imprimir (emojis) se omite, en vez de salir como '?'."""
    salida = bytearray()
    for ch in str(s):
        try:
            salida += ch.encode("cp437")
            continue
        except UnicodeEncodeError:
            pass
        base = unicodedata.normalize("NFD", ch)[:1]
        try:
            salida += base.encode("ascii")
        except UnicodeEncodeError:
            pass
    return bytes(salida)


def _dinero(valor):
    try:
        return f"{float(valor):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _sep(ancho, ch="-"):
    return _txt(ch * ancho + "\n")


def _lr(izq, der, ancho):
    """Una linea con texto a la izquierda y otro pegado a la derecha."""
    izq, der = str(izq), str(der)
    izq = izq[:max(0, ancho - len(der) - 1)]       # nunca pasarse del renglon
    espacio = max(1, ancho - len(izq) - len(der))
    return _txt(izq + " " * espacio + der + "\n")


def _envolver(texto, ancho, sangria=0):
    lineas = textwrap.wrap(str(texto), max(8, ancho - sangria)) or [""]
    return [" " * sangria + l for l in lineas]


def armar_comanda(payload, ancho):
    p = [INIT, CENTRO, DOBLE_ALTO_ON, NEGRITA_ON]
    p.append(_txt(payload.get("etiqueta", "COMANDA")).strip() + b"\n")   # sin el emoji ni su espacio
    p += [DOBLE_ALTO_OFF, NEGRITA_OFF, IZQUIERDA]
    p.append(_sep(ancho))
    p.append(_txt(f"Mesa: {payload.get('mesa', '-')}\n"))
    if payload.get("mesero"):
        p.append(_txt(f"Mesero: {payload['mesero']}\n"))
    p.append(_txt(f"Hora: {payload.get('hora', '-')}\n"))
    p.append(_sep(ancho))
    for item in payload.get("items", []):
        for linea in _envolver(f"{item.get('cantidad', 1)}x {item.get('nombre', '')}", ancho):
            p.append(NEGRITA_ON + _txt(linea + "\n") + NEGRITA_OFF)
        if item.get("comentario"):
            for linea in _envolver(f"* {item['comentario']}", ancho, 3):
                p.append(_txt(linea + "\n"))
    p.append(_sep(ancho))
    p.append(FEED * 3)
    p.append(CORTE)
    return b"".join(p)


def armar_ticket_caja(payload, ancho):
    """Precuenta o factura completa (tipo = 'precuenta' | 'factura')."""
    es_precuenta = payload.get("tipo") == "precuenta"
    p = [INIT, CENTRO, NEGRITA_ON]
    for linea in _envolver(payload.get("empresa", ""), ancho):
        p.append(_txt(linea + "\n"))
    p.append(NEGRITA_OFF)
    p.append(DOBLE_ALTO_ON + NEGRITA_ON + _txt(payload.get("titulo", "") + "\n") + NEGRITA_OFF + DOBLE_ALTO_OFF)
    if es_precuenta:
        for linea in _envolver("No es factura - No valida como pago", ancho):
            p.append(_txt(linea + "\n"))
    p.append(IZQUIERDA)
    p.append(_sep(ancho))
    if payload.get("numero"):
        p.append(_txt(f"Ticket: {payload['numero']}\n"))
    mesa = payload.get("mesa")
    if mesa:
        p.append(_txt(f"{mesa}" + (f" - {payload['cuenta']}" if payload.get("cuenta") else "") + "\n"))
    p.append(_txt(f"Fecha: {payload.get('fecha', '')}\n"))
    if payload.get("atendio"):
        p.append(_txt(f"Atendio: {payload['atendio']}\n"))
    p.append(_txt(f"Cliente: {payload.get('cliente') or 'Publico General'}\n"))
    p.append(_sep(ancho))
    for it in payload.get("items", []):
        der = _dinero(it.get("subtotal"))
        lineas = _envolver(f"{it.get('cantidad', 1)}x {it.get('nombre', '')}", ancho - len(der) - 1)
        p.append(NEGRITA_ON + _lr(lineas[0], der, ancho) + NEGRITA_OFF)
        for linea in lineas[1:]:
            p.append(_txt(linea + "\n"))
        p.append(_txt(f"   C$ {_dinero(it.get('precio_unitario'))} c/u\n"))
        if it.get("comentario"):
            for linea in _envolver(f"* {it['comentario']}", ancho, 3):
                p.append(_txt(linea + "\n"))
    p.append(_sep(ancho))
    p.append(_lr("Subtotal:", "C$ " + _dinero(payload.get("subtotal")), ancho))
    if float(payload.get("descuento") or 0) > 0:
        pct = payload.get("descuento_pct")
        etiqueta = f"Descuento ({pct:g}%):" if pct else "Descuento:"
        p.append(_lr(etiqueta, "- C$ " + _dinero(payload.get("descuento")), ancho))
    if es_precuenta:
        p.append(_lr("Total:", "C$ " + _dinero(payload.get("total")), ancho))
        etiqueta_propina = "Propina sugerida (10%):" if ancho >= 40 else "Propina sug. 10%:"
        p.append(_lr(etiqueta_propina, "+ C$ " + _dinero(payload.get("propina_sugerida")), ancho))
        p.append(_sep(ancho, "="))
        p.append(NEGRITA_ON + _lr("TOTAL CON PROPINA:", "C$ " + _dinero(payload.get("total_con_propina")), ancho) + NEGRITA_OFF)
        p.append(CENTRO + _txt("\nLa propina es voluntaria.\n") + IZQUIERDA)
    else:
        if float(payload.get("propina") or 0) > 0:
            p.append(_lr("Propina:", "+ C$ " + _dinero(payload.get("propina")), ancho))
        p.append(_sep(ancho, "="))
        p.append(NEGRITA_ON + _lr("TOTAL A PAGAR:", "C$ " + _dinero(payload.get("total")), ancho) + NEGRITA_OFF)
        p.append(_sep(ancho))
        if payload.get("notas"):
            for linea in _envolver("Nota: " + payload["notas"], ancho):
                p.append(_txt(linea + "\n"))
        pagos = payload.get("pagos") or []
        if pagos:
            p.append(_txt("Metodo de pago: Mixto\n"))
            for pg in pagos:
                p.append(_lr("  " + str(pg.get("metodo", "")), "C$ " + _dinero(pg.get("monto")), ancho))
        else:
            p.append(_txt(f"Metodo de pago: {payload.get('metodo_pago', '')}\n"))
        p.append(CENTRO + _txt("\nGracias por su compra!\n") + IZQUIERDA)
    p.append(FEED * 3)
    p.append(CORTE)
    return b"".join(p)


# ---------------------------------------------------------------- envio
def _config(nombre):
    """Config normalizada de una impresora (o None si no esta configurada)."""
    cfg = IMPRESORAS.get(nombre)
    if not cfg:
        return None
    if isinstance(cfg, str):                       # formato viejo: solo la IP
        cfg = {"tipo": "red", "ip": cfg, "ancho": 48}
    return cfg


def _enviar_red(cfg, datos):
    with socket.create_connection((cfg["ip"], cfg.get("puerto", PUERTO_IMPRESORA_RED)), timeout=5) as s:
        s.sendall(datos)


def _winspool():
    """winspool.drv (el spooler de Windows) con los tipos bien declarados.
    Sirve en Windows 7 en adelante y no necesita instalar nada."""
    import ctypes
    from ctypes import wintypes

    if sys.platform != "win32":
        raise RuntimeError("Imprimir por USB (nombre de Windows) solo existe en Windows")

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR),
                    ("pDatatype", wintypes.LPWSTR)]

    w = ctypes.WinDLL("winspool.drv", use_last_error=True)
    w.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    w.OpenPrinterW.restype = wintypes.BOOL
    w.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
    w.StartDocPrinterW.restype = wintypes.DWORD
    w.StartPagePrinter.argtypes = [wintypes.HANDLE]
    w.StartPagePrinter.restype = wintypes.BOOL
    w.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    w.WritePrinter.restype = wintypes.BOOL
    w.EndPagePrinter.argtypes = [wintypes.HANDLE]
    w.EndPagePrinter.restype = wintypes.BOOL
    w.EndDocPrinter.argtypes = [wintypes.HANDLE]
    w.EndDocPrinter.restype = wintypes.BOOL
    w.ClosePrinter.argtypes = [wintypes.HANDLE]
    w.ClosePrinter.restype = wintypes.BOOL
    w.EnumPrintersW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    w.EnumPrintersW.restype = wintypes.BOOL
    return w, DOC_INFO_1


def listar_impresoras_windows():
    """Nombres de las impresoras instaladas en Windows (para el campo "nombre")."""
    import ctypes
    from ctypes import wintypes

    w, _ = _winspool()

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pServerName", wintypes.LPWSTR),
                    ("Attributes", wintypes.DWORD)]

    banderas = 0x2 | 0x4                                   # LOCAL | CONNECTIONS
    necesita, devueltas = wintypes.DWORD(0), wintypes.DWORD(0)
    w.EnumPrintersW(banderas, None, 4, None, 0, ctypes.byref(necesita), ctypes.byref(devueltas))
    if not necesita.value:
        return []
    buf = ctypes.create_string_buffer(necesita.value)
    if not w.EnumPrintersW(banderas, None, 4, buf, necesita.value, ctypes.byref(necesita), ctypes.byref(devueltas)):
        raise RuntimeError("Windows no pudo listar las impresoras (error %d)" % ctypes.get_last_error())
    filas = (PRINTER_INFO_4 * devueltas.value).from_buffer(buf)
    return [f.pPrinterName for f in filas]


def _enviar_usb(cfg, datos):
    """Trabajo RAW al spooler de Windows. Usa pywin32 si esta instalado y, si
    no, habla directo con winspool.drv (no hace falta instalar nada)."""
    try:
        import win32print
    except ImportError:
        win32print = None
    if win32print is not None:
        h = win32print.OpenPrinter(cfg["nombre"])
        try:
            win32print.StartDocPrinter(h, 1, ("Quesillos POS", None, "RAW"))
            try:
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, datos)
                win32print.EndPagePrinter(h)
            finally:
                win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return

    import ctypes
    from ctypes import wintypes

    w, DOC_INFO_1 = _winspool()
    h = wintypes.HANDLE()
    if not w.OpenPrinterW(cfg["nombre"], ctypes.byref(h), None):
        raise RuntimeError(
            "Windows no encuentra la impresora '%s' (error %d). Revisa el nombre con: "
            "python probar_impresoras.py listar" % (cfg["nombre"], ctypes.get_last_error()))
    try:
        doc = DOC_INFO_1("Quesillos POS", None, "RAW")
        if not w.StartDocPrinterW(h, 1, ctypes.byref(doc)):
            raise RuntimeError("La impresora no acepta trabajos RAW (error %d)" % ctypes.get_last_error())
        try:
            if not w.StartPagePrinter(h):
                raise RuntimeError("No se pudo iniciar la pagina (error %d)" % ctypes.get_last_error())
            escritos = wintypes.DWORD(0)
            if not w.WritePrinter(h, datos, len(datos), ctypes.byref(escritos)) or escritos.value != len(datos):
                raise RuntimeError("Solo se enviaron %d de %d bytes (error %d)"
                                   % (escritos.value, len(datos), ctypes.get_last_error()))
            w.EndPagePrinter(h)
        finally:
            w.EndDocPrinter(h)
    finally:
        w.ClosePrinter(h)


def _enviar_bluetooth(cfg, datos):
    try:
        import serial
    except ImportError:
        raise RuntimeError("Falta pyserial (pip install pyserial)")
    with serial.Serial(cfg["puerto"], cfg.get("baudios", 9600), timeout=5, write_timeout=15) as s:
        for i in range(0, len(datos), 512):       # por partes: el buffer Bluetooth es chico
            s.write(datos[i:i + 512])
            s.flush()
            time.sleep(0.05)
        time.sleep(0.5)                           # deja vaciar antes de cerrar


# "usb" = cualquier impresora INSTALADA EN WINDOWS (por su nombre), sin importar
# el cable: USB, serial o paralelo. "serial" y "bluetooth" abren un puerto COM
# directo (la serial de Epson suele ir a 38400 baudios: "baudios": 38400).
ENVIADORES = {"red": _enviar_red, "usb": _enviar_usb, "bluetooth": _enviar_bluetooth, "serial": _enviar_bluetooth}

# Una impresora fisica atiende un ticket a la vez. Varias categorias
# (cocina, quesillo, bebidas) pueden apuntar a la MISMA impresora y sus
# comandas llegan casi juntas, cada una en su hilo: sin este candado dos
# hilos abren el mismo puerto Bluetooth a la vez y el segundo falla.
_CANDADOS = {}
_CANDADOS_LOCK = threading.Lock()


def _candado(cfg):
    clave = (cfg.get("tipo", "red"), cfg.get("nombre") or cfg.get("puerto") or cfg.get("ip"))
    with _CANDADOS_LOCK:
        return _CANDADOS.setdefault(clave, threading.Lock())


def imprimir(nombre, constructor, payload):
    cfg = _config(nombre)
    if not cfg:
        print(f"  [aviso] la impresora '{nombre}' no esta configurada, se ignora")
        return False
    tipo = cfg.get("tipo", "red")
    # El Bluetooth a veces falla la primera vez (la impresora "dormida"): 1 reintento.
    intentos = 2 if tipo == "bluetooth" else 1
    try:
        datos = constructor(payload, int(cfg.get("ancho", 48)))
        with _candado(cfg):
            for intento in range(intentos):
                try:
                    ENVIADORES[tipo](cfg, datos)
                    break
                except Exception:  # noqa: BLE001
                    if intento == intentos - 1:
                        raise
                    time.sleep(2)
        print(f"  [OK] Impreso en '{nombre}' ({tipo})")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [ERROR] No se pudo imprimir en '{nombre}' ({tipo}): {e}")
        return False


# ---------------------------------------------------------------- conexion
def _aviso(texto):
    """Escribe en la ventana sin romperse nunca: la consola de Windows no
    puede mostrar emojis y un fallo aqui NO debe impedir imprimir."""
    try:
        print(texto)
    except Exception:  # noqa: BLE001
        print(texto.encode("ascii", "replace").decode("ascii"))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    if socketio is None:
        print("Falta la libreria 'python-socketio'. Instala las dependencias con:")
        print("    pip install -r requirements.txt")
        sys.exit(1)
    if not TOKEN:
        print("Falta la clave del agente. Agrega esta linea al archivo .env del sistema:")
        print("    PRINT_AGENT_TOKEN=<una clave larga>")
        print("(genera una con:  python -c \"import secrets; print(secrets.token_urlsafe(32))\")")
        sys.exit(1)

    sio = socketio.Client(reconnection=True, reconnection_delay=3)

    @sio.event
    def connect():
        print(f"[conectado] {SERVIDOR_URL}")

    @sio.event
    def disconnect():
        print("[desconectado] reintentando solo...")

    @sio.on("comanda_impresion")
    def on_comanda(payload):
        _aviso(f"[comanda] {payload.get('etiqueta')} - Mesa {payload.get('mesa')}")
        imprimir(payload.get("impresora"), armar_comanda, payload)

    @sio.on("ticket_caja")
    def on_ticket_caja(payload):
        _aviso(f"[{payload.get('tipo')}] {payload.get('mesa') or payload.get('numero')}")
        imprimir("caja", armar_ticket_caja, payload)

    print("Agente de impresion Quesillos POS")
    print(f"Servidor: {SERVIDOR_URL}")
    for nombre in ("quesillo", "cocina", "bebidas", "caja"):
        cfg = _config(nombre)
        print(f"  {nombre:9s} -> {cfg if cfg else '(sin configurar)'}")
    print()
    while True:
        try:
            sio.connect(SERVIDOR_URL, auth={"token": TOKEN})
            sio.wait()
        except KeyboardInterrupt:
            print("\nCerrado por el usuario.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[error de conexion] {e} -- reintentando en 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
