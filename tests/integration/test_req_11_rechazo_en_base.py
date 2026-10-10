"""REQ-11: rechazar una transacción inválida dejándola en `rejected`, sin bloque.

La fila rechazada se guarda con `block_id` nulo y nunca entra a un bloque; el
esquema es el que impide lo contrario con su CHECK de coherencia entre estado y
bloque (REQ-12), cuyos dos lados se provocan aquí. En el ledger, además, la fila
`rejected` solo se escribe cuando el esquema la admite: los motivos que el propio
esquema ya impide —monto no positivo, emisor igual al receptor, wallet
inexistente y firma repetida— se informan sin escribir, como manda la sección
"Conducta observable ante una transacción inválida" del diseño.
"""
import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from src.domain import blockchain
from src.domain.transaction import RejectionReason, TransactionStatus
from src.persistence.postgres import PostgresTransactionRepository

# Identificador y marca de tiempo fijos: la firma canónica los incluye, así que
# repetirlos es la forma de repetir la firma sin tocar la criptografía.
CREATED_AT = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
FIXED_ID = UUID("00000000-0000-4000-8000-000000000011")


@pytest.fixture
def transacciones(conexion):
    """El repositorio de transacciones contra la conexión de la sesión."""
    return PostgresTransactionRepository(conexion)


@pytest.fixture
def emisora_fondeada(ledger, emisora, receptora, transaccion):
    """Emisora con saldo confirmado: sin fondos, toda transacción saliente se rechaza.

    El ingreso se confirma por el camino real —se escribe pendiente y se agrupa—
    para que el saldo salga de `balance_terms` y no de un número inventado.
    """
    ledger.transactions.add(
        transaccion(sender=receptora, receiver=emisora, amount=Decimal("100.00000000"))
    )
    ledger.group_pending()
    return emisora


def test_req_11_una_rechazada_se_guarda_con_block_id_nulo(transacciones, base_limpia, transaccion):
    """La transacción inválida queda en `rejected`, sin bloque, y no entra al pool."""
    firmada = transaccion(status=TransactionStatus.REJECTED, block_id=None)

    guardada = transacciones.add(firmada)

    assert guardada.status is TransactionStatus.REJECTED
    assert guardada.block_id is None
    assert transacciones.pending() == []
    assert transacciones.count() == 1


def test_req_11_una_confirmada_sin_bloque_levanta_check_violation(
    transacciones, base_limpia, transaccion
):
    """El esquema no admite una confirmada sin bloque: el estado y el bloque van juntos."""
    sin_bloque = transaccion(status=TransactionStatus.CONFIRMED, block_id=None)

    with pytest.raises(psycopg.errors.CheckViolation):
        transacciones.add(sin_bloque)

    assert transacciones.count() == 0


def test_req_11_una_pendiente_con_bloque_levanta_check_violation(
    transacciones, base_limpia, transaccion, bloque
):
    """El otro lado de la coherencia: una pendiente tampoco puede traer bloque."""
    pendiente_con_bloque = transaccion(block_id=bloque().id)

    with pytest.raises(psycopg.errors.CheckViolation):
        transacciones.add(pendiente_con_bloque)

    assert transacciones.count() == 0


def test_req_11_la_transaccion_valida_queda_pendiente_en_el_pool(
    ledger, emisora_fondeada, receptora
):
    """El camino válido guarda la fila como `pending`, sin bloque, dentro del pool."""
    resultado = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("25.00000000"),
    )

    assert resultado.accepted is True
    assert resultado.reason is None
    assert resultado.stored is not None
    assert resultado.stored.status is TransactionStatus.PENDING
    assert resultado.stored.block_id is None
    assert [fila.id for fila in ledger.transactions.pending()] == [resultado.stored.id]


def test_req_11_el_saldo_insuficiente_se_guarda_como_rejected(ledger, emisora, receptora):
    """El saldo insuficiente cabe en el esquema, así que la fila queda en `rejected`."""
    resultado = ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
    )

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.INSUFFICIENT_FUNDS
    assert resultado.stored is not None
    assert resultado.stored.status is TransactionStatus.REJECTED
    assert resultado.stored.block_id is None
    assert ledger.transactions.pending() == []
    assert ledger.transactions.count() == 1


def test_req_06_dos_transacciones_que_juntas_exceden_no_entran_las_dos(
    ledger, emisora_fondeada, receptora
):
    """REQ-06: dos transacciones que por separado caben pero juntas exceden no entran las dos.

    El saldo disponible descuenta lo que la primera comprometió en el pool, así que la
    segunda se rechaza por saldo; se comprueba por los dos caminos reales de
    `create_transaction` y no con un `BalanceTerms` armado a mano.
    """
    primera = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("60.00000000"),
    )
    segunda = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("60.00000000"),
    )

    assert primera.accepted is True
    assert segunda.accepted is False
    assert segunda.reason is RejectionReason.INSUFFICIENT_FUNDS
    assert segunda.stored is not None
    assert segunda.stored.status is TransactionStatus.REJECTED
    # La primera comprometió 60 de los 100 confirmados; la rechazada no cuenta.
    assert ledger.available_balance(emisora_fondeada.id) == Decimal("40.00000000")
    assert [fila.id for fila in ledger.transactions.pending()] == [primera.stored.id]


