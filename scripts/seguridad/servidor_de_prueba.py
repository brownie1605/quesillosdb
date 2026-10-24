#!/usr/bin/env python3
"""Servidor de prueba para validar las defensas SIN tocar MySQL.

Levanta la app real en http://127.0.0.1:5099 usando una base SQLite en
memoria (se crea vacia y se borra al cerrar). Sirve para correr
`validar_defensas.py` en cualquier maquina sin tener que configurar MySQL
ni el .env. NO es el servidor del negocio: para eso se usa `run.py`.

Uso:
    # Terminal 1
    python scripts/seguridad/servidor_de_prueba.py
    # Terminal 2
    python scripts/seguridad/validar_defensas.py --url http://127.0.0.1:5099
"""
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "tests"))

from conftest import TestConfig  # noqa: E402  (config de pruebas: SQLite en memoria)
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


class ConfigServidorDePrueba(TestConfig):
    # Las defensas de red ENCENDIDAS (es lo que queremos medir), pero sin
    # CSRF para poder golpear /login con un POST simple desde el validador.
    TESTING = False
    RATELIMIT_ENABLED = True
    WTF_CSRF_ENABLED = False


app = create_app(ConfigServidorDePrueba, iniciar_jobs=False)
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    print("Servidor de prueba en http://127.0.0.1:5099  (SQLite en memoria; Ctrl+C para salir)")
    app.run(host="127.0.0.1", port=5099, threaded=True)
