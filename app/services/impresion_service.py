"""Comandas por impresora (Quesillo / Cocina / Bebidas).

El servidor NUNCA habla directo con una impresora fisica: si el sistema
vive en la nube (Railway) y las impresoras estan en la red del local, no
hay forma de que se "vean" entre si. Lo que este servicio hace es agrupar
los productos de un pedido por la impresora que les corresponde y avisar
por Socket.IO -- el que de verdad manda el ticket a la impresora es el
agente local (ver `print_agent/`), que corre en una PC/tablet dentro del
local y si tiene acceso de red a las impresoras.

Una vez se compren las impresoras, lo unico que falta configurar es su
IP en `print_agent/agente.py` -- todo lo demas (que producto va a cual
impresora, el armado del ticket, el aviso en tiempo real) ya esta listo.
"""
from decimal import Decimal

from app.models.producto import Producto
from app.utils.date_utils import nicaragua_now

ETIQUETAS = {"quesillo": "🧀 QUESILLO", "cocina": "🍳 COCINA", "bebidas": "🥤 BEBIDAS"}

# Los agentes de impresion conectados (por id de sesion de Socket.IO) y la
# sala a la que se unen: los tickets de caja (precuenta/factura) solo viajan
# a esa sala, no a cualquier navegador conectado.
SALA_AGENTES = "impresion"
AGENTES = set()
NOMBRE_NEGOCIO = "QUESILLOS LO NUESTRO"


class ImpresionService:

    @staticmethod
    def agrupar_por_impresora(items):
        """`items`: lista de dicts del carrito ({id_producto, cantidad,
        comentario, ...}) tal como los manda el mesero. Devuelve
        {categoria: [{nombre, cantidad, comentario}]} -- solo las
        categorias que de verdad tienen productos en este pedido."""
        ids = [it.get("id_producto") for it in items if it.get("id_producto")]
        if not ids:
            return {}
        productos = {
            p.id_producto: p
            for p in Producto.query.filter(Producto.id_producto.in_(ids)).all()
        }

        grupos = {}
        for it in items:
            prod = productos.get(it.get("id_producto"))
            categoria = prod.impresora if prod else None
            if not categoria:
                continue  # sin impresora asignada: no imprime en ningun lado
            grupos.setdefault(categoria, []).append({
                "nombre": prod.nombre,
                "cantidad": it.get("cantidad", 1),
                "comentario": it.get("comentario"),
            })
        return grupos

    @staticmethod
    def emitir_comandas(mesa_nombre, items, mesero=None):
        """Agrupa `items` por impresora y emite un evento Socket.IO
        `comanda_impresion` por cada grupo no vacio. El agente local
        filtra por el campo `impresora` y solo imprime lo que le toca."""
        from app.extensions import socketio

        grupos = ImpresionService.agrupar_por_impresora(items)
        if not grupos:
            return grupos

        hora = nicaragua_now().strftime("%d/%m/%Y %H:%M")
        for categoria, productos_grupo in grupos.items():
            payload = {
                "impresora": categoria,
                "etiqueta": ETIQUETAS.get(categoria, categoria.upper()),
                "mesa": mesa_nombre,
                "mesero": mesero,
                "hora": hora,
                "items": productos_grupo,
            }
            try:
                socketio.emit("comanda_impresion", payload)
            except Exception:  # noqa: BLE001
                pass  # sin agente conectado todavia, o sin socketio en tests: no bloquea el pedido
        return grupos

    # -----------------------------------------------------------------
    @staticmethod
    def agentes_conectados():
        return len(AGENTES)

    # -----------------------------------------------------------------
    @staticmethod
    def armar_ticket_caja(tipo, venta, numero_cuenta=1, total_cuentas=1):
        """Datos del ticket de caja. `tipo`: 'precuenta' (cuenta abierta, no
        cobra nada) o 'factura' (venta ya cobrada, el ticket completo)."""
        from app.models.mesa import Mesa

        mesa = Mesa.query.get(venta.id_mesa) if venta.id_mesa else None
        dos = Decimal("0.01")
        subtotal = Decimal(str(venta.subtotal or 0))
        descuento = Decimal(str(venta.descuento or 0))
        base = max(subtotal - descuento, Decimal("0")).quantize(dos)
        items = [
            {
                "cantidad": "%g" % float(d.cantidad or 0),
                "nombre": d.producto.nombre if d.producto else "Producto",
                "precio_unitario": float(d.precio_unitario or 0),
                "subtotal": float(d.subtotal or 0),
                "comentario": d.comentario,
            }
            for d in venta.detalles
        ]
        payload = {
            "impresora": "caja",
            "tipo": tipo,
            "empresa": NOMBRE_NEGOCIO,
            "titulo": "PRECUENTA" if tipo == "precuenta" else "FACTURA DE VENTA",
            "numero": venta.numero_venta if tipo == "factura" else None,
            "mesa": mesa.nombre if mesa else None,
            "cuenta": f"Cuenta {numero_cuenta} de {total_cuentas}" if total_cuentas > 1 else None,
            "fecha": (venta.fecha_venta if tipo == "factura" and venta.fecha_venta else nicaragua_now()).strftime("%Y-%m-%d %H:%M"),
            "atendio": venta.usuario.nombre_completo if venta.usuario else None,
            "cliente": venta.cliente.nombre if venta.cliente else None,
            "items": items,
            "subtotal": float(subtotal),
            "descuento": float(descuento),
            "descuento_pct": float(venta.descuento_pct) if venta.descuento_pct is not None else None,
        }
        if tipo == "precuenta":
            propina = (base * Decimal("0.10")).quantize(dos)
            payload.update(total=float(base), propina_sugerida=float(propina),
                           total_con_propina=float(base + propina))
        else:
            payload.update(propina=float(venta.propina or 0), total=float(venta.total or 0),
                           metodo_pago=venta.metodo_pago, pagos=venta.pagos_detalle, notas=venta.notas)
        return payload

    # -----------------------------------------------------------------
    @staticmethod
    def emitir_ticket_caja(payload):
        """Manda el ticket al agente de impresion. Devuelve False si no hay
        ningun agente conectado (el llamador decide que hacer: la pantalla
        vuelve a imprimir con el navegador)."""
        from app.extensions import socketio

        if not AGENTES:
            return False
        try:
            socketio.emit("ticket_caja", payload, to=SALA_AGENTES)
        except Exception:  # noqa: BLE001
            return False
        return True
