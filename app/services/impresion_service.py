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
from app.models.producto import Producto
from app.utils.date_utils import nicaragua_now

ETIQUETAS = {"quesillo": "🧀 QUESILLO", "cocina": "🍳 COCINA", "bebidas": "🥤 BEBIDAS"}


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
