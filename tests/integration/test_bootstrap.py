"""Arranque del ledger con datos de demostración (REQ-14, REQ-05).

Los datos de demostración representan el caso del eje: una wallet de fondo que
recibe aportes de los asociados y les gira retiros. La regla del REQ-05 es lo que
estas pruebas comprueban sobre los datos reales: ningún asociado puede quedar con
saldo disponible negativo, que es el defecto que arrastraban los datos del
repositorio anterior.
"""
import subprocess
import sys

from src.bootstrap import FONDO, wallet_del_constituyente
from src.persistence.factory import master_key


def test_los_aportes_financian_los_retiros(base_vacia_ejecutando_bootstrap):
    """Los datos de demostración representan el caso del eje y cumplen la regla de saldo."""
    chain = base_vacia_ejecutando_bootstrap
    fondo = chain.wallets.get_by_public_key(FONDO)
    assert fondo is not None, "la demostración tiene que tener la wallet del fondo"

    # Los asociados son las tres wallets de la demostración que no son el fondo ni la
    # wallet del constituyente. El constituyente queda fuera de la regla de saldo a
    # propósito: es la puerta por la que el capital de constitución entra al ledger
    # —el modelo de saldos no tiene emisión—, así que su saldo es un dato del
    # arranque y no del ciclo de aportes y retiros. La regla se comprueba sobre el
    # fondo y sobre cada asociado, que son los actores del caso del eje.
    constituyente = wallet_del_constituyente(master_key())
    asociados = [
        w for w in chain.wallets.list() if w.id not in {fondo.id, constituyente.id}
    ]
    assert len(asociados) == 3, "la demostración tiene tres asociados"

    for wallet in [fondo, *asociados]:
        assert chain.available_balance(wallet.id) >= 0


def test_el_bootstrap_es_idempotente(base_vacia_ejecutando_bootstrap):
    """Correr el arranque dos veces no duplica wallets, bloques ni transacciones."""
    chain = base_vacia_ejecutando_bootstrap
    antes = chain.ledger_state()

    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)

    assert chain.ledger_state() == antes
