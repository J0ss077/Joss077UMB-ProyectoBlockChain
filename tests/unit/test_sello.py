"""Sello de vigilancia: fijar y leer el ancla externa contra el recorte de la cola.

Se ejercita el adaptador de archivo del spec §2 sin base de datos (REQ-17): la
firma HMAC-SHA256 sobre el JSON canónico, la escritura atómica y la lectura que
nunca levanta. Cada caso trabaja sobre `tmp_path`, así que la suite no toca el
`datos/sello-de-vigilancia.json` del proyecto.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta

from src.domain.auditoria import LecturaDelSello, Sello
from src.persistence.sello import SelloDeVigilancia

# Clave y hash de las pruebas: el hash tiene la forma de un SHA-256 hexadecimal,
# que es la que guarda el sello en producción.
CLAVE = b"clave-de-pruebas"
HASH = "a" * 64
FIRMA_HEXADECIMAL = re.compile(r"[0-9a-f]{64}")


def _datos_canonicos(datos: dict) -> bytes:
    """Los mismos bytes que firma el adaptador: JSON con claves ordenadas y compacto."""
    return json.dumps(
        datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def test_fijar_y_leer_devuelve_el_mismo_sello(tmp_path):
    """El sello recién fijado se lee igual, con la altura y el hash que se pasaron."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)

    fijado = sello.fijar(altura=7, hash=HASH)

    assert fijado.altura == 7
    assert fijado.hash == HASH
    assert fijado.fijado_en.utcoffset() == timedelta(0)
    assert sello.leer() == LecturaDelSello(sello=fijado, problema=None)


def test_el_adaptador_expone_la_ruta_del_archivo(tmp_path):
    """La ruta pública es la del archivo que se lee y se escribe."""
    ruta = tmp_path / "sello.json"
    assert SelloDeVigilancia(ruta, CLAVE).ruta == ruta


def test_un_byte_cambiado_en_el_archivo_se_declara_ilegible(tmp_path):
    """Alterar un carácter de los datos firma distinta: el archivo no es confiable."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)
    sello.fijar(altura=7, hash=HASH)
    contenido = ruta.read_text(encoding="utf-8")
    alterado = contenido.replace('"hash":"a', '"hash":"b', 1)

    assert alterado != contenido
    ruta.write_text(alterado, encoding="utf-8")

    assert sello.leer() == LecturaDelSello(sello=None, problema="ilegible")


def test_un_json_roto_se_declara_ilegible(tmp_path):
    """Un archivo que no es JSON se informa como ilegible, sin excepción."""
    ruta = tmp_path / "sello.json"
    ruta.write_text('{"datos": ', encoding="utf-8")

    lectura = SelloDeVigilancia(ruta, CLAVE).leer()

    assert lectura == LecturaDelSello(sello=None, problema="ilegible")


def test_un_json_incompleto_se_declara_ilegible(tmp_path):
    """Un JSON válido al que le falta la firma tampoco se puede leer."""
    ruta = tmp_path / "sello.json"
    ruta.write_text(json.dumps({"datos": {"altura": 7, "hash": HASH}}), encoding="utf-8")

    lectura = SelloDeVigilancia(ruta, CLAVE).leer()

    assert lectura == LecturaDelSello(sello=None, problema="ilegible")


def test_una_clave_distinta_se_declara_ilegible(tmp_path):
    """Con otra clave la firma no cuadra: el sello se informa ilegible."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)
    sello.fijar(altura=7, hash=HASH)

    lectura = SelloDeVigilancia(ruta, b"otra-clave").leer()

    assert lectura == LecturaDelSello(sello=None, problema="ilegible")


def test_sin_archivo_el_problema_es_ausente(tmp_path):
    """Sin archivo no hay sello fijado: se informa ausente, no ilegible."""
    lectura = SelloDeVigilancia(tmp_path / "sello.json", CLAVE).leer()

    assert lectura == LecturaDelSello(sello=None, problema="ausente")


def test_el_archivo_es_json_valido_con_datos_y_firma(tmp_path):
    """El archivo guarda `datos` y `firma`, y la firma cubre los datos canónicos."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)
    fijado = sello.fijar(altura=7, hash=HASH)

    contenido = json.loads(ruta.read_text(encoding="utf-8"))

    assert set(contenido) == {"datos", "firma"}
    assert set(contenido["datos"]) == {"altura", "hash", "fijado_en"}
    assert contenido["datos"]["altura"] == 7
    assert contenido["datos"]["hash"] == HASH
    assert datetime.fromisoformat(contenido["datos"]["fijado_en"]) == fijado.fijado_en
    assert FIRMA_HEXADECIMAL.fullmatch(contenido["firma"])
    esperada = hmac.new(
        CLAVE, _datos_canonicos(contenido["datos"]), hashlib.sha256
    ).hexdigest()
    assert contenido["firma"] == esperada


def test_fijar_crea_la_carpeta_si_no_existe(tmp_path):
    """Fijar crea la carpeta de `datos/` cuando todavía no está."""
    ruta = tmp_path / "datos" / "fondo" / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)

    fijado = sello.fijar(altura=0, hash="0" * 64)

    assert ruta.exists()
    assert sello.leer().sello == fijado


def test_fijar_no_deja_el_archivo_temporal(tmp_path):
    """La escritura atómica deja solo el archivo final, sin temporales sueltos."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)

    sello.fijar(altura=7, hash=HASH)

    assert [archivo.name for archivo in tmp_path.iterdir()] == ["sello.json"]


def test_leer_despues_de_fijar_dos_veces_devuelve_el_ultimo(tmp_path):
    """Volver a fijar reemplaza el sello anterior con otro válido."""
    ruta = tmp_path / "sello.json"
    sello = SelloDeVigilancia(ruta, CLAVE)
    sello.fijar(altura=3, hash="b" * 64)

    segundo = sello.fijar(altura=4, hash="c" * 64)

    assert isinstance(segundo, Sello)
    assert sello.leer() == LecturaDelSello(sello=segundo, problema=None)
    assert sello.leer().sello.hash == "c" * 64
