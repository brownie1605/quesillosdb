"""Modulo de recetas: solo Admin y Cocinero."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Producto, Receta, UnidadMedida, Categoria
from app.services.receta_service import RecetaService, RecetaError
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles

receta_bp = Blueprint("receta", __name__, url_prefix="/recetas")


@receta_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cocinero")


# ---------------------------------------------------------------- vistas
@receta_bp.route("/")
@login_required
def lista():
    unidades = UnidadMedida.query.filter_by(estado="activo").all()
    return render_template("recetas/lista.html", unidades=unidades)


@receta_bp.route("/<int:id_receta>")
@login_required
def detalle(id_receta):
    receta = Receta.query.get_or_404(id_receta)
    return render_template("recetas/detalle.html", receta=receta)


@receta_bp.route("/api/categorias", methods=["GET"])
@login_required
def api_categorias():
    """Para el selector de categoria al crear un producto nuevo desde aqui."""
    categorias = Categoria.query.filter_by(estado="activo").order_by(Categoria.nombre).all()
    return jsonify([c.to_dict() for c in categorias])


# ---------------------------------------------------------------- API
@receta_bp.route("/api/lista", methods=["GET"])
@login_required
def api_lista():
    recetas = Receta.query.order_by(Receta.nombre).all()
    salida = []
    for r in recetas:
        d = r.to_dict()
        d["max_producible"] = RecetaService.maximo_producible(r.id_producto)
        d["precio_venta"] = float(r.producto.precio_venta or 0) if r.producto else 0
        d["margen"] = round(d["precio_venta"] - d["costo_total"], 2)
        salida.append(d)
    return jsonify(salida)


@receta_bp.route("/api/<int:id_receta>", methods=["GET"])
@login_required
def api_detalle(id_receta):
    receta = Receta.query.get_or_404(id_receta)
    d = receta.to_dict()
    d["max_producible"] = RecetaService.maximo_producible(receta.id_producto)
    return jsonify(d)


@receta_bp.route("/api/insumos-y-opciones/<int:id_producto>", methods=["GET"])
@login_required
def api_insumos_y_opciones(id_producto):
    """Vista previa de personalizacion para el admin/cocinero al editar la receta."""
    datos = RecetaService.opciones_de_venta(id_producto)
    return jsonify(datos or {"tiene_personalizacion": False})


@receta_bp.route("/api/productos-disponibles", methods=["GET"])
@login_required
def api_productos_disponibles():
    """Productos finales que aun no tienen receta."""
    con_receta = {r.id_producto for r in Receta.query.all()}
    productos = (
        Producto.query.filter(Producto.estado == "activo")
        .filter(Producto.tipo_producto == "final")
        .order_by(Producto.nombre)
        .all()
    )
    return jsonify([p.to_dict() for p in productos if p.id_producto not in con_receta])


@receta_bp.route("/api/insumos", methods=["GET"])
@login_required
def api_insumos():
    """Productos utilizables como ingrediente (insumos y materiales)."""
    from app.services.inventario_service import InventarioService

    productos = (
        Producto.query.filter(Producto.estado == "activo")
        .filter(Producto.tipo_producto.in_(["insumo", "material"]))
        .order_by(Producto.nombre)
        .all()
    )
    salida = []
    for p in productos:
        d = p.to_dict()
        d["stock"] = float(InventarioService.stock_de(p.id_producto))
        salida.append(d)
    return jsonify(salida)


@receta_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.get_json(silent=True) or {}
    try:
        id_producto = data.get("id_producto")
        receta = RecetaService.crear_receta(
            int(id_producto) if id_producto else None,
            data,
            data.get("ingredientes") or [],
            current_user.id_usuario,
            producto_nuevo=data.get("producto_nuevo"),
            grupos_opciones=data.get("grupos_opciones"),
        )
        registrar_auditoria(
            "crear", "recetas",
            {"id_receta": receta.id_receta, "producto": receta.nombre},
        )
        return jsonify({"success": True, "message": "Receta creada", "receta": receta.to_dict()})
    except RecetaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@receta_bp.route("/api/<int:id_receta>/actualizar", methods=["POST", "PUT"])
@login_required
def api_actualizar(id_receta):
    data = request.get_json(silent=True) or {}
    try:
        receta = RecetaService.actualizar_receta(
            id_receta, data, data.get("ingredientes"), current_user.id_usuario,
            grupos_opciones=data.get("grupos_opciones"),
        )
        registrar_auditoria("actualizar", "recetas", {"id_receta": id_receta})
        return jsonify({"success": True, "message": "Receta actualizada", "receta": receta.to_dict()})
    except RecetaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@receta_bp.route("/api/<int:id_receta>/eliminar", methods=["POST", "DELETE"])
@login_required
def api_eliminar(id_receta):
    try:
        RecetaService.eliminar_receta(id_receta, current_user.id_usuario)
        registrar_auditoria("eliminar", "recetas", {"id_receta": id_receta})
        return jsonify({"success": True, "message": "Receta eliminada"})
    except RecetaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@receta_bp.route("/api/<int:id_receta>/costo", methods=["GET"])
@login_required
def api_costo(id_receta):
    receta = Receta.query.get_or_404(id_receta)
    costo = float(RecetaService.calcular_costo_receta(receta))
    precio = float(receta.producto.precio_venta or 0) if receta.producto else 0
    return jsonify(
        {
            "costo_total": costo,
            "precio_venta": precio,
            "margen": round(precio - costo, 2),
            "margen_pct": round((precio - costo) / precio * 100, 2) if precio else 0,
            "max_producible": RecetaService.maximo_producible(receta.id_producto),
        }
    )
