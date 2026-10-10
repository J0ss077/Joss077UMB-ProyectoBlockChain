"""Puertos de persistencia: el contrato que el dominio espera de la base (REQ-16).

Son `Protocol` y no clases base porque describen la forma, no la herencia: el
dominio depende de estos nombres —y no de `psycopg`—, y así cargarlo no arrastra
el driver. Los adaptadores que cumplen estos contratos viven en `postgres.py` y la
unidad de trabajo, en `unit_of_work.py`.
"""
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from src.domain.block import Block
from src.domain.blockchain import BalanceTerms
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import Wallet


class WalletRepository(Protocol):
    """Acceso a las wallets registradas (REQ-01)."""

    def add(self, wallet: Wallet) -> Wallet: ...

    def get(self, wallet_id: UUID) -> Wallet | None: ...

    def get_by_public_key(self, public_key: str) -> Wallet | None: ...

    def list(self, limit: int = 100) -> Sequence[Wallet]: ...

    def count(self) -> int: ...


class BlockRepository(Protocol):
    """Acceso a los bloques de la cadena (REQ-07, REQ-08, REQ-14)."""

    def add(self, block: Block) -> Block: ...

    def get_by_index(self, block_index: int) -> Block | None: ...

    def last(self) -> Block | None: ...

    def list(self) -> Sequence[Block]: ...

    def count(self) -> int: ...


class TransactionRepository(Protocol):
    """Acceso al pool, a las confirmadas y a las rechazadas (REQ-03, REQ-05, REQ-11, REQ-13)."""

    def add(self, transaction: Transaction) -> Transaction: ...

    def confirm(self, transaction_ids: Sequence[UUID], block_id: UUID) -> int: ...

    def get(self, transaction_id: UUID) -> Transaction | None: ...

    def list(
        self,
        *,
        status: TransactionStatus | None = None,
        wallet_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[Transaction]: ...

    def pending(self) -> Sequence[Transaction]: ...

    def of_block(self, block_id: UUID) -> Sequence[Transaction]: ...

    def balance_terms(self, wallet_id: UUID) -> BalanceTerms: ...

    def signature_exists(self, signature: str) -> bool: ...

    def count(self) -> int: ...


class UnitOfWork(Protocol):
    """Agrupa los tres repositorios y cierra el trabajo en una sola transacción.

    La implementación es el contexto que hace atómica la agrupación de REQ-18:
    `commit` aplica todo o nada y `rollback` deshace lo escrito cuando algo falla
    a mitad.
    """

    wallets: WalletRepository
    blocks: BlockRepository
    transactions: TransactionRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, *exc_info: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
