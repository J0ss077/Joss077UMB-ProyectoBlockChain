"""Implementación PostgreSQL de los repositorios.

Ninguna operación repite las reglas del esquema. Si una escritura viola un CHECK,
una clave foránea o una restricción de unicidad, el error de PostgreSQL se
propaga tal cual: es la respuesta que interesa ver.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from src.block import Block
from src.transaction import Transaction, TransactionStatus
from src.wallet import Wallet

WALLET_COLUMNS = "id, public_key, private_key_encrypted, created_at"
BLOCK_COLUMNS = "id, block_index, timestamp, previous_hash, hash"
TRANSACTION_COLUMNS = (
    "id, sender_id, receiver_id, amount, status, signature, block_id, created_at"
)


def _wallet_from_row(row: dict[str, Any]) -> Wallet:
    return Wallet(
        id=row["id"],
        public_key=row["public_key"],
        private_key_encrypted=bytes(row["private_key_encrypted"]),
        created_at=row["created_at"],
    )


def _block_from_row(row: dict[str, Any]) -> Block:
    return Block(
        id=row["id"],
        block_index=row["block_index"],
        timestamp=row["timestamp"],
        previous_hash=row["previous_hash"],
        hash=row["hash"],
    )


def _transaction_from_row(row: dict[str, Any]) -> Transaction:
    return Transaction(
        id=row["id"],
        sender_id=row["sender_id"],
        receiver_id=row["receiver_id"],
        amount=row["amount"],
        status=TransactionStatus(row["status"]),
        signature=row["signature"],
        block_id=row["block_id"],
        created_at=row["created_at"],
    )


class PostgresWalletRepository:
    """CRUD sobre la tabla wallets."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def create(self, public_key: str, private_key_encrypted: bytes) -> Wallet:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO wallets (public_key, private_key_encrypted)
                VALUES (%s, %s)
                RETURNING {WALLET_COLUMNS}
                """,
                (public_key, private_key_encrypted),
            )
            row = cursor.fetchone()
        self._connection.commit()
        return _wallet_from_row(row)

    def get(self, wallet_id: UUID) -> Wallet | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {WALLET_COLUMNS} FROM wallets WHERE id = %s", (wallet_id,)
            )
            row = cursor.fetchone()
        return _wallet_from_row(row) if row else None

    def list(self, limit: int = 100) -> Sequence[Wallet]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {WALLET_COLUMNS} FROM wallets ORDER BY created_at LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
        return [_wallet_from_row(row) for row in rows]

    def update(self, wallet: Wallet) -> Wallet:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE wallets
                   SET public_key = %s,
                       private_key_encrypted = %s
                 WHERE id = %s
                RETURNING {WALLET_COLUMNS}
                """,
                (wallet.public_key, wallet.private_key_encrypted, wallet.id),
            )
            row = cursor.fetchone()
        self._connection.commit()
        if row is None:
            raise LookupError(f"No existe la wallet {wallet.id}")
        return _wallet_from_row(row)

    def delete(self, wallet_id: UUID) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM wallets WHERE id = %s", (wallet_id,))
            deleted = cursor.rowcount > 0
        self._connection.commit()
        return deleted

    def count(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS total FROM wallets")
            row = cursor.fetchone()
        return int(row["total"])


class PostgresBlockRepository:
    """CRUD sobre la tabla blocks, sin actualización."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def create(
        self,
        block_index: int,
        previous_hash: str,
        block_hash: str,
        timestamp: datetime | None = None,
    ) -> Block:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO blocks (block_index, timestamp, previous_hash, hash)
                VALUES (%s, COALESCE(%s, NOW()), %s, %s)
                RETURNING {BLOCK_COLUMNS}
                """,
                (block_index, timestamp, previous_hash, block_hash),
            )
            row = cursor.fetchone()
        self._connection.commit()
        return _block_from_row(row)

    def get(self, block_id: UUID) -> Block | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {BLOCK_COLUMNS} FROM blocks WHERE id = %s", (block_id,)
            )
            row = cursor.fetchone()
        return _block_from_row(row) if row else None

    def list(self, limit: int = 100) -> Sequence[Block]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {BLOCK_COLUMNS} FROM blocks ORDER BY block_index LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
        return [_block_from_row(row) for row in rows]

    def delete(self, block_id: UUID) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM blocks WHERE id = %s", (block_id,))
            deleted = cursor.rowcount > 0
        self._connection.commit()
        return deleted

    def count(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS total FROM blocks")
            row = cursor.fetchone()
        return int(row["total"])


class PostgresTransactionRepository:
    """CRUD sobre la tabla transactions."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def create(
        self,
        sender_id: UUID,
        receiver_id: UUID,
        amount: Decimal,
        signature: str,
        status: TransactionStatus = TransactionStatus.PENDING,
        block_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> Transaction:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO transactions (
                    sender_id, receiver_id, amount, status, signature, block_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
                RETURNING {TRANSACTION_COLUMNS}
                """,
                (
                    sender_id,
                    receiver_id,
                    amount,
                    status.value,
                    signature,
                    block_id,
                    created_at,
                ),
            )
            row = cursor.fetchone()
        self._connection.commit()
        return _transaction_from_row(row)

    def get(self, transaction_id: UUID) -> Transaction | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {TRANSACTION_COLUMNS} FROM transactions WHERE id = %s",
                (transaction_id,),
            )
            row = cursor.fetchone()
        return _transaction_from_row(row) if row else None

    def list(
        self,
        status: TransactionStatus | None = None,
        wallet_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[Transaction]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {TRANSACTION_COLUMNS}
                  FROM transactions
                 WHERE (%s::text IS NULL OR status = %s)
                   AND (%s::uuid IS NULL OR sender_id = %s OR receiver_id = %s)
                 ORDER BY created_at
                 LIMIT %s
                """,
                (
                    status.value if status else None,
                    status.value if status else None,
                    wallet_id,
                    wallet_id,
                    wallet_id,
                    limit,
                ),
            )
            rows = cursor.fetchall()
        return [_transaction_from_row(row) for row in rows]

    def update(self, transaction: Transaction) -> Transaction:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE transactions
                   SET receiver_id = %s,
                       amount = %s,
                       status = %s,
                       signature = %s,
                       block_id = %s
                 WHERE id = %s
                RETURNING {TRANSACTION_COLUMNS}
                """,
                (
                    transaction.receiver_id,
                    transaction.amount,
                    transaction.status.value,
                    transaction.signature,
                    transaction.block_id,
                    transaction.id,
                ),
            )
            row = cursor.fetchone()
        self._connection.commit()
        if row is None:
            raise LookupError(f"No existe la transacción {transaction.id}")
        return _transaction_from_row(row)

    def delete(self, transaction_id: UUID) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
            deleted = cursor.rowcount > 0
        self._connection.commit()
        return deleted

    def count(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS total FROM transactions")
            row = cursor.fetchone()
        return int(row["total"])
