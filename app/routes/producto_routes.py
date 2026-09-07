from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Producto, Categoria, Inventario, UnidadMedida, Proveedor
from datetime import datetime
import io
from flask import send_file

from app.utils.decorators import require_roles, usuario_tiene_rol
from app.utils.imagenes import leer_imagen_validada

producto_bp = Blueprint("producto", __name__, url_prefix="/productos")

@producto_bp.before_request
def check_roles():
    # Ver el catalogo: Admin, Cajero, Cocinero. Crear/editar/eliminar: solo Admin
    # (se valida aparte en cada endpoint de escritura, ver `_solo_admin`).
    # Insumos vive ahora dentro de Productos (filtro "Tipo"), asi que Mesero
    # tambien necesita poder verla, igual que antes con /insumos.
    return require_roles('Admin', 'Administrador', 'Cajero', 'Cocinero', 'Mesero')


def _solo_admin():
    if not usuario_tiene_rol('Admin', 'Administrador'):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    return None


@producto_bp.route("/")
@login_required
def lista():
    return render_template("productos/lista.html")

@producto_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()

    # Una sola consulta para categorias e inventario en vez de una por
    # producto (N+1): con el catalogo creciendo esto importa cada vez mas.
    categorias = {c.id_categoria: c.nombre for c in Categoria.query.all()}
    ids_producto = [p.id_producto for p in productos]
    inventarios = {
        inv.id_producto: inv
        for inv in Inventario.query.filter(Inventario.id_producto.in_(ids_producto)).all()
    } if ids_producto else {}

    resultado = []
    for p in productos:
        inv = inventarios.get(p.id_producto)

        data = p.to_dict()
        data["categoria_nombre"] = categorias.get(p.id_categoria, "Sin Categoría")
        data["precio_compra"] = float(p.precio_compra) if p.precio_compra else 0.0
        data["stock"] = float(inv.stock_actual) if inv else 0.0
        data["stock_minimo"] = float(inv.stock_minimo) if inv and inv.stock_minimo else 0.0
        data["estado"] = p.estado
        data["id_proveedor"] = p.id_proveedor
        data["id_unidad"] = p.id_unidad
        data["codigo_barra"] = p.codigo_barra
        data["descripcion"] = p.descripcion
        data["aplica_impuesto"] = p.aplica_impuesto
        resultado.append(data)
    return jsonify(resultado)

@producto_bp.route("/api/categorias", methods=["GET"])
@login_required
def api_categorias():
    categorias = Categoria.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([c.to_dict() for c in categorias])

@producto_bp.route("/api/proveedores", methods=["GET"])
@login_required
def api_proveedores_para_producto():
    """Lista de proveedores para el selector del formulario de producto."""
    proveedores = Proveedor.query.filter_by(
        estado="activo", id_empresa=current_user.id_empresa
    ).order_by(Proveedor.nombre).all()
    return jsonify([p.to_dict() for p in proveedores])


