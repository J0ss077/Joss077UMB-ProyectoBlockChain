"""Adaptadores PostgreSQL: traducen el dominio a las tablas del eje (REQ-01, REQ-19).

Tres repositorios, uno por protocolo de `src/persistence/ports.py`, que reciben
la conexión ya abierta. **No hay ningún `except` que traduzca errores**: REQ-19
exige que la violación de un CHECK, de una clave foránea o del índice único
llegue cruda desde el motor, y quien decide qué hacer con ella es la capa de
arriba. La conexión tampoco se cierra desde aquí: la cierra quien la abrió,
porque los tres repositorios comparten una sola transacción de base de datos
(REQ-18) y cerrarla a mitad la cortaría.
"""
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from src.domain.block import Block
from src.domain.blockchain import BalanceTerms
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import Wallet

# Las columnas se nombran una vez en cada INSERT para que el valor devuelto
# (`RETURNING *`) sea la fila tal como quedó en la base, no la que se propuso.
_WALLET_COLUMNS = "id, public_key, private_key_encrypted, created_at"
_BLOCK_COLUMNS = "id, block_index, timestamp, previous_hash, hash"
_TRANSACTION_COLUMNS = "id, sender_id, receiver_id, amount, status, signature, block_id, created_at"


def _row_to_wallet(row: dict[str, Any]) -> Wallet:
    """Fila de `wallets` al objeto del dominio."""
    return Wallet(
        id=row["id"],
        public_key=row["public_key"],
        private_key_encrypted=bytes(row["private_key_encrypted"]),
        created_at=row["created_at"],
    )


def _row_to_block(row: dict[str, Any]) -> Block:
    """Fila de `blocks` al objeto del dominio.

    Los hashes se guardan en `CHAR(64)`; PostgreSQL los devuelve con relleno de
    espacios si el valor fuera más corto, y el CHECK del esquema garantiza que
    no lo sea, así que el valor llega tal cual se escribió.
    """
    return Block(
        id=row["id"],
        block_index=row["block_index"],
        timestamp=row["timestamp"],
        previous_hash=row["previous_hash"],
        hash=row["hash"],
    )


def _row_to_transaction(row: dict[str, Any]) -> Transaction:
    """Fila de `transactions` al objeto del dominio."""
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
    """Repositorio de wallets sobre PostgreSQL (REQ-01)."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    def add(self, wallet: Wallet) -> Wallet:
        """Registra la wallet y devuelve la fila escrita."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            f"""
            INSERT INTO wallets ({_WALLET_COLUMNS})
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (wallet.id, wallet.public_key, wallet.private_key_encrypted, wallet.created_at),
        )
        return _row_to_wallet(cursor.fetchone())

    def get(self, wallet_id: UUID) -> Wallet | None:
        """La wallet con ese identificador, o `None` si no existe."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM wallets WHERE id = %s", (wallet_id,))
        row = cursor.fetchone()
        return _row_to_wallet(row) if row is not None else None

    def get_by_public_key(self, public_key: str) -> Wallet | None:
        """La wallet con esa pública, o `None`: es el índice único del esquema el que busca."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM wallets WHERE public_key = %s", (public_key,))
        row = cursor.fetchone()
        return _row_to_wallet(row) if row is not None else None

    def list(self, limit: int = 100) -> Sequence[Wallet]:
        """Las wallets registradas, de la más antigua a la más nueva."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            "SELECT * FROM wallets ORDER BY created_at, id LIMIT %s",
            (limit,),
        )
        return [_row_to_wallet(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Cuántas wallets hay registradas."""
        return self._connection.execute("SELECT count(*) FROM wallets").fetchone()[0]


class PostgresBlockRepository:
    """Repositorio de bloques sobre PostgreSQL (REQ-07, REQ-08, REQ-14)."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    def add(self, block: Block) -> Block:
        """Escribe el bloque y devuelve la fila escrita."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            f"""
            INSERT INTO blocks ({_BLOCK_COLUMNS})
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (block.id, block.block_index, block.timestamp, block.previous_hash, block.hash),
        )
        return _row_to_block(cursor.fetchone())

    def get_by_index(self, block_index: int) -> Block | None:
        """El bloque de ese índice, o `None` si la cadena no llega hasta ahí."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM blocks WHERE block_index = %s", (block_index,))
        row = cursor.fetchone()
        return _row_to_block(row) if row is not None else None

    def last(self) -> Block | None:
        """El bloque de índice mayor, que es el último eslabón; `None` si no hay cadena."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM blocks ORDER BY block_index DESC LIMIT 1")
        row = cursor.fetchone()
        return _row_to_block(row) if row is not None else None

    def list(self) -> Sequence[Block]:
        """La cadena completa, del génesis al último bloque."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM blocks ORDER BY block_index")
        return [_row_to_block(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Cuántos bloques tiene la cadena."""
        return self._connection.execute("SELECT count(*) FROM blocks").fetchone()[0]


