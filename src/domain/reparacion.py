"""Reparaciones guiadas del ledger: qué se recalcula y qué filas no pertenecen.

Reúne la lógica pura de las reparaciones que la fachada escribe después: la
dataclass `Reparacion` con el resultado, el recálculo en orden de los hashes de la
cadena (reencadenar), la agrupación de las transacciones por bloque y la
revalidación de una fila con `Transaction.validate`.

No importa Flask ni `psycopg` y no escribe: la persistencia la hacen los métodos de
`src.domain.blockchain.Blockchain`, cada uno dentro de una sola unidad de trabajo. El
cálculo de los hashes no toca el reloj ni las marcas de tiempo: solo reescribe
`previous_hash` y `hash`, así que los índices y los `timestamp` quedan intactos.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from src.domain.block import Block
from src.domain.blockchain import GENESIS_PREVIOUS_HASH
from src.domain.transaction import (
    AMOUNT_MAX,
    RejectionReason,
    Transaction,
    TransactionStatus,
)

# Motivos de `Transaction.validate` que no convierten una fila en inválida para las
# reparaciones. El saldo no se revalida —la creación ya lo descartó y el orden del
# pool lo cambiaría— y la firma repetida se descarta al escribir, no al reparar; por
# eso la revalidación pide saldo máximo y firma inexistente y, aun así, los ignora.
MOTIVOS_QUE_NO_INVALIDAN = frozenset(
    {RejectionReason.INSUFFICIENT_FUNDS, RejectionReason.DUPLICATE_SIGNATURE}
)


@dataclass(frozen=True, slots=True)
class Reparacion:
    """Resultado de una reparación guiada: qué acción fue, si aplicó y qué cambió.

    `cambios` cuenta las filas escritas —bloques con hashes reescritos o
    transacciones pasadas a `rejected`—, no los hallazgos que la motivaron. Una
    reparación queda sin aplicar cuando no había nada que cerrar o cuando la cadena
    no admite la reparación, como un hueco de índices.
    """

    accion: str
    aplicada: bool
    detalle: str
    cambios: int


@dataclass(frozen=True, slots=True)
class Reencadenado:
    """Resultado puro de recalcular la cadena, todavía sin escribir.

    `bloques` son copias nuevas con `previous_hash` y `hash` recalculados en orden;
    `cambios` cuenta cuántos difieren de los guardados y `huecos` los índices a los
    que les falta al menos el bloque anterior, que la reparación no renumera.
    """

    bloques: tuple[Block, ...]
    cambios: int
    huecos: tuple[int, ...]


def cantidad(n: int, singular: str, plural: str) -> str:
    """«1 bloque» o «3 bloques», para que los detalles se lean bien."""
    return f"{n} {singular if n == 1 else plural}"


def agrupar_por_bloque(
    transacciones: Sequence[Transaction],
) -> dict[UUID, list[Transaction]]:
    """Agrupa en memoria las transacciones que declaran un bloque, en el orden leído.

    Es la lectura que reencadenar necesita para calcular el hash de cada bloque sin
    una consulta por bloque; solo las filas con `block_id` entran, igual que en la
    auditoría, que también cuenta las rechazadas con bloque si las hubiera.
    """
    agrupadas: dict[UUID, list[Transaction]] = {}
    for transaction in transacciones:
        if transaction.block_id is not None:
            agrupadas.setdefault(transaction.block_id, []).append(transaction)
    return agrupadas


def se_puede_reencadenar(bloques: Sequence[Block]) -> bool:
    """Si la cadena empieza en el bloque 0 y admite que se recalculen sus hashes.

    Sin el génesis, el recálculo encadenaría el primer bloque que haya a los ceros
    del eslabón cero: fabricaría un encadenamiento que nunca existió y borraría el
    rastro de la cabeza eliminada. Por eso las reparaciones que reencadenan de paso
    solo lo aplican cuando la cadena empieza en el índice 0.
    """
    return bool(bloques) and bloques[0].block_index == 0


def recalcular_cadena(
    bloques: Sequence[Block],
    por_bloque: Mapping[UUID, Sequence[Transaction]],
) -> Reencadenado:
    """Recalcula `previous_hash` y `hash` en orden a partir del bloque 0, sin escribir.

    El primer bloque se encadena al hash previo del génesis y cada uno a la copia
    recalculada del anterior; el hash propio se calcula con las transacciones
    agrupadas por `block_id`. Las marcas de tiempo y los índices no se tocan. Los
    índices que no son consecutivos se devuelven como huecos: la reparación no los
    puede cerrar porque no renumera. Quien llama tiene que comprobar antes con
    `se_puede_reencadenar` que la cadena empieza en el génesis; si no, este cálculo
    fabricaría un encadenamiento falso.
    """
    nuevos: list[Block] = []
    cambios = 0
    huecos: list[int] = []
    anterior: Block | None = None
    for block in bloques:
        if anterior is not None and block.block_index != anterior.block_index + 1:
            huecos.append(block.block_index)
        anterior_hash = (
            GENESIS_PREVIOUS_HASH if anterior is None else nuevos[-1].hash
        )
        nuevo = replace(block, previous_hash=anterior_hash)
        nuevo.hash = nuevo.calculate_hash(por_bloque.get(block.id, ()))
        if (nuevo.previous_hash, nuevo.hash) != (block.previous_hash, block.hash):
            cambios += 1
        nuevos.append(nuevo)
        anterior = block
    return Reencadenado(bloques=tuple(nuevos), cambios=cambios, huecos=tuple(huecos))


def motivo_de_invalidez(
    transaction: Transaction,
    *,
    sender_public_key: str | None,
    receiver_public_key: str | None,
) -> RejectionReason | None:
    """Motivo por el que la fila no pertenece a la cadena, o `None` si es válida.

    Revalida con la pública actual de las dos wallets y `available=AMOUNT_MAX` para
    que el saldo no decida, y `signature_exists=False` porque la repetición no es un
    defecto de la fila. Cubre monto, wallets, firma y emisor igual al receptor; la
    coherencia entre estado y bloque se comprueba aparte con `esta_desencajada`.
    """
    validacion = transaction.validate(
        sender_public_key=sender_public_key,
        receiver_public_key=receiver_public_key,
        available=AMOUNT_MAX,
        signature_exists=False,
    )
    if validacion.accepted or validacion.reason in MOTIVOS_QUE_NO_INVALIDAN:
        return None
    return validacion.reason


def esta_desencajada(
    transaction: Transaction, *, ids_de_bloques: set[UUID]
) -> bool:
    """Si el estado y el bloque no concuerdan, entre los casos que la reparación cierra.

    Una confirmada sin bloque, o con un bloque que no está, se aísla; una pendiente
    con bloque se rechaza. Una rechazada con bloque rompe el contrato de REQ-12 pero
    ninguna reparación de la pantalla la cierra, así que no se marca aquí.
    """
    if transaction.status is TransactionStatus.CONFIRMED:
        return transaction.block_id is None or transaction.block_id not in ids_de_bloques
    if transaction.status is TransactionStatus.PENDING:
        return transaction.block_id is not None
    return False


def detalle_de_huecos(huecos: Sequence[int]) -> str | None:
    """Frase que declara los índices faltantes, o `None` si no hay huecos."""
    if not huecos:
        return None
    indices = ", ".join(str(indice) for indice in huecos)
    return (
        f"Los índices no son consecutivos: falta al menos un bloque antes de {indices}. "
        "No se renumera."
    )


def detalle_de_encadenado(reencadenado: Reencadenado) -> str:
    """Detalle de «encadenar»: cuántos bloques se reescribieron y qué hueco queda."""
    if reencadenado.cambios:
        partes = [
            "Se reescribieron los hashes de "
            f"{cantidad(reencadenado.cambios, 'bloque', 'bloques')}."
        ]
    else:
        partes = ["La cadena ya estaba encadenada: no se reescribió ningún bloque."]
    huecos = detalle_de_huecos(reencadenado.huecos)
    if huecos is not None:
        partes.append(huecos)
    return " ".join(partes)
