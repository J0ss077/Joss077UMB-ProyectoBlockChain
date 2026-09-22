"""Entidad Block."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Block:
    """Agrupación de transacciones confirmadas.

    ``hash`` y ``previous_hash`` son SHA-256 en hexadecimal minúscula de sesenta
    y cuatro caracteres. Este corte del backend no los calcula: solo los guarda.
    """

    id: UUID
    block_index: int
    timestamp: datetime
    previous_hash: str
    hash: str
