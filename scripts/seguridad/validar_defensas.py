#!/usr/bin/env python3
"""Validador de defensas de Quesillos POS bajo carga real.

Para que sirve
--------------
Comprueba, contra el servidor DE VERDAD (sockets reales, no el cliente de
pruebas de Flask), que las defensas contra abuso siguen en pie:

  * El limite de peticiones (Flask-Limiter) responde 429 cuando un equipo
    inunda de peticiones, en vez de dejar pasar todo y saturar la base.
  * El servidor sigue atendiendo a los demas mientras un equipo lo
    bombardea (no se cae ni deja de responder).
  * Una conexion que manda la peticion byte a byte (lenta, tipo
    "slowloris") no deja colgado al servidor para todos.
  * Los endpoints de login y recuperacion cortan la fuerza bruta.

Esto es una herramienta DEFENSIVA: se corre contra TU propio servidor (por
defecto http://127.0.0.1:5000) para demostrar, con numeros, que aguanta.
No ataca sistemas ajenos y se niega a apuntar fuera de la red local salvo
que se le pase --permitir-remoto a conciencia.

Como se usa
-----------
    # 1. En una terminal, levanta el servidor:
    python run.py

    # 2. En otra, corre el validador:
    python scripts/seguridad/validar_defensas.py
    python scripts/seguridad/validar_defensas.py --url http://127.0.0.1:5000
    python scripts/seguridad/validar_defensas.py --solo flood

Devuelve codigo de salida 0 si TODAS las defensas respondieron como se
espera, y 1 si alguna fallo (util para integrarlo en CI o en una revision).

Solo usa la biblioteca estandar de Python: no instala nada.
"""
import argparse
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Colores suaves en terminal (se apagan solos si no es una consola).
_C = sys.stdout.isatty()
def verde(t):   return "\033[92m%s\033[0m" % t if _C else t
def rojo(t):    return "\033[91m%s\033[0m" % t if _C else t
def gris(t):    return "\033[90m%s\033[0m" % t if _C else t
def amar(t):    return "\033[93m%s\033[0m" % t if _C else t


def _pedir(url, metodo="GET", cuerpo=None, headers=None, timeout=5):
    """Una peticion HTTP. Devuelve (codigo, segundos) o (None, segundos)."""
    datos = cuerpo.encode() if isinstance(cuerpo, str) else cuerpo
    req = Request(url, data=datos, method=metodo, headers=headers or {})
    t0 = time.monotonic()
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, time.monotonic() - t0
    except HTTPError as e:
        return e.code, time.monotonic() - t0
    except (URLError, socket.timeout, ConnectionError, OSError):
        return None, time.monotonic() - t0


# ===================================================================
#  Resultado de cada prueba
# ===================================================================
class Resultado:
    def __init__(self):
        self.ok = True
        self.lineas = []

    def comprobar(self, condicion, descripcion, detalle=""):
        marca = verde("  PASA  ") if condicion else rojo("  FALLA ")
        self.lineas.append("%s %s %s" % (marca, descripcion, gris(detalle)))
        if not condicion:
            self.ok = False
        return condicion


# ===================================================================
#  Prueba 1: inundacion de peticiones (flood) -> debe aparecer 429
# ===================================================================
def prueba_flood(base, res, n=400, hilos=20):
    print(amar("\n[1] Inundacion de peticiones (flood) a /healthz"))
    print(gris("    Lanzando %d peticiones con %d hilos desde este equipo..." % (n, hilos)))
    url = base + "/healthz"
    codigos = []
    lock = threading.Lock()

    def golpe(_):
        c, _t = _pedir(url, timeout=5)
        with lock:
            codigos.append(c)

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        list(ex.map(golpe, range(n)))
    dur = time.monotonic() - t0

    exitosas = sum(1 for c in codigos if c == 200)
    limitadas = sum(1 for c in codigos if c == 429)
    caidas = sum(1 for c in codigos if c is None)

    print(gris("    %d respondidas en %.1fs  |  200=%d  429=%d  sin-respuesta=%d"
                % (len(codigos), dur, exitosas, limitadas, caidas)))

    res.comprobar(limitadas > 0,
                  "El limite de peticiones se activa bajo flood",
                  "(%d respuestas 429)" % limitadas)
    res.comprobar(caidas == 0,
                  "El servidor no deja peticiones sin respuesta durante el flood",
                  "(%d sin respuesta)" % caidas)


# ===================================================================
#  Prueba 2: sigue atendiendo a otros mientras lo bombardean
# ===================================================================
def prueba_disponibilidad_bajo_carga(base, res, segundos=5):
    print(amar("\n[2] Disponibilidad mientras un equipo bombardea"))
    print(gris("    Un hilo bombardea %ds; en paralelo medimos la latencia de /healthz..." % segundos))
    url = base + "/healthz"
    parar = threading.Event()

    def bombardear():
        while not parar.is_set():
            _pedir(url, timeout=3)

    hilos = [threading.Thread(target=bombardear, daemon=True) for _ in range(15)]
    for h in hilos:
        h.start()

    latencias, fallos = [], 0
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        c, t = _pedir(url, timeout=5)
        if c is None:
            fallos += 1
        else:
            latencias.append(t)
        time.sleep(0.1)
    parar.set()

    peor = max(latencias) if latencias else 0
    print(gris("    mediciones=%d  fallos=%d  peor latencia=%.2fs"
                % (len(latencias), fallos, peor)))
    res.comprobar(fallos == 0,
                  "El servidor responde a un cliente legitimo durante la carga",
                  "(%d fallos)" % fallos)
    res.comprobar(peor < 3.0,
                  "La latencia se mantiene usable bajo carga",
                  "(peor: %.2fs)" % peor)


