"""El tablero del usuario común: envío, historial y verificación propios.

Tres rutas con una sola regla de alcance (REQ-34, REQ-35, REQ-39): el emisor de un
envío sale de la sesión y nunca del formulario, el historial y la verificación se
filtran por la wallet de la sesión, y el administrador que entra acá vuelve a su
portada. El destinatario se resuelve primero como nombre de usuario y después como
identificador de wallet, que es el orden que fija el diseño (decisión 4).

La verificación y el historial comparten una sola página, `/mi-historial`: arriba
va el dictamen de la cadena y debajo todas las transacciones de la sesión con su
estado, y las confirmadas con el índice del bloque que las agrupa. `/mi-verificacion`
sobrevive como redirección para no romper un enlace guardado.

`/mis-contactos` es la agenda: las cuentas que la persona agregó por su nombre de
usuario, con cuántos movimientos tiene con cada una y un atajo para enviarle. La
agenda no muestra nada que el envío no muestre ya —el nombre y los movimientos
propios—, así que no abre la vista a las wallets de otros (REQ-35).
`/mis-contactos/sugerencias` es la vista previa de los campos de destinatario:
mientras se teclea, ofrece los nombres de las cuentas que pueden recibir un envío.

Todo lo que lee el usuario común va en palabras de todos los días: nada de pool,
wallet, bloque ni firma. Los motivos de rechazo del dominio se traducen acá con
`MOTIVOS_EN_PALABRAS`; el administrador los sigue viendo tal como los da el dominio.

La resolución usa el servicio de cuentas y no el repositorio: la presentación no
consulta la base (REQ-29). La validez del envío —saldo, firma, formato— la sigue
decidiendo `Blockchain.create_transaction`, y su motivo se muestra tal cual; acá
sólo se decide quién puede llamar, qué se pinta y con qué palabras.

El blueprint se arma con las fábricas que le pasa `create_app`, por la misma razón
que la aplicación: este módulo no puede construir el ledger ni las cuentas sin
conocer la persistencia.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from src.accounts.model import Usuario
from src.accounts.service import ContactoInvalido, Cuentas
from src.domain.blockchain import Blockchain, TransactionResult
from src.domain.transaction import RejectionReason, Transaction, TransactionStatus
from src.emision import CONSTITUYENTE_ID
from src.web.auth import requiere_usuario_comun
from src.web.forms import a_monto, a_uuid

# El único rechazo que decide la presentación: el destinatario no es ni una cuenta
# ni una wallet. Los demás motivos los pone el dominio y se muestran sin traducir,
# así que este texto no repite ninguna regla de negocio.
MENSAJE_DESTINATARIO_INEXISTENTE = (
    "No encontramos a nadie con ese nombre de usuario."
)

# Los motivos del dominio dichos para una persona sin conocimientos técnicos. Un
# motivo que falte acá se muestra tal cual, así que agregar uno al dominio no deja
# a la pantalla sin explicación.
MOTIVOS_EN_PALABRAS: dict[str, str] = {
    RejectionReason.AMOUNT_NOT_POSITIVE: "El monto tiene que ser mayor que cero.",
    RejectionReason.AMOUNT_PRECISION: "El monto tiene demasiados decimales.",
    RejectionReason.AMOUNT_OUT_OF_RANGE: "El monto es demasiado grande.",
    RejectionReason.SAME_SENDER_AND_RECEIVER: "No puedes enviarte dinero a ti mismo.",
    RejectionReason.UNKNOWN_WALLET: "No encontramos a esa persona.",
    RejectionReason.BAD_SIGNATURE: "No pudimos autorizar el envío. Intenta de nuevo.",
    RejectionReason.INSUFFICIENT_FUNDS: "No tienes saldo suficiente para este envío.",
    RejectionReason.DUPLICATE_SIGNATURE: "Este envío ya se había hecho.",
}


def en_palabras(motivo: object) -> str:
    """El motivo de un rechazo como lo entiende cualquier persona."""
    texto = str(motivo)
    return MOTIVOS_EN_PALABRAS.get(texto, texto)

MENSAJE_CONTACTO_AGREGADO = "Agregaste a {nombre} a tus contactos."
MENSAJE_CONTACTO_QUITADO = "Lo sacaste de tus contactos."
MENSAJE_CONTACTO_YA_NO_ESTABA = "Ese contacto ya no estaba en tu agenda."

FabricaDeCadenas = Callable[[], AbstractContextManager[Blockchain]]
FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]


def crear_blueprint_del_usuario(
    abrir_cadena: FabricaDeCadenas, abrir_cuentas: FabricaDeCuentas
) -> Blueprint:
    """Arma las rutas del tablero con las fábricas que recibe de `create_app`."""
    tablero = Blueprint("usuario", __name__)

    @tablero.context_processor
    def palabras_del_usuario() -> dict[str, object]:
        """Lo que las plantillas del común necesitan para hablar sin tecnicismos.

        El saldo de bienvenida sale de la wallet del constituyente, que en una
        base sin semilla no tiene dueño: sin su identificador la fila diría
        «Sin dueño» en vez de «Saldo de bienvenida».
        """
        return {"en_palabras": en_palabras, "bienvenida_id": CONSTITUYENTE_ID}

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
            return _pintar_tablero(chain, resultado=resultado)

    @tablero.get("/mi-historial")
    @requiere_usuario_comun
    def mi_historial() -> str:
        """REQ-35 y REQ-39: el dictamen de la cadena y todo el historial propio.

        El dictamen es global —la cadena completa se verifica— pero la lista se
        filtra por la wallet de la sesión: de otros no se muestra ni el
        identificador de su transacción. Las confirmadas llevan el índice del
        bloque que las agrupa, que es lo que las vuelve verificables; con la cadena
        alterada la página lo dice aunque las filas sigan listadas.
        """
        wallet_id = _wallet_de_la_sesion()
        with abrir_cadena() as chain:
            return render_template(
                "mi_historial.html",
                dictamen=chain.verify_chain(),
                transacciones=chain.wallet_history(wallet_id),
                indices_de_bloque=_indices_de_bloque(chain),
                wallet_id=wallet_id,
            )

    @tablero.get("/mi-verificacion")
    @requiere_usuario_comun
    def mi_verificacion() -> Response:
        """La página se unificó en `/mi-historial` y el enlace guardado no se rompe.

        Se devuelve una redirección 302 y no un alias de la misma vista: el
        historial es una sola página y un enlace viejo tiene que llegar a ella.
        """
        return redirect(url_for("usuario.mi_historial"), code=302)

    @tablero.get("/mis-contactos")
    @requiere_usuario_comun
    def mis_contactos() -> str:
        """La agenda de la sesión, con los movimientos que tiene con cada contacto."""
        wallet_id = _wallet_de_la_sesion()
        with abrir_cuentas() as cuentas:
            agenda = cuentas.contactos(g.user.id)
        with abrir_cadena() as chain:
            historial = chain.wallet_history(wallet_id)
        return render_template(
            "mis_contactos.html",
            contactos=_contactos_con_movimientos(agenda, historial, wallet_id),
        )

    @tablero.get("/mis-contactos/sugerencias")
    @requiere_usuario_comun
    def sugerencias() -> str:
        """La vista previa de los campos de destinatario: quién coincide con lo tecleado.

        Devuelve el fragmento con la lista y no un JSON para que el avatar y el
        escapado salgan de las mismas plantillas que el resto de la página. Con
        `sin_contactos=1` —el campo de agregar contacto— no ofrece a quien ya está
        en la agenda, que el formulario rechazaría por repetido.
        """
        with abrir_cuentas() as cuentas:
            nombres = cuentas.sugerir_destinatarios(
                g.user.id,
                request.args.get("q", ""),
                sin_contactos=request.args.get("sin_contactos") == "1",
            )
        return render_template("_sugerencias.html", nombres=nombres)

    @tablero.post("/mis-contactos")
    @requiere_usuario_comun
    def agregar_contacto() -> Response:
        """Agenda por nombre de usuario y vuelve a la agenda con el resultado.

        Se responde con redirección y aviso, como la cola del administrador: así
        recargar la página no vuelve a mandar el formulario.
        """
        nombre = request.form.get("usuario", "")
        with abrir_cuentas() as cuentas:
            try:
                contacto = cuentas.agregar_contacto(g.user.id, nombre)
            except ContactoInvalido as error:
                flash(str(error), "aviso")
            else:
                flash(MENSAJE_CONTACTO_AGREGADO.format(nombre=contacto.username), "exito")
        return redirect(url_for("usuario.mis_contactos"))

    @tablero.post("/mis-contactos/<identificador>/quitar")
    @requiere_usuario_comun
    def quitar_contacto(identificador: str) -> Response:
        """Saca a alguien de la agenda de la sesión; la de otros no se puede tocar.

        El dueño de la agenda sale de la sesión y nunca de la ruta, igual que el
        emisor de un envío: la ruta sólo dice a quién sacar.
        """
        contacto_id = a_uuid(identificador)
        if contacto_id is None:
            abort(404, description="Ese contacto no existe.")
        with abrir_cuentas() as cuentas:
            if cuentas.quitar_contacto(g.user.id, contacto_id):
                flash(MENSAJE_CONTACTO_QUITADO, "exito")
            else:
                flash(MENSAJE_CONTACTO_YA_NO_ESTABA, "aviso")
        return redirect(url_for("usuario.mis_contactos"))

    return tablero


@dataclass(frozen=True, slots=True)
class ContactoConMovimientos:
    """Un contacto de la agenda y lo que la wallet de la sesión movió con él."""

    usuario: Usuario
    movimientos: int
    ultimo: datetime | None


def _contactos_con_movimientos(
    agenda: Sequence[Usuario], historial: Sequence[Transaction], propia: UUID
) -> list[ContactoConMovimientos]:
    """Cuenta, para cada contacto, las transacciones propias en que es la contraparte.

    El historial ya viene filtrado por la wallet de la sesión y de la más nueva a
    la más vieja, así que la primera que aparece de cada contraparte es la última.
    """
    por_contraparte: dict[UUID, list[Transaction]] = {}
    for transaction in historial:
        otra = transaction.receiver_id if transaction.sender_id == propia else transaction.sender_id
        por_contraparte.setdefault(otra, []).append(transaction)
    resultado = []
    for usuario in agenda:
        comunes = por_contraparte.get(usuario.wallet_id, [])
        resultado.append(
            ContactoConMovimientos(
                usuario=usuario,
                movimientos=len(comunes),
                ultimo=comunes[0].created_at if comunes else None,
            )
        )
    return resultado


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


def _indices_de_bloque(chain: Blockchain) -> dict[UUID, int]:
    """El índice de cada bloque, por identificador, para la tabla del historial.

    La transacción guarda el identificador del bloque y no su índice; el índice es
    el dato que la persona puede comparar con la cadena. Se arma con la lista de la
    fachada, que ya viene ordenada del génesis al último bloque (REQ-07).
    """
    return {block.id: block.block_index for block in chain.blocks.list()}


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
) -> str:
    """Pinta el tablero con la wallet de la sesión y lo que el ledger tiene de ella.

    El saldo es el disponible real de la fachada —el mismo que usa el envío para
    decidir—, y el historial se filtra por la wallet de la sesión. La lista de
    movimientos vive en Mi historial; acá el historial sólo alimenta lo que no se
    ve en otra pestaña: el resumen del mes y con quién se mueve más la persona.
    No se pasa el panel lateral de `base.html`: esa lista es de la portada del
    administrador y mostraría las wallets de otros, que es justo lo que REQ-35
    prohíbe.
    """
    wallet_id = _wallet_de_la_sesion()
    historial = chain.wallet_history(wallet_id)
    return render_template(
        "tablero.html",
        wallet_id=wallet_id,
        saldo=chain.available_balance(wallet_id),
        transacciones=historial,
        resumen=_resumen_del_mes(historial, wallet_id, datetime.now(UTC)),
        personas=_con_quien_mas(historial, wallet_id),
        resultado=resultado,
        error_formulario=error_formulario,
    )


MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


@dataclass(frozen=True, slots=True)
class ResumenDelMes:
    """Lo que entró y salió de la wallet en el mes en curso, sólo lo completado."""

    mes: str
    recibido: Decimal
    enviado: Decimal
    recepciones: int
    envios: int

    @property
    def diferencia(self) -> Decimal:
        return self.recibido - self.enviado


@dataclass(frozen=True, slots=True)
class PersonaFrecuente:
    """Una contraparte y cuántos movimientos tiene con la wallet de la sesión."""

    wallet_id: UUID
    movimientos: int


def _resumen_del_mes(
    historial: Sequence[Transaction], propia: UUID, ahora: datetime
) -> ResumenDelMes:
    """Suma lo completado del mes de `ahora`: lo que está en espera ya lo cuenta la
    tarjeta del saldo y lo rechazado nunca movió dinero."""
    recibido = enviado = Decimal(0)
    recepciones = envios = 0
    for transaction in historial:
        momento = transaction.created_at.astimezone(UTC)
        if transaction.status is not TransactionStatus.CONFIRMED or (
            (momento.year, momento.month) != (ahora.year, ahora.month)
        ):
            continue
        if transaction.sender_id == propia:
            enviado += transaction.amount
            envios += 1
        else:
            recibido += transaction.amount
            recepciones += 1
    return ResumenDelMes(
        mes=MESES[ahora.month - 1],
        recibido=recibido,
        enviado=enviado,
        recepciones=recepciones,
        envios=envios,
    )


def _con_quien_mas(
    historial: Sequence[Transaction], propia: UUID
) -> list[PersonaFrecuente]:
    """Las contrapartes ordenadas de la que más movimientos tiene a la que menos.

    No cuenta lo rechazado ni el saldo de bienvenida: ninguno de los dos es un
    intercambio con otra persona. La plantilla decide cuántas mostrar y salta las
    wallets sin dueño, que no tienen nombre al que enviar.
    """
    cuentas: dict[UUID, int] = {}
    for transaction in historial:
        if transaction.status is TransactionStatus.REJECTED:
            continue
        otra = transaction.receiver_id if transaction.sender_id == propia else transaction.sender_id
        if otra == CONSTITUYENTE_ID:
            continue
        cuentas[otra] = cuentas.get(otra, 0) + 1
    return [
        PersonaFrecuente(wallet_id=wallet_id, movimientos=movimientos)
        for wallet_id, movimientos in sorted(cuentas.items(), key=lambda par: -par[1])
    ]
