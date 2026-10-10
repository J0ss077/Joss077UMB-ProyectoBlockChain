"""Fachada del ledger: saldo disponible, pool, agrupación atómica y génesis.

Reúne las reglas que el CU-02 y el CU-03 necesitan detrás de una sola clase, para
que la presentación no decida nada: `create_transaction` valida y firma con el
saldo disponible del emisor (REQ-04, REQ-05, REQ-06) y `group_pending` encadena un
bloque nuevo con el último (REQ-08), confirma las transacciones del pool (REQ-09)
y hace las dos escrituras dentro de una sola transacción de base de datos
(REQ-18). `ensure_genesis` registra el eslabón cero de forma idempotente (REQ-14)
y `verify_chain` recalcula la cadena y localiza la alteración sin escribir nada
(REQ-10, REQ-22).

El dominio no conoce el motor: habla con los protocolos de
`src/persistence/ports.py` (REQ-16), y por eso la agrupación recibe una fábrica de
unidad de trabajo y no una conexión.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.block import Block
from src.domain.transaction import (
    RejectionReason,
    Transaction,
    TransactionStatus,
)
from src.domain.wallet import Wallet, create_wallet, sign_payload

if TYPE_CHECKING:
    # Solo para las anotaciones: importar los protocolos en tiempo de ejecución
    # cerraría el ciclo ports -> blockchain -> ports (y no hace falta, REQ-16).
    from src.persistence.ports import (
        BlockRepository,
        TransactionRepository,
        UnitOfWork,
        WalletRepository,
    )

# Hash previo del génesis: sesenta y cuatro ceros porque no tiene predecesor (REQ-14).
GENESIS_PREVIOUS_HASH = "0" * 64

# Motivos que el esquema sí admite guardar en una fila `rejected`. Los demás los
# impide el propio motor —el CHECK del monto, el del emisor distinto del receptor,
# las claves foráneas y el índice único de la firma—, así que se informan sin
# escribir y el error del motor queda como el respaldo que REQ-19 exige poder
# comprobar (sección "Conducta observable ante una transacción inválida").
REASONS_STORING_REJECTED = frozenset(
    {RejectionReason.BAD_SIGNATURE, RejectionReason.INSUFFICIENT_FUNDS}
)


@dataclass(frozen=True, slots=True)
class BalanceTerms:
    """Las tres sumas con las que se calcula el saldo disponible de una wallet."""

    confirmed_in: Decimal
    confirmed_out: Decimal
    pending_out: Decimal


def available_balance(terms: BalanceTerms) -> Decimal:
    """Saldo disponible: lo confirmado a favor menos lo comprometido (REQ-05, REQ-06).

    Descontar `pending_out` es lo que hace que dos transacciones que juntas
    exceden el saldo no pasen las dos: la primera ya comprometió su monto.
    """
    return terms.confirmed_in - terms.confirmed_out - terms.pending_out


@dataclass(frozen=True, slots=True)
class TransactionResult:
    """Resultado de proponer una transacción: si se aceptó, por qué no y qué quedó guardado.

    `stored` es nulo cuando el rechazo no dejó fila porque el esquema no la
    admitiría; el motivo igual viaja para que quien propuso sepa qué pasó (CU-02).
    """

    accepted: bool
    reason: RejectionReason | None
    stored: Transaction | None


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Dictamen de integridad: si la cadena es válida y, si no, dónde empieza la alteración.

    `altered_block_index` es nulo cuando la cadena es válida y el índice del primer
    bloque que no encaja cuando no lo es (REQ-10).
    """

    valid: bool
    altered_block_index: int | None


