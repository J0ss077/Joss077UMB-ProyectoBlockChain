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
from src.domain.wallet import create_wallet
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
    """Una cuenta pendiente, lista para que el repositorio la escriba.

    La cuenta no lleva wallet: la propiedad vive en `wallets.owner_id` y una
    aprobación le asigna la suya recién en el servicio (REQ-33).
    """
    return Usuario(
        id=uuid4(),
        username=username,
        password_hash=HASH,
        role=USUARIO,
        estado=PENDIENTE,
        motivo_rechazo=None,
        creado_en=creado_en,
        aprobado_en=None,
    )


@pytest.fixture
def usuarios(conexion) -> PostgresAccountsRepository:
    """El repositorio de usuarios contra la conexión de la sesión."""
    return PostgresAccountsRepository(conexion)


def test_req_30_el_registro_deja_la_fila_pendiente_sin_wallet(usuarios, base_limpia):
    """REQ-30: la fila existe pendiente y la cuenta no es dueña de ninguna wallet."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    fila = usuarios.get_by_username("ana")
    assert fila is not None
    assert fila.estado == PENDIENTE
    assert usuarios.wallets_de(creado.id) == []
    assert usuarios.wallet_principal(creado.id) is None
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


def test_req_31_aprobar_cambia_el_estado_y_no_liga_wallet(usuarios, base_limpia):
    """REQ-31: al aprobar, el estado pasa a `aprobado`; la wallet la liga el servicio.

    El repositorio ya no recibe una wallet: la propiedad vive en `wallets.owner_id`
    y la aprobación de REQ-33 la asigna en la misma transacción del servicio.
    """
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))

    aprobado = usuarios.aprobar(creado.id)

    assert aprobado is not None
    assert aprobado.estado == APROBADO
    assert aprobado.aprobado_en is not None
    assert usuarios.get(creado.id) == aprobado
    assert usuarios.list_pendientes() == []
    assert usuarios.wallets_de(creado.id) == []


def test_req_46_el_repositorio_asigna_solo_wallets_sin_dueno(
    usuarios, base_limpia, emisora, receptora
):
    """REQ-46: `asignar_wallet` liga una wallet libre y no reemplaza a un dueño.

    Devuelve `False` si la wallet ya tiene dueño o no existe, y deja la primera
    asignación intacta: la propiedad no se puede pisar por accidente.
    """
    ana = usuarios.add_pendiente(usuario_nuevo("ana"))
    beto = usuarios.add_pendiente(usuario_nuevo("beto"))
    usuarios.aprobar(ana.id)
    usuarios.aprobar(beto.id)

    assert usuarios.asignar_wallet(emisora.id, ana.id) is True
    assert usuarios.wallets_de(ana.id) == [emisora.id]
    assert usuarios.wallet_principal(ana.id) == emisora.id
    assert usuarios.asignar_wallet(emisora.id, beto.id) is False
    assert usuarios.asignar_wallet(uuid4(), beto.id) is False
    assert usuarios.wallets_de(beto.id) == []


def test_req_46_list_aprobados_trae_solo_las_cuentas_comunes_aprobadas_por_nombre(
    usuarios, conexion, base_limpia
):
    """REQ-46: el selector de dueño lista las cuentas comunes aprobadas por nombre.

    Quedan fuera el administrador —no puede ser dueño—, las pendientes y las
    rechazadas, y el orden es el del nombre para que el selector sea estable.
    """
    usuarios.add_pendiente(usuario_nuevo("beto"))
    carla = usuarios.add_pendiente(usuario_nuevo("carla"))
    usuarios.aprobar(carla.id)
    ana = usuarios.add_pendiente(usuario_nuevo("ana"))
    usuarios.aprobar(ana.id)
    dora = usuarios.add_pendiente(usuario_nuevo("dora"))
    usuarios.rechazar(dora.id, "no corresponde")
    conexion.execute(
        """
        INSERT INTO users (username, password_hash, role, estado)
        VALUES ('adminx', 'hash', 'administrador', 'aprobado')
        """
    )

    assert [usuario.username for usuario in usuarios.list_aprobados()] == [
        "ana",
        "carla",
    ]


def test_req_47_las_wallets_de_la_cuenta_van_de_la_mas_antigua_a_la_mas_nueva(
    usuarios, wallets, base_limpia, master_key
):
    """REQ-47: `wallets_de` ordena por antigüedad y `wallet_principal` da la primera.

    El orden no es el de inserción: se asignan en orden inverso para que la prueba
    mida el `ORDER BY created_at, id` del repositorio y no el azar del alta.
    """
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))
    usuarios.aprobar(creado.id)
    antigua = wallets.add(
        create_wallet(master_key=master_key, created_at=CREADO_EN)
    )
    nueva = wallets.add(
        create_wallet(
            master_key=master_key, created_at=CREADO_EN + timedelta(minutes=1)
        )
    )
    assert usuarios.asignar_wallet(nueva.id, creado.id) is True
    assert usuarios.asignar_wallet(antigua.id, creado.id) is True

    assert usuarios.wallets_de(creado.id) == [antigua.id, nueva.id]
    assert usuarios.wallet_principal(creado.id) == antigua.id


def test_req_31_una_segunda_aprobacion_no_vuelve_a_escribir(
    usuarios, base_limpia
):
    """REQ-31: aprobar dos veces no repite la escritura."""
    creado = usuarios.add_pendiente(usuario_nuevo("ana"))
    primera = usuarios.aprobar(creado.id)

    assert usuarios.aprobar(creado.id) is None
    assert usuarios.get(creado.id) == primera


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
    assert usuarios.wallets_de(creado.id) == []
    assert rechazado.aprobado_en is None
    with pytest.raises(psycopg.errors.CheckViolation):
        conexion.execute(
            "UPDATE users SET motivo_rechazo = NULL WHERE id = %s", (creado.id,)
        )
    assert usuarios.get(creado.id).motivo_rechazo == "documentación incompleta"


def test_req_31_list_pendientes_trae_solo_los_pendientes_y_en_orden(
    usuarios, base_limpia
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
    usuarios.aprobar(aprobada.id)
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
