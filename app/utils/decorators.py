"""Control de acceso por rol.

Roles del sistema: Admin, Cocinero, Cajero, Mesero.
El Admin siempre pasa cualquier verificacion.
"""
from functools import wraps

from flask import abort, redirect, url_for, flash, request, jsonify
from flask_login import current_user

ADMIN_ALIASES = ("admin", "administrador")

# Pantalla de inicio de cada rol (nombre del rol en minusculas -> endpoint).
# Es la que se abre al entrar, al abrir la app ya con sesion y a donde se
# manda a quien intenta abrir una pantalla que no es suya.
DESTINO_POR_ROL = {
    "admin": "dashboard.dashboard",
    "administrador": "dashboard.dashboard",
    "cajero": "venta.pos",
    "mesero": "mesa.lista",
    "cocinero": "cocina.pendientes",
    "inventario": "inventario.lista",       # puede abrir Inventario, Compras y Proveedores (no Productos)
}
# Un rol sin pantalla propia (ej. Bodeguero) cae en Configuracion: es la unica
# que cualquier usuario con sesion puede abrir.
DESTINO_POR_DEFECTO = "configuracion.index"


def destino_inicial(user=None):
    """Endpoint de la pantalla de inicio del usuario segun su rol."""
    user = user or current_user
    rol = getattr(user, "rol_nombre", "") or ""
    return DESTINO_POR_ROL.get(rol, DESTINO_POR_DEFECTO)


def _es_api():
    # Las rutas de API real van bajo el prefijo de cada blueprint
    # ("/ventas/api/...", "/mesas/api/...", "/productos/api/..."), nunca
    # bajo "/api/" a secas -- ese prefijo literal no calzaba con nada, asi
    # que toda falla de sesion/rol en un endpoint AJAX terminaba
    # devolviendo un redirect HTML (a /login o al dashboard) en vez de un
    # JSON 401/403, lo que el fetch() del frontend no esperaba y quedaba
    # colgado o mostraba errores confusos en vez del mensaje real.
    if "/api/" in request.path:
        return True
    return request.accept_mimetypes.best == "application/json"


def _normalizar(roles):
    return {r.strip().lower() for r in roles}


def _rol_actual():
    if not current_user.is_authenticated or not current_user.rol:
        return None
    return (current_user.rol.nombre or "").strip().lower()


def usuario_tiene_rol(*roles):
    rol = _rol_actual()
    if rol is None:
        return False
    if rol in ADMIN_ALIASES:
        return True
    return rol in _normalizar(roles)


def require_roles(*roles):
    """Uso como blueprint.before_request: `return require_roles('Cajero')`."""
    if not current_user.is_authenticated:
        if _es_api():
            return jsonify({"success": False, "message": "No autenticado"}), 401
        flash("Debes iniciar sesión para acceder.", "warning")
        return redirect(url_for("auth.login"))

    if not usuario_tiene_rol(*roles):
        if _es_api():
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
        destino = destino_inicial()
        if request.endpoint == destino:
            # Ni su propia pantalla de inicio le dan: mostrar "acceso denegado"
            # en vez de rebotarlo en circulo sin fin.
            abort(403)
        flash("No tienes permisos para acceder a esta página.", "danger")
        return redirect(url_for(destino))
    return None


def roles_requeridos(*roles):
    """Decorador por vista: @roles_requeridos('Admin', 'Cocinero')."""

    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            resultado = require_roles(*roles)
            if resultado is not None:
                return resultado
            return f(*args, **kwargs)

        return wrapper

    return decorador


def solo_admin(f):
    return roles_requeridos("Admin")(f)