# ===================================================================
#  Prueba 3: conexion lenta (estilo slowloris) no bloquea a los demas
# ===================================================================
def prueba_conexion_lenta(base, res):
    print(amar("\n[3] Conexion lenta que nunca termina de enviar (slowloris)"))
    u = urlparse(base)
    host, puerto = u.hostname, u.port or 80

    sockets_lentos = []
    try:
        for _ in range(10):
            s = socket.create_connection((host, puerto), timeout=5)
            # Empieza una peticion y JAMAS la termina (sin la linea en blanco).
            s.sendall(b"GET /healthz HTTP/1.1\r\nHost: %s\r\n" % host.encode())
            sockets_lentos.append(s)
        print(gris("    %d conexiones lentas abiertas y sostenidas." % len(sockets_lentos)))

        # Mientras tanto, un cliente normal debe RESPONDER rapido. Lo que
        # prueba el slowloris es que el servidor no queda colgado esperando
        # a las conexiones lentas: una respuesta veloz (200, o 429 si este
        # equipo ya gasto su cuota de peticiones) demuestra que sigue vivo;
        # lo que seria una falla es que no responda o tarde segundos.
        c, t = _pedir(base + "/healthz", timeout=5)
        print(gris("    Cliente normal en paralelo -> codigo=%s (%.2fs)" % (c, t)))
        res.comprobar(c is not None and t < 3.0,
                      "El servidor responde rapido pese a las conexiones lentas abiertas",
                      "(codigo %s en %.2fs)" % (c, t))
    except OSError as e:
        res.comprobar(False, "No se pudieron abrir las conexiones lentas", str(e))
    finally:
        for s in sockets_lentos:
            try:
                s.close()
            except OSError:
                pass


# ===================================================================
#  Prueba 4: fuerza bruta de login -> el endpoint corta con 429
# ===================================================================
def prueba_fuerza_bruta_login(base, res, n=40):
    print(amar("\n[4] Fuerza bruta contra /login"))
    print(gris("    %d intentos seguidos de contrasena..." % n))
    url = base + "/login"
    codigos = []
    for i in range(n):
        c, _t = _pedir(url, metodo="POST",
                       cuerpo="usuario=admin&password=prueba%d" % i,
                       headers={"Content-Type": "application/x-www-form-urlencoded"},
                       timeout=5)
        codigos.append(c)
    limitadas = sum(1 for c in codigos if c == 429)
    print(gris("    codigos: 429=%d  otros=%d" % (limitadas, len(codigos) - limitadas)))
    res.comprobar(limitadas > 0,
                  "El login corta la fuerza bruta con 429",
                  "(%d bloqueadas de %d)" % (limitadas, n))


# ===================================================================
def _es_local(url):
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    return host.startswith(("192.168.", "10.", "172.16.", "172.17.", "172.18.",
                            "172.19.", "172.2", "172.30.", "172.31."))


def main():
    ap = argparse.ArgumentParser(description="Valida las defensas de Quesillos POS bajo carga real.")
    ap.add_argument("--url", default="http://127.0.0.1:5000", help="URL del servidor (por defecto local).")
    ap.add_argument("--solo", choices=["flood", "disponibilidad", "lenta", "login"],
                    help="Correr una sola prueba.")
    ap.add_argument("--permitir-remoto", action="store_true",
                    help="Confirma que tienes permiso para probar una URL fuera de la red local.")
    args = ap.parse_args()

    base = args.url.rstrip("/")

    if not _es_local(base) and not args.permitir_remoto:
        print(rojo("Esta herramienta solo apunta a tu servidor local (127.0.0.1 / red privada)."))
        print(rojo("Probar un sistema que no es tuyo sin permiso puede ser ilegal."))
        print(gris("Si de verdad tienes autorizacion por escrito, agrega --permitir-remoto."))
        return 2

    # El servidor debe estar arriba.
    c, _ = _pedir(base + "/healthz", timeout=3)
    if c is None:
        print(rojo("No hay respuesta en %s" % base))
        print(gris("Levanta el servidor primero:  python run.py"))
        return 2

    print("Validando defensas de: " + base)
    print(gris("Objetivo: demostrar con numeros que el sistema aguanta abuso y sigue en pie."))

    res = Resultado()
    pruebas = {
        "flood": lambda: prueba_flood(base, res),
        "disponibilidad": lambda: prueba_disponibilidad_bajo_carga(base, res),
        "lenta": lambda: prueba_conexion_lenta(base, res),
        "login": lambda: prueba_fuerza_bruta_login(base, res),
    }
    if args.solo:
        pruebas[args.solo]()
    else:
        for p in pruebas.values():
            p()

    print("\n" + "=" * 60)
    for linea in res.lineas:
        print(linea)
    print("=" * 60)
    if res.ok:
        print(verde("TODAS las defensas respondieron como se espera."))
        return 0
    print(rojo("Alguna defensa no respondio como se espera (revisa arriba)."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
