"""Reparaciones guiadas de la fachada: reencadenar, aislar y rechazar el pool.

Cada prueba arma la cadena sobre los dobles de `tests/dobles.py`, la rompe de una
forma concreta y exige que la reparación deje el estado coherente sin tocar índices
ni marcas de tiempo. También se prueban las funciones puras de
`src.domain.reparacion` sin pasar por la fachada. Corre sin base de datos (REQ-17).
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.reparacion import (
    agrupar_por_bloque,
    esta_desencajada,
    motivo_de_invalidez,
    recalcular_cadena,
    se_puede_reencadenar,
)
from src.domain.transaction import RejectionReason, Transaction, TransactionStatus
from src.domain.wallet import create_wallet, sign_payload
from tests.dobles import BLOCK_AT, build_block, build_chain

# Una sola clave maestra para toda la prueba: las wallets y las firmas se arman con
# ella, así que la revalidación mide el estado del ledger y no la clave.
MASTER_KEY = Fernet.generate_key()


@pytest.fixture
def wallets():
    """Una emisora y una receptora con la clave maestra con la que se firma."""
    return {
        "emisora": create_wallet(master_key=MASTER_KEY),
        "receptora": create_wallet(master_key=MASTER_KEY),
    }


def _chain(wallets, *, blocks=(), transactions=()):
    """Ledger sobre dobles con las dos wallets registradas y la cadena que se le pase."""
    return build_chain(
        blocks=blocks,
        transactions=transactions,
        wallets=[wallets["emisora"], wallets["receptora"]],
        master_key=MASTER_KEY,
    )


def _transaccion(
    wallets,
    *,
    status: TransactionStatus = TransactionStatus.PENDING,
    block_id=None,
    amount: Decimal = Decimal("10.00000000"),
    sender_id=None,
    receiver_id=None,
) -> Transaction:
    """Transacción firmada por la emisora con los valores que pida la prueba."""
    emisora = wallets["emisora"]
    receptora = wallets["receptora"]
    transaction = Transaction(
        id=uuid4(),
        sender_id=emisora.id if sender_id is None else sender_id,
        receiver_id=receptora.id if receiver_id is None else receiver_id,
        amount=amount,
        status=status,
        signature="",
        block_id=block_id,
        created_at=BLOCK_AT,
    )
    transaction.signature = sign_payload(
        emisora,
        transaction.signing_payload(emisora.public_key, receptora.public_key),
        MASTER_KEY,
    )
    return transaction


def _cadena_valida(wallets, *, pendientes=()):
    """Génesis y un bloque con una confirmada bien firmada; opcionalmente, el pool."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    genesis = build_block(0)
    bloque = build_block(1, genesis, transactions=[confirmada])
    confirmada.block_id = bloque.id
    chain = _chain(
        wallets,
        blocks=[genesis, bloque],
        transactions=[confirmada, *pendientes],
    )
    return chain, genesis, bloque, confirmada


def _foto(chain):
    """Estado observable de la cadena, para comparar que una reparación no escribió."""
    return (
        [(b.block_index, b.timestamp, b.previous_hash, b.hash) for b in chain.blocks.rows],
        [(t.id, t.status, t.block_id, t.signature, t.amount) for t in chain.transactions.rows],
    )


def test_reencadenar_deja_la_cadena_valida_despues_de_alterar_un_hash(wallets):
    """Un hash guardado a mano se corrige recalculando el bloque y su encadenamiento."""
    chain, genesis, bloque, confirmada = _cadena_valida(wallets)
    bloque.hash = "f" * 64
    assert chain.audit_chain().resumen.valida is False

    reparacion = chain.repair_chain()

    assert reparacion.accion == "encadenar"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert bloque.hash == bloque.calculate_hash([confirmada])
    assert bloque.previous_hash == genesis.hash
    assert chain.audit_chain().resumen.valida is True


def test_reencadenar_no_toca_los_indices_ni_las_marcas_de_tiempo(wallets):
    """La reparación reescribe hashes y nada más: índice y `timestamp` quedan iguales."""
    chain, _, bloque, _ = _cadena_valida(wallets)
    bloque.hash = "f" * 64
    antes = [(b.block_index, b.timestamp) for b in chain.blocks.list()]

    chain.repair_chain()

    assert [(b.block_index, b.timestamp) for b in chain.blocks.list()] == antes


def test_reencadenar_una_cadena_sana_no_escribe_nada(wallets):
    """Con los hashes ya correctos la reparación no aplica y no toca ninguna fila."""
    chain, *_ = _cadena_valida(wallets)
    antes = _foto(chain)

    reparacion = chain.repair_chain()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert _foto(chain) == antes


