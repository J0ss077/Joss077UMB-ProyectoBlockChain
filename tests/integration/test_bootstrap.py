"""Arranque del ledger con datos de demostración (REQ-14, REQ-05, REQ-02).

Los datos de demostración representan el caso del eje: una wallet de fondo que
recibe aportes de los asociados y les gira retiros. Estas pruebas comprueban sobre
los datos reales que la regla del REQ-05 se cumple —ningún asociado ni el fondo
quedan con saldo disponible negativo, que es el defecto que arrastraban los datos
del repositorio anterior— y que la emisión fundacional no es una excepción a la
firma del REQ-02, aunque sí lo sea a la regla de saldo.
"""
import subprocess
import sys

from src.bootstrap import FONDO, wallet_del_constituyente
from src.domain.wallet import verify
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


def test_req_02_la_emision_fundacional_esta_firmada_por_el_constituyente(
    base_vacia_ejecutando_bootstrap,
):
    """REQ-02: la emisión fundacional se verifica contra la pública del constituyente.

    La emisión se escribe por el repositorio porque la regla de saldo (REQ-05) la
    rechazaría, ya que el modelo del eje no tiene emisión; la dispensa es solo para
    esa fila. La firma, en cambio, no se dispensa: se comprueba aquí contra la
    pública de su emisor, como la de cualquier otra transacción.
    """
    chain = base_vacia_ejecutando_bootstrap
    fondo = chain.wallets.get_by_public_key(FONDO)
    constituyente = wallet_del_constituyente(master_key())

    emision = next(
        t
        for t in chain.wallet_history(fondo.id)
        if t.sender_id == constituyente.id and t.receiver_id == fondo.id
    )

    assert emision.signature, "la emisión tiene que llevar firma, no una marca"
    assert verify(
        constituyente.public_key,
        emision.signature,
        emision.signing_payload(constituyente.public_key, fondo.public_key),
    )

    assert chain.verify_chain().valid is True
    assert chain.available_balance(constituyente.id) < 0
    assert chain.available_balance(fondo.id) >= 0
