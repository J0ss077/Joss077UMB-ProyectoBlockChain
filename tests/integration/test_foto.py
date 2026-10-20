"""La foto de perfil: subirla, reemplazarla, quitarla y verla en la interfaz.

Sin foto, la cuenta se pinta con la inicial de su nombre. El servidor acepta sólo
JPEG, PNG o WebP de hasta 2 MB, reconocidos por sus bytes, y la sirve a quien tiene
sesión con el tipo que reconoció y `nosniff`. La imagen es un archivo aparte en la
carpeta de fotos: la base guarda sólo su nombre, y reemplazarla o quitarla borra
el archivo que ya no se usa.
"""
import base64
import io
from uuid import uuid4

import psycopg
import pytest

from src.accounts.almacen import CarpetaDeFotos
from src.accounts.fotos import (
    MOTIVO_DE_FOTO_GRANDE,
    MOTIVO_DE_FOTO_TIPO,
    TAMANO_MAXIMO_DE_FOTO,
)
from src.web.perfil import MENSAJE_FOTO_GUARDADA, MENSAJE_FOTO_QUITADA
from tests.integration.conftest import CARPETA_DE_FOTOS_DE_PRUEBA, CONTRASENA_DE_PRUEBA

# Un PNG real de 1×1: el servidor no lo decodifica, pero así la prueba sube lo que
# subiría una persona.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _archivos():
    return sorted(CARPETA_DE_FOTOS_DE_PRUEBA.iterdir())


def _referencia(conexion):
    return conexion.execute("SELECT archivo, tipo FROM fotos_de_perfil").fetchall()