def test_sin_bloques_la_reparacion_crea_el_genesis(wallets):
    """Una cadena vacía se repara creando el eslabón cero, como el arranque."""
    chain = _chain(wallets)

    reparacion = chain.repair_chain()

    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    genesis = chain.blocks.get_by_index(0)
    assert genesis is not None
    assert genesis.previous_hash == "0" * 64
    assert genesis.hash == genesis.calculate_hash([])
    assert chain.audit_chain().resumen.valida is True


def test_si_el_primer_bloque_no_es_el_genesis_no_se_renumera(wallets):
    """Una cadena que empieza en el índice 1 no se aplica y se explica, sin renumerar."""
    ajeno = build_block(1, previous_hash="a" * 64)
    chain = _chain(wallets, blocks=[ajeno])

    reparacion = chain.repair_chain()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert "no se renumera" in reparacion.detalle
    assert [b.block_index for b in chain.blocks.list()] == [1]


def test_un_hueco_de_indices_queda_declarado_y_no_se_renumera(wallets):
    """Una cadena 0, 1, 3 se reencadena pero el hueco se declara y sigue ahí."""
    genesis = build_block(0)
    segundo = build_block(1, genesis)
    salteado = build_block(3, segundo)
    chain = _chain(wallets, blocks=[genesis, segundo, salteado])

    reparacion = chain.repair_chain()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert "índices" in reparacion.detalle
    assert [b.block_index for b in chain.blocks.list()] == [0, 1, 3]
    assert any(h.codigo == "indice" for h in chain.audit_chain().hallazgos)


def test_aislar_una_confirmada_con_firma_invalida_la_rechaza_y_reencadena(wallets):
    """Una confirmada con firma inventada sale de su bloque y el bloque se recalcula."""
    chain, genesis, bloque, confirmada = _cadena_valida(wallets)
    confirmada.signature = "ab" * 64
    assert chain.audit_chain().resumen.valida is False

    reparacion = chain.isolate_invalid_transactions()

    assert reparacion.accion == "aislar"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 2
    assert confirmada.status is TransactionStatus.REJECTED
    assert confirmada.block_id is None
    assert bloque.hash == bloque.calculate_hash([])
    assert bloque.previous_hash == genesis.hash
    assert chain.audit_chain().resumen.valida is True


def test_aislar_una_confirmada_sin_bloque_la_rechaza(wallets):
    """Una confirmada que no está en ningún bloque se aísla sin reencadenar nada."""
    huerfana = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    genesis = build_block(0)
    chain = _chain(wallets, blocks=[genesis], transactions=[huerfana])

    reparacion = chain.isolate_invalid_transactions()

    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert huerfana.status is TransactionStatus.REJECTED
    assert huerfana.block_id is None
    assert chain.audit_chain().resumen.valida is True


def test_aislar_no_toca_las_confirmadas_validas(wallets):
    """Sin confirmadas inválidas no se rechaza ninguna fila válida."""
    chain, *_ = _cadena_valida(wallets)
    antes = _foto(chain)

    reparacion = chain.isolate_invalid_transactions()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert _foto(chain) == antes


def test_aislar_sin_genesis_no_fabrica_el_encadenamiento(wallets):
    """Sin el bloque 0 se rechaza la inválida, pero no se reescriben sus hashes.

    Reencadenar a partir de un bloque que no es el génesis encadenaría el primero a
    los ceros del eslabón cero y borraría el rastro de la cabeza eliminada, así que
    aislar rechaza y deja el encadenamiento como estaba.
    """
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    confirmada.signature = "ab" * 64
    huerfano = build_block(1, previous_hash="a" * 64, transactions=[confirmada])
    confirmada.block_id = huerfano.id
    chain = _chain(wallets, blocks=[huerfano], transactions=[confirmada])
    hash_guardado = huerfano.hash

    reparacion = chain.isolate_invalid_transactions()

    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert confirmada.status is TransactionStatus.REJECTED
    assert confirmada.block_id is None
    assert huerfano.previous_hash == "a" * 64
    assert huerfano.hash == hash_guardado
    assert "no se aplicó" in reparacion.detalle
    assert any(h.codigo == "cabeza" for h in chain.audit_chain().hallazgos)


def test_reparar_todo_sin_genesis_conserva_el_encadenamiento(wallets):
    """«Reparar todo» sin génesis rechaza e aísla, y el tercer paso no toca los hashes."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    confirmada.signature = "ab" * 64
    huerfano = build_block(1, previous_hash="a" * 64, transactions=[confirmada])
    confirmada.block_id = huerfano.id
    chain = _chain(wallets, blocks=[huerfano], transactions=[confirmada])

    reparaciones = chain.repair_all()

    assert tuple(r.accion for r in reparaciones) == (
        "rechazar-pendientes",
        "aislar",
        "encadenar",
    )
    assert reparaciones[0].aplicada is False
    assert reparaciones[1].aplicada is True
    assert reparaciones[1].cambios == 1
    assert reparaciones[2].aplicada is False
    assert huerfano.previous_hash == "a" * 64
    assert any(h.codigo == "cabeza" for h in chain.audit_chain().hallazgos)


def test_rechazar_pendientes_invalidas_no_toca_las_validas(wallets):
    """La firma inválida del pool se rechaza; la pendiente válida sigue pendiente."""
    invalida = _transaccion(wallets)
    invalida.signature = "ab" * 64
    valida = _transaccion(wallets)
    chain, *_ = _cadena_valida(wallets, pendientes=[invalida, valida])

    reparacion = chain.reject_invalid_pending()

    assert reparacion.accion == "rechazar-pendientes"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert invalida.status is TransactionStatus.REJECTED
    assert invalida.block_id is None
    assert valida.status is TransactionStatus.PENDING


@pytest.mark.parametrize(
    "monto",
    [Decimal("0"), Decimal("-1.00000000"), Decimal("NaN")],
    ids=["cero", "negativo", "nan"],
)
def test_rechazar_pendientes_con_monto_invalido(wallets, monto):
    """Un monto que no cabe en las reglas de admisión se rechaza desde el pool."""
    invalida = _transaccion(wallets, amount=monto)
    chain, *_ = _cadena_valida(wallets, pendientes=[invalida])

    assert chain.reject_invalid_pending().cambios == 1
    assert invalida.status is TransactionStatus.REJECTED


def test_rechazar_una_pendiente_con_wallet_inexistente(wallets):
    """Una pendiente que apunta a una wallet que no está se rechaza."""
    huerfana = _transaccion(wallets, sender_id=uuid4())
    chain, *_ = _cadena_valida(wallets, pendientes=[huerfana])

    assert chain.reject_invalid_pending().cambios == 1
    assert huerfana.status is TransactionStatus.REJECTED


def test_rechazar_un_pool_sin_invalidas_no_escribe_nada(wallets):
    """El pool sano no se toca: todas las válidas quedan como estaban."""
    chain, *_ = _cadena_valida(wallets, pendientes=[_transaccion(wallets)])
    antes = _foto(chain)

    reparacion = chain.reject_invalid_pending()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert _foto(chain) == antes


def test_reparar_todo_devuelve_las_tres_reparaciones_en_orden(wallets):
    """El orden es rechazar pendientes, aislar confirmadas y encadenar."""
    invalida_del_pool = _transaccion(wallets)
    invalida_del_pool.signature = "ab" * 64
    chain, _, bloque, confirmada = _cadena_valida(wallets, pendientes=[invalida_del_pool])
    confirmada.signature = "cd" * 64
    bloque.hash = "f" * 64

    reparaciones = chain.repair_all()

    assert tuple(r.accion for r in reparaciones) == (
        "rechazar-pendientes",
        "aislar",
        "encadenar",
    )
    assert reparaciones[0].cambios == 1
    assert reparaciones[1].aplicada is True
    # Aislar ya reencadenó: el tercer paso no encuentra nada que reescribir.
    assert reparaciones[2].aplicada is False
    assert reparaciones[2].cambios == 0
    assert chain.audit_chain().resumen.valida is True


def test_reparar_todo_es_idempotente(wallets):
    """La segunda pasada no encuentra nada que reparar ni escribe ninguna fila."""
    invalida = _transaccion(wallets)
    invalida.signature = "ab" * 64
    chain, _, bloque, _ = _cadena_valida(wallets, pendientes=[invalida])
    bloque.hash = "f" * 64
    chain.repair_all()
    antes = _foto(chain)

    segunda = chain.repair_all()

    assert tuple(r.aplicada for r in segunda) == (False, False, False)
    assert tuple(r.cambios for r in segunda) == (0, 0, 0)
    assert _foto(chain) == antes


def test_agrupar_por_bloque_toma_las_filas_que_declaran_bloque(wallets):
    """El agrupamiento por `block_id` deja fuera solo las filas sin bloque."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    rechazada = _transaccion(wallets, status=TransactionStatus.REJECTED)
    pendiente = _transaccion(wallets)
    bloque = build_block(0)
    confirmada.block_id = bloque.id
    rechazada.block_id = bloque.id

    agrupadas = agrupar_por_bloque([confirmada, rechazada, pendiente])

    assert agrupadas == {bloque.id: [confirmada, rechazada]}


def test_recalcular_cadena_no_modifica_los_bloques_originales(wallets):
    """La función pura devuelve bloques nuevos y cuenta cuántos cambian de hash."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    genesis = build_block(0)
    bloque = build_block(1, genesis, transactions=[confirmada])
    confirmada.block_id = bloque.id
    bloque.hash = "f" * 64
    antes = (genesis.hash, bloque.hash, bloque.previous_hash)

    reencadenado = recalcular_cadena(
        [genesis, bloque], agrupar_por_bloque([confirmada])
    )

    assert (genesis.hash, bloque.hash, bloque.previous_hash) == antes
    assert reencadenado.cambios == 1
    assert reencadenado.huecos == ()
    assert [nuevo.hash for nuevo in reencadenado.bloques] == [
        genesis.hash,
        bloque.calculate_hash([confirmada]),
    ]
    assert reencadenado.bloques[1].previous_hash == genesis.hash


def test_recalcular_cadena_declara_los_huecos(wallets):
    """Un salto entre índices se devuelve como hueco aunque los hashes encadenen."""
    genesis = build_block(0)
    salteado = build_block(3, genesis)

    reencadenado = recalcular_cadena([genesis, salteado], {})

    assert reencadenado.huecos == (3,)
    assert reencadenado.cambios == 0


def test_se_puede_reencadenar_solo_con_el_genesis(wallets):
    """El recálculo solo se aplica cuando la cadena empieza en el bloque índice 0."""
    assert se_puede_reencadenar([]) is False
    assert se_puede_reencadenar([build_block(0)]) is True
    assert se_puede_reencadenar([build_block(1, previous_hash="a" * 64)]) is False


def test_motivo_de_invalidez_revalida_firma_monto_y_wallet(wallets):
    """La revalidación devuelve el motivo que impide que la fila esté en la cadena."""
    emisora = wallets["emisora"]
    receptora = wallets["receptora"]

    valida = _transaccion(wallets)
    assert (
        motivo_de_invalidez(
            valida,
            sender_public_key=emisora.public_key,
            receiver_public_key=receptora.public_key,
        )
        is None
    )

    firmada_por_otra = _transaccion(wallets)
    firmada_por_otra.signature = "ab" * 64
    assert (
        motivo_de_invalidez(
            firmada_por_otra,
            sender_public_key=emisora.public_key,
            receiver_public_key=receptora.public_key,
        )
        is RejectionReason.BAD_SIGNATURE
    )

    sin_monto = _transaccion(wallets, amount=Decimal("0"))
    assert (
        motivo_de_invalidez(
            sin_monto,
            sender_public_key=emisora.public_key,
            receiver_public_key=receptora.public_key,
        )
        is RejectionReason.AMOUNT_NOT_POSITIVE
    )

    sin_wallet = _transaccion(wallets)
    assert (
        motivo_de_invalidez(
            sin_wallet, sender_public_key=None, receiver_public_key=receptora.public_key
        )
        is RejectionReason.UNKNOWN_WALLET
    )


def test_esta_desencajada_solo_marca_lo_que_la_reparacion_cierra(wallets):
    """La coherencia que las reparaciones pueden cerrar es la de confirmadas y pool."""
    genesis = build_block(0)
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    confirmada.block_id = genesis.id
    pendiente = _transaccion(wallets)

    assert esta_desencajada(confirmada, ids_de_bloques={genesis.id}) is False
    assert esta_desencajada(pendiente, ids_de_bloques={genesis.id}) is False

    confirmada_sin_bloque = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    assert esta_desencajada(confirmada_sin_bloque, ids_de_bloques={genesis.id}) is True

    confirmada_con_bloque_ajeno = _transaccion(
        wallets, status=TransactionStatus.CONFIRMED, block_id=uuid4()
    )
    assert esta_desencajada(confirmada_con_bloque_ajeno, ids_de_bloques={genesis.id}) is True

    pendiente_con_bloque = _transaccion(wallets, block_id=genesis.id)
    assert esta_desencajada(pendiente_con_bloque, ids_de_bloques={genesis.id}) is True

    rechazada_con_bloque = _transaccion(
        wallets, status=TransactionStatus.REJECTED, block_id=genesis.id
    )
    assert esta_desencajada(rechazada_con_bloque, ids_de_bloques={genesis.id}) is False
