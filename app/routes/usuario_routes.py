from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os
import io
from flask import send_file
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from app.models import Usuario, Rol
from app.services.auditoria_service import registrar_auditoria

from app.utils.decorators import require_roles

usuario_bp = Blueprint("usuario", __name__, url_prefix="/usuarios")

@usuario_bp.before_request
def check_roles():
    return require_roles('Administrador')


@usuario_bp.route("/")
@login_required
def lista():
    return render_template("usuarios/lista.html")

@usuario_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    usuarios = Usuario.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    res = []
    for u in usuarios:
        rol = Rol.query.get(u.id_rol) if u.id_rol else None
        d = u.to_dict()
        d["rol_nombre"] = rol.nombre if rol else "Sin Rol"
        res.append(d)
    return jsonify(res)

@usuario_bp.route("/api/roles", methods=["GET"])
@login_required
def api_roles():
    roles = Rol.query.all()
    return jsonify([r.to_dict() for r in roles])

@usuario_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.form
    imagen = request.files.get('imagen')
    imagen_url = None
    imagen_datos = None
    imagen_mimetype = None
    
    if imagen and imagen.filename:
        imagen_datos = imagen.read()
        imagen_mimetype = imagen.mimetype

    try:
        usuario = data.get("usuario")
        correo = data.get("correo")
        telefono = data.get("telefono", "")

        # Validar duplicados
        if Usuario.query.filter_by(usuario=usuario).first():
            return jsonify({"success": False, "message": f"El usuario '{usuario}' ya está en uso."}), 400
        if Usuario.query.filter_by(correo=correo).first():
            return jsonify({"success": False, "message": f"El correo '{correo}' ya está en uso."}), 400
            
        # Limpiar y validar telefono (solo numeros, sin guiones)
        if telefono:
            telefono = telefono.replace("-", "").strip()
            if not telefono.isdigit():
                return jsonify({"success": False, "message": "El teléfono solo debe contener números."}), 400

        nuevo = Usuario(
            id_empresa=current_user.id_empresa,
            id_sucursal=current_user.id_sucursal,
            id_rol=data.get("id_rol"),
            usuario=usuario,
            nombre_completo=data.get("nombre_completo"),
            correo=correo,
            telefono=telefono,
            password_hash=generate_password_hash(data.get("password") or "123456"),
            imagen_url=imagen_url,
            imagen_datos=imagen_datos,
            imagen_mimetype=imagen_mimetype,
            estado="activo"
        )
        db.session.add(nuevo)
        db.session.flush() # Get ID
        
        if imagen_datos:
            nuevo.imagen_url = f"/usuarios/imagen/{nuevo.id_usuario}"
            
        db.session.commit()
        registrar_auditoria("CREAR USUARIO", "Usuarios", f"Usuario {nuevo.usuario} creado")
        return jsonify({"success": True})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "message": "El nombre de usuario o correo ya está en uso en esta empresa."}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@usuario_bp.route("/api/editar/<int:id>", methods=["PUT"])
@login_required
def api_editar(id):
    data = request.form
    imagen = request.files.get('imagen')
    
    try:
        u = Usuario.query.get_or_404(id)
        if u.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        if imagen and imagen.filename:
            u.imagen_datos = imagen.read()
            u.imagen_mimetype = imagen.mimetype
            u.imagen_url = f"/usuarios/imagen/{u.id_usuario}"

        usuario = data.get("usuario", u.usuario)
        correo = data.get("correo", u.correo)
        telefono = data.get("telefono", u.telefono)

        # Validar duplicados (excluyendo el actual)
        if Usuario.query.filter(Usuario.usuario == usuario, Usuario.id_usuario != id).first():
            return jsonify({"success": False, "message": f"El usuario '{usuario}' ya está en uso."}), 400
        if Usuario.query.filter(Usuario.correo == correo, Usuario.id_usuario != id).first():
            return jsonify({"success": False, "message": f"El correo '{correo}' ya está en uso."}), 400
            
        # Limpiar y validar telefono
        if telefono:
            telefono = telefono.replace("-", "").strip()
            if not telefono.isdigit():
                return jsonify({"success": False, "message": "El teléfono solo debe contener números."}), 400

        u.nombre_completo = data.get("nombre_completo", u.nombre_completo)
        u.usuario = usuario
        u.correo = correo
        u.telefono = telefono
        u.id_rol = data.get("id_rol", u.id_rol)
        
        if data.get("password"):
            u.password_hash = generate_password_hash(data.get("password"))
        
        db.session.commit()
        registrar_auditoria("EDITAR USUARIO", "Usuarios", f"Usuario {u.usuario} modificado")
        return jsonify({"success": True})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "message": "El nombre de usuario o correo ya está en uso."}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@usuario_bp.route("/api/eliminar/<int:id>", methods=["DELETE"])
@login_required
def api_eliminar(id):
    try:
        u = Usuario.query.get_or_404(id)
        if u.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        u.estado = "inactivo"
        db.session.commit()
        registrar_auditoria("ELIMINAR USUARIO", "Usuarios", f"Usuario {u.usuario} marcado como inactivo")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@usuario_bp.route("/imagen/<int:id>", methods=["GET"])
def obtener_imagen(id):
    u = Usuario.query.get_or_404(id)
    if u.imagen_datos and u.imagen_mimetype:
        return send_file(
            io.BytesIO(u.imagen_datos),
            mimetype=u.imagen_mimetype,
            as_attachment=False
        )
    return "", 404
