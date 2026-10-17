"""Adaptador PostgreSQL del repositorio de usuarios (REQ-30, REQ-31).

Recibe la conexión ya abierta y no la cierra, igual que los repositorios de
`src/persistence/postgres.py`: la conexión pertenece a quien la abrió y las
escrituras de una aprobación comparten una sola transacción (REQ-18, REQ-33).

La única traducción de errores del proyecto vive acá. El nombre de usuario es
único y REQ-30 exige rechazar el registro repetido con un motivo; el servicio no
debe conocer el driver, así que la violación de unicidad del nombre se traduce a
`UsuarioDuplicado` y el resto de los errores del motor sube crudo (REQ-19).

El nombre se normaliza en el repositorio, al escribir y al buscar, para que
ningún llamador pueda saltarse la regla de REQ-30.
"""
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from src.accounts.credentials import normalizar_usuario
from src.accounts.model import APROBADO, PENDIENTE, RECHAZADO, Usuario, UsuarioDuplicado

# Los dos nombres con los que el motor puede informar la unicidad del nombre: el
# `UNIQUE` exacto del esquema y el índice único sobre `lower(username)`. Como la
# aplicación normaliza antes de escribir, un duplicado puede violar cualquiera de
# los dos; una violación de `users_wallet_id_key` no es un nombre repetido y sube
# sin traducir.
_UNICIDAD_DEL_NOMBRE = frozenset({"users_username_key", "users_username_minusculas"})


def _row_to_usuario(row: dict[str, Any]) -> Usuario:
    """Fila de `users` al objeto del modelo."""
    return Usuario(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=row["role"],
        estado=row["estado"],
        motivo_rechazo=row["motivo_rechazo"],
        wallet_id=row["wallet_id"],
        creado_en=row["creado_en"],
        aprobado_en=row["aprobado_en"],
    )


