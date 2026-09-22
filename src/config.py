"""Configuración del backend.

Resuelve la cadena de conexión a PostgreSQL. El valor se toma de la variable de
entorno DATABASE_URL y, si no está definida, se lee del archivo .env del
repositorio.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class ConfigError(RuntimeError):
    """Falta configuración indispensable para conectar con la base."""


def _read_env_file(path: Path) -> dict[str, str]:
    """Lee un archivo .env sin dependencias externas.

    Ignora líneas vacías y comentarios. No interpreta comillas ni expansión de
    variables, porque el archivo del proyecto no las usa.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def database_url() -> str:
    """Devuelve la cadena de conexión, con prioridad del entorno sobre el archivo."""
    from_environment = os.environ.get("DATABASE_URL")
    if from_environment:
        return from_environment

    from_file = _read_env_file(ENV_FILE).get("DATABASE_URL")
    if from_file:
        return from_file

    raise ConfigError(
        "Falta DATABASE_URL. Definila en el entorno o copiá .env.example a .env."
    )
