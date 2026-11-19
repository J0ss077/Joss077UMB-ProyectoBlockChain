"""Panel de auditoría y ruta de reparaciones en /verificar (spec §4 y §5).

La pantalla de verificación suma, debajo del dictamen, el resumen del ledger, los
hallazgos con su severidad, las reparaciones guiadas y la tabla de bloques. La
lectura no escribe nada (REQ-22); las reparaciones son un POST aparte que exige
administrador (REQ-38) y confirmación explícita, y siempre termina en un 303 a
`/verificar` con un aviso en la bandeja.

La alteración de la cadena se hace con un `UPDATE` directo, que es el camino del
sabotaje: la fila cambia por fuera de la aplicación y la auditoría tiene que
enumerarla con su bloque y su transacción. El sello se inyecta con un archivo
temporal para no tocar el de `datos/`.
"""
from contextlib import contextmanager

import pytest

from src.domain.blockchain import ensure_genesis
from src.persistence.factory import open_ledger
from src.persistence.sello import SelloDeVigilancia
from src.web.idioma import COOKIE_DEL_IDIOMA
from tests.integration.conftest import (
    CONTRASENA_DEL_ADMINISTRADOR,
    crear_app_de_prueba,
    ingresar_como,
)


def _tablas(conexion) -> dict[str, list[tuple]]:
    """Contenido de las tres tablas del ledger con orden fijo, para comparar tal cual."""
    return {
        "wallets": conexion.execute("SELECT * FROM wallets ORDER BY id").fetchall(),
        "blocks": conexion.execute("SELECT * FROM blocks ORDER BY block_index").fetchall(),
        "transactions": conexion.execute(
            "SELECT * FROM transactions ORDER BY id"
        ).fetchall(),
    }


@pytest.fixture
def cadena_alterada(ledger, transaccion, conexion):
    """Una transacción confirmada con el monto cambiado por SQL directo.

    Se agrupa por el camino real para que la fila tenga bloque y firma válida
    antes de la alteración; el `UPDATE` la cambia por fuera de la fachada, así que
    solo recalculando el hash del bloque se puede detectar.
    """
    fila = ledger.transactions.add(transaccion())
    bloque = ledger.group_pending()
    conexion.execute(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s", (fila.id,)
    )
    return fila, bloque


@pytest.fixture
def cliente_con_sello(conexion, base_limpia, master_key, administrador, tmp_path):
    """Un cliente administrador sobre una app a la que se le inyecta un sello temporal.

    Devuelve el cliente, el adaptador del sello y la ruta del archivo. El sello no
    existe todavía: lo fija la prueba con la ruta de reparaciones, y así se comprueba
    que el `GET` de la verificación no escribe nada.
    """
    ruta = tmp_path / "sello-de-vigilancia.json"
    sello = SelloDeVigilancia(ruta, b"clave-de-prueba")

    @contextmanager
    def fabrica():
        chain = open_ledger(conexion, encryption_key=master_key)
        ensure_genesis(chain)
        yield chain

    aplicacion = crear_app_de_prueba(fabrica, sello=sello)
    cliente = aplicacion.test_client()
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    return cliente, sello, ruta


def test_get_verificar_muestra_el_panel_y_el_resumen(cliente_admin):
    """El panel existe debajo del dictamen y trae el resumen completo del ledger."""
    respuesta = cliente_admin.get("/verificar")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "La cadena es válida." in cuerpo
    assert "Auditoría del estado" in cuerpo
    for etiqueta in (
        "Altura",
        "Bloques",
        "Confirmadas",
        "En el pool",
        "Rechazadas",
        "Wallets",
        "Último bloque",
        "Hash de la cabeza",
        "Sello de vigilancia",
    ):
        assert etiqueta in cuerpo, etiqueta
    # Sin sello configurado el estado se muestra y no se inventa uno.
    assert "Sin fijar" in cuerpo
    # Con el génesis apenas, la cadena y el pool cuadran: se avisa.
    assert "La cadena y el pool cuadran con lo registrado." in cuerpo
    # La tabla de bloques va en una caja acotada, con desplazamiento propio, para
    # que una cadena larga no alargue la página entera.
    assert "tabla-bloques-caja" in cuerpo
    assert cuerpo.count('id="contenido"') == 1


