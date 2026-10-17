"""REQ-30 y REQ-33: la semilla, sus cuentas y el recorrido de demostración.

Además de las cinco wallets de la convención, el arranque deja el administrador
—aprobado y sin wallet, que es la única cuenta a la que el CHECK se lo permite— y
un usuario de demostración por cada wallet sembrada, todos aprobados y con la
contraseña documentada. La semilla se puede correr dos veces: no duplica cuentas
ni wallets.

El tercer caso es el recorrido del diseño (§13) de punta a punta con el cliente de
pruebas: el administrador aprueba a una persona, esa persona ingresa, ve su saldo
de bienvenida, manda un envío, el administrador agrupa el bloque, y la persona ve
la transacción confirmada en su historial y en su verificación.
"""
import re
import subprocess
import sys
from decimal import Decimal

from src.accounts.credentials import verificar_contrasena
from src.accounts.model import ADMINISTRADOR, APROBADO, USUARIO
from src.bootstrap import (
    CONTRASENA_DE_DEMOSTRACION,
    MENSAJE_DE_VOLUMEN_VIEJO,
    NOMBRES_DE_DEMOSTRACION,
    USERNAME_DEL_ADMINISTRADOR,
)
from src.domain.transaction import TransactionStatus
from src.persistence.factory import admin_password, transaction
from tests.integration.conftest import ingresar_como

# La cuenta que se registra y se aprueba en el recorrido. El nombre y la
# contraseña son de la prueba: la persona del recorrido no es una cuenta
# sembrada, es una que llega por el registro como llegaría cualquiera.
USUARIO_DE_LA_DEMO = "persona-demo"
CONTRASENA_DE_LA_DEMO = "clave-de-la-persona"
MONTO_DEL_ENVIO = Decimal("125.00000000")


def test_req_30_la_semilla_crea_el_administrador_y_cinco_usuarios(
    base_vacia_ejecutando_bootstrap,
):
    """Criterio: el administrador queda aprobado y sin wallet con la contraseña de
    `ADMIN_PASSWORD`, y cada una de las cinco wallets sembradas tiene su usuario
    aprobado con la contraseña de demostración."""
    chain = base_vacia_ejecutando_bootstrap

    with transaction() as actual:
        administrador = actual.usuarios.get_by_username(USERNAME_DEL_ADMINISTRADOR)
        assert administrador is not None
        assert administrador.role == ADMINISTRADOR
        assert administrador.estado == APROBADO
        assert administrador.wallet_id is None
        assert administrador.aprobado_en is not None
        assert verificar_contrasena(admin_password(), administrador.password_hash)

        demostracion = [
            actual.usuarios.get_by_username(nombre)
            for nombre in NOMBRES_DE_DEMOSTRACION
        ]

    assert all(usuario is not None for usuario in demostracion)
    assert {usuario.role for usuario in demostracion} == {USUARIO}
    assert {usuario.estado for usuario in demostracion} == {APROBADO}
    assert all(
        verificar_contrasena(CONTRASENA_DE_DEMOSTRACION, usuario.password_hash)
        for usuario in demostracion
    )
    # Uno por cada wallet sembrada y ninguno repetida: el conjunto de wallets de
    # las cinco cuentas es el conjunto de wallets de la semilla.
    assert len({usuario.wallet_id for usuario in demostracion}) == 5
    assert {usuario.wallet_id for usuario in demostracion} == {
        wallet.id for wallet in chain.wallets.list()
    }


def test_req_30_la_semilla_es_idempotente(base_vacia_ejecutando_bootstrap):
    """Criterio: correr el arranque dos veces no duplica usuarios ni wallets."""
    chain = base_vacia_ejecutando_bootstrap
    with transaction() as actual:
        cuentas_antes = actual.usuarios.count()
    ledger_antes = chain.ledger_state()
    assert cuentas_antes == 6, "el administrador y los cinco de demostración"

    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)

    with transaction() as actual:
        assert actual.usuarios.count() == cuentas_antes
        administrador = actual.usuarios.get_by_username(USERNAME_DEL_ADMINISTRADOR)
        assert administrador is not None and administrador.wallet_id is None
    assert chain.ledger_state() == ledger_antes


def test_req_30_el_arranque_falla_si_el_nombre_admin_ya_es_otra_cuenta(
    base_limpia, cuentas
):
    """Criterio: el administrador se reconoce por rol y estado, no sólo por nombre.

    Si una persona se registró como `admin` antes del primer arranque, la semilla no
    puede crear al administrador. En vez de seguir sin nadie que apruebe, falla con
    un mensaje que dice liberar el nombre o recrear el volumen.
    """
    cuentas.registrar(USERNAME_DEL_ADMINISTRADOR, CONTRASENA_DE_LA_DEMO)

    proceso = subprocess.run(
        [sys.executable, "-m", "src.bootstrap"], capture_output=True, text=True
    )

    assert proceso.returncode == 1, proceso.stdout
    assert USERNAME_DEL_ADMINISTRADOR in proceso.stderr
    assert "rol `usuario`" in proceso.stderr
    assert "estado `pendiente`" in proceso.stderr
    assert "no es un administrador aprobado" in proceso.stderr
    assert "Recreá el volumen" in proceso.stderr
    assert "Traceback" not in proceso.stderr