def _subir(cliente, datos, nombre="foto.png"):
    return cliente.post(
        "/perfil/foto",
        data={"foto": (io.BytesIO(datos), nombre)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_sin_foto_el_avatar_es_la_inicial(cliente_comun):
    cuerpo = cliente_comun.get("/perfil").get_data(as_text=True)

    assert '<span class="inicial inicial-grande" aria-hidden="true">A</span>' in cuerpo
    assert "/foto/ana" not in cuerpo
    assert "Quitar foto" not in cuerpo


def test_subir_una_foto_la_muestra_en_el_perfil_y_en_la_barra(cliente_comun):
    cuerpo = _subir(cliente_comun, PNG).get_data(as_text=True)

    assert MENSAJE_FOTO_GUARDADA in cuerpo
    assert 'class="inicial avatar-foto inicial-grande" src="/foto/ana?v=' in cuerpo
    assert 'class="inicial avatar-foto avatar-mini" src="/foto/ana?v=' in cuerpo
    assert "Quitar foto" in cuerpo


def test_la_foto_se_sirve_con_su_tipo_y_sin_adivinar(cliente_comun):
    _subir(cliente_comun, PNG)

    respuesta = cliente_comun.get("/foto/ana?v=1")

    assert respuesta.status_code == 200
    assert respuesta.data == PNG
    assert respuesta.mimetype == "image/png"
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert "immutable" in respuesta.headers["Cache-Control"]


def test_reemplazar_la_foto_cambia_el_tipo(cliente_comun):
    _subir(cliente_comun, PNG)
    _subir(cliente_comun, JPEG, "foto.jpg")

    respuesta = cliente_comun.get("/foto/ana")

    assert respuesta.data == JPEG
    assert respuesta.mimetype == "image/jpeg"


def test_quitar_la_foto_vuelve_a_la_inicial(cliente_comun):
    _subir(cliente_comun, PNG)

    cuerpo = cliente_comun.post("/perfil/foto/quitar", follow_redirects=True).get_data(
        as_text=True
    )

    assert MENSAJE_FOTO_QUITADA in cuerpo
    assert '<span class="inicial inicial-grande" aria-hidden="true">A</span>' in cuerpo
    assert cliente_comun.get("/foto/ana").status_code == 404


def test_un_archivo_que_no_es_imagen_se_rechaza(cliente_comun):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

    cuerpo = _subir(cliente_comun, svg, "foto.png").get_data(as_text=True)

    assert MOTIVO_DE_FOTO_TIPO in cuerpo
    assert cliente_comun.get("/foto/ana").status_code == 404


def test_una_imagen_de_mas_de_2_mb_se_rechaza(cliente_comun):
    grande = PNG + b"\x00" * TAMANO_MAXIMO_DE_FOTO

    cuerpo = _subir(cliente_comun, grande).get_data(as_text=True)

    assert MOTIVO_DE_FOTO_GRANDE in cuerpo
    assert cliente_comun.get("/foto/ana").status_code == 404


def test_un_cuerpo_mas_grande_que_el_tope_vuelve_al_perfil(cliente_comun):
    enorme = PNG + b"\x00" * (4 * 1024 * 1024)

    cuerpo = _subir(cliente_comun, enorme).get_data(as_text=True)

    assert MOTIVO_DE_FOTO_GRANDE in cuerpo


def test_ver_una_foto_exige_sesion(cliente, cliente_comun):
    _subir(cliente_comun, PNG)
    cliente_comun.post("/salir")

    respuesta = cliente.get("/foto/ana")

    assert respuesta.status_code == 302


def test_la_foto_se_ve_en_la_agenda_de_otro(aplicacion, cliente_comun, cuentas):
    _subir(cliente_comun, PNG)
    beto = cuentas.aprobar(cuentas.registrar("beto", CONTRASENA_DE_PRUEBA).id)
    cuentas.agregar_contacto(beto.id, "ana")
    otro = aplicacion.test_client()
    otro.post("/ingresar", data={"usuario": "beto", "contrasena": CONTRASENA_DE_PRUEBA})

    cuerpo = otro.get("/mis-contactos").get_data(as_text=True)

    assert 'class="inicial avatar-foto" src="/foto/ana?v=' in cuerpo
    assert otro.get("/foto/ana").data == PNG


def test_la_imagen_es_un_archivo_y_la_base_guarda_solo_su_nombre(cliente_comun, conexion):
    _subir(cliente_comun, PNG, "mi foto.png")

    ((archivo, tipo),) = _referencia(conexion)
    (guardado,) = _archivos()
    assert guardado.name == archivo
    assert guardado.read_bytes() == PNG
    assert tipo == "image/png"
    # El nombre lo pone el servidor: el del archivo subido no llega a la carpeta.
    assert "mi foto" not in archivo
    columnas = {
        fila[0]
        for fila in conexion.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'fotos_de_perfil'"
        )
    }
    assert columnas == {"usuario_id", "archivo", "tipo", "actualizado_en"}


def test_reemplazar_borra_el_archivo_anterior(cliente_comun, conexion):
    _subir(cliente_comun, PNG)
    (primero,) = _archivos()

    _subir(cliente_comun, JPEG, "foto.jpg")

    (segundo,) = _archivos()
    assert segundo != primero
    assert segundo.suffix == ".jpg"
    assert _referencia(conexion) == [(segundo.name, "image/jpeg")]


def test_quitar_borra_el_archivo(cliente_comun, conexion):
    _subir(cliente_comun, PNG)

    cliente_comun.post("/perfil/foto/quitar")

    assert _archivos() == []
    assert _referencia(conexion) == []


def test_si_la_base_falla_no_queda_el_archivo(cuentas):
    # Una cuenta que no existe viola la clave foránea al guardar la referencia.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cuentas.poner_foto(uuid4(), PNG)

    assert _archivos() == []


def test_si_falta_el_archivo_la_foto_no_se_sirve(cliente_comun):
    _subir(cliente_comun, PNG)
    for archivo in _archivos():
        archivo.unlink()

    assert cliente_comun.get("/foto/ana").status_code == 404


@pytest.mark.parametrize("nombre", ["../.env", "otra/ruta.png", "foto.svg", "ABC.png"])
def test_el_almacen_no_sale_de_su_carpeta(tmp_path, nombre):
    afuera = tmp_path / "afuera.png"
    afuera.write_bytes(PNG)
    almacen = CarpetaDeFotos(tmp_path / "fotos")

    assert almacen.ruta(nombre) is None
    almacen.borrar("../afuera.png")
    assert afuera.exists()

