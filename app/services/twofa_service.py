"""2FA (TOTP) por usuario -- ej. Google Authenticator, Authy, etc.

Flujo de activacion (nunca se guarda un secreto a medias en la BD):
  1. iniciar_activacion(): genera un secreto nuevo, lo deja SOLO en la
     sesion del navegador (no en la BD todavia) y devuelve el QR.
  2. confirmar_activacion(): el usuario manda el codigo de 6 digitos que
     le genero su app. Si es correcto, AHI SI se guarda `totp_secret` y
     `totp_habilitado=True`, y se generan los codigos de recuperacion
     (se muestran una sola vez, solo se guarda su hash).
"""
import base64
import hashlib
import io
import json
import secrets

import pyotp
import qrcode

from app.extensions import db

ISSUER = "Quesillos POS"
CANTIDAD_RECOVERY_CODES = 8


class TwoFAService:

    # -----------------------------------------------------------------
    @staticmethod
    def generar_secreto():
        return pyotp.random_base32()

    # -----------------------------------------------------------------
    @staticmethod
    def uri_provisioning(usuario, secreto):
        return pyotp.totp.TOTP(secreto).provisioning_uri(
            name=usuario.correo or usuario.usuario, issuer_name=ISSUER
        )

    # -----------------------------------------------------------------
    @staticmethod
    def qr_data_uri(uri_provisioning):
        """Genera el QR como imagen PNG embebida (data: URI) -- no hace
        falta guardar ningun archivo ni exponer un endpoint aparte."""
        img = qrcode.make(uri_provisioning)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    # -----------------------------------------------------------------
    @staticmethod
    def verificar_codigo(secreto, codigo):
        if not secreto or not codigo:
            return False
        codigo = codigo.strip().replace(" ", "")
        try:
            return pyotp.TOTP(secreto).verify(codigo, valid_window=1)
        except Exception:  # noqa: BLE001
            return False

    # -----------------------------------------------------------------
    @staticmethod
    def _hash_recovery(codigo):
        return hashlib.sha256(codigo.encode("utf-8")).hexdigest()

    @staticmethod
    def generar_recovery_codes():
        """Devuelve (codigos_planos, codigos_hasheados_json). Los planos se
        muestran UNA sola vez al usuario; solo el hash se guarda."""
        planos = ["-".join([secrets.token_hex(2), secrets.token_hex(2)]) for _ in range(CANTIDAD_RECOVERY_CODES)]
        hasheados = [TwoFAService._hash_recovery(c) for c in planos]
        return planos, json.dumps(hasheados)

    @staticmethod
    def verificar_y_consumir_recovery(usuario, codigo):
        """Si `codigo` coincide con uno de los codigos de recuperacion
        todavia sin usar, lo consume (no sirve dos veces) y devuelve True."""
        if not usuario.totp_recovery_codes or not codigo:
            return False
        try:
            hasheados = json.loads(usuario.totp_recovery_codes)
        except (TypeError, ValueError):
            return False
        h = TwoFAService._hash_recovery(codigo.strip())
        if h not in hasheados:
            return False
        hasheados.remove(h)
        usuario.totp_recovery_codes = json.dumps(hasheados)
        db.session.commit()
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def activar(usuario, secreto):
        """Confirma el secreto pendiente (ya verificado por fuera) y genera
        codigos de recuperacion nuevos. Devuelve los codigos en texto plano
        para mostrarlos una sola vez."""
        planos, hasheados_json = TwoFAService.generar_recovery_codes()
        usuario.totp_secret = secreto
        usuario.totp_habilitado = True
        usuario.totp_recovery_codes = hasheados_json
        db.session.commit()
        return planos

    @staticmethod
    def desactivar(usuario):
        usuario.totp_secret = None
        usuario.totp_habilitado = False
        usuario.totp_recovery_codes = None
        db.session.commit()
