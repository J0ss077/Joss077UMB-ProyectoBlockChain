"""REQ-30 y REQ-31: el modelo de usuario y su repositorio sobre PostgreSQL.

La tabla `users` es del esquema y estas pruebas no la crean: cada una pide
`base_limpia` y escribe por el repositorio, salvo las que provocan a propósito una
violación del motor para comprobar que la base también impide el dato inválido
cuando se escribe por fuera de la aplicación. La conexión de la sesión está en
autocommit, así que lo escrito se ve desde la siguiente sentencia.

El nombre se guarda y se busca normalizado: el repositorio normaliza por su
cuenta, de modo que ningún llamador pueda saltarse la regla de REQ-30.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from src.accounts.credentials import hashear_contrasena
from src.accounts.model import (
    APROBADO,
    PENDIENTE,
    RECHAZADO,
    USUARIO,
    Usuario,
    UsuarioDuplicado,
)
from src.accounts.postgres import PostgresAccountsRepository
from src.persistence.factory import database_url
from src.persistence.unit_of_work import PostgresUnitOfWork

# Fecha fija del alta: el orden de `list_pendientes` se mide sobre `creado_en`, y
# fijarla hace que el resultado no dependa del reloj de la corrida.
CREADO_EN = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
# El hash se calcula una vez: el repositorio no lo interpreta, y repetir scrypt en
# cada fábrica sólo agregaría tiempo a una prueba que mide persistencia.
HASH = hashear_contrasena("secreta1")

# La sentencia directa que la aplicación no usa: sirve para comprobar que la base,
# y no solo el repositorio, impide dos nombres que difieren sólo en la caja.
INSERT_DIRECTO = (
    "INSERT INTO users (username, password_hash, role, estado) "
    "VALUES (%s, %s, 'usuario', 'pendiente')"
)


def usuario_nuevo(username: str, *, creado_en: datetime = CREADO_EN) -> Usuario:
    """Una cuenta pendiente, sin wallet, lista para que el repositorio la escriba."""
    return Usuario(
        id=uuid4(),
        username=username,
        password_hash=HASH,
        role=USUARIO,
        estado=PENDIENTE,
        motivo_rechazo=None,
        wallet_id=None,
        creado_en=creado_en,
        aprobado_en=None,
    )


@pytest.fixture
def usuarios(conexion) -> PostgresAccountsRepository:
    """El repositorio de usuarios contra la conexión de la sesión."""
    return PostgresAccountsRepository(conexion)


def test_req_30_el_registro_deja_la_fila_pendiente_sin_wallet(usuarios, base_limpia):
    """REQ-30: la fila existe con `estado = 'pendiente'` y sin wallet."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    fila = usuarios.get_by_username("ana")
    assert fila is not None
    assert fila.estado == PENDIENTE
    assert fila.wallet_id is None
    assert fila.aprobado_en is None
    assert fila.motivo_rechazo is None
    assert fila.id == creado.id
    assert usuarios.get(creado.id) == creado
    assert usuarios.count() == 1


def test_req_30_el_nombre_es_unico_sin_distinguir_mayusculas(usuarios, base_limpia):
    """REQ-30: un usuario repetido se rechaza con `UsuarioDuplicado`, no con el driver."""
    usuarios.add_pendiente(usuario_nuevo("ana"))

    with pytest.raises(UsuarioDuplicado):
        usuarios.add_pendiente(usuario_nuevo("ANA"))
    assert usuarios.count() == 1


def test_req_30_el_repositorio_normaliza_el_nombre_al_escribir_y_al_buscar(
    usuarios, base_limpia
):
    """REQ-30: el nombre se guarda y se busca normalizado aunque el llamador no lo haga."""
    creado = usuarios.add_pendiente(usuario_nuevo("  ANA  "))

    assert creado.username == "ana"
    assert usuarios.get_by_username("ANA").id == creado.id
    assert usuarios.get_by_username("  Ana ").id == creado.id
    assert usuarios.get_by_username("ana").id == creado.id


def test_req_30_el_esquema_rechaza_dos_nombres_que_solo_difieren_en_la_caja(
    conexion, base_limpia
):
    """REQ-30: la base impide `ana` y `ANA` aunque se escriba por fuera del repositorio."""
    conexion.execute(INSERT_DIRECTO, ("ana", HASH))

    with pytest.raises(psycopg.errors.UniqueViolation) as error:
        conexion.execute(INSERT_DIRECTO, ("ANA", HASH))
    assert error.value.diag.constraint_name == "users_username_minusculas"


