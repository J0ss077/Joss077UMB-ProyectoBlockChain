"""Ensamblado del ledger: configuración del entorno y adaptadores (REQ-16, REQ-21).

Resuelve de dónde salen la cadena de conexión, la clave maestra, el secreto de la
sesión y la contraseña del administrador, y arma la fachada del dominio con los
tres repositorios PostgreSQL y la unidad de trabajo de REQ-18. `open_ledger` trabaja
sobre una conexión que no abre —así la reutilizan el arranque y las pruebas— y
`ledger()` es el punto de entrada que sí la abre y la cierra.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from src.domain.blockchain import Blockchain
from src.persistence.postgres import (
    PostgresBlockRepository,
    PostgresTransactionRepository,
    PostgresWalletRepository,
)
from src.persistence.unit_of_work import PostgresUnitOfWork

# `.env` vive en la raíz del repositorio y está en `.gitignore` (REQ-21): es el
# respaldo local de las variables del entorno, nunca su reemplazo ni un secreto
# versionado.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Nombre de la variable que trae la cadena de conexión. Es una constante y no un
# literal porque el lector del entorno y la prueba que lo ejercita tienen que nombrar
# la misma variable: el guard de REQ-17 prohíbe el literal en `tests/unit`, así que la
# prueba importa esta constante en vez de escribirlo.
VARIABLE_DE_LA_CADENA_DE_CONEXION = "DATABASE_URL"

# Las dos variables de la sesión y del administrador sembrado van en constantes por
# la misma razón que la cadena de conexión: el lector y su prueba tienen que nombrar
# la misma variable y el guard de REQ-17 prohíbe el literal en `tests/unit`.
VARIABLE_DEL_SECRETO_DE_SESION = "SESSION_SECRET"
VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR = "ADMIN_PASSWORD"


def _env_value(name: str) -> str | None:
    """Valor de una variable del entorno o, si no está, del `.env` local.

    Devuelve `None` cuando no está en ninguno de los dos.
    """
    value = os.environ.get(name)
    if value:
        return value
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip().strip("'\"")
    return None


def normalizar_cadena(cadena: str) -> str:
    """Devuelve la cadena de conexión con `connect_timeout` puesto si no lo traía.

    Sin tiempo de espera, cuánto aguantar frente a un puerto que no contesta lo deciden
    la librería y el sistema operativo —y detrás del retransmisor de WSL2 en Windows
    puede ser mucho—, así que un puerto mal puesto se ve como un cuelgue en lugar de
    como un error. Un `connect_timeout` explícito en la cadena se respeta tal cual.

    Las dos entradas de una cadena pasan por acá: el lector del entorno y el argumento
    explícito de `open_ledger`. Normalizar en una sola función es lo que impide que una
    de las dos quede sin el tiempo de espera por olvido.

    La cadena vuelve en la forma canónica de libpq (`host=... port=...
    connect_timeout=5`), no en la forma de URL que se escribe en `.env`: para saber si
    ya traía un tiempo de espera hay que interpretarla, y `conninfo` la vuelve a
    escribir con todos sus parámetros más el que se agrega. `psycopg` acepta las dos
    formas, y de esta función solo sale la cadena con la que se conecta, así que el
    cambio de forma no llega a nadie más.
    """
    parametros = conninfo_to_dict(cadena)
    parametros.setdefault("connect_timeout", "5")
    return make_conninfo(**parametros)


def database_url() -> str:
    """Cadena de conexión del entorno o de `.env`, normalizada antes de devolverla.

    Si falta, falla con la instrucción en vez de adivinar un valor: una
    configuración a medias tiene que doler ahora y no en la primera consulta.

    Normalizar aquí y no en cada conexión cubre las dos que abre el ledger: la de
    `ledger()` y la de la unidad de trabajo, que reciben esta misma cadena.
    """
    url = _env_value(VARIABLE_DE_LA_CADENA_DE_CONEXION)
    if url:
        return normalizar_cadena(url)
    raise RuntimeError(
        f"Falta {VARIABLE_DE_LA_CADENA_DE_CONEXION} en el entorno y en `.env`: levante "
        "la base con `docker compose up -d` (o `podman compose up -d`) y copie "
        "`.env.example` a `.env`."
    )


def master_key() -> bytes:
    """Clave Fernet con la que se cifra el material privado de las wallets (REQ-21)."""
    value = _env_value("MASTER_KEY")
    if value:
        return value.encode("ascii")
    raise RuntimeError("Falta MASTER_KEY en el entorno y en `.env`: copie `.env.example` a `.env`.")


def session_secret() -> bytes:
    """Clave con la que Flask firma la cookie de sesión (REQ-37).

    Se devuelve como bytes porque es lo que espera `app.secret_key`; se lee del
    entorno y, si no está, de `.env`, igual que la clave maestra.
    """
    value = _env_value(VARIABLE_DEL_SECRETO_DE_SESION)
    if value:
        return value.encode("utf-8")
    raise RuntimeError(
        f"Falta {VARIABLE_DEL_SECRETO_DE_SESION} en el entorno y en `.env`: copie "
        "`.env.example` a `.env` y genere la clave con "
        '`.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"`.'
    )


def admin_password() -> str:
    """Contraseña de la cuenta de administrador que siembra el arranque (decisión 4)."""
    value = _env_value(VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR)
    if value:
        return value
    raise RuntimeError(
        f"Falta {VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR} en el entorno y en "
        "`.env`: copie `.env.example` a `.env` y fije la contraseña del administrador."
    )


def _utc_now() -> datetime:
    """Reloj por defecto del ledger, en UTC como la base y las marcas canónicas."""
    return datetime.now(UTC)


def open_ledger(
    connection: psycopg.Connection,
    *,
    encryption_key: bytes,
    clock: Callable[[], datetime] | None = None,
    database_dsn: str | None = None,
) -> Blockchain:
    """Arma el ledger sobre una conexión abierta que este módulo no cierra.

    `encryption_key` es la clave maestra con la que el ledger cifra y firma
    (decisión 3); se llama así aquí para no tapar la función `master_key()`, que es
    la que la lee del entorno.

    `database_dsn` es la cadena con la que se abre la unidad de trabajo; si no se
    pasa, se resuelve del entorno **una sola vez** aquí. Resolverla una vez y no en
    cada agrupación es lo que garantiza que las lecturas y las escrituras apunten a
    la misma base aunque el entorno cambie a mitad de camino. La cadena explícita se
    normaliza igual que la del entorno: es la otra puerta por la que entra una cadena
    y no hay razón para que una llegue con `connect_timeout` y la otra sin él.

    Los tres repositorios de lectura comparten esa conexión; la agrupación no,
    porque REQ-18 exige que sus dos escrituras ocurran en una sola transacción de
    base de datos y para eso la unidad de trabajo abre la suya propia.
    """
    dsn = database_url() if database_dsn is None else normalizar_cadena(database_dsn)
    return Blockchain(
        wallets=PostgresWalletRepository(connection),
        blocks=PostgresBlockRepository(connection),
        transactions=PostgresTransactionRepository(connection),
        unit_of_work=lambda: PostgresUnitOfWork.open(dsn),
        master_key=encryption_key,
        clock=clock if clock is not None else _utc_now,
    )


@contextmanager
def ledger() -> Iterator[Blockchain]:
    """Abre la conexión del entorno, entrega el ledger y la cierra al salir.

    La conexión va en autocommit, igual que la de las pruebas: cada lectura ve lo
    último confirmado, incluido lo que la agrupación confirmó en su transacción
    aparte. Es el punto de entrada de `src.bootstrap` y de la aplicación web, y por
    eso resuelve la cadena una sola vez y se la pasa a la fachada: la conexión que
    abre y la unidad de trabajo usan el mismo destino.
    """
    dsn = database_url()
    with psycopg.connect(dsn, autocommit=True) as connection:
        # La zona de la sesión decide cómo se leen las columnas `TIMESTAMPTZ`, y el
        # hash del bloque cubre `datetime.isoformat()`: sin UTC, la misma fila se
        # leería con otro desplazamiento y una cadena válida se verificaría como
        # alterada. Toda conexión del ledger queda en UTC por esta razón.
        connection.execute("SET TIME ZONE 'UTC'")
        yield open_ledger(connection, encryption_key=master_key(), database_dsn=dsn)
