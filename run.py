"""Punto de entrada de Quesillos Lo Nuestro POS (local + nube)."""
import os

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "production") != "production"
    socketio.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 5000)),
        debug=debug,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
