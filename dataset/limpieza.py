"""Las reglas que convierten la capa cruda en la limpia, y cuántas filas tocó cada una.

Cada regla responde a un defecto de `crudo.py`. Primero se descarta lo que no sirve y
después se normaliza lo que queda, así cada conteo habla sólo de filas que llegan al
limpio:

1. **Duplicados:** se quitan las filas idénticas (mismo identificador y mismo contenido).
2. **Otra causa:** se descarta toda fila que no se pueda interpretar sin adivinar: un
   monto que no está en uno de los tres formatos conocidos (`1234.56`, `$1234.56` o
   `1.234,56`) o que no es finito, una fecha ilegible, un identificador vacío, un tipo
   de movimiento desconocido, o un identificador que se repite con **otro** contenido
   (no se sabe cuál de las dos versiones vale, así que no pasa ninguna). Un defecto nuevo
   no llega al limpio en silencio.
3. **Monto inválido:** se descartan los montos cero o negativos.
4. **Cuenta inexistente:** se descartan las filas cuyo origen o destino no está en la
   tabla de cuentas (ni es el fondo).
5. **Monto:** se normaliza a número con punto decimal (`1.234,56` y `$1234.56` → `1234.56`).
6. **Fecha:** se interpreta con su zona y se lleva a UTC.
7. **Canal:** si falta, se imputa `desconocido` en vez de descartar la fila: el canal no
   cambia cuánto dinero se movió.
"""

from __future__ import annotations

import math
import re

import pandas as pd

from dataset.perfiles import FONDO, TIPOS

CANAL_DESCONOCIDO = "desconocido"

REGLAS = (
    "duplicados_eliminados",
    "descartadas_por_otra_causa",
    "monto_invalido_descartado",
    "cuenta_inexistente_descartada",
    "monto_normalizado",
    "fecha_convertida_a_utc",
    "canal_imputado",
)

_MONTO_CANONICO = r"^-?\d+\.\d{2}$"
_MONTO_CON_SIGNO_PESO = r"^\$-?\d+\.\d{2}$"
_MONTO_CON_COMA = r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$"


def _monto(texto: object) -> float | None:
    """El monto como número, sólo si está en uno de los tres formatos conocidos.

    Cualquier otra forma (`1,234.56`, `1.234`, `inf`) devuelve `None`: adivinar si un
    punto es de miles o decimal es justo el error que corrompe un dataset sin avisar.
    """
    if texto is None or (isinstance(texto, float) and math.isnan(texto)):
        return None
    limpio = str(texto).strip()
    if re.match(_MONTO_CANONICO, limpio):
        return float(limpio)
    if re.match(_MONTO_CON_SIGNO_PESO, limpio):
        return float(limpio[1:])
    if re.match(_MONTO_CON_COMA, limpio):
        return float(limpio.replace(".", "").replace(",", "."))
    return None


def _vacio(serie: pd.Series) -> pd.Series:
    return serie.isna() | (serie.astype(str).str.strip() == "")


def limpiar(crudo: pd.DataFrame, cuentas: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """El limpio, con tipos y en UTC, y el conteo de filas que tocó cada regla."""
    conteos = dict.fromkeys(REGLAS, 0)
    tabla = crudo.copy()

    antes = len(tabla)
    tabla = tabla.drop_duplicates()
    conteos["duplicados_eliminados"] = antes - len(tabla)

    monto = tabla["monto"].map(_monto)
    texto_fecha = tabla["fecha"].astype(str)
    fecha = pd.to_datetime(texto_fecha, utc=True, errors="coerce", format="ISO8601")
    repetido = tabla["transaccion_id"].notna() & tabla["transaccion_id"].duplicated(keep=False)
    ilegible = (
        monto.isna()
        | fecha.isna()
        | _vacio(tabla["transaccion_id"])
        | ~tabla["tipo"].isin(TIPOS)
        | repetido
    )
    conteos["descartadas_por_otra_causa"] = int(ilegible.sum())
    tabla, monto, fecha, texto_fecha = (
        tabla[~ilegible],
        monto[~ilegible],
        fecha[~ilegible],
        texto_fecha[~ilegible],
    )

    invalido = monto <= 0
    conteos["monto_invalido_descartado"] = int(invalido.sum())
    tabla, monto, fecha, texto_fecha = (
        tabla[~invalido],
        monto[~invalido],
        fecha[~invalido],
        texto_fecha[~invalido],
    )

    conocidas = set(cuentas["cuenta_id"]) | {FONDO}
    huerfana = ~(tabla["cuenta_origen"].isin(conocidas) & tabla["cuenta_destino"].isin(conocidas))
    conteos["cuenta_inexistente_descartada"] = int(huerfana.sum())
    tabla, monto, fecha, texto_fecha = (
        tabla[~huerfana].copy(),
        monto[~huerfana],
        fecha[~huerfana],
        texto_fecha[~huerfana],
    )

    conteos["monto_normalizado"] = int(
        (~tabla["monto"].astype(str).str.match(_MONTO_CANONICO)).sum()
    )
    tabla["monto"] = monto.astype(float).round(2)
    conteos["fecha_convertida_a_utc"] = int((~texto_fecha.str.endswith("+00:00")).sum())
    tabla["fecha"] = fecha
    faltan = _vacio(tabla["canal"])
    conteos["canal_imputado"] = int(faltan.sum())
    tabla.loc[faltan, "canal"] = CANAL_DESCONOCIDO

    tabla = tabla.astype(
        {
            "transaccion_id": str,
            "cuenta_origen": str,
            "cuenta_destino": str,
            "tipo": str,
            "canal": str,
        }
    )
    tabla = tabla.sort_values(["fecha", "transaccion_id"]).reset_index(drop=True)
    return tabla, conteos
