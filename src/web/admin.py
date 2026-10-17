"""La cola de pendientes del administrador (REQ-31).

Tres rutas con la puerta del administrador: la lista de cuentas pendientes y las
dos acciones del alta moderada. Este módulo no consulta la base ni ejecuta reglas
del dominio (REQ-29): recibe la fábrica de cuentas que le pasa `create_app` y
delega en `Cuentas.pendientes`, `Cuentas.aprobar` y `Cuentas.rechazar`. La
aprobación crea la wallet y acredita el saldo dentro del servicio (REQ-33), así
que la presentación sólo informa el resultado.

El único control que vive acá es el del motivo del rechazo: un texto en blanco no
llega al servicio porque el rechazo tiene que explicar por qué. Una fila que dejó
de estar pendiente —o que ya no existe— se informa y se vuelve a la cola: la
pantalla pudo quedar vieja y el botón no puede romper la petición.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from src.accounts.service import Cuentas, UsuarioInexistente, UsuarioNoPendiente
from src.web.auth import requiere_administrador

FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]

# Los avisos de la cola. El de la aprobación nombra lo que se creó porque la
# persona no ve la wallet desde acá; los de fallo repiten el texto del servicio,
# que ya viene en español y con el estado que tenía la fila.
MENSAJE_APROBADA = "La cuenta quedó aprobada: ya tiene su wallet y su saldo."
MENSAJE_RECHAZADA = "La cuenta quedó rechazada con el motivo indicado."
MENSAJE_SIN_MOTIVO = "El rechazo necesita un motivo."


def crear_blueprint_de_la_cola(abrir_cuentas: FabricaDeCuentas) -> Blueprint:
    """Arma la cola con la fábrica de cuentas que recibe de `create_app`."""
    cola = Blueprint("admin", __name__, url_prefix="/admin")

    @cola.get("/pendientes")
    @requiere_administrador
    def pendientes() -> str:
        """REQ-31: las cuentas que esperan aprobación, con su usuario y su fecha."""
        with abrir_cuentas() as cuentas:
            return render_template("pendientes.html", pendientes=cuentas.pendientes())

    @cola.post("/pendientes/<identificador>/aprobar")
    @requiere_administrador
    def aprobar(identificador: str) -> Response:
        """REQ-31: aprueba una cuenta pendiente y vuelve a la cola.

        La wallet y el saldo los escribe `Cuentas.aprobar` en una sola transacción
        (REQ-33). Si la fila ya no estaba pendiente, el servicio no escribe nada y
        su motivo se informa como aviso: una segunda aprobación desde otra pestaña
        no puede crear otra wallet ni terminar en una página de error.
        """
        cuenta_id = _identificador(identificador)
        with abrir_cuentas() as cuentas:
            try:
                cuentas.aprobar(cuenta_id)
            except (UsuarioNoPendiente, UsuarioInexistente) as error:
                flash(str(error), "aviso")
            else:
                flash(MENSAJE_APROBADA, "exito")
        return redirect(url_for("admin.pendientes"))

    @cola.post("/pendientes/<identificador>/rechazar")
    @requiere_administrador
    def rechazar(identificador: str) -> Response:
        """REQ-31: rechaza con un motivo obligatorio y vuelve a la cola.

        El motivo en blanco se corta antes de llamar al servicio: el rechazo sin
        explicación no se escribe y la cola avisa. Un motivo válido lo guarda
        `Cuentas.rechazar`, que también se niega a tocar una fila que ya no está
        pendiente; ese caso se informa igual que en la aprobación.
        """
        cuenta_id = _identificador(identificador)
        motivo = request.form.get("motivo", "")
        if not motivo.strip():
            flash(MENSAJE_SIN_MOTIVO, "aviso")
            return redirect(url_for("admin.pendientes"))
        with abrir_cuentas() as cuentas:
            try:
                cuentas.rechazar(cuenta_id, motivo)
            except (UsuarioNoPendiente, UsuarioInexistente) as error:
                flash(str(error), "aviso")
            else:
                flash(MENSAJE_RECHAZADA, "exito")
        return redirect(url_for("admin.pendientes"))

    return cola


def _identificador(valor: str) -> UUID:
    """Convierte el identificador de la ruta; una forma inválida es un 404.

    El mismo criterio que el historial: un identificador que no es un UUID no es
    una cuenta que dejó de estar pendiente, es una ruta que no existe.
    """
    try:
        return UUID(valor)
    except ValueError:
        abort(404, description="El identificador no es un UUID válido.")
