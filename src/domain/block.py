"""Bloque del ledger: agrupa transacciones y fija el hash de su contenido.

Resuelve cómo se representa un bloque, cómo se calcula el hash que lo encadena al
anterior y cómo ese hash cubre las transacciones que agrupa (REQ-07): es la forma
que usan la agrupación y la verificación de `blockchain.py`.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from src.domain.transaction import Transaction


@dataclass(slots=True)
class Block:
    """Bloque con el hash del anterior y el de su propio contenido.

    Invariante: `hash` es lo que devuelve `calculate_hash` sobre las transacciones
    que el bloque agrupa; `previous_hash` es el hash del bloque anterior, o
    sesenta y cuatro ceros si es el génesis (REQ-07 y REQ-14).
    """

    id: UUID
    block_index: int
    timestamp: datetime
    previous_hash: str
    hash: str

    def calculate_hash(self, transactions: Sequence[Transaction]) -> str:
        """Hash SHA-256 del bloque sobre su contenido agrupado (REQ-07).

        El mensaje lleva la cabecera del bloque y después los `hash_payload()` de
        las transacciones **ordenados alfabéticamente**: ordenarlos es lo que hace
        que el hash no dependa del orden en que se leyeron del pool. Como cada
        payload incluye el `id` de su transacción, mover una transacción de un
        bloque a otro también cambia el hash.
        """
        header = f"{self.block_index}|{self.timestamp.isoformat()}|{self.previous_hash}|"
        payloads = sorted(transaction.hash_payload() for transaction in transactions)
        return sha256((header + "|".join(payloads)).encode("utf-8")).hexdigest()
