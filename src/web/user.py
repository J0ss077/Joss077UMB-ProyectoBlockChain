"""El tablero del usuario común: envío, historial y verificación propios.

Cuatro rutas con una sola regla de alcance (REQ-34, REQ-35, REQ-39): el emisor de
un envío sale de la sesión y nunca del formulario, el historial y la verificación
se filtran por la wallet de la sesión, y el administrador que entra acá vuelve a
su portada. El destinatario se resuelve primero como nombre de usuario y después
como identificador de wallet, que es el orden que fija el diseño (decisión 4).

La resolución usa el servicio de cuentas y no el repositorio: la presentación no
consulta la base (REQ-29). La validez del envío —saldo, firma, formato— la sigue
decidiendo `Blockchain.create_transaction`, y su motivo se muestra tal cual; acá
sólo se decide quién puede llamar y qué se pinta.

El blueprint se arma con las fábricas que le pasa `create_app`, por la misma razón
que la aplicación: este módulo no puede construir el ledger ni las cuentas sin
conocer la persistencia.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from flask import Blueprint, abort, g, render_template, request

from src.accounts.service import Cuentas
from src.domain.blockchain import Blockchain, TransactionResult
from src.domain.transaction import TransactionStatus
from src.web.auth import requiere_usuario_comun
from src.web.forms import a_monto, a_uuid

# El único rechazo que decide la presentación: el destinatario no es ni una cuenta
# ni una wallet. Los demás motivos los pone el dominio y se muestran sin traducir,
# así que este texto no repite ninguna regla de negocio.
MENSAJE_DESTINATARIO_INEXISTENTE = (
    "No se encontró una cuenta ni una wallet con ese destinatario."
)

FabricaDeCadenas = Callable[[], AbstractContextManager[Blockchain]]
FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]


def crear_blueprint_del_usuario(
    abrir_cadena: FabricaDeCadenas, abrir_cuentas: FabricaDeCuentas
) -> Blueprint:
    """Arma las rutas del tablero con las fábricas que recibe de `create_app`."""
    tablero = Blueprint("usuario", __name__)

    @tablero.get("/mi-tablero")
    @requiere_usuario_comun
    def mi_tablero() -> str:
        """REQ-34: la pantalla de trabajo del usuario común, con su envío."""
        with abrir_cadena() as chain:
            return _pintar_tablero(chain)

    @tablero.post("/mi-envio")
    @requiere_usuario_comun
    def mi_envio() -> str:
        """REQ-34: propone un envío desde la wallet de la sesión y nunca desde otra.

        El emisor es `g.user.wallet_id`: si el formulario trae un `sender_id`, no
        se lee. El destinatario se resuelve primero por nombre de usuario —que es
        único— y después por el identificador de la wallet. Un destinatario que no
        existe se informa antes de llegar al dominio porque no hay wallet con la
        que firmar; el resto de los rechazos los decide `create_transaction` y su
        motivo se muestra sin traducir.
        """
        wallet_propia = _wallet_de_la_sesion()
        destinatario = request.form.get("destinatario", "")
        with abrir_cuentas() as cuentas:
            wallet_destino = _wallet_del_destinatario(cuentas, destinatario)
        with abrir_cadena() as chain:
            if wallet_destino is None:
                return _pintar_tablero(
                    chain, error_formulario=MENSAJE_DESTINATARIO_INEXISTENTE
                )
            resultado = chain.create_transaction(
                sender_id=wallet_propia,
                receiver_id=wallet_destino,
                amount=a_monto(request.form.get("amount")),
            )
            return _pintar_tablero(
                chain,
                resultado=resultado,
                motivo_por_transaccion=_motivo_por_la_transaccion(resultado),
            )

    @tablero.get("/mi-historial")
    @requiere_usuario_comun
    def mi_historial() -> str:
        """REQ-35: sólo las transacciones de la wallet de la sesión."""
        wallet_id = _wallet_de_la_sesion()
        with abrir_cadena() as chain:
            return render_template(
                "mi_historial.html",
                wallet_id=wallet_id,
                transacciones=chain.wallet_history(wallet_id),
            )

    @tablero.get("/mi-verificacion")
    @requiere_usuario_comun
    def mi_verificacion() -> str:
        """REQ-39: el dictamen de la cadena y sólo las confirmadas de la sesión.

        La cadena completa se verifica porque el dictamen es global, pero la lista
        se filtra por la wallet de la sesión: de otros no se muestra ni el
        identificador de su transacción. Con la cadena alterada la página lo dice
        y no presenta las confirmadas como si estuvieran respaldadas.
        """
        wallet_id = _wallet_de_la_sesion()
        with abrir_cadena() as chain:
            confirmadas = [
                transaction
                for transaction in chain.wallet_history(wallet_id)
                if transaction.status is TransactionStatus.CONFIRMED
            ]
            return render_template(
                "mi_verificacion.html",
                dictamen=chain.verify_chain(),
                transacciones=confirmadas,
                wallet_id=wallet_id,
            )

    return tablero


def _wallet_de_la_sesion() -> UUID:
    """La wallet de la cuenta que tiene la sesión abierta (REQ-34).

    El esquema exige wallet en toda cuenta aprobada, así que la falta es un estado
    imposible del que igual conviene no depender: sin wallet no hay tablero y la
    respuesta es 403, no una consulta con `None`.
    """
    wallet_id = g.user.wallet_id
    if wallet_id is None:
        abort(403)
    return wallet_id


def _wallet_del_destinatario(cuentas: Cuentas, destinatario: str) -> UUID | None:
    """La wallet del destinatario: primero por nombre de usuario, luego por id.

    El orden es el del diseño (decisión 4): el nombre de usuario es el camino
    normal y el identificador es el atajo de quien lo tiene a mano. Un nombre que
    no existe todavía puede ser un identificador escrito a mano, así que se
    intenta interpretar como UUID; si tampoco lo es, la ruta informa el rechazo
    sin consultar el ledger. Una cuenta sin wallet (pendiente o rechazada) no
    puede recibir y cae por el mismo camino que un nombre inexistente.
    """
    texto = destinatario.strip()
    if not texto:
        return None
    usuario = cuentas.por_username(texto)
    if usuario is not None and usuario.wallet_id is not None:
        return usuario.wallet_id
    return a_uuid(texto)


def _pintar_tablero(
    chain: Blockchain,
    *,
    resultado: TransactionResult | None = None,
    error_formulario: str | None = None,
    motivo_por_transaccion: dict[UUID, str] | None = None,
) -> str:
    """Pinta el tablero con la wallet de la sesión y lo que el ledger tiene de ella.

    El saldo es el disponible real de la fachada —el mismo que usa el envío para
    decidir—, y el historial se filtra por la wallet de la sesión. No se pasa el
    panel lateral de `base.html`: esa lista es de la portada del administrador y
    mostraría las wallets de otros, que es justo lo que REQ-35 prohíbe.
    """
    wallet_id = _wallet_de_la_sesion()
    return render_template(
        "tablero.html",
        wallet_id=wallet_id,
        saldo=chain.available_balance(wallet_id),
        transacciones=chain.wallet_history(wallet_id),
        resultado=resultado,
        error_formulario=error_formulario,
        motivo_por_transaccion=motivo_por_transaccion or {},
    )


def _motivo_por_la_transaccion(resultado: TransactionResult) -> dict[UUID, str]:
    """El motivo del rechazo, atado a la fila que acaba de quedar `rejected`.

    La base guarda el estado de la rechazada pero no su motivo —el esquema no
    tiene esa columna—, así que el único momento en que se puede mostrar junto a
    la fila es la respuesta del envío que la produjo. En un rechazo que no dejó
    fila no hay nada que anotar.
    """
    if resultado.accepted or resultado.stored is None:
        return {}
    return {resultado.stored.id: str(resultado.reason)}
