"""REQ-47: una cuenta común aprobada puede tener varias wallets y elegir con cuál opera.

La propiedad vive en `wallets.owner_id` (diseño §2), así que una cuenta puede
acumular wallets: la que crea la aprobación con el saldo de bienvenida y las que el
administrador le registra después, que nacen en cero. El tablero muestra el
selector «Tus wallets» cuando hay más de una y la sesión recuerda la elegida en
`session["wallet_elegida"]`, validada siempre contra las wallets de la cuenta; sin
elección —o con una que ya no le pertenece— opera la principal, que es la más
antigua.

Lo que se mide es el criterio del diseño: las tres wallets aparecen en el selector,
cambiar la elegida cambia el saldo y el historial, el envío sale de la elegida y una
wallet de otra cuenta no se puede elegir. El envío por nombre de usuario sigue
apuntando a la wallet principal del destinatario (decisión 6).
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import pytest

from src.accounts.service import Cuentas
from src.domain.blockchain import Blockchain
from src.domain.transaction import Transaction, TransactionStatus
from src.emision import CONSTITUYENTE_ID
from src.web.user import CLAVE_DE_LA_WALLET_ELEGIDA
from tests.integration.conftest import CONTRASENA_DE_PRUEBA

# El patrón de la tarjeta grande del saldo (`cantidad` en `_macros.html`): el
# `title` lleva el valor exacto con ocho decimales, que es el que se compara.
_PATRON_DEL_SALDO = re.compile(
    r'<p class="saldo-cifra">\s*<span class="cantidad" title="([0-9.]+)"'
)


def _saldo_de_la_tarjeta(cuerpo: str) -> str:
    """El saldo exacto que muestra la tarjeta principal del tablero."""
    hallado = _PATRON_DEL_SALDO.search(cuerpo)
    assert hallado is not None, "el tablero no muestra el saldo de la wallet elegida"
    return hallado.group(1)


def _corto(wallet_id: UUID) -> str:
    """La forma corta del identificador, igual que la macro `corto` de las plantillas."""
    texto = str(wallet_id)
    return f"{texto[:8]}…{texto[-4:]}"


@dataclass(frozen=True, slots=True)
class TresWallets:
    """Las tres wallets de la cuenta y los dos movimientos que las distinguen."""

    principal: UUID
    segunda: UUID
    tercera: UUID
    bienvenida: Transaction
    credito: Transaction


@pytest.fixture
def bruno(cuentas: Cuentas):
    """Un segundo usuario común aprobado, con su wallet de bienvenida."""
    return cuentas.aprobar(cuentas.registrar("bruno", CONTRASENA_DE_PRUEBA).id)


@pytest.fixture
def tres_wallets(cuentas: Cuentas, usuario_comun, ledger: Blockchain) -> TresWallets:
    """Le da tres wallets a la misma cuenta, con saldos distintos, y las devuelve.

    La principal es la del saldo de bienvenida (1000); a la segunda se le acredita
    250 por el camino de la emisión, para que el saldo cambie al elegirla; la
    tercera queda en cero. Los movimientos se devuelven para poder afirmar que el
    historial también cambia con la elegida.
    """
    principal = cuentas.wallet_principal(usuario_comun.id)
    segunda = cuentas.registrar_wallet(usuario_comun.id).id
    tercera = cuentas.registrar_wallet(usuario_comun.id).id
    bloque = ledger.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=segunda,
        monto=Decimal("250.00000000"),
    )
    (credito,) = ledger.transactions.of_block(bloque.id)
    bienvenida = next(
        fila
        for fila in ledger.wallet_history(principal)
        if fila.status is TransactionStatus.CONFIRMED
    )
    return TresWallets(principal, segunda, tercera, bienvenida, credito)


def test_req_47_la_cuenta_con_tres_wallets_tiene_su_selector(
    cliente_comun, usuario_comun, tres_wallets: TresWallets, cuentas: Cuentas
):
    """Criterio: las tres wallets de la cuenta aparecen en el selector del tablero."""
    assert cuentas.wallets_de(usuario_comun.id) == [
        tres_wallets.principal,
        tres_wallets.segunda,
        tres_wallets.tercera,
    ]

    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert "Tus wallets" in cuerpo
    assert 'action="/mi-wallet"' in cuerpo
    assert 'name="wallet"' in cuerpo
    assert "Elegir" in cuerpo
    for wallet in (tres_wallets.principal, tres_wallets.segunda, tres_wallets.tercera):
        assert f'value="{wallet}"' in cuerpo
        assert _corto(wallet) in cuerpo
    # Cada opción lleva el saldo de su wallet: se elige con la información a la vista.
    assert "1000.00000000" in cuerpo
    assert "250.00000000" in cuerpo
    assert "0.00000000" in cuerpo


def test_req_47_con_una_sola_wallet_no_hay_selector(cliente_comun):
    """Una cuenta con una sola wallet no ve el selector: no hay nada que elegir."""
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert "Tus wallets" not in cuerpo
    assert 'action="/mi-wallet"' not in cuerpo


def test_req_47_elegir_otra_wallet_cambia_el_saldo_y_el_historial(
    cliente_comun, tres_wallets: TresWallets
):
    """Criterio: cambiar la elegida cambia el saldo y el historial de la sesión."""
    assert _saldo_de_la_tarjeta(cliente_comun.get("/mi-tablero").get_data(as_text=True)) == (
        "1000.00000000"
    )
    historial = cliente_comun.get("/mi-historial").get_data(as_text=True)
    assert str(tres_wallets.bienvenida.id) in historial
    assert str(tres_wallets.credito.id) not in historial

    respuesta = cliente_comun.post(
        "/mi-wallet",
        data={"wallet": str(tres_wallets.segunda), "volver": "/mi-tablero"},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/mi-tablero"
    with cliente_comun.session_transaction() as sesion:
        assert sesion[CLAVE_DE_LA_WALLET_ELEGIDA] == str(tres_wallets.segunda)

    tablero = cliente_comun.get("/mi-tablero").get_data(as_text=True)
    assert _saldo_de_la_tarjeta(tablero) == "250.00000000"
    assert "Wallet elegida." in tablero
    historial = cliente_comun.get("/mi-historial").get_data(as_text=True)
    assert str(tres_wallets.credito.id) in historial
    assert str(tres_wallets.bienvenida.id) not in historial


def test_req_47_el_envio_sale_de_la_wallet_elegida(
    cliente_comun, tres_wallets: TresWallets, bruno, cuentas: Cuentas, conexion
):
    """Criterio: el emisor del envío es la wallet elegida y no otra de la cuenta."""
    wallet_de_bruno = cuentas.wallet_principal(bruno.id)
    cliente_comun.post(
        "/mi-envio", data={"destinatario": "bruno", "amount": "10.00000000"}
    )
    cliente_comun.post("/mi-wallet", data={"wallet": str(tres_wallets.segunda)})
    respuesta = cliente_comun.post(
        "/mi-envio", data={"destinatario": "bruno", "amount": "5.00000000"}
    )

    assert respuesta.status_code == 200
    filas = conexion.execute(
        """
        SELECT sender_id, receiver_id, amount, status FROM transactions
        WHERE sender_id IN (%s, %s)
        """,
        (tres_wallets.principal, tres_wallets.segunda),
    ).fetchall()
    assert set(filas) == {
        (tres_wallets.principal, wallet_de_bruno, Decimal("10.00000000"), "pending"),
        (tres_wallets.segunda, wallet_de_bruno, Decimal("5.00000000"), "pending"),
    }


def test_req_47_el_envio_por_nombre_va_a_la_wallet_principal_del_destinatario(
    cliente_comun, tres_wallets: TresWallets, bruno, cuentas: Cuentas, conexion
):
    """Criterio: el nombre de usuario apunta a la principal del destinatario.

    Se le registra a Bruno una segunda wallet para que la prueba distinga la
    principal de una adicional: el envío por nombre tiene que ir a la primera.
    """
    principal_de_bruno = cuentas.wallet_principal(bruno.id)
    adicional_de_bruno = cuentas.registrar_wallet(bruno.id).id
    assert adicional_de_bruno != principal_de_bruno

    cliente_comun.post(
        "/mi-envio", data={"destinatario": "bruno", "amount": "10.00000000"}
    )

    fila = conexion.execute(
        "SELECT receiver_id FROM transactions WHERE sender_id = %s",
        (tres_wallets.principal,),
    ).fetchone()
    assert fila == (principal_de_bruno,)


def test_req_47_una_wallet_ajena_no_se_puede_elegir(
    cliente_comun, tres_wallets: TresWallets, bruno, cuentas: Cuentas
):
    """Criterio: la sesión sólo elige wallets de su cuenta; una ajena se descarta."""
    ajena = cuentas.wallet_principal(bruno.id)

    respuesta = cliente_comun.post(
        "/mi-wallet", data={"wallet": str(ajena), "volver": "/mi-tablero"}
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/mi-tablero"
    with cliente_comun.session_transaction() as sesion:
        assert sesion.get(CLAVE_DE_LA_WALLET_ELEGIDA) is None
    assert _saldo_de_la_tarjeta(
        cliente_comun.get("/mi-tablero").get_data(as_text=True)
    ) == "1000.00000000"

    # Con una propia ya elegida, el intento ajeno no la reemplaza: la elección se
    # valida contra las wallets de la cuenta en cada cambio.
    cliente_comun.post("/mi-wallet", data={"wallet": str(tres_wallets.segunda)})
    cliente_comun.post("/mi-wallet", data={"wallet": str(ajena)})
    cliente_comun.post("/mi-wallet", data={"wallet": "no-es-un-uuid"})
    with cliente_comun.session_transaction() as sesion:
        assert sesion[CLAVE_DE_LA_WALLET_ELEGIDA] == str(tres_wallets.segunda)
    assert _saldo_de_la_tarjeta(
        cliente_comun.get("/mi-tablero").get_data(as_text=True)
    ) == "250.00000000"


def test_req_47_una_eleccion_guardada_que_no_es_de_la_cuenta_cae_a_la_principal(
    cliente_comun, tres_wallets: TresWallets, bruno, cuentas: Cuentas
):
    """Una cookie manipulada no saca a la sesión de las wallets de su cuenta."""
    with cliente_comun.session_transaction() as sesion:
        sesion[CLAVE_DE_LA_WALLET_ELEGIDA] = str(cuentas.wallet_principal(bruno.id))

    assert _saldo_de_la_tarjeta(
        cliente_comun.get("/mi-tablero").get_data(as_text=True)
    ) == "1000.00000000"
    historial = cliente_comun.get("/mi-historial").get_data(as_text=True)
    assert str(tres_wallets.bienvenida.id) in historial


def test_req_47_elegir_wallet_solo_vuelve_a_una_ruta_propia(
    cliente_comun, tres_wallets: TresWallets
):
    """El `volver` del formulario no sirve de redirección abierta."""
    propia = cliente_comun.post(
        "/mi-wallet",
        data={"wallet": str(tres_wallets.segunda), "volver": "/mi-historial"},
    )
    assert propia.headers["Location"] == "/mi-historial"

    # El navegador normaliza la barra invertida a barra, así que `/\evil.example`
    # equivale a `//evil.example` y también saldría del sitio.
    for externa in ("https://ejemplo.example", "//ejemplo.example", "/\\evil.example"):
        respuesta = cliente_comun.post(
            "/mi-wallet",
            data={"wallet": str(tres_wallets.principal), "volver": externa},
        )
        assert respuesta.headers["Location"] == "/mi-tablero", externa


def test_req_47_el_perfil_lista_las_tres_wallets_de_la_cuenta(
    cliente_comun, tres_wallets: TresWallets
):
    """Criterio: el perfil de la cuenta con varias wallets las lista todas, la principal primero."""
    cuerpo = cliente_comun.get("/perfil").get_data(as_text=True)

    assert "Tus wallets" in cuerpo
    # Cada wallet ocupa una fila con su identificador completo en el marcado y la
    # forma corta a la vista; el orden es el de `Cuentas.wallets_de`, principal primero.
    filas = cuerpo.split('class="dato-wallet"')[1:]
    assert len(filas) == 3
    ordenadas = [
        next(
            wallet
            for wallet in (
                tres_wallets.principal,
                tres_wallets.segunda,
                tres_wallets.tercera,
            )
            if str(wallet) in fila
        )
        for fila in filas
    ]
    assert ordenadas == [
        tres_wallets.principal,
        tres_wallets.segunda,
        tres_wallets.tercera,
    ]
