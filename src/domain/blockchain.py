"""Reglas del ledger que deciden qué transacciones del pool pueden entrar.

Implementa la regla del CU-02 (REQ-05 y REQ-06): el saldo disponible de una
wallet es lo confirmado a favor menos lo confirmado en contra y menos lo
comprometido en el pool. La validación es secuencial —cada transacción admitida
descuenta el disponible de la siguiente— porque el eje deja la concurrencia
fuera de alcance; la fachada que agrupa y encadena llega en la tarea 7.
"""
from dataclasses import dataclass
from decimal import Decimal


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