@producto_bp.route("/api/categorias/crear", methods=["POST"])
@login_required
def api_categorias_crear():
    """Crea una categoria (ej. Asados, Extras, Quesillos, Insumos) para
    agrupar productos en el panel de administracion y en el POS."""
    error = _solo_admin()
    if error:
        return error
    data = request.json or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    try:
        nueva = Categoria(
            id_empresa=current_user.id_empresa,
            nombre=nombre,
            descripcion=data.get("descripcion"),
            estado="activo",
        )
        db.session.add(nueva)
        db.session.commit()
        return jsonify({"success": True, "categoria": nueva.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/unidades", methods=["GET"])
@login_required
def api_unidades():
    unidades = UnidadMedida.query.filter_by(estado="activo").all()
    return jsonify([u.to_dict() for u in unidades])

@producto_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    error = _solo_admin()
    if error:
        return error
    try:
        imagen_file = request.files.get('imagen')
        imagen_url = None
        imagen_datos = None
        imagen_mimetype = None

        if imagen_file and imagen_file.filename:
            imagen_datos, imagen_mimetype = leer_imagen_validada(imagen_file)

        tipo_producto = request.form.get("tipo_producto") or "final"
        # Insumo/material son solo para costear recetas: no se venden, no
        # llevan categoria propia ni impuesto. Solo "final" es vendible.
        vendible = tipo_producto == "final"

        nuevo_prod = Producto(
            id_empresa=current_user.id_empresa,
            id_categoria=(request.form.get("id_categoria") or None) if vendible else None,
            id_proveedor=request.form.get("id_proveedor") or None,
            id_unidad=request.form.get("id_unidad") or None,
            impresora=request.form.get("impresora") or None,
            codigo=request.form.get("codigo", ""),
            codigo_barra=request.form.get("codigo_barra", ""),
            nombre=request.form.get("nombre"),
            descripcion=request.form.get("descripcion", ""),
            precio_compra=float(request.form.get("precio_compra", 0.0)),
            precio_venta=float(request.form.get("precio_venta", 0.0)) if vendible else 0.0,
            aplica_impuesto=(request.form.get("aplica_impuesto") == 'true') if vendible else False,
            tipo_producto=tipo_producto,
            se_vende=vendible,
            imagen_url=imagen_url,
            imagen_datos=imagen_datos,
            imagen_mimetype=imagen_mimetype,
            estado="activo"
        )
        db.session.add(nuevo_prod)
        db.session.flush() # Get ID
        
        if imagen_datos:
            nuevo_prod.imagen_url = f"/productos/imagen/{nuevo_prod.id_producto}"

        # El codigo se autogenera solo si viene vacio (ver evento
        # `_asignar_codigo` en app/models/producto.py), asi que ya esta
        # garantizado en este punto -- no hace falta reforzarlo aqui.

        # Crear inventario en 0
        nuevo_inv = Inventario(
            id_sucursal=current_user.id_sucursal,
            id_producto=nuevo_prod.id_producto,
            stock_actual=0.0,
            stock_minimo=float(request.form.get("stock_minimo", 0.0))
        )
        db.session.add(nuevo_inv)
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("CREAR PRODUCTO", "Productos", f"Producto {nuevo_prod.nombre} creado (Código: {nuevo_prod.codigo})")
        return jsonify({"success": True})
    except ValueError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/editar/<int:id>", methods=["POST"])
@login_required
def api_editar(id):
    error = _solo_admin()
    if error:
        return error
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403

        imagen_file = request.files.get('imagen')
        if imagen_file and imagen_file.filename:
            prod.imagen_datos, prod.imagen_mimetype = leer_imagen_validada(imagen_file)
            prod.imagen_url = f"/productos/imagen/{prod.id_producto}"

        prod.codigo = request.form.get("codigo", prod.codigo)
        prod.codigo_barra = request.form.get("codigo_barra", prod.codigo_barra)
        prod.nombre = request.form.get("nombre", prod.nombre)
        prod.descripcion = request.form.get("descripcion", prod.descripcion)
        prod.id_proveedor = request.form.get("id_proveedor") or None
        prod.impresora = request.form.get("impresora") or None
        prod.id_unidad = request.form.get("id_unidad") or None
        prod.precio_compra = float(request.form.get("precio_compra", prod.precio_compra or 0.0))
        if request.form.get("tipo_producto"):
            prod.tipo_producto = request.form.get("tipo_producto")

        # Insumo/material son solo para costear recetas: no se venden, no
        # llevan categoria propia ni impuesto. Solo "final" es vendible.
        vendible = prod.tipo_producto == "final"
        prod.id_categoria = (request.form.get("id_categoria") or None) if vendible else None
        prod.precio_venta = float(request.form.get("precio_venta", prod.precio_venta)) if vendible else 0.0
        prod.aplica_impuesto = (request.form.get("aplica_impuesto") == 'true') if vendible else False
        prod.se_vende = vendible

        # Actualizar stock mínimo si existe el registro de inventario
        inv = Inventario.query.filter_by(id_producto=prod.id_producto).first()
        if inv:
            inv.stock_minimo = float(request.form.get("stock_minimo", inv.stock_minimo or 0.0))
        
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("EDITAR PRODUCTO", "Productos", f"Producto {prod.nombre} modificado")
        return jsonify({"success": True})
    except ValueError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/estado/<int:id>", methods=["PUT", "POST"])
@login_required
def api_cambiar_estado(id):
    """Activa o desactiva un producto directamente (selector de estado en la
    tabla, con confirmacion desde el modal en el frontend)."""
    error = _solo_admin()
    if error:
        return error
    data = request.json or {}
    nuevo_estado = (data.get("estado") or "").strip().lower()
    if nuevo_estado not in ("activo", "inactivo"):
        return jsonify({"success": False, "message": "Estado invalido"}), 400
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403

        prod.estado = nuevo_estado
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria(
            "CAMBIAR ESTADO PRODUCTO", "Productos",
            f"Producto {prod.nombre} marcado como {nuevo_estado}",
        )
        return jsonify({"success": True, "estado": nuevo_estado})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500



@producto_bp.route("/imagen/<int:id>", methods=["GET"])
def obtener_imagen(id):
    prod = Producto.query.get_or_404(id)
    if prod.imagen_datos and prod.imagen_mimetype:
        return send_file(
            io.BytesIO(prod.imagen_datos),
            mimetype=prod.imagen_mimetype,
            as_attachment=False
        )
    # Retornar una imagen por defecto o error 404
    return "", 404
