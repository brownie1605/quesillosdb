"""Validacion compartida de imagenes subidas (productos, usuarios...).

No se confia en el mimetype que manda el navegador (se puede falsear): se
deriva del nombre de archivo validado contra una lista blanca de
extensiones, y se limita el tamano para evitar subidas gigantes (no hay
`MAX_CONTENT_LENGTH` global que las frene antes).
"""
from werkzeug.utils import secure_filename

EXTENSIONES_IMAGEN = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
IMAGEN_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def leer_imagen_validada(imagen_file):
    """Valida extension y tamano de un archivo subido (FileStorage de Flask).

    Devuelve (datos_bytes, mimetype_canonico) o lanza ValueError con un
    mensaje listo para mostrarle al usuario.
    """
    nombre = secure_filename(imagen_file.filename or "")
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext not in EXTENSIONES_IMAGEN:
        raise ValueError("Formato de imagen no permitido (usa PNG, JPG, WEBP o GIF)")

    datos = imagen_file.read()
    if len(datos) > IMAGEN_MAX_BYTES:
        raise ValueError("La imagen no puede pesar más de 5 MB")
    if not datos:
        raise ValueError("El archivo de imagen está vacío")

    return datos, EXTENSIONES_IMAGEN[ext]
