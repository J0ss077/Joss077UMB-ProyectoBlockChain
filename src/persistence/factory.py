"""Ensamblado del ledger: configuración del entorno y adaptadores (REQ-16, REQ-21).

Resuelve de dónde salen la cadena de conexión y la clave maestra, y arma la
fachada del dominio con los tres repositorios PostgreSQL y la unidad de trabajo de
REQ-18. `open_ledger` trabaja sobre una conexión que no abre —así la reutilizan el
arranque y las pruebas— y `ledger()` es el punto de entrada que sí la abre y la
cierra.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg

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


def database_url() -> str:
    """Cadena de conexión del entorno o de `.env`.

    Si falta, falla con la instrucción en vez de adivinar un valor: una
    configuración a medias tiene que doler ahora y no en la primera consulta.
    """
    url = _env_value("DATABASE_URL")
    if url:
        return url
    raise RuntimeError(
        "Falta DATABASE_URL en el entorno y en `.env`: levante la base con "
        "`docker compose up -d` (o `podman compose up -d`) y copie `.env.example` a `.env`."
    )


def master_key() -> bytes:
    """Clave Fernet con la que se cifra el material privado de las wallets (REQ-21)."""
    value = _env_value("MASTER_KEY")
    if value:
        return value.encode("ascii")
    raise RuntimeError("Falta MASTER_KEY en el entorno y en `.env`: copie `.env.example` a `.env`.")


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
    la misma base aunque el entorno cambie a mitad de camino.

    Los tres repositorios de lectura comparten esa conexión; la agrupación no,
    porque REQ-18 exige que sus dos escrituras ocurran en una sola transacción de
    base de datos y para eso la unidad de trabajo abre la suya propia.
    """
    dsn = database_dsn if database_dsn is not None else database_url()
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
        connection.execute("SET TIME ZONE 'UTC'")
        yield open_ledger(connection, encryption_key=master_key(), database_dsn=dsn)
