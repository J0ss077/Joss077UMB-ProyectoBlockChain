"""REQ-44: el conector del ayudante no manda una clave ambigua a ciegas.

La clave que empieza por `sk-` la comparten OpenAI, DeepSeek y Mistral: sin
`ASISTENTE_PROVEEDOR` no se puede saber a cuál de los tres pertenece, así que no
se crea el conector y el ayudante sigue con su guía local. Los comienzos que
identifican a un único servicio sí se reconocen solos.

Aquí también se prueba el tope de preguntas por cuenta, que vive en
`src/web/asistente.py` como una función sin Flask. Todo corre sin base (REQ-17).
"""
import logging

import pytest

from src.web.asistente import (
    PREGUNTAS_POR_MINUTO,
    VENTANA_DEL_LIMITE,
    LimitadorDePreguntas,
    permite_pregunta,
)
from src.web.ia import (
    VARIABLE_DE_LA_CLAVE,
    VARIABLE_DEL_PROVEEDOR,
    crear_conector,
    detectar_proveedor,
)


@pytest.mark.parametrize(
    ("clave", "proveedor"),
    [
        ("sk-ant-clave-de-prueba", "anthropic"),
        ("sk-or-clave-de-prueba", "openrouter"),
        ("gsk_clave-de-prueba", "groq"),
        ("AIzaClaveDePrueba", "gemini"),
        ("xai-clave-de-prueba", "xai"),
    ],
)
def test_req_44_cada_prefijo_inequivoco_reconoce_su_servicio(clave, proveedor):
    """Criterio: el comienzo que identifica a un solo servicio no pide más datos."""
    assert detectar_proveedor(clave) == proveedor


def test_req_44_una_clave_sk_pelada_es_ambigua(caplog):
    """Criterio: sin proveedor, una clave `sk-` no viaja a ningún lado y se avisa.

    El aviso tiene que nombrar la variable que falta para que la persona sepa qué
    definir; la clave nunca aparece en el registro.
    """
    with caplog.at_level(logging.WARNING, logger="src.web.ia"):
        conector = crear_conector(
            {VARIABLE_DE_LA_CLAVE: "sk-clave-que-no-dice-su-servicio"}
        )

    assert detectar_proveedor("sk-clave-que-no-dice-su-servicio") is None
    assert conector is None
    assert VARIABLE_DEL_PROVEEDOR in caplog.text
    assert "sk-clave-que-no-dice-su-servicio" not in caplog.text


def test_req_44_sk_con_proveedor_usa_la_url_de_ese_servicio():
    """Criterio: con `ASISTENTE_PROVEEDOR=deepseek`, la clave va a DeepSeek."""
    conector = crear_conector(
        {
            VARIABLE_DE_LA_CLAVE: "sk-clave-de-deepseek",
            VARIABLE_DEL_PROVEEDOR: "deepseek",
        }
    )

    assert conector is not None
    assert conector.proveedor.nombre == "deepseek"
    assert conector.url == "https://api.deepseek.com/v1"


def test_req_44_sin_configuracion_no_hay_conector():
    """Criterio: sin variables del ayudante, la guía local es el único camino."""
    assert crear_conector(None) is None
    assert crear_conector({}) is None


def test_req_44_ollama_funciona_sin_clave():
    """Criterio: un servidor local no exige credencial."""
    conector = crear_conector({VARIABLE_DEL_PROVEEDOR: "ollama"})

    assert conector is not None
    assert conector.clave is None
    assert conector.url == "http://localhost:11434/v1"


def test_req_44_el_repr_del_conector_no_revela_la_clave():
    """Criterio: imprimir el conector en el registro no expone la credencial."""
    clave = "sk-ant-clave-que-no-debe-salir"
    conector = crear_conector({VARIABLE_DE_LA_CLAVE: clave})

    assert conector is not None
    assert clave not in repr(conector)


def test_req_44_el_tope_deja_pasar_solo_cinco_preguntas_por_minuto():
    """Criterio: con cinco marcas dentro de la ventana, la sexta no pasa."""
    ahora = 1000.0
    marcas = [ahora - segundo for segundo in range(PREGUNTAS_POR_MINUTO)]

    assert permite_pregunta(marcas, ahora) is False
    assert permite_pregunta(marcas[1:], ahora) is True
    assert permite_pregunta(marcas, ahora + VENTANA_DEL_LIMITE) is True


def test_req_44_el_limitador_cuenta_por_cuenta():
    """Criterio: el tope de una cuenta no bloquea a otra."""
    limitador = LimitadorDePreguntas()

    for _ in range(PREGUNTAS_POR_MINUTO):
        assert limitador.permite("ana", ahora=100.0) is True
    assert limitador.permite("ana", ahora=100.0) is False
    assert limitador.permite("beto", ahora=100.0) is True