class PostgresAccountsRepository:
    """Repositorio de usuarios sobre PostgreSQL (REQ-30, REQ-31)."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    def _insertar(
        self, sentencia: str, parametros: tuple[object, ...], username: str
    ) -> Usuario:
        """Ejecuta un `INSERT` de `users` y traduce la violación del nombre.

        Las dos altas —la pendiente del registro y la ya aprobada de la
        semilla— comparten la traducción a `UsuarioDuplicado`: el servicio no
        tiene que conocer el driver para rechazar un nombre repetido (REQ-30).
        Una violación de `users_wallet_id_key` no es un nombre repetido y sube
        sin traducir.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        try:
            cursor.execute(sentencia, parametros)
        except psycopg.errors.UniqueViolation as error:
            if error.diag.constraint_name not in _UNICIDAD_DEL_NOMBRE:
                raise
            raise UsuarioDuplicado(username) from error
        return _row_to_usuario(cursor.fetchone())

    def add_pendiente(self, usuario: Usuario) -> Usuario:
        """Registra la cuenta como pendiente y devuelve la fila escrita (REQ-30).

        El estado, el motivo, la wallet y la fecha de aprobación se escriben
        fijos: una cuenta que nace no puede estar aprobada ni tener wallet, y
        dejar esos campos en manos del llamador permitiría una fila que el alta
        moderada no contempla. El nombre se normaliza acá.
        """
        username = normalizar_usuario(usuario.username)
        return self._insertar(
            """
            INSERT INTO users (
                id, username, password_hash, role, estado,
                motivo_rechazo, wallet_id, creado_en, aprobado_en
            )
            VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, NULL)
            RETURNING *
            """,
            (
                usuario.id,
                username,
                usuario.password_hash,
                usuario.role,
                PENDIENTE,
                usuario.creado_en,
            ),
            username,
        )

    def sembrar(self, usuario: Usuario) -> Usuario:
        """Escribe una fila ya aprobada, con su wallet o sin ella (semilla).

        El alta normal pasa por `add_pendiente` y `aprobar`; este camino existe
        para que el arranque deje al administrador aprobado sin wallet —la única
        cuenta a la que el esquema se lo admite— y a los usuarios de demostración
        aprobados con la wallet que ya sembró. La fila la decide el llamador
        porque la semilla no pasa por el alta moderada, pero el esquema sigue
        siendo el que impide una combinación inválida. El nombre se normaliza y
        la violación de unicidad se traduce igual que en el registro.
        """
        username = normalizar_usuario(usuario.username)
        return self._insertar(
            """
            INSERT INTO users (
                id, username, password_hash, role, estado,
                motivo_rechazo, wallet_id, creado_en, aprobado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                usuario.id,
                username,
                usuario.password_hash,
                usuario.role,
                usuario.estado,
                usuario.motivo_rechazo,
                usuario.wallet_id,
                usuario.creado_en,
                usuario.aprobado_en,
            ),
            username,
        )

    def get_by_username(self, username: str) -> Usuario | None:
        """La cuenta con ese nombre, buscado ya normalizado (REQ-30).

        La comparación es contra `lower(username)` y no contra la columna cruda:
        así una fila escrita por fuera de la aplicación en mayúsculas también se
        encuentra, y el índice único sobre `lower(username)` es el que resuelve
        la búsqueda.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            "SELECT * FROM users WHERE lower(username) = %s",
            (normalizar_usuario(username),),
        )
        row = cursor.fetchone()
        return _row_to_usuario(row) if row is not None else None

    def get(self, id: UUID) -> Usuario | None:
        """La cuenta con ese identificador, o `None` si no existe."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute("SELECT * FROM users WHERE id = %s", (id,))
        row = cursor.fetchone()
        return _row_to_usuario(row) if row is not None else None

    def list_pendientes(self) -> Sequence[Usuario]:
        """Las cuentas que esperan aprobación, de la más antigua a la más nueva (REQ-31)."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            "SELECT * FROM users WHERE estado = %s ORDER BY creado_en, id",
            (PENDIENTE,),
        )
        return [_row_to_usuario(row) for row in cursor.fetchall()]

    def nombres_por_wallet(self) -> dict[UUID, str]:
        """El nombre de usuario de cada wallet que tiene dueño.

        Sólo las cuentas aprobadas tienen wallet (el CHECK del esquema lo exige),
        así que el mapa no incluye pendientes ni rechazadas. Las wallets que no son
        de ninguna cuenta —las que registra el administrador— no aparecen.
        """
        filas = self._connection.execute(
            "SELECT wallet_id, username FROM users WHERE wallet_id IS NOT NULL"
        ).fetchall()
        return {wallet_id: username for wallet_id, username in filas}

    def aprobar(self, id: UUID, wallet_id: UUID) -> Usuario | None:
        """Liga la wallet y pasa la cuenta a `aprobado` en una sola escritura (REQ-31).

        La condición `estado = 'pendiente'` viaja dentro del mismo `UPDATE`: dos
        aprobaciones simultáneas no pueden dejar dos wallets ni reemplazar la
        primera, y una cuenta que ya no está pendiente devuelve `None` sin
        escribir. La fecha de aprobación la pone el reloj de la base.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            UPDATE users
            SET estado = %s, wallet_id = %s, aprobado_en = NOW()
            WHERE id = %s AND estado = %s
            RETURNING *
            """,
            (APROBADO, wallet_id, id, PENDIENTE),
        )
        row = cursor.fetchone()
        return _row_to_usuario(row) if row is not None else None

    def rechazar(self, id: UUID, motivo: str) -> Usuario | None:
        """Guarda el motivo y pasa la cuenta a `rechazado` (REQ-31).

        El rechazo es final: sólo toca las pendientes, y una cuenta ya aprobada o
        rechazada devuelve `None` sin escribir. El motivo vacío lo impide el
        esquema cuando es nulo y la presentación cuando es blanco; acá no se
        traduce, porque REQ-19 quiere el error del motor tal como llega.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            UPDATE users
            SET estado = %s, motivo_rechazo = %s
            WHERE id = %s AND estado = %s
            RETURNING *
            """,
            (RECHAZADO, motivo, id, PENDIENTE),
        )
        row = cursor.fetchone()
        return _row_to_usuario(row) if row is not None else None

    def count(self) -> int:
        """Cuántas cuentas hay registradas, en cualquier estado."""
        return self._connection.execute("SELECT count(*) FROM users").fetchone()[0]
