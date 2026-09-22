"""Entidad Transaction y sus estados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class TransactionStatus(StrEnum):
    """Estados posibles de una transacción.

    Los tres valores coinciden con el CHECK del esquema.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass(slots=True)
class Transaction:
    """Transferencia firmada entre dos wallets.

    ``block_id`` es nulo mientras la transacción está pendiente o rechazada. El
    esquema exige que sea no nulo solo cuando el estado es confirmado.
    """

    id: UUID
    sender_id: UUID
    receiver_id: UUID
    amount: Decimal
    status: TransactionStatus
    signature: str
    block_id: UUID | None
    created_at: datetime
