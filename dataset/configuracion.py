"""Los parámetros del dataset: tamaño, fechas, semilla y tasa de cada defecto.

Todo lo que cambia el resultado vive acá y en ningún otro lado, para que el README del
dataset pueda citar estos números y para que las pruebas corran el mismo generador en
pequeño. La fecha de fin es fija y no `now()`: si dependiera del reloj, dos corridas en
días distintos darían archivos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True, slots=True)
class Configuracion:
    """Cuántas cuentas y meses se simulan y cuánto se ensucia la capa cruda.

    Las tasas son la proporción de filas (sobre las transacciones verdaderas) que
    reciben cada defecto. Son bajas a propósito: un sistema real no está roto, tiene
    errores aislados, y el reporte de calidad tiene que mostrarlos como tales.
    """

    cuentas: int
    meses: int
    fin: date
    semilla: int
    tasa_duplicados: float = 0.008
    tasa_nulos: float = 0.012
    tasa_formato: float = 0.015
    tasa_zona: float = 0.010
    tasa_invalidos: float = 0.004


# El dataset que se publica: 2.500 cuentas y ocho años que terminan en octubre de 2026,
# el último mes completo antes de la entrega. Da del orden de 800.000 transacciones.
COMPLETA = Configuracion(cuentas=2500, meses=96, fin=date(2026, 10, 31), semilla=2026)

# El mismo generador en pequeño, para las pruebas: corre en segundos.
PEQUENA = replace(COMPLETA, cuentas=24, meses=14)
