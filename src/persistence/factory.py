"""Ensamblado del ledger.

Es el único lugar donde se unen el dominio y los adaptadores. Sirve para que
tanto el punto de entrada como una sesión interactiva construyan el ledger de la
misma forma.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from src.blockchain import Blockchain
from src.persistence.connection import connect
from src.persistence.repositories import (
    PostgresBlockRepository,
    PostgresTransactionRepository,
    PostgresWalletRepository,
)


def _build(connection: psycopg.Connection) -> Blockchain:
    """Arma el ledger sobre una conexión ya abierta."""
    return Blockchain(
        wallets=PostgresWalletRepository(connection),
        blocks=PostgresBlockRepository(connection),
        transactions=PostgresTransactionRepository(connection),
    )


@contextmanager
def ledger() -> Iterator[Blockchain]:
    """Entrega el ledger y cierra la conexión al salir, haya error o no.

    Es la forma recomendada dentro de un script.
    """
    connection = connect()
    try:
        yield _build(connection)
    finally:
        connection.close()


def open_ledger() -> Blockchain:
    """Entrega el ledger con la conexión abierta, para una sesión interactiva.

    La conexión se cierra cuando termina el proceso. Dentro de un script conviene
    ``ledger()``, que la cierra al salir del bloque ``with``.
    """
    return _build(connect())
