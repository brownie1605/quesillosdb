from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Producto, Cliente, Venta, DetalleVenta, Inventario, Categoria
from app.services.auditoria_service import registrar_auditoria
from app.services.venta_service import VentaService
from app.services.receta_service import RecetaService
from app.services.inventario_service import InventarioService, StockInsuficiente
from app.services.network_service import NetworkService
from app.services.sync_service import SyncService
from app.utils.decorators import require_roles, usuario_tiene_rol

venta_bp = Blueprint("venta", __name__, url_prefix="/ventas")


@venta_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero", "Mesero")


# ---------------------------------------------------------------- vistas
@venta_bp.route("/pos")
@login_required
def pos():
    return render_template("ventas/pos.html")


@venta_bp.route("/historial")
@login_required
def historial():
    return render_template("ventas/historial.html")


# ---------------------------------------------------------------- API
@venta_bp.route("/api/historial", methods=["GET"])
@login_required
def api_historial():
    q = Venta.query.filter_by(id_empresa=current_user.id_empresa)
    # El mesero solo ve sus propias ventas.
    if usuario_tiene_rol("Mesero") and not usuario_tiene_rol("Admin", "Administrador", "Cajero"):
        q = q.filter_by(id_usuario=current_user.id_usuario)
    ventas = q.order_by(Venta.fecha_venta.desc()).limit(500).all()

    res = []
    for v in ventas:
        cliente = Cliente.query.get(v.id_cliente) if v.id_cliente else None
        d = v.to_dict()
        d["cliente"] = cliente.nombre if cliente else "Público General"
        d["usuario"] = v.usuario.nombre_completo if v.usuario else None
        res.append(d)
    return jsonify(res)


@venta_bp.route("/api/historial/<int:id_venta>/detalles", methods=["GET"])
@login_required
def api_historial_detalles(id_venta):
    venta = Venta.query.get_or_404(id_venta)
    if venta.id_empresa != current_user.id_empresa:
        return jsonify({"success": False, "message": "Acceso denegado"}), 403

    detalles = DetalleVenta.query.filter_by(id_venta=id_venta).all()
    resultado = []
    for d in detalles:
        producto = Producto.query.get(d.id_producto)
        resultado.append(
            {
                "producto": producto.nombre if producto else "Desconocido",
                "cantidad": float(d.cantidad),
                "precio_unitario": float(d.precio_unitario),
                "subtotal": float(d.subtotal),
                "consumio_receta": bool(d.consumio_receta),
                "comentario": d.comentario,
            }
        )
    return jsonify(resultado)


@venta_bp.route("/api/productos", methods=["GET"])
@login_required
def api_productos():
    """Catalogo vendible: productos finales + insumos marcados como vendibles."""
    productos = (
        Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa)
        .filter(Producto.tipo_producto.in_(["final", "insumo"]))
        .order_by(Producto.nombre)
        .all()
    )
    categorias = {c.id_categoria: c.nombre for c in Categoria.query.all()}

    resultado = []
    for p in productos:
        if p.se_vende is False:
            continue
        data = p.to_dict()
        data["categoria_nombre"] = categorias.get(p.id_categoria) or "Sin categoría"
        if p.es_receta:
            # Un producto con receta no tiene stock propio: depende de sus insumos.
            data["stock"] = RecetaService.maximo_producible(p.id_producto)
            data["stock_tipo"] = "receta"
            data["tiene_personalizacion"] = bool(
                p.receta and p.receta.estado == "activo" and p.receta.tiene_personalizacion
            )
        else:
            inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
            data["stock"] = float(inv.stock_actual) if inv else 0.0
            data["stock_tipo"] = "directo"
            data["tiene_personalizacion"] = False
        resultado.append(data)
    return jsonify(resultado)


@venta_bp.route("/api/personalizacion/<int:id_producto>", methods=["GET"])
@login_required
def api_personalizacion(id_producto):
    """Ingredientes que se pueden quitar y grupos de opciones (elige uno)
    para mostrar en el modal del POS antes de agregar el producto al carrito."""
    opciones = RecetaService.opciones_de_venta(id_producto)
    if not opciones:
        return jsonify({"tiene_personalizacion": False})
    opciones["tiene_personalizacion"] = True
    return jsonify(opciones)


@venta_bp.route("/api/clientes", methods=["GET"])
@login_required
def api_clientes():
    clientes = Cliente.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([c.to_dict() for c in clientes])


@venta_bp.route("/api/verificar-stock", methods=["POST"])
@login_required
def api_verificar_stock():
    """Comprueba el carrito antes de cobrar, expandiendo recetas."""
    data = request.get_json(silent=True) or {}
    cart = data.get("cart", [])
    if not cart:
        return jsonify({"success": True, "faltantes": []})
    try:
        requerimientos = RecetaService.requerimiento_de_carrito(cart)
        InventarioService.verificar_disponibilidad(requerimientos)
        return jsonify({"success": True, "faltantes": []})
    except StockInsuficiente as e:
        return jsonify({"success": False, "faltantes": e.faltantes, "message": str(e)})


@venta_bp.route("/api/cobrar", methods=["POST"])
@login_required
def api_cobrar():
    data = request.get_json(silent=True) or {}
    cart = data.get("cart", [])
    if not cart:
        return jsonify({"success": False, "message": "El carrito está vacío"}), 400

    try:
        venta = VentaService.registrar_venta(
            current_user,
            cart,
            metodo_pago=data.get("metodo_pago", "Efectivo"),
            descuento=float(data.get("descuento", 0.0) or 0),
            propina=float(data.get("propina", 0.0) or 0),
            id_cliente=data.get("id_cliente"),
            monto_recibido=float(data.get("monto_recibido", 0.0) or 0),
        )
        registrar_auditoria(
            "NUEVA VENTA", "Ventas",
            {"venta_id": venta.id_venta, "numero": venta.numero_venta, "total": float(venta.total)},
        )
        online = NetworkService.is_online()
        return jsonify(
            {
                "success": True,
                "message": "Venta procesada exitosamente"
                if online
                else "Venta guardada localmente. Se sincronizará al recuperar la conexión.",
                "venta_id": venta.id_venta,
                "numero_venta": venta.numero_venta,
                "total": float(venta.total),
                "cambio": float(venta.cambio or 0),
                "online": online,
                "pendientes_sync": SyncService.contar_pendientes(),
            }
        )
    except StockInsuficiente as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e), "faltantes": e.faltantes}), 409
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@venta_bp.route("/api/<int:id_venta>/anular", methods=["POST"])
@login_required
def api_anular(id_venta):
    if not usuario_tiene_rol("Admin", "Administrador", "Cajero"):
        return jsonify({"success": False, "message": "Sin permiso para anular"}), 403
    data = request.get_json(silent=True) or {}
    try:
        venta = VentaService.anular_venta(
            id_venta, current_user, data.get("motivo", "Anulada por el usuario")
        )
        registrar_auditoria("actualizar", "Ventas", {"venta_id": id_venta, "accion": "anular"})
        return jsonify({"success": True, "message": "Venta anulada", "venta": venta.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@venta_bp.route("/factura/<int:id_venta>", methods=["GET"])
@login_required
def ver_factura(id_venta):
    venta = Venta.query.get_or_404(id_venta)
    if venta.id_empresa != current_user.id_empresa:
        return "Acceso denegado", 403

    detalles = DetalleVenta.query.filter_by(id_venta=id_venta).all()
    return render_template("ventas/factura.html", venta=venta, detalles=detalles)
