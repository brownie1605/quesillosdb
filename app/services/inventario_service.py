"""Control de existencias con registro de movimientos y encolado de sync."""
import logging
from decimal import Decimal

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.models.inventario import Inventario
from app.models.movimiento_inventario import MovimientoInventario
from app.models.producto import Producto
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("inventario")


class StockInsuficiente(Exception):
    def __init__(self, faltantes):
        self.faltantes = faltantes
        detalle = ", ".join(
            f"{f['producto']} (requiere {f['requerido']}, hay {f['disponible']})"
            for f in faltantes
        )
        super().__init__("Stock insuficiente: " + detalle)


class InventarioService:

    # -----------------------------------------------------------------
    @staticmethod
    def obtener_o_crear(id_producto):
        inv = Inventario.query.filter_by(id_producto=id_producto).first()
        if not inv:
            inv = Inventario(
                id_producto=id_producto,
                id_sucursal=current_app.config.get("ID_SUCURSAL", 1),
                stock_actual=0,
                stock_minimo=0,
                stock_maximo=0,
            )
            db.session.add(inv)
            db.session.flush()
        return inv

    # -----------------------------------------------------------------
    @staticmethod
    def stock_de(id_producto):
        inv = Inventario.query.filter_by(id_producto=id_producto).first()
        return Decimal(str(inv.stock_actual)) if inv and inv.stock_actual is not None else Decimal("0")

    # -----------------------------------------------------------------
    @staticmethod
    def verificar_disponibilidad(requerimientos):
        """requerimientos: dict {id_producto: cantidad}. Lanza StockInsuficiente.

        OJO: esto es una verificacion rapida "de cortesia" para poder avisar
        al cajero ANTES de intentar cobrar (ej. "falta queso"), pero NO es el
        punto que de verdad garantiza que no se venda mas de lo que hay --
        entre este chequeo y el descuento real puede pasar otra venta
        concurrente. La garantia real esta en el UPDATE atomico de
        `mover()` (ver auditoria H-02): esta funcion puede decir "si hay
        stock" y aun asi `mover()` fallar un instante despues si alguien
        mas se adelanto, y eso es correcto -- gana quien de verdad llega
        primero a la base de datos, no quien vio el numero mas alto en pantalla.
        """
        faltantes = []
        for id_producto, cantidad in requerimientos.items():
            disponible = InventarioService.stock_de(id_producto)
            if disponible < Decimal(str(cantidad)):
                producto = Producto.query.get(id_producto)
                faltantes.append(
                    {
                        "id_producto": id_producto,
                        "producto": producto.nombre if producto else str(id_producto),
                        "requerido": float(cantidad),
                        "disponible": float(disponible),
                    }
                )
        if faltantes:
            raise StockInsuficiente(faltantes)
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def mover(id_producto, cantidad, tipo_movimiento, usuario_id,
              referencia=None, observacion=None, encolar=True, commit=False):
        """Aplica un movimiento de stock. `cantidad` positiva = entrada.

        El encolado para la nube lo hace solo `sync_events`; aqui no hace
        falta llamarlo.

        Auditoria H-02 (race condition): antes esto leia `stock_actual`,
        calculaba el nuevo valor en Python y lo fijaba de vuelta -- entre
        esa lectura y esa escritura, otra venta concurrente del mismo
        producto podia colarse y el resultado final quedaba mal (incluso
        pudiendo dejar stock negativo con dos ventas simultaneas del
        ultimo producto). Ahora el descuento/aumento es un solo UPDATE
        atomico (`stock_actual = stock_actual + :delta ... AND
        stock_actual + :delta >= 0`): MySQL/InnoDB toma el lock de fila de
        ese UPDATE, asi que una segunda transaccion concurrente sobre el
        mismo producto queda bloqueada hasta que la primera termina, y
        cuando le toca su turno vuelve a evaluar la condicion contra el
        valor YA actualizado -- nunca puede dejar el stock en negativo.
        """
        inv = InventarioService.obtener_o_crear(id_producto)
        delta = Decimal(str(cantidad))
        ahora = nicaragua_now()

        resultado = db.session.execute(
            text(
                """UPDATE inventario
                   SET stock_actual = stock_actual + :delta,
                       fecha_actualizacion = :ahora,
                       estado_sync = 'pendiente'
                   WHERE id_producto = :id_producto
                     AND (stock_actual + :delta) >= 0"""
            ),
            # float, no Decimal: pymysql acepta Decimal en un bind param,
            # pero el driver sqlite3 (el que usa la suite de tests) no --
            # "Error binding parameter: type 'decimal.Decimal' is not
            # supported". El valor real que queda guardado en la columna
            # DECIMAL de la BD no pierde precision por esto: la aritmetica
            # (stock_actual + :delta) la hace el motor de la base de datos
            # sobre su propio tipo de columna, no Python.
            {"delta": float(delta), "ahora": ahora, "id_producto": id_producto},
        )

        if resultado.rowcount == 0:
            # No alcanzaba -- ni el nuestro ni ningun movimiento concurrente
            # gano nada aqui, la fila no se toco.
            disponible = InventarioService.stock_de(id_producto)
            producto = Producto.query.get(id_producto)
            raise StockInsuficiente([{
                "id_producto": id_producto,
                "producto": producto.nombre if producto else str(id_producto),
                "requerido": float(-delta) if delta < 0 else float(delta),
                "disponible": float(disponible),
            }])

        # El UPDATE crudo de arriba no pasa por el ORM, asi que el objeto
        # `inv` que ya esta en la sesion se habria quedado con el valor
        # viejo en memoria -- hay que refrescarlo desde la BD para dejar
        # tanto `inv` como el resto de este metodo con el dato real.
        db.session.refresh(inv)
        nuevo = Decimal(str(inv.stock_actual))
        anterior = nuevo - delta

        # `sync_events.py` encola automaticamente cualquier cambio hecho a
        # traves del ORM (INSERT/UPDATE/DELETE) al hacer flush -- pero un
        # UPDATE crudo como el de arriba es invisible para ese listener (a
        # proposito: es el mismo truco que usa el pull para no re-encolar
        # lo que ya vino de la nube). Sin este encolado manual, el cambio
        # de `stock_actual` de esta venta nunca llegaria a la nube.
        from app.services.sync_service import SyncService

        SyncService.encolar(
            "inventario", inv.id_inventario, "UPDATE",
            payload={
                "id_inventario": inv.id_inventario,
                "id_producto": inv.id_producto,
                "id_sucursal": inv.id_sucursal,
                "stock_actual": float(nuevo),
                "stock_minimo": float(inv.stock_minimo or 0),
                "stock_maximo": float(inv.stock_maximo or 0),
                "fecha_actualizacion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            },
            usuario_id=usuario_id, timestamp=ahora, commit=False,
        )

        mov = MovimientoInventario(
            id_empresa=current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=current_app.config.get("ID_SUCURSAL", 1),
            id_producto=id_producto,
            id_usuario=usuario_id,
            tipo_movimiento=tipo_movimiento,
            cantidad=abs(delta),
            stock_anterior=anterior,
            stock_nuevo=nuevo,
            referencia=referencia,
            observacion=observacion,
            fecha_movimiento=nicaragua_now(),
            timestamp_operacion=nicaragua_now(),
        )
        db.session.add(mov)
        db.session.flush()

        if commit:
            db.session.commit()
        return mov

    # -----------------------------------------------------------------
    @staticmethod
    def registrar_compra(id_producto, cantidad, costo_unitario, usuario_id,
                          referencia=None, observacion=None, commit=False):
        """Punto unico de "se compro algo": suma el stock dejando un
        movimiento auditado (tipo 'compra') y actualiza `precio_compra` al
        ultimo costo pagado -- los precios cambian cuando se compra, es el
        mismo criterio que en el alta normal de producto. Usado por
        Compras (alta, edicion e importacion masiva) para no reimplementar
        esta logica en cada endpoint.
        """
        mov = InventarioService.mover(
            id_producto, cantidad, "compra", usuario_id,
            referencia=referencia, observacion=observacion, commit=False,
        )
        if costo_unitario:
            producto = Producto.query.get(id_producto)
            if producto:
                producto.precio_compra = costo_unitario
        if commit:
            db.session.commit()
        return mov

    # -----------------------------------------------------------------
    @staticmethod
    def ajustar_absoluto(id_producto, nuevo_stock, usuario_id, motivo, commit=False):
        """Ajuste manual de inventario (ej. conteo fisico, rotura, merma).

        A diferencia de sobreescribir `stock_actual` a lo bruto, esto calcula
        el delta real y lo deja auditado como movimiento tipo 'ajuste' con un
        motivo obligatorio -- para poder responder despues "por que cambio
        este numero" en vez de perder el dato de por que se corrigio.
        """
        actual = InventarioService.stock_de(id_producto)
        delta = Decimal(str(nuevo_stock)) - actual
        if delta == 0:
            return None
        return InventarioService.mover(
            id_producto, delta, "ajuste", usuario_id,
            observacion=motivo, commit=commit,
        )

    # -----------------------------------------------------------------
    @staticmethod
    def revertir_venta(venta, motivo="Reversion de venta"):
        """Devuelve al stock todo lo que la venta habia descontado.

        Se devuelve exactamente lo que la venta registro en sus movimientos
        (referencia "VENTA-<id>"): la opcion elegida (Fajitas bowl de res
        devuelve fajitas de res), sin los ingredientes que se quitaron, y
        con las cantidades de la receta que habia al venderla. Lo que ya se
        devolvio antes (quitar un plato de la cuenta, otra anulacion) se
        descuenta del neto, asi que nunca se devuelve dos veces.

        Antes se recalculaba con la receta ACTUAL y sin la personalizacion:
        una receta de solo opciones no devolvia nada y un Desayuno tipico
        no devolvia la opcion elegida.
        """
        from app.services.receta_service import RecetaService

        referencia = "VENTA-" + str(venta.id_venta)
        movimientos = MovimientoInventario.query.filter_by(referencia=referencia).all()
        if movimientos:
            neto = {}
            for m in movimientos:
                delta = Decimal(str(m.stock_nuevo)) - Decimal(str(m.stock_anterior))
                neto[m.id_producto] = neto.get(m.id_producto, Decimal("0")) + delta
            for id_producto, total in neto.items():
                if total < 0:
                    InventarioService.mover(
                        id_producto,
                        -total,  # positivo = entrada
                        "devolucion",
                        venta.id_usuario,
                        referencia=referencia,
                        observacion=motivo,
                        commit=False,
                    )
            db.session.commit()
            return

        # Venta sin movimientos registrados (anterior a que existieran):
        # se calcula con la receta, como antes.
        for det in venta.detalles:
            requerimientos = RecetaService.requerimiento_de_venta(det.id_producto, det.cantidad)
            for id_producto, cantidad in requerimientos.items():
                InventarioService.mover(
                    id_producto,
                    cantidad,  # positivo = entrada
                    "devolucion",
                    venta.id_usuario,
                    referencia="VENTA-" + str(venta.id_venta),
                    observacion=motivo,
                    commit=False,
                )
        db.session.commit()

    # -----------------------------------------------------------------
    MOTIVOS_BAJA = ("Merma", "Vencido", "Dañado", "Consumo interno", "Otro")
    REFERENCIA_BAJA = "BAJA"

    @staticmethod
    def registrar_baja(id_producto, cantidad, motivo, usuario_id, detalle=None):
        """Baja de inventario (merma, vencido, danado...): resta stock con un
        movimiento 'ajuste' marcado como BAJA, para poder listarlas aparte."""
        cantidad = Decimal(str(cantidad or 0))
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a cero")
        motivo = motivo if motivo in InventarioService.MOTIVOS_BAJA else "Otro"
        texto = "Baja: " + motivo + (" - " + detalle.strip()[:200] if detalle and detalle.strip() else "")
        mov = InventarioService.mover(
            id_producto, -cantidad, "ajuste", usuario_id,
            referencia=InventarioService.REFERENCIA_BAJA, observacion=texto, commit=False,
        )
        db.session.commit()
        return mov

    @staticmethod
    def bajas(desde, hasta):
        """Bajas registradas entre dos fechas (inclusive), la mas reciente primero."""
        from datetime import datetime, timedelta

        inicio = datetime.combine(desde, datetime.min.time())
        fin = datetime.combine(hasta, datetime.min.time()) + timedelta(days=1)
        movs = (
            MovimientoInventario.query
            .filter(MovimientoInventario.referencia == InventarioService.REFERENCIA_BAJA)
            .filter(MovimientoInventario.fecha_movimiento >= inicio)
            .filter(MovimientoInventario.fecha_movimiento < fin)
            .order_by(MovimientoInventario.fecha_movimiento.desc())
            .all()
        )
        productos = {
            p.id_producto: p for p in
            Producto.query.filter(Producto.id_producto.in_({m.id_producto for m in movs} or {0})).all()
        }
        filas = []
        for m in movs:
            p = productos.get(m.id_producto)
            cantidad = Decimal(str(m.stock_anterior)) - Decimal(str(m.stock_nuevo))
            costo = Decimal(str((p.precio_compra if p else 0) or 0))
            filas.append({
                "id_movimiento": m.id_movimiento,
                "fecha": m.fecha_movimiento.strftime("%Y-%m-%d %H:%M") if m.fecha_movimiento else "",
                "id_producto": m.id_producto,
                "producto": p.nombre if p else str(m.id_producto),
                "cantidad": float(cantidad),
                "motivo": (m.observacion or "").replace("Baja: ", "", 1),
                "costo": float((cantidad * costo).quantize(Decimal("0.01"))),
                "id_usuario": m.id_usuario,
            })
        return filas

    @staticmethod
    def consumo(desde, hasta, agrupar="dia"):
        """Cuanto se uso de cada producto por dia o por mes al vender.

        Sale de los movimientos de las ventas (referencia VENTA-<id>): lo
        que se desconto (venta directa o insumos de la receta) menos lo que
        se devolvio al anular o al quitar un plato de la cuenta. Asi
        "Toalla quesillo" cuenta lo que de verdad salio en platos.
        """
        from datetime import datetime, timedelta

        inicio = datetime.combine(desde, datetime.min.time())
        fin = datetime.combine(hasta, datetime.min.time()) + timedelta(days=1)
        movs = (
            MovimientoInventario.query
            .filter(MovimientoInventario.referencia.like("VENTA-%"))
            .filter(MovimientoInventario.fecha_movimiento >= inicio)
            .filter(MovimientoInventario.fecha_movimiento < fin)
            .all()
        )
        formato = "%Y-%m" if agrupar == "mes" else "%Y-%m-%d"
        por_periodo, total = {}, {}
        for m in movs:
            usado = Decimal(str(m.stock_anterior)) - Decimal(str(m.stock_nuevo))
            periodo = m.fecha_movimiento.strftime(formato)
            clave = (periodo, m.id_producto)
            por_periodo[clave] = por_periodo.get(clave, Decimal("0")) + usado
            total[m.id_producto] = total.get(m.id_producto, Decimal("0")) + usado

        productos = {
            p.id_producto: p for p in
            Producto.query.filter(Producto.id_producto.in_(set(total) or {0})).all()
        }
        from app.models import UnidadMedida
        unidades = {u.id_unidad: u.abreviatura for u in UnidadMedida.query.all()}

        def info(pid):
            p = productos.get(pid)
            return {
                "id_producto": pid,
                "producto": p.nombre if p else str(pid),
                "tipo_producto": p.tipo_producto if p else "",
                "unidad": unidades.get(p.id_unidad, "") if p else "",
            }

        detalle = [
            dict(info(pid), periodo=periodo, cantidad=float(cant))
            for (periodo, pid), cant in por_periodo.items() if cant > 0
        ]
        detalle.sort(key=lambda d: (d["periodo"], -d["cantidad"]), reverse=False)
        resumen = [dict(info(pid), cantidad=float(cant)) for pid, cant in total.items() if cant > 0]
        resumen.sort(key=lambda d: -d["cantidad"])
        return {"agrupar": "mes" if agrupar == "mes" else "dia", "resumen": resumen, "detalle": detalle}

    # -----------------------------------------------------------------
    @staticmethod
    def productos_bajo_minimo():
        return (
            db.session.query(Inventario, Producto)
            .join(Producto, Producto.id_producto == Inventario.id_producto)
            .filter(Inventario.stock_actual <= Inventario.stock_minimo)
            .filter(Producto.estado == "activo")
            .all()
        )
