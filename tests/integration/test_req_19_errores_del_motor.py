"""REQ-19: los errores del esquema suben sin traducir ni duplicar los CHECK.

Las violaciones se provocan escribiendo directo en la base, porque el camino de
la aplicación las evita validando antes (REQ-04). Lo que se comprueba es que
nadie atrapa el error en el medio: el tipo que llega es el del motor.
"""
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest


def test_req_19_monto_no_positivo_levanta_check_violation(conexion, base_limpia, emisora, receptora):
    """Un monto menor o igual a cero viola el CHECK y llega como `CheckViolation`."""
    with pytest.raises(psycopg.errors.CheckViolation):
        conexion.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, signature) VALUES (%s, %s, %s, %s)",
            (emisora.id, receptora.id, Decimal("-1"), "firma-x"),
        )
    conexion.rollback()


def test_req_19_wallet_inexistente_levanta_foreign_key_violation(conexion, base_limpia, emisora, receptora):
    """Una wallet que no existe viola la clave foránea, sin traducción de por medio."""
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conexion.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, signature) VALUES (%s, %s, %s, %s)",
            (emisora.id, uuid4(), Decimal("1"), "firma-sin-wallet"),
        )
    conexion.rollback()


def test_req_19_la_violacion_no_deja_fila_a_medias(conexion, base_limpia, emisora, receptora):
    """El error del motor deja la tabla como estaba: ninguna fila a medias."""
    with pytest.raises(psycopg.errors.CheckViolation):
        conexion.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, signature) VALUES (%s, %s, %s, %s)",
            (emisora.id, receptora.id, Decimal("0"), "firma-cero"),
        )
    conexion.rollback()

    cursor = conexion.execute("SELECT count(*) FROM transactions")
    assert cursor.fetchone()[0] == 0
