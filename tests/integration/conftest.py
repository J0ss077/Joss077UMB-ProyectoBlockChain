"""Fixtures de las pruebas de integración: una conexión viva y una base limpia.

El esquema se aplica con `db/init.sql` sobre el contenedor o sobre el clúster
nativo del equipo, así que estas pruebas no crean ni modifican tablas: solo
borran filas. El fixture `ledger` (la fachada armada) no vive aquí porque nace
en la tarea 7, junto con `src/persistence/factory.py`.
"""
import os
from pathlib import Path

import psycopg
import pytest

# Raíz del repositorio: la suite se corre desde aquí, y las pruebas que invocan
# `git` o que buscan `src` dependen de este directorio de trabajo.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    """Cadena de conexión del entorno o de `.env`; si falta, falla con la instrucción."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for linea in env_file.read_text(encoding="utf-8").splitlines():
            clave, separador, valor = linea.partition("=")
            if separador and clave.strip() == "DATABASE_URL":
                return valor.strip().strip("'\"")
    raise RuntimeError(
        "Falta DATABASE_URL en el entorno y en `.env`: levante la base con "
        "`docker compose up -d` (o `podman compose up -d`) y copie `.env.example` a `.env`. "
        "Una prueba omitida en silencio no verifica nada, así que esto falla en vez de saltarse."
    )


@pytest.fixture(scope="session")
def conexion():
    """Conexión abierta a la base del entorno, en UTC y sin cierre automático por sentencia.

    El alcance es de sesión porque PostgreSQL es un recurso caro de abrir por
    prueba; la limpieza de filas la hace `base_limpia` antes de cada una.
    """
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        connection.execute("SET TIME ZONE 'UTC'")
        yield connection


@pytest.fixture
def base_limpia(conexion):
    """Vacía las tres tablas antes de cada prueba, en orden inverso a las claves foráneas.

    Se borra con `DELETE` y no con `TRUNCATE`: `TRUNCATE` es DDL y REQ-15 lo
    prohíbe desde las pruebas. No es `autouse` a propósito: una prueba sin base
    (REQ-15 y REQ-21) no debe arrastrar la conexión y, con ella, la exigencia de
    `DATABASE_URL`; cada prueba que toca la base lo pide.
    """
    conexion.execute("DELETE FROM transactions")
    conexion.execute("DELETE FROM blocks")
    conexion.execute("DELETE FROM wallets")
    yield
