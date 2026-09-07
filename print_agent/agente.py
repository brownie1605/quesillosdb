"""Agente de impresion - Quesillos POS.

Que hace: se conecta al sistema (viva en Railway o donde sea) y, cada vez
que un mesero envia un pedido, imprime la comanda en la impresora que le
corresponde (Quesillo / Cocina / Bebidas).

Por que existe este archivo aparte de la app principal: el sistema vive
en la nube, pero las impresoras estan conectadas a la red del local -- la
nube no tiene forma de "verlas" directamente. Este agente SI corre dentro
del local (en cualquier PC o tablet que se deje encendida, conectada a la
misma red que las impresoras) y hace de puente entre ambos.

===========================================================================
CONFIGURACION -- esto es lo UNICO que hay que tocar. Una vez tengas las
impresoras, pon su IP aqui abajo y listo, no hay que cambiar nada mas.
===========================================================================
"""

# URL publica del sistema (la de Railway una vez este desplegado).
SERVIDOR_URL = "https://tu-app.up.railway.app"

# IP de cada impresora en la red del local. Se averigua desde el menu de
# configuracion de red de la propia impresora (casi todas las termicas de
# red la muestran al imprimir su "pagina de prueba"/self-test).
IMPRESORAS = {
    "quesillo": "192.168.1.50",
    "cocina": "192.168.1.51",
    "bebidas": "192.168.1.52",
}

# Puerto estandar de impresion ESC/POS por red (RAW / JetDirect). Casi
# todas las impresoras termicas de red usan este mismo puerto -- no hace
# falta cambiarlo salvo que el manual de la impresora diga otra cosa.
PUERTO_IMPRESORA = 9100

# ===========================================================================
# De aqui para abajo no hace falta tocar nada.
# ===========================================================================

import socket
import sys
import time

try:
    import socketio
except ImportError:
    print("Falta la libreria 'python-socketio'. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)


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
    """Codifica a CP437: el set de caracteres que casi toda impresora
    termica ESC/POS entiende por defecto. Los acentos/enies que no
    existan en CP437 se reemplazan por el caracter mas parecido."""
    return s.encode("cp437", "replace")


def armar_ticket(payload):
    partes = [INIT, CENTRO, DOBLE_ALTO_ON, NEGRITA_ON]
    partes.append(_txt(payload.get("etiqueta", "COMANDA") + "\n"))
    partes += [DOBLE_ALTO_OFF, NEGRITA_OFF, IZQUIERDA]
    partes.append(_txt("-" * 32 + "\n"))
    partes.append(_txt(f"Mesa: {payload.get('mesa', '-')}\n"))
    if payload.get("mesero"):
        partes.append(_txt(f"Mesero: {payload['mesero']}\n"))
    partes.append(_txt(f"Hora: {payload.get('hora', '-')}\n"))
    partes.append(_txt("-" * 32 + "\n"))
    for item in payload.get("items", []):
        linea = f"{item.get('cantidad', 1)}x {item.get('nombre', '')}\n"
        partes.append(NEGRITA_ON + _txt(linea) + NEGRITA_OFF)
        if item.get("comentario"):
            partes.append(_txt(f"   * {item['comentario']}\n"))
    partes.append(_txt("-" * 32 + "\n"))
    partes.append(FEED * 3)
    partes.append(CORTE)
    return b"".join(partes)


def imprimir(ip, datos):
    try:
        with socket.create_connection((ip, PUERTO_IMPRESORA), timeout=5) as s:
            s.sendall(datos)
        print(f"  [OK] Impreso en {ip}")
    except Exception as e:  # noqa: BLE001
        print(f"  [ERROR] No se pudo imprimir en {ip}: {e}")


sio = socketio.Client(reconnection=True, reconnection_delay=3)


@sio.event
def connect():
    print(f"[conectado] {SERVIDOR_URL}")


@sio.event
def disconnect():
    print("[desconectado] reintentando solo...")


@sio.on("comanda_impresion")
def on_comanda(payload):
    categoria = payload.get("impresora")
    print(f"[comanda] {payload.get('etiqueta')} - Mesa {payload.get('mesa')}")
    ip = IMPRESORAS.get(categoria)
    if not ip:
        print(f"  [aviso] no hay IP configurada para '{categoria}', se ignora esta comanda")
        return
    imprimir(ip, armar_ticket(payload))


def main():
    print("Agente de impresion Quesillos POS")
    print(f"Servidor: {SERVIDOR_URL}")
    print(f"Impresoras configuradas: {IMPRESORAS}")
    print()
    while True:
        try:
            sio.connect(SERVIDOR_URL)
            sio.wait()
        except KeyboardInterrupt:
            print("\nCerrado por el usuario.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[error de conexion] {e} -- reintentando en 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