def test_req_31_aprobar_liga_la_wallet_y_cambia_el_estado(
    usuarios, base_limpia, emisora
):
    """REQ-31: al aprobar, el estado pasa a `aprobado` y queda ligada la wallet."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    aprobado = usuarios.aprobar(creado.id, emisora.id)

    assert aprobado is not None
    assert aprobado.estado == APROBADO
    assert aprobado.wallet_id == emisora.id
    assert aprobado.aprobado_en is not None
    assert usuarios.get(creado.id) == aprobado
    assert usuarios.list_pendientes() == []


def test_req_31_aprobar_con_una_wallet_inexistente_no_cambia_el_estado(
    usuarios, base_limpia
):
    """REQ-31: estado y wallet se mueven juntos; si la wallet no existe, no queda nada."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        usuarios.aprobar(creado.id, uuid4())

    fila = usuarios.get(creado.id)
    assert fila.estado == PENDIENTE
    assert fila.wallet_id is None
    assert fila.aprobado_en is None


def test_req_31_una_segunda_aprobacion_no_vuelve_a_escribir(
    usuarios, base_limpia, emisora, receptora
):
    """REQ-31: aprobar dos veces no reemplaza la wallet ni repite la escritura."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))
    primera = usuarios.aprobar(creado.id, emisora.id)

    assert usuarios.aprobar(creado.id, receptora.id) is None
    assert usuarios.get(creado.id) == primera
    assert usuarios.get(creado.id).wallet_id == emisora.id


def test_req_31_rechazar_guarda_el_motivo_y_el_esquema_no_lo_admite_vacio(
    usuarios, conexion, base_limpia
):
    """REQ-31: al rechazar se guarda el motivo; una fila rechazada sin motivo viola el CHECK.

    El estado queda en `rechazado`, sin wallet y sin fecha de aprobación. Después
    se intenta dejar el motivo en nulo por fuera del repositorio, que es la forma
    de comprobar que el esquema —y no solo la aplicación— exige el motivo.
    """
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    rechazado = usuarios.rechazar(creado.id, "documentación incompleta")

    assert rechazado is not None
    assert rechazado.estado == RECHAZADO
    assert rechazado.motivo_rechazo == "documentación incompleta"
    assert rechazado.wallet_id is None
    assert rechazado.aprobado_en is None
    with pytest.raises(psycopg.errors.CheckViolation):
        conexion.execute(
            "UPDATE users SET motivo_rechazo = NULL WHERE id = %s", (creado.id,)
        )
    assert usuarios.get(creado.id).motivo_rechazo == "documentación incompleta"


def test_req_31_list_pendientes_trae_solo_los_pendientes_y_en_orden(
    usuarios, base_limpia, emisora
):
    """REQ-31: la lista de pendientes excluye aprobados y rechazados y va por fecha de alta."""
    segunda = usuarios.add_pendiente(
        usuario_nuevo("beto", creado_en=CREADO_EN + timedelta(minutes=1))
    )
    primera = usuarios.add_pendiente(usuario_nuevo("ana"))
    aprobada = usuarios.add_pendiente(
        usuario_nuevo("carla", creado_en=CREADO_EN + timedelta(minutes=2))
    )
    rechazada = usuarios.add_pendiente(
        usuario_nuevo("dora", creado_en=CREADO_EN + timedelta(minutes=3))
    )
    usuarios.aprobar(aprobada.id, emisora.id)
    usuarios.rechazar(rechazada.id, "no corresponde")

    pendientes = usuarios.list_pendientes()

    assert [usuario.username for usuario in pendientes] == ["ana", "beto"]
    assert [usuario.id for usuario in pendientes] == [primera.id, segunda.id]


def test_req_18_la_unidad_de_trabajo_expone_los_usuarios_sobre_su_conexion(
    conexion, base_limpia
):
    """REQ-18: `usuarios` y `connection` comparten la transacción que la unidad cierra."""
    with PostgresUnitOfWork.open(database_url()) as unidad:
        unidad.usuarios.add_pendiente(usuario_nuevo("ana"))
        # Se lee por la propiedad `connection` antes del commit: la fila está en la
        # misma transacción porque es la misma conexión, no otra abierta por el
        # repositorio.
        assert unidad.connection.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        unidad.commit()

    assert conexion.execute("SELECT count(*) FROM users").fetchone()[0] == 1
