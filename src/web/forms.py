"""Conversión de los datos de un formulario de trabajo (REQ-24, REQ-34).

Un dato mal escrito no puede tumbar la página: el identificador y el monto se
convierten con un valor neutro, y el dominio decide después con su motivo. Las
funciones viven acá porque las usan varias rutas —transacciones del administrador,
envío del usuario común y los formularios que vuelven a la página de origen—; con
una copia en cada módulo, un cambio en una sola dejaría a las demás aceptando cosas
distintas.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID


def a_uuid(value: str | None) -> UUID | None:
    """Convierte el identificador del formulario; `None` si no es un UUID.

    Se devuelve `None` y no se levanta el error: un identificador mal escrito es un
    dato que el caso de uso tiene que rechazar con su motivo, no una caída.
    """
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


def a_monto(value: str | None) -> Decimal:
    """Convierte el monto del formulario; un valor ilegible se convierte en cero.

    Cero es un monto que el dominio rechaza con su motivo (REQ-04), así que un
    formulario mal escrito sigue el camino del rechazo y no el de la excepción.
    """
    try:
        return Decimal(value) if value else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def ruta_interna(valor: str | None, por_defecto: str) -> str:
    """El destino de una redirección si es una ruta propia, o `por_defecto`.

    Se descartan las direcciones absolutas —`https://otro.example`—, las que
    empiezan por dos barras —`//otro.example`, que el navegador lee como otro
    dominio— y las que empiezan por barra y barra invertida: el navegador normaliza
    la barra invertida a barra, así que `/\\otro.example` también saldría del sitio.
    Es la misma regla para los formularios que vuelven a la página de origen.
    """
    if valor and valor.startswith("/") and not valor.startswith(("//", "/\\")):
        return valor
    return por_defecto
