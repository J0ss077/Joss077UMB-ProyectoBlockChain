"""REQ-05 y REQ-06: el saldo disponible descuenta lo comprometido en el pool."""
from decimal import Decimal

from src.domain.blockchain import BalanceTerms, available_balance
from src.domain.transaction import RejectionReason


def test_req_05_solo_las_confirmadas_cuentan_para_el_saldo():
    """Criterio: el saldo disponible es lo confirmado a favor menos lo confirmado en contra."""
    terms = BalanceTerms(
        confirmed_in=Decimal("100"), confirmed_out=Decimal("30"), pending_out=Decimal("0")
    )
    assert available_balance(terms) == Decimal("70")


def test_req_06_el_pool_descuenta_el_disponible():
    """Criterio: lo comprometido en el pool se descuenta del saldo disponible."""
    terms = BalanceTerms(
        confirmed_in=Decimal("100"), confirmed_out=Decimal("0"), pending_out=Decimal("80")
    )
    assert available_balance(terms) == Decimal("20")


def test_req_06_dos_transacciones_que_juntas_exceden_no_pasan_las_dos(transaccion):
    """Criterio: la segunda transacción se rechaza por saldo porque la primera ya lo comprometió."""
    disponible = available_balance(BalanceTerms(Decimal("100"), Decimal("0"), Decimal("0")))
    primera = transaccion(amount=Decimal("60")).validate(
        available=disponible, signature_exists=False
    )
    assert primera.accepted is True
    con_pool = available_balance(BalanceTerms(Decimal("100"), Decimal("0"), Decimal("60")))
    segunda = transaccion(amount=Decimal("60")).validate(available=con_pool, signature_exists=False)
    assert segunda.reason is RejectionReason.INSUFFICIENT_FUNDS


def test_req_05_un_saldo_nan_se_rechaza_sin_levantar_el_error(transaccion):
    """Criterio: un saldo `NaN` se rechaza por saldo, sin caer en la comparación.

    `NaN` no es comparable con `<`, así que sin esta defensa la ruta levantaría
    `InvalidOperation` con una fila de monto `NaN` insertada directo en la base.
    """
    resultado = transaccion().validate(available=Decimal("NaN"), signature_exists=False)

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.INSUFFICIENT_FUNDS
