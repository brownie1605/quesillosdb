"""Respuesta JSON para errores no previstos en las rutas de API.

Antes cada `except Exception as e` devolvia `str(e)` al navegador: el texto
crudo de la excepcion, que en un error de base de datos incluye la consulta
SQL, nombres de tablas/columnas y a veces el host de MySQL -- justo lo que
un atacante busca para afinar una inyeccion. El detalle completo (con la
traza) ahora va solo al log del servidor; el cliente recibe un mensaje
generico.
"""
from flask import current_app, jsonify


def respuesta_error_interno(e):
    if isinstance(e, ValueError):
        # Un dato mal formado que llego en la peticion (una fecha, un
        # numero) o una regla de negocio de los servicios ("stock
        # insuficiente"): culpa del cliente, no del servidor. Su mensaje se
        # escribe para el usuario y no trae SQL, asi que se conserva.
        current_app.logger.warning("Dato invalido en %s: %s", _ruta(), e)
        return jsonify({"success": False, "message": str(e) or "Datos invalidos en la solicitud."}), 400
    current_app.logger.exception("Error interno en %s", _ruta())
    return jsonify({"success": False, "message": "Ocurrió un error interno. Ya quedó registrado."}), 500


def _ruta():
    from flask import request

    return "%s %s" % (request.method, request.path)