class PostgresTransactionRepository:
    """Repositorio de transacciones sobre PostgreSQL (REQ-03, REQ-05, REQ-11, REQ-13)."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    def add(self, transaction: Transaction) -> Transaction:
        """Escribe la transacción con su estado; una `rejected` se guarda sin bloque (REQ-11)."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            f"""
            INSERT INTO transactions ({_TRANSACTION_COLUMNS})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                transaction.id,
                transaction.sender_id,
                transaction.receiver_id,
                transaction.amount,
                transaction.status.value,
                transaction.signature,
                transaction.block_id,
                transaction.created_at,
            ),
        )
        return _row_to_transaction(cursor.fetchone())

    def confirm(self, transaction_ids: Sequence[UUID], block_id: UUID) -> int:
        """Liga las transacciones pendientes al bloque y devuelve cuántas confirmó.

        Solo toca las `pending`: una transacción ya confirmada no se mueve de su
        bloque, y la que estaba `rejected` tampoco entra a la cadena.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            """
            UPDATE transactions
            SET status = 'confirmed', block_id = %s
            WHERE id = ANY(%s) AND status = 'pending'
            """,
            (block_id, list(transaction_ids)),
        )
        return cursor.rowcount

    def get(self, transaction_id: UUID) -> Transaction | None:
        """La transacción con ese identificador, o `None` si no existe."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,))
        row = cursor.fetchone()
        return _row_to_transaction(row) if row is not None else None

    def list(
        self,
        *,
        status: TransactionStatus | None = None,
        wallet_id: UUID | None = None,
        limit: int = 100,
        newest_first: bool = False,
    ) -> Sequence[Transaction]:
        """Las transacciones que cumplen los filtros, de la más antigua a la más nueva.

        `wallet_id` mira las dos direcciones: el historial de una wallet son sus
        envíos y sus recepciones (REQ-13). Con `newest_first` el orden se invierte en
        la consulta y no después, para que el `LIMIT` deje fuera las más viejas.
        """
        condiciones: list[str] = []
        parametros: list[Any] = []
        if status is not None:
            condiciones.append("status = %s")
            parametros.append(status.value)
        if wallet_id is not None:
            condiciones.append("(sender_id = %s OR receiver_id = %s)")
            parametros.extend((wallet_id, wallet_id))
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        parametros.append(limit)
        orden = "created_at DESC, id DESC" if newest_first else "created_at, id"

        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            f"SELECT * FROM transactions {where} ORDER BY {orden} LIMIT %s",
            parametros,
        )
        return [_row_to_transaction(row) for row in cursor.fetchall()]

    def pending(self) -> Sequence[Transaction]:
        """Las transacciones del pool, las que un bloque puede agrupar."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            "SELECT * FROM transactions WHERE status = 'pending' ORDER BY created_at, id"
        )
        return [_row_to_transaction(row) for row in cursor.fetchall()]

    def of_block(self, block_id: UUID) -> Sequence[Transaction]:
        """Las transacciones que ese bloque agrupa."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            "SELECT * FROM transactions WHERE block_id = %s ORDER BY created_at, id",
            (block_id,),
        )
        return [_row_to_transaction(row) for row in cursor.fetchall()]

    def balance_terms(self, wallet_id: UUID) -> BalanceTerms:
        """Las tres sumas del saldo disponible (REQ-05) en una sola consulta.

        Las sumas van contra `transactions` y la wallet entra solo por el `WHERE`, sin
        ninguna tabla que multiplicar: una wallet sin movimientos devuelve ceros
        porque `SUM` sobre cero filas es `NULL` y el `COALESCE` lo lleva a cero, no
        porque haya una fila artificial. `pending_out` solo cuenta las pendientes
        porque lo confirmado en contra ya está en `confirmed_out`; sumar las dos sería
        contar dos veces lo mismo.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE WHEN t.receiver_id = %s AND t.status = 'confirmed' THEN t.amount END
                ), 0) AS confirmed_in,
                COALESCE(SUM(
                    CASE WHEN t.sender_id = %s AND t.status = 'confirmed' THEN t.amount END
                ), 0) AS confirmed_out,
                COALESCE(SUM(
                    CASE WHEN t.sender_id = %s AND t.status = 'pending' THEN t.amount END
                ), 0) AS pending_out
            FROM transactions t
            WHERE t.sender_id = %s OR t.receiver_id = %s
            """,
            (wallet_id, wallet_id, wallet_id, wallet_id, wallet_id),
        )
        row = cursor.fetchone()
        return BalanceTerms(
            confirmed_in=row["confirmed_in"],
            confirmed_out=row["confirmed_out"],
            pending_out=row["pending_out"],
        )

    def signature_exists(self, signature: str) -> bool:
        """Si esa firma ya está registrada; el dominio lo consulta antes de escribir (REQ-03)."""
        return (
            self._connection.execute(
                "SELECT 1 FROM transactions WHERE signature = %s LIMIT 1", (signature,)
            ).fetchone()
            is not None
        )

    def count(self) -> int:
        """Cuántas transacciones hay registradas, en cualquier estado."""
        return self._connection.execute("SELECT count(*) FROM transactions").fetchone()[0]
