"""Caja: apertura/cierre de turno y movimientos de efectivo (gastos/ingresos)."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.services.caja_service import CajaService, CajaError
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles

caja_bp = Blueprint("caja", __name__, url_prefix="/caja")


@caja_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero")


@caja_bp.route("/")
@login_required
def index():
    return render_template("caja/index.html")


@caja_bp.route("/api/estado", methods=["GET"])
@login_required
def api_estado():
    apertura = CajaService.apertura_actual()
    if not apertura:
        return jsonify({"abierta": False})
    resumen = CajaService.resumen_turno(apertura)
    return jsonify({
        "abierta": True,
        "id_apertura": apertura.id_apertura,
        "monto_inicial": float(apertura.monto_inicial),
        "fecha_apertura": apertura.fecha_apertura.strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": apertura.usuario.nombre_completo if apertura.usuario else None,
        "total_ventas": float(resumen["total_ventas"]),
        "cantidad_ventas": resumen["cantidad_ventas"],
        "monto_esperado": float(resumen["monto_esperado"]),
        # Desglose del cuadre: inicial + ventas en efectivo - gastos = esperado.
        "efectivo_en_ventas": float(resumen["efectivo_en_ventas"]),
        "ventas_otros_metodos": float(resumen["ventas_otros_metodos"]),
        "otros_ingresos": float(resumen["total_ingresos"]),
        "otros_egresos": float(resumen["total_egresos"]),
        "total_gastos": float(resumen["total_gastos"]),
        "gastos": [
            {
                "hora": c.fecha_compra.strftime("%H:%M") if c.fecha_compra else "",
                "descripcion": c.descripcion_gasto or ("Compra " + (c.numero_compra or "")),
                "tipo": "Gasto" if c.tipo_compra == "varios" else "Compra",
                "monto": float(c.total or 0),
            }
            for c in resumen["gastos"]
        ],
    })


@caja_bp.route("/api/abrir", methods=["POST"])
@login_required
def api_abrir():
    data = request.get_json(silent=True) or {}
    try:
        apertura = CajaService.abrir_turno(current_user, data.get("monto_inicial", 0))
        registrar_auditoria("ABRIR CAJA", "Caja", {"monto_inicial": float(apertura.monto_inicial)})
        return jsonify({"success": True, "id_apertura": apertura.id_apertura})
    except CajaError as e:
        return jsonify({"success": False, "message": str(e)}), 400


@caja_bp.route("/api/cerrar", methods=["POST"])
@login_required
def api_cerrar():
    data = request.get_json(silent=True) or {}
    try:
        cierre = CajaService.cerrar_turno(
            current_user,
            data.get("monto_real", 0),
            data.get("observacion"),
            detalle_conteo=data.get("detalle_conteo"),
            tipo_cambio=data.get("tipo_cambio"),
        )
        registrar_auditoria(
            "CERRAR CAJA", "Caja",
            {"monto_real": float(cierre.monto_real), "diferencia": float(cierre.diferencia)},
        )
        return jsonify({
            "success": True,
            "diferencia": float(cierre.diferencia),
            "monto_esperado": float(cierre.monto_esperado),
            "monto_real": float(cierre.monto_real),
        })
    except CajaError as e:
        return jsonify({"success": False, "message": str(e)}), 400