def test_con_la_cadena_alterada_enumera_el_hallazgo_y_ofrece_reparar(
    cliente_admin, cadena_alterada
):
    """La alteración por SQL aparece como hallazgo crítico con su bloque y su tx."""
    fila, bloque = cadena_alterada

    respuesta = cliente_admin.get("/verificar")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    # El contrato de REQ-27 sigue: dictamen y primer bloque que no encaja.
    assert "La cadena no es válida." in cuerpo
    assert "El primer bloque que no encaja es el de índice" in cuerpo
    # El hallazgo enumera el bloque y la transacción responsables.
    assert "Crítico" in cuerpo
    assert "El hash del bloque no coincide" in cuerpo
    assert f"Bloque {bloque.block_index}" in cuerpo
    assert f"Transacción {str(fila.id)[:8]}…" in cuerpo
    # Se ofrece la reparación con la confirmación explícita en el HTML.
    assert 'action="/verificar/reparar"' in cuerpo
    assert 'name="accion" value="reparar-todo"' in cuerpo
    assert 'name="confirmar"' in cuerpo
    assert 'value="si"' in cuerpo
    assert "Reparar todo lo que se pueda" in cuerpo


def test_reparar_sin_confirmar_no_escribe_nada(cliente_admin, cadena_alterada, conexion):
    """Un POST sin `confirmar=si` avisa y no toca ninguna fila."""
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar", data={"accion": "encadenar"}, follow_redirects=True
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    assert "falta marcar la casilla de confirmación" in respuesta.get_data(as_text=True)


def test_reparar_con_una_accion_desconocida_no_escribe_nada(
    cliente_admin, cadena_alterada, conexion
):
    """Una acción inventada no rompe la ruta: se avisa y se vuelve a /verificar."""
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "inventada", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    assert "esa acción no existe" in respuesta.get_data(as_text=True)


def test_reparar_encadenar_restaura_la_cadena_y_avisa(
    cliente_admin, cadena_alterada, ledger, conexion
):
    """`encadenar` reescribe los hashes, deja la cadena válida y avisa qué pasó."""
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "encadenar", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert respuesta.request.path == "/verificar"
    assert _tablas(conexion) != antes
    assert ledger.verify_chain().valid
    cuerpo = respuesta.get_data(as_text=True)
    assert "La cadena quedó reencadenada" in cuerpo
    assert "La cadena ya estaba encadenada" not in cuerpo


def test_reparar_encadenar_sin_nada_que_hacer_informa_el_detalle(
    cliente_admin, conexion
):
    """Sin nada que reencadenar, el aviso informa el detalle y no afirma que reparó."""
    # El primer GET asegura el génesis; la cadena queda ya encadenada.
    cliente_admin.get("/verificar")
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "encadenar", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    cuerpo = respuesta.get_data(as_text=True)
    assert "La cadena ya estaba encadenada: no se reescribió ningún bloque." in cuerpo
    assert "La cadena quedó reencadenada" not in cuerpo


def test_reparar_aislar_sin_invalidas_informa_el_detalle(cliente_admin, conexion):
    """Sin confirmadas inválidas, el aviso dice que no se aisló ninguna."""
    cliente_admin.get("/verificar")
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "aislar", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    cuerpo = respuesta.get_data(as_text=True)
    assert "No hay transacciones confirmadas inválidas: no se aisló ninguna." in cuerpo
    assert "Se aislaron las transacciones confirmadas inválidas" not in cuerpo


