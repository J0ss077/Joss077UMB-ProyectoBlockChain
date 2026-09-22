"""Entidad Wallet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Wallet:
    """Par de llaves de un participante.

    La llave privada se guarda cifrada y nunca en texto plano. Este corte del
    backend no genera llaves ni firma: solo transporta lo que está en la base.
    """

    id: UUID
    public_key: str
    private_key_encrypted: bytes
    created_at: datetime
