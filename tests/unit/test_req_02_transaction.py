"""REQ-02: la validación exige que la firma corresponda a la llave pública del emisor."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from src.domain.transaction import RejectionReason, Transaction, TransactionStatus

# Valores fijos para fijar los formatos canónicos: las públicas miden los mismos
# 66 caracteres hexadecimales que las reales, y la marca de tiempo va fijada
# para que el literal de la prueba sea reproducible.
CLAVE_EMISOR = "02" + "aa" * 32
CLAVE_RECEPTOR = "03" + "bb" * 32
TIMESTAMP = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def test_req_02_firma_de_otra_wallet_se_rechaza(transaccion_de_otra_wallet):
    """Criterio: la misma transacción firmada por otra wallet se rechaza, y el motivo lo dice."""
    resultado = transaccion_de_otra_wallet.validate(available=Decimal("100"), signature_exists=False)
    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.BAD_SIGNATURE


def test_req_02_transaccion_correcta_se_acepta(transaccion):
    """Criterio: una transacción firmada por su emisor verifica y se acepta."""
    assert transaccion().is_valid(available=Decimal("100"), signature_exists=False) is True


def test_req_02_el_payload_de_firma_es_la_cadena_canonica():
    """Criterio: lo que se firma es literalmente id|pública emisor|pública receptor|monto|fecha.

    El literal se escribe a mano: cambiar un separador, el orden de las públicas
    o la escala del monto cambia lo que se firma y esta prueba falla.
    """
    transaccion = Transaction(
        id=UUID("00000000-0000-0000-0000-00000000000f"),
        sender_id=UUID("00000000-0000-0000-0000-0000000000a1"),
        receiver_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        amount=Decimal("12.34000000"),
        status=TransactionStatus.PENDING,
        signature="firma-que-no-va-en-este-payload",
        block_id=None,
        created_at=TIMESTAMP,
    )
    esperado = (
        "00000000-0000-0000-0000-00000000000f"
        f"|{CLAVE_EMISOR}|{CLAVE_RECEPTOR}"
        "|12.34000000|2026-10-10T12:00:00+00:00"
    ).encode("utf-8")
    assert transaccion.signing_payload(CLAVE_EMISOR, CLAVE_RECEPTOR) == esperado


def test_req_07_el_payload_del_hash_es_la_cadena_canonica():
    """Criterio: la forma que hashea el bloque es id|emisor|receptor|monto|firma|fecha.

    El `status` y el `block_id` van puestos con valores que el payload no debe
    contener: los dos cambian justo al agrupar, y el hash del bloque se calcula
    antes de ese cambio.
    """
    transaccion = Transaction(
        id=UUID("00000000-0000-0000-0000-00000000000f"),
        sender_id=UUID("00000000-0000-0000-0000-0000000000a1"),
        receiver_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        amount=Decimal("12.34000000"),
        status=TransactionStatus.CONFIRMED,
        signature="firma-de-prueba",
        block_id=UUID("00000000-0000-0000-0000-0000000000cc"),
        created_at=TIMESTAMP,
    )
    esperado = (
        "00000000-0000-0000-0000-00000000000f"
        "|00000000-0000-0000-0000-0000000000a1"
        "|00000000-0000-0000-0000-0000000000b1"
        "|12.34000000|firma-de-prueba|2026-10-10T12:00:00+00:00"
    )
    assert transaccion.hash_payload() == esperado
