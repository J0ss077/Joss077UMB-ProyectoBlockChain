"""Puertos de persistencia.

El dominio depende de estos protocolos y no de PostgreSQL. Es el límite que fija
el ADR-0005, y es lo que permite probar las reglas sin levantar la base.

Las firmas usan tipos simples en las operaciones de creación para que el
identificador y la marca de tiempo los genere la base, con sus valores por
defecto, en lugar de duplicar esa decisión en Python.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.block import Block
from src.transaction import Transaction, TransactionStatus
from src.wallet import Wallet


class WalletRepository(Protocol):
    """Acceso a la tabla wallets."""

    def create(self, public_key: str, private_key_encrypted: bytes) -> Wallet: ...

    def get(self, wallet_id: UUID) -> Wallet | None: ...

    def list(self, limit: int = 100) -> Sequence[Wallet]: ...

    def update(self, wallet: Wallet) -> Wallet: ...

    def delete(self, wallet_id: UUID) -> bool: ...

    def count(self) -> int: ...


class BlockRepository(Protocol):
    """Acceso a la tabla blocks.

    No hay operación de actualización: un bloque ya encadenado no se modifica.
    Cambiarlo es precisamente lo que el sistema debe detectar.
    """

    def create(
        self,
        block_index: int,
        previous_hash: str,
        block_hash: str,
        timestamp: datetime | None = None,
    ) -> Block: ...

    def get(self, block_id: UUID) -> Block | None: ...

    def list(self, limit: int = 100) -> Sequence[Block]: ...

    def delete(self, block_id: UUID) -> bool: ...

    def count(self) -> int: ...


class TransactionRepository(Protocol):
    """Acceso a la tabla transactions."""

    def create(
        self,
        sender_id: UUID,
        receiver_id: UUID,
        amount: Decimal,
        signature: str,
        status: TransactionStatus = TransactionStatus.PENDING,
        block_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> Transaction: ...

    def get(self, transaction_id: UUID) -> Transaction | None: ...

    def list(
        self,
        status: TransactionStatus | None = None,
        wallet_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[Transaction]: ...

    def update(self, transaction: Transaction) -> Transaction: ...

    def delete(self, transaction_id: UUID) -> bool: ...

    def count(self) -> int: ...
