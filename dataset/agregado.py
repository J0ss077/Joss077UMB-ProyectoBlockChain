"""El resumen mensual por cuenta y los ejemplos que entran a la red.

**Mensual.** Una fila por cuenta y por cada mes en que la cuenta estuvo activa, aunque
ese mes no se haya movido: un panel completo, sin huecos, que es lo que se espera de una
tabla analítica. Lleva lo recibido, lo enviado, cuántos movimientos hubo y el saldo con
que cerró el mes.

**Ejemplos.** Una fila por cuenta y fecha de corte (el primer instante de cada mes). Las
ocho entradas se calculan con `red_neuronal.caracteristicas.vector`, **la misma función
que usa la aplicación** con el historial de la wallet: lo que la red ve al entrenar es
exactamente lo que ve en la página. Los dos objetivos son lo que la cuenta recibió y
envió en los treinta días siguientes al corte, divididos por la misma escala que la
aplicación usa para volver a pesos, y acotados en `TOPE_DEL_OBJETIVO` veces esa escala.
El monto real, sin tope y en pesos, también se guarda (`real_recibido`, `real_enviado`):
el error del modelo se mide contra eso y no contra el objetivo recortado.

Sólo hay ejemplo cuando la cuenta lleva al menos sesenta días de alta (las dos ventanas
de `vector` tienen que existir) y sigue activa los treinta días del objetivo: una
cuenta dada de baja no tiene «mes siguiente».

**Partición temporal.** Los cortes se ordenan y el primer 70 % es entrenamiento, el
15 % siguiente validación y el último 15 % prueba. Partir al azar mezclaría el futuro
con el pasado y el error de prueba saldría mejor de lo que el modelo es en realidad.

**Normalización.** La media y la desviación de cada entrada se calculan **sólo** con
entrenamiento; la red las usa en su capa `Normalization`.
"""

from __future__ import annotations

import bisect
import math
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from dataset.configuracion import Configuracion
from dataset.perfiles import FONDO
from red_neuronal.caracteristicas import CAMPOS, DIAS, Movimiento, vector

ENTRENAMIENTO, VALIDACION, PRUEBA = "entrenamiento", "validacion", "prueba"

# El objetivo más alto, en veces la escala. Cuando una cuenta casi no recibió nada en
# los últimos treinta días, la escala cae en su saldo (a veces de un peso) y lo que mueva
# el mes siguiente da proporciones de miles: unos pocos ejemplos así dominan el error de
# la red. Se acotan en 5, el mismo tope que la entrada `colchon`, y el reporte de
# calidad dice cuántos se recortaron.
TOPE_DEL_OBJETIVO = 5.0
PROPORCIONES = (0.70, 0.15, 0.15)


def _primeros_de_mes(desde: date, hasta: date) -> list[date]:
    """El primer día de cada mes entre `desde` y `hasta`, inclusive."""
    actual = desde.replace(day=1)
    lista = []
    while actual <= hasta:
        lista.append(actual)
        actual = (actual + timedelta(days=32)).replace(day=1)
    return lista


def _libro(limpio: pd.DataFrame) -> pd.DataFrame:
    """Cada transacción dos veces, una por lado, con el signo desde esa cuenta."""
    entra = limpio[["fecha", "cuenta_destino", "monto"]].rename(
        columns={"cuenta_destino": "cuenta_id"}
    )
    sale = limpio[["fecha", "cuenta_origen", "monto"]].rename(
        columns={"cuenta_origen": "cuenta_id"}
    )
    libro = pd.concat([entra.assign(signo=1), sale.assign(signo=-1)], ignore_index=True)
    libro = libro[libro["cuenta_id"] != FONDO]
    return libro.sort_values(["cuenta_id", "fecha"], kind="stable").reset_index(drop=True)


def _ultimo_dia(cuenta: dict, conf: Configuracion) -> date:
    baja = cuenta["fecha_baja"]
    return conf.fin if baja is None or pd.isna(baja) else min(baja, conf.fin)


def mensual(limpio: pd.DataFrame, cuentas: pd.DataFrame, conf: Configuracion) -> pd.DataFrame:
    """Una fila por cuenta y mes activo: recibido, enviado, movimientos y saldo de cierre."""
    libro = _libro(limpio)
    libro["anio"] = libro["fecha"].dt.year
    libro["mes"] = libro["fecha"].dt.month
    libro["recibido"] = np.where(libro["signo"] > 0, libro["monto"], 0.0)
    libro["enviado"] = np.where(libro["signo"] < 0, libro["monto"], 0.0)
    sumas = libro.groupby(["cuenta_id", "anio", "mes"]).agg(
        recibido=("recibido", "sum"), enviado=("enviado", "sum"), movimientos=("monto", "size")
    )

    panel = [
        (cuenta["cuenta_id"], inicio.year, inicio.month)
        for cuenta in cuentas.to_dict("records")
        for inicio in _primeros_de_mes(cuenta["fecha_alta"], _ultimo_dia(cuenta, conf))
    ]
    tabla = pd.DataFrame(panel, columns=["cuenta_id", "anio", "mes"])
    tabla = tabla.merge(sumas.reset_index(), on=["cuenta_id", "anio", "mes"], how="left")
    tabla[["recibido", "enviado"]] = tabla[["recibido", "enviado"]].fillna(0.0).round(2)
    tabla["movimientos"] = tabla["movimientos"].fillna(0).astype(int)
    tabla["saldo_cierre"] = (
        (tabla["recibido"] - tabla["enviado"]).groupby(tabla["cuenta_id"]).cumsum().round(2)
    )
    tabla["mes_seno"] = np.sin(2 * math.pi * tabla["mes"] / 12).round(6)
    tabla["mes_coseno"] = np.cos(2 * math.pi * tabla["mes"] / 12).round(6)
    return tabla


