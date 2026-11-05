"""Las ocho características que entran a la red, iguales al entrenar y al predecir.

La red no lee transacciones: lee ocho números que resumen cómo se movió una cuenta en
los últimos treinta días. Este módulo es el único lugar donde esos números se arman, y
por eso lo usan las dos puntas:

- el entrenamiento, que los saca de las transacciones del dataset (`dataset/agregado.py`);
- la aplicación, que los saca del historial real de la wallet.

Las cantidades van **en relación con lo que la cuenta recibió**, no en pesos. Un fondo
que mueve 80.000 al mes y una persona que mueve 1.000 se comportan igual si gastan la
misma proporción de lo que reciben, y un modelo entrenado con montos absolutos no puede
predecir para la cuenta chica: nunca vio cifras tan bajas y extrapola cualquier cosa.
Con ratios, la misma red sirve para las dos.

`escala` es el divisor que la aplicación necesita para volver a pesos: lo que la cuenta
recibió en los últimos treinta días. La predicción son dos proporciones y se multiplican
por esa escala al mostrarlas.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

# Las ocho posiciones, en orden. El nombre viaja en el documento y en la figura.
CAMPOS = (
    "gasto_relativo",
    "movimientos_30d",
    "neto_relativo",
    "colchon",
    "movimientos_previos",
    "recibido_escala",
    "mes_seno",
    "mes_coseno",
)

# Escalas de las dos únicas cifras que no son una proporción: el monto recibido (para
# que entre en el mismo orden que el resto) y los conteos de movimientos.
ESCALA_DE_MONTO = 10_000.0
ESCALA_DE_CUENTA = 10.0

DIAS = 30
DOS_PI = 2 * math.pi


@dataclass(frozen=True, slots=True)
class Movimiento:
    """Una transacción reducida a lo que la proyección necesita.

    `signo` es +1 cuando el dinero entra a la cuenta y -1 cuando sale. Sólo las
    confirmadas cuentan: una pendiente todavía no movió nada y una rechazada nunca lo
    hizo.
    """

    fecha: datetime
    signo: int
    monto: Decimal
    confirmada: bool


@dataclass(frozen=True, slots=True)
class Resumen:
    """Lo que la cuenta movió en los últimos sesenta días, en pesos.

    `recibido` es la escala: el modelo predice proporciones sobre ella y la aplicación
    vuelve a pesos multiplicando.
    """

    recibido: float
    enviado: float
    movimientos: float
    neto_previo: float
    saldo: float
    movimientos_previos: float


def _ventana(
    movimientos: Sequence[Movimiento], desde: datetime, hasta: datetime
) -> list[Movimiento]:
    """Los movimientos confirmados que caen en la ventana `[desde, hasta)`."""
    return [
        movimiento
        for movimiento in movimientos
        if movimiento.confirmada and desde <= movimiento.fecha < hasta
    ]


def resumen(
    movimientos: Sequence[Movimiento], saldo: Decimal, ahora: datetime
) -> Resumen:
    """Lo de los últimos treinta días y lo de los treinta anteriores, en pesos.

    Se separan recibido de enviado a propósito: una cuenta que recibe mil y envía mil
    no se mueve igual que una que no recibe nada, aunque el neto sea el mismo.
    """
    hace_30 = ahora - timedelta(days=DIAS)
    hace_60 = ahora - timedelta(days=2 * DIAS)
    ultimos = _ventana(movimientos, hace_30, ahora)
    anteriores = _ventana(movimientos, hace_60, hace_30)

    recibido = sum((m.monto for m in ultimos if m.signo > 0), Decimal(0))
    enviado = sum((m.monto for m in ultimos if m.signo < 0), Decimal(0))
    neto_previo = sum((Decimal(m.signo) * m.monto for m in anteriores), Decimal(0))
    return Resumen(
        recibido=float(recibido),
        enviado=float(enviado),
        movimientos=float(len(ultimos)),
        neto_previo=float(neto_previo),
        saldo=float(saldo),
        movimientos_previos=float(len(anteriores)),
    )


def _proporcion(valor: float, base: float) -> float:
    """`valor` sobre `base`, con un piso de 1 para no dividir por cero."""
    return valor / (base + 1.0)


def vector(
    movimientos: Sequence[Movimiento], saldo: Decimal, ahora: datetime
) -> tuple[list[float], float]:
    """El vector de ocho números que entra a la red y la escala con la que se vuelve a pesos."""
    datos = resumen(movimientos, saldo, ahora)
    base = datos.recibido if datos.recibido > 0 else max(datos.saldo, 1.0)
    caracteristicas = [
        min(_proporcion(datos.enviado, base), 3.0),
        min(datos.movimientos / ESCALA_DE_CUENTA, 3.0),
        max(min(_proporcion(datos.neto_previo, base), 3.0), -3.0),
        min(_proporcion(datos.saldo, base), 5.0),
        min(datos.movimientos_previos / ESCALA_DE_CUENTA, 3.0),
        base / ESCALA_DE_MONTO,
        math.sin(DOS_PI * ahora.month / 12),
        math.cos(DOS_PI * ahora.month / 12),
    ]
    return caracteristicas, base
