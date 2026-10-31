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
from src.accounts.model import (
    APROBADO,
    PENDIENTE,
    RECHAZADO,
    USUARIO,
    FotoDePerfil,
    SolicitudDeContrasena,
    SolicitudYaPendiente,
    Usuario,
    UsuarioDuplicado,
)

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


# Las columnas de la solicitud más el nombre de la cuenta, que la cola necesita.
_SELECT_SOLICITUD = """
    SELECT s.*, u.username
    FROM solicitudes_de_contrasena s
    JOIN users u ON u.id = s.usuario_id
"""


def _row_to_solicitud(row: dict[str, Any]) -> SolicitudDeContrasena:
    """Fila de `solicitudes_de_contrasena` (con el nombre de la cuenta) al modelo."""
    return SolicitudDeContrasena(
        id=row["id"],
        usuario_id=row["usuario_id"],
        username=row["username"],
        password_hash=row["password_hash"],
        estado=row["estado"],
        motivo_rechazo=row["motivo_rechazo"],
        creado_en=row["creado_en"],
        resuelto_en=row["resuelto_en"],
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

    def agregar_contacto(self, usuario_id: UUID, contacto_id: UUID) -> bool:
        """Agenda la cuenta como contacto; `False` si ya estaba agendada.

        El `ON CONFLICT` hace que agregar dos veces —el doble clic, otra pestaña—
        no sea un error del motor sino una fila que ya existía. Quién puede
        agendarse lo decide el servicio; el CHECK del esquema sólo respalda que
        nadie se agende a sí mismo.
        """
        cursor = self._connection.execute(
            """
            INSERT INTO contactos (usuario_id, contacto_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (usuario_id, contacto_id),
        )
        return cursor.rowcount == 1

    def quitar_contacto(self, usuario_id: UUID, contacto_id: UUID) -> bool:
        """Saca la cuenta de la agenda; `False` si no estaba."""
        cursor = self._connection.execute(
            "DELETE FROM contactos WHERE usuario_id = %s AND contacto_id = %s",
            (usuario_id, contacto_id),
        )
        return cursor.rowcount == 1

    def contactos_de(self, usuario_id: UUID) -> Sequence[Usuario]:
        """Las cuentas que ese usuario agendó, por nombre de usuario."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            SELECT u.*
            FROM contactos c
            JOIN users u ON u.id = c.contacto_id
            WHERE c.usuario_id = %s
            ORDER BY u.username
            """,
            (usuario_id,),
        )
        return [_row_to_usuario(row) for row in cursor.fetchall()]

    def destinatarios_parecidos(
        self, texto: str, usuario_id: UUID, sin_contactos: bool, limite: int
    ) -> Sequence[str]:
        """Los nombres de las cuentas comunes aprobadas que contienen `texto`.

        Primero los que empiezan por el texto y después los que sólo lo contienen,
        cada grupo por nombre. Queda fuera la cuenta que pregunta y, con
        `sin_contactos`, las que ya agendó. Los comodines de `LIKE` del texto se
        escapan: un `%` tecleado busca un `%` y no todos los nombres.
        """
        patron = (
            normalizar_usuario(texto)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        filas = self._connection.execute(
            """
            SELECT u.username
            FROM users u
            WHERE u.role = %(rol)s
              AND u.estado = %(estado)s
              AND u.id <> %(usuario_id)s
              AND u.username LIKE '%%' || %(patron)s || '%%'
              AND NOT (%(sin_contactos)s AND EXISTS (
                  SELECT 1 FROM contactos c
                  WHERE c.usuario_id = %(usuario_id)s AND c.contacto_id = u.id
              ))
            ORDER BY u.username NOT LIKE %(patron)s || '%%', u.username
            LIMIT %(limite)s
            """,
            {
                "rol": USUARIO,
                "estado": APROBADO,
                "usuario_id": usuario_id,
                "patron": patron,
                "sin_contactos": sin_contactos,
                "limite": limite,
            },
        ).fetchall()
        return [username for (username,) in filas]

    def cambiar_hash(self, usuario_id: UUID, password_hash: str) -> bool:
        """Reemplaza el hash de la contraseña; `False` si la cuenta ya no existe."""
        cursor = self._connection.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, usuario_id),
        )
        return cursor.rowcount == 1

    def crear_solicitud(
        self, usuario_id: UUID, password_hash: str
    ) -> SolicitudDeContrasena:
        """Deja pendiente un cambio de contraseña y lo devuelve.

        El índice único parcial impide una segunda pendiente de la misma cuenta; esa
        violación se traduce a `SolicitudYaPendiente` y cualquier otra sube cruda.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        try:
            cursor.execute(
                """
                INSERT INTO solicitudes_de_contrasena (usuario_id, password_hash)
                VALUES (%s, %s)
                RETURNING id
                """,
                (usuario_id, password_hash),
            )
        except psycopg.errors.UniqueViolation as error:
            if error.diag.constraint_name != "uq_solicitudes_de_contrasena_una_pendiente":
                raise
            raise SolicitudYaPendiente(usuario_id) from error
        return self.solicitud(cursor.fetchone()["id"])

    def ultima_solicitud(self, usuario_id: UUID) -> SolicitudDeContrasena | None:
        """La solicitud más reciente de la cuenta, en cualquier estado."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            _SELECT_SOLICITUD + " WHERE s.usuario_id = %s ORDER BY s.creado_en DESC, s.id LIMIT 1",
            (usuario_id,),
        )
        row = cursor.fetchone()
        return _row_to_solicitud(row) if row is not None else None

    def solicitud(self, id: UUID) -> SolicitudDeContrasena | None:
        """La solicitud con ese identificador, o `None` si no existe."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(_SELECT_SOLICITUD + " WHERE s.id = %s", (id,))
        row = cursor.fetchone()
        return _row_to_solicitud(row) if row is not None else None

    def solicitudes_pendientes(self) -> Sequence[SolicitudDeContrasena]:
        """Las solicitudes que esperan al administrador, de la más antigua a la más nueva."""
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            _SELECT_SOLICITUD + " WHERE s.estado = %s ORDER BY s.creado_en, s.id",
            (PENDIENTE,),
        )
        return [_row_to_solicitud(row) for row in cursor.fetchall()]

    def resolver_solicitud(
        self, id: UUID, *, aprobada: bool, motivo: str | None = None
    ) -> SolicitudDeContrasena | None:
        """Aprueba o rechaza una solicitud pendiente; `None` si ya no lo estaba.

        Igual que la aprobación de cuentas, la condición `estado = 'pendiente'` va
        dentro del `UPDATE`: dos administradores no pueden resolverla dos veces.
        Al aprobar, el hash nuevo pasa a la cuenta en la misma transacción.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            UPDATE solicitudes_de_contrasena
            SET estado = %s, motivo_rechazo = %s, resuelto_en = NOW()
            WHERE id = %s AND estado = %s
            RETURNING usuario_id, password_hash
            """,
            (APROBADO if aprobada else RECHAZADO, motivo, id, PENDIENTE),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        if aprobada:
            self.cambiar_hash(row["usuario_id"], row["password_hash"])
        return self.solicitud(id)

    def guardar_foto(self, usuario_id: UUID, archivo: str, tipo: str) -> str | None:
        """Apunta la foto de la cuenta a ese archivo y devuelve el que tenía antes.

        El nombre anterior se lee en la misma sentencia, antes de reemplazarlo, para
        que quien llama pueda borrar ese archivo después de confirmar.
        """
        fila = self._connection.execute(
            """
            WITH anterior AS (
                SELECT archivo FROM fotos_de_perfil WHERE usuario_id = %s
            )
            INSERT INTO fotos_de_perfil (usuario_id, archivo, tipo)
            VALUES (%s, %s, %s)
            ON CONFLICT (usuario_id)
            DO UPDATE SET archivo = EXCLUDED.archivo, tipo = EXCLUDED.tipo,
                          actualizado_en = NOW()
            RETURNING (SELECT archivo FROM anterior)
            """,
            (usuario_id, usuario_id, archivo, tipo),
        ).fetchone()
        return fila[0]

    def quitar_foto(self, usuario_id: UUID) -> str | None:
        """Borra la referencia a la foto y devuelve el archivo; `None` si no tenía."""
        fila = self._connection.execute(
            "DELETE FROM fotos_de_perfil WHERE usuario_id = %s RETURNING archivo",
            (usuario_id,),
        ).fetchone()
        return fila[0] if fila is not None else None

    def foto_de(self, username: str) -> FotoDePerfil | None:
        """La referencia a la foto de la cuenta con ese nombre, o `None` si no tiene."""
        fila = self._connection.execute(
            """
            SELECT f.archivo, f.tipo, f.actualizado_en
            FROM fotos_de_perfil f
            JOIN users u ON u.id = f.usuario_id
            WHERE lower(u.username) = %s
            """,
            (normalizar_usuario(username),),
        ).fetchone()
        if fila is None:
            return None
        archivo, tipo, actualizado_en = fila
        return FotoDePerfil(archivo=archivo, tipo=tipo, actualizado_en=actualizado_en)

    def fotos_por_nombre(self) -> dict[str, FotoDePerfil]:
        """La foto de cada cuenta que tiene una, por nombre de usuario.

        Es lo que necesita una página para decidir, sin traer los bytes, a quién
        pintar con foto y a quién con su inicial. Devuelve la referencia completa
        —archivo, tipo y fecha— y no sólo la fecha, porque quien decide si sirve
        es el servicio: una fila cuyo archivo ya no está en la carpeta no se pinta.
        """
        filas = self._connection.execute(
            """
            SELECT u.username, f.archivo, f.tipo, f.actualizado_en
            FROM fotos_de_perfil f
            JOIN users u ON u.id = f.usuario_id
            """
        ).fetchall()
        return {
            username: FotoDePerfil(archivo=archivo, tipo=tipo, actualizado_en=actualizado_en)
            for username, archivo, tipo, actualizado_en in filas
        }
