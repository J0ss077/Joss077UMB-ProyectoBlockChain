"""REQ-40: el registro de una wallet elige a su dueño.

El administrador registra la wallet y decide a quién se la asigna. La propiedad
vive en `wallets.owner_id` (diseño §2): una cuenta común aprobada puede quedar
como dueña de la wallet recién creada y la opción vacía deja `owner_id` nulo. Sólo
una cuenta común aprobada puede ser dueña; el administrador, las pendientes, las
rechazadas y un identificador inexistente se rechazan sin crear la wallet.

El registro sigue siendo del administrador (REQ-38) y es la única puerta que crea
wallets sueltas: la aprobación de REQ-33 crea la primera wallet de la cuenta y se
la asigna como dueña. Las pruebas cubren el servicio, que es donde vive la regla, y
la ruta, que es el camino que usa la persona.
"""
from uuid import uuid4

import pytest

from src.accounts.service import (
    MENSAJE_DE_DUENO_INVALIDO,
    Cuentas,
    DuenoInvalido,
)
from tests.integration.conftest import CONTRASENA_DE_PRUEBA


def _wallets_registradas(conexion) -> set:
    """Los identificadores de todas las wallets de la base."""
    return {
        fila[0]
        for fila in conexion.execute("SELECT id FROM wallets").fetchall()
    }


def _owner_de(conexion, wallet_id):
    """El dueño guardado en la fila, leído de la base y no del objeto que devolvió el servicio."""
    return conexion.execute(
        "SELECT owner_id FROM wallets WHERE id = %s", (wallet_id,)
    ).fetchone()[0]


def test_req_40_un_dueno_aprobado_queda_como_owner_id(
    cuentas: Cuentas, usuario_comun, ledger, conexion
):
    """Criterio: con una cuenta aprobada elegida, la wallet queda con su `owner_id`."""
    wallet = cuentas.registrar_wallet(usuario_comun.id)

    assert _owner_de(conexion, wallet.id) == usuario_comun.id
    # La wallet nueva se suma a las de la cuenta y no reemplaza a la principal.
    assert wallet.id in cuentas.wallets_de(usuario_comun.id)
    assert cuentas.wallet_principal(usuario_comun.id) != wallet.id
    assert cuentas.nombres_por_wallet()[wallet.id] == usuario_comun.username
    # Nace con saldo 0: las adicionales se mueven con transacciones (decisión 4).
    assert ledger.available_balance(wallet.id) == 0


def test_req_40_la_opcion_vacia_deja_la_wallet_sin_dueno(
    cuentas: Cuentas, ledger, conexion
):
    """Criterio: sin dueño elegido, la wallet existe con `owner_id` nulo."""
    antes = ledger.ledger_state()["wallets"]

    wallet = cuentas.registrar_wallet(None)

    assert _owner_de(conexion, wallet.id) is None
    assert ledger.ledger_state()["wallets"] == antes + 1
    assert wallet.id not in cuentas.nombres_por_wallet()


def test_req_40_un_dueno_que_no_sirve_no_crea_la_wallet(
    cuentas: Cuentas, administrador, conexion
):
    """Criterio: pendiente, rechazada, administrador o id inexistente no crean wallet.

    La validación de la regla vive en el servicio, porque el esquema ya no puede
    expresarla como CHECK entre dos tablas (decisión 5). El motivo es el mismo en
    los cuatro casos: el registro no cuenta en qué estado está la cuenta elegida.
    """
    pendiente = cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)
    rechazada = cuentas.registrar("carla", CONTRASENA_DE_PRUEBA)
    cuentas.rechazar(rechazada.id, "no corresponde")
    antes = _wallets_registradas(conexion)

    for no_puede in (pendiente, rechazada, administrador):
        with pytest.raises(DuenoInvalido) as error:
            cuentas.registrar_wallet(no_puede.id)
        assert str(error.value) == MENSAJE_DE_DUENO_INVALIDO
    with pytest.raises(DuenoInvalido):
        cuentas.registrar_wallet(uuid4())

    assert _wallets_registradas(conexion) == antes
    for cuenta in (pendiente, rechazada, administrador):
        assert cuentas.wallets_de(cuenta.id) == []


