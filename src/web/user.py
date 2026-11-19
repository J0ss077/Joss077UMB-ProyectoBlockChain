"""El tablero del usuario común: envío, historial y verificación propios.

Tres rutas con una sola regla de alcance (REQ-34, REQ-35, REQ-39): el emisor de un
envío sale de la sesión y nunca del formulario, el historial y la verificación se
filtran por la wallet de la sesión, y el administrador que entra acá vuelve a su
portada. El destinatario se resuelve primero como nombre de usuario y después como
identificador de wallet, que es el orden que fija el diseño (decisión 4).

Una cuenta común puede tener varias wallets (REQ-41): la que usa la sesión es la
elegida en el tablero, guardada con `wallet_elegida` en la cookie; si no hay
elección, o la guardada ya no pertenece a la cuenta, se usa la principal, que es
la más antigua. `POST /mi-wallet` valida y guarda la elección. El envío por nombre
de usuario apunta a la wallet principal del destinatario —las demás sólo por su
identificador— y la agenda compara cada contacto contra su principal.

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
    session,
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
MENSAJE_WALLET_ELEGIDA = "Wallet elegida."

# La clave de la cookie que recuerda cuál de las wallets de la cuenta se está
# usando (REQ-41). Guarda el identificador como texto, igual que la de la sesión:
# nunca se confía en lo que trae sin contrastarlo con `Cuentas.wallets_de`.
CLAVE_DE_LA_WALLET_ELEGIDA = "wallet_elegida"

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
        with abrir_cuentas() as cuentas:
            wallets = _wallets_de_la_sesion(cuentas)
            wallet_id = _wallet_de_la_sesion(cuentas, wallets)
        with abrir_cadena() as chain:
            return _pintar_tablero(chain, wallets, wallet_id)

    @tablero.post("/mi-envio")
    @requiere_usuario_comun
    def mi_envio() -> str:
        """REQ-34: propone un envío desde la wallet elegida y nunca desde otra.

        El emisor es la wallet de la sesión —la elegida en el tablero o, si no hay
        elección, la principal—: si el formulario trae un `sender_id`, no se lee.
        El destinatario se resuelve primero por nombre de usuario —que es único y
        apunta a su wallet principal— y después por el identificador de la wallet.
        Un destinatario que no existe se informa antes de llegar al dominio porque
        no hay wallet con la que firmar; el resto de los rechazos los decide
        `create_transaction` y su motivo se muestra sin traducir.
        """
        destinatario = request.form.get("destinatario", "")
        with abrir_cuentas() as cuentas:
            wallets = _wallets_de_la_sesion(cuentas)
            wallet_propia = _wallet_de_la_sesion(cuentas, wallets)
            wallet_destino = _wallet_del_destinatario(cuentas, destinatario)
        with abrir_cadena() as chain:
            if wallet_destino is None:
                return _pintar_tablero(
                    chain,
                    wallets,
                    wallet_propia,
                    error_formulario=MENSAJE_DESTINATARIO_INEXISTENTE,
                )
            resultado = chain.create_transaction(
                sender_id=wallet_propia,
                receiver_id=wallet_destino,
                amount=a_monto(request.form.get("amount")),
            )
            return _pintar_tablero(chain, wallets, wallet_propia, resultado=resultado)

    @tablero.post("/mi-wallet")
    @requiere_usuario_comun
    def elegir_wallet() -> Response:
        """REQ-41: cambia la wallet con la que opera la sesión.

        La wallet tiene que ser una de las de la cuenta; una de otra, un
        identificador mal escrito o uno inexistente se descartan sin guardar y sin
        contar nada de su existencia. Igual que `/idioma`, sólo se vuelve a una ruta
        propia: un `volver` que no empiece por una sola barra se descarta para que el
        formulario no sirva de redirección abierta.
        """
        elegida = a_uuid(request.form.get("wallet"))
        with abrir_cuentas() as cuentas:
            wallets = _wallets_de_la_sesion(cuentas)
        if elegida is not None and elegida in wallets:
            session[CLAVE_DE_LA_WALLET_ELEGIDA] = str(elegida)
            flash(MENSAJE_WALLET_ELEGIDA, "exito")
        volver = request.form.get("volver", "")
        if not volver.startswith("/") or volver.startswith("//"):
            volver = url_for("usuario.mi_tablero")
        return redirect(volver)

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
        with abrir_cuentas() as cuentas:
            wallet_id = _wallet_de_la_sesion(cuentas)
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
        with abrir_cuentas() as cuentas:
            agenda = cuentas.contactos(g.user.id)
            wallet_id = _wallet_de_la_sesion(cuentas)
            with abrir_cadena() as chain:
                historial = chain.wallet_history(wallet_id)
            contactos = _contactos_con_movimientos(agenda, historial, wallet_id, cuentas)
        return render_template("mis_contactos.html", contactos=contactos)

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


@dataclass(frozen=True, slots=True)
class WalletDeLaSesion:
    """Una wallet de la cuenta con su saldo, para el selector de «Tus wallets»."""

    id: UUID
    saldo: Decimal


def _contactos_con_movimientos(
    agenda: Sequence[Usuario],
    historial: Sequence[Transaction],
    propia: UUID,
    cuentas: Cuentas,
) -> list[ContactoConMovimientos]:
    """Cuenta, para cada contacto, las transacciones propias en que es la contraparte.

    El historial ya viene filtrado por la wallet de la sesión y de la más nueva a
    la más vieja, así que la primera que aparece de cada contraparte es la última.
    El envío por nombre apunta a la wallet principal del contacto, así que es esa
    la que se compara: con una segunda wallet del contacto no se movió nada.
    """
    por_contraparte: dict[UUID, list[Transaction]] = {}
    for transaction in historial:
        otra = transaction.receiver_id if transaction.sender_id == propia else transaction.sender_id
        por_contraparte.setdefault(otra, []).append(transaction)
    resultado = []
    for usuario in agenda:
        principal = cuentas.wallet_principal(usuario.id)
        comunes = por_contraparte.get(principal, []) if principal is not None else []
        resultado.append(
            ContactoConMovimientos(
                usuario=usuario,
                movimientos=len(comunes),
                ultimo=comunes[0].created_at if comunes else None,
            )
        )
    return resultado


def _wallets_de_la_sesion(cuentas: Cuentas) -> Sequence[UUID]:
    """Las wallets de la cuenta de la sesión, de la principal a la más nueva (REQ-41)."""
    return cuentas.wallets_de(g.user.id)


def _wallet_de_la_sesion(
    cuentas: Cuentas, wallets: Sequence[UUID] | None = None
) -> UUID:
    """La wallet con la que opera la sesión (REQ-34, REQ-41).

    Es la elegida en el tablero si sigue perteneciendo a la cuenta y, si no —sin
    elección, con una cookie manipulada o con una wallet que otro ya no le
    reconoce—, la principal: la más antigua. `wallets` se puede pasar ya leído para
    no repetir la consulta. Sin wallets la falta es un estado imposible de una
    cuenta aprobada, así que la respuesta es 403 y no una consulta con `None`.
    """
    if wallets is None:
        wallets = _wallets_de_la_sesion(cuentas)
    if not wallets:
        abort(403)
    elegida = session.get(CLAVE_DE_LA_WALLET_ELEGIDA)
    if isinstance(elegida, str):
        try:
            guardada = UUID(elegida)
        except ValueError:
            guardada = None
        if guardada in wallets:
            return guardada
    return wallets[0]


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
    normal y el identificador es el atajo de quien lo tiene a mano. Un nombre
    apunta a la wallet principal del destinatario (decisión 6); sus demás wallets
    sólo se alcanzan por su identificador. Un nombre que no existe todavía puede
    ser un identificador escrito a mano, así que se intenta interpretar como UUID;
    si tampoco lo es, la ruta informa el rechazo sin consultar el ledger. Una
    cuenta sin wallet (pendiente o rechazada) no puede recibir y cae por el mismo
    camino que un nombre inexistente.
    """
    texto = destinatario.strip()
    if not texto:
        return None
    usuario = cuentas.por_username(texto)
    if usuario is not None:
        principal = cuentas.wallet_principal(usuario.id)
        if principal is not None:
            return principal
    return a_uuid(texto)


def _pintar_tablero(
    chain: Blockchain,
    wallets: Sequence[UUID],
    wallet_id: UUID,
    *,
    resultado: TransactionResult | None = None,
    error_formulario: str | None = None,
) -> str:
    """Pinta el tablero con la wallet elegida y lo que el ledger tiene de ella.

    El saldo es el disponible real de la fachada —el mismo que usa el envío para
    decidir—, y el historial se filtra por la wallet elegida. La lista de
    movimientos vive en Mi historial; acá el historial sólo alimenta lo que no se
    ve en otra pestaña: el resumen del mes y con quién se mueve más la persona.
    El selector de «Tus wallets» sólo se pinta cuando la cuenta tiene más de una,
    y lleva el saldo de cada una para poder elegir con la información a la vista.
    No se pasa el panel lateral de `base.html`: esa lista es de la portada del
    administrador y mostraría las wallets de otros, que es justo lo que REQ-35
    prohíbe.
    """
    historial = chain.wallet_history(wallet_id)
    return render_template(
        "tablero.html",
        wallet_id=wallet_id,
        wallets=[
            WalletDeLaSesion(id=wallet, saldo=chain.available_balance(wallet))
            for wallet in wallets
        ],
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
