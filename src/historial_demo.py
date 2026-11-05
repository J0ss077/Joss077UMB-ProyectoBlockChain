"""Historial de demostración: doce meses con perfiles de cuenta bien distintos.

La semilla deja el caso del eje con unos pocos movimientos del mismo día, que alcanza
para mostrar que la cadena funciona pero no para mirar una tendencia: la página de
estadísticas filtra por período y la proyección mira los últimos treinta y sesenta días,
y con un solo día no hay nada que ver.

Este módulo agrega trece meses de historia (los doce anteriores y lo que va del actual)
a las wallets que ya sembró el arranque, con el mismo camino que usa la aplicación: cada
transacción se firma con la llave del emisor, se valida el saldo disponible y se agrupa
en un bloque encadenado. No escribe filas a mano: si una transacción no fuera válida,
no entraría.

Para que las gráficas de cada persona cuenten una historia propia —saldos que suben y
bajan, contrapartes principales distintas y una mezcla de estados creíble—, cada usuario
común tiene un perfil:

- **asociado1, la comerciante.** Le compra seguido a asociado2 (dos o tres pagos al
  mes) y asociado2 le devuelve parte en ventas; su contraparte principal es asociado2,
  no el fondo. Retira del fondo un monto que sube y baja con la temporada y algunos
  meses aporta más de lo que retiró, así el saldo cae. Opera entre semana por la mañana.
- **asociado2, la de movimientos chicos y frecuentes.** Retiros semanales chicos del
  fondo, primas grandes en junio y diciembre que gasta en los meses siguientes, y muchos
  envíos a asociado1. Opera los fines de semana por la noche. Su contraparte principal
  también es asociado1, pero con el fondo en segundo lugar y por poco.
- **asociado3, el esporádico de montos grandes.** Sólo se mueve en algunos meses, pero
  cuando lo hace retira entre 4.000 y 12.000 del fondo, devuelve una parte y le presta
  a asociado1, que le paga en cuotas los meses siguientes. Su contraparte principal sí
  es el fondo. Opera jueves y viernes por la tarde.
- **constituyente, el emisor.** Emite capital al fondo cada dos meses (entre 8.000 y
  20.000) y el fondo le devuelve excedentes tres veces al año. Opera el primer día hábil
  del mes, temprano. Es el único con saldo negativo, porque es la puerta por la que el
  capital entra al ledger.

El fondo no tiene perfil propio: su historia es la contraparte de las otras cuatro.

Los estados también se reparten: cada perfil intenta, en meses al azar, operaciones que
superan su saldo (quedan rechazadas, mezcladas con el resto de la historia y no todas
en el mismo mes), y lo de los últimos días queda en el pool, en espera. La semilla es
fija: dos corridas dan la misma historia.

Antes de cada salida normal se mira el saldo disponible y, si no alcanza, el monto se
recorta; así ninguna operación se rechaza por accidente y las únicas rechazadas son
las que se buscan a propósito.

**Es idempotente**: si la wallet del fondo ya tiene un movimiento de hace más de 45
días, no hace nada. Correrlo dos veces no duplica la historia.

Uso:

    <venv> -m src.historial_demo
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg

from src.accounts.postgres import PostgresAccountsRepository
from src.bootstrap import FONDO, entrega_de_capital
from src.domain.blockchain import Blockchain
from src.emision import CONSTITUYENTE_ID
from src.persistence.factory import database_url, master_key, open_ledger

# Cuántos meses completos hacia atrás se siembran; el mes en curso se suma hasta hoy.
MESES = 12
# Los movimientos de los últimos días quedan en el pool, para que la página muestre el
# estado «En espera» además de «Completada».
DIAS_EN_ESPERA = 9
# Capital que la puerta de emisión entrega al fondo antes del primer mes. Los retiros de
# los perfiles suman bastante más de lo que vuelve en aportes, así que el fondo
# necesita colchón para todo el año.
CAPITAL_DEL_FONDO = Decimal("30000.00")
# Semilla de la variación: fija para que la historia se pueda reproducir.
SEMILLA = 2026
# El monto mínimo que vale la pena mover: debajo de esto, la salida se descarta.
MINIMO = Decimal("10")

# Movimientos recientes que quedan en el pool, además de los que la historia deja en
# los últimos días: hace cuántas horas, quién, a quién y cuánto. Si el monto supera el
# saldo se recorta, igual que en la historia, para que no se rechace por accidente.
EN_ESPERA: tuple[tuple[int, str, str, Decimal], ...] = (
    (20, "asociado1", "fondo", Decimal("850.00")),
    (44, "asociado1", "asociado2", Decimal("420.00")),
    (5, "asociado2", "asociado1", Decimal("75.00")),
    (60, "asociado2", "fondo", Decimal("180.00")),
    (96, "asociado2", "asociado3", Decimal("240.00")),
    (30, "asociado3", "fondo", Decimal("2400.00")),
    (52, "asociado3", "asociado1", Decimal("900.00")),
    (70, "asociado3", "asociado2", Decimal("350.00")),
)

# Si el fondo ya tiene un movimiento más viejo que esto, la historia ya está sembrada.
UMBRAL_DE_HISTORIA = timedelta(days=45)

# Las cuentas que aportan y reciben. Son sólo las tres de asociados: el fondo es la
# contraparte y el constituyente ya tiene su papel en la emisión.
ASOCIADOS_DE_LA_HISTORIA = ("asociado1", "asociado2", "asociado3")

# Lunes = 0 … domingo = 6.
LUNES, MARTES, MIERCOLES, JUEVES, VIERNES, SABADO, DOMINGO = range(7)


@dataclass(frozen=True, slots=True)
class Evento:
    """Un movimiento planeado: cuándo, quién manda, quién recibe y cuánto.

    Si `rechazo` es verdadero, el monto se ignora: al sembrar se pide más de lo que
    la cuenta tiene, para que la validación de saldo lo rechace.
    """

    momento: datetime
    origen: str
    destino: str
    monto: Decimal
    rechazo: bool = False


class Reloj:
    """Reloj controlable: es el que sella los bloques con la fecha del día que toca."""

    def __init__(self, ahora: datetime) -> None:
        self.ahora = ahora

    def __call__(self) -> datetime:
        return self.ahora


def _primer_dia(meses_atras: int, hoy: datetime) -> datetime:
    """El primer día del mes que está `meses_atras` meses antes del actual, en UTC."""
    anio, mes = hoy.year, hoy.month - meses_atras
    while mes <= 0:
        mes += 12
        anio -= 1
    return datetime(anio, mes, 1, tzinfo=UTC)


def _dias_del_mes(inicio: datetime) -> int:
    siguiente = (inicio + timedelta(days=32)).replace(day=1)
    return (siguiente - inicio).days


def _en_dia(
    inicio: datetime, dia: int, semana: tuple[int, ...], hora: int, minuto: int
) -> datetime:
    """El primer día desde `dia` que cae en uno de los días de `semana`, a esa hora.

    Si el corrimiento se sale del mes, busca hacia atrás: el movimiento siempre queda
    dentro del mes que se está sembrando.
    """
    largo = _dias_del_mes(inicio)
    dia = max(1, min(dia, largo))
    candidato = inicio.replace(day=dia)
    for _ in range(7):
        if candidato.weekday() in semana and candidato.month == inicio.month:
            break
        candidato += timedelta(days=1)
    else:
        candidato = inicio.replace(day=dia)
    if candidato.month != inicio.month:
        candidato = inicio.replace(day=dia)
        while candidato.weekday() not in semana and candidato.day > 1:
            candidato -= timedelta(days=1)
    return datetime.combine(candidato.date(), time(hora, minuto), tzinfo=UTC)


def _redondo(valor: float, paso: int = 10) -> Decimal:
    return Decimal(max(paso, int(round(valor / paso)) * paso))


def _intento_rechazado(
    inicio: datetime,
    azar: random.Random,
    origen: str,
    destinos: tuple[str, ...],
    semana: tuple[int, ...],
    horas: tuple[int, int],
) -> Evento:
    """Una operación que supera el saldo, en un día y hacia un destino al azar."""
    return Evento(
        _en_dia(
            inicio, azar.randint(2, 27), semana, azar.randint(*horas), azar.randrange(0, 60, 5)
        ),
        origen,
        azar.choice(destinos),
        Decimal(0),
        rechazo=True,
    )


# ── Los perfiles ───────────────────────────────────────────────────────────────
# Cada uno recibe el índice del mes (0 = el más viejo, MESES = el actual), el primer día
# de ese mes y el generador de azar, y devuelve sus eventos del mes.

PerfilDeMes = Callable[[int, datetime, random.Random], Iterator[Evento]]


def _comerciante(i: int, inicio: datetime, azar: random.Random) -> Iterator[Evento]:
    """asociado1: retiro de temporada, aportes desparejos y muchos pagos a asociado2."""
    semana = (LUNES, MARTES, MIERCOLES)
    # El retiro sube y baja con una onda de unos siete meses, no crece siempre.
    retiro = _redondo(1500 + 900 * math.sin(i * 0.9) + azar.uniform(-250, 250), 50)
    yield Evento(
        _en_dia(inicio, azar.randint(2, 6), semana, 8, azar.randrange(0, 60, 5)),
        "fondo",
        "asociado1",
        retiro,
    )
    # Un aporte que algunos meses devuelve poco y otros más de lo retirado.
    aporte = _redondo(float(retiro) * azar.choice((0.3, 0.5, 0.8, 1.1, 1.3)))
    yield Evento(
        _en_dia(inicio, azar.randint(18, 26), semana, 10, azar.randrange(0, 60, 5)),
        "asociado1",
        "fondo",
        aporte,
    )
    # Las compras a asociado2: dos o tres pagos por mes, de tamaño muy variable.
    for _ in range(azar.randint(2, 3)):
        yield Evento(
            _en_dia(
                inicio, azar.randint(4, 27), semana, azar.randint(8, 11), azar.randrange(0, 60, 5)
            ),
            "asociado1",
            "asociado2",
            _redondo(azar.uniform(350, 1600)),
        )
    # Las cuotas de lo que le prestó asociado3, algunos meses sí y otros no.
    if azar.random() < 0.55:
        yield Evento(
            _en_dia(inicio, azar.randint(10, 20), semana, 9, 30),
            "asociado1",
            "asociado3",
            _redondo(azar.uniform(300, 1100)),
        )
    if azar.random() < 0.35:
        yield _intento_rechazado(
            inicio, azar, "asociado1", ("fondo", "asociado2", "asociado3"), semana, (8, 11)
        )


def _frecuente(i: int, inicio: datetime, azar: random.Random) -> Iterator[Evento]:
    """asociado2: retiros semanales chicos, primas en junio y diciembre, muchos envíos."""
    semana = (SABADO, DOMINGO)
    for dia in (2, 9, 16, 23):
        if azar.random() < 0.8:
            yield Evento(
                _en_dia(inicio, dia, semana, 19, azar.randrange(0, 60, 5)),
                "fondo",
                "asociado2",
                _redondo(azar.uniform(100, 380)),
            )
        for _ in range(azar.randint(0, 3)):
            destino = "asociado1" if azar.random() < 0.8 else "asociado3"
            yield Evento(
                _en_dia(
                    inicio,
                    dia + azar.randint(0, 6),
                    (azar.choice(semana),),
                    azar.randint(20, 22),
                    azar.randrange(0, 60, 5),
                ),
                "asociado2",
                destino,
                _redondo(azar.uniform(80, 750)),
            )
    if inicio.month in (6, 12):
        # La prima se queda casi entera: el saldo salta y se gasta en los meses siguientes.
        prima = _redondo(azar.uniform(2500, 4200), 50)
        yield Evento(_en_dia(inicio, 27, semana, 18, 0), "fondo", "asociado2", prima)
    if inicio.month in (1, 7):
        # El mes después de la prima, un gasto grande que la baja de golpe.
        yield Evento(
            _en_dia(inicio, 10, semana, 21, 0),
            "asociado2",
            "asociado1",
            _redondo(azar.uniform(1500, 2600), 50),
        )
    # Un aporte mensual mínimo y, algunos meses, uno grande que baja el saldo de golpe.
    if azar.random() < 0.7:
        yield Evento(
            _en_dia(inicio, 12, semana, 20, 0),
            "asociado2",
            "fondo",
            _redondo(azar.uniform(80, 300)),
        )
    if azar.random() < 0.45:
        yield Evento(
            _en_dia(inicio, 20, semana, 20, 30),
            "asociado2",
            "fondo",
            _redondo(azar.uniform(2000, 5000), 50),
        )
    if azar.random() < 0.4:
        yield _intento_rechazado(
            inicio, azar, "asociado2", ("fondo", "asociado1", "asociado3"), semana, (19, 22)
        )


# Los meses (por índice) en que asociado3 se mueve. Tiene huecos largos a propósito y
# el último mes completo y el actual activos, para que la proyección vea un pico.
MESES_ACTIVOS_DEL_ESPORADICO = {0, 2, 3, 6, 9, MESES - 1, MESES}


def _esporadico(i: int, inicio: datetime, azar: random.Random) -> Iterator[Evento]:
    """asociado3: pocos meses activos, montos muy altos y préstamos a asociado1."""
    semana = (JUEVES, VIERNES)
    if i not in MESES_ACTIVOS_DEL_ESPORADICO:
        # En los meses quietos, a veces intenta algo que no le alcanza.
        if azar.random() < 0.3:
            yield _intento_rechazado(
                inicio, azar, "asociado3", ("fondo", "asociado1"), semana, (14, 17)
            )
        return
    retiro = _redondo(azar.uniform(4000, 12000), 100)
    dia = azar.choice((1, 4, 8))
    yield Evento(
        _en_dia(inicio, dia, semana, 15, azar.randrange(0, 60, 5)), "fondo", "asociado3", retiro
    )
    # Algunos meses devuelve menos de lo que retiró y otros salda lo de antes también.
    aporte = _redondo(float(retiro) * azar.uniform(0.5, 1.35), 50)
    yield Evento(
        _en_dia(inicio, dia + 6, semana, 16, azar.randrange(0, 60, 5)), "asociado3", "fondo", aporte
    )
    if azar.random() < 0.7:
        prestamo = _redondo(azar.uniform(800, 2200), 50)
        yield Evento(_en_dia(inicio, dia + 13, semana, 14, 30), "asociado3", "asociado1", prestamo)
    if azar.random() < 0.3:
        yield Evento(
            _en_dia(inicio, dia + 16, semana, 17, 0),
            "asociado3",
            "asociado2",
            _redondo(azar.uniform(150, 500)),
        )
    if azar.random() < 0.25:
        yield _intento_rechazado(
            inicio, azar, "asociado3", ("fondo", "asociado1", "asociado2"), semana, (14, 17)
        )


# Los meses (por índice) en que el constituyente emite capital al fondo, y en los que el
# fondo le devuelve excedentes. La última emisión cae en el mes actual y queda en espera.
MESES_DE_EMISION = {2, 4, 6, 8, 10}
MESES_DE_DEVOLUCION = {3, 7, 11}
# Los meses en que el constituyente intenta girar por el camino normal: con saldo
# negativo se rechaza, y eso muestra que la regla de saldo también vale para él.
MESES_DE_RECHAZO_DEL_EMISOR = {5, 9}


def _emisor(i: int, inicio: datetime, azar: random.Random) -> Iterator[Evento]:
    """constituyente: emisiones bimestrales grandes y devoluciones del fondo cada cuatro meses.

    Es el único perfil con saldo negativo: emite sin haber recibido, que es su papel de
    puerta de entrada del capital. Opera el primer día hábil del mes, temprano.
    """
    habiles = (LUNES, MARTES, MIERCOLES, JUEVES, VIERNES)
    if i in MESES_DE_EMISION or i == MESES:
        monto = _redondo(azar.uniform(8000, 20000), 500)
        yield Evento(_en_dia(inicio, 1, habiles, 7, 0), "constituyente", "fondo", monto)
    if i in MESES_DE_DEVOLUCION:
        monto = _redondo(azar.uniform(1500, 4000), 100)
        yield Evento(_en_dia(inicio, 28, habiles, 11, 30), "fondo", "constituyente", monto)
    if i in MESES_DE_RECHAZO_DEL_EMISOR:
        yield _intento_rechazado(inicio, azar, "constituyente", ("fondo",), habiles, (7, 9))


PERFILES: dict[str, PerfilDeMes] = {
    "constituyente": _emisor,
    "asociado1": _comerciante,
    "asociado2": _frecuente,
    "asociado3": _esporadico,
}


def planear(hoy: datetime) -> list[Evento]:
    """Todos los eventos de los trece meses, en orden cronológico y sin futuro.

    Cada perfil tiene su propio generador de azar, derivado de la semilla y de su
    nombre: así agregar o tocar un perfil no cambia la historia de los demás.
    """
    eventos: list[Evento] = []
    azares = {nombre: random.Random(f"{SEMILLA}-{nombre}") for nombre in PERFILES}
    for i, meses_atras in enumerate(range(MESES, -1, -1)):
        inicio = _primer_dia(meses_atras, hoy)
        for nombre, perfil in PERFILES.items():
            eventos.extend(perfil(i, inicio, azares[nombre]))
    limite = hoy - timedelta(hours=1)
    return sorted((e for e in eventos if e.momento < limite), key=lambda e: e.momento)


def _ya_sembrada(chain: Blockchain, fondo_id: UUID) -> bool:
    """Si el fondo ya tiene historia vieja, no hay nada que sembrar."""
    limite = datetime.now(UTC) - UMBRAL_DE_HISTORIA
    return any(
        transaction.created_at < limite
        for transaction in chain.wallet_history(fondo_id, limit=100_000)
    )


def _cierre(dia: date, hoy: datetime) -> datetime:
    """Las 23:00 de ese día, o ahora si el día es hoy."""
    return min(datetime.combine(dia, time(23, 0), tzinfo=UTC), hoy)


def _monto_rechazado(disponible: Decimal, momento: datetime) -> Decimal:
    """Un monto que supera el saldo por un margen que cambia de un intento a otro."""
    azar = random.Random(f"{SEMILLA}-rechazo-{momento.isoformat()}")
    base = max(disponible, Decimal(0))
    return _redondo(float(base) * azar.uniform(1.2, 2.8) + azar.uniform(300, 4000), 50)


def _mover(
    chain: Blockchain,
    origen: UUID,
    destino: UUID,
    monto: Decimal,
    momento: datetime,
    reserva: Decimal = Decimal(0),
) -> bool:
    """Una salida normal: recorta el monto al saldo disponible para que no se rechace.

    `reserva` es lo que la cuenta recibió de la semilla base. Esas filas están fechadas
    hoy, así que la gráfica de saldo las suma al final; si la historia las gastara
    antes, la curva pasaría por debajo de cero en el pasado.
    """
    disponible = chain.available_balance(origen) - reserva
    monto = min(monto, (disponible * Decimal("0.95")).quantize(Decimal("10")))
    if monto < MINIMO:
        return False
    resultado = chain.create_transaction(
        sender_id=origen, receiver_id=destino, amount=monto, created_at=momento
    )
    return resultado.stored is not None


def sembrar(
    chain: Blockchain, usuarios: PostgresAccountsRepository, reloj: Reloj
) -> tuple[int, int]:
    """Siembra la historia y devuelve cuántos bloques y transacciones agregó."""
    fondo = chain.wallets.get_by_public_key(FONDO)
    if fondo is None:
        return 0, 0
    if _ya_sembrada(chain, fondo.id):
        return 0, 0

    wallets: dict[str, UUID] = {"fondo": fondo.id, "constituyente": CONSTITUYENTE_ID}
    for nombre in ASOCIADOS_DE_LA_HISTORIA:
        usuario = usuarios.get_by_username(nombre)
        if usuario is not None and usuario.wallet_id is not None:
            wallets[nombre] = usuario.wallet_id
    if len(wallets) == 2:
        return 0, 0

    hoy = datetime.now(UTC)
    bloques = transacciones = 0

    # El capital del fondo, emitido por la misma puerta que usa la semilla base y fechado
    # antes de la primera historia.
    reloj.ahora = _primer_dia(MESES + 1, hoy) + timedelta(days=1)
    chain.transactions.add(entrega_de_capital(chain, CONSTITUYENTE_ID, fondo.id, CAPITAL_DEL_FONDO))
    if chain.group_pending() is not None:
        bloques += 1
        transacciones += 1
    # Lo que cada cuenta ya tiene de la semilla base (agrupada recién, junto con el
    # capital del fondo) no se gasta en el pasado: ver `_mover`.
    reservas = {
        wallet: chain.available_balance(wallet)
        for nombre, wallet in wallets.items()
        if nombre in ASOCIADOS_DE_LA_HISTORIA
    }

    # Cada día con movimientos se sella en su propio bloque al cerrar el día, así lo que
    # entra un día ya cuenta como saldo el siguiente. Los últimos días quedan en el pool.
    desde_espera = (hoy - timedelta(days=DIAS_EN_ESPERA)).date()
    dia_abierto: date | None = None
    for evento in planear(hoy):
        if evento.origen not in wallets or evento.destino not in wallets:
            continue
        dia = evento.momento.date()
        if dia_abierto is not None and dia != dia_abierto and dia_abierto < desde_espera:
            reloj.ahora = _cierre(dia_abierto, hoy)
            if chain.group_pending() is not None:
                bloques += 1
        dia_abierto = dia

        origen = wallets[evento.origen]
        destino = wallets[evento.destino]
        if evento.rechazo:
            # A propósito por encima del saldo: la validación la deja como rechazada.
            resultado = chain.create_transaction(
                sender_id=origen,
                receiver_id=destino,
                amount=_monto_rechazado(chain.available_balance(origen), evento.momento),
                created_at=evento.momento,
            )
            transacciones += 1 if resultado.stored is not None else 0
            continue
        if evento.origen == "constituyente":
            # La emisión no pasa por la regla de saldo: entra por la misma puerta que
            # la semilla base, firmada por el constituyente y fechada con el evento.
            reloj.ahora = evento.momento
            chain.transactions.add(entrega_de_capital(chain, origen, destino, evento.monto))
            transacciones += 1
            continue
        transacciones += _mover(
            chain, origen, destino, evento.monto, evento.momento, reservas.get(origen, Decimal(0))
        )

    if dia_abierto is not None and dia_abierto < desde_espera:
        reloj.ahora = _cierre(dia_abierto, hoy)
        if chain.group_pending() is not None:
            bloques += 1

    # Unos movimientos recientes más que quedan en el pool, para que todas las cuentas
    # muestren el estado «En espera» sin depender de qué días cayó la historia.
    for horas, nombre, destino, monto in EN_ESPERA:
        if nombre not in wallets or destino not in wallets:
            continue
        transacciones += _mover(
            chain, wallets[nombre], wallets[destino], monto, hoy - timedelta(hours=horas)
        )
    return bloques, transacciones


def main() -> None:
    """Abre la conexión, siembra la historia que falte e informa qué hizo."""
    dsn = database_url()
    with psycopg.connect(dsn, autocommit=True) as conexion:
        # La misma zona que el resto del ledger: el hash cubre `isoformat()`.
        conexion.execute("SET TIME ZONE 'UTC'")
        reloj = Reloj(datetime.now(UTC))
        chain = open_ledger(
            conexion,
            encryption_key=master_key(),
            clock=reloj,
            database_dsn=dsn,
        )
        usuarios = PostgresAccountsRepository(conexion)
        bloques, transacciones = sembrar(chain, usuarios, reloj)
        if bloques:
            estado = chain.ledger_state()
            print(
                f"historial sembrado: {bloques} bloques y {transacciones} transacciones "
                f"en {MESES} meses y lo que va del actual"
            )
            print(
                f"estado del ledger: {estado['wallets']} wallets, {estado['blocks']} bloques, "
                f"{estado['transactions']} transacciones"
            )
        else:
            print("la historia ya estaba sembrada: no se agregó nada")


if __name__ == "__main__":
    main()
