"""La capa cruda: las transacciones como saldrían de un sistema real, con defectos.

Un dataset que llega perfecto no deja ver la limpieza, y la limpieza es la mitad del
trabajo con datos. Esta capa toma las transacciones verdaderas y les aplica los errores
que de verdad aparecen al exportar de un sistema transaccional, cada uno en una
proporción baja y fija (`Configuracion`):

| Defecto | Qué se ve en el crudo |
| ------- | --------------------- |
| Duplicados | La misma fila exportada dos veces (reintento de una exportación) |
| Canal nulo | El campo `canal` vacío |
| Formato de monto | `1.234,56` (coma decimal) o `$1234.56` en vez de `1234.56` |
| Zona horaria | La fecha en hora de Colombia (`-05:00`) en vez de UTC |
| Filas inválidas | Filas **nuevas** con monto cero o negativo, o hacia una cuenta que no existe |

Las filas inválidas se agregan en vez de corromper filas verdaderas: así la limpieza
recupera exactamente las transacciones que se generaron, y las pruebas lo comprueban.

Todas las columnas quedan como texto, que es como llega un CSV exportado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dataset.configuracion import Configuracion

# Una cuenta que no existe en la tabla de cuentas, para las filas huérfanas.
CUENTA_INEXISTENTE = "C99999"


def _monto_con_coma(monto: float) -> str:
    entero, decimales = f"{monto:.2f}".split(".")
    con_puntos = f"{int(entero):,}".replace(",", ".")
    return f"{con_puntos},{decimales}"


def ensuciar(transacciones: pd.DataFrame, conf: Configuracion) -> pd.DataFrame:
    """Las transacciones como texto, con los defectos de la tabla del módulo."""
    azar = np.random.default_rng([conf.semilla, 1])
    n = len(transacciones)
    crudo = pd.DataFrame(
        {
            "transaccion_id": transacciones["transaccion_id"].astype(str),
            "fecha": transacciones["fecha"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "cuenta_origen": transacciones["cuenta_origen"].astype(str),
            "cuenta_destino": transacciones["cuenta_destino"].astype(str),
            "monto": transacciones["monto"].map(lambda m: f"{m:.2f}"),
            "tipo": transacciones["tipo"].astype(str),
            "canal": transacciones["canal"].astype(str),
        }
    )

    # Cada defecto cae en filas distintas, para que el reporte cuente cada uno una vez.
    orden = azar.permutation(n)
    cortes = np.cumsum(
        [round(n * conf.tasa_nulos), round(n * conf.tasa_formato), round(n * conf.tasa_zona)]
    )
    nulos, formato, zona = np.split(orden[: cortes[-1]], cortes[:-1])

    crudo.loc[nulos, "canal"] = None
    crudo.loc[formato, "monto"] = [
        _monto_con_coma(float(transacciones.at[i, "monto"]))
        if azar.random() < 0.5
        else f"${transacciones.at[i, 'monto']:.2f}"
        for i in formato
    ]
    crudo.loc[zona, "fecha"] = (
        transacciones.loc[zona, "fecha"]
        .dt.tz_convert("America/Bogota")
        .dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    ).str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True)

    # Filas inválidas nuevas: la mitad con monto cero o negativo y la otra mitad hacia
    # una cuenta que no existe. Copian el resto de una fila real para parecer legítimas.
    invalidas = round(n * conf.tasa_invalidos)
    base = crudo.iloc[azar.choice(n, size=invalidas, replace=False)].copy()
    base["transaccion_id"] = [f"T{n + i + 1:07d}" for i in range(invalidas)]
    mitad = invalidas // 2
    base.iloc[:mitad, base.columns.get_loc("monto")] = [
        "0.00" if azar.random() < 0.5 else f"-{azar.uniform(10, 900):.2f}" for _ in range(mitad)
    ]
    base.iloc[mitad:, base.columns.get_loc("cuenta_destino")] = CUENTA_INEXISTENTE

    duplicados = crudo.iloc[azar.choice(n, size=round(n * conf.tasa_duplicados), replace=False)]
    juntas = pd.concat([crudo, base, duplicados], ignore_index=True)
    # Un sistema no exporta en orden: las filas quedan mezcladas.
    juntas = juntas.iloc[azar.permutation(len(juntas))].reset_index(drop=True)
    return juntas.astype(object)
