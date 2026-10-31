"""La agenda del usuario común: `/mis-contactos`.

Se agrega a alguien por su nombre de usuario y sólo si es otra cuenta común
aprobada, que es la única que puede recibir un envío. La agenda es de un solo
sentido y de la sesión: nadie ve ni toca la agenda de otro.
"""
from decimal import Decimal

import pytest

from src.accounts.service import (
    LIMITE_DE_SUGERENCIAS,
    MENSAJE_CONTACTO_INEXISTENTE,
    MENSAJE_CONTACTO_PROPIO,
    MENSAJE_CONTACTO_REPETIDO,
    ContactoInvalido,
)
from tests.integration.conftest import CONTRASENA_DE_PRUEBA, ingresar_como


@pytest.fixture
def otro_comun(cuentas):
    """Una segunda cuenta común aprobada, para agendarla."""
    return cuentas.aprobar(cuentas.registrar("beto", CONTRASENA_DE_PRUEBA).id)


def test_se_agrega_un_contacto_por_su_nombre_y_se_lista(
    cliente_comun, usuario_comun, otro_comun, cuentas
):
    respuesta = cliente_comun.post("/mis-contactos", data={"usuario": "Beto"})

    assert respuesta.status_code == 302
    assert [c.id for c in cuentas.contactos(usuario_comun.id)] == [otro_comun.id]
    cuerpo = cliente_comun.get("/mis-contactos").get_data(as_text=True)
    assert "Agregaste a beto a tus contactos." in cuerpo
    assert 'aria-label="Contacto beto"' in cuerpo
    assert "/mi-tablero?destinatario=beto" in cuerpo


def test_la_agenda_es_de_un_solo_sentido(usuario_comun, otro_comun, cuentas):
    cuentas.agregar_contacto(usuario_comun.id, "beto")

    assert cuentas.contactos(otro_comun.id) == []


@pytest.mark.parametrize(
    ("nombre", "motivo"),
    [
        ("nadie", MENSAJE_CONTACTO_INEXISTENTE),
        ("ana", MENSAJE_CONTACTO_PROPIO),
    ],
)
def test_no_se_agrega_un_nombre_inexistente_ni_el_propio(
    usuario_comun, cuentas, nombre, motivo
):
    with pytest.raises(ContactoInvalido, match=motivo):
        cuentas.agregar_contacto(usuario_comun.id, nombre)
    assert cuentas.contactos(usuario_comun.id) == []


def test_no_se_agrega_una_cuenta_pendiente_ni_un_administrador(
    usuario_comun, administrador, cuentas
):
    cuentas.registrar("pendiente", CONTRASENA_DE_PRUEBA)

    for nombre in ("pendiente", administrador.username):
        with pytest.raises(ContactoInvalido, match=MENSAJE_CONTACTO_INEXISTENTE):
            cuentas.agregar_contacto(usuario_comun.id, nombre)
    assert cuentas.contactos(usuario_comun.id) == []


def test_agregar_dos_veces_avisa_y_no_duplica(usuario_comun, otro_comun, cuentas):
    cuentas.agregar_contacto(usuario_comun.id, "beto")

    with pytest.raises(ContactoInvalido, match=MENSAJE_CONTACTO_REPETIDO):
        cuentas.agregar_contacto(usuario_comun.id, "beto")
    assert len(cuentas.contactos(usuario_comun.id)) == 1


def test_se_quita_un_contacto(cliente_comun, usuario_comun, otro_comun, cuentas):
    cuentas.agregar_contacto(usuario_comun.id, "beto")

    respuesta = cliente_comun.post(f"/mis-contactos/{otro_comun.id}/quitar")

    assert respuesta.status_code == 302
    assert cuentas.contactos(usuario_comun.id) == []
    segunda = cliente_comun.post(f"/mis-contactos/{otro_comun.id}/quitar")
    assert segunda.status_code == 302
    assert "ya no estaba" in cliente_comun.get("/mis-contactos").get_data(as_text=True)


def test_quitar_solo_toca_la_agenda_de_la_sesion(
    cliente, usuario_comun, otro_comun, cuentas
):
    """La ruta dice a quién sacar, pero la agenda es siempre la de la sesión."""
    cuentas.agregar_contacto(usuario_comun.id, "beto")
    ingresar_como(cliente, "beto", CONTRASENA_DE_PRUEBA)

    cliente.post(f"/mis-contactos/{otro_comun.id}/quitar")

    assert [c.id for c in cuentas.contactos(usuario_comun.id)] == [otro_comun.id]


