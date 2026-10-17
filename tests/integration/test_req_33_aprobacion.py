"""REQ-33: la aprobación crea la wallet, acredita 1000 y gana un bloque.

Las tres escrituras de la aprobación —wallet, bloque con el crédito y estado del
usuario— caen dentro de una sola transacción de base (`factory.transaction()`), y
el `commit` único es lo que hace que un fallo del crédito no deje nada escrito.
La segunda aprobación de la misma cuenta falla antes de escribir: no crea otra
wallet ni repite el crédito.
"""
from uuid import UUID, uuid4

import pytest

from src.accounts.model import APROBADO, PENDIENTE, Usuario
from src.accounts.service import Cuentas, UsuarioInexistente, UsuarioNoPendiente
from src.domain.blockchain import Blockchain
from src.domain.transaction import TransactionStatus
from src.emision import CONSTITUYENTE_ID, SALDO_DE_BIENVENIDA
from src.persistence.factory import transaction


def _estado() -> dict[str, int]:
    """Conteos de las cuatro tablas, leídos en una transacción propia."""
    with transaction() as actual:
        return {
            "wallets": actual.ledger.wallets.count(),
            "blocks": actual.ledger.blocks.count(),
            "transactions": actual.ledger.transactions.count(),
            "usuarios": actual.usuarios.count(),
        }


def _usuario(usuario_id: UUID) -> Usuario:
    """La fila del usuario leída de la base, no el objeto que devolvió el servicio."""
    with transaction() as actual:
        usuario = actual.usuarios.get(usuario_id)
    assert usuario is not None
    return usuario


def test_req_33_aprobar_crea_wallet_saldo_y_un_bloque(cuentas: Cuentas, ledger: Blockchain):
    """Criterio: una wallet ligada al usuario con 1000 disponibles, el constituyente
    bajó 1000 y la cadena ganó un bloque con esa única transacción."""
    creado = cuentas.registrar("ana", "secreta1")
    antes = ledger.ledger_state()
    antes_constituyente = ledger.available_balance(CONSTITUYENTE_ID)
    ultimo = ledger.blocks.last()

    aprobado = cuentas.aprobar(creado.id)

    assert aprobado.estado == APROBADO
    assert aprobado.wallet_id is not None
    assert aprobado.aprobado_en is not None
    wallet = ledger.wallets.get(aprobado.wallet_id)
    assert wallet is not None
    assert ledger.available_balance(wallet.id) == SALDO_DE_BIENVENIDA
    assert ledger.available_balance(CONSTITUYENTE_ID) == (
        antes_constituyente - SALDO_DE_BIENVENIDA
    )
    assert ledger.ledger_state() == {
        "wallets": antes["wallets"] + 1,
        "blocks": antes["blocks"] + 1,
        "transactions": antes["transactions"] + 1,
    }

    bloque = ledger.blocks.last()
    assert bloque.block_index == ultimo.block_index + 1
    assert bloque.previous_hash == ultimo.hash
    filas = ledger.transactions.of_block(bloque.id)
    assert len(filas) == 1
    credito = filas[0]
    assert credito.status is TransactionStatus.CONFIRMED
    assert credito.sender_id == CONSTITUYENTE_ID
    assert credito.receiver_id == wallet.id
    assert credito.amount == SALDO_DE_BIENVENIDA
    assert ledger.verify_chain().valid is True


def test_req_33_aprobar_dos_veces_no_crea_dos_wallets(cuentas: Cuentas):
    """Criterio: la segunda aprobación falla sin escribir ni crear otra wallet."""
    creado = cuentas.registrar("ana", "secreta1")
    primera = cuentas.aprobar(creado.id)
    antes = _estado()

    with pytest.raises(UsuarioNoPendiente):
        cuentas.aprobar(creado.id)

    assert _estado() == antes
    fila = _usuario(creado.id)
    assert fila.estado == APROBADO
    assert fila.wallet_id == primera.wallet_id


def test_req_33_si_falla_el_credito_no_queda_la_wallet(
    cuentas: Cuentas, monkeypatch: pytest.MonkeyPatch
):
    """Criterio: si el crédito falla no queda ni la wallet ni el cambio de estado.

    El fallo se inyecta en `Blockchain.acreditar` ya dentro de la transacción, con
    la wallet recién insertada; el ROLLBACK tiene que dejar la base exactamente
    como estaba, incluida la fila del usuario.
    """
    creado = cuentas.registrar("ana", "secreta1")
    antes = _estado()
    antes_usuario = _usuario(creado.id)

    def credito_que_falla(*args, **kwargs):
        raise RuntimeError("fallo inyectado en el crédito")

    monkeypatch.setattr(Blockchain, "acreditar", credito_que_falla)

    with pytest.raises(RuntimeError, match="fallo inyectado en el crédito"):
        cuentas.aprobar(creado.id)

    assert _estado() == antes
    despues = _usuario(creado.id)
    assert despues == antes_usuario
    assert despues.estado == PENDIENTE
    assert despues.wallet_id is None
    assert despues.aprobado_en is None


def test_req_31_una_cuenta_inexistente_no_se_puede_aprobar_ni_rechazar(cuentas: Cuentas):
    """Criterio: aprobar o rechazar un identificador desconocido falla sin escribir."""
    antes = _estado()
    with pytest.raises(UsuarioInexistente):
        cuentas.aprobar(uuid4())
    with pytest.raises(UsuarioInexistente):
        cuentas.rechazar(uuid4(), "no existe")
    assert _estado() == antes
