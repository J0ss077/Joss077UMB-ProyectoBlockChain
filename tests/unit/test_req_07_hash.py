"""REQ-07: el hash cubre el contenido agrupado; cambiar un dato agrupado lo cambia."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from src.domain.block import Block
from src.domain.transaction import Transaction, TransactionStatus

# Marca de tiempo fija: el bloque la incluye en su hash, y fijarla hace
# reproducible el valor que las pruebas comparan.
TIMESTAMP = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bloque() -> Block:
    """Bloque sin hash calculado: lo que se mide es el que devuelve `calculate_hash`."""
    return Block(
        id=uuid4(),
        block_index=1,
        timestamp=TIMESTAMP,
        previous_hash="0" * 64,
        hash="",
    )


@pytest.fixture
def transacciones(transaccion) -> list[Transaction]:
    """Tres transacciones firmadas de montos distintos: el contenido que el bloque agrupa."""
    return [
        transaccion(amount=Decimal("10.00000000")).transaction,
        transaccion(amount=Decimal("20.00000000")).transaction,
        transaccion(amount=Decimal("30.00000000")).transaction,
    ]


def test_req_07_el_hash_es_sha256_hex_de_sesenta_y_cuatro(bloque, transacciones):
    """Criterio: el hash es un SHA-256 en hexadecimal minúscula de 64 caracteres."""
    valor = bloque.calculate_hash(transacciones)
    assert len(valor) == 64 and valor == valor.lower()
    int(valor, 16)


def test_req_07_cambiar_un_monto_agrupado_cambia_el_hash(bloque, transacciones):
    """Criterio: cambiar el monto de una transacción agrupada cambia el hash del bloque."""
    original = bloque.calculate_hash(transacciones)
    alteradas = [replace(transacciones[0], amount=Decimal("99.00000000")), *transacciones[1:]]
    assert bloque.calculate_hash(alteradas) != original


def test_req_07_el_orden_de_las_transacciones_no_cambia_el_hash(bloque, transacciones):
    """Criterio: el hash no depende del orden en que se leyeron las transacciones."""
    assert bloque.calculate_hash(list(reversed(transacciones))) == bloque.calculate_hash(transacciones)


def test_req_07_el_mensaje_hasheado_es_la_cadena_canonica():
    """Criterio: el hash es el SHA-256 del mensaje literal del brief, sin cambiar nada.

    El mensaje se escribe a mano —cabecera, y después los payloads en su orden
    alfabético— y las transacciones llegan al revés: cambiar un separador, quitar
    el orden o cambiar un campo del bloque o del payload cambia el resultado.
    """
    previous_hash = "ab" * 32
    bloque = Block(
        id=UUID("00000000-0000-0000-0000-0000000000bb"),
        block_index=7,
        timestamp=TIMESTAMP,
        previous_hash=previous_hash,
        hash="",
    )
    primera = Transaction(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        sender_id=UUID("00000000-0000-0000-0000-0000000000a1"),
        receiver_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        amount=Decimal("10.00000000"),
        status=TransactionStatus.PENDING,
        signature="firma-uno",
        block_id=None,
        created_at=TIMESTAMP,
    )
    segunda = Transaction(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        sender_id=UUID("00000000-0000-0000-0000-0000000000a2"),
        receiver_id=UUID("00000000-0000-0000-0000-0000000000b2"),
        amount=Decimal("20.00000000"),
        status=TransactionStatus.PENDING,
        signature="firma-dos",
        block_id=None,
        created_at=TIMESTAMP,
    )
    payload_primero = (
        "00000000-0000-0000-0000-000000000001"
        "|00000000-0000-0000-0000-0000000000a1"
        "|00000000-0000-0000-0000-0000000000b1"
        "|10.00000000|firma-uno|2026-10-10T12:00:00+00:00"
    )
    payload_segundo = (
        "00000000-0000-0000-0000-000000000002"
        "|00000000-0000-0000-0000-0000000000a2"
        "|00000000-0000-0000-0000-0000000000b2"
        "|20.00000000|firma-dos|2026-10-10T12:00:00+00:00"
    )
    mensaje = (
        "7|2026-10-10T12:00:00+00:00|" + previous_hash + "|"
        + payload_primero + "|" + payload_segundo
    )
    esperado = sha256(mensaje.encode("utf-8")).hexdigest()
    assert bloque.calculate_hash([segunda, primera]) == esperado
