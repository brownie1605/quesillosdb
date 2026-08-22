"""Envio de correos (recuperacion de contrasena) via SMTP de Gmail.

Requiere una "Contrasena de aplicacion" de Google en SMTP_PASS.
Ver README_INSTALACION.md, seccion "Configurar Gmail".
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import current_app

log = logging.getLogger("email")

PLANTILLA_CODIGO = """\
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;
            border:1px solid #eee;border-radius:12px;overflow:hidden">
  <div style="background:#8B2E2E;color:#fff;padding:20px 24px">
    <h2 style="margin:0;font-size:20px">Quesillos Lo Nuestro</h2>
    <p style="margin:4px 0 0;opacity:.85;font-size:13px">Recuperación de contraseña</p>
  </div>
  <div style="padding:24px">
    <p>Hola <strong>{nombre}</strong>,</p>
    <p>Recibimos una solicitud para restablecer tu contraseña. Tu código de
       verificación es:</p>
    <div style="font-size:34px;font-weight:700;letter-spacing:10px;text-align:center;
                background:#faf6f2;border:1px dashed #d8c3b0;border-radius:10px;
                padding:18px;margin:18px 0;color:#8B2E2E">{codigo}</div>
    <p style="font-size:13px;color:#666">
       Este código expira en <strong>15 minutos</strong>.<br>
       Si no solicitaste el cambio, ignora este mensaje y no compartas el código
       con nadie.</p>
  </div>
</div>
"""


def enviar_codigo_recuperacion(destinatario, codigo, nombre=""):
    """Devuelve (enviado: bool, detalle: str)."""
    servidor = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    puerto = current_app.config.get("MAIL_PORT", 587)
    usuario = current_app.config.get("MAIL_USERNAME")
    clave = current_app.config.get("MAIL_PASSWORD")

    if not usuario or not clave:
        return False, "SMTP sin credenciales configuradas"

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = "Quesillos Lo Nuestro <" + usuario + ">"
        msg["To"] = destinatario
        msg["Subject"] = "Código de recuperación - Quesillos Lo Nuestro"

        texto = (
            "Hola " + (nombre or "") + ",\n\n"
            "Tu código de recuperación es: " + codigo + "\n"
            "Expira en 15 minutos. No lo compartas con nadie.\n"
        )
        html = PLANTILLA_CODIGO.format(nombre=nombre or destinatario, codigo=codigo)

        msg.attach(MIMEText(texto, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(servidor, puerto, timeout=20) as server:
            server.starttls()
            server.login(usuario, clave)
            server.sendmail(usuario, destinatario, msg.as_string())

        log.info("Código de recuperación enviado a %s", destinatario)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("Fallo al enviar correo a %s: %s", destinatario, exc)
        return False, str(exc)[:200]
