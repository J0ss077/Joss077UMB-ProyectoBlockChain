"""Modelo de usuario: la cuenta y su estado en el alta moderada (REQ-30, REQ-31).

`Usuario` describe una fila de `users` y las constantes son los únicos valores
que el esquema admite para el rol y para el estado. El modelo no sabe de base ni
de sesión: el repositorio de `postgres.py` es quien lo lee y lo escribe, y el
servicio de cuentas, quien decide cuándo se crea y cuándo se aprueba.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# Los dos roles del diseño (decisión 1): el común usa el sistema como una wallet
# y el administrador conserva el control del sistema entero (REQ-38).
ADMINISTRADOR = "administrador"
USUARIO = "usuario"

# Los tres estados del alta moderada (REQ-30, REQ-31): el registro deja la cuenta
# pendiente, la aprobación la habilita y el rechazo es final.
PENDIENTE = "pendiente"
APROBADO = "aprobado"
RECHAZADO = "rechazado"


class UsuarioDuplicado(Exception):
    """El nombre de usuario ya está registrado (REQ-30).

    La levanta el repositorio al traducir la violación del índice único del
    nombre: el servicio de cuentas no tiene que conocer el driver para rechazar
    el registro repetido con un motivo. El nombre normalizado viaja en el
    argumento, que es el que intentó registrarse.
    """


@dataclass(frozen=True, slots=True)
class Usuario:
    """Una cuenta del sistema, tal como vive en `users` (REQ-30, REQ-31).

    Invariante: mientras `estado` sea `pendiente` o `rechazado`, `wallet_id` y
    `aprobado_en` son nulos; sólo el `aprobado` tiene wallet, y el rechazado
    lleva siempre su `motivo_rechazo` (esquema §6 y REQ-31).
    """

    id: UUID
    username: str
    password_hash: str
    role: str
    estado: str
    motivo_rechazo: str | None
    wallet_id: UUID | None
    creado_en: datetime
    aprobado_en: datetime | None
