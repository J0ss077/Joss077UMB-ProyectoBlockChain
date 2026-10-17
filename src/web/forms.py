"""Conversión de los datos de un formulario de trabajo (REQ-24, REQ-34).

Un dato mal escrito no puede tumbar la página: el identificador y el monto se
convierten con un valor neutro, y el dominio decide después con su motivo. Las dos
funciones viven acá porque las usan la ruta de transacciones del administrador y
la del envío del usuario común; con una copia en cada módulo, un cambio en una
sola dejaría a las dos rutas aceptando cosas distintas.
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
