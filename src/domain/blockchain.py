"""Fachada del ledger: saldo disponible, pool, agrupación atómica y génesis.

Reúne las reglas que el CU-02 y el CU-03 necesitan detrás de una sola clase, para
que la presentación no decida nada: `create_transaction` valida y firma con el
saldo disponible del emisor (REQ-04, REQ-05, REQ-06), `acreditar` emite el saldo
de bienvenida en un bloque propio sin pasar por esa regla (REQ-33) y
`group_pending` encadena un bloque nuevo con el último (REQ-08), confirma las
transacciones del pool (REQ-09) y hace las dos escrituras dentro de una sola
transacción de base de datos (REQ-18). `ensure_genesis` registra el eslabón cero
de forma idempotente (REQ-14), `verify_chain` recalcula la cadena y localiza la
alteración sin escribir nada (REQ-10, REQ-22) y `audit_chain` enumera todo lo que la
cadena y el pool tienen mal, también sin escribir (REQ-22). Las reparaciones guiadas
—`repair_chain`, `isolate_invalid_transactions`, `reject_invalid_pending` y
`repair_all`— son las únicas escrituras de recuperación: cada una va dentro de una
sola unidad de trabajo y reescribe hashes o estados sin tocar índices ni marcas de
tiempo.

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
    # La auditoría importa este módulo para reutilizar la fachada; acá se importa
    # solo para anotar y el import real es local al método, para no cerrar el ciclo.
    from src.domain.auditoria import Auditoria, Sello

    # Igual que `auditoria`: `reparacion` importa este módulo para el hash del
    # génesis, así que el import real es local a cada método.
    from src.domain.reparacion import Reparacion

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

        Las precondiciones de la emisión —monto positivo y emisor distinto del
        destino— se validan antes de leer o escribir nada. El CHECK del esquema
        también las rechaza, pero este camino no tiene unidad de trabajo propia: si
        se dejara al motor, el bloque ya estaría escrito cuando la transacción
        violara la restricción, y una llamada directa fallida dejaría un eslabón
        huérfano en la cadena.
        """
        if monto <= 0:
            raise ValueError("el monto de la emisión tiene que ser positivo")
        if emisor_id == destino_id:
            raise ValueError(
                "el emisor y el destino de la emisión tienen que ser distintos"
            )

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

    def audit_chain(
        self,
        *,
        sello: Sello | None = None,
        problema_del_sello: str | None = None,
    ) -> Auditoria:
        """Audita todos los bloques y el pool sin escribir nada (REQ-22).

        Delega en `src.domain.auditoria` con los tres repositorios de la fachada y el
        sello ya leído. El import es local porque `auditoria` importa de este módulo:
        hacerlo arriba cerraría el ciclo `blockchain -> auditoria -> blockchain`.

        `sello` es el ancla externa contra el recorte de la cola y
        `problema_del_sello` dice si no se pudo leer; con un problema, la auditoría
        lo trata como ausente y declara el límite del recorte. La auditoría no escribe
        tablas ni el sello: las reparaciones son un paso aparte y explícito.
        """
        from src.domain.auditoria import auditar

        return auditar(
            blocks=self.blocks,
            transactions=self.transactions,
            wallets=self.wallets,
            sello=sello,
            problema_del_sello=problema_del_sello,
        )

    def repair_chain(self) -> Reparacion:
        """«encadenar»: recalcula los hashes de la cadena en orden y escribe los cambios.

        Sin bloques, crea el génesis como el arranque (`ensure_genesis`). Si el
        primer bloque no es el índice 0 no aplica y lo explica: renumerar cambiaría el
        hash de cada eslabón y reasignaría la historia, así que un hueco de índices se
        declara y queda. En el caso normal recalcula `previous_hash` y `hash` con las
        transacciones agrupadas por `block_id` —una sola lectura de `all()`— y escribe
        con `set_hashes` solo los bloques que cambian, todo dentro de una sola unidad
        de trabajo. No toca el reloj ni las marcas de tiempo y no toca los índices.
        """
        from src.domain.auditoria import ENCADENAR
        from src.domain.reparacion import (
            Reparacion,
            agrupar_por_bloque,
            detalle_de_encadenado,
            recalcular_cadena,
        )

        if not self.blocks.list():
            ensure_genesis(self)
            return Reparacion(
                accion=ENCADENAR,
                aplicada=True,
                detalle="No había ningún bloque: se creó el génesis.",
                cambios=1,
            )

        with self._unit_of_work() as work:
            bloques = list(work.blocks.list())
            if bloques[0].block_index != 0:
                return Reparacion(
                    accion=ENCADENAR,
                    aplicada=False,
                    detalle=(
                        f"El primer bloque es el {bloques[0].block_index} y no el "
                        "génesis: el reencadenado no se aplica y no se renumera."
                    ),
                    cambios=0,
                )
            transacciones = list(work.transactions.all())
            reencadenado = recalcular_cadena(
                bloques, agrupar_por_bloque(transacciones)
            )
            for original, nuevo in zip(
                bloques, reencadenado.bloques, strict=True
            ):
                if (original.previous_hash, original.hash) != (
                    nuevo.previous_hash,
                    nuevo.hash,
                ):
                    work.blocks.set_hashes(nuevo)
            work.commit()

        return Reparacion(
            accion=ENCADENAR,
            aplicada=reencadenado.cambios > 0,
            detalle=detalle_de_encadenado(reencadenado),
            cambios=reencadenado.cambios,
        )

    def isolate_invalid_transactions(self) -> Reparacion:
        """«aislar»: pasa a `rejected` las confirmadas inválidas y reencadena los bloques.

        Revalida firma, monto, wallets y coherencia estado/bloque de cada confirmada
        y rechaza las que no pertenecen a la cadena; después recalcula los hashes de
        todos los bloques porque su contenido cambió. Las dos escrituras van dentro de
        una sola unidad de trabajo, así que no queda una transacción rechazada con su
        bloque viejo ni un bloque con un hash que ya no corresponde.

        El reencadenado solo se aplica si la cadena empieza en el bloque 0: sin el
        génesis, recalcular encadenaría el primer bloque que haya a los ceros del
        eslabón cero, fabricaría un encadenamiento que nunca existió y borraría el
        rastro de la cabeza eliminada. En ese caso se rechazan las inválidas y se
        informa que el reencadenado no se aplicó.
        """
        from src.domain.auditoria import AISLAR
        from src.domain.reparacion import (
            Reparacion,
            agrupar_por_bloque,
            cantidad,
            detalle_de_huecos,
            esta_desencajada,
            recalcular_cadena,
            se_puede_reencadenar,
        )

        with self._unit_of_work() as work:
            bloques = list(work.blocks.list())
            ids_de_bloques = {bloque.id for bloque in bloques}
            filas = list(work.transactions.all())
            cache: dict[UUID, Wallet | None] = {}
            invalidas = [
                fila
                for fila in filas
                if fila.status is TransactionStatus.CONFIRMED
                and (
                    esta_desencajada(fila, ids_de_bloques=ids_de_bloques)
                    or self._motivo_de_invalidez(fila, cache) is not None
                )
            ]
            if not invalidas:
                return Reparacion(
                    accion=AISLAR,
                    aplicada=False,
                    detalle=(
                        "No hay transacciones confirmadas inválidas: no se aisló "
                        "ninguna."
                    ),
                    cambios=0,
                )
            aisladas = {fila.id for fila in invalidas}
            work.transactions.reject([fila.id for fila in invalidas])
            # Sin el génesis no se recalcula nada: encadenar el primer bloque a los
            # ceros del eslabón cero inventaría un encadenamiento y borraría el
            # rastro de la cabeza eliminada.
            reencadenado = None
            if se_puede_reencadenar(bloques):
                # Las rechazadas ya no agrupan, aunque la lectura se hizo antes del
                # UPDATE: el hash del bloque se calcula con lo que queda en él.
                por_bloque = agrupar_por_bloque(
                    [fila for fila in filas if fila.id not in aisladas]
                )
                reencadenado = recalcular_cadena(bloques, por_bloque)
                for original, nuevo in zip(
                    bloques, reencadenado.bloques, strict=True
                ):
                    if (original.previous_hash, original.hash) != (
                        nuevo.previous_hash,
                        nuevo.hash,
                    ):
                        work.blocks.set_hashes(nuevo)
            work.commit()

        detalle = (
            "Se aislaron "
            f"{cantidad(len(invalidas), 'transacción', 'transacciones')}."
        )
        if reencadenado is None:
            detalle += (
                " El reencadenado no se aplicó porque la cadena no empieza en el "
                "génesis: no se renumera."
            )
            cambios = len(invalidas)
        else:
            if reencadenado.cambios:
                detalle += (
                    " Se reencadenaron "
                    f"{cantidad(reencadenado.cambios, 'bloque', 'bloques')}."
                )
            huecos = detalle_de_huecos(reencadenado.huecos)
            if huecos is not None:
                detalle = f"{detalle} {huecos}"
            cambios = len(invalidas) + reencadenado.cambios
        return Reparacion(
            accion=AISLAR,
            aplicada=True,
            detalle=detalle,
            cambios=cambios,
        )

    def reject_invalid_pending(self) -> Reparacion:
        """«rechazar-pendientes»: pasa a `rejected` las del pool que no serían admitidas.

        Revalida firma, monto, wallets y coherencia de cada pendiente con las mismas
        reglas que la auditoría; las válidas no se tocan. No reencadena: una fila del
        pool no está en ningún bloque, así que rechazarla no cambia ningún hash. Toda
        la escritura va dentro de una sola unidad de trabajo.
        """
        from src.domain.auditoria import RECHAZAR_PENDIENTES
        from src.domain.reparacion import Reparacion, cantidad

        with self._unit_of_work() as work:
            filas = list(work.transactions.all())
            cache: dict[UUID, Wallet | None] = {}
            invalidas = [
                fila
                for fila in filas
                if fila.status is TransactionStatus.PENDING
                and (
                    fila.block_id is not None
                    or self._motivo_de_invalidez(fila, cache) is not None
                )
            ]
            if not invalidas:
                return Reparacion(
                    accion=RECHAZAR_PENDIENTES,
                    aplicada=False,
                    detalle=(
                        "El pool no tiene transacciones inválidas: no se rechazó "
                        "ninguna."
                    ),
                    cambios=0,
                )
            work.transactions.reject([fila.id for fila in invalidas])
            work.commit()

        return Reparacion(
            accion=RECHAZAR_PENDIENTES,
            aplicada=True,
            detalle=(
                "Se rechazaron "
                f"{cantidad(len(invalidas), 'transacción', 'transacciones')} del pool."
            ),
            cambios=len(invalidas),
        )

    def repair_all(self) -> tuple[Reparacion, ...]:
        """Las tres reparaciones en orden: rechazar el pool, aislar y encadenar.

        Es el botón «reparar todo lo que se pueda». El orden importa: lo que se
        rechaza del pool deja de poder confirmarse y lo que se aísla cambia el
        contenido de los bloques, así que el reencadenado va al final. Es idempotente:
        una segunda pasada no encuentra nada que escribir.
        """
        return (
            self.reject_invalid_pending(),
            self.isolate_invalid_transactions(),
            self.repair_chain(),
        )

    def wallet_history(self, wallet_id: UUID, limit: int = 100) -> Sequence[Transaction]:
        """Los envíos y las recepciones de una wallet, en cualquier estado (CU-05, REQ-13).

        Van de la más nueva a la más vieja: el último movimiento queda arriba. El
        historial de la pantalla se queda con los últimos `limit`; las estadísticas
        piden más, porque filtran por todo el año.
        """
        return self.transactions.list(wallet_id=wallet_id, limit=limit, newest_first=True)

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

    def _publicas_de(
        self, transaction: Transaction, cache: dict[UUID, Wallet | None]
    ) -> tuple[str | None, str | None]:
        """Públicas actuales del emisor y del receptor, con una consulta por wallet.

        La caché dura lo que dura una reparación; la revalidación la necesita para
        comprobar la firma contra la llave pública que la wallet tiene hoy.
        """
        if transaction.sender_id not in cache:
            cache[transaction.sender_id] = self.wallets.get(transaction.sender_id)
        if transaction.receiver_id not in cache:
            cache[transaction.receiver_id] = self.wallets.get(transaction.receiver_id)
        emisor = cache[transaction.sender_id]
        receptor = cache[transaction.receiver_id]
        return (
            None if emisor is None else emisor.public_key,
            None if receptor is None else receptor.public_key,
        )

    def _motivo_de_invalidez(
        self, transaction: Transaction, cache: dict[UUID, Wallet | None]
    ) -> RejectionReason | None:
        """Motivo por el que la fila no pertenece a la cadena, o `None` si es válida."""
        from src.domain.reparacion import motivo_de_invalidez

        emisor, receptor = self._publicas_de(transaction, cache)
        return motivo_de_invalidez(
            transaction,
            sender_public_key=emisor,
            receiver_public_key=receptor,
        )

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
