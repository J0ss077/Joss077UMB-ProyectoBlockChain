"""REQ-02: la validación exige que la firma corresponda a la llave pública del emisor."""
from decimal import Decimal

from src.domain.transaction import RejectionReason


def test_req_02_firma_de_otra_wallet_se_rechaza(transaccion_de_otra_wallet):
    """Criterio: la misma transacción firmada por otra wallet se rechaza, y el motivo lo dice."""
    resultado = transaccion_de_otra_wallet.validate(available=Decimal("100"), signature_exists=False)
    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.BAD_SIGNATURE


def test_req_02_transaccion_correcta_se_acepta(transaccion):
    """Criterio: una transacción firmada por su emisor verifica y se acepta."""
    assert transaccion().is_valid(available=Decimal("100"), signature_exists=False) is True
