"""Fachada del ledger.

Expone las operaciones sobre las tres entidades. Recibe los repositorios ya
construidos y no conoce PostgreSQL: todo lo que usa está declarado en
``persistence/ports.py``.

Alcance de este corte: solo CRUD. La validación de transacciones, la agrupación
en bloques, el cálculo del hash y la verificación de la cadena todavía no están
implementados.
"""

from __future__ import annotations

from src.persistence.ports import (
    BlockRepository,
    TransactionRepository,
    WalletRepository,
)


class Blockchain:
    """Punto de acceso al ledger.

    El nombre es el que fija el diseño del proyecto para el componente que
    coordina el ledger, y el que usan el glosario y el documento de entrega.
    """

    def __init__(
        self,
        wallets: WalletRepository,
        blocks: BlockRepository,
        transactions: TransactionRepository,
    ) -> None:
        self.wallets = wallets
        self.blocks = blocks
        self.transactions = transactions

    def counts(self) -> dict[str, int]:
        """Cuenta las filas de las tres tablas, en el orden del ledger."""
        return {
            "wallets": self.wallets.count(),
            "blocks": self.blocks.count(),
            "transactions": self.transactions.count(),
        }
