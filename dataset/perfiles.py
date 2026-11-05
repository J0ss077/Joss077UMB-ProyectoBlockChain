"""Las cuentas del fondo simulado y sus transacciones «verdaderas».

Cada cuenta tiene un **perfil** que decide cómo se mueve, y dentro del perfil cada una
sortea sus propios parámetros (ingreso, días y horas en que opera, canal preferido), así
que no hay dos cuentas iguales. Los perfiles salen de lo que hace la gente en un fondo
de empleados:

| Perfil | Cómo se mueve |
| ------ | ------------- |
| `ahorrador` | Un retiro al mes y dos aportes que devuelven casi todo: saldo que crece despacio |
| `frecuente` | Retiros semanales chicos y muchas transferencias chicas a otras cuentas |
| `esporadico` | Meses quietos y, de vez en cuando, montos grandes que devuelve en parte |
| `con_primas` | Ingreso mensual y primas en junio y diciembre que gasta los meses siguientes |
| `endeudado` | Un préstamo grande al año y cuotas mensuales para pagarlo |
| `comerciante` | Vende a otras cuentas: recibe muchas transferencias y aporta al fondo |
| `que_se_retira` | Opera como un ahorrador hasta su baja y ese mes liquida lo que le queda |

El `FONDO` es la contraparte de aportes, retiros, primas, préstamos y cuotas, igual que
la wallet del fondo en la aplicación. No tiene perfil ni tope de saldo: es la puerta por
la que el dinero entra y sale del dataset.

Las transacciones se planean por cuenta y mes y después se **aplican en orden
cronológico** llevando el saldo de cada cuenta: si una salida supera lo que la cuenta
tiene en ese momento, se recorta, y si queda en menos de un peso se descarta. Es la
misma regla que aplica el ledger (una wallet no gira más de lo que tiene), así que
ninguna cuenta del dataset queda en negativo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import numpy as np
import pandas as pd

from dataset.configuracion import Configuracion

FONDO = "FONDO"

# Los tipos de movimiento que puede tener una transacción. La limpieza descarta cualquier
# otro: un tipo desconocido es un defecto que no se adivina.
TIPOS = ("aporte", "retiro", "transferencia", "prima", "prestamo", "cuota", "liquidacion")

# Proporción de cuentas de cada perfil. El frecuente es el que más movimientos aporta,
# así que no es el más común: con más frecuentes el dataset sería casi todo montos chicos.
PERFILES: dict[str, float] = {
    "ahorrador": 0.24,
    "frecuente": 0.14,
    "esporadico": 0.14,
    "con_primas": 0.16,
    "endeudado": 0.12,
    "comerciante": 0.10,
    "que_se_retira": 0.10,
}

# Ingreso mensual típico de cada perfil (la mediana de una lognormal), en la escala de
# las wallets de demostración de la aplicación: de cientos a pocos miles por mes.
INGRESO_MEDIANO: dict[str, float] = {
    "ahorrador": 1800.0,
    "frecuente": 900.0,
    "esporadico": 2500.0,
    "con_primas": 1600.0,
    "endeudado": 1400.0,
    "comerciante": 1200.0,
    "que_se_retira": 1700.0,
}

CIUDADES = (
    "Pasto",
    "Bogotá",
    "Medellín",
    "Cali",
    "Barranquilla",
    "Bucaramanga",
    "Ipiales",
    "Popayán",
    "Manizales",
    "Pereira",
)
CANALES = ("app", "web", "oficina", "programada")

# El monto más alto que puede tener un movimiento: los préstamos de las cuentas de
# ingreso alto pasarían de esta cifra, y en el fondo hay un tope por operación.
TOPE_POR_MOVIMIENTO = 50_000.0

# Cuánto sube el ingreso por año, entre estos dos extremos: una cuenta de ocho años no
# puede mover lo mismo el primer mes que el último.
AUMENTO_ANUAL = (0.02, 0.08)

LUNES_A_VIERNES = (0, 1, 2, 3, 4)
FIN_DE_SEMANA = (5, 6)
TODOS = (0, 1, 2, 3, 4, 5, 6)


@dataclass(frozen=True, slots=True)
class Plan:
    """Un movimiento planeado antes de mirar el saldo: puede recortarse o descartarse."""

    fecha: datetime
    origen: str
    destino: str
    monto: float
    tipo: str
    canal: str


def _meses(conf: Configuracion) -> list[date]:
    """El primer día de cada mes simulado, del más viejo al más nuevo."""
    anio, mes = conf.fin.year, conf.fin.month
    lista = []
    for _ in range(conf.meses):
        lista.append(date(anio, mes, 1))
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return list(reversed(lista))


def _fin_de_mes(inicio: date) -> date:
    return (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def generar_cuentas(conf: Configuracion) -> pd.DataFrame:
    """Una fila por cuenta: perfil, alta, baja, ingreso, ciudad y edad.

    Seis de cada diez cuentas existen desde el primer mes; el resto se afilia a lo largo
    de los primeros años. Las que se retiran lo hacen al menos un año después del alta.
    """
    azar = np.random.default_rng([conf.semilla, 0])
    meses = _meses(conf)
    primero, ultimo = meses[0], conf.fin
    nombres = list(PERFILES)
    pesos = np.array(list(PERFILES.values()))
    perfiles = azar.choice(nombres, size=conf.cuentas, p=pesos / pesos.sum())
    filas = []
    for indice, perfil in enumerate(perfiles, start=1):
        if azar.random() < 0.6:
            alta = primero
        else:
            alta = primero + timedelta(
                days=int(azar.integers(0, int(0.7 * (ultimo - primero).days)))
            )
        baja = None
        dias_restantes = (ultimo - alta).days
        if perfil == "que_se_retira" and dias_restantes > 400:
            baja = alta + timedelta(days=int(azar.integers(365, dias_restantes)))
        elif perfil != "que_se_retira" and dias_restantes > 400 and azar.random() < 0.04:
            baja = alta + timedelta(days=int(azar.integers(365, dias_restantes)))
        ingreso = INGRESO_MEDIANO[perfil] * float(azar.lognormal(0.0, 0.35))
        filas.append(
            {
                "cuenta_id": f"C{indice:05d}",
                "perfil": str(perfil),
                "fecha_alta": alta,
                "fecha_baja": baja,
                "ingreso_mensual": round(ingreso, 2),
                "ciudad": str(azar.choice(CIUDADES)),
                "edad": int(azar.integers(20, 63)),
            }
        )
    return pd.DataFrame(filas)


class _Agenda:
    """Lo que una cuenta prefiere: días de la semana, franja horaria y canal."""

    def __init__(self, perfil: str, azar: np.random.Generator) -> None:
        if perfil in ("frecuente", "comerciante"):
            self.dias = FIN_DE_SEMANA if azar.random() < 0.5 else TODOS
            self.horas = (17, 22)
        elif perfil == "esporadico":
            self.dias = (3, 4)
            self.horas = (13, 18)
        else:
            self.dias = LUNES_A_VIERNES
            self.horas = (7, 12) if azar.random() < 0.6 else (12, 18)
        preferido = azar.choice(CANALES[:3])
        self.canales = [preferido, *(c for c in CANALES if c != preferido)]
        self.azar = azar

    def momento(self, inicio: date, dia: int) -> datetime:
        """Un momento de ese mes cerca del `dia` pedido, en un día que la cuenta opera."""
        fin = _fin_de_mes(inicio)
        candidato = inicio.replace(day=max(1, min(dia, fin.day)))
        for _ in range(7):
            if candidato.weekday() in self.dias:
                break
            siguiente = candidato + timedelta(days=1)
            candidato = siguiente if siguiente <= fin else candidato - timedelta(days=6)
        hora = int(self.azar.integers(self.horas[0], self.horas[1]))
        minuto = int(self.azar.integers(0, 60))
        segundo = int(self.azar.integers(0, 60))
        return datetime.combine(candidato, time(hora, minuto, segundo), tzinfo=UTC)

    def canal(self, tipo: str) -> str:
        if tipo in ("cuota", "aporte") and self.azar.random() < 0.35:
            return "programada"
        return str(
            self.canales[0] if self.azar.random() < 0.75 else self.azar.choice(self.canales[1:])
        )


def _plan_de_la_cuenta(
    cuenta: dict, meses: list[date], conf: Configuracion, otras: list[str], comerciantes: list[str]
) -> list[Plan]:
    """Todos los movimientos que la cuenta intentaría hacer, mes por mes."""
    indice = int(cuenta["cuenta_id"][1:])
    azar = np.random.default_rng([conf.semilla, indice])
    agenda = _Agenda(cuenta["perfil"], azar)
    perfil = cuenta["perfil"]
    alta, baja = cuenta["fecha_alta"], cuenta["fecha_baja"]
    aumento = float(azar.uniform(*AUMENTO_ANUAL))
    # Un desfase propio en la estacionalidad: no todas las cuentas tienen el mes flojo
    # en el mismo momento del año.
    fase = float(azar.uniform(0, 2 * math.pi))
    planes: list[Plan] = []
    id_ = cuenta["cuenta_id"]
    deuda = 0.0

    def plan(inicio: date, dia: int, origen: str, destino: str, monto: float, tipo: str) -> None:
        if monto >= 1:
            monto = min(monto, TOPE_POR_MOVIMIENTO)
            planes.append(
                Plan(
                    agenda.momento(inicio, dia),
                    origen,
                    destino,
                    round(monto, 2),
                    tipo,
                    agenda.canal(tipo),
                )
            )

    def par() -> str:
        if comerciantes and azar.random() < 0.5:
            return str(azar.choice(comerciantes))
        return str(azar.choice(otras))

    for numero, inicio in enumerate(meses):
        if _fin_de_mes(inicio) < alta or (baja is not None and inicio > baja):
            continue
        anios = numero / 12
        estacional = 1 + 0.18 * math.sin(2 * math.pi * inicio.month / 12 + fase)
        base = float(cuenta["ingreso_mensual"]) * (1 + aumento) ** anios * estacional
        ruido = lambda: float(azar.lognormal(0.0, 0.18))  # noqa: E731

        if perfil in ("ahorrador", "que_se_retira"):
            retiro = base * ruido()
            plan(inicio, int(azar.integers(1, 6)), FONDO, id_, retiro, "retiro")
            proporcion = float(azar.choice((0.4, 0.7, 0.9, 1.0, 1.2)))
            plan(
                inicio, int(azar.integers(10, 16)), id_, FONDO, retiro * proporcion * 0.55, "aporte"
            )
            plan(
                inicio, int(azar.integers(20, 28)), id_, FONDO, retiro * proporcion * 0.45, "aporte"
            )
            if azar.random() < 0.3:
                plan(
                    inicio,
                    int(azar.integers(5, 25)),
                    id_,
                    par(),
                    base * azar.uniform(0.05, 0.3),
                    "transferencia",
                )
            if perfil == "que_se_retira" and baja is not None and _fin_de_mes(inicio) >= baja:
                # La liquidación: el último día devuelve todo lo que tiene al fondo. El
                # monto se recorta al saldo al aplicarse, así que pedir de más es seguro.
                plan(inicio, baja.day, id_, FONDO, 1e9, "liquidacion")

        elif perfil == "frecuente":
            for dia in (2, 9, 16, 23):
                if azar.random() < 0.85:
                    plan(inicio, dia, FONDO, id_, base * 0.27 * ruido(), "retiro")
                for _ in range(int(azar.integers(1, 4))):
                    plan(
                        inicio,
                        dia + int(azar.integers(0, 7)),
                        id_,
                        par(),
                        base * azar.uniform(0.02, 0.16),
                        "transferencia",
                    )
            if azar.random() < 0.6:
                plan(inicio, 12, id_, FONDO, base * azar.uniform(0.05, 0.2), "aporte")
            if azar.random() < 0.25:
                plan(inicio, 20, id_, FONDO, base * azar.uniform(0.6, 1.4), "aporte")

        elif perfil == "esporadico":
            if azar.random() < 0.3:
                monto = base * azar.uniform(2.5, 6.0)
                dia = int(azar.integers(1, 15))
                plan(inicio, dia, FONDO, id_, monto, "retiro")
                plan(inicio, dia + 7, id_, FONDO, monto * azar.uniform(0.4, 1.2), "aporte")
                if azar.random() < 0.6:
                    plan(
                        inicio, dia + 12, id_, par(), base * azar.uniform(0.3, 1.0), "transferencia"
                    )
            elif azar.random() < 0.15:
                plan(
                    inicio,
                    int(azar.integers(5, 25)),
                    id_,
                    FONDO,
                    base * azar.uniform(0.2, 0.6),
                    "aporte",
                )

        elif perfil == "con_primas":
            plan(inicio, int(azar.integers(1, 6)), FONDO, id_, base * ruido(), "retiro")
            if inicio.month in (6, 12):
                plan(
                    inicio,
                    int(azar.integers(15, 28)),
                    FONDO,
                    id_,
                    base * azar.uniform(1.3, 2.2),
                    "prima",
                )
            gasto = 1.6 if inicio.month in (1, 7) else 0.85
            plan(
                inicio,
                int(azar.integers(8, 15)),
                id_,
                FONDO,
                base * gasto * 0.5 * ruido(),
                "aporte",
            )
            for _ in range(int(azar.integers(1, 3))):
                plan(
                    inicio,
                    int(azar.integers(10, 28)),
                    id_,
                    par(),
                    base * gasto * azar.uniform(0.1, 0.35),
                    "transferencia",
                )

        elif perfil == "endeudado":
            plan(inicio, int(azar.integers(1, 6)), FONDO, id_, base * ruido(), "retiro")
            if deuda <= 0 and azar.random() < 0.12:
                deuda = base * azar.uniform(4.0, 8.0)
                plan(inicio, int(azar.integers(5, 12)), FONDO, id_, deuda, "prestamo")
            if deuda > 0:
                cuota = min(deuda, base * azar.uniform(0.45, 0.7))
                deuda -= cuota
                plan(inicio, int(azar.integers(25, 29)), id_, FONDO, cuota, "cuota")
            plan(
                inicio,
                int(azar.integers(12, 20)),
                id_,
                FONDO,
                base * azar.uniform(0.2, 0.5),
                "aporte",
            )
            if azar.random() < 0.4:
                plan(
                    inicio,
                    int(azar.integers(8, 25)),
                    id_,
                    par(),
                    base * azar.uniform(0.05, 0.25),
                    "transferencia",
                )

        elif perfil == "comerciante":
            if azar.random() < 0.5:
                plan(inicio, int(azar.integers(1, 6)), FONDO, id_, base * 0.5 * ruido(), "retiro")
            for semana in (6, 13, 20, 27):
                plan(inicio, semana, id_, FONDO, base * azar.uniform(0.15, 0.45), "aporte")
            if azar.random() < 0.5:
                plan(
                    inicio,
                    int(azar.integers(5, 25)),
                    id_,
                    par(),
                    base * azar.uniform(0.1, 0.4),
                    "transferencia",
                )

    fin = datetime.combine(conf.fin, time(23, 59, 59), tzinfo=UTC)
    limite_baja = datetime.combine(baja, time(23, 59, 59), tzinfo=UTC) if baja is not None else fin
    inicio_alta = datetime.combine(alta, time(0, 0), tzinfo=UTC)
    return [p for p in planes if inicio_alta <= p.fecha <= min(fin, limite_baja)]


def generar_transacciones(conf: Configuracion, cuentas: pd.DataFrame) -> pd.DataFrame:
    """Las transacciones verdaderas: planeadas por cuenta y aplicadas en orden con saldo.

    Una transferencia hacia otra cuenta sólo se aplica si la destinataria está activa ese
    día; si no, se descarta (en la vida real, el sistema no deja girar a una cuenta
    dada de baja).
    """
    meses = _meses(conf)
    registros = cuentas.to_dict("records")
    ids = [c["cuenta_id"] for c in registros]
    comerciantes = [c["cuenta_id"] for c in registros if c["perfil"] == "comerciante"]
    vida = {c["cuenta_id"]: (c["fecha_alta"], c["fecha_baja"]) for c in registros}

    planes: list[Plan] = []
    for cuenta in registros:
        otras = [i for i in ids if i != cuenta["cuenta_id"]]
        propios_comerciantes = [i for i in comerciantes if i != cuenta["cuenta_id"]]
        planes.extend(_plan_de_la_cuenta(cuenta, meses, conf, otras, propios_comerciantes))
    # Orden total y estable: fecha y, para empates, los datos del movimiento.
    planes.sort(key=lambda p: (p.fecha, p.origen, p.destino, p.monto, p.tipo))

    saldo: dict[str, float] = {i: 0.0 for i in ids}
    filas = []
    for p in planes:
        if p.destino != FONDO:
            alta, baja = vida[p.destino]
            if p.fecha.date() < alta or (baja is not None and p.fecha.date() > baja):
                continue
        monto = p.monto
        if p.origen != FONDO:
            monto = min(monto, math.floor(saldo[p.origen] * 100) / 100)
            if monto < 1:
                continue
            saldo[p.origen] = round(saldo[p.origen] - monto, 2)
        if p.destino != FONDO:
            saldo[p.destino] = round(saldo[p.destino] + monto, 2)
        filas.append((p.fecha, p.origen, p.destino, round(monto, 2), p.tipo, p.canal))

    tabla = pd.DataFrame(
        filas, columns=["fecha", "cuenta_origen", "cuenta_destino", "monto", "tipo", "canal"]
    )
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], utc=True)
    tabla.insert(0, "transaccion_id", [f"T{n:07d}" for n in range(1, len(tabla) + 1)])
    return tabla
