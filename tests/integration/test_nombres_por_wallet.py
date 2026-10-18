"""El mapa de wallet a nombre de usuario que usa la presentación.

`nombres_por_wallet` es una lectura: devuelve el dueño de cada wallet que tiene
cuenta y nada más. Las cuentas pendientes y las rechazadas no tienen wallet —el
`CHECK` del esquema lo exige— y las wallets que registra el administrador no
tienen dueño, así que ninguna de las tres aparece. La prueba cubre las dos capas:
el adaptador PostgreSQL, que es donde vive la consulta, y el servicio, que es por
donde la presentación pide el mapa.
"""
from src.accounts.postgres import PostgresAccountsRepository
from src.accounts.service import Cuentas
from tests.integration.conftest import CONTRASENA_DE_PRUEBA


def _cuatro_casos(cuentas: Cuentas, ledger):
    """Deja una cuenta de cada clase y devuelve la aprobada y la wallet sin dueño.

    La aprobada es la única que tiene wallet; la pendiente y la rechazada no
    pueden tenerla y la wallet del administrador nace sin cuenta. Las tres formas
    de no aparecer quedan así en la misma base y en la misma prueba.
    """
    aprobada = cuentas.aprobar(cuentas.registrar("ana", CONTRASENA_DE_PRUEBA).id)
    pendiente = cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)
    rechazada = cuentas.registrar("carla", CONTRASENA_DE_PRUEBA)
    cuentas.rechazar(rechazada.id, "no corresponde")
    sin_dueno = ledger.register_wallet()
    return aprobada, pendiente, rechazada, sin_dueno


def test_el_repositorio_solo_devuelve_las_wallets_con_cuenta(cuentas, ledger, conexion):
    """El adaptador lee una sola fila por wallet y sólo si tiene dueño."""
    aprobada, pendiente, rechazada, sin_dueno = _cuatro_casos(cuentas, ledger)

    nombres = PostgresAccountsRepository(conexion).nombres_por_wallet()

    assert dict(nombres) == {aprobada.wallet_id: "ana"}
    assert pendiente.wallet_id is None
    assert rechazada.wallet_id is None
    assert sin_dueno.id not in nombres
    assert "beto" not in nombres.values()
    assert "carla" not in nombres.values()


def test_el_servicio_solo_devuelve_las_wallets_con_cuenta(cuentas, ledger):
    """El servicio devuelve el mismo mapa que el repositorio, sin agregar filas."""
    aprobada, pendiente, rechazada, sin_dueno = _cuatro_casos(cuentas, ledger)

    nombres = cuentas.nombres_por_wallet()

    assert dict(nombres) == {aprobada.wallet_id: "ana"}
    assert pendiente.wallet_id is None
    assert rechazada.wallet_id is None
    assert sin_dueno.id not in nombres
    assert "beto" not in nombres.values()
    assert "carla" not in nombres.values()
