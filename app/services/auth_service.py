# auth_service.py
from werkzeug.security import generate_password_hash, check_password_hash


def generar_password(password):
    return generate_password_hash(password)


def verificar_password(hash_password, password):
    return check_password_hash(hash_password, password)