"""Mesas: Mesas -> Pedido (cuenta abierta) -> Cobrar."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.utils.errores import respuesta_error_interno
from app.extensions import db
from app.models import Mesa, Venta, DetalleVenta
from app.services.mesa_service import MesaService, MesaError
from app.services.venta_service import VentaService, VentaError
from app.services.inventario_service import StockInsuficiente
from app.services.receta_service import RecetaError
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles, usuario_tiene_rol

mesa_bp = Blueprint("mesa", __name__, url_prefix="/mesas")


@mesa_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero", "Mesero")


# ---------------------------------------------------------------- vistas
@mesa_bp.route("/")
@login_required
def lista():
    mesas = MesaService.listar()
    return render_template(
        "mesas/lista.html",
        mesas=[m for m in mesas if m.tipo == "mesa"],
        para_llevar=[m for m in mesas if m.tipo == "llevar"],
        barra=[m for m in mesas if m.tipo == "barra"],
    )


@mesa_bp.route("/<int:id_mesa>/pedido")
@login_required
def pedido(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    return render_template("mesas/pedido.html", mesa=mesa)


# ---------------------------------------------------------------- API
@mesa_bp.route("/api/<int:id_mesa>/atender", methods=["POST"])
@login_required
def api_atender(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    try:
        venta = VentaService.abrir_mesa(mesa, current_user, cart=[])
        registrar_auditoria("ATENDER MESA", "Mesas", {"mesa": mesa.nombre, "venta": venta.id_venta})
        return jsonify({"success": True, "id_venta": venta.id_venta})
    except (MesaError, VentaError) as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


def _cuenta_elegida(mesa, id_venta=None):
    """La cuenta abierta sobre la que se trabaja: la que pide la pantalla
    (Cuenta 1, Cuenta 2, ... cuando se separo) o la de la mesa."""
    if id_venta:
        venta = Venta.query.get(int(id_venta))
        if venta and venta.id_mesa == mesa.id_mesa and venta.estado == "pendiente":
            return venta
    if mesa.id_venta_actual:
        return Venta.query.get(mesa.id_venta_actual)
    return None


@mesa_bp.route("/<int:id_mesa>/precuenta")
@login_required
def precuenta(id_mesa):
    """Ticket para mostrarle al cliente cuanto lleva, SIN cobrar: solo lee la
    cuenta (no toca caja, inventario ni el estado de la venta)."""
    from decimal import Decimal
    from app.utils.date_utils import nicaragua_now

    mesa = Mesa.query.get_or_404(id_mesa)
    cuentas = VentaService.cuentas_de_mesa(mesa)
    venta = _cuenta_elegida(mesa, request.args.get("venta", type=int))
    if not venta or venta.estado != "pendiente":
        return "Esta mesa no tiene una cuenta abierta", 404

    ids = [c.id_venta for c in cuentas]
    base = Decimal(str(venta.subtotal or 0)) - Decimal(str(venta.descuento or 0))
    propina = (max(base, Decimal("0")) * Decimal("0.10")).quantize(Decimal("0.01"))
    return render_template(
        "mesas/precuenta.html",
        mesa=mesa, venta=venta, detalles=list(venta.detalles),
        numero_cuenta=ids.index(venta.id_venta) + 1 if venta.id_venta in ids else 1,
        total_cuentas=len(cuentas),
        total_sin_propina=max(base, Decimal("0")).quantize(Decimal("0.01")),
        propina=propina,
        total_con_propina=(max(base, Decimal("0")) + propina).quantize(Decimal("0.01")),
        ahora=nicaragua_now(),
    )


@mesa_bp.route("/api/<int:id_mesa>/cuenta", methods=["GET"])
@login_required
def api_cuenta(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    cuentas = VentaService.cuentas_de_mesa(mesa)
    if not cuentas:
        return jsonify({"mesa": mesa.to_dict(), "venta": None, "detalles": [], "cuentas": []})

    venta = _cuenta_elegida(mesa, request.args.get("venta", type=int)) or cuentas[0]
    if venta.id_venta not in [c.id_venta for c in cuentas]:
        venta = cuentas[0]
    datos = venta.to_dict()
    datos["id_cliente"] = venta.id_cliente
    datos["cliente_nombre"] = venta.cliente.nombre if venta.cliente else None
    return jsonify({
        "mesa": mesa.to_dict(),
        "venta": datos,
        "detalles": [d.to_dict() for d in venta.detalles],
        "cuentas": [
            {"id_venta": c.id_venta, "numero": i + 1, "total": float(c.total or 0)}
            for i, c in enumerate(cuentas)
        ],
    })


@mesa_bp.route("/api/<int:id_mesa>/agregar", methods=["POST"])
@login_required
def api_agregar(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"success": False, "message": "No hay productos que agregar"}), 400

    try:
        if not mesa.id_venta_actual:
            venta = VentaService.abrir_mesa(mesa, current_user, cart=items)
        else:
            venta = _cuenta_elegida(mesa, data.get("id_venta"))
            venta = VentaService.agregar_items(venta, items, current_user)

        from app.services.notificacion_service import NotificacionService
        NotificacionService.avisar_nuevo_pedido(id_mesa, current_user.nombre_completo)

        from app.services.impresion_service import ImpresionService
        ImpresionService.emitir_comandas(mesa.nombre, items, current_user.nombre_completo)

        return jsonify({"success": True, "venta": venta.to_dict()})
    except StockInsuficiente as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e), "faltantes": e.faltantes}), 409
    except (MesaError, VentaError, RecetaError) as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/quitar/<int:id_detalle>", methods=["DELETE", "POST"])
@login_required
def api_quitar_item(id_mesa, id_detalle):
    mesa = Mesa.query.get_or_404(id_mesa)
    if not mesa.id_venta_actual:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400
    det = DetalleVenta.query.get(id_detalle)
    venta = _cuenta_elegida(mesa, det.id_venta if det else None)
    try:
        venta = VentaService.quitar_item(venta, id_detalle, current_user)
        return jsonify({"success": True, "venta": venta.to_dict()})
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/cobrar", methods=["POST"])
@login_required
def api_cobrar(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    if not mesa.id_venta_actual:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400

    data = request.get_json(silent=True) or {}
    venta = _cuenta_elegida(mesa, data.get("id_venta"))
    try:
        venta = VentaService.cobrar_mesa(
            venta, current_user,
            metodo_pago=data.get("metodo_pago", "Efectivo"),
            descuento=float(data.get("descuento", 0.0) or 0),
            propina=float(data.get("propina", 0.0) or 0),
            monto_recibido=float(data.get("monto_recibido", 0.0) or 0),
            id_cliente=data.get("id_cliente"),
            notas=data.get("notas"),
            pagos=data.get("pagos"),
        )
        registrar_auditoria(
            "COBRAR MESA", "Mesas",
            {"mesa": mesa.nombre, "venta": venta.id_venta, "total": float(venta.total)},
        )
        return jsonify({
            "success": True, "venta_id": venta.id_venta,
            "numero_venta": venta.numero_venta, "total": float(venta.total),
            "cambio": float(venta.cambio or 0),
            "cuentas_restantes": len(VentaService.cuentas_de_mesa(mesa)),
        })
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return respuesta_error_interno(e)


@mesa_bp.route("/api/<int:id_mesa>/separar", methods=["POST"])
@login_required
def api_separar(id_mesa):
    """Pasa productos de una cuenta a una cuenta nueva de la misma mesa."""
    mesa = Mesa.query.get_or_404(id_mesa)
    data = request.get_json(silent=True) or {}
    venta = _cuenta_elegida(mesa, data.get("id_venta"))
    if not venta:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400
    try:
        nueva = VentaService.separar_cuenta(venta, data.get("movimientos") or [], current_user)
        registrar_auditoria(
            "SEPARAR CUENTA", "Mesas",
            {"mesa": mesa.nombre, "de_venta": venta.id_venta, "a_venta": nueva.id_venta},
        )
        return jsonify({"success": True, "id_venta": nueva.id_venta,
                        "cuentas": len(VentaService.cuentas_de_mesa(mesa))})
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/descuento", methods=["POST"])
@login_required
def api_descuento(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    data = request.get_json(silent=True) or {}
    venta = _cuenta_elegida(mesa, data.get("id_venta"))
    if not venta:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400
    try:
        venta = VentaService.fijar_descuento(venta, data.get("porcentaje", 0))
        registrar_auditoria(
            "DESCUENTO CUENTA", "Mesas",
            {"mesa": mesa.nombre, "venta": venta.id_venta,
             "porcentaje": float(venta.descuento_pct or 0), "monto": float(venta.descuento or 0)},
        )
        return jsonify({"success": True, "venta": venta.to_dict()})
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/cliente", methods=["POST"])
@login_required
def api_cliente(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    data = request.get_json(silent=True) or {}
    venta = _cuenta_elegida(mesa, data.get("id_venta"))
    if not venta:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400
    try:
        VentaService.fijar_cliente(venta, data.get("id_cliente"))
        return jsonify({"success": True})
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/gestion", methods=["GET"])
@login_required
def api_gestion():
    """Listado simple para el admin (crear/desactivar mesas)."""
    return jsonify([m.to_dict() for m in Mesa.query.order_by(Mesa.orden).all()])


@mesa_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    mesa = MesaService.crear(
        nombre, tipo=data.get("tipo", "mesa"), capacidad=int(data.get("capacidad", 4) or 4)
    )
    return jsonify({"success": True, "mesa": mesa.to_dict()})


@mesa_bp.route("/api/<int:id_mesa>/desactivar", methods=["POST"])
@login_required
def api_desactivar(id_mesa):
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    try:
        MesaService.desactivar(id_mesa)
        return jsonify({"success": True})
    except MesaError as e:
        return jsonify({"success": False, "message": str(e)}), 400
