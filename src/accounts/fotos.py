"""La foto de perfil: qué archivo se acepta. Es una regla pura, sin base ni web.

El tipo se reconoce por los primeros bytes y no por el nombre ni por lo que dice
el navegador: los dos los elige quien sube el archivo. Sólo se admiten JPEG, PNG y
WebP, que el navegador pinta sin ejecutar nada; un SVG puede llevar código y
queda afuera. El tope es el mismo que el CHECK de `fotos_de_perfil`.
"""

TAMANO_MAXIMO_DE_FOTO = 2 * 1024 * 1024
MOTIVO_DE_FOTO_VACIA = "Elige una imagen para subir."
MOTIVO_DE_FOTO_GRANDE = "La imagen pesa más de 2 MB. Elige una más liviana."
MOTIVO_DE_FOTO_TIPO = "Sólo se aceptan imágenes JPG, PNG o WebP."


def tipo_de_imagen(datos: bytes) -> str | None:
    """El tipo MIME de la imagen según sus bytes, o `None` si no es uno admitido."""
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(datos: bytes) -> str | None:
    """Devuelve `None` si la imagen se puede guardar, o el motivo del rechazo."""
    if not datos:
        return MOTIVO_DE_FOTO_VACIA
    if len(datos) > TAMANO_MAXIMO_DE_FOTO:
        return MOTIVO_DE_FOTO_GRANDE
    if tipo_de_imagen(datos) is None:
        return MOTIVO_DE_FOTO_TIPO
    return None
