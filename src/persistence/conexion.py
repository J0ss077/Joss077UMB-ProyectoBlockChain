"""La conexión con PostgreSQL, en un módulo propio.

Todo lo que abre una conexión pasa por acá —la del ledger, la de la transacción
que comparten el ledger y las cuentas, y la de la unidad de trabajo de la
agrupación—, y eso da dos cosas que antes estaban repetidas en cada punto:

1. **Una sola traducción del fallo.** Un motor que no responde se levanta como
   `NoHayConexion`, el error que la aplicación sabe pintar como página 503, en
   vez de un `OperationalError` que cada capa tuviera que reconocer.
2. **Una sola zona horaria.** La sesión queda en UTC porque el hash del bloque
   cubre `datetime.isoformat()`: dos sesiones en zonas distintas calcularían
   hashes distintos para la misma fila y una cadena válida se leería como
   alterada.

El resto de la configuración —de dónde sale la cadena de conexión— sigue en
`factory.py`, que es el ensamblado del ledger. Este módulo no decide con qué base
se habla: recibe la cadena ya resuelta.
"""
from __future__ import annotations

import psycopg

from src.errores import MENSAJE_SIN_CONEXION, NoHayConexion


def abrir(dsn: str, *, autocommit: bool = False) -> psycopg.Connection:
    """Abre una conexión y traduce el fallo del motor a `NoHayConexion`.

    `autocommit` queda en `False` por defecto: la conexión que comparten el ledger
    y las cuentas decide cuándo confirma (REQ-18, REQ-33). El ledger de lectura y
    las pruebas piden `autocommit=True`, porque cada lectura tiene que ver lo
    último confirmado.

    Sólo se traduce `OperationalError`, que es el fallo de conexión —host, puerto,
    credenciales, motor apagado—. Un error de otra clase sigue subiendo sin
    traducir (REQ-19): si el motor responde y falla una restricción, eso es un
    problema del dato y la traza completa hace falta para diagnosticarlo.
    """
    try:
        return psycopg.connect(dsn, autocommit=autocommit)
    except psycopg.OperationalError as error:
        raise NoHayConexion(MENSAJE_SIN_CONEXION) from error


def abrir_en_utc(dsn: str, *, autocommit: bool = False) -> psycopg.Connection:
    """Abre la conexión y deja la sesión en UTC, que es lo que exige el hash.

    Si el motor acepta la conexión pero rechaza el `SET TIME ZONE`, la conexión se
    cierra antes de subir el error: es de este módulo y nadie más la conoce, así
    que dejarla abierta sería una conexión perdida por cada intento.
    """
    connection = abrir(dsn, autocommit=autocommit)
    try:
        connection.execute("SET TIME ZONE 'UTC'")
    except BaseException:
        connection.close()
        raise
    return connection
