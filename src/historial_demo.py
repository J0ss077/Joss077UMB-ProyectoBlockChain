"""Historial de demostración: doce meses de aportes y retiros para las cuentas de prueba.

La semilla deja el caso del eje con unos pocos movimientos del mismo día, que alcanza
para mostrar que la cadena funciona pero no para mirar una tendencia: la página de
estadísticas filtra por período y la proyección mira los últimos treinta y sesenta días,
y con un solo día no hay nada que ver.

Este módulo agrega doce meses de historia a las wallets que ya sembró el arranque, con
el mismo camino que usa la aplicación: cada transacción se firma con la llave del
emisor, se valida el saldo disponible y se agrupa en un bloque encadenado. No escribe
filas a mano: si una transacción no fuera válida, no entraría.

**Es idempotente**: si la wallet del fondo ya tiene un movimiento de hace más de 45
días, no hace nada. Correrlo dos veces no duplica la historia.

Uso:

    <venv> -m src.historial_demo
"""
from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import psycopg

from src.accounts.postgres import PostgresAccountsRepository
from src.bootstrap import FONDO
from src.domain.blockchain import Blockchain
from src.persistence.factory import database_url, master_key, open_ledger

# Cuántos meses hacia atrás se siembran y qué se mueve en cada uno.
MESES = 12
# Aporte de cada asociado al fondo el día 6; retiro del fondo el día 21. Los montos
# varían un poco entre meses para que las gráficas no salgan planas.
APORTE = Decimal("30.00")
RETIRO = Decimal("25.00")
DIAS_DE_COBRANZA = 6
DIAS_DE_RETIRO = 21
# Si el fondo ya tiene un movimiento más viejo que esto, la historia ya está sembrada.
UMBRAL_DE_HISTORIA = timedelta(days=45)

# Las cuentas que aportan y reciben. Son sólo las tres de asociados: el fondo es la
# contraparte y el constituyente ya tiene su papel en la emisión; si entraran en la
# lista, el fondo se pagaría a sí mismo o le giraría al constituyente, que no es el
# caso de uso de un fondo de empleados.
ASOCIADOS_DE_LA_HISTORIA = ("asociado1", "asociado2", "asociado3")


class Reloj:
    """Reloj controlable: es el que sella los bloques con la fecha del mes que toca."""

    def __init__(self, ahora: datetime) -> None:
        self.ahora = ahora

    def __call__(self) -> datetime:
        return self.ahora


def _primer_dia(meses_atras: int) -> datetime:
    """El primer día del mes que está `meses_atras` meses antes del actual, en UTC."""
    hoy = datetime.now(UTC)
    anio, mes = hoy.year, hoy.month - meses_atras
    while mes <= 0:
        mes += 12
        anio -= 1
    return datetime(anio, mes, 1, tzinfo=UTC)


def _fin_de_mes(inicio: datetime) -> datetime:
    """El último día de ese mes a las 23:00, que es cuando se sella el bloque."""
    siguiente = (inicio + timedelta(days=32)).replace(day=1)
    return siguiente - timedelta(hours=1)


def _ya_sembrada(chain: Blockchain, fondo_id) -> bool:
    """Si el fondo ya tiene historia vieja, no hay nada que sembrar."""
    limite = datetime.now(UTC) - UMBRAL_DE_HISTORIA
    return any(
        transaction.created_at < limite
        for transaction in chain.wallet_history(fondo_id)
    )


def sembrar(
    chain: Blockchain, usuarios: PostgresAccountsRepository, reloj: Reloj
) -> tuple[int, int]:
    """Siembra los meses que falten y devuelve cuántos bloques y transacciones agregó."""
    fondo = chain.wallets.get_by_public_key(FONDO)
    if fondo is None:
        return 0, 0
    if _ya_sembrada(chain, fondo.id):
        return 0, 0

    asociados = []
    for nombre in ASOCIADOS_DE_LA_HISTORIA:
        usuario = usuarios.get_by_username(nombre)
        if usuario is not None and usuario.wallet_id is not None:
            asociados.append(usuario.wallet_id)
    if not asociados:
        return 0, 0

    bloques = transacciones = 0
    for meses_atras in range(MESES - 1, -1, -1):
        inicio = _primer_dia(meses_atras)
        # Primero los aportes: el fondo necesita el saldo antes de girar los retiros.
        for asociado in asociados:
            resultado = chain.create_transaction(
                sender_id=asociado,
                receiver_id=fondo.id,
                amount=APORTE,
                created_at=datetime.combine(
                    (inicio + timedelta(days=DIAS_DE_COBRANZA - 1)).date(),
                    time(10, 0),
                    tzinfo=UTC,
                ),
            )
            transacciones += 1 if resultado.stored is not None else 0
        for asociado in asociados:
            resultado = chain.create_transaction(
                sender_id=fondo.id,
                receiver_id=asociado,
                amount=RETIRO,
                created_at=datetime.combine(
                    (inicio + timedelta(days=DIAS_DE_RETIRO - 1)).date(),
                    time(17, 0),
                    tzinfo=UTC,
                ),
            )
            transacciones += 1 if resultado.stored is not None else 0
        reloj.ahora = _fin_de_mes(inicio)
        if chain.group_pending() is not None:
            bloques += 1
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
                f"en {MESES} meses"
            )
            print(
                f"estado del ledger: {estado['wallets']} wallets, {estado['blocks']} bloques, "
                f"{estado['transactions']} transacciones"
            )
        else:
            print("la historia ya estaba sembrada: no se agregó nada")


if __name__ == "__main__":
    main()
