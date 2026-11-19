"""Dobles nuevos de persistencia: lectura completa, rechazo y reescritura de hashes.

La auditoría y las reparaciones necesitan leer todas las transacciones de una sola
vez, pasar filas a `rejected` sin bloque y reescribir los dos hashes de un bloque.
Estas pruebas fijan esos tres contratos sobre los dobles de `tests/dobles.py` y que
`build_chain` siembre las wallets que recibe, sin base de datos (REQ-17).
"""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from cryptography.fernet import Fernet

from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import create_wallet
from tests.dobles import BLOCK_AT, build_block, build_chain


def _fila(
    *,
    status: TransactionStatus = TransactionStatus.PENDING,
    block_id=None,
    created_at=BLOCK_AT,
    signature: str = "firma-de-prueba",
) -> Transaction:
    """Fila con el estado y el bloque que la prueba necesite; no se firma de verdad."""
    return Transaction(
        id=uuid4(),
        sender_id=uuid4(),
        receiver_id=uuid4(),
        amount=Decimal("1.00000000"),
        status=status,
        signature=signature,
        block_id=block_id,
        created_at=created_at,
    )


def test_all_devuelve_todas_las_filas_y_reject_las_pasa_a_rechazadas():
    """`all` lee el pool y las confirmadas; `reject` deja la fila rechazada y sin bloque."""
    genesis = build_block(0)
    pendiente = _fila(created_at=BLOCK_AT + timedelta(minutes=1))
    confirmada = _fila(status=TransactionStatus.CONFIRMED, block_id=genesis.id)
    chain = build_chain(blocks=[genesis], transactions=[pendiente, confirmada])

    assert len(chain.transactions.all()) == 2
    assert chain.transactions.reject([pendiente.id]) == 1

    rechazada = chain.transactions.get(pendiente.id)
    assert rechazada is not None
    assert rechazada.status is TransactionStatus.REJECTED
    assert rechazada.block_id is None
    # La confirmada que no estaba en la lista queda como estaba.
    assert chain.transactions.get(confirmada.id).status is TransactionStatus.CONFIRMED


def test_all_ordena_por_creacion_e_identificador():
    """El orden de `all` es el de la consulta real: la más vieja primero y el id desempata."""
    primera = _fila(created_at=BLOCK_AT)
    segunda = _fila(created_at=BLOCK_AT + timedelta(minutes=1))
    # Se guardan al revés a propósito: el orden lo tiene que poner el método, no la lista.
    chain = build_chain(transactions=[segunda, primera])

    assert list(chain.transactions.all()) == [primera, segunda]


def test_reject_tambien_limpia_el_bloque_de_una_confirmada():
    """Pasar a rechazada una confirmada le quita el bloque, como exige REQ-12."""
    genesis = build_block(0)
    confirmada = _fila(status=TransactionStatus.CONFIRMED, block_id=genesis.id)
    chain = build_chain(blocks=[genesis], transactions=[confirmada])

    assert chain.transactions.reject([confirmada.id]) == 1
    assert chain.transactions.get(confirmada.id).block_id is None


def test_reject_cuenta_solo_las_filas_que_existen():
    """El valor devuelto es el número de filas tocadas, no el largo de la lista."""
    pendiente = _fila()
    chain = build_chain(transactions=[pendiente])

    assert chain.transactions.reject([pendiente.id, uuid4()]) == 1


def test_reject_sin_identificadores_devuelve_cero():
    """Una lista vacía no cambia nada y devuelve cero."""
    pendiente = _fila()
    chain = build_chain(transactions=[pendiente])

    assert chain.transactions.reject([]) == 0
    assert chain.transactions.get(pendiente.id).status is TransactionStatus.PENDING


def test_set_hashes_actualiza_los_dos_hashes_del_bloque():
    """`set_hashes` deja en la fila el `previous_hash` y el `hash` del bloque recibido."""
    genesis = build_block(0)
    chain = build_chain(blocks=[genesis])
    nuevo = replace(genesis, previous_hash="f" * 64, hash="e" * 64)

    escrito = chain.blocks.set_hashes(nuevo)

    assert escrito.hash == "e" * 64
    assert escrito.previous_hash == "f" * 64
    assert chain.blocks.get_by_index(0).hash == "e" * 64


def test_set_hashes_conserva_identificador_indice_y_marca_de_tiempo():
    """Reescribir los hashes no toca la identidad ni el instante del bloque."""
    genesis = build_block(0)
    chain = build_chain(blocks=[genesis])
    nuevo = replace(genesis, previous_hash="f" * 64, hash="e" * 64)

    escrito = chain.blocks.set_hashes(nuevo)

    assert escrito.id == genesis.id
    assert escrito.block_index == genesis.block_index == 0
    assert escrito.timestamp == genesis.timestamp == BLOCK_AT
    assert list(chain.blocks.list()) == [escrito]


def test_build_chain_registra_las_wallets_recibidas():
    """`build_chain` siembra el repositorio de wallets con la lista que recibe."""
    clave = Fernet.generate_key()
    emisora = create_wallet(master_key=clave)
    receptora = create_wallet(master_key=clave)

    chain = build_chain(wallets=[emisora, receptora])

    assert chain.wallets.count() == 2
    assert chain.wallets.get(emisora.id) == emisora
    assert chain.wallets.get(receptora.id) == receptora


def test_build_chain_sin_wallets_las_deja_vacias():
    """Las llamadas que ya existían siguen sin sembrar wallets."""
    assert build_chain().wallets.count() == 0
