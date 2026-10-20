"""El inicio del usuario común (`/mi-tablero`).

La lista de movimientos vive en Mi historial; el inicio muestra lo que ninguna
otra pestaña tiene: cuánto entró y salió este mes y con quién se mueve más la
persona, con un atajo para enviarle.
"""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.transaction import Transaction, TransactionStatus
from src.emision import CONSTITUYENTE_ID
from src.web.user import _con_quien_mas, _resumen_del_mes
from tests.integration.conftest import CONTRASENA_DE_PRUEBA

PROPIA = uuid4()
OTRA = uuid4()
AHORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _movimiento(sender, receiver, amount, status=TransactionStatus.CONFIRMED, created_at=AHORA):
    return Transaction(
        id=uuid4(),
        sender_id=sender,
        receiver_id=receiver,
        amount=Decimal(amount),
        status=status,
        signature="firma",
        block_id=None,
        created_at=created_at,
    )


def test_el_resumen_del_mes_suma_solo_lo_completado_del_mes():
    historial = [
        _movimiento(OTRA, PROPIA, "50"),
        _movimiento(PROPIA, OTRA, "20"),
        _movimiento(PROPIA, OTRA, "5", status=TransactionStatus.PENDING),
        _movimiento(PROPIA, OTRA, "9", status=TransactionStatus.REJECTED),
        _movimiento(OTRA, PROPIA, "100", created_at=datetime(2026, 9, 30, 23, 0, tzinfo=UTC)),
    ]

    resumen = _resumen_del_mes(historial, PROPIA, AHORA)

    assert resumen.mes == "octubre"
    assert (resumen.recibido, resumen.recepciones) == (Decimal("50"), 1)
    assert (resumen.enviado, resumen.envios) == (Decimal("20"), 1)
    assert resumen.diferencia == Decimal("30")


def test_con_quien_mas_ordena_y_no_cuenta_rechazos_ni_la_bienvenida():
    tercera = uuid4()
    historial = [
        _movimiento(CONSTITUYENTE_ID, PROPIA, "1000"),
        _movimiento(PROPIA, tercera, "1"),
        _movimiento(PROPIA, OTRA, "1"),
        _movimiento(OTRA, PROPIA, "1", status=TransactionStatus.PENDING),
        _movimiento(PROPIA, tercera, "1", status=TransactionStatus.REJECTED),
    ]

    personas = _con_quien_mas(historial, PROPIA)

    assert [(p.wallet_id, p.movimientos) for p in personas] == [(OTRA, 2), (tercera, 1)]


@pytest.fixture
def bruno(cuentas):
    return cuentas.aprobar(cuentas.registrar("bruno", CONTRASENA_DE_PRUEBA).id)


def test_el_inicio_ya_no_lista_los_movimientos(cliente_comun):
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert "Mis movimientos" not in cuerpo
    assert "Resumen de " in cuerpo
    assert "Con quién más te mueves" in cuerpo


def test_el_inicio_muestra_con_quien_mas_te_mueves(cliente_comun, bruno):
    cliente_comun.post("/mi-envio", data={"destinatario": "bruno", "amount": "10"})

    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert 'aria-label="Enviar a bruno"' in cuerpo
    assert "/mi-tablero?destinatario=bruno" in cuerpo
    assert "1 movimiento<" in cuerpo


def test_sin_movimientos_con_nadie_el_inicio_lo_dice(cliente_comun):
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert "Aún no te has movido con nadie." in cuerpo