def test_req_40_el_formulario_ofrece_solo_las_cuentas_aprobadas(
    cliente_admin, administrador, usuario_comun, cuentas: Cuentas
):
    """Criterio: el selector trae las cuentas aprobadas y la opción de dejarla sin dueño.

    El administrador de la sesión y una cuenta pendiente no son opciones: el
    servicio las rechazaría, así que la pantalla no las ofrece.
    """
    pendiente = cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)

    respuesta = cliente_admin.get("/wallets")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert 'name="dueno"' in cuerpo
    assert "¿A quién se la asignas?" in cuerpo
    assert "Déjala sin dueño" in cuerpo
    assert "Registrar wallet" in cuerpo
    assert f'value="{usuario_comun.id}"' in cuerpo
    assert f">{usuario_comun.username}<" in cuerpo
    assert f'value="{pendiente.id}"' not in cuerpo
    assert f'value="{administrador.id}"' not in cuerpo


def test_req_40_sin_cuentas_aprobadas_el_formulario_lo_dice(cliente_admin):
    """Criterio: sin cuentas aprobadas queda la opción vacía y el aviso de que no hay."""
    cuerpo = cliente_admin.get("/wallets").get_data(as_text=True)

    assert "Déjala sin dueño" in cuerpo
    assert "No hay cuentas aprobadas todavía." in cuerpo
    assert 'name="dueno"' in cuerpo


def test_req_40_la_ruta_registra_la_wallet_a_nombre_del_dueno(
    cliente_admin, usuario_comun, cuentas: Cuentas, conexion
):
    """Criterio: el POST con una cuenta aprobada crea la wallet con ese `owner_id`."""
    antes = _wallets_registradas(conexion)

    respuesta = cliente_admin.post("/wallets", data={"dueno": str(usuario_comun.id)})

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert f"Wallet registrada a nombre de {usuario_comun.username}." in cuerpo
    (nueva,) = _wallets_registradas(conexion) - antes
    assert _owner_de(conexion, nueva) == usuario_comun.id
    assert str(nueva) in cuerpo
    assert nueva in cuentas.wallets_de(usuario_comun.id)


def test_req_40_la_ruta_puede_dejar_la_wallet_sin_dueno(cliente_admin, conexion):
    """Criterio: el POST con la opción vacía crea la wallet con `owner_id` nulo."""
    antes = _wallets_registradas(conexion)

    respuesta = cliente_admin.post("/wallets", data={"dueno": ""})

    assert respuesta.status_code == 200
    assert "Wallet registrada sin dueño." in respuesta.get_data(as_text=True)
    (nueva,) = _wallets_registradas(conexion) - antes
    assert _owner_de(conexion, nueva) is None


def test_req_40_la_ruta_rechaza_un_dueno_invalido_sin_crear_la_wallet(
    cliente_admin, administrador, cuentas: Cuentas, conexion
):
    """Criterio: la ruta repinta el formulario con el motivo y no escribe la wallet."""
    pendiente = cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)
    rechazada = cuentas.registrar("carla", CONTRASENA_DE_PRUEBA)
    cuentas.rechazar(rechazada.id, "no corresponde")
    antes = _wallets_registradas(conexion)

    for dueno in (
        str(pendiente.id),
        str(rechazada.id),
        str(administrador.id),
        str(uuid4()),
        "no-es-un-uuid",
    ):
        respuesta = cliente_admin.post("/wallets", data={"dueno": dueno})

        assert respuesta.status_code == 200, dueno
        cuerpo = respuesta.get_data(as_text=True)
        assert MENSAJE_DE_DUENO_INVALIDO in cuerpo, dueno
        assert "Wallet registrada a nombre de" not in cuerpo, dueno
        assert "Wallet registrada sin dueño" not in cuerpo, dueno
    assert _wallets_registradas(conexion) == antes
