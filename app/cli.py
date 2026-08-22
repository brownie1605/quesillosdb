"""Comandos de consola: `flask init-local`, `flask seed`, `flask sync-now`, ..."""
import click
from flask.cli import with_appcontext

from app.extensions import db
from app.utils.date_utils import nicaragua_now

ROLES = [
    ("Admin", "Acceso total al sistema"),
    ("Cajero", "Ventas, cobros y manejo de caja"),
    ("Mesero", "Toma de órdenes y ventas"),
    ("Cocinero", "Recetas, insumos y órdenes de cocina"),
]

UNIDADES = [
    ("Unidad", "und"),
    ("Docena", "doc"),
    ("Libra", "lb"),
    ("Onza", "oz"),
    ("Gramo", "g"),
    ("Kilogramo", "kg"),
    ("Litro", "L"),
    ("Mililitro", "ml"),
    ("Porción", "porc"),
]


def registrar_comandos(app):
    app.cli.add_command(init_local)
    app.cli.add_command(seed)
    app.cli.add_command(crear_admin)
    app.cli.add_command(sync_now)
    app.cli.add_command(sync_status)
    app.cli.add_command(demo_quesillo)


# ==================================================================
@click.command("init-local")
@with_appcontext
def init_local():
    """Crea todas las tablas en la BD local a partir de los modelos."""
    db.create_all()
    click.echo("Tablas creadas en la base de datos local.")


# ==================================================================
@click.command("seed")
@with_appcontext
def seed():
    """Inserta empresa, sucursal, roles y unidades de medida basicas."""
    from app.models import Empresa, Sucursal, Rol, UnidadMedida, Categoria

    if not db.session.get(Empresa, 1):
        db.session.add(
            Empresa(
                id_empresa=1,
                nombre="Quesillos Lo Nuestro",
                telefono="",
                correo="quesilloslonuestro26@gmail.com",
                estado="activo",
                fecha_creacion=nicaragua_now(),
            )
        )
        db.session.flush()
        click.echo("Empresa creada.")

    if not db.session.get(Sucursal, 1):
        db.session.add(
            Sucursal(
                id_sucursal=1,
                id_empresa=1,
                nombre="Sucursal Principal",
                estado="activo",
                fecha_creacion=nicaragua_now(),
            )
        )
        db.session.flush()
        click.echo("Sucursal creada.")

    for nombre, desc in ROLES:
        if not Rol.query.filter_by(nombre=nombre).first():
            db.session.add(
                Rol(
                    id_empresa=1,
                    nombre=nombre,
                    descripcion=desc,
                    estado="activo",
                    fecha_creacion=nicaragua_now(),
                )
            )
    db.session.flush()

    for nombre, abrev in UNIDADES:
        if not UnidadMedida.query.filter_by(abreviatura=abrev).first():
            db.session.add(UnidadMedida(nombre=nombre, abreviatura=abrev, estado="activo"))

    for nombre in ("General", "Bebidas", "Comidas", "Insumos"):
        if not Categoria.query.filter_by(nombre=nombre).first():
            db.session.add(Categoria(id_empresa=1, nombre=nombre, estado="activo"))

    db.session.commit()
    click.echo("Roles, unidades y categorías listos.")


# ==================================================================
@click.command("crear-admin")
@click.option("--usuario", default="admin")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--correo", default="quesilloslonuestro26@gmail.com")
@click.option("--nombre", default="Administrador")
@with_appcontext
def crear_admin(usuario, password, correo, nombre):
    """Crea (o actualiza) el usuario administrador."""
    from app.models import Usuario, Rol
    from app.services.auth_service import generar_password

    rol = Rol.query.filter_by(nombre="Admin").first()
    if not rol:
        click.echo("Ejecuta primero: flask seed")
        return

    u = Usuario.query.filter_by(usuario=usuario).first()
    if u:
        u.password_hash = generar_password(password)
        u.id_rol = rol.id_rol
        u.correo = correo
        click.echo("Usuario existente actualizado.")
    else:
        db.session.add(
            Usuario(
                id_empresa=1,
                id_sucursal=1,
                id_rol=rol.id_rol,
                usuario=usuario,
                nombre_completo=nombre,
                correo=correo,
                password_hash=generar_password(password),
                estado="activo",
                fecha_creacion=nicaragua_now(),
            )
        )
        click.echo("Usuario administrador creado.")
    db.session.commit()


