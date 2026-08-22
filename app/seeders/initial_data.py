from app import create_app
from app.extensions import db

from app.models.usuario import Usuario
from app.services.auth_service import generar_password

app = create_app()

with app.app_context():

    admin = Usuario.query.filter_by(usuario="admin").first()

    if admin:
        admin.password_hash = generar_password("admin123")
        admin.estado = "activo"
        db.session.commit()
        print("ADMIN ACTUALIZADO 🔥")

    else:
        nuevo_admin = Usuario(
            id_empresa=1,
            id_sucursal=1,
            id_rol=1,
            usuario="admin",
            nombre_completo="Administrador",
            correo="admin@pos.com",
            telefono="8888-8888",
            password_hash=generar_password("admin123"),
            estado="activo"
        )

        db.session.add(nuevo_admin)
        db.session.commit()
        print("ADMIN CREADO 🔥")