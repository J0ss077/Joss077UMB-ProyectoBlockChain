"""El mapa de wallet a nombre de usuario que usa la presentación.

`Cuentas.nombres_por_wallet` es una lectura: devuelve el dueño de cada wallet que
tiene cuenta y nada más. Las cuentas pendientes o rechazadas no tienen wallet, y
las wallets que registra el administrador no tienen dueño, así que ninguna de las
dos aparece en el mapa.
"""
from src.accounts.service import Cuentas
from tests.integration.conftest import CONTRASENA_DE_PRUEBA


def test_el_mapa_tiene_el_dueno_de_cada_wallet_aprobada(cuentas: Cuentas, ledger):
    aprobada = cuentas.aprobar(cuentas.registrar("ana", CONTRASENA_DE_PRUEBA).id)
    pendiente = cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)
    sin_dueno = ledger.register_wallet()

    nombres = cuentas.nombres_por_wallet()

    assert nombres[aprobada.wallet_id] == "ana"
    assert "beto" not in nombres.values()
    assert pendiente.wallet_id is None
    assert sin_dueno.id not in nombres
