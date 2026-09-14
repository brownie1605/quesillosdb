"""Clientes: alta rapida (se usa tambien desde el selector del POS)."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text
from datetime import datetime

from app.extensions import db
from app.models import Cliente
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles, usuario_tiene_rol

cliente_bp = Blueprint("cliente", __name__, url_prefix="/clientes")


@cliente_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero", "Mesero")


@cliente_bp.route("/")
@login_required
def lista():
    return render_template("clientes/lista.html")


@cliente_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    return jsonify([c.to_dict() for c in clientes])


@cliente_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    try:
        tipo_cliente = data.get("tipo_cliente") or "externo"
        if tipo_cliente not in ("interno", "externo"):
            tipo_cliente = "externo"
        cliente = Cliente(
            id_empresa=current_user.id_empresa,
            nombre=nombre,
            cedula=data.get("cedula"),
            telefono=data.get("telefono"),
            direccion=data.get("direccion"),
            tipo_cliente=tipo_cliente,
            es_preferencial=bool(data.get("es_preferencial")),
            estado="activo",
        )
        db.session.add(cliente)
        db.session.commit()
        registrar_auditoria("CREAR CLIENTE", "Clientes", {"cliente": nombre})
        return jsonify({"success": True, "cliente": cliente.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@cliente_bp.route("/api/editar/<int:id_cliente>", methods=["POST"])
@login_required
def api_editar(id_cliente):
    cliente = Cliente.query.get_or_404(id_cliente)
    data = request.get_json(silent=True) or {}
    try:
        cliente.nombre = data.get("nombre", cliente.nombre)
        cliente.cedula = data.get("cedula", cliente.cedula)
        cliente.telefono = data.get("telefono", cliente.telefono)
        cliente.direccion = data.get("direccion", cliente.direccion)
        if data.get("tipo_cliente") in ("interno", "externo"):
            cliente.tipo_cliente = data.get("tipo_cliente")
        if "es_preferencial" in data:
            cliente.es_preferencial = bool(data.get("es_preferencial"))
        db.session.commit()
        registrar_auditoria("EDITAR CLIENTE", "Clientes", {"cliente": cliente.nombre})
        return jsonify({"success": True, "cliente": cliente.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@cliente_bp.route("/api/eliminar/<int:id_cliente>", methods=["DELETE", "POST"])
@login_required
def api_eliminar(id_cliente):
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    cliente = Cliente.query.get_or_404(id_cliente)
    try:
        cliente.estado = "inactivo"
        db.session.commit()
        registrar_auditoria("ELIMINAR CLIENTE", "Clientes", {"cliente": cliente.nombre})
        return jsonify({"success": True})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@cliente_bp.route("/api/platillos_por_cliente", methods=["GET"])
@login_required
def api_platillos_por_cliente():
    """Reportería: platillos consumidos por cliente en un rango de fechas."""
    try:
        inicio = request.args.get('inicio')
        fin = request.args.get('fin')

        if not inicio or not fin:
            return jsonify({"success": False, "message": "Fechas requeridas"}), 400

        # Query: clientes y sus platillos consumidos, con el descuento
        # aplicado a cada linea (dv.descuento) sumado por platillo, y el
        # subtotal bruto (antes de descuento) para poder calcular el %.
        query = text("""
            SELECT
                c.id_cliente,
                c.nombre as cliente_nombre,
                c.tipo_cliente,
                p.nombre as platillo_nombre,
                SUM(dv.cantidad) as cantidad,
                SUM(dv.descuento) as descuento_platillo,
                SUM(dv.subtotal) as subtotal_platillo
            FROM clientes c
            LEFT JOIN ventas v ON c.id_cliente = v.id_cliente AND v.id_empresa = :empresa AND v.estado = 'completada'
                AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin
            LEFT JOIN detalle_ventas dv ON v.id_venta = dv.id_venta
            LEFT JOIN productos p ON dv.id_producto = p.id_producto
            WHERE c.id_empresa = :empresa AND c.estado = 'activo'
            GROUP BY c.id_cliente, c.nombre, c.tipo_cliente, p.nombre
            ORDER BY c.nombre ASC, p.nombre ASC
        """)

        result = db.session.execute(query, {
            "empresa": current_user.id_empresa,
            "inicio": inicio,
            "fin": fin
        }).fetchall()

        # Descuento total a nivel de pedido (venta), aparte del de cada
        # linea -- un pedido puede llevar descuento general ademas del
        # de cada platillo, y aqui se suma sin duplicar por cada linea.
        query_descuento_pedido = text("""
            SELECT v.id_cliente, COALESCE(SUM(v.descuento), 0) as descuento_pedidos
            FROM ventas v
            WHERE v.id_empresa = :empresa AND v.estado = 'completada'
            AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin
            AND v.id_cliente IS NOT NULL
            GROUP BY v.id_cliente
        """)
        descuentos_pedido = {
            row[0]: float(row[1] or 0)
            for row in db.session.execute(query_descuento_pedido, {
                "empresa": current_user.id_empresa, "inicio": inicio, "fin": fin
            }).fetchall()
        }

        # Procesar y agrupar por cliente
        clientes_dict = {}
        for row in result:
            cliente_id = row[0]
            cliente_nombre = row[1]
            tipo_cliente = row[2]
            platillo_nombre = row[3]
            cantidad = row[4]
            descuento_platillo = row[5]
            subtotal_platillo = row[6]

            if cliente_id not in clientes_dict:
                clientes_dict[cliente_id] = {
                    "cliente_nombre": cliente_nombre,
                    "tipo_cliente": tipo_cliente,
                    "platillos": [],
                    "descuento_pedido": descuentos_pedido.get(cliente_id, 0.0),
                    "subtotal_bruto": 0.0,
                }

            if platillo_nombre:  # Solo agregar si hay platillo
                clientes_dict[cliente_id]["platillos"].append({
                    "nombre": platillo_nombre,
                    "cantidad": int(cantidad or 0),
                    "descuento": float(descuento_platillo or 0),
                })
                clientes_dict[cliente_id]["subtotal_bruto"] += float(subtotal_platillo or 0)

        # Descuento total (lineas + pedido) y su % sobre lo consumido,
        # calculado aqui para que el frontend no tenga que rehacer la
        # cuenta -- % = descuento_total / (subtotal_bruto + descuento_total).
        # subtotal_bruto ya es el subtotal DESPUES de aplicar el descuento
        # de linea (dv.subtotal = cantidad*precio - descuento), por eso se
        # sim vuelve a sumar el descuento para reconstruir el bruto real.
        for c in clientes_dict.values():
            descuento_lineas = sum(p["descuento"] for p in c["platillos"])
            descuento_total = descuento_lineas + c["descuento_pedido"]
            base = c["subtotal_bruto"] + descuento_lineas  # bruto antes de descuento de linea
            c["descuento_total"] = round(descuento_total, 2)
            c["descuento_pct"] = round((descuento_total / base * 100), 1) if base > 0 else 0.0
            del c["subtotal_bruto"]

        # Convertir a lista
        data = list(clientes_dict.values())

        return jsonify({
            "success": True,
            "data": data,
            "inicio": inicio,
            "fin": fin
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
