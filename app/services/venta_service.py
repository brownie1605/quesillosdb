"""Registro de ventas offline-first con descuento automatico de recetas.

Dos flujos de venta:
  - Directa (mostrador/barra): `registrar_venta()` cobra de una vez.
  - Por mesa (salon): `abrir_mesa()` crea una cuenta abierta (estado
    'pendiente') a la que se le van agregando productos con
    `agregar_items()`/`quitar_item()` mientras el cliente esta en la mesa,
    y se cierra con `cobrar_mesa()` cuando se paga.
"""
import uuid
import logging
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.venta import Venta
from app.models.detalle_venta import DetalleVenta
from app.models.producto import Producto
from app.services.receta_service import RecetaService
from app.services.inventario_service import InventarioService, StockInsuficiente
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("ventas")


class VentaError(Exception):
    pass


class VentaService:

    @staticmethod
    def numero_venta():
        return "V-" + nicaragua_now().strftime("%Y%m%d%H%M%S%f")[:20]

    # -----------------------------------------------------------------
    @staticmethod
    def _crear_detalle(venta, item, usuario, ahora):
        """Agrega una linea al carrito de `venta` y descuenta inventario.

        Devuelve el subtotal de esa linea. Usado tanto por la venta directa
        como por el flujo de mesas para no duplicar la logica.
        """
        id_producto = int(item["id_producto"])
        cantidad = Decimal(str(item["cantidad"]))
        if cantidad <= 0:
            # Sin este chequeo, una cantidad negativa produce una linea con
            # subtotal negativo (baja el total de la venta sin pasar por
            # anulacion) y ademas le devuelve stock al insumo en vez de
            # descontarlo (ver RecetaService.descontar_ingredientes, que
            # multiplica el requerimiento por esta misma cantidad).
            raise VentaError("La cantidad de cada producto debe ser mayor a cero")

        # El precio SIEMPRE se recalcula aqui, del producto en la BD -- nunca
        # se confia en el "precio" que manda el cliente. Si se usara el del
        # request, cualquiera con sesion de Mesero/Cajero podria editar el
        # payload (ej. con las herramientas del navegador) y cobrar
        # cualquier plato al precio que quisiera antes de enviar la venta.
        producto = Producto.query.get(id_producto)
        if not producto or producto.estado != "activo":
            raise VentaError(f"El producto (id {id_producto}) no existe o ya no esta activo")
        precio = Decimal(str(producto.precio_venta or 0))
        sub_item = (cantidad * precio).quantize(Decimal("0.01"))

        excluidos = item.get("excluidos") or []
        opciones = item.get("opciones") or []
        comentario = item.get("comentario") or RecetaService.comentario_de_personalizacion(
            id_producto, excluidos, opciones
        )
        # Incluye la nota libre del mesero; la columna es de 500.
        comentario = str(comentario).strip()[:500] if comentario else None

        det = DetalleVenta(
            id_venta=venta.id_venta,
            id_producto=id_producto,
            cantidad=cantidad,
            precio_unitario=precio,
            descuento=Decimal("0"),
            subtotal=sub_item,
            consumio_receta=bool(producto and producto.es_receta),
            personalizacion={"excluidos": excluidos, "opciones": opciones}
            if (excluidos or opciones) else None,
            comentario=comentario,
            timestamp_local_creacion=ahora,
            estado_sync="pendiente",
        )
        db.session.add(det)
        db.session.flush()

        RecetaService.descontar_ingredientes(
            id_producto, cantidad, usuario.id_usuario,
            referencia="VENTA-" + str(venta.id_venta),
            excluidos=excluidos, opciones=opciones,
        )
        return sub_item

    # -----------------------------------------------------------------
    @staticmethod
    def _recalcular_totales(venta):
        subtotal = sum((d.subtotal for d in venta.detalles), Decimal("0"))
        venta.subtotal = subtotal
        if venta.descuento_pct is not None:
            # Descuento en % de la mesa: sigue al subtotal al agregar/quitar.
            venta.descuento = (subtotal * Decimal(str(venta.descuento_pct)) / 100).quantize(Decimal("0.01"))
        venta.total = (
            subtotal - Decimal(str(venta.descuento or 0)) + Decimal(str(venta.propina or 0))
        ).quantize(Decimal("0.01"))
        venta.cambio = max(Decimal("0"), Decimal(str(venta.monto_recibido or 0)) - venta.total)

    # -----------------------------------------------------------------
    @staticmethod
    def _es_efectivo(metodo):
        return (metodo or "").strip().lower() == "efectivo"

    @staticmethod
    def _aplicar_pagos(venta, pagos):
        """Pago dividido: parte en un metodo y parte en otro (ej. transferencia
        + efectivo). `pagos` = [{"metodo": "Transferencia", "monto": 200}, ...].

        Con un solo pago (o ninguno) no cambia nada: manda `metodo_pago` como
        siempre. Con dos o mas, la venta queda con metodo_pago = "Mixto" y el
        desglose en `pagos_detalle`. Lo que no es efectivo no puede pasar del
        total (no se da vuelto de una tarjeta o transferencia); el efectivo si
        puede sobrar, y eso es el cambio.
        """
        validos = []
        for p in pagos or []:
            metodo = (p.get("metodo") or "").strip()
            try:
                monto = Decimal(str(p.get("monto") or 0)).quantize(Decimal("0.01"))
            except ArithmeticError:
                raise VentaError("Monto de pago invalido")
            if monto < 0:
                raise VentaError("Un pago no puede ser negativo")
            if metodo and monto > 0:
                validos.append({"metodo": metodo[:50], "monto": monto})
        if len(validos) < 2:
            venta.pagos_detalle = None
            return

        total = Decimal(str(venta.total or 0))
        pagado = sum((p["monto"] for p in validos), Decimal("0"))
        no_efectivo = sum(
            (p["monto"] for p in validos if not VentaService._es_efectivo(p["metodo"])), Decimal("0")
        )
        if pagado < total:
            raise VentaError("Los pagos (C$ %s) no cubren el total (C$ %s)" % (pagado, total))
        if no_efectivo > total:
            raise VentaError("Lo pagado con tarjeta o transferencia no puede pasar del total")

        venta.metodo_pago = "Mixto"
        venta.pagos_detalle = [{"metodo": p["metodo"], "monto": float(p["monto"])} for p in validos]
        venta.monto_recibido = pagado
        venta.cambio = pagado - total

    @staticmethod
    def efectivo_de(venta):
        """Cuanto efectivo deja esta venta en la caja (ya sin el cambio)."""
        if venta.pagos_detalle:
            no_efectivo = sum(
                (Decimal(str(p.get("monto") or 0)) for p in venta.pagos_detalle
                 if not VentaService._es_efectivo(p.get("metodo"))),
                Decimal("0"),
            )
            return Decimal(str(venta.total or 0)) - no_efectivo
        if VentaService._es_efectivo(venta.metodo_pago):
            return Decimal(str(venta.total or 0))
        return Decimal("0")

    # -----------------------------------------------------------------
    @staticmethod
    def _exigir_caja_abierta():
        """Sin turno de caja abierto no se puede completar ninguna venta."""
        from app.services.caja_service import CajaService, CajaError

        try:
            CajaService.exigir_abierta()
        except CajaError as e:
            raise VentaError(str(e))

    # -----------------------------------------------------------------
    @staticmethod
    def _push_si_hay_internet():
        from app.services.sync_service import SyncService
        from app.services.network_service import NetworkService

        if NetworkService.is_online():
            try:
                SyncService.push_pending_operations(limite=50)
            except Exception:  # noqa: BLE001
                log.warning("Push inmediato fallo; queda en cola", exc_info=True)

    # =================================================================
    # VENTA DIRECTA (mostrador / barra)
    # =================================================================
    @staticmethod
    def registrar_venta(usuario, cart, metodo_pago="Efectivo", descuento=0.0,
                        propina=0.0, id_cliente=None, monto_recibido=0.0, id_mesa=None,
                        notas=None, pagos=None):
        """Registra la venta en la BD LOCAL y la encola para la nube.

        cart: [{id_producto, cantidad, precio, excluidos?, opciones?}]
        `excluidos`: ids de ingredientes de la receta que el cliente pidio quitar.
        `opciones`: ids de RecetaOpcionItem elegidos (uno por grupo).
        Lanza StockInsuficiente si no alcanzan los insumos.
        """
        if not cart:
            raise ValueError("El carrito esta vacio")

        VentaService._exigir_caja_abierta()

        # 1. Consumo real de inventario (expande recetas a sus insumos).
        requerimientos = RecetaService.requerimiento_de_carrito(cart)
        InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        venta = Venta(
            id_empresa=usuario.id_empresa or current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=usuario.id_sucursal or current_app.config.get("ID_SUCURSAL", 1),
            id_usuario=usuario.id_usuario,
            id_cliente=id_cliente or None,
            id_mesa=id_mesa,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal(str(descuento or 0)),
            impuesto=Decimal("0"),
            propina=Decimal(str(propina or 0)),
            metodo_pago=metodo_pago,
            notas=(notas or "").strip() or None,
            estado="completada",
            total=Decimal("0"),
            subtotal=Decimal("0"),
            monto_recibido=Decimal(str(monto_recibido or 0)),
            fecha_venta=ahora,
            timestamp_local_creacion=ahora,
            timestamp_local_actualizacion=ahora,
            origen="local",
            estado_sync="pendiente",
        )
        db.session.add(venta)
        db.session.flush()

        for item in cart:
            VentaService._crear_detalle(venta, item, usuario, ahora)

        VentaService._recalcular_totales(venta)
        VentaService._aplicar_pagos(venta, pagos)

        # 3. Se encola solo (ver app/services/sync_events.py).
        db.session.commit()

        # 4. Si hay internet intenta subirla de inmediato (no bloquea la venta).
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def anular_venta(id_venta, usuario, motivo="Anulada por el usuario"):
        venta = Venta.query.get(id_venta)
        if not venta:
            raise ValueError("Venta no encontrada")
        if venta.estado == "anulada":
            return venta

        venta.estado = "anulada"
        venta.motivo_anulacion = motivo
        venta.estado_sync = "pendiente"
        venta.timestamp_local_actualizacion = nicaragua_now()

        InventarioService.revertir_venta(venta, motivo=motivo)

        if venta.id_mesa:
            VentaService._soltar_mesa(venta)

        db.session.commit()

        # Sin este push inmediato, la anulacion se queda "pendiente" hasta
        # el proximo ciclo de sincronizacion. Si en ese rato entra un PULL
        # (que sobrescribe sin comparar fechas -- ver sync_service),
        # jala la version vieja de la nube ("completada") y la venta
        # anulada vuelve a aparecer activa sola, sin que nadie lo note.
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def editar_datos_venta(id_venta, id_cliente=None, metodo_pago=None, notas=None):
        """Corrige datos NO financieros de una factura ya cobrada: a quien
        se le vendio, el metodo/banco de pago (ej. el cajero marco el banco
        equivocado) y la nota de la factura (ej. para dejar por escrito el
        motivo de un descuento). A proposito NO toca productos, cantidades
        ni totales
        -- esos alimentan los reportes de ganancias y el kardex, y una
        factura cerrada no deberia poder reescribirlos silenciosamente.
        Para corregir un monto real, la venta se anula y se rehace.

        Devuelve (venta, cambios) con `cambios` como lista de strings
        legibles para dejar en la auditoria.
        """
        from app.models.cliente import Cliente

        venta = Venta.query.get(id_venta)
        if not venta:
            raise VentaError("Venta no encontrada")
        if venta.estado != "completada":
            raise VentaError("Solo se pueden editar ventas completadas (no pendientes ni anuladas)")

        cambios = []

        if id_cliente is not None:
            nuevo_id = int(id_cliente) if id_cliente else None
            if nuevo_id != venta.id_cliente:
                nombre_anterior = "Público general"
                if venta.id_cliente:
                    c = Cliente.query.get(venta.id_cliente)
                    nombre_anterior = c.nombre if c else "Público general"

                nombre_nuevo = "Público general"
                if nuevo_id:
                    c = Cliente.query.get(nuevo_id)
                    if not c:
                        raise VentaError("El cliente seleccionado no existe")
                    nombre_nuevo = c.nombre

                venta.id_cliente = nuevo_id
                cambios.append(f"Cliente: {nombre_anterior} -> {nombre_nuevo}")

        if metodo_pago is not None:
            metodo_pago = metodo_pago.strip()
            if metodo_pago and metodo_pago != venta.metodo_pago:
                cambios.append(f"Método de pago: {venta.metodo_pago} -> {metodo_pago}")
                venta.metodo_pago = metodo_pago

        if notas is not None:
            notas_nuevas = notas.strip() or None
            if notas_nuevas != venta.notas:
                cambios.append("Nota de la factura actualizada")
                venta.notas = notas_nuevas

        if not cambios:
            return venta, cambios

        venta.estado_sync = "pendiente"
        venta.timestamp_local_actualizacion = nicaragua_now()
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta, cambios

    # =================================================================
    # FLUJO DE MESAS (cuenta abierta)
    # =================================================================
    @staticmethod
    def abrir_mesa(mesa, usuario, cart=None):
        """Abre una cuenta (venta 'pendiente') ligada a `mesa`."""
        cart = cart or []
        if mesa.estado == "ocupada" and mesa.id_venta_actual:
            raise VentaError("Esa mesa ya esta ocupada")

        if cart:
            requerimientos = RecetaService.requerimiento_de_carrito(cart)
            InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        venta = Venta(
            id_empresa=usuario.id_empresa or current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=usuario.id_sucursal or current_app.config.get("ID_SUCURSAL", 1),
            id_usuario=usuario.id_usuario,
            id_mesa=mesa.id_mesa,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal("0"),
            impuesto=Decimal("0"),
            propina=Decimal("0"),
            metodo_pago="Efectivo",
            estado="pendiente",
            total=Decimal("0"),
            subtotal=Decimal("0"),
            fecha_venta=ahora,
            timestamp_local_creacion=ahora,
            timestamp_local_actualizacion=ahora,
            origen="local",
            estado_sync="pendiente",
        )
        db.session.add(venta)
        db.session.flush()

        for item in cart:
            VentaService._crear_detalle(venta, item, usuario, ahora)
        VentaService._recalcular_totales(venta)

        mesa.estado = "ocupada"
        mesa.id_venta_actual = venta.id_venta
        mesa.estado_sync = "pendiente"

        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def agregar_items(venta, items, usuario):
        """Agrega productos a una cuenta abierta ya existente."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        if not items:
            return venta

        requerimientos = RecetaService.requerimiento_de_carrito(items)
        InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        for item in items:
            VentaService._crear_detalle(venta, item, usuario, ahora)

        VentaService._recalcular_totales(venta)
        venta.timestamp_local_actualizacion = ahora
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def quitar_item(venta, id_detalle, usuario):
        """Quita una linea de una cuenta abierta y revierte su inventario."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")

        det = DetalleVenta.query.get(id_detalle)
        if not det or det.id_venta != venta.id_venta:
            raise VentaError("Ese producto no esta en la cuenta")

        personalizacion = det.personalizacion or {}
        requerimientos = RecetaService.requerimiento_de_venta(
            det.id_producto, det.cantidad,
            excluidos=personalizacion.get("excluidos"),
            opciones=personalizacion.get("opciones"),
        )
        for pid, cant in requerimientos.items():
            InventarioService.mover(
                pid, cant, "ajuste", usuario.id_usuario,
                referencia="VENTA-" + str(venta.id_venta),
                observacion="Se quito de la cuenta antes de cobrar", commit=False,
            )

        # `venta.detalles.remove()` (no session.delete() directo) para que la
        # coleccion en memoria quede al dia de inmediato: _recalcular_totales
        # suma sobre `venta.detalles`, y el cascade delete-orphan se encarga
        # de borrar la fila.
        venta.detalles.remove(det)
        db.session.flush()

        VentaService._recalcular_totales(venta)
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def cobrar_mesa(venta, usuario, metodo_pago="Efectivo", descuento=0.0,
                    propina=0.0, monto_recibido=0.0, id_cliente=None, notas=None,
                    pagos=None):
        """Cierra la cuenta de una mesa: cobra y libera la mesa."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        if not venta.detalles:
            raise VentaError("La cuenta esta vacia")

        VentaService._exigir_caja_abierta()

        venta.descuento = Decimal(str(descuento or 0))
        venta.propina = Decimal(str(propina or 0))
        venta.metodo_pago = metodo_pago
        venta.monto_recibido = Decimal(str(monto_recibido or 0))
        venta.id_cliente = id_cliente or venta.id_cliente
        if notas is not None:
            venta.notas = (notas or "").strip() or None
        venta.estado = "completada"
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"

        VentaService._recalcular_totales(venta)
        VentaService._aplicar_pagos(venta, pagos)

        if venta.id_mesa:
            VentaService._soltar_mesa(venta)

        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def cuentas_de_mesa(mesa):
        """Cuentas abiertas de la mesa (Cuenta 1, Cuenta 2, ...) en orden."""
        cuentas = (Venta.query.filter_by(id_mesa=mesa.id_mesa, estado="pendiente")
                   .order_by(Venta.id_venta).all())
        if mesa.id_venta_actual and all(c.id_venta != mesa.id_venta_actual for c in cuentas):
            actual = Venta.query.get(mesa.id_venta_actual)
            if actual and actual.estado == "pendiente":
                cuentas.insert(0, actual)
        return cuentas

    # -----------------------------------------------------------------
    @staticmethod
    def _soltar_mesa(venta):
        """La cuenta `venta` ya se cobro o anulo. Si a la mesa le quedan otras
        cuentas abiertas (se separo), sigue ocupada con una de ellas; si no,
        queda libre como siempre."""
        from app.models.mesa import Mesa
        from app.services.mesa_service import MesaService

        otra = (Venta.query.filter(Venta.id_mesa == venta.id_mesa, Venta.estado == "pendiente",
                                   Venta.id_venta != venta.id_venta)
                .order_by(Venta.id_venta).first())
        if not otra:
            MesaService.liberar(venta.id_mesa)
            return
        mesa = Mesa.query.get(venta.id_mesa)
        if mesa and mesa.id_venta_actual in (None, venta.id_venta):
            mesa.estado = "ocupada"
            mesa.id_venta_actual = otra.id_venta
            mesa.estado_sync = "pendiente"

    # -----------------------------------------------------------------
    @staticmethod
    def separar_cuenta(venta, movimientos, usuario):
        """Pasa productos de la cuenta `venta` a una cuenta nueva de la misma
        mesa. `movimientos` = [{"id_detalle": 12, "cantidad": 2}, ...]; si la
        cantidad es menor a la de la linea, la linea se parte en dos.

        Lo que el producto desconto del inventario se pasa tambien a la
        cuenta nueva (sale de "VENTA-<vieja>" y entra a "VENTA-<nueva>"), asi
        anular o quitar despues devuelve justo lo de cada cuenta. El stock
        total no cambia."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")

        pedidos = {}
        for m in movimientos or []:
            try:
                id_det = int(m.get("id_detalle"))
                cant = Decimal(str(m.get("cantidad")))
            except (TypeError, ValueError, ArithmeticError):
                raise VentaError("Datos de separacion invalidos")
            if cant <= 0:
                raise VentaError("La cantidad a pasar debe ser mayor a cero")
            pedidos[id_det] = pedidos.get(id_det, Decimal("0")) + cant
        if not pedidos:
            raise VentaError("Elige al menos un producto para la otra cuenta")

        lineas = {d.id_detalle_venta: d for d in venta.detalles}
        for id_det, cant in pedidos.items():
            det = lineas.get(id_det)
            if not det:
                raise VentaError("Ese producto no esta en la cuenta")
            if cant > Decimal(str(det.cantidad)):
                raise VentaError(f"Solo hay {det.cantidad:g} de {det.producto.nombre if det.producto else 'ese producto'}")
        if sum(pedidos.values()) >= sum(Decimal(str(d.cantidad)) for d in venta.detalles):
            raise VentaError("Deja al menos un producto en la cuenta original")

        ahora = nicaragua_now()
        nueva = Venta(
            id_empresa=venta.id_empresa,
            id_sucursal=venta.id_sucursal,
            id_usuario=usuario.id_usuario,
            id_mesa=venta.id_mesa,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal("0"),
            impuesto=Decimal("0"),
            propina=Decimal("0"),
            metodo_pago="Efectivo",
            estado="pendiente",
            total=Decimal("0"),
            subtotal=Decimal("0"),
            fecha_venta=ahora,
            timestamp_local_creacion=ahora,
            timestamp_local_actualizacion=ahora,
            origen="local",
            estado_sync="pendiente",
        )
        db.session.add(nueva)
        db.session.flush()

        for id_det, cant in pedidos.items():
            det = lineas[id_det]
            if cant == Decimal(str(det.cantidad)):
                det.venta = nueva          # la linea entera cambia de cuenta
                det.estado_sync = "pendiente"
            else:
                det.cantidad = Decimal(str(det.cantidad)) - cant
                det.subtotal = (det.cantidad * Decimal(str(det.precio_unitario))).quantize(Decimal("0.01"))
                det.estado_sync = "pendiente"
                nueva.detalles.append(DetalleVenta(
                    id_producto=det.id_producto,
                    cantidad=cant,
                    precio_unitario=det.precio_unitario,
                    descuento=Decimal("0"),
                    subtotal=(cant * Decimal(str(det.precio_unitario))).quantize(Decimal("0.01")),
                    consumio_receta=det.consumio_receta,
                    personalizacion=det.personalizacion,
                    comentario=det.comentario,
                    timestamp_local_creacion=ahora,
                    estado_sync="pendiente",
                ))

            personalizacion = det.personalizacion or {}
            requerimientos = RecetaService.requerimiento_de_venta(
                det.id_producto, cant,
                excluidos=personalizacion.get("excluidos"),
                opciones=personalizacion.get("opciones"),
            )
            for pid, req in requerimientos.items():
                InventarioService.mover(
                    pid, req, "ajuste", usuario.id_usuario,
                    referencia="VENTA-" + str(venta.id_venta),
                    observacion="Se paso a otra cuenta de la mesa", commit=False,
                )
                InventarioService.mover(
                    pid, -req, "venta", usuario.id_usuario,
                    referencia="VENTA-" + str(nueva.id_venta),
                    observacion="Viene de otra cuenta de la mesa", commit=False,
                )
        db.session.flush()

        VentaService._recalcular_totales(venta)
        VentaService._recalcular_totales(nueva)
        venta.timestamp_local_actualizacion = ahora
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return nueva

    # -----------------------------------------------------------------
    @staticmethod
    def fijar_descuento(venta, porcentaje):
        """Descuento en % de una cuenta abierta (0 = sin descuento)."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        try:
            pct = Decimal(str(porcentaje or 0))
        except ArithmeticError:
            raise VentaError("Porcentaje invalido")
        if pct < 0 or pct > 100:
            raise VentaError("El descuento debe estar entre 0 y 100 %")
        venta.descuento_pct = pct if pct > 0 else None
        if venta.descuento_pct is None:
            venta.descuento = Decimal("0")
        VentaService._recalcular_totales(venta)
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def fijar_cliente(venta, id_cliente):
        """Cliente de una cuenta abierta (None = Publico general)."""
        from app.models.cliente import Cliente

        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        if id_cliente:
            cliente = Cliente.query.get(int(id_cliente))
            if not cliente or cliente.estado != "activo":
                raise VentaError("Ese cliente no existe o no esta activo")
            venta.id_cliente = cliente.id_cliente
        else:
            venta.id_cliente = None
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta
