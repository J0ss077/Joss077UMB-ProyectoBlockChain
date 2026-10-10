"""REQ-13: consultar el historial y el estado del ledger.

El criterio cubre las tres tablas: se listan y se cuentan wallets, bloques y
transacciones, el listado de transacciones se filtra por estado y por wallet, y
`balance_terms` resuelve las tres sumas del saldo disponible (REQ-05) en una
sola consulta sobre `transactions`.
"""
from decimal import Decimal

import pytest

from src.domain.blockchain import BalanceTerms
from src.domain.transaction import TransactionStatus
from src.domain.wallet import create_wallet
from src.persistence.postgres import PostgresTransactionRepository


@pytest.fixture
def transacciones(conexion):
    """El repositorio de transacciones contra la conexión de la sesión."""
    return PostgresTransactionRepository(conexion)


@pytest.fixture
def historial(transacciones, base_limpia, emisora, receptora, bloque, transaccion, wallets, master_key):
    """Un escenario con cada suma del saldo distinguible de las otras.

    Montos a propósito distintos entre sí: si `balance_terms` contara el estado
    equivocado o cruzara las direcciones, las sumas no podrían coincidir por
    casualidad. La emisora termina con 3 confirmado a favor, 7 confirmado en
    contra y 10 comprometido en el pool; la receptora, con las sumas espejo.
    """
    tercera = wallets.add(create_wallet(master_key=master_key))
    pendientes = [
        transacciones.add(transaccion(amount=Decimal("4.00000000"))),
        transacciones.add(transaccion(receiver=tercera, amount=Decimal("6.00000000"))),
        transacciones.add(transaccion(sender=receptora, receiver=tercera)),
    ]
    # Una rechazada del mismo emisor: no suma en ninguna de las tres cuentas.
    transacciones.add(
        transaccion(status=TransactionStatus.REJECTED, block_id=None, amount=Decimal("99.00000000"))
    )

    nuevo = bloque(block_index=0)
    # Se escribe pendiente y se confirma con el repositorio, que es el camino
    # real; el CHECK del esquema impide escribirla ya confirmada sin bloque.
    entrante = transacciones.add(
        transaccion(sender=receptora, receiver=emisora, amount=Decimal("3.00000000"))
    )
    saliente = transacciones.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("7.00000000"))
    )
    transacciones.confirm([entrante.id, saliente.id], nuevo.id)

    return {
        "pendientes": pendientes,
        "confirmadas": [entrante, saliente],
        "confirmada": transacciones.get(entrante.id),
        "bloque": nuevo,
        "emisora": emisora,
        "receptora": receptora,
        "tercera": tercera,
    }


def test_req_13_se_listan_y_cuentan_las_wallets_y_los_bloques(wallets, bloques, historial):
    """Las wallets y los bloques también se listan y se cuentan, y el bloque se busca por índice.

    El criterio de REQ-13 habla de las tres tablas, no solo de las transacciones.
    """
    assert wallets.count() == 3
    assert {wallet.id for wallet in wallets.list()} == {
        historial["emisora"].id,
        historial["receptora"].id,
        historial["tercera"].id,
    }

    assert bloques.count() == 1
    assert [block.id for block in bloques.list()] == [historial["bloque"].id]
    assert bloques.last().id == historial["bloque"].id
    assert bloques.get_by_index(0).id == historial["bloque"].id
    assert bloques.get_by_index(1) is None


def test_req_13_se_listan_las_transacciones_y_se_cuentan_las_filas(transacciones, historial):
    """El listado total devuelve las seis filas del escenario y `count` coincide."""
    assert len(transacciones.list()) == 6
    assert transacciones.count() == 6