def test_la_agenda_cuenta_los_movimientos_con_cada_contacto(
    cliente_comun, usuario_comun, otro_comun, cuentas, ledger
):
    cuentas.agregar_contacto(usuario_comun.id, "beto")
    for _ in range(2):
        resultado = ledger.create_transaction(
            sender_id=usuario_comun.wallet_id,
            receiver_id=otro_comun.wallet_id,
            amount=Decimal("5"),
        )
        assert resultado.accepted, resultado.reason

    cuerpo = cliente_comun.get("/mis-contactos").get_data(as_text=True)

    assert "<b>2</b> movimientos contigo" in cuerpo


def test_el_boton_enviar_deja_el_destinatario_escrito(cliente_comun):
    cuerpo = cliente_comun.get("/mi-tablero?destinatario=beto").get_data(as_text=True)

    assert 'name="destinatario" value="beto"' in cuerpo


def test_la_agenda_exige_sesion(cliente):
    respuesta = cliente.get("/mis-contactos")

    assert respuesta.status_code == 302
    assert "/ingresar" in respuesta.headers["Location"]


def test_el_administrador_en_la_agenda_va_a_su_portada(cliente_admin):
    respuesta = cliente_admin.get("/mis-contactos")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/")


def _aprobado(cuentas, nombre):
    return cuentas.aprobar(cuentas.registrar(nombre, CONTRASENA_DE_PRUEBA).id)


def test_la_vista_previa_ofrece_solo_a_quien_puede_recibir(
    usuario_comun, administrador, otro_comun, cuentas
):
    _aprobado(cuentas, "roberto")
    cuentas.registrar("bea_pendiente", CONTRASENA_DE_PRUEBA)

    # Primero los que empiezan por lo tecleado y después los que sólo lo contienen.
    assert cuentas.sugerir_destinatarios(usuario_comun.id, "BE") == ["beto", "roberto"]
    # Ni la cuenta propia, ni un administrador, ni una pendiente.
    assert cuentas.sugerir_destinatarios(usuario_comun.id, "ana") == []
    assert cuentas.sugerir_destinatarios(usuario_comun.id, administrador.username) == []
    assert cuentas.sugerir_destinatarios(usuario_comun.id, "bea") == []


def test_la_vista_previa_de_agregar_no_ofrece_a_los_ya_agendados(
    usuario_comun, otro_comun, cuentas
):
    cuentas.agregar_contacto(usuario_comun.id, "beto")

    assert cuentas.sugerir_destinatarios(usuario_comun.id, "be") == ["beto"]
    assert cuentas.sugerir_destinatarios(usuario_comun.id, "be", sin_contactos=True) == []


@pytest.mark.parametrize("texto", ["", "   ", "%", "_"])
def test_la_vista_previa_no_lista_a_todos(usuario_comun, otro_comun, cuentas, texto):
    assert cuentas.sugerir_destinatarios(usuario_comun.id, texto) == []


def test_la_vista_previa_tiene_un_limite(usuario_comun, cuentas):
    for i in range(LIMITE_DE_SUGERENCIAS + 2):
        _aprobado(cuentas, f"socio{i}")

    assert len(cuentas.sugerir_destinatarios(usuario_comun.id, "socio")) == LIMITE_DE_SUGERENCIAS


def test_la_ruta_de_sugerencias_devuelve_las_opciones(cliente_comun, otro_comun):
    cuerpo = cliente_comun.get("/mis-contactos/sugerencias?q=be").get_data(as_text=True)

    assert 'role="option"' in cuerpo
    assert 'data-nombre="beto"' in cuerpo


def test_la_ruta_de_sugerencias_avisa_cuando_no_hay_nadie(cliente_comun):
    cuerpo = cliente_comun.get("/mis-contactos/sugerencias?q=zzz").get_data(as_text=True)

    assert 'role="option"' not in cuerpo
    assert "No encontramos a nadie con ese nombre de usuario." in cuerpo


def test_los_campos_de_destinatario_piden_la_vista_previa(cliente_comun):
    agenda = cliente_comun.get("/mis-contactos").get_data(as_text=True)
    tablero = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert 'data-sugerencias="/mis-contactos/sugerencias?sin_contactos=1"' in agenda
    assert 'data-sugerencias="/mis-contactos/sugerencias"' in tablero


def test_las_sugerencias_exigen_sesion(cliente):
    respuesta = cliente.get("/mis-contactos/sugerencias?q=be")

    assert respuesta.status_code == 302
    assert "/ingresar" in respuesta.headers["Location"]


def test_el_administrador_no_pide_sugerencias(cliente_admin):
    respuesta = cliente_admin.get("/mis-contactos/sugerencias?q=be")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/")
