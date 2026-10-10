"""REQ-07: el hash cubre el contenido agrupado; cambiar un dato agrupado lo cambia."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.block import Block
from src.domain.transaction import Transaction

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
