"""Aplicación Flask con las cinco rutas del eje (REQ-24 a REQ-29).

La presentación resuelve una cosa sola: toma la petición, llama a la fachada del
ledger y pinta la plantilla con lo que la fachada devolvió. Ninguna ruta decide
reglas de negocio ni ejecuta consultas (REQ-29), así que este módulo no conoce el
motor ni los repositorios: recibe una fábrica de cadenas y habla con `Blockchain` y
con `Wallet`. El motivo del rechazo se muestra porque el CU-02 lo pide: quien
propone una transacción tiene que saber por qué no entró al pool.

Uso: `python -m src.web`.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import Flask, abort, render_template, request
from werkzeug.exceptions import NotFound

from src.domain.blockchain import Blockchain, ensure_genesis


def create_app(chain_factory: Callable[[], AbstractContextManager[Blockchain]]) -> Flask:
    """Arma la aplicación con la fábrica que abre el ledger de cada petición.

    La fábrica llega por parámetro en vez de armarse aquí porque este módulo no
    puede importar la capa que la construye (REQ-29): la presentación no sabe de
    dónde sale la cadena, solo que puede pedir una. Ese es también el punto por el
    que las pruebas inyectan su propia base, y por el que `src/web/__main__.py` es
    quien la cablea cuando se levanta la aplicación de verdad.
    """
    app = Flask(__name__)

    @contextmanager
    def abrir_cadena() -> Iterator[Blockchain]:
        """Abre el ledger y deja el génesis asegurado antes de usarlo."""
        with chain_factory() as chain:
            # El génesis se asegura en cada petición porque es idempotente: así la
            # aplicación no depende de que alguien haya corrido el arranque antes.
            ensure_genesis(chain)
            yield chain

    @app.get("/")
    def portada():
        """Portada: los conteos del ledger y el acceso a los cinco casos de uso."""
        with abrir_cadena() as chain:
            return render_template("index.html", estado=chain.ledger_state())

    @app.route("/wallets", methods=["GET", "POST"])
    def wallets():
        """CU-01: registra una wallet y muestra la lista con sus claves públicas (REQ-24).

        La rama `GET` pasa además las wallets registradas porque el CU-05 necesita una
        puerta visible: sin la lista habría que teclear a mano una llave pública de 66
        caracteres que no aparece en ninguna otra página. La lista va dentro de esta
        ruta, que ya existe, para no agregar una sexta al eje.
        """
        if request.method == "GET":
            with abrir_cadena() as chain:
                return render_template(
                    "wallet.html", wallet=None, wallets=chain.wallets.list()
                )
        with abrir_cadena() as chain:
            wallet = chain.register_wallet()
            return render_template("wallet.html", wallet=wallet)

    @app.route("/transacciones", methods=["GET", "POST"])
    def transacciones():
        """CU-02: propone una transacción e informa si entró al pool o por qué no (REQ-25).

        El motivo se muestra aunque no haya fila guardada: el rechazo sin escritura
        también es un resultado del caso de uso, y quien propuso necesita saberlo.
        """
        if request.method == "GET":
            with abrir_cadena() as chain:
                return render_template(
                    "transaccion.html",
                    resultado=None,
                    wallets=chain.wallets.list(),
                    error_formulario=None,
                )
        with abrir_cadena() as chain:
            sender_id = _uuid(request.form.get("sender_id"))
            receiver_id = _uuid(request.form.get("receiver_id"))
            if sender_id is None or receiver_id is None:
                # Un identificador ausente o mal escrito no llega a la fachada: se
                # informa en la misma página, que es el resultado del caso de uso.
                return render_template(
                    "transaccion.html",
                    resultado=None,
                    wallets=chain.wallets.list(),
                    error_formulario="El emisor y el receptor deben ser wallets registradas.",
                )
            resultado = chain.create_transaction(
                sender_id=sender_id,
                receiver_id=receiver_id,
                amount=_monto(request.form.get("amount")),
            )
            return render_template(
                "transaccion.html",
                resultado=resultado,
                wallets=chain.wallets.list(),
                error_formulario=None,
            )

    @app.route("/bloques", methods=["GET", "POST"])
    def bloques():
        """CU-03: agrupa el pool en un bloque nuevo y muestra el eslabón creado (REQ-26)."""
        if request.method == "GET":
            return render_template("bloque.html", bloque=None, habia_pool=False)
        with abrir_cadena() as chain:
            habia_pool = bool(chain.transactions.pending())
            bloque = chain.group_pending()
            return render_template("bloque.html", bloque=bloque, habia_pool=habia_pool)

    @app.get("/verificar")
    def verificar():
        """CU-04: recalcula la cadena y muestra el dictamen (REQ-27)."""
        with abrir_cadena() as chain:
            return render_template("verificar.html", dictamen=chain.verify_chain())

    @app.get("/historial/<wallet>")
    def historial(wallet: str):
        """CU-05: el historial de una wallet, con el estado de cada transacción (REQ-28).

        El identificador se valida antes de consultar nada y la wallet se busca en la
        fachada: si no existe, la respuesta es la página de error con 404 y no un
        error del motor en pantalla (RF-5).
        """
        try:
            wallet_id = UUID(wallet)
        except ValueError:
            abort(404, description="El identificador no es un UUID válido.")
        with abrir_cadena() as chain:
            if chain.wallets.get(wallet_id) is None:
                abort(404, description="No hay ninguna wallet registrada con ese identificador.")
            return render_template(
                "historial.html",
                wallet_id=wallet_id,
                transacciones=chain.wallet_history(wallet_id),
            )

    @app.errorhandler(404)
    def no_encontrado(error):
        """Página de error clara y en español para lo que no existe (RF-5).

        Las rutas de este módulo pasan su descripción en español. Cuando la ruta no
        existe, la descripción la pone Werkzeug en inglés, así que se reemplaza por
        una propia en vez de mostrarla dentro de una página en español.
        """
        detalle = error.description
        if not detalle or detalle == NotFound.description:
            detalle = "No se encontró lo que buscaba."
        return render_template("error.html", detalle=detalle), 404

    return app


def _uuid(value: str | None) -> UUID | None:
    """Convierte el identificador del formulario; `None` si no es un UUID.

    Se devuelve `None` y no se levanta el error: un identificador mal escrito es un
    dato que el caso de uso tiene que rechazar con su motivo, no una caída.
    """
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


def _monto(value: str | None) -> Decimal:
    """Convierte el monto del formulario; un valor ilegible se convierte en cero.

    Cero es un monto que el dominio rechaza con su motivo (REQ-04), así que un
    formulario mal escrito sigue el camino del rechazo y no el de la excepción.
    """
    try:
        return Decimal(value) if value else Decimal(0)
    except InvalidOperation:
        return Decimal(0)