def test_req_13_el_listado_se_filtra_por_estado(transacciones, historial):
    """El filtro por estado separa las pendientes del pool, las confirmadas y la rechazada."""
    pendientes = transacciones.list(status=TransactionStatus.PENDING)
    confirmadas = transacciones.list(status=TransactionStatus.CONFIRMED)
    rechazadas = transacciones.list(status=TransactionStatus.REJECTED)

    assert {fila.id for fila in pendientes} == {fila.id for fila in historial["pendientes"]}
    assert {fila.id for fila in confirmadas} == {fila.id for fila in historial["confirmadas"]}
    assert len(rechazadas) == 1
    assert all(fila.status is TransactionStatus.PENDING for fila in pendientes)
    assert {fila.id for fila in transacciones.pending()} == {fila.id for fila in pendientes}


def test_req_13_el_listado_se_filtra_por_wallet(transacciones, historial):
    """El historial de una wallet son sus envíos y sus recepciones, en cualquier estado."""
    # La emisora tiene cinco: dos salientes del pool, una rechazada, una
    # entrante confirmada y una saliente confirmada.
    assert len(transacciones.list(wallet_id=historial["emisora"].id)) == 5
    # La receptora tiene cinco: tres entrantes del pool (dos de la emisora y
    # la rechazada de 99), una entrante confirmada y su saliente confirmada.
    assert len(transacciones.list(wallet_id=historial["receptora"].id)) == 5
    # La tercera solo recibe: dos entrantes, y ninguna confirmada.
    assert len(transacciones.list(wallet_id=historial["tercera"].id)) == 2
    assert len(transacciones.list(wallet_id=historial["tercera"].id, status=TransactionStatus.PENDING)) == 2


def test_req_13_el_listado_de_un_bloque_son_sus_transacciones(
    transacciones, base_limpia, historial, bloque
):
    """`of_block` devuelve lo que el bloque agrupa y `confirm` no vuelve a confirmar."""
    agrupadas = transacciones.of_block(historial["bloque"].id)
    assert {fila.id for fila in agrupadas} == {fila.id for fila in historial["confirmadas"]}

    # Confirmar lo ya confirmado no es un cambio: devuelve cero y deja la fila
    # en su bloque, así que una segunda agrupación no puede moverla.
    otro = bloque(block_index=1, previous_hash=historial["bloque"].hash)
    assert transacciones.confirm([historial["confirmada"].id], otro.id) == 0
    assert transacciones.get(historial["confirmada"].id).block_id == historial["bloque"].id
    assert transacciones.count() == 6


def test_req_13_las_sumas_del_saldo_se_resuelven_en_una_consulta(transacciones, historial):
    """`balance_terms` separa lo confirmado a favor, lo confirmado en contra y el pool.

    Cada estado aporta un monto distinto, así que contar un estado por otro o
    cruzar las direcciones cambia el resultado.
    """
    assert transacciones.balance_terms(historial["emisora"].id) == BalanceTerms(
        confirmed_in=Decimal("3.00000000"),
        confirmed_out=Decimal("7.00000000"),
        pending_out=Decimal("10.00000000"),
    )
    # La receptora es el espejo: recibe los 7 confirmados de la emisora, le
    # envía los 3 confirmados y tiene 10 comprometidos hacia la tercera.
    assert transacciones.balance_terms(historial["receptora"].id) == BalanceTerms(
        confirmed_in=Decimal("7.00000000"),
        confirmed_out=Decimal("3.00000000"),
        pending_out=Decimal("10.00000000"),
    )
    # La tercera recibe 16 en el pool y no ha movido nada confirmado.
    assert transacciones.balance_terms(historial["tercera"].id) == BalanceTerms(
        confirmed_in=Decimal("0"),
        confirmed_out=Decimal("0"),
        pending_out=Decimal("0"),
    )


def test_req_13_una_wallet_sin_transacciones_suma_cero(transacciones, historial, wallets, master_key):
    """El agregado devuelve ceros, y no `NULL`, cuando la wallet no tiene movimientos."""
    intocada = wallets.add(create_wallet(master_key=master_key))

    assert transacciones.balance_terms(intocada.id) == BalanceTerms(
        confirmed_in=Decimal("0"),
        confirmed_out=Decimal("0"),
        pending_out=Decimal("0"),
    )