def test_reparar_todo_sin_nada_que_reparar_informa_el_detalle(cliente_admin, conexion):
    """Sin nada que reparar, «reparar todo» informa el estado y no dice que reparó."""
    cliente_admin.get("/verificar")
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "reparar-todo", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    cuerpo = respuesta.get_data(as_text=True)
    assert "La cadena ya estaba encadenada: no se reescribió ningún bloque." in cuerpo
    assert "Se reparó todo lo que se pudo" not in cuerpo


def test_el_aviso_de_una_reparacion_sin_cambios_sale_en_ingles(
    cliente_admin, conexion
):
    """El detalle del dominio que muestra el aviso también se traduce."""
    cliente_admin.get("/verificar")
    cliente_admin.set_cookie(COOKIE_DEL_IDIOMA, "en")

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "encadenar", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "The chain was already chained: no block was rewritten." in cuerpo
    assert "La cadena ya estaba encadenada" not in cuerpo


def test_reagrupar_confirma_el_pool_en_un_bloque(
    cliente_admin, ledger, pendientes
):
    """`reagrupar` cierra el pool en un bloque nuevo por el camino de la fachada."""
    pendientes(1)
    indice_antes = ledger.blocks.last().block_index

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "reagrupar", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert ledger.blocks.last().block_index == indice_antes + 1
    assert "El pool quedó agrupado en un bloque nuevo." in respuesta.get_data(
        as_text=True
    )


def test_fijar_sello_escribe_el_archivo_y_el_panel_lo_muestra(cliente_con_sello, ledger):
    """`fijar-sello` escribe el ancla en el archivo y el panel siguiente la refleja."""
    cliente, sello, ruta = cliente_con_sello
    assert sello.leer().problema == "ausente"
    cabeza = ledger.blocks.last()

    respuesta = cliente.post(
        "/verificar/reparar",
        data={"accion": "fijar-sello", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert ruta.exists()
    lectura = sello.leer()
    assert lectura.problema is None
    assert lectura.sello is not None
    assert lectura.sello.altura == cabeza.block_index
    assert lectura.sello.hash == cabeza.hash
    cuerpo = respuesta.get_data(as_text=True)
    assert "Coincide" in cuerpo
    assert f"Fijado en el bloque {cabeza.block_index}" in cuerpo


def test_fijar_sello_sin_sello_configurado_avisa_y_no_escribe(
    cliente_admin, conexion
):
    """Sin sello inyectado la acción no inventa un archivo: avisa y no toca la base."""
    # El primer GET asegura el génesis, que la aplicación crea al abrir la cadena:
    # así la foto de las tablas no le atribuye a la reparación esa escritura.
    cliente_admin.get("/verificar")
    antes = _tablas(conexion)

    respuesta = cliente_admin.post(
        "/verificar/reparar",
        data={"accion": "fijar-sello", "confirmar": "si"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert _tablas(conexion) == antes
    assert "No hay un sello de vigilancia configurado" in respuesta.get_data(as_text=True)


def test_un_anonimo_no_puede_reparar(cliente, cadena_alterada, conexion):
    """REQ-38: sin sesión la ruta manda al ingreso y no escribe nada."""
    antes = _tablas(conexion)

    respuesta = cliente.post(
        "/verificar/reparar", data={"accion": "encadenar", "confirmar": "si"}
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/ingresar"
    assert _tablas(conexion) == antes


def test_verificar_sigue_sin_escribir_filas(cliente_admin, cadena_alterada, conexion):
    """REQ-22: el GET con hallazgos y acciones tampoco modifica las tablas."""
    antes = _tablas(conexion)

    cliente_admin.get("/verificar")
    cliente_admin.get("/verificar")

    assert _tablas(conexion) == antes


def test_verificar_no_escribe_el_sello(cliente_con_sello):
    """El panel de lectura ni siquiera crea el archivo del sello."""
    cliente, sello, ruta = cliente_con_sello

    cliente.get("/verificar")
    cliente.get("/verificar")

    assert not ruta.exists()
    assert sello.leer().problema == "ausente"
