"""REQ-04: las cuatro condiciones se comprueban antes de entrar al pool."""
from decimal import Decimal
from uuid import uuid4

from src.domain.transaction import RejectionReason


def test_req_04_monto_no_positivo_se_rechaza(transaccion):
    """Criterio: un monto menor o igual a cero se rechaza antes de entrar al pool."""
    resultado = transaccion(amount=Decimal("0")).validate(
        available=Decimal("100"), signature_exists=False
    )
    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.AMOUNT_NOT_POSITIVE


def test_req_04_emisor_igual_al_receptor_se_rechaza(transaccion):
    """Criterio: el emisor y el receptor deben ser wallets distintas."""
    mismo = uuid4()
    resultado = transaccion(sender_id=mismo, receiver_id=mismo).validate(
        available=Decimal("100"), signature_exists=False
    )
    assert resultado.reason is RejectionReason.SAME_SENDER_AND_RECEIVER


def test_req_04_rf1_monto_con_mas_de_ocho_decimales_se_rechaza(transaccion):
    """Criterio: un monto con más de ocho decimales no cabe en NUMERIC(18,8) y se rechaza."""
    resultado = transaccion(amount=Decimal("0.000000001")).validate(
        available=Decimal("100"), signature_exists=False
    )
    assert resultado.reason is RejectionReason.AMOUNT_PRECISION


def test_req_04_rf2_monto_fuera_del_rango_de_numeric_18_8_se_rechaza(transaccion):
    """Criterio: un monto de diez mil millones o más queda fuera del rango de NUMERIC(18,8)."""
    resultado = transaccion(amount=Decimal("10000000000")).validate(
        available=Decimal("100"), signature_exists=False
    )
    assert resultado.reason is RejectionReason.AMOUNT_OUT_OF_RANGE


def test_req_04_una_wallet_desconocida_se_rechaza(transaccion):
    """Criterio: las dos wallets tienen que existir; un identificador desconocido no pasa."""
    resultado = transaccion(sender_id=uuid4()).validate(
        available=Decimal("100"), signature_exists=False
    )

    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.UNKNOWN_WALLET


def test_req_04_monto_no_finito_se_rechaza_sin_levantar_el_error(transaccion):
    """Criterio: un monto `NaN` o infinito se rechaza como no positivo, sin excepción.

    `NaN` no es comparable ni cuantizable —`quantize` levanta `InvalidOperation`— y
    PostgreSQL tampoco lo detiene, porque evalúa `'NaN'::numeric > 0` como verdadero.
    """
    for monto in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")):
        resultado = transaccion(amount=monto).validate(
            available=Decimal("100"), signature_exists=False
        )
        assert resultado.accepted is False, monto
        assert resultado.reason is RejectionReason.AMOUNT_NOT_POSITIVE, monto
