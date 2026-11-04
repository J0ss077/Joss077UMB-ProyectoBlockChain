"""La serie mensual sintética con la que se entrena la proyección.

El prototipo no tiene histórico: la base de demostración se siembra con movimientos de
unos pocos días, y con eso no se puede aprender una tendencia. Para que el modelo
signifique algo se genera una serie de **veinte años de meses calendario** con las
reglas que un fondo de empleados tiene de verdad: aportes estables, retiros con picos a
mitad y a fin de año, meses flojos y algo de ruido. Es un dato sintético declarado como
tal: sirve para entrenar el método y para que la página muestre una proyección
plausible, no para afirmar nada sobre el dinero real.

Los meses son fechas de calendario y no un índice, porque el modelo recibe el mes del
año como entrada: la estacionalidad tiene que ser la misma en la serie y en la
aplicación, que mira el reloj.

La semilla es fija: dos corridas dan la misma serie y las mismas cifras en el documento.
"""
from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime

from red_neuronal.caracteristicas import ESCALA_DE_CUENTA, ESCALA_DE_MONTO

SEMILLA = 2026
MESES = 240
PISO_DE_MOVIMIENTOS = 2
TECHO_DE_MOVIMIENTOS = 12


def _meses_hacia_atras(cantidad: int) -> list[date]:
    """Los primeros días de los últimos `cantidad` meses, del más viejo al más nuevo."""
    hoy = datetime.now(UTC)
    anio, mes = hoy.year, hoy.month
    lista = []
    for _ in range(cantidad):
        lista.append(date(anio, mes, 1))
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return list(reversed(lista))


def _monto_del_mes(azar: random.Random, base: float, amplitud: float, mes: int) -> float:
    """Un monto con estacionalidad anual, picos en julio y diciembre y algo de ruido."""
    estacional = amplitud * math.sin(2 * math.pi * mes / 12)
    diciembre = 1.6 if mes == 12 else 1.0
    julio = 1.3 if mes == 7 else 1.0
    ruido = azar.gauss(0, base * 0.06)
    return max(50.0, (base + estacional) * diciembre * julio + ruido)


def serie(meses: int = MESES, semilla: int = SEMILLA) -> list[dict[str, float]]:
    """Cada mes con lo que entró, lo que salió, cuántos movimientos, el saldo y su mes.

    El saldo arranca en 1.000 y se arrastra; si un mes lo dejaría en negativo se
    recorta el retiro, porque una cuenta real no gira más de lo que tiene y la serie
    tiene que parecerse a lo que el ledger acepta.
    """
    azar = random.Random(semilla)
    saldo = 1000.0
    filas = []
    for fecha in _meses_hacia_atras(meses):
        recibido = _monto_del_mes(azar, base=1800.0, amplitud=350.0, mes=fecha.month)
        enviado = _monto_del_mes(azar, base=1450.0, amplitud=300.0, mes=fecha.month)
        enviado = min(enviado, saldo + recibido - 100.0)
        movimientos = float(azar.randint(PISO_DE_MOVIMIENTOS, TECHO_DE_MOVIMIENTOS))
        saldo = saldo + recibido - enviado
        filas.append(
            {
                "recibido": round(recibido, 2),
                "enviado": round(max(0.0, enviado), 2),
                "movimientos": movimientos,
                "saldo": round(saldo, 2),
                "mes": float(fecha.month),
            }
        )
    return filas


def ejemplos(
    filas: list[dict[str, float]] | None = None,
) -> tuple[list[list[float]], list[list[float]], list[float]]:
    """Las entradas, las salidas y la escala de cada ejemplo.

    Las entradas son las mismas ocho proporciones que arma la aplicación con el
    historial real, y las salidas son dos proporciones sobre lo recibido: cuánto se
    espera recibir y cuánto enviar el mes siguiente. Trabajar en proporciones es lo que
    permite que un mismo modelo sirva para una cuenta de mil pesos y para un fondo de
    ochenta mil.

    La tercera lista devuelve la escala de cada ejemplo (lo recibido ese mes) para que
    el error se pueda informar en pesos, que es la única unidad que se entiende.
    """
    filas = serie() if filas is None else filas
    entradas: list[list[float]] = []
    salidas: list[list[float]] = []
    escalas: list[float] = []
    for indice in range(1, len(filas) - 1):
        actual = filas[indice]
        anterior = filas[indice - 1]
        base = actual["recibido"] if actual["recibido"] > 0 else max(actual["saldo"], 1.0)
        mes = actual["mes"]
        crudo = (
            min(actual["enviado"] / base, 3.0),
            min(actual["movimientos"] / ESCALA_DE_CUENTA, 3.0),
            max(
                min((anterior["recibido"] - anterior["enviado"]) / base, 3.0),
                -3.0,
            ),
            min(actual["saldo"] / base, 5.0),
            min(anterior["movimientos"] / ESCALA_DE_CUENTA, 3.0),
            base / ESCALA_DE_MONTO,
            math.sin(2 * math.pi * mes / 12),
            math.cos(2 * math.pi * mes / 12),
        )
        entradas.append(list(crudo))
        siguiente = filas[indice + 1]
        salidas.append([siguiente["recibido"] / base, siguiente["enviado"] / base])
        escalas.append(base)
    return entradas, salidas, escalas
