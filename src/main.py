"""Punto de entrada del backend.

Comprueba que la conexión con PostgreSQL funcione y reporta el estado del
ledger. No interpreta argumentos ni ejecuta operaciones: para el CRUD manual se
usa una sesión interactiva, como se describe en docs/puesta-en-marcha.md.
"""

from __future__ import annotations

import sys

import psycopg

from src.config import ConfigError
from src.persistence.connection import server_version
from src.persistence.factory import ledger


def main() -> int:
    """Verifica la conexión y muestra el conteo de las tres tablas."""
    try:
        print(f"PostgreSQL: {server_version()}")
        with ledger() as chain:
            for table, total in chain.counts().items():
                print(f"{table}: {total}")
    except ConfigError as error:
        print(f"Configuración incompleta: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"No se pudo conectar con la base: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