def ejemplos(limpio: pd.DataFrame, cuentas: pd.DataFrame, conf: Configuracion) -> pd.DataFrame:
    """Las ocho entradas de la red, los dos objetivos y la escala, por cuenta y corte."""
    libro = _libro(limpio)
    por_cuenta = {cuenta: grupo for cuenta, grupo in libro.groupby("cuenta_id", sort=False)}
    ventana = timedelta(days=DIAS)
    filas = []
    for cuenta in cuentas.to_dict("records"):
        alta = datetime.combine(cuenta["fecha_alta"], time(0), tzinfo=UTC)
        hasta = datetime.combine(_ultimo_dia(cuenta, conf) + timedelta(days=1), time(0), tzinfo=UTC)
        grupo = por_cuenta.get(cuenta["cuenta_id"])
        if grupo is None:
            fechas, signos, montos = [], [], []
        else:
            fechas = [f.to_pydatetime() for f in grupo["fecha"]]
            signos = grupo["signo"].tolist()
            montos = grupo["monto"].tolist()
        acumulado = np.concatenate([[0.0], np.cumsum(np.array(signos) * np.array(montos))])
        movimientos = [
            Movimiento(fecha=f, signo=s, monto=Decimal(f"{m:.2f}"), confirmada=True)
            for f, s, m in zip(fechas, signos, montos, strict=True)
        ]
        for inicio in _primeros_de_mes(cuenta["fecha_alta"], hasta.date()):
            corte = datetime.combine(inicio, time(0), tzinfo=UTC)
            if corte - alta < 2 * ventana or corte + ventana > hasta:
                continue
            desde = bisect.bisect_left(fechas, corte - 2 * ventana)
            antes = bisect.bisect_left(fechas, corte)
            despues = bisect.bisect_left(fechas, corte + ventana)
            saldo = Decimal(f"{acumulado[antes]:.2f}")
            entradas, escala = vector(movimientos[desde:antes], saldo, corte)
            siguiente = range(antes, despues)
            recibido = sum(montos[i] for i in siguiente if signos[i] > 0)
            enviado = sum(montos[i] for i in siguiente if signos[i] < 0)
            filas.append(
                [
                    cuenta["cuenta_id"],
                    corte,
                    *entradas,
                    recibido / escala,
                    enviado / escala,
                    escala,
                    recibido,
                    enviado,
                ]
            )

    columnas = [
        "cuenta_id",
        "fecha_corte",
        *CAMPOS,
        "objetivo_recibido",
        "objetivo_enviado",
        "escala",
        "real_recibido",
        "real_enviado",
    ]
    tabla = pd.DataFrame(filas, columns=columnas)
    tabla["fecha_corte"] = pd.to_datetime(tabla["fecha_corte"], utc=True)
    objetivos = ["objetivo_recibido", "objetivo_enviado"]
    tabla[objetivos] = tabla[objetivos].clip(upper=TOPE_DEL_OBJETIVO)
    numericas = [*CAMPOS, *objetivos, "escala"]
    tabla[numericas] = tabla[numericas].round(6)
    tabla[["real_recibido", "real_enviado"]] = tabla[["real_recibido", "real_enviado"]].round(2)
    tabla["particion"] = _particion(tabla["fecha_corte"])
    return tabla.sort_values(["fecha_corte", "cuenta_id"]).reset_index(drop=True)


def _particion(fechas: pd.Series) -> pd.Series:
    """Entrenamiento, validación o prueba según el lugar del corte en el tiempo."""
    cortes = sorted(fechas.unique())
    n = len(cortes)
    fin_entrenamiento = max(1, round(n * PROPORCIONES[0]))
    fin_validacion = max(fin_entrenamiento + 1, round(n * (PROPORCIONES[0] + PROPORCIONES[1])))
    nombre = {}
    for i, corte in enumerate(cortes):
        nombre[corte] = (
            ENTRENAMIENTO if i < fin_entrenamiento else VALIDACION if i < fin_validacion else PRUEBA
        )
    return fechas.map(nombre)


def normalizacion(tabla: pd.DataFrame) -> dict[str, dict[str, float]]:
    """La media y la desviación de cada entrada, calculadas sólo con entrenamiento."""
    entrenamiento = tabla[tabla["particion"] == ENTRENAMIENTO]
    return {
        campo: {
            "media": float(entrenamiento[campo].mean()),
            "desviacion": float(entrenamiento[campo].std(ddof=0)),
        }
        for campo in CAMPOS
    }