class Blockchain:
    """Fachada del ledger: las reglas de los casos de uso CU-02 a CU-04 en un punto de entrada.

    Invariante: las lecturas usan los repositorios que recibe; las dos escrituras
    de la agrupación pasan por la unidad de trabajo, que es lo que las hace
    atómicas (REQ-18); la verificación no escribe nada (REQ-22).
    """

    def __init__(
        self,
        *,
        wallets: WalletRepository,
        blocks: BlockRepository,
        transactions: TransactionRepository,
        unit_of_work: Callable[[], UnitOfWork],
        master_key: bytes,
        clock: Callable[[], datetime],
    ) -> None:
        self.wallets = wallets
        self.blocks = blocks
        self.transactions = transactions
        self._unit_of_work = unit_of_work
        self._master_key = master_key
        self._clock = clock

    def register_wallet(self) -> Wallet:
        """Genera el par, cifra la privada y registra la wallet (CU-01, REQ-01).

        El identificador y la marca de tiempo los pone el dominio y no el valor por
        defecto del esquema: el camino real conoce la fila antes de escribirla
        (decisión 5).
        """
        return self.wallets.add(
            create_wallet(master_key=self._master_key, created_at=self._clock())
        )

    def create_transaction(
        self,
        *,
        sender_id: UUID,
        receiver_id: UUID,
        amount: Decimal,
        transaction_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> TransactionResult:
        """Valida, firma y decide qué fila queda (CU-02, REQ-02, REQ-04, REQ-05, REQ-11).

        Se firma antes de validar porque comprobar la firma es parte de la
        validación. El resultado lleva el motivo en todos los rechazos, pero la
        fila `rejected` solo se escribe cuando el esquema la admite; cuando no,
        `stored` queda nulo y no se escribe nada, y quien responde por la
        restricción es el motor (REQ-19).
        """
        sender = self.wallets.get(sender_id)
        receiver = self.wallets.get(receiver_id)
        transaction = Transaction(
            id=transaction_id if transaction_id is not None else uuid4(),
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount=amount,
            status=TransactionStatus.PENDING,
            signature="",
            block_id=None,
            created_at=created_at if created_at is not None else self._clock(),
        )
        # Sin las dos públicas no hay nada que firmar; la validación lo rechaza por
        # wallet inexistente antes de llegar a la firma.
        if sender is not None and receiver is not None:
            transaction.signature = sign_payload(
                sender,
                transaction.signing_payload(sender.public_key, receiver.public_key),
                self._master_key,
            )

        validation = transaction.validate(
            sender_public_key=None if sender is None else sender.public_key,
            receiver_public_key=None if receiver is None else receiver.public_key,
            available=available_balance(self.transactions.balance_terms(sender_id)),
            signature_exists=self.transactions.signature_exists(transaction.signature),
        )
        if validation.accepted:
            return TransactionResult(True, None, self.transactions.add(transaction))
        if validation.reason in REASONS_STORING_REJECTED:
            transaction.status = TransactionStatus.REJECTED
            return TransactionResult(
                False, validation.reason, self.transactions.add(transaction)
            )
        return TransactionResult(False, validation.reason, None)

    def group_pending(self) -> Block | None:
        """Agrupa el pool en un bloque nuevo encadenado al último (CU-03, REQ-08, REQ-09).

        Con el pool vacío no se crea bloque: es el flujo alterno del CU-03. Las dos
        escrituras —el bloque y la confirmación de sus transacciones— van dentro de
        una sola unidad de trabajo, y el `commit` único es lo que hace cierto a
        REQ-18: si la confirmación falla, el ROLLBACK del contexto deshace el
        bloque insertado y las transacciones siguen en el pool.
        """
        pending = self.transactions.pending()
        if not pending:
            return None

        last = self.blocks.last()
        block = self._build_block(
            block_index=0 if last is None else last.block_index + 1,
            previous_hash=GENESIS_PREVIOUS_HASH if last is None else last.hash,
            transactions=pending,
        )
        with self._unit_of_work() as work:
            work.blocks.add(block)
            work.transactions.confirm(
                [transaction.id for transaction in pending], block.id
            )
            work.commit()
        return block

    def verify_chain(self) -> VerificationReport:
        """Recalcula la cadena y localiza el primer bloque que no encaja (CU-04, REQ-10).

        Para cada bloque recalcula su hash propio con las transacciones que tiene
        ligadas y lo compara con el guardado, y encadena cada eslabón con el hash
        del anterior comparando también el índice: un hueco en los índices no
        cambia ningún hash, así que sin esa comparación una cadena 0, 1, 3 se vería
        válida (RF-3). Recalcula además el hash del génesis: el CU-04 habla de
        "para cada bloque desde el índice 1" porque describe el encadenamiento,
        pero sin recalcular el eslabón cero alterar su marca de tiempo dejando el
        hash guardado intacto pasaría inadvertido (decisión 13).

        Solo lee: no escribe ni confirma nada (REQ-22). Ante la primera
        discrepancia detiene el recorrido y devuelve su índice; seguir no cambia el
        dictamen.
        """
        anterior: Block | None = None
        for block in self.blocks.list():
            if block.calculate_hash(self.transactions.of_block(block.id)) != block.hash:
                return VerificationReport(valid=False, altered_block_index=block.block_index)
            if anterior is not None:
                if block.previous_hash != anterior.hash:
                    return VerificationReport(
                        valid=False, altered_block_index=block.block_index
                    )
                if block.block_index != anterior.block_index + 1:
                    return VerificationReport(
                        valid=False, altered_block_index=block.block_index
                    )
            anterior = block
        return VerificationReport(valid=True, altered_block_index=None)

    def wallet_history(self, wallet_id: UUID) -> Sequence[Transaction]:
        """Los envíos y las recepciones de una wallet, en cualquier estado (CU-05, REQ-13)."""
        return self.transactions.list(wallet_id=wallet_id)

    def available_balance(self, wallet_id: UUID) -> Decimal:
        """Saldo disponible de una wallet: confirma a favor menos lo comprometido (REQ-05).

        Es la misma cuenta que usa `create_transaction` para decidir si acepta una
        transacción; se expone aquí para que el arranque y la presentación puedan
        consultarla sin volver a armarla por su cuenta.
        """
        return available_balance(self.transactions.balance_terms(wallet_id))

    def ledger_state(self) -> dict[str, int]:
        """Cuántas filas tiene cada tabla, para la portada y para las pruebas (REQ-13)."""
        return {
            "wallets": self.wallets.count(),
            "blocks": self.blocks.count(),
            "transactions": self.transactions.count(),
        }

    def _build_block(
        self, *, block_index: int, previous_hash: str, transactions: Sequence[Transaction]
    ) -> Block:
        """Arma el bloque con su hash ya calculado; no lo escribe.

        El hash se calcula antes de insertar porque cubre solo la forma canónica de
        las transacciones, no su estado ni su bloque: eso es lo que permite
        confirmarlas después sin invalidarlo.
        """
        block = Block(
            id=uuid4(),
            block_index=block_index,
            timestamp=self._clock(),
            previous_hash=previous_hash,
            hash="",
        )
        block.hash = block.calculate_hash(transactions)
        return block


def ensure_genesis(chain: Blockchain) -> Block:
    """Registra el bloque génesis si no existe y devuelve el que haya (REQ-14).

    Es idempotente porque el arranque se puede repetir: si el eslabón cero ya
    está, no se escribe otro. El génesis lo crea la aplicación y no `db/init.sql`
    porque su hash es un cálculo (decisión 7) y porque REQ-15 prohíbe el DDL desde
    el código.
    """
    genesis = chain.blocks.get_by_index(0)
    if genesis is not None:
        return genesis
    return chain.blocks.add(
        chain._build_block(
            block_index=0, previous_hash=GENESIS_PREVIOUS_HASH, transactions=[]
        )
    )
