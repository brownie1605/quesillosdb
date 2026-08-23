from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Compra, DetalleCompra, Producto, Proveedor, Inventario, Categoria, Marca, UnidadMedida
from datetime import datetime
from app.utils.date_utils import nicaragua_now

from app.utils.decorators import require_roles

compra_bp = Blueprint("compra", __name__, url_prefix="/compras")

@compra_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@compra_bp.route("/")
@login_required
def lista():
    return render_template("compras/lista.html")

@compra_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    compras = Compra.query.filter_by(id_empresa=current_user.id_empresa).order_by(Compra.fecha_compra.desc()).all()
    res = []
    for c in compras:
        prov = Proveedor.query.get(c.id_proveedor) if c.id_proveedor else None
        d = c.to_dict()
        if c.tipo_compra == 'varios':
            d["proveedor_nombre"] = "Gasto Vario"
            if c.descripcion_gasto:
                d["proveedor_nombre"] += f" ({c.descripcion_gasto})"
        else:
            d["proveedor_nombre"] = prov.nombre if prov else "Desconocido"
        d["id_proveedor"] = c.id_proveedor
        res.append(d)
    return jsonify(res)

@compra_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.json
    id_proveedor = data.get("id_proveedor")
    items = data.get("items", [])
    
    if id_proveedor == "varios":
        descripcion = data.get("descripcion")
        monto = data.get("monto")
        if not descripcion or not monto:
            return jsonify({"success": False, "message": "Descripción y monto son obligatorios para gastos"}), 400
        
        try:
            prov_varios = Proveedor.query.filter(Proveedor.nombre.ilike('%varios%')).first()
            id_prov_varios = prov_varios.id_proveedor if prov_varios else None

            num_compra = f"GV-{nicaragua_now().strftime('%Y%m%d%H%M%S')}"
            nueva_compra = Compra(
                id_empresa=current_user.id_empresa,
                id_sucursal=current_user.id_sucursal,
                id_usuario=current_user.id_usuario,
                id_proveedor=id_prov_varios,
                numero_compra=num_compra,
                subtotal=float(monto),
                impuesto=0.0,
                total=float(monto),
                estado="completada",
                tipo_compra="varios",
                descripcion_gasto=descripcion
            )
            db.session.add(nueva_compra)
            db.session.commit()
            return jsonify({"success": True, "message": "Gasto vario registrado exitosamente"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)}), 500
            
    if not items:
        return jsonify({"success": False, "message": "No hay productos en la compra"}), 400
        
    try:
        subtotal_compra = 0.0
        num_compra = f"C-{nicaragua_now().strftime('%Y%m%d%H%M%S')}"
        
        nueva_compra = Compra(
            id_empresa=current_user.id_empresa,
            id_sucursal=current_user.id_sucursal,
            id_usuario=current_user.id_usuario,
            id_proveedor=id_proveedor,
            numero_compra=num_compra,
            subtotal=0.0,
            impuesto=0.0,
            total=0.0,
            estado="completada"
        )
        db.session.add(nueva_compra)
        db.session.flush()
        
        for item in items:
            producto_id = item.get("id_producto")
            cantidad = float(item.get("cantidad", 0))
            costo_unitario = float(item.get("costo_unitario", 0))
            subtotal_item = cantidad * costo_unitario
            subtotal_compra += subtotal_item
            
            detalle = DetalleCompra(
                id_compra=nueva_compra.id_compra,
                id_producto=producto_id,
                cantidad=cantidad,
                precio_unitario=costo_unitario,
                subtotal=subtotal_item
            )
            db.session.add(detalle)
            
            # Sumar al inventario
            inv = Inventario.query.filter_by(id_producto=producto_id).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) + cantidad
            else:
                inv = Inventario(
                    id_sucursal=current_user.id_sucursal,
                    id_producto=producto_id,
                    stock_actual=cantidad,
                    stock_minimo=0
                )
                db.session.add(inv)
                
        nueva_compra.subtotal = subtotal_compra
        nueva_compra.total = subtotal_compra # Asumimos 0 impuesto por ahora
        
        db.session.commit()
        return jsonify({"success": True, "message": "Compra registrada exitosamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@compra_bp.route("/api/detalle/<int:id>", methods=["GET"])
@login_required
def api_detalle(id):
    try:
        compra = Compra.query.get_or_404(id)
        if compra.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        detalles = DetalleCompra.query.filter_by(id_compra=id).all()
        res_detalles = []
        if compra.tipo_compra == 'varios':
            res_detalles.append({
                "producto_nombre": "Gasto Vario: " + (compra.descripcion_gasto or ""),
                "cantidad": 1,
                "precio_unitario": float(compra.total),
                "subtotal": float(compra.total)
            })
        else:
            for d in detalles:
                prod = Producto.query.get(d.id_producto)
                dt = d.to_dict()
                dt["producto_nombre"] = prod.nombre if prod else "Desconocido"
                res_detalles.append(dt)
            
        return jsonify({"success": True, "detalles": res_detalles})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@compra_bp.route("/api/editar/<int:id>", methods=["PUT"])
@login_required
def api_editar(id):
    compra = Compra.query.get_or_404(id)
    if compra.id_empresa != current_user.id_empresa:
        return jsonify({"success": False, "message": "Acceso denegado"}), 403
        
    data = request.json
    id_proveedor = data.get("id_proveedor")
    items = data.get("items", [])
    
    if id_proveedor == "varios":
        descripcion = data.get("descripcion")
        monto = data.get("monto")
        if not descripcion or not monto:
            return jsonify({"success": False, "message": "Descripción y monto son obligatorios para gastos"}), 400
        try:
            prov_varios = Proveedor.query.filter(Proveedor.nombre.ilike('%varios%')).first()
            id_prov_varios = prov_varios.id_proveedor if prov_varios else None

            compra.id_proveedor = id_prov_varios
            compra.tipo_compra = "varios"
            compra.descripcion_gasto = descripcion
            compra.subtotal = float(monto)
            compra.total = float(monto)
            db.session.commit()
            return jsonify({"success": True, "message": "Gasto actualizado exitosamente"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)}), 500

    if not items:
        return jsonify({"success": False, "message": "No hay productos en la compra"}), 400
        
    try:
        # 1. Revertir inventario de la compra anterior
        detalles_previos = DetalleCompra.query.filter_by(id_compra=id).all()
        for dp in detalles_previos:
            inv = Inventario.query.filter_by(id_producto=dp.id_producto).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) - float(dp.cantidad)
                
        # 2. Eliminar detalles de compra anteriores
        DetalleCompra.query.filter_by(id_compra=id).delete()
        
        # 3. Guardar nuevos datos de compra y calcular total
        compra.id_proveedor = id_proveedor
        subtotal_compra = 0.0
        
        for item in items:
            producto_id = item.get("id_producto")
            cantidad = float(item.get("cantidad", 0))
            costo_unitario = float(item.get("costo_unitario", 0))
            subtotal_item = cantidad * costo_unitario
            subtotal_compra += subtotal_item
            
            detalle = DetalleCompra(
                id_compra=compra.id_compra,
                id_producto=producto_id,
                cantidad=cantidad,
                precio_unitario=costo_unitario,
                subtotal=subtotal_item
            )
            db.session.add(detalle)
            
            # Sumar al inventario
            inv = Inventario.query.filter_by(id_producto=producto_id).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) + cantidad
            else:
                inv = Inventario(
                    id_sucursal=current_user.id_sucursal,
                    id_producto=producto_id,
                    stock_actual=cantidad,
                    stock_minimo=0
                )
                db.session.add(inv)
                
        compra.subtotal = subtotal_compra
        compra.total = subtotal_compra

        db.session.commit()
        return jsonify({"success": True, "message": "Compra actualizada exitosamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# Carga masiva de compras por Excel: "solo lo que se compra rellena el
# inventario". Cada fila es una linea de compra (producto, cantidad, costo,
# proveedor). El stock nunca se pisa: se SUMA a traves de una Compra real,
# igual que si se registrara a mano. Las filas se agrupan por Proveedor y
# se genera una Compra por cada proveedor distinto que aparezca.
# ============================================================================

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


@compra_bp.route("/api/importar_masivo", methods=["POST"])
@login_required
def api_importar_masivo():
    """Recibe filas ya parseadas en el navegador (SheetJS) desde la plantilla
    de Excel de "Cargar compra masiva" y registra una o mas Compras reales.

    Fase 1: por cada fila, crea o actualiza el Producto (sin tocar stock) y
    valida/crea Proveedor, Categoria, Marca, Unidad segun corresponda. Cada
    fila se confirma con su propio commit/rollback para que una fila mala no
    tumbe ni deje a medias las demas.
    Fase 2: agrupa las filas validas por Proveedor y genera una Compra con
    sus DetalleCompra por grupo; ahi es donde se suma el stock, igual que
    una compra registrada a mano. Cada grupo tambien tiene su propio
    commit/rollback.
    """
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
    proveedores_cache = {
        p.nombre.strip().lower(): p
        for p in Proveedor.query.filter_by(id_empresa=current_user.id_empresa, estado="activo").all()
    }
    unidades_cache = {}
    for u in UnidadMedida.query.filter_by(estado="activo").all():
        unidades_cache[u.nombre.strip().lower()] = u
        if u.abreviatura:
            unidades_cache[u.abreviatura.strip().lower()] = u

    errores = []
    filas_validas = []  # [{id_producto, id_proveedor, proveedor_nombre, cantidad, costo_unitario, es_nuevo}]

    # ---- Fase 1: producto por producto ----
    for idx, fila in enumerate(filas, start=2):  # fila 1 = encabezados en el Excel
        try:
            nombre = (fila.get("nombre") or "").strip()
            if not nombre:
                errores.append(f"Fila {idx}: falta el nombre del producto")
                continue

            cantidad = _num(fila.get("cantidad"))
            if cantidad <= 0:
                errores.append(f"Fila {idx} ({nombre}): la cantidad comprada debe ser mayor a 0")
                continue

            costo_unitario = _num(fila.get("costo_unitario"))

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
            es_nuevo = prod is None

            # Marca (para heredar su proveedor si la fila no trae uno propio)
            id_marca = None
            marca_obj = None
            marca_nombre = (fila.get("marca") or "").strip()
            if marca_nombre:
                marca_obj = marcas_cache.get(marca_nombre.lower())
                if not marca_obj:
                    marca_obj = Marca(id_empresa=current_user.id_empresa, nombre=marca_nombre, estado="activo")
                    db.session.add(marca_obj)
                    db.session.flush()
                    marcas_cache[marca_nombre.lower()] = marca_obj
                id_marca = marca_obj.id_marca

            # Proveedor: el de la fila, o si no viene, el de la marca elegida
            prov_nombre = (fila.get("proveedor") or "").strip()
            proveedor = None
            if prov_nombre:
                proveedor = proveedores_cache.get(prov_nombre.lower())
                if not proveedor:
                    proveedor = Proveedor(id_empresa=current_user.id_empresa, nombre=prov_nombre, estado="activo")
                    db.session.add(proveedor)
                    db.session.flush()
                    proveedores_cache[prov_nombre.lower()] = proveedor
            elif marca_obj and marca_obj.id_proveedor:
                proveedor = Proveedor.query.get(marca_obj.id_proveedor)

            if not proveedor:
                db.session.rollback()
                errores.append(f"Fila {idx} ({nombre}): falta el Proveedor (o una Marca que ya tenga proveedor asignado)")
                continue

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

            id_unidad = None
            unidad_nombre = (fila.get("unidad") or "").strip()
            if unidad_nombre:
                uni = unidades_cache.get(unidad_nombre.lower())
                if uni:
                    id_unidad = uni.id_unidad

            precio_venta_val = fila.get("precio_venta")
            aplica_iva_val = fila.get("aplica_impuesto")
            stock_minimo_val = fila.get("stock_minimo")

            if prod:
                # Solo se actualiza lo que venga lleno en la fila. El stock
                # NO se toca aqui, eso pasa solo via el detalle de compra.
                if fila.get("tipo"):
                    prod.tipo_producto = tipo
                    vendible = prod.tipo_producto == "final"
                if not vendible:
                    prod.id_categoria = None
                    prod.precio_venta = 0.0
                    prod.aplica_impuesto = False
                else:
                    if id_categoria:
                        prod.id_categoria = id_categoria
                    if precio_venta_val not in (None, ""):
                        prod.precio_venta = _num(precio_venta_val)
                    if aplica_iva_val not in (None, ""):
                        prod.aplica_impuesto = _si_no(aplica_iva_val)
                if id_marca:
                    prod.id_marca = id_marca
                if id_unidad:
                    prod.id_unidad = id_unidad
                if costo_unitario:
                    prod.precio_compra = costo_unitario
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
                    precio_compra=costo_unitario,
                    precio_venta=_num(precio_venta_val) if vendible else 0.0,
                    aplica_impuesto=vendible and _si_no(aplica_iva_val),
                    tipo_producto=tipo,
                    se_vende=vendible,
                    estado="activo",
                )
                db.session.add(prod)

            db.session.flush()  # asegura id_producto

            if stock_minimo_val not in (None, ""):
                inv = Inventario.query.filter_by(id_producto=prod.id_producto).first()
                if inv:
                    inv.stock_minimo = _num(stock_minimo_val)
                # si no existe inventario todavia, se crea en la Fase 2 al
                # sumar la cantidad comprada (con ese mismo stock_minimo).

            db.session.commit()

            filas_validas.append({
                "id_producto": prod.id_producto,
                "id_proveedor": proveedor.id_proveedor,
                "proveedor_nombre": proveedor.nombre,
                "cantidad": cantidad,
                "costo_unitario": costo_unitario,
                "es_nuevo": es_nuevo,
                "stock_minimo": _num(stock_minimo_val) if stock_minimo_val not in (None, "") else None,
            })

        except Exception as e:  # noqa: BLE001 - una fila mala no debe tumbar el resto
            db.session.rollback()
            errores.append(f"Fila {idx} ({fila.get('nombre', '?')}): {e}")

    if not filas_validas:
        return jsonify({"success": False, "message": "Ninguna fila se pudo procesar", "errores": errores}), 400

    # ---- Fase 2: una Compra por Proveedor, ahi se suma el stock ----
    grupos = {}
    for f in filas_validas:
        grupos.setdefault(f["id_proveedor"], {"proveedor_nombre": f["proveedor_nombre"], "filas": []})["filas"].append(f)

    compras_generadas = []
    productos_creados = 0
    productos_actualizados = 0

    for i, (id_proveedor, grupo) in enumerate(grupos.items(), start=1):
        try:
            num_compra = f"CM-{nicaragua_now().strftime('%Y%m%d%H%M%S')}-{i}"
            nueva_compra = Compra(
                id_empresa=current_user.id_empresa,
                id_sucursal=current_user.id_sucursal,
                id_usuario=current_user.id_usuario,
                id_proveedor=id_proveedor,
                numero_compra=num_compra,
                subtotal=0.0,
                impuesto=0.0,
                total=0.0,
                estado="completada",
                tipo_compra="productos",
            )
            db.session.add(nueva_compra)
            db.session.flush()

            subtotal_compra = 0.0
            for f in grupo["filas"]:
                subtotal_item = f["cantidad"] * f["costo_unitario"]
                subtotal_compra += subtotal_item

                detalle = DetalleCompra(
                    id_compra=nueva_compra.id_compra,
                    id_producto=f["id_producto"],
                    cantidad=f["cantidad"],
                    precio_unitario=f["costo_unitario"],
                    subtotal=subtotal_item,
                )
                db.session.add(detalle)

                inv = Inventario.query.filter_by(id_producto=f["id_producto"]).first()
                if inv:
                    inv.stock_actual = float(inv.stock_actual) + f["cantidad"]
                else:
                    inv = Inventario(
                        id_sucursal=current_user.id_sucursal,
                        id_producto=f["id_producto"],
                        stock_actual=f["cantidad"],
                        stock_minimo=f["stock_minimo"] or 0,
                    )
                    db.session.add(inv)

                if f["es_nuevo"]:
                    productos_creados += 1
                else:
                    productos_actualizados += 1

            nueva_compra.subtotal = subtotal_compra
            nueva_compra.total = subtotal_compra

            db.session.commit()
            compras_generadas.append({
                "proveedor": grupo["proveedor_nombre"],
                "numero_compra": num_compra,
                "lineas": len(grupo["filas"]),
                "total": subtotal_compra,
            })
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            errores.append(f"Compra a {grupo['proveedor_nombre']}: {e}")

    try:
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria(
            "IMPORTAR COMPRA MASIVA",
            "Compras",
            f"{len(compras_generadas)} compra(s) generadas, {productos_creados} productos nuevos, "
            f"{productos_actualizados} actualizados, {len(errores)} con error",
        )
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "success": True,
        "compras": compras_generadas,
        "productos_creados": productos_creados,
        "productos_actualizados": productos_actualizados,
        "errores": errores,
    })
