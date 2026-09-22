"""Conexión con PostgreSQL."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from src.config import database_url


def connect() -> psycopg.Connection:
    """Abre una conexión nueva que devuelve las filas como diccionarios."""
    return psycopg.connect(database_url(), row_factory=dict_row)


def server_version() -> str:
    """Devuelve la versión del servidor, como comprobación de que responde."""
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            row = cursor.fetchone()
        return str(row["server_version"]) if row else "desconocida"
    finally:
        connection.close()
