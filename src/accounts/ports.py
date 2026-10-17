"""Puerto del repositorio de usuarios: lo que el servicio de cuentas espera (REQ-16).

Es un `Protocol` y no una clase base porque describe la forma y no la herencia:
el servicio depende de estos nombres —y no de `psycopg`—, y el adaptador que los
cumple vive en `postgres.py`. La lista de pendientes se devuelve como `Sequence`,
igual que las listas de los repositorios del ledger.
"""
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from src.accounts.model import Usuario


class RepositorioDeUsuarios(Protocol):
    """Acceso a las cuentas del alta moderada (REQ-30, REQ-31)."""

    def add_pendiente(self, usuario: Usuario) -> Usuario: ...

    def sembrar(self, usuario: Usuario) -> Usuario: ...

    def get_by_username(self, username: str) -> Usuario | None: ...

    def get(self, id: UUID) -> Usuario | None: ...

    def list_pendientes(self) -> Sequence[Usuario]: ...

    def aprobar(self, id: UUID, wallet_id: UUID) -> Usuario | None: ...

    def rechazar(self, id: UUID, motivo: str) -> Usuario | None: ...

    def count(self) -> int: ...