def test_req_30_un_volumen_viejo_falla_con_el_mensaje(
    base_vacia_ejecutando_bootstrap, conexion
):
    """Criterio: sin la tabla `users`, el arranque falla con el mensaje y el código 1.

    El proyecto no tiene migraciones (diseño §6): un volumen anterior a las cuentas es
    un caso que el arranque tiene que reconocer y explicar, no un volcado del motor.
    Se renombra la tabla y se restaura en el `finally`; es la única prueba que toca el
    esquema, y lo hace para que el motor levante el `UndefinedTable` real que el
    arranque captura.
    """
    tabla_vieja = "users_de_un_volumen_anterior"
    conexion.execute(f"ALTER TABLE users RENAME TO {tabla_vieja}")
    try:
        proceso = subprocess.run(
            [sys.executable, "-m", "src.bootstrap"], capture_output=True, text=True
        )
    finally:
        conexion.execute(f"ALTER TABLE {tabla_vieja} RENAME TO users")

    assert proceso.returncode == 1, proceso.stdout
    assert MENSAJE_DE_VOLUMEN_VIEJO in proceso.stderr
    assert "Traceback" not in proceso.stderr


def test_req_33_el_recorrido_de_demostracion_completo(
    base_vacia_ejecutando_bootstrap, cliente
):
    """Criterio: el administrador aprueba a una persona, esa persona ingresa, ve su
    saldo de bienvenida, manda un envío, lo ve confirmado en su historial y
    verifica su historial."""
    # 1. El administrador sembrado ingresa con la contraseña del entorno.
    ingresar_como(cliente, USERNAME_DEL_ADMINISTRADOR, admin_password())

    # 2. Registra a la persona y la aprueba desde la cola real, sin conocer su
    # identificador de antemano: se lo da la propia página de pendientes.
    registro = cliente.post(
        "/registrarme",
        data={
            "usuario": USUARIO_DE_LA_DEMO,
            "contrasena": CONTRASENA_DE_LA_DEMO,
            "repetir": CONTRASENA_DE_LA_DEMO,
        },
    )
    assert registro.status_code == 200
    assert "esperando aprobación" in registro.get_data(as_text=True)
    cola = cliente.get("/admin/pendientes").get_data(as_text=True)
    aprobar = re.search(r"/admin/pendientes/[0-9a-f-]+/aprobar", cola)
    assert aprobar is not None, "la persona recién registrada tiene que estar en la cola"
    assert cliente.post(aprobar.group(0)).status_code == 302

    with transaction() as actual:
        persona = actual.usuarios.get_by_username(USUARIO_DE_LA_DEMO)
        assert persona is not None
        assert persona.estado == APROBADO
        assert persona.wallet_id is not None
        wallet_de_la_persona = persona.wallet_id

    # 3. La persona ingresa y ve su saldo de bienvenida (REQ-33).
    cliente.post("/salir")
    ingreso = cliente.post(
        "/ingresar",
        data={"usuario": USUARIO_DE_LA_DEMO, "contrasena": CONTRASENA_DE_LA_DEMO},
    )
    assert ingreso.status_code == 302
    tablero = cliente.get("/mi-tablero").get_data(as_text=True)
    assert "1000.00000000" in tablero

    # 4. Manda un envío a la wallet de un usuario de demostración. El destinatario
    # se resuelve por nombre de usuario, que es el camino normal del tablero.
    envio = cliente.post(
        "/mi-envio",
        data={"destinatario": "fondo", "amount": str(MONTO_DEL_ENVIO)},
    )
    assert envio.status_code == 200

    with transaction() as actual:
        fila = next(
            transaction
            for transaction in actual.ledger.wallet_history(wallet_de_la_persona)
            if transaction.sender_id == wallet_de_la_persona
            and transaction.receiver_id != wallet_de_la_persona
        )
        assert fila.amount == MONTO_DEL_ENVIO
        assert fila.status is TransactionStatus.PENDING
        envio_id = fila.id

    # 5. El historial propio ya la lista, todavía pendiente.
    historial = cliente.get("/mi-historial").get_data(as_text=True)
    assert str(envio_id) in historial
    assert "pending" in historial

    # 6. El administrador agrupa el pool: sin eso el envío no puede confirmarse.
    cliente.post("/salir")
    ingresar_como(cliente, USERNAME_DEL_ADMINISTRADOR, admin_password())
    assert cliente.post("/bloques").status_code == 200
    cliente.post("/salir")
    ingreso = cliente.post(
        "/ingresar",
        data={"usuario": USUARIO_DE_LA_DEMO, "contrasena": CONTRASENA_DE_LA_DEMO},
    )
    assert ingreso.status_code == 302

    # 7. La persona ve el envío confirmado en su historial y en su verificación.
    historial = cliente.get("/mi-historial").get_data(as_text=True)
    assert str(envio_id) in historial
    assert "confirmed" in historial
    verificacion = cliente.get("/mi-verificacion").get_data(as_text=True)
    assert "respaldado" in verificacion
    assert str(envio_id) in verificacion

    with transaction() as actual:
        confirmada = actual.ledger.transactions.get(envio_id)
        assert confirmada is not None
        assert confirmada.status is TransactionStatus.CONFIRMED
        assert actual.ledger.available_balance(wallet_de_la_persona) == (
            Decimal("1000.00000000") - MONTO_DEL_ENVIO
        )
