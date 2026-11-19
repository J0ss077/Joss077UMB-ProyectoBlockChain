"""Auditoría profunda del estado de la cadena: hallazgos, reparaciones y límites.

Recorre todos los bloques, todas las transacciones confirmadas y todo el pool sin
detenerse en la primera discrepancia. Las transacciones se leen una sola vez con
`TransactionRepository.all()` y se agrupan por bloque en memoria, así que no se hace
una consulta por bloque. Comprueba encadenamiento, hashes, coherencia de estado,
wallets, montos, firmas y sello de vigilancia; no escribe nada (REQ-22) y no depende
de Flask ni de `psycopg`: habla solo con los protocolos de `src/persistence/ports.py`
(REQ-16).

La firma se verifica contra la llave pública **actual** del emisor con
`src.domain.wallet.verify` y el `signing_payload` de la transacción. Eso es lo que
hace detectables el cambio de llave de una wallet, una pendiente con firma inventada
y la alteración de un monto: la auditoría no necesita confiar solo en el hash del
bloque.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.block import Block
from src.domain.blockchain import GENESIS_PREVIOUS_HASH
from src.domain.transaction import (
    AMOUNT_MAX,
    AMOUNT_SCALE,
    Transaction,
    TransactionStatus,
)
from src.domain.wallet import Wallet, verify

if TYPE_CHECKING:
    # Solo para las anotaciones: importar los protocolos en tiempo de ejecución
    # cerraría el ciclo domain -> persistence -> domain y no hace falta (REQ-16).
    from src.persistence.ports import (
        BlockRepository,
        TransactionRepository,
        WalletRepository,
    )

# Las tres severidades, de la más grave a la más leve. `valida` se calcula sobre los
# críticos y `limpia` sobre los críticos y los avisos; una nota no invalida la cadena.
SEVERIDADES = ("critico", "aviso", "nota")
CRITICO, AVISO, NOTA = SEVERIDADES

# Reparaciones que la interfaz puede ofrecer. Son claves estables y no frases: quien
# las pinta las traduce y quien las aplica las despacha.
ENCADENAR = "encadenar"
AISLAR = "aislar"
RECHAZAR_PENDIENTES = "rechazar-pendientes"
FIJAR_SELLO = "fijar-sello"


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """Un fallo comprobado, con dónde está y qué reparación lo puede atender.

    `codigo` es la clave estable que la interfaz traduce; `detalle` lleva los valores
    concretos —hashes, índices, motivos— y no se traduce. `reparacion` es nula cuando
    ninguna de las reparaciones de la pantalla cierra el hallazgo.
    """

    codigo: str
    severidad: str
    ubicacion: str
    detalle: str
    reparacion: str | None


@dataclass(frozen=True, slots=True)
class RevisionDeBloque:
    """Lo que la auditoría encontró en un bloque, para la tabla del panel.

    `estado` es una sola palabra que resume el peor problema del eslabón, en este
    orden de prioridad: `cabeza`, `hueco`, `encadenamiento`, `alterado` y
    `correcto`. `detalle` explica ese estado y es nulo cuando el bloque está bien.
    """

    indice: int
    hash: str
    transacciones: int
    estado: str
    detalle: str | None


@dataclass(frozen=True, slots=True)
class Sello:
    """Ancla externa contra el recorte de la cola: la altura y el hash que se fijaron.

    `fijado_en` es el instante en que se fijó, en UTC. El sello no se actualiza solo:
    lo fija la persona después de sembrar, de reparar o de comprobar el estado.
    """

    altura: int
    hash: str
    fijado_en: datetime


@dataclass(frozen=True, slots=True)
class EstadoDelSello:
    """Resultado de comparar el sello fijado con la cadena actual.

    `problema` es "ausente" cuando no hay sello e "ilegible" cuando existe pero no se
    puede leer; en esos casos `sello` es nulo y `coincide` es falso. `crecio` cuenta
    los bloques nuevos por encima de la altura sellada y solo tiene valor cuando el
    bloque sellado sigue intacto.
    """

    sello: Sello | None
    problema: str | None
    coincide: bool
    crecio: int | None


@dataclass(frozen=True, slots=True)
class LecturaDelSello:
    """Lo que devolvió leer el archivo del sello: el sello o el motivo de su ausencia.

    Es el contrato que el adaptador de persistencia entrega a la auditoría; `problema`
    vale "ausente" cuando no hay archivo e "ilegible" cuando existe pero no se puede
    leer o su firma no cuadra.
    """

    sello: Sello | None
    problema: str | None


@dataclass(frozen=True, slots=True)
class Resumen:
    """Las cifras del estado de la cadena, tal como se muestran en el panel."""

    bloques: int
    altura: int | None
    cabeza_hash: str | None
    cabeza_en: datetime | None
    genesis_hash: str | None
    confirmadas: int
    pendientes: int
    rechazadas: int
    wallets: int
    valida: bool


@dataclass(frozen=True, slots=True)
class Limite:
    """Algo que la auditoría no puede comprobar, con el porqué en palabras simples."""

    titulo: str
    detalle: str


@dataclass(frozen=True, slots=True)
class Auditoria:
    """El resultado completo de auditar: resumen, hallazgos, bloques, límites y sello."""

    resumen: Resumen
    hallazgos: tuple[Hallazgo, ...]
    bloques: tuple[RevisionDeBloque, ...]
    limites: tuple[Limite, ...]
    sello: EstadoDelSello

    @property
    def limpia(self) -> bool:
        """Si no hay críticos ni avisos; una nota no ensucia el dictamen."""
        return not any(
            hallazgo.severidad in (CRITICO, AVISO) for hallazgo in self.hallazgos
        )

    def contar(self, severidad: str) -> int:
        """Cuántos hallazgos hay con esa severidad."""
        return sum(
            1 for hallazgo in self.hallazgos if hallazgo.severidad == severidad
        )

    @property
    def reparaciones(self) -> tuple[str, ...]:
        """Las reparaciones sugeridas por los hallazgos, únicas y en orden alfabético."""
        return tuple(
            sorted(
                {
                    hallazgo.reparacion
                    for hallazgo in self.hallazgos
                    if hallazgo.reparacion is not None
                }
            )
        )


_LIMITE_DEL_RECORTE = Limite(
    titulo="Recorte de la cola",
    detalle=(
        "El recorte de la cola solo se detecta con un sello fijado antes del recorte; "
        "sin sello es indistinguible de una cadena que nunca tuvo esos bloques."
    ),
)

_LIMITES_FIJOS = (
    Limite(
        titulo="Origen del sello",
        detalle=(
            "Quien pueda escribir en la base y en el archivo del sello puede falsificar "
            "los dos."
        ),
    ),
    Limite(
        titulo="Alcance del reencadenado",
        detalle=(
            "Reencadenar devuelve la coherencia, no el contenido original de un dato "
            "alterado o borrado."
        ),
    ),
    Limite(
        titulo="Huecos y borrados",
        detalle=(
            "Un hueco de índices o un bloque borrado en medio no se repara desde la "
            "interfaz."
        ),
    ),
)


def _corto(identificador: UUID | str) -> str:
    """Los primeros ocho caracteres de un identificador, con puntos suspensivos."""
    return f"{str(identificador)[:8]}…"


def _hash_corto(valor: str) -> str:
    """Los primeros doce caracteres de un hash, con puntos suspensivos si es más largo."""
    return f"{valor[:12]}…" if len(valor) > 12 else valor


def _ubicacion_de(transaccion: Transaction) -> str:
    """Ubicación de un hallazgo de transacción: el identificador corto, como el panel."""
    return f"Transacción {_corto(transaccion.id)}"


def _motivo_del_monto(monto: Decimal) -> str | None:
    """Por qué el monto no cabe en la escala del esquema, o `None` si cabe.

    Se comprueba en el mismo orden que la validación de creación —finito, positivo,
    rango y precisión— para que el detalle diga la causa real y no la primera que
    falle por casualidad. Un `NaN` se descarta antes de compararlo porque las
    comparaciones con `NaN` no son de fiar y `quantize` levanta `InvalidOperation`.
    """
    if not monto.is_finite():
        return "El monto no es un número finito."
    if monto <= 0:
        return "El monto no es positivo."
    if monto > AMOUNT_MAX:
        return "El monto no cabe en la escala NUMERIC(18, 8) del esquema."
    if monto != monto.quantize(AMOUNT_SCALE):
        return "El monto tiene más de ocho decimales."
    return None


def auditar(
    *,
    blocks: BlockRepository,
    transactions: TransactionRepository,
    wallets: WalletRepository,
    sello: Sello | None = None,
    problema_del_sello: str | None = None,
) -> Auditoria:
    """Audita la cadena y el pool sin escribir nada (REQ-22).

    `blocks`, `transactions` y `wallets` son los tres repositorios; la auditoría no
    toca la base por otra vía. `sello` es el ancla externa ya leída y
    `problema_del_sello` dice si no se pudo leer: cuando viene un problema, el sello
    se trata como ausente, porque sin ancla utilizable el recorte no se puede
    comprobar.

    La lectura es completa y el recorrido no se detiene en el primer fallo: cada
    bloque y cada transacción se revisan enteros, de modo que el panel enumera todo lo
    que el sistema puede comprobar.
    """
    filas_de_bloques = list(blocks.list())
    filas_de_transacciones = list(transactions.all())

    # Una consulta por wallet distinta, no una por transacción: la caché evita repetir
    # la lectura de la misma pública cuando una wallet participa en muchas filas.
    cache_de_wallets: dict[UUID, Wallet | None] = {}

    def wallet_de(wallet_id: UUID) -> Wallet | None:
        if wallet_id not in cache_de_wallets:
            cache_de_wallets[wallet_id] = wallets.get(wallet_id)
        return cache_de_wallets[wallet_id]

    por_bloque: dict[UUID, list[Transaction]] = {}
    for transaction in filas_de_transacciones:
        if transaction.block_id is not None:
            por_bloque.setdefault(transaction.block_id, []).append(transaction)

    hallazgos: list[Hallazgo] = []
    revisiones: list[RevisionDeBloque] = []

    if not filas_de_bloques:
        hallazgos.append(
            Hallazgo(
                codigo="cadena-vacia",
                severidad=CRITICO,
                ubicacion="Cadena",
                detalle="No hay ningún bloque: falta el eslabón génesis.",
                reparacion=ENCADENAR,
            )
        )
    else:
        _revisar_bloques(filas_de_bloques, por_bloque, hallazgos, revisiones)

    ids_de_bloques = {block.id for block in filas_de_bloques}
    _revisar_transacciones(
        filas_de_transacciones, ids_de_bloques, wallet_de, hallazgos
    )
    _revisar_firmas_repetidas(filas_de_transacciones, hallazgos)

    estado_del_sello = _revisar_sello(
        filas_de_bloques, sello, problema_del_sello, hallazgos
    )

    resumen = Resumen(
        bloques=len(filas_de_bloques),
        altura=filas_de_bloques[-1].block_index if filas_de_bloques else None,
        cabeza_hash=filas_de_bloques[-1].hash if filas_de_bloques else None,
        cabeza_en=filas_de_bloques[-1].timestamp if filas_de_bloques else None,
        genesis_hash=next(
            (block.hash for block in filas_de_bloques if block.block_index == 0), None
        ),
        confirmadas=sum(
            1
            for transaction in filas_de_transacciones
            if transaction.status is TransactionStatus.CONFIRMED
        ),
        pendientes=sum(
            1
            for transaction in filas_de_transacciones
            if transaction.status is TransactionStatus.PENDING
        ),
        rechazadas=sum(
            1
            for transaction in filas_de_transacciones
            if transaction.status is TransactionStatus.REJECTED
        ),
        wallets=wallets.count(),
        valida=not any(hallazgo.severidad == CRITICO for hallazgo in hallazgos),
    )

    return Auditoria(
        resumen=resumen,
        hallazgos=tuple(hallazgos),
        bloques=tuple(revisiones),
        limites=_limites(estado_del_sello),
        sello=estado_del_sello,
    )


def _revisar_bloques(
    filas: Sequence[Block],
    por_bloque: dict[UUID, list[Transaction]],
    hallazgos: list[Hallazgo],
    revisiones: list[RevisionDeBloque],
) -> None:
    """Recorre todos los bloques: cabeza, índices, encadenamiento y hash recalculado."""
    anterior: Block | None = None
    for block in filas:
        agrupadas = por_bloque.get(block.id, [])
        estado = "correcto"
        detalle_del_estado: str | None = None
        if anterior is None:
            if block.block_index != 0:
                estado = "cabeza"
                detalle_del_estado = (
                    f"El primer bloque es el {block.block_index} y no el génesis: "
                    "falta el eslabón 0."
                )
                hallazgos.append(
                    Hallazgo(
                        codigo="cabeza",
                        severidad=CRITICO,
                        ubicacion=f"Bloque {block.block_index}",
                        detalle=detalle_del_estado,
                        reparacion=None,
                    )
                )
            elif block.previous_hash != GENESIS_PREVIOUS_HASH:
                estado = "cabeza"
                detalle_del_estado = (
                    "El bloque 0 no tiene el hash previo en ceros: "
                    f"{_hash_corto(block.previous_hash)}."
                )
                hallazgos.append(
                    Hallazgo(
                        codigo="cabeza",
                        severidad=CRITICO,
                        ubicacion="Bloque 0",
                        detalle=detalle_del_estado,
                        reparacion=ENCADENAR,
                    )
                )
        else:
            if block.block_index != anterior.block_index + 1:
                estado = "hueco"
                detalle_del_estado = (
                    "Los índices no son consecutivos: al bloque "
                    f"{anterior.block_index} le sigue el {block.block_index}."
                )
                hallazgos.append(
                    Hallazgo(
                        codigo="indice",
                        severidad=CRITICO,
                        ubicacion=f"Bloque {block.block_index}",
                        detalle=detalle_del_estado,
                        reparacion=None,
                    )
                )
            if block.previous_hash != anterior.hash:
                if estado == "correcto":
                    estado = "encadenamiento"
                    detalle_del_estado = (
                        f"El hash previo {_hash_corto(block.previous_hash)} no es el "
                        f"hash {_hash_corto(anterior.hash)} del bloque "
                        f"{anterior.block_index}."
                    )
                hallazgos.append(
                    Hallazgo(
                        codigo="encadenamiento",
                        severidad=CRITICO,
                        ubicacion=f"Bloque {block.block_index}",
                        detalle=(
                            f"El hash previo {_hash_corto(block.previous_hash)} no es "
                            f"el hash {_hash_corto(anterior.hash)} del bloque "
                            f"{anterior.block_index}."
                        ),
                        reparacion=ENCADENAR,
                    )
                )

        recalculado = block.calculate_hash(agrupadas)
        if recalculado != block.hash:
            detalle_del_hash = (
                f"El hash guardado {_hash_corto(block.hash)} no es el recalculado "
                f"{_hash_corto(recalculado)} con sus {len(agrupadas)} transacciones."
            )
            if estado == "correcto":
                estado = "alterado"
                detalle_del_estado = detalle_del_hash
            hallazgos.append(
                Hallazgo(
                    codigo="hash",
                    severidad=CRITICO,
                    ubicacion=f"Bloque {block.block_index}",
                    detalle=detalle_del_hash,
                    reparacion=ENCADENAR,
                )
            )

        revisiones.append(
            RevisionDeBloque(
                indice=block.block_index,
                hash=block.hash,
                transacciones=len(agrupadas),
                estado=estado,
                detalle=detalle_del_estado,
            )
        )
        anterior = block


def _revisar_transacciones(
    filas: Sequence[Transaction],
    ids_de_bloques: set[UUID],
    wallet_de: Callable[[UUID], Wallet | None],
    hallazgos: list[Hallazgo],
) -> None:
    """Revisa coherencia, wallets, montos y firmas de las confirmadas y del pool.

    Las rechazadas solo se miran por coherencia: son historia y el objetivo de la
    auditoría es revisar los bloques, las confirmadas y el pool. Una rechazada con
    bloque, en cambio, rompe el contrato estado/bloque y se declara igual.
    """
    for transaction in filas:
        ubicacion = _ubicacion_de(transaction)
        if transaction.status is TransactionStatus.CONFIRMED:
            reparacion = AISLAR
            if transaction.block_id is None:
                hallazgos.append(
                    Hallazgo(
                        codigo="transaccion-sin-bloque",
                        severidad=CRITICO,
                        ubicacion=ubicacion,
                        detalle="La transacción está confirmada y no tiene bloque.",
                        reparacion=reparacion,
                    )
                )
            elif transaction.block_id not in ids_de_bloques:
                hallazgos.append(
                    Hallazgo(
                        codigo="transaccion-sin-bloque",
                        severidad=CRITICO,
                        ubicacion=ubicacion,
                        detalle=(
                            "La transacción apunta al bloque "
                            f"{_corto(transaction.block_id)} y ese bloque no existe."
                        ),
                        reparacion=reparacion,
                    )
                )
        elif transaction.status is TransactionStatus.PENDING:
            reparacion = RECHAZAR_PENDIENTES
            if transaction.block_id is not None:
                hallazgos.append(
                    Hallazgo(
                        codigo="coherencia-de-estado",
                        severidad=CRITICO,
                        ubicacion=ubicacion,
                        detalle=(
                            "La transacción está pendiente y tiene bloque: el pool no "
                            "debería tener bloque."
                        ),
                        reparacion=reparacion,
                    )
                )
        else:
            if transaction.block_id is not None:
                hallazgos.append(
                    Hallazgo(
                        codigo="coherencia-de-estado",
                        severidad=CRITICO,
                        ubicacion=ubicacion,
                        detalle="La transacción está rechazada y tiene bloque.",
                        reparacion=None,
                    )
                )
            continue

        emisor = wallet_de(transaction.sender_id)
        receptor = wallet_de(transaction.receiver_id)
        if emisor is None or receptor is None:
            if emisor is None and receptor is None:
                detalle = (
                    "Faltan las wallets del emisor "
                    f"{_corto(transaction.sender_id)} y del receptor "
                    f"{_corto(transaction.receiver_id)}."
                )
            elif emisor is None:
                detalle = f"Falta la wallet del emisor {_corto(transaction.sender_id)}."
            else:
                detalle = f"Falta la wallet del receptor {_corto(transaction.receiver_id)}."
            hallazgos.append(
                Hallazgo(
                    codigo="wallet-inexistente",
                    severidad=CRITICO,
                    ubicacion=ubicacion,
                    detalle=detalle,
                    reparacion=reparacion,
                )
            )

        motivo = _motivo_del_monto(transaction.amount)
        if motivo is not None:
            hallazgos.append(
                Hallazgo(
                    codigo="monto",
                    severidad=CRITICO,
                    ubicacion=ubicacion,
                    detalle=motivo,
                    reparacion=reparacion,
                )
            )

        # Sin las dos públicas no hay forma de recomponer la forma firmada; el
        # hallazgo de wallet inexistente ya explica por qué no se puede comprobar.
        if emisor is None or receptor is None:
            continue
        payload = transaction.signing_payload(emisor.public_key, receptor.public_key)
        if verify(emisor.public_key, transaction.signature, payload):
            continue
        severidad = CRITICO if transaction.status is TransactionStatus.CONFIRMED else AVISO
        hallazgos.append(
            Hallazgo(
                codigo="firma",
                severidad=severidad,
                ubicacion=ubicacion,
                detalle=(
                    "La firma no corresponde a la llave pública actual del emisor."
                ),
                reparacion=reparacion,
            )
        )


def _revisar_firmas_repetidas(
    filas: Sequence[Transaction], hallazgos: list[Hallazgo]
) -> None:
    """Marca cada firma que aparece en más de una fila, sin importar su estado."""
    por_firma: dict[str, list[Transaction]] = {}
    for transaction in filas:
        por_firma.setdefault(transaction.signature, []).append(transaction)
    for repetidas in por_firma.values():
        if len(repetidas) < 2:
            continue
        listado = ", ".join(_ubicacion_de(transaction) for transaction in repetidas)
        hallazgos.append(
            Hallazgo(
                codigo="firma-repetida",
                severidad=CRITICO,
                ubicacion=_ubicacion_de(repetidas[0]),
                detalle=(
                    f"{len(repetidas)} transacciones comparten la misma firma: "
                    f"{listado}."
                ),
                reparacion=None,
            )
        )


def _revisar_sello(
    filas: Sequence[Block],
    sello: Sello | None,
    problema_del_sello: str | None,
    hallazgos: list[Hallazgo],
) -> EstadoDelSello:
    """Compara el sello con la cadena y declara el hallazgo que corresponda.

    Un problema informado manda sobre el sello: sin lectura utilizable no hay ancla
    con la que comparar. Cuando el bloque sellado no está o su hash cambió, el
    sello ya no coincide y se ofrece fijar de nuevo el estado actual.
    """
    if problema_del_sello is not None:
        es_ausente = problema_del_sello == "ausente"
        hallazgos.append(
            Hallazgo(
                codigo="sello-ausente" if es_ausente else "sello-ilegible",
                severidad=NOTA if es_ausente else AVISO,
                ubicacion="Sello",
                detalle=(
                    "No hay un sello fijado: el recorte de la cola no se puede "
                    "comprobar."
                    if es_ausente
                    else "El sello no se puede leer o su firma no cuadra."
                ),
                reparacion=FIJAR_SELLO,
            )
        )
        return EstadoDelSello(
            sello=None, problema=problema_del_sello, coincide=False, crecio=None
        )

    if sello is None:
        hallazgos.append(
            Hallazgo(
                codigo="sello-ausente",
                severidad=NOTA,
                ubicacion="Sello",
                detalle=(
                    "No hay un sello fijado: el recorte de la cola no se puede "
                    "comprobar."
                ),
                reparacion=FIJAR_SELLO,
            )
        )
        return EstadoDelSello(
            sello=None, problema="ausente", coincide=False, crecio=None
        )

    bloque = next(
        (bloque for bloque in filas if bloque.block_index == sello.altura), None
    )
    if bloque is None:
        hallazgos.append(
            Hallazgo(
                codigo="sello-no-coincide",
                severidad=CRITICO,
                ubicacion="Sello",
                detalle=(
                    f"El sello apunta al bloque {sello.altura} y ese bloque no "
                    "existe: la cadena se recortó o se reescribió."
                ),
                reparacion=FIJAR_SELLO,
            )
        )
        return EstadoDelSello(
            sello=sello, problema=None, coincide=False, crecio=None
        )
    if bloque.hash != sello.hash:
        hallazgos.append(
            Hallazgo(
                codigo="sello-no-coincide",
                severidad=CRITICO,
                ubicacion="Sello",
                detalle=(
                    f"El bloque {sello.altura} tiene el hash "
                    f"{_hash_corto(bloque.hash)} y el sello guarda "
                    f"{_hash_corto(sello.hash)}."
                ),
                reparacion=FIJAR_SELLO,
            )
        )
        return EstadoDelSello(
            sello=sello, problema=None, coincide=False, crecio=None
        )

    crecio = sum(1 for bloque in filas if bloque.block_index > sello.altura)
    return EstadoDelSello(
        sello=sello, problema=None, coincide=True, crecio=crecio
    )


def _limites(estado_del_sello: EstadoDelSello) -> tuple[Limite, ...]:
    """Los límites que la auditoría declara, con el del recorte solo sin sello.

    Sin un sello utilizable no hay ancla externa con la que notar un recorte por la
    cola, así que el límite se declara además de los tres que valen siempre.
    """
    if estado_del_sello.sello is None:
        return (_LIMITE_DEL_RECORTE, *_LIMITES_FIJOS)
    return _LIMITES_FIJOS
