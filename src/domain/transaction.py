"""Transacción del ledger: forma canónica y reglas de admisión al pool.

Resuelve qué transacciones pueden entrar al pool y por qué se rechazan las que
no (REQ-02, REQ-04, REQ-05, REQ-06). El estado `rejected` y el bloque nulo
acompañan a la transacción inválida que el esquema permite guardar (REQ-11).
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from src.domain.wallet import verify

# Escala del esquema. El monto se escribe con ocho decimales en las formas
# canónicas para que la firma, el hash y la base hablen del mismo número.
AMOUNT_SCALE = Decimal("0.00000001")
# Mayor valor representable en NUMERIC(18, 8): diez dígitos enteros y ocho decimales.
AMOUNT_MAX = Decimal("9999999999.99999999")


class TransactionStatus(StrEnum):
    """Estados del ciclo de vida: pendiente en el pool, confirmada en un bloque o rechazada."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RejectionReason(StrEnum):
    """Motivo del rechazo; el texto es el que se le muestra a quien la propuso."""

    AMOUNT_NOT_POSITIVE = "el monto debe ser mayor que cero"
    AMOUNT_PRECISION = "el monto no puede tener más de ocho decimales"
    AMOUNT_OUT_OF_RANGE = "el monto no cabe en NUMERIC(18, 8)"
    SAME_SENDER_AND_RECEIVER = "el emisor y el receptor deben ser distintos"
    UNKNOWN_WALLET = "alguna de las wallets no existe"
    BAD_SIGNATURE = "la firma no corresponde a la llave pública del emisor"
    INSUFFICIENT_FUNDS = "el saldo disponible no alcanza"
    DUPLICATE_SIGNATURE = "esa firma ya fue registrada"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Resultado de la validación: si no se acepta, el motivo explica por qué."""

    accepted: bool
    reason: RejectionReason | None


@dataclass(slots=True)
class Transaction:
    """Transacción con su estado y el bloque que la confirma.

    Invariante: `block_id` es nulo mientras está `pending` o `rejected`, y no
    nulo cuando está `confirmed` (REQ-12).
    """

    id: UUID
    sender_id: UUID
    receiver_id: UUID
    amount: Decimal
    status: TransactionStatus
    signature: str
    block_id: UUID | None
    created_at: datetime

    def signing_payload(self, sender_public_key: str, receiver_public_key: str) -> bytes:
        """Cadena canónica que firma el emisor (decisión 2 del diseño).

        Incluye las dos públicas, el monto a escala fija y la marca de tiempo,
        de modo que la firma sea única por transacción.
        """
        return (
            f"{self.id}|{sender_public_key}|{receiver_public_key}"
            f"|{self.amount:.8f}|{self.created_at.isoformat()}"
        ).encode()

    def hash_payload(self) -> str:
        """Forma canónica que el bloque incluye en su hash.

        No incluye `status` ni `block_id` a propósito: ambos cambian justo al
        agrupar, y el hash del bloque tiene que calcularse antes de ese cambio.
        Ese orden es el que hace posible el encadenamiento.
        """
        return (
            f"{self.id}|{self.sender_id}|{self.receiver_id}"
            f"|{self.amount:.8f}|{self.signature}|{self.created_at.isoformat()}"
        )

    def validate(
        self,
        *,
        sender_public_key: str | None,
        receiver_public_key: str | None,
        available: Decimal,
        signature_exists: bool,
    ) -> ValidationResult:
        """Aplica las reglas en orden y devuelve el primer motivo encontrado.

        Orden: formato (monto positivo, rango, precisión y emisor distinto del
        receptor), luego wallets conocidas, firma, saldo y firma repetida. Las
        reglas de formato van primero porque no dependen de nada externo.

        Las públicas llegan en `None` cuando la wallet no existe: el dominio no
        consulta la base, solo valida lo que el ledger le entrega.
        """
        # Un monto no finito (`NaN`, `sNaN`, `Infinity`) no se puede comparar ni
        # cuantizar: las comparaciones dan falso y `quantize` levanta
        # `InvalidOperation`, que es lo que hacía caer la ruta con un error del
        # programa. Se rechaza antes de cualquier comparación, y el CHECK del esquema
        # no lo respalda: PostgreSQL evalúa `'NaN'::numeric > 0` como verdadero.
        if not self.amount.is_finite():
            return ValidationResult(False, RejectionReason.AMOUNT_NOT_POSITIVE)
        if self.amount <= 0:
            return ValidationResult(False, RejectionReason.AMOUNT_NOT_POSITIVE)
        # El rango se comprueba antes de la precisión: `quantize` sobre un monto
        # mayor que NUMERIC(18, 8) podría desbordar la precisión del contexto.
        if self.amount > AMOUNT_MAX:
            return ValidationResult(False, RejectionReason.AMOUNT_OUT_OF_RANGE)
        if self.amount != self.amount.quantize(AMOUNT_SCALE):
            return ValidationResult(False, RejectionReason.AMOUNT_PRECISION)
        if self.sender_id == self.receiver_id:
            return ValidationResult(False, RejectionReason.SAME_SENDER_AND_RECEIVER)
        if sender_public_key is None or receiver_public_key is None:
            return ValidationResult(False, RejectionReason.UNKNOWN_WALLET)
        payload = self.signing_payload(sender_public_key, receiver_public_key)
        if not verify(sender_public_key, self.signature, payload):
            return ValidationResult(False, RejectionReason.BAD_SIGNATURE)
        if available.is_nan() or available < self.amount:
            # Un saldo `NaN` —una fila con ese monto insertada directo, que el CHECK
            # del esquema no detiene— haría que la comparación levante
            # `InvalidOperation`; rechazar por saldo es la lectura conservadora de un
            # estado que no debería existir.
            return ValidationResult(False, RejectionReason.INSUFFICIENT_FUNDS)
        if signature_exists:
            return ValidationResult(False, RejectionReason.DUPLICATE_SIGNATURE)
        return ValidationResult(True, None)

    def is_valid(self, **kwargs) -> bool:
        """Atajo booleano de `validate` para quien no necesita el motivo."""
        return self.validate(**kwargs).accepted
