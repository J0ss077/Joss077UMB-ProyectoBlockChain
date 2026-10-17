"""Fachada del ledger: saldo disponible, pool, agrupación atómica y génesis.

Reúne las reglas que el CU-02 y el CU-03 necesitan detrás de una sola clase, para
que la presentación no decida nada: `create_transaction` valida y firma con el
saldo disponible del emisor (REQ-04, REQ-05, REQ-06), `acreditar` emite el saldo
de bienvenida en un bloque propio sin pasar por esa regla (REQ-33) y
`group_pending` encadena un bloque nuevo con el último (REQ-08), confirma las
transacciones del pool (REQ-09) y hace las dos escrituras dentro de una sola
transacción de base de datos (REQ-18). `ensure_genesis` registra el eslabón cero
de forma idempotente (REQ-14) y `verify_chain` recalcula la cadena y localiza la
alteración sin escribir nada (REQ-10, REQ-22).

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
        validación. El resultado lleva el motivo en todos los rechazos, pero la fila
        `rejected` solo se escribe cuando el esquema la admite; cuando no, `stored`
        queda nulo y no se escribe nada. La firma repetida nunca se escribe, aunque
        la validación haya dado antes otro motivo, porque el índice único ya la
        tiene (REQ-03 y REQ-19).
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

        # La consulta se guarda porque decide dos cosas: el motivo que devuelve la
        # validación y si la fila se puede escribir.
        signature_exists = self.transactions.signature_exists(transaction.signature)
        validation = transaction.validate(
            sender_public_key=None if sender is None else sender.public_key,
            receiver_public_key=None if receiver is None else receiver.public_key,
            available=available_balance(self.transactions.balance_terms(sender_id)),
            signature_exists=signature_exists,
        )
        if validation.accepted:
            return TransactionResult(True, None, self.transactions.add(transaction))
        if signature_exists:
            # La repetición se informa aunque la validación haya dado antes otro
            # motivo —el saldo se revisa antes que la firma—: escribir la fila
            # `rejected` haría subir la violación del índice único en vez del motivo
            # que el CU-02 pide mostrar.
            return TransactionResult(False, RejectionReason.DUPLICATE_SIGNATURE, None)
        if validation.reason in REASONS_STORING_REJECTED:
            transaction.status = TransactionStatus.REJECTED
            return TransactionResult(
                False, validation.reason, self.transactions.add(transaction)
            )
        return TransactionResult(False, validation.reason, None)

    def acreditar(
        self, *, emisor_id: UUID, destino_id: UUID, monto: Decimal
    ) -> Block:
        """Emite saldo desde el emisor al destino en un bloque propio (REQ-33).

        Es la única operación que acredita sin pasar por la regla de saldo: el
        emisor es la puerta por la que el capital entra al ledger y el diseño lo
        admite en negativo. La transacción se firma con el mismo camino que
        `create_transaction` —se descifra la privada del emisor y se firma la forma
        canónica— y se escribe ya confirmada, ligada a un bloque calculado sobre
        ella y sólo ella. Agrupar el pool no sirve para esto: el saldo disponible
        sólo cuenta lo confirmado, y arrastrar las pendientes haría que el crédito
        dependiera de lo que haya en el pool.

        Las dos escrituras van por los repositorios que recibió la fachada y no por
        una unidad de trabajo propia: la aprobación de REQ-33 abre la transacción
        de base y necesita que estas filas caigan dentro de ella.
        """
        emisor = self.wallets.get(emisor_id)
        destino = self.wallets.get(destino_id)
        if emisor is None or destino is None:
            # Es un error de armado y no un rechazo de negocio: quien emite crea el
            # destino en la misma operación, así que una wallet que falta no se
            # informa con un motivo sino que se detiene antes de escribir.
            raise ValueError("el emisor y el destino de la emisión tienen que existir")

        # La transacción nace como cualquier otra y se confirma recién cuando el
        # bloque está calculado: la firma y el hash cubren la forma canónica, que no
        # incluye el estado ni el bloque, y eso es lo que permite ligarla después.
        transaction = Transaction(
            id=uuid4(),
            sender_id=emisor_id,
            receiver_id=destino_id,
            amount=monto,
            status=TransactionStatus.PENDING,
            signature="",
            block_id=None,
            created_at=self._clock(),
        )
        transaction.signature = sign_payload(
            emisor,
            transaction.signing_payload(emisor.public_key, destino.public_key),
            self._master_key,
        )

        last = self.blocks.last()
        block = self._build_block(
            block_index=0 if last is None else last.block_index + 1,
            previous_hash=GENESIS_PREVIOUS_HASH if last is None else last.hash,
            transactions=[transaction],
        )
        transaction.status = TransactionStatus.CONFIRMED
        transaction.block_id = block.id

        # El bloque primero: la clave foránea de la transacción lo referencia.
        self.blocks.add(block)
        self.transactions.add(transaction)
        return block

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

        La cabeza tiene que ser el génesis: índice cero y hash previo de sesenta y
        cuatro ceros. Sin esa comprobación, borrar el eslabón cero deja una cadena
        1..n con todos sus hashes intactos y la alteración pasaría inadvertida
        (decisión 13). El recorte por la cola queda fuera de alcance: para notarlo
        habría que saber cuál era el último bloque y el historial no lo guarda.

        En el recorrido, cada bloque se recalcula con las transacciones que tiene
        ligadas y se compara con el hash guardado; el encadenamiento compara el
        `previous_hash` con el del bloque anterior **y** que el índice sea el
        siguiente, porque un hueco en los índices no cambia ningún hash y una cadena
        0, 1, 3 se vería válida (RF-3). El génesis también se recalcula: sin eso,
        alterar su marca de tiempo dejando su hash intacto pasaría inadvertido
        (decisión 13).

        Solo lee (REQ-22) y, ante la primera discrepancia, detiene el recorrido y
        devuelve su índice; seguir no cambia el dictamen.
        """
        blocks = self.blocks.list()
        if not blocks:
            # Sin ningún bloque falta el eslabón cero, que es el que se señala.
            return VerificationReport(valid=False, altered_block_index=0)
        head = blocks[0]
        if head.block_index != 0 or head.previous_hash != GENESIS_PREVIOUS_HASH:
            return VerificationReport(valid=False, altered_block_index=head.block_index)

        anterior: Block | None = None
        for block in blocks:
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