# ==================================================================
@click.command("sync-now")
@with_appcontext
def sync_now():
    """Fuerza una sincronizacion completa contra la nube."""
    from app.services.sync_service import SyncService

    resultado = SyncService.sync_full(disparador="cli")
    click.echo(resultado)


@click.command("sync-status")
@with_appcontext
def sync_status():
    """Muestra el estado de la sincronizacion."""
    from app.services.sync_service import SyncService
    from app.services.network_service import NetworkService

    NetworkService.check_connectivity()
    click.echo(SyncService.estado_general())


# ==================================================================
@click.command("demo-quesillo")
@with_appcontext
def demo_quesillo():
    """Crea el ejemplo real: Quesillo = 2 tortillas + 1/4 crema + 6oz cebolla + 1 quesillo."""
    from app.models import Producto, UnidadMedida, Inventario, Usuario
    from app.services.receta_service import RecetaService

    admin = Usuario.query.filter(Usuario.estado == "activo").first()
    if not admin:
        click.echo("Crea primero un usuario: flask crear-admin")
        return

    def unidad(abrev):
        u = UnidadMedida.query.filter_by(abreviatura=abrev).first()
        return u.id_unidad if u else None

    def crear(nombre, tipo, precio_compra, precio_venta, abrev, stock):
        p = Producto.query.filter_by(nombre=nombre).first()
        if not p:
            p = Producto(
                id_empresa=1,
                nombre=nombre,
                tipo_producto=tipo,
                precio_compra=precio_compra,
                precio_venta=precio_venta,
                id_unidad=unidad(abrev),
                es_ingrediente_receta=(tipo == "insumo"),
                se_vende=True,
                estado="activo",
            )
            db.session.add(p)
            db.session.flush()
        if not Inventario.query.filter_by(id_producto=p.id_producto).first():
            db.session.add(
                Inventario(
                    id_producto=p.id_producto, id_sucursal=1,
                    stock_actual=stock, stock_minimo=5, stock_maximo=stock * 2,
                )
            )
            db.session.flush()
        return p

    tortilla = crear("Tortilla", "insumo", 1.5, 3.0, "und", 300)
    crema = crear("Crema", "insumo", 60.0, 90.0, "L", 20)
    cebolla = crear("Cebolla encurtida", "insumo", 2.0, 5.0, "oz", 200)
    quesillo_ins = crear("Quesillo (insumo)", "insumo", 25.0, 40.0, "und", 80)
    producto_final = crear("Quesillo Lo Nuestro", "final", 0, 60.0, "und", 0)

    db.session.commit()

    if not producto_final.es_receta:
        RecetaService.crear_receta(
            producto_final.id_producto,
            {
                "nombre": "Quesillo Lo Nuestro",
                "descripcion": "Quesillo tradicional nicaragüense",
                "modo_preparacion": "Calentar la tortilla, colocar el quesillo, "
                                    "agregar crema y cebolla encurtida. Envolver.",
                "tiempo_preparacion": 5,
                "rendimiento": 1,
                "id_unidad_rendimiento": unidad("und"),
            },
            [
                {"id_producto": tortilla.id_producto, "cantidad_necesaria": 2, "id_unidad": unidad("und")},
                {"id_producto": crema.id_producto, "cantidad_necesaria": 0.25, "id_unidad": unidad("L")},
                {"id_producto": cebolla.id_producto, "cantidad_necesaria": 6, "id_unidad": unidad("oz")},
                {"id_producto": quesillo_ins.id_producto, "cantidad_necesaria": 1, "id_unidad": unidad("und")},
            ],
            admin.id_usuario,
        )
        click.echo("Receta 'Quesillo Lo Nuestro' creada con 4 insumos.")
    else:
        click.echo("La receta ya existía.")

    click.echo("Máximo producible: %s" % RecetaService.maximo_producible(producto_final.id_producto))
