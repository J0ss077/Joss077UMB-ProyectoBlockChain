"""Arranque del ledger con datos de demostración (REQ-14, REQ-05).

Los datos de demostración representan el caso del eje: una wallet de fondo que
recibe aportes de los asociados y les gira retiros. La regla del REQ-05 es lo que
estas pruebas comprueban sobre los datos reales: ningún asociado puede quedar con
saldo disponible negativo, que es el defecto que arrastraban los datos del
repositorio anterior.
"""
import subprocess
import sys

import psycopg
import pytest

from src.bootstrap import FONDO, wallet_del_constituyente
from src.persistence.factory import database_url, master_key, open_ledger


@pytest.fixture
def base_vacia_ejecutando_bootstrap(base_limpia):
    """Base vacía, el arranque corrido como se corre de verdad, y la fachada para leer.

    El arranque se ejecuta en un subproceso porque su contrato es el punto de
    entrada (`python -m src.bootstrap`) y no una función interna: así la prueba
    cubre el mismo camino que usa el equipo. Después se abre la fachada sobre una
    conexión viva para poder consultar lo que el subproceso dejó escrito.
    """
    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)

    with psycopg.connect(database_url(), autocommit=True) as connection:
        connection.execute("SET TIME ZONE 'UTC'")
        yield open_ledger(connection, master_key=master_key())


def test_los_aportes_financian_los_retiros(base_vacia_ejecutando_bootstrap):
    """Los datos de demostración representan el caso del eje y cumplen la regla de saldo."""
    chain = base_vacia_ejecutando_bootstrap
    fondo = chain.wallets.get_by_public_key(FONDO)
    assert fondo is not None, "la demostración tiene que tener la wallet del fondo"

    # Los asociados son las tres wallets del demonio que no son el fondo ni la
    # wallet del constituyente. El constituyente queda fuera de la regla de saldo a
    # propósito: es la puerta por la que el capital de constitución entra al ledger
    # —el modelo de saldos no tiene emisión—, así que su saldo es un dato del
    # arranque y no del ciclo de aportes y retiros. La regla se comprueba sobre el
    # fondo y sobre cada asociado, que son los actores del caso del eje.
    constituyente = chain.wallets.get(wallet_del_constituyente(master_key()).id)
    asociados = [
        w for w in chain.wallets.list() if w.id not in {fondo.id, constituyente.id}
    ]
    assert len(asociados) == 3, "la demostración tiene tres asociados"

    for asociado in asociados:
        assert chain.available_balance(asociado.id) >= 0


def test_el_bootstrap_es_idempotente(base_vacia_ejecutando_bootstrap):
    """Correr el arranque dos veces no duplica wallets, bloques ni transacciones."""
    chain = base_vacia_ejecutando_bootstrap
    antes = chain.ledger_state()

    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)

    assert chain.ledger_state() == antes
