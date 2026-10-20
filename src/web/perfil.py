"""El perfil de la cuenta: sus datos, el idioma y el cambio de contraseña.

Es de las dos clases de cuenta. El usuario común no cambia su contraseña por su
cuenta: el formulario deja una solicitud con la contraseña nueva ya hasheada y un
administrador la aprueba desde su cola (`admin.py`); mientras tanto la persona
sigue entrando con la de siempre. El administrador no tiene a quién pedírsela, así
que la suya se aplica de una vez. Las dos cosas las decide `Cuentas`; acá sólo se
compara la repetición, que es una regla del formulario y no de la cuenta.

El idioma se elige con el mismo formulario que la barra superior (`POST /idioma`),
así que esta pantalla no guarda nada por su cuenta.

La foto de perfil se sube, se reemplaza o se quita acá. Con JavaScript, `foto.js`
abre un editor para encuadrarla y sube el recorte; sin él, se sube el archivo tal
cual. En los dos casos `Cuentas.poner_foto` decide si la imagen sirve y la guarda
como un archivo aparte, fuera de la base. La foto se sirve desde
`/foto/<usuario>` sólo a quien tiene sesión, con el tipo que se reconoció al
guardarla y sin dejar que el navegador adivine otro.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.accounts.fotos import TAMANO_MAXIMO_DE_FOTO
from src.accounts.model import ADMINISTRADOR
from src.accounts.service import CambioDeContrasenaInvalido, Cuentas, FotoInvalida
from src.web.auth import requiere_sesion

MENSAJE_CONTRASENAS_DISTINTAS = "Las contraseñas no coinciden."
MENSAJE_SOLICITUD_ENVIADA = (
    "Listo: tu solicitud se envió. Un administrador tiene que aprobarla; "
    "mientras tanto sigues entrando con tu contraseña de siempre."
)
MENSAJE_CONTRASENA_CAMBIADA = "Tu contraseña se cambió."
MENSAJE_FOTO_GUARDADA = "Tu foto de perfil se guardó."
MENSAJE_FOTO_QUITADA = "Quitaste tu foto de perfil."

# Una dirección con `?v=` no cambia nunca de contenido —la versión es la fecha de
# la foto—, así que el navegador puede guardarla sin volver a pedirla.
CACHE_DE_FOTO_VERSIONADA = "private, max-age=31536000, immutable"

FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]


def crear_blueprint_del_perfil(abrir_cuentas: FabricaDeCuentas) -> Blueprint:
    """Arma las rutas del perfil con la fábrica de cuentas de `create_app`."""
    perfil = Blueprint("perfil", __name__)

    @perfil.get("/perfil")
    @requiere_sesion
    def ver() -> str:
        """Los datos de la cuenta de la sesión y el estado de su último cambio de contraseña."""
        solicitud = None
        if g.user.role != ADMINISTRADOR:
            with abrir_cuentas() as cuentas:
                solicitud = cuentas.ultima_solicitud(g.user.id)
        return render_template("perfil.html", solicitud=solicitud)

    @perfil.post("/perfil/contrasena")
    @requiere_sesion
    def cambiar_contrasena() -> Response:
        """Pide (o, para el administrador, aplica) el cambio y vuelve al perfil con el resultado."""
        nueva = request.form.get("nueva", "")
        if nueva != request.form.get("repetir", ""):
            flash(MENSAJE_CONTRASENAS_DISTINTAS, "motivo")
            return redirect(url_for("perfil.ver"))
        with abrir_cuentas() as cuentas:
            try:
                solicitud = cuentas.cambiar_contrasena(
                    g.user.id, request.form.get("actual", ""), nueva
                )
            except CambioDeContrasenaInvalido as error:
                flash(str(error), "motivo")
                return redirect(url_for("perfil.ver"))
        flash(
            MENSAJE_CONTRASENA_CAMBIADA if solicitud is None else MENSAJE_SOLICITUD_ENVIADA,
            "exito",
        )
        return redirect(url_for("perfil.ver"))

    @perfil.post("/perfil/foto")
    @requiere_sesion
    def poner_foto() -> Response:
        """Pone o reemplaza la foto de la cuenta de la sesión y vuelve al perfil.

        Se lee un byte más que el tope: alcanza para saber que se pasó sin cargar
        en memoria un archivo de cualquier tamaño.
        """
        archivo = request.files.get("foto")
        datos = archivo.read(TAMANO_MAXIMO_DE_FOTO + 1) if archivo else b""
        with abrir_cuentas() as cuentas:
            try:
                cuentas.poner_foto(g.user.id, datos)
            except FotoInvalida as error:
                flash(str(error), "motivo")
            else:
                flash(MENSAJE_FOTO_GUARDADA, "exito")
        return redirect(url_for("perfil.ver"))

    @perfil.post("/perfil/foto/quitar")
    @requiere_sesion
    def quitar_foto() -> Response:
        """Vuelve al avatar por defecto: la inicial del nombre."""
        with abrir_cuentas() as cuentas:
            cuentas.quitar_foto(g.user.id)
        flash(MENSAJE_FOTO_QUITADA, "exito")
        return redirect(url_for("perfil.ver"))

    @perfil.get("/foto/<username>")
    @requiere_sesion
    def foto(username: str) -> Response:
        """La foto de perfil de una cuenta, para quien tiene sesión; 404 si no tiene.

        `nosniff` y la política de contenido vacía hacen que la respuesta sólo
        pueda pintarse como la imagen que dice ser.
        """
        with abrir_cuentas() as cuentas:
            guardada = cuentas.archivo_de_foto(username)
        if guardada is None:
            abort(404)
        ruta, tipo = guardada
        respuesta = send_file(ruta, mimetype=tipo, conditional=True)
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["Content-Security-Policy"] = "default-src 'none'"
        respuesta.headers["Cache-Control"] = (
            CACHE_DE_FOTO_VERSIONADA if request.args.get("v") else "private, no-cache"
        )
        return respuesta

    return perfil
