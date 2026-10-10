"""Unidad de trabajo: las dos escrituras de la agrupación en una sola transacción (REQ-18).

La agrupación del CU-03 inserta el bloque y confirma sus transacciones; si la
segunda falla, la primera no puede quedar aplicada. Esta unidad de trabajo es la
que lo garantiza: abre su propia conexión sin autocommit, deja las dos escrituras
pendientes y recién ahí confirma, y ante cualquier fallo deshace todo. La conexión
es suya y por eso la cierra ella, a diferencia de los repositorios de
`postgres.py`, que reciben una conexión ya abierta.
"""
from __future__ import annotations

from types import TracebackType

import psycopg

from src.persistence.postgres import (
    PostgresBlockRepository,
    PostgresTransactionRepository,
    PostgresWalletRepository,
)


class PostgresUnitOfWork:
    """Los tres repositorios sobre una conexión transaccional propia (REQ-18)."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self.wallets = PostgresWalletRepository(connection)
        self.blocks = PostgresBlockRepository(connection)
        self.transactions = PostgresTransactionRepository(connection)

    @classmethod
    def open(cls, database_url: str) -> PostgresUnitOfWork:
        """Abre la conexión de la unidad de trabajo.

        Sin `autocommit`: las dos escrituras quedan pendientes hasta el `commit`
        único, que es exactamente lo que REQ-18 exige. Si la conexión fuera de
        autocommit, cada escritura se confirmaría sola y el fallo de la segunda
        dejaría la primera aplicada.
        """
        return cls(psycopg.connect(database_url))

    def __enter__(self) -> PostgresUnitOfWork:
        return self

    def __exit__(self, exc_type, exc_value, traceback: TracebackType | None) -> None:
        # Un fallo a mitad de camino no deja media agrupación: se deshace lo escrito
        # y el error sigue subiendo sin traducir (REQ-18 y REQ-19).
        if exc_type is not None:
            self.rollback()
        self._connection.close()

    def commit(self) -> None:
        """Cierra la transacción de base de datos: las dos escrituras o ninguna."""
        self._connection.commit()

    def rollback(self) -> None:
        """Deshace lo escrito desde el comienzo de la unidad de trabajo."""
        self._connection.rollback()
