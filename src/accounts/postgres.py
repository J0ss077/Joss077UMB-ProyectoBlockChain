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
# los dos; cualquier otra violación de unicidad sube sin traducir.
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
        Cualquier otra violación de unicidad sube sin traducir.
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

        El estado, el motivo y la fecha de aprobación se escriben fijos: una
        cuenta que nace no puede estar aprobada, y dejar esos campos en manos del
        llamador permitiría una fila que el alta moderada no contempla. La cuenta
        nace sin wallet: la propiedad vive en `wallets.owner_id`. El nombre se
        normaliza acá.
        """
        username = normalizar_usuario(usuario.username)
        return self._insertar(
            """
            INSERT INTO users (
                id, username, password_hash, role, estado,
                motivo_rechazo, creado_en, aprobado_en
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s, NULL)
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
        """Escribe una fila ya aprobada o rechazada (semilla).

        El alta normal pasa por `add_pendiente` y `aprobar`; este camino existe
        para que el arranque deje las cuentas de demostración en el estado que la
        convención fija sin pasar por el alta moderada, que nadie va a aprobar. La
        fila la decide el llamador porque la semilla no es un alta, pero el
        esquema sigue siendo el que impide una combinación inválida. La wallet no
        se escribe acá: el arranque la asigna después con `asignar_wallet`. El
        nombre se normaliza y la violación de unicidad se traduce igual que en el
        registro.
        """
        username = normalizar_usuario(usuario.username)
        return self._insertar(
            """
            INSERT INTO users (
                id, username, password_hash, role, estado,
                motivo_rechazo, creado_en, aprobado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                usuario.id,
                username,
                usuario.password_hash,
                usuario.role,
                usuario.estado,
                usuario.motivo_rechazo,
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

    def list_aprobados(self) -> Sequence[Usuario]:
        """Las cuentas comunes aprobadas, por nombre de usuario (REQ-46).

        Es la lista del selector de dueño: sólo una cuenta común aprobada puede
        ser dueña de una wallet (diseño de wallet con dueño, §2). El administrador
        queda fuera por su rol.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            SELECT * FROM users
            WHERE role = %s AND estado = %s
            ORDER BY username
            """,
            (USUARIO, APROBADO),
        )
        return [_row_to_usuario(row) for row in cursor.fetchall()]

    def nombres_por_wallet(self) -> dict[UUID, str]:
        """El nombre de usuario de cada wallet que tiene dueño.

        La relación vive en `wallets.owner_id`, así que el mapa sale del JOIN de
        las dos tablas. Las wallets sin dueño —las que el administrador registra
        sin asignar— no aparecen (REQ-46).
        """
        filas = self._connection.execute(
            """
            SELECT w.id, u.username
            FROM wallets w
            JOIN users u ON u.id = w.owner_id
            """
        ).fetchall()
        return {wallet_id: username for wallet_id, username in filas}

    def wallets_de(self, usuario_id: UUID) -> Sequence[UUID]:
        """Identificadores de las wallets de la cuenta, de la más antigua a la más nueva (REQ-47).

        El orden es `created_at, id`: la primera es la principal. Una cuenta común
        aprobada puede tener ninguna, una o varias wallets.
        """
        filas = self._connection.execute(
            """
            SELECT id FROM wallets
            WHERE owner_id = %s
            ORDER BY created_at, id
            """,
            (usuario_id,),
        ).fetchall()
        return [wallet_id for (wallet_id,) in filas]

    def wallet_principal(self, usuario_id: UUID) -> UUID | None:
        """La wallet más antigua de la cuenta, o `None` si no tiene ninguna (REQ-34).

        Es la que resuelve el envío por nombre de usuario: las demás se
        direccionan por su identificador (diseño de wallet con dueño, decisión 6).
        """
        fila = self._connection.execute(
            """
            SELECT id FROM wallets
            WHERE owner_id = %s
            ORDER BY created_at, id
            LIMIT 1
            """,
            (usuario_id,),
        ).fetchone()
        return fila[0] if fila is not None else None

    def asignar_wallet(self, wallet_id: UUID, usuario_id: UUID) -> bool:
        """Le pone dueño a una wallet sin dueño; `False` si no existe o ya lo tiene (REQ-46).

        La condición `owner_id IS NULL` viaja dentro del mismo `UPDATE`: el dueño
        queda fijo y dos asignaciones simultáneas no pueden reemplazarlo. La
        validez del dueño la comprueba el servicio, que es el único que conoce la
        regla de rol y estado.
        """
        cursor = self._connection.execute(
            "UPDATE wallets SET owner_id = %s WHERE id = %s AND owner_id IS NULL",
            (usuario_id, wallet_id),
        )
        return cursor.rowcount == 1

    def aprobar(self, id: UUID) -> Usuario | None:
        """Pasa la cuenta a `aprobado` en una sola escritura (REQ-31).

        La condición `estado = 'pendiente'` viaja dentro del mismo `UPDATE`: dos
        aprobaciones simultáneas no pueden aprobar dos veces, y una cuenta que ya
        no está pendiente devuelve `None` sin escribir. La wallet de bienvenida y
        su dueño los liga el servicio en la misma transacción (REQ-33). La fecha
        de aprobación la pone el reloj de la base.
        """
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.execute(
            """
            UPDATE users
            SET estado = %s, aprobado_en = NOW()
            WHERE id = %s AND estado = %s
            RETURNING *
            """,
            (APROBADO, id, PENDIENTE),
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
