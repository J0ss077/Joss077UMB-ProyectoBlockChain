"""REQ-15: el esquema no lo decide el código.

Aquí viven las dos comprobaciones del requisito: que ninguna ruta del código
contiene sentencias de definición de datos, y que el esquema que sí se aplica
—el de `db/init.sql`— tiene las cuatro tablas del modelo —las tres del eje y
`users`— y el índice único sobre `transactions.signature` de la decisión 4.
"""
import pathlib
import re

import psycopg
import pytest
from psycopg.rows import dict_row


def columnas_de(conexion, tabla: str) -> set[str]:
    """Columnas de una tabla del esquema público, leídas del catálogo."""
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (tabla,),
        )
        return {fila["column_name"] for fila in cursor.fetchall()}


def indices_y_restricciones(conexion, tabla: str) -> set[str]:
    """Nombres de las restricciones y los índices de una tabla del esquema público.

    Se miran las dos fuentes porque un `UNIQUE` deja restricción e índice con el
    mismo nombre, mientras que un `CHECK` solo vive en `pg_constraint`: el conjunto
    tiene que cubrir las dos clases para que la prueba no dependa de cuál es cuál.
    """
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT conname AS nombre
            FROM pg_constraint
            WHERE conrelid = to_regclass(%s)
            """,
            (f"public.{tabla}",),
        )
        nombres = {fila["nombre"] for fila in cursor.fetchall()}
        cursor.execute(
            """
            SELECT indexname AS nombre
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
            """,
            (tabla,),
        )
        nombres |= {fila["nombre"] for fila in cursor.fetchall()}
    return nombres


def test_req_15_no_hay_ddl_en_el_codigo():
    """Ninguna ruta del código contiene sentencias de definición de datos."""
    patron = re.compile(
        r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|EXTENSION|SCHEMA)\b", re.IGNORECASE
    )
    ofensores = [
        str(ruta)
        for ruta in pathlib.Path("src").rglob("*.py")
        if patron.search(ruta.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_req_15_el_esquema_aplicado_tiene_las_cuatro_tablas_y_el_indice_unico(
    conexion, base_limpia
):
    """El esquema aplicado tiene las cuatro tablas y `signature` es única."""
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        tablas = {fila["table_name"] for fila in cursor.fetchall()}
    assert tablas == {"wallets", "blocks", "transactions", "users"}

    # El catálogo se consulta en vez de reaplicar `db/init.sql`: reaplicarlo
    # sería DDL desde la prueba, que es justo lo que REQ-15 prohíbe.
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'transactions'
              AND indexdef ILIKE '%unique%'
              AND indexdef ILIKE '%(signature)%'
            """
        )
        indices_unicos = cursor.fetchall()
    assert len(indices_unicos) == 1, "hace falta el índice único sobre transactions.signature"


def test_req_30_el_esquema_tiene_la_tabla_de_usuarios(conexion):
    """REQ-30: la tabla `users` existe con sus restricciones."""
    columnas = columnas_de(conexion, "users")
    assert set(columnas) == {"id", "username", "password_hash", "role", "estado",
                             "motivo_rechazo", "wallet_id", "creado_en", "aprobado_en"}
    assert indices_y_restricciones(conexion, "users") >= {
        "users_username_key",
        "users_username_minusculas",
        "users_wallet_id_key",
        "users_role_check",
        "users_estado_check",
        "chk_users_motivo_rechazo_requerido",
        "chk_users_wallet_coherente_con_el_estado",
    }


def test_req_31_un_rechazado_puede_quedarse_sin_wallet(conexion, base_limpia):
    """REQ-31: el rechazo guarda el motivo y deja al usuario sin wallet.

    Es la regresión del CHECK: si se lo vuelve a escribir contra `pendiente`, el
    rechazado queda obligado a tener wallet y esta inserción falla.
    """
    try:
        fila = conexion.execute(
            """
            INSERT INTO users (username, password_hash, role, estado, motivo_rechazo)
            VALUES ('rechazado_sin_wallet', 'hash', 'usuario', 'rechazado', 'no corresponde')
            RETURNING wallet_id
            """
        ).fetchone()
        assert fila[0] is None
    finally:
        conexion.execute("DELETE FROM users WHERE username = 'rechazado_sin_wallet'")


def test_req_30_un_administrador_aprobado_puede_quedarse_sin_wallet(
    conexion, base_limpia
):
    """REQ-30: el administrador sembrado se admite aprobado y sin wallet.

    Es la corrección del CHECK: la bicondicional contra `aprobado` obligaba a que
    toda cuenta aprobada tuviera wallet, y el administrador del diseño no la tiene
    (decisión 4 y §6). La fila se escribe por fuera del repositorio porque lo que
    se mide es el esquema, no el camino del alta.
    """
    try:
        fila = conexion.execute(
            """
            INSERT INTO users (username, password_hash, role, estado)
            VALUES ('admin_sin_wallet', 'hash', 'administrador', 'aprobado')
            RETURNING wallet_id, aprobado_en
            """
        ).fetchone()
        assert fila[0] is None
    finally:
        conexion.execute("DELETE FROM users WHERE username = 'admin_sin_wallet'")


def test_req_30_un_usuario_comun_aprobado_sin_wallet_sigue_prohibido(
    conexion, base_limpia
):
    """REQ-30: un aprobado común sin wallet sigue violando el CHECK del esquema.

    La corrección distingue por rol; no afloja la regla que REQ-33 necesita: la
    aprobación de una persona común crea su wallet en la misma operación.
    """
    with pytest.raises(psycopg.errors.CheckViolation) as error:
        conexion.execute(
            """
            INSERT INTO users (username, password_hash, role, estado)
            VALUES ('comun_sin_wallet', 'hash', 'usuario', 'aprobado')
            """
        )
    assert (
        error.value.diag.constraint_name
        == "chk_users_wallet_coherente_con_el_estado"
    )
