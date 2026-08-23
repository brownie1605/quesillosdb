from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Producto, Categoria, Inventario, Marca, UnidadMedida
from datetime import datetime
import os
import io
from werkzeug.utils import secure_filename
from flask import send_file

from app.utils.decorators import require_roles, usuario_tiene_rol

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
    resultado = []
    for p in productos:
        cat = Categoria.query.get(p.id_categoria) if p.id_categoria else None
        inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
        
        data = p.to_dict()
        data["categoria_nombre"] = cat.nombre if cat else "Sin Categoría"
        data["precio_compra"] = float(p.precio_compra) if p.precio_compra else 0.0
        data["stock"] = float(inv.stock_actual) if inv else 0.0
        data["stock_minimo"] = float(inv.stock_minimo) if inv and inv.stock_minimo else 0.0
        data["estado"] = p.estado
        data["id_marca"] = p.id_marca
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

@producto_bp.route("/api/marcas", methods=["GET"])
@login_required
def api_marcas():
    marcas = Marca.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([m.to_dict() for m in marcas])

@producto_bp.route("/api/marcas/crear", methods=["POST"])
@login_required
def api_marcas_crear():
    error = _solo_admin()
    if error:
        return error
    data = request.json
    try:
        nueva_marca = Marca(
            id_empresa=current_user.id_empresa,
            nombre=data.get("nombre", ""),
            estado="activo"
        )
        db.session.add(nueva_marca)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


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
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads', 'productos')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        imagen_file = request.files.get('imagen')
        imagen_url = None
        imagen_datos = None
        imagen_mimetype = None

        if imagen_file and imagen_file.filename:
            imagen_datos = imagen_file.read()
            imagen_mimetype = imagen_file.mimetype

        tipo_producto = request.form.get("tipo_producto") or "final"
        # Insumo/material son solo para costear recetas: no se venden, no
        # llevan categoria propia ni impuesto. Solo "final" es vendible.
        vendible = tipo_producto == "final"

        nuevo_prod = Producto(
            id_empresa=current_user.id_empresa,
            id_categoria=(request.form.get("id_categoria") or None) if vendible else None,
            id_marca=request.form.get("id_marca") or None,
            id_unidad=request.form.get("id_unidad") or None,
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
            
        # Generar código automáticamente si no se proporcionó
        if not nuevo_prod.codigo or nuevo_prod.codigo.strip() == "":
            nuevo_prod.codigo = f"P{nuevo_prod.id_producto:03d}"
            
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
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/editar/<int:id>", methods=["POST"])
@login_required
def api_editar(id):
    error = _solo_admin()
    if error:
        return error
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads', 'productos')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403

        imagen_file = request.files.get('imagen')
        if imagen_file and imagen_file.filename:
            prod.imagen_datos = imagen_file.read()
            prod.imagen_mimetype = imagen_file.mimetype
            prod.imagen_url = f"/productos/imagen/{prod.id_producto}"

        prod.codigo = request.form.get("codigo", prod.codigo)
        prod.codigo_barra = request.form.get("codigo_barra", prod.codigo_barra)
        prod.nombre = request.form.get("nombre", prod.nombre)
        prod.descripcion = request.form.get("descripcion", prod.descripcion)
        prod.id_marca = request.form.get("id_marca") or None
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
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/eliminar/<int:id>", methods=["DELETE"])
@login_required
def api_eliminar(id):
    error = _solo_admin()
    if error:
        return error
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        prod.estado = "inactivo"
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("ELIMINAR PRODUCTO", "Productos", f"Producto {prod.nombre} marcado como inactivo")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/entrada/<int:id>", methods=["POST"])
@login_required
def api_entrada(id):
    data = request.json
    cantidad = float(data.get("cantidad", 0.0))
    if cantidad <= 0:
        return jsonify({"success": False, "message": "Cantidad debe ser mayor a 0"}), 400
        
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        inv = Inventario.query.filter_by(id_producto=id).first()
        if not inv:
            return jsonify({"success": False, "message": "Inventario no encontrado para este producto"}), 404
            
        inv.stock_actual = float(inv.stock_actual) + cantidad
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

def _num(valor):
    """Convierte celdas de Excel (numero, texto o vacio) a float sin tronar."""
    try:
        if valor is None or valor == "":
            return 0.0
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _si_no(valor):
    return str(valor or "").strip().lower() in ("si", "sí", "s", "yes", "true", "1", "x")


@producto_bp.route("/api/importar_masivo", methods=["POST"])
@login_required
def api_importar_masivo():
    """Carga masiva de productos + inventario desde la plantilla de Excel
    (parseada en el navegador con SheetJS y enviada aqui como JSON).

    Empareja cada fila con un producto existente por Codigo, o si no, por
    Nombre (sin importar mayusculas); si no encuentra nada, crea uno nuevo.
    El Stock Actual/Minimo de la fila REEMPLAZA el que tenga el producto.
    """
    error = _solo_admin()
    if error:
        return error

    data = request.json or {}
    filas = data.get("filas") or []
    if not filas:
        return jsonify({"success": False, "message": "No se recibieron filas para importar"}), 400

    TIPOS_VALIDOS = {"final", "insumo", "material"}

    categorias_cache = {
        c.nombre.strip().lower(): c
        for c in Categoria.query.filter_by(id_empresa=current_user.id_empresa, estado="activo").all()
    }
    marcas_cache = {
        m.nombre.strip().lower(): m
        for m in Marca.query.filter_by(id_empresa=current_user.id_empresa, estado="activo").all()
    }
    unidades_cache = {}
    for u in UnidadMedida.query.filter_by(estado="activo").all():
        unidades_cache[u.nombre.strip().lower()] = u
        if u.abreviatura:
            unidades_cache[u.abreviatura.strip().lower()] = u

    creados = 0
    actualizados = 0
    errores = []

    for idx, fila in enumerate(filas, start=2):  # fila 1 = encabezados en el Excel
        try:
            nombre = (fila.get("nombre") or "").strip()
            if not nombre:
                errores.append(f"Fila {idx}: falta el nombre")
                continue

            tipo = (fila.get("tipo") or "final").strip().lower()
            if tipo not in TIPOS_VALIDOS:
                tipo = "final"
            vendible = tipo == "final"

            codigo = (fila.get("codigo") or "").strip()

            prod = None
            if codigo:
                prod = Producto.query.filter_by(id_empresa=current_user.id_empresa, codigo=codigo).first()
            if not prod:
                prod = Producto.query.filter(
                    Producto.id_empresa == current_user.id_empresa,
                    db.func.lower(Producto.nombre) == nombre.lower(),
                ).first()

            id_categoria = None
            if vendible:
                cat_nombre = (fila.get("categoria") or "").strip()
                if cat_nombre:
                    cat = categorias_cache.get(cat_nombre.lower())
                    if not cat:
                        cat = Categoria(id_empresa=current_user.id_empresa, nombre=cat_nombre, estado="activo")
                        db.session.add(cat)
                        db.session.flush()
                        categorias_cache[cat_nombre.lower()] = cat
                    id_categoria = cat.id_categoria

            id_marca = None
            marca_nombre = (fila.get("marca") or "").strip()
            if marca_nombre:
                marca = marcas_cache.get(marca_nombre.lower())
                if not marca:
                    marca = Marca(id_empresa=current_user.id_empresa, nombre=marca_nombre, estado="activo")
                    db.session.add(marca)
                    db.session.flush()
                    marcas_cache[marca_nombre.lower()] = marca
                id_marca = marca.id_marca

            id_unidad = None
            unidad_nombre = (fila.get("unidad") or "").strip()
            if unidad_nombre:
                uni = unidades_cache.get(unidad_nombre.lower())
                if uni:
                    id_unidad = uni.id_unidad

            precio_compra = _num(fila.get("precio_compra"))
            precio_venta = _num(fila.get("precio_venta")) if vendible else 0.0
            stock_actual = _num(fila.get("stock_actual"))
            stock_minimo = _num(fila.get("stock_minimo"))
            aplica_iva = vendible and _si_no(fila.get("aplica_impuesto"))

            es_nuevo = prod is None
            if prod:
                prod.nombre = nombre
                prod.tipo_producto = tipo
                prod.id_categoria = id_categoria
                if id_marca:
                    prod.id_marca = id_marca
                if id_unidad:
                    prod.id_unidad = id_unidad
                prod.precio_compra = precio_compra
                prod.precio_venta = precio_venta
                prod.aplica_impuesto = aplica_iva
                prod.se_vende = vendible
                prod.estado = "activo"
            else:
                prod = Producto(
                    id_empresa=current_user.id_empresa,
                    id_categoria=id_categoria,
                    id_marca=id_marca,
                    id_unidad=id_unidad,
                    codigo=codigo,
                    nombre=nombre,
                    precio_compra=precio_compra,
                    precio_venta=precio_venta,
                    aplica_impuesto=aplica_iva,
                    tipo_producto=tipo,
                    se_vende=vendible,
                    estado="activo",
                )
                db.session.add(prod)

            db.session.flush()  # asegura id_producto para el inventario

            inv = Inventario.query.filter_by(id_producto=prod.id_producto).first()
            if not inv:
                inv = Inventario(
                    id_sucursal=current_user.id_sucursal,
                    id_producto=prod.id_producto,
                    stock_actual=0.0,
                    stock_minimo=0.0,
                )
                db.session.add(inv)
            inv.stock_actual = stock_actual
            inv.stock_minimo = stock_minimo

            # Se confirma fila por fila: si una fila falla al guardar (ej. un
            # dato invalido para la BD), un rollback() deshace TODA la
            # transaccion en SQLAlchemy, no solo esa fila. Comitear aqui
            # evita perder las filas anteriores que sí estaban bien, y solo
            # contamos la fila como creada/actualizada si el commit funciono.
            db.session.commit()
            if es_nuevo:
                creados += 1
            else:
                actualizados += 1

        except Exception as e:  # noqa: BLE001 - una fila mala no debe tumbar el resto
            db.session.rollback()
            errores.append(f"Fila {idx} ({fila.get('nombre', '?')}): {e}")

    try:
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria(
            "IMPORTAR PRODUCTOS",
            "Productos",
            f"Importacion masiva: {creados} creados, {actualizados} actualizados, {len(errores)} con error",
        )
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "success": True,
        "creados": creados,
        "actualizados": actualizados,
        "errores": errores,
    })


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
