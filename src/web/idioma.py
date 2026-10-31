"""Idioma de la interfaz: español o inglés, elegido por cada persona.

El texto de siempre es el español y es también la clave: las plantillas escriben
`t("Mi historial")` y, si la persona eligió inglés, sale la traducción de
`traducciones.EN`. Así el español no cambia —ni para las pruebas ni para quien no
elige nada— y una frase sin traducir se ve en español en vez de romper la página.

Los mensajes que llegan armados desde el servicio o el dominio («Tu cuenta fue
rechazada: documentación incompleta.») se traducen por patrón: las claves de
`MENSAJES_ARMADOS` describen la frase con marcadores `{nombre}`, y lo que ocupa
cada marcador se traduce a su vez sólo si es una clave exacta (por ejemplo, el
estado de una cuenta); un texto libre, como el motivo, queda tal cual.

La elección vive en una cookie y no en la cuenta: el idioma tiene que valer
también en el ingreso y el registro, antes de que haya sesión.
"""
from __future__ import annotations

import re

from flask import has_request_context, request

from src.web.traducciones import EN, MENSAJES_ARMADOS, TEXTOS_DE_JS

IDIOMAS = {"es": "Español", "en": "English"}
IDIOMA_POR_DEFECTO = "es"
COOKIE_DEL_IDIOMA = "idioma"
# Un año: es una preferencia, no un dato de la sesión, y no tiene por qué vencer al
# cerrar el navegador.
DURACION_DE_LA_COOKIE = 365 * 24 * 60 * 60

_MARCADOR = re.compile(r"\\\{(\w+)\\\}")


def _patron(clave: str) -> re.Pattern[str]:
    """La clave con marcadores convertida en una expresión que captura cada uno."""
    return re.compile(_MARCADOR.sub(r"(?P<\1>.+?)", re.escape(clave)), re.DOTALL)


_PATRONES = [(clave, _patron(clave)) for clave in MENSAJES_ARMADOS]


def idioma_actual() -> str:
    """El idioma de la petición en curso; fuera de una petición, el español."""
    if not has_request_context():
        return IDIOMA_POR_DEFECTO
    valor = request.cookies.get(COOKIE_DEL_IDIOMA, "")
    return valor if valor in IDIOMAS else IDIOMA_POR_DEFECTO


def _al_ingles(texto: str) -> str:
    """La traducción exacta o, si no hay, la de la primera clave con marcadores que calce."""
    exacta = EN.get(texto)
    if exacta is not None:
        return exacta
    for clave, patron in _PATRONES:
        calce = patron.fullmatch(texto)
        if calce:
            return EN[clave].format(
                **{nombre: EN.get(valor, valor) for nombre, valor in calce.groupdict().items()}
            )
    return texto


def t(texto: object, **valores: object) -> str:
    """El texto en el idioma de la petición, con los marcadores ya reemplazados.

    `texto` es la frase en español. Con `valores`, la frase es una plantilla y
    sus marcadores se llenan después de traducirla; sin ellos, una frase ya armada
    se intenta traducir por patrón.
    """
    frase = str(texto)
    if idioma_actual() == "en":
        frase = EN.get(frase, frase) if valores else _al_ingles(frase)
    return frase.format(**valores) if valores else frase


def textos_de_js() -> dict[str, str]:
    """Las traducciones que necesitan los guiones, sólo si la página va en inglés."""
    if idioma_actual() != "en":
        return {}
    return {clave: EN[clave] for clave in TEXTOS_DE_JS}