def test_req_11_el_monto_no_positivo_se_informa_sin_fila(ledger, emisora, receptora):
    """El CHECK del monto lo impide: el rechazo se informa sin escribir."""
    resultado = ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=receptora.id,
        amount=Decimal("0"),
    )

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.AMOUNT_NOT_POSITIVE
    assert resultado.stored is None
    assert ledger.transactions.count() == 0


def test_req_11_el_emisor_igual_al_receptor_se_informa_sin_fila(ledger, emisora):
    """El CHECK del emisor distinto del receptor lo impide: se informa sin escribir."""
    resultado = ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=emisora.id,
        amount=Decimal("1.00000000"),
    )

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.SAME_SENDER_AND_RECEIVER
    assert resultado.stored is None
    assert ledger.transactions.count() == 0


def test_req_11_la_wallet_inexistente_se_informa_sin_fila(ledger, emisora):
    """La clave foránea la impide: se informa sin escribir y sin dejar el motivo en la base."""
    resultado = ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=uuid4(),
        amount=Decimal("1.00000000"),
    )

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.UNKNOWN_WALLET
    assert resultado.stored is None
    assert ledger.transactions.count() == 0


def test_req_11_la_firma_repetida_se_informa_sin_fila(
    ledger, emisora_fondeada, receptora, monkeypatch
):
    """El motivo sale del dominio y la repetición no deja fila.

    La firma ECDSA no es determinista, así que el mismo envío produce firmas
    distintas y esta rama no se alcanzaría sola: se fija el valor que devuelve el
    firmante. La repetición reusa el identificador y la firma, así que su forma
    canónica es la misma y la firma verifica; el saldo alcanza, de modo que la regla
    que decide es la de la firma repetida, y como ese motivo no cabe en una fila
    `rejected`, el rechazo se informa sin escribir.
    """
    presentada = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
        transaction_id=FIXED_ID,
        created_at=CREATED_AT,
    )
    assert presentada.accepted is True
    assert presentada.stored is not None

    monkeypatch.setattr(
        blockchain, "sign_payload", lambda wallet, payload, key: presentada.stored.signature
    )
    repetida = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
        transaction_id=FIXED_ID,
        created_at=CREATED_AT,
    )

    assert repetida.accepted is False
    assert repetida.reason is RejectionReason.DUPLICATE_SIGNATURE
    assert repetida.stored is None
    # El ingreso confirmado de la emisora y la primera transacción: la repetición
    # no agrega fila.
    assert ledger.transactions.count() == 2


def test_req_11_la_firma_repetida_con_saldo_insuficiente_no_llega_al_motor(
    ledger, emisora_fondeada, receptora, transaccion, monkeypatch
):
    """Firma repetida y saldo insuficiente: se informa el motivo y no la violación del índice.

    El orden de las reglas lo fija el diseño y mira el saldo antes que la firma
    repetida, así que este caso llega a la validación como INSUFFICIENT_FUNDS; con
    esa respuesta el ledger escribiría una fila `rejected`, y el escape de la firma
    repetida evita que choque con el índice único. La repetición lleva un
    identificador nuevo a propósito: lo único que puede colisionar es esa firma, y no
    la clave primaria. Se fija el valor que devuelve el firmante porque la ECDSA no
    reproduce su propia firma.
    """
    # La firma que la repetición va a presentar ya tiene que estar en la tabla, y se
    # firma con el identificador de la repetición para que verifique. La fila se
    # escribe con otro identificador porque lo que la tabla aporta aquí es la firma ya
    # vista, no una fila que el camino de la aplicación hubiera producido: ese camino
    # nunca repite una firma.
    identificador_repetido = uuid4()
    presentada = transaccion(
        sender=emisora_fondeada,
        receiver=receptora,
        amount=Decimal("1.00000000"),
        created_at=CREATED_AT,
        transaction_id=identificador_repetido,
    )
    ledger.transactions.add(dataclasses.replace(presentada, id=FIXED_ID))
    # Una pendiente que agota el disponible: el saldo se revisa antes que la firma.
    ledger.transactions.add(
        transaccion(sender=emisora_fondeada, amount=Decimal("100.00000000"))
    )

    monkeypatch.setattr(
        blockchain, "sign_payload", lambda wallet, payload, key: presentada.signature
    )
    repetida = ledger.create_transaction(
        sender_id=emisora_fondeada.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
        transaction_id=identificador_repetido,
        created_at=CREATED_AT,
    )

    assert repetida.accepted is False
    assert repetida.reason is RejectionReason.DUPLICATE_SIGNATURE
    assert repetida.stored is None
    # El ingreso confirmado, la fila presentada y la pendiente que agotó el saldo: la
    # repetición no agrega fila.
    assert ledger.transactions.count() == 3
