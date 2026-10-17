"""REQ-33: el dominio acredita el saldo de bienvenida en un bloque propio.

La emisión es la única operación que no pasa por la regla de saldo: el
constituyente es la puerta por la que el capital entra al ledger y puede quedar
más negativo. El crédito se confirma en un bloque propio porque el saldo
disponible sólo cuenta lo confirmado. Corre sin base (REQ-17), sobre los dobles
de `tests/dobles.py`.
"""
from decimal import Decimal

from cryptography.fernet import Fernet

from src.domain.blockchain import ensure_genesis
from src.domain.transaction import TransactionStatus
from src.domain.wallet import create_wallet, verify
from src.emision import CONSTITUYENTE_ID, SALDO_DE_BIENVENIDA
from tests.dobles import build_chain


def _cadena_con_wallets(master_key: bytes):
    """Ledger en memoria con el constituyente, un destino y el génesis ya puesto."""
    chain = build_chain(master_key=master_key)
    emisor = chain.wallets.add(
        create_wallet(master_key=master_key, wallet_id=CONSTITUYENTE_ID)
    )
    destino = chain.wallets.add(create_wallet(master_key=master_key))
    genesis = ensure_genesis(chain)
    return chain, emisor, destino, genesis


def test_req_33_acreditar_sube_el_saldo_del_destino_y_baja_el_del_emisor():
    """Criterio: el destino queda con 1000 disponibles y la cadena sigue verificando.

    El emisor termina con 1000 más negativo y el bloque del crédito tiene una sola
    transacción, confirmada y ligada a ese bloque.
    """
    master_key = Fernet.generate_key()
    chain, emisor, destino, genesis = _cadena_con_wallets(master_key)

    bloque = chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )

    assert chain.available_balance(destino.id) == SALDO_DE_BIENVENIDA
    assert chain.available_balance(emisor.id) == -SALDO_DE_BIENVENIDA
    assert chain.verify_chain().valid is True

    filas = chain.transactions.of_block(bloque.id)
    assert len(filas) == 1
    credito = filas[0]
    assert credito.status is TransactionStatus.CONFIRMED
    assert credito.block_id == bloque.id
    assert credito.amount == SALDO_DE_BIENVENIDA
    assert bloque.block_index == genesis.block_index + 1
    assert bloque.previous_hash == genesis.hash
    assert bloque.calculate_hash(filas) == bloque.hash


def test_req_33_la_firma_del_credito_es_la_del_emisor():
    """La firma se calcula como la de cualquier transacción y valida contra su emisor.

    `validate` recibe un saldo ficticio a favor del emisor para aislar la firma y el
    formato de la regla de saldo: lo que esta prueba mide es que la fila de la
    emisión no es una marca sino una transacción firmada de verdad.
    """
    master_key = Fernet.generate_key()
    chain, emisor, destino, _ = _cadena_con_wallets(master_key)

    bloque = chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )
    credito = chain.transactions.of_block(bloque.id)[0]

    assert credito.signature, "el crédito tiene que llevar firma, no una marca"
    assert verify(
        emisor.public_key,
        credito.signature,
        credito.signing_payload(emisor.public_key, destino.public_key),
    )
    assert credito.validate(
        sender_public_key=emisor.public_key,
        receiver_public_key=destino.public_key,
        available=SALDO_DE_BIENVENIDA,
        signature_exists=False,
    ).accepted is True


def test_req_33_la_emision_no_arrastra_las_pendientes():
    """Criterio: el bloque del crédito tiene una sola transacción aunque haya pool.

    La transacción pendiente sigue pendiente y el crédito se confirma en su propio
    eslabón, que es lo que permite acreditar sin agrupar lo que haya en el pool.
    """
    master_key = Fernet.generate_key()
    chain, emisor, destino, _ = _cadena_con_wallets(master_key)
    chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )
    pendiente = chain.create_transaction(
        sender_id=destino.id,
        receiver_id=emisor.id,
        amount=Decimal("10.00000000"),
    )
    assert pendiente.accepted is True
    assert pendiente.stored is not None

    bloque = chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )

    filas = chain.transactions.of_block(bloque.id)
    assert len(filas) == 1
    assert filas[0].sender_id == CONSTITUYENTE_ID
    assert [t.id for t in chain.transactions.pending()] == [pendiente.stored.id]
    assert chain.verify_chain().valid is True
    assert chain.blocks.count() == 3
