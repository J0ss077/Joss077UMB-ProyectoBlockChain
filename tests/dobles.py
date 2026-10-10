"""Dobles en memoria de los repositorios: dominio y verificación sin base (REQ-17).

La verificación de REQ-10 necesita una cadena que se pueda alterar a mano sin
tocar PostgreSQL, y el dominio solo conoce los protocolos de
`src/persistence/ports.py` (REQ-16): estos dobles los implementan sobre listas y
`build_chain` arma una `Blockchain` que los usa.
"""
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cryptography.fernet import Fernet

from src.domain.block import Block
from src.domain.blockchain import GENESIS_PREVIOUS_HASH, BalanceTerms, Blockchain
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import Wallet

# Reloj fijo de la cadena de prueba: la marca de tiempo entra en el hash del
# bloque, así que fijarla hace que la cadena sea la misma en cada corrida.
BLOCK_AT = datetime(2026, 10, 10, 13, 0, tzinfo=UTC)


class InMemoryWalletRepository:
    """`WalletRepository` sobre una lista (REQ-16)."""

    def __init__(self, wallets: Sequence[Wallet] = ()) -> None:
        self.rows = list(wallets)

    def add(self, wallet: Wallet) -> Wallet:
        self.rows.append(wallet)
        return wallet

    def get(self, wallet_id: UUID) -> Wallet | None:
        return next((wallet for wallet in self.rows if wallet.id == wallet_id), None)

    def get_by_public_key(self, public_key: str) -> Wallet | None:
        return next(
            (wallet for wallet in self.rows if wallet.public_key == public_key), None
        )

    def list(self, limit: int = 100) -> Sequence[Wallet]:
        return self.rows[:limit]

    def count(self) -> int:
        return len(self.rows)


class InMemoryBlockRepository:
    """`BlockRepository` sobre una lista; ordena por índice, como la cadena real."""

    def __init__(self, blocks: Sequence[Block] = ()) -> None:
        self.rows = list(blocks)

    def add(self, block: Block) -> Block:
        self.rows.append(block)
        return block

    def get_by_index(self, block_index: int) -> Block | None:
        return next(
            (block for block in self.rows if block.block_index == block_index), None
        )

    def last(self) -> Block | None:
        return max(self.rows, key=lambda block: block.block_index, default=None)

    def list(self) -> Sequence[Block]:
        return sorted(self.rows, key=lambda block: block.block_index)

    def count(self) -> int:
        return len(self.rows)


class InMemoryTransactionRepository:
    """`TransactionRepository` sobre una lista (REQ-03, REQ-05, REQ-11, REQ-13)."""

    def __init__(self, transactions: Sequence[Transaction] = ()) -> None:
        self.rows = list(transactions)

    def add(self, transaction: Transaction) -> Transaction:
        self.rows.append(transaction)
        return transaction

    def confirm(self, transaction_ids: Sequence[UUID], block_id: UUID) -> int:
        ids = set(transaction_ids)
        confirmadas = 0
        for transaction in self.rows:
            if transaction.id in ids and transaction.status is TransactionStatus.PENDING:
                transaction.status = TransactionStatus.CONFIRMED
                transaction.block_id = block_id
                confirmadas += 1
        return confirmadas

    def get(self, transaction_id: UUID) -> Transaction | None:
        return next((t for t in self.rows if t.id == transaction_id), None)

    def list(
        self,
        *,
        status: TransactionStatus | None = None,
        wallet_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[Transaction]:
        filas = [
            transaction
            for transaction in self.rows
            if (status is None or transaction.status is status)
            and (
                wallet_id is None
                or wallet_id in (transaction.sender_id, transaction.receiver_id)
            )
        ]
        return filas[:limit]

    def pending(self) -> Sequence[Transaction]:
        return [t for t in self.rows if t.status is TransactionStatus.PENDING]

    def of_block(self, block_id: UUID) -> Sequence[Transaction]:
        return [t for t in self.rows if t.block_id == block_id]

    def balance_terms(self, wallet_id: UUID) -> BalanceTerms:
        def total(**match: object) -> Decimal:
            return sum(
                (
                    transaction.amount
                    for transaction in self.rows
                    if all(
                        getattr(transaction, campo) == valor
                        for campo, valor in match.items()
                    )
                ),
                Decimal("0"),
            )

        return BalanceTerms(
            confirmed_in=total(receiver_id=wallet_id, status=TransactionStatus.CONFIRMED),
            confirmed_out=total(sender_id=wallet_id, status=TransactionStatus.CONFIRMED),
            pending_out=total(sender_id=wallet_id, status=TransactionStatus.PENDING),
        )

    def signature_exists(self, signature: str) -> bool:
        return any(t.signature == signature for t in self.rows)

    def count(self) -> int:
        return len(self.rows)


class InMemoryUnitOfWork:
    """`UnitOfWork` sobre los mismos dobles: agrupa el trabajo y no hay motor que confirmar."""

    def __init__(
        self,
        wallets: InMemoryWalletRepository,
        blocks: InMemoryBlockRepository,
        transactions: InMemoryTransactionRepository,
    ) -> None:
        self.wallets = wallets
        self.blocks = blocks
        self.transactions = transactions

    def __enter__(self) -> "InMemoryUnitOfWork":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def build_chain(
    *,
    blocks: Sequence[Block] = (),
    transactions: Sequence[Transaction] = (),
) -> Blockchain:
    """Ledger sobre dobles en memoria, con la cadena que se le pase ya poblada."""
    wallets = InMemoryWalletRepository()
    block_repository = InMemoryBlockRepository(blocks)
    transaction_repository = InMemoryTransactionRepository(transactions)
    return Blockchain(
        wallets=wallets,
        blocks=block_repository,
        transactions=transaction_repository,
        unit_of_work=lambda: InMemoryUnitOfWork(
            wallets, block_repository, transaction_repository
        ),
        master_key=Fernet.generate_key(),
        clock=lambda: BLOCK_AT,
    )


def build_block(
    block_index: int,
    previous: Block | None = None,
    *,
    transactions: Sequence[Transaction] = (),
    previous_hash: str | None = None,
    timestamp: datetime = BLOCK_AT,
) -> Block:
    """Bloque con su hash calculado sobre las transacciones que agrupa.

    `previous` es el eslabón anterior y aporta el `previous_hash`; sin él, el hash
    previo es el de sesenta y cuatro ceros del génesis. Pasar `previous_hash` a
    mano es lo que permite armar un eslabón huérfano a propósito.
    """
    if previous_hash is None:
        previous_hash = GENESIS_PREVIOUS_HASH if previous is None else previous.hash
    block = Block(
        id=uuid4(),
        block_index=block_index,
        timestamp=timestamp,
        previous_hash=previous_hash,
        hash="",
    )
    block.hash = block.calculate_hash(transactions)
    return block
