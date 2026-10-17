"""Credenciales de usuario: la forma del nombre y el hash de la contraseña.

REQ-30 fija qué nombres de usuario se aceptan y REQ-36 cómo se guarda una
contraseña. Acá no hay base ni sesión: son reglas puras.
"""
import base64
import hashlib
import hmac
import re
import secrets

# El único lugar donde vive el conjunto de caracteres permitidos: los formularios
# lo usan como `pattern` y `validar_usuario` lo aplica, así que no pueden divergir.
PATRON_DE_USUARIO = r"[a-z0-9_.-]{3,20}"

# El motivo repite la regla del patrón porque es el texto que lee la persona; si
# el patrón cambia, este mensaje cambia con él.
MOTIVO_DE_USUARIO_INVALIDO = (
    "El usuario sólo admite minúsculas, dígitos, punto, guion y guion bajo, "
    "entre 3 y 20 caracteres."
)

# Piso de contraseña que el diseño deja a criterio: ocho caracteres alcanzan para
# el prototipo y no estorban en la demostración.
LARGO_MINIMO_DE_CONTRASENA = 8
MOTIVO_DE_CONTRASENA_CORTA = (
    f"La contraseña debe tener al menos {LARGO_MINIMO_DE_CONTRASENA} caracteres."
)

# Costo de scrypt: 2**14 bloques y r=8 piden 16 MiB por hash, que es el mínimo que
# recomienda la propia documentación de Python para un uso interactivo. El costo
# viaja dentro del hash, así que subirlo no invalida las contraseñas viejas.
COSTO_N = 2**14
BLOQUE_R = 8
PARALELISMO_P = 1
ALGORITMO = "scrypt"
LARGO_DE_LA_SAL = 16
LARGO_DEL_HASH = 32


def normalizar_usuario(texto: str) -> str:
    """Recorta los extremos y pasa a minúsculas: así se guarda y se compara."""
    return texto.strip().lower()


def validar_usuario(texto: str) -> str | None:
    """Devuelve `None` si el usuario es válido, o el motivo del rechazo.

    No normaliza: el patrón de los formularios recibe el texto tal cual, y esta
    validación tiene que aceptar exactamente lo mismo que ese patrón.
    """
    if re.fullmatch(PATRON_DE_USUARIO, texto):
        return None
    return MOTIVO_DE_USUARIO_INVALIDO


def validar_contrasena(texto: str) -> str | None:
    """Devuelve `None` si la contraseña llega al mínimo, o el motivo del rechazo."""
    if len(texto) < LARGO_MINIMO_DE_CONTRASENA:
        return MOTIVO_DE_CONTRASENA_CORTA
    return None


def _a_base64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def hashear_contrasena(texto: str) -> str:
    """Devuelve el hash autodescriptivo `scrypt$n$r$p$sal_b64$hash_b64` de `texto`.

    La sal es nueva en cada llamada, así que dos personas con la misma contraseña
    no comparten hash.
    """
    sal = secrets.token_bytes(LARGO_DE_LA_SAL)
    derivada = hashlib.scrypt(
        texto.encode("utf-8"),
        salt=sal,
        n=COSTO_N,
        r=BLOQUE_R,
        p=PARALELISMO_P,
        dklen=LARGO_DEL_HASH,
    )
    return (
        f"{ALGORITMO}${COSTO_N}${BLOQUE_R}${PARALELISMO_P}"
        f"${_a_base64(sal)}${_a_base64(derivada)}"
    )


def _leer_guardado(guardado: str) -> tuple[int, int, int, bytes, bytes] | None:
    """Parte un hash guardado, o devuelve `None` si no tiene el formato esperado."""
    campos = guardado.split("$")
    if len(campos) != 6 or campos[0] != ALGORITMO:
        return None
    try:
        n, r, p = (int(campo) for campo in campos[1:4])
        sal = base64.b64decode(campos[4], validate=True)
        esperada = base64.b64decode(campos[5], validate=True)
    except ValueError:
        # `binascii.Error` hereda de `ValueError`: cubre el base64 roto y los
        # números que no son números.
        return None
    if n < 2 or r < 1 or p < 1 or not sal or not esperada:
        return None
    return n, r, p, sal, esperada


def verificar_contrasena(texto: str, guardado: str) -> bool:
    """Compara `texto` con el hash guardado, sin filtrar por tiempo.

    Un valor guardado corrupto no lanza: devuelve `False`, porque la sesión que lo
    encuentre tiene que rechazar el ingreso y seguir.
    """
    parametros = _leer_guardado(guardado)
    if parametros is None:
        return False
    n, r, p, sal, esperada = parametros
    try:
        derivada = hashlib.scrypt(
            texto.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=len(esperada)
        )
    except (ValueError, OverflowError, MemoryError):
        # Parámetros fuera de rango o demasiado caros: el valor guardado no sirve.
        return False
    return hmac.compare_digest(derivada, esperada)
