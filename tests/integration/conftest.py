"""Fixtures de las pruebas de integración: una conexión viva, una base limpia y
los datos que casi todas las pruebas de adaptadores necesitan.

El esquema se aplica con `db/init.sql` sobre el contenedor o sobre el clúster
nativo del equipo, así que estas pruebas no crean ni modifican tablas: solo
borran filas. La configuración del entorno la lee `src/persistence/factory.py`,
que es también quien arma la fachada: las pruebas y la aplicación no pueden
leer cosas distintas de `.env`.
"""
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from flask import Flask
from flask.testing import FlaskClient

from src.accounts.credentials import hashear_contrasena
from src.accounts.model import ADMINISTRADOR, PENDIENTE, Usuario
from src.accounts.postgres import PostgresAccountsRepository
from src.accounts.service import Cuentas
from src.bootstrap import wallet_del_constituyente
from src.domain.block import Block
from src.domain.blockchain import Blockchain, ensure_genesis
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import Wallet, create_wallet, sign_payload
from src.persistence.factory import database_url, open_ledger, session_secret, transaction
from src.persistence.factory import master_key as master_key_from_env
from src.persistence.ports import BlockRepository, WalletRepository
from src.persistence.postgres import PostgresBlockRepository, PostgresWalletRepository
from src.web.app import create_app

# Marca de tiempo fija: el payload firmado la incluye, y fijarla hace
# reproducibles las transacciones que arman las pruebas.
CREATED_AT = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
# Reloj fijo de la fachada: las marcas de tiempo de los bloques que producen las
# pruebas quedan fuera del reloj de pared y el hash del bloque no cambia entre
# corridas.
BLOCK_AT = datetime(2026, 10, 10, 13, 0, tzinfo=UTC)
DEFAULT_AMOUNT = Decimal("10.00000000")

# Contraseñas de las cuentas que siembran las pruebas de la sesión. Son constantes
# y no las del entorno porque el administrador de estas pruebas no es el de la
# semilla de la Task 9: acá se crea directo con el repositorio.
CONTRASENA_DE_PRUEBA = "secreta1"
CONTRASENA_DEL_ADMINISTRADOR = "clave-del-administrador-de-prueba"


def crear_app_de_prueba(chain_factory, *, secret_key=None) -> Flask:
    """Arma la aplicación con la fábrica del ledger y la del servicio de cuentas.

    La fábrica de cuentas se compone acá, con `transaction()` real, para que las
    rutas de entrada y la recarga del usuario por petición usen la misma base que
    el resto de la suite. La clave de la sesión sale del entorno por el mismo
    lector que usa el arranque, así la prueba firma con la clave de verdad.
    """

    @contextmanager
    def fabrica_de_cuentas():
        yield Cuentas(transaction)

    return create_app(
        chain_factory,
        fabrica_de_cuentas,
        secret_key=session_secret() if secret_key is None else secret_key,
    )


def ingresar_como(cliente, usuario: str, contrasena: str):
    """Ingresa con esas credenciales y exige que la sesión se haya abierto.

    Se usa en las pruebas de rutas para dejar al cliente como administrador. Un
    ingreso fallido devuelve 200 con el motivo, así que un 302 es la señal de que
    la cookie quedó puesta.
    """
    respuesta = cliente.post(
        "/ingresar", data={"usuario": usuario, "contrasena": contrasena}
    )
    assert respuesta.status_code == 302, respuesta.get_data(as_text=True)
    return respuesta


def _sembrar_cuenta(
    conexion,
    *,
    username: str,
    role: str,
    contrasena: str,
    wallet_id=None,
) -> Usuario:
    """Crea una cuenta aprobada directo en la base, sin pasar por el servicio.

    El servicio siempre registra el rol `usuario`, así que el administrador sólo
    puede nacer por el repositorio. El camino del alta (`aprobar`) liga una wallet,
    así que se le pasa una aunque el esquema ya no se la exija al administrador:
    la corrección del CHECK distingue por rol, no obliga a que la tenga.
    """
    usuarios = PostgresAccountsRepository(conexion)
    pendiente = usuarios.add_pendiente(
        Usuario(
            id=uuid4(),
            username=username,
            password_hash=hashear_contrasena(contrasena),
            role=role,
            estado=PENDIENTE,
            motivo_rechazo=None,
            wallet_id=None,
            creado_en=datetime.now(UTC),
            aprobado_en=None,
        )
    )
    aprobado = usuarios.aprobar(pendiente.id, wallet_id)
    assert aprobado is not None
    return aprobado


@pytest.fixture(scope="session")
def conexion():
    """Conexión abierta a la base del entorno, en UTC y sin cierre automático por sentencia.

    El alcance es de sesión porque PostgreSQL es un recurso caro de abrir por
    prueba; la limpieza de filas la hace `base_limpia` antes de cada una. La
    comprobación de `DATABASE_URL` vive aquí dentro y no en el módulo: las
    pruebas sin base no pueden arrastrar la exigencia de conexión.
    """
    with psycopg.connect(database_url(), autocommit=True) as connection:
        connection.execute("SET TIME ZONE 'UTC'")
        yield connection


@pytest.fixture
def base_limpia(conexion):
    """Vacía las cuatro tablas antes de cada prueba, en orden inverso a las claves foráneas.

    `users` va antes que `wallets` porque `users.wallet_id` la referencia con
    `ON DELETE RESTRICT`: al revés, la limpieza fallaría en cuanto hubiera una
    cuenta aprobada. Se borra con `DELETE` y no con `TRUNCATE`: `TRUNCATE` es DDL y
    REQ-15 lo prohíbe desde las pruebas. No es `autouse` a propósito: una prueba sin
    base (REQ-15 y REQ-21) no debe arrastrar la conexión y, con ella, la exigencia
    de `DATABASE_URL`; cada prueba que toca la base lo pide.
    """
    conexion.execute("DELETE FROM transactions")
    conexion.execute("DELETE FROM blocks")
    conexion.execute("DELETE FROM users")
    conexion.execute("DELETE FROM wallets")
    yield


@pytest.fixture
def master_key():
    """Clave Fernet del entorno; los adaptadores solo guardan su resultado cifrado."""
    return master_key_from_env()


@pytest.fixture
def ledger(conexion, base_limpia, master_key) -> Blockchain:
    """La fachada del ledger sobre la conexión de la sesión, con el génesis asegurado.

    Se pide `base_limpia` aquí para que la cadena arranque sobre tablas vacías: el
    génesis que se asegura es el único bloque que las demás pruebas pueden dar por
    sentado. Las lecturas usan la conexión de la sesión para que las aserciones y
    lo que las pruebas escriben hablen de las mismas filas; la agrupación abre su
    propia transacción de base de datos (REQ-18).
    """
    chain = open_ledger(conexion, encryption_key=master_key, clock=lambda: BLOCK_AT)
    ensure_genesis(chain)
    return chain


@pytest.fixture
def cuentas(ledger, master_key) -> Cuentas:
    """El servicio de cuentas real, con el constituyente ya registrado.

    `Cuentas` abre cada operación con `factory.transaction()`, una conexión
    propia; el ledger de la sesión siembra y lee lo confirmado. El constituyente
    tiene que existir porque la aprobación emite desde él (REQ-33); el ledger de
    la sesión lo ve apenas se escribe porque está en autocommit.
    """
    ledger.wallets.add(wallet_del_constituyente(master_key))
    return Cuentas(transaction)


@pytest.fixture
def base_vacia_ejecutando_bootstrap(conexion, base_limpia, master_key) -> Blockchain:
    """Base vacía, el arranque corrido como se corre de verdad, y la fachada para leer.

    El arranque se ejecuta en un subproceso porque su contrato es el punto de
    entrada (`python -m src.bootstrap`) y no una función interna: así las pruebas
    cubren el mismo camino que usa el equipo. Después se abre la fachada sobre la
    conexión de la sesión para poder consultar lo que el subproceso dejó escrito.
    """
    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)
    return open_ledger(conexion, encryption_key=master_key)


@pytest.fixture
def pendientes(ledger, transaccion):
    """Fábrica de transacciones pendientes ya escritas en el pool.

    Se escriben con el repositorio y no con `create_transaction` porque agrupar no
    vuelve a mirar el saldo: lo que REQ-09 mide es que las del pool queden
    confirmadas y ligadas al bloque (CU-03), no cómo llegaron al pool.
    """

    def build(count: int = 1) -> list[Transaction]:
        return [ledger.transactions.add(transaccion()) for _ in range(count)]

    return build


@pytest.fixture
def transaccion(master_key, emisora, receptora):
    """Fábrica de transacciones pendientes, firmadas por la emisora y listas para escribir.

    Las dos wallets ya están en la base, así que las claves foráneas se cumplen.
    La firma se calcula aquí con la privada de la emisora porque es el camino
    real: la transacción nace firmada y el `add` no vuelve a firmarla. La fábrica
    no escribe nada; de eso se encarga el repositorio.
    """

    def build(
        *,
        sender: Wallet | None = None,
        receiver: Wallet | None = None,
        status: TransactionStatus = TransactionStatus.PENDING,
        block_id: UUID | None = None,
        amount: Decimal = DEFAULT_AMOUNT,
        created_at: datetime = CREATED_AT,
        transaction_id: UUID | None = None,
    ) -> Transaction:
        emisor = sender if sender is not None else emisora
        destino = receiver if receiver is not None else receptora
        transaction = Transaction(
            id=transaction_id if transaction_id is not None else uuid4(),
            sender_id=emisor.id,
            receiver_id=destino.id,
            amount=amount,
            status=status,
            signature="",
            block_id=block_id,
            created_at=created_at,
        )
        transaction.signature = sign_payload(
            emisor, transaction.signing_payload(emisor.public_key, destino.public_key), master_key
        )
        return transaction

    return build


@pytest.fixture
def wallets(conexion) -> WalletRepository:
    """El repositorio de wallets contra la conexión de la sesión."""
    return PostgresWalletRepository(conexion)


@pytest.fixture
def emisora(wallets, master_key) -> Wallet:
    """Wallet emisora ya registrada en la base, para que las claves foráneas existan."""
    return wallets.add(create_wallet(master_key=master_key))


@pytest.fixture
def receptora(wallets, master_key) -> Wallet:
    """Wallet receptora ya registrada en la base."""
    return wallets.add(create_wallet(master_key=master_key))


@pytest.fixture
def bloques(conexion) -> BlockRepository:
    """El repositorio de bloques contra la conexión de la sesión."""
    return PostgresBlockRepository(conexion)


@pytest.fixture
def bloque(bloques):
    """Fábrica de bloques ya escritos, distintos entre sí por índice y por hash.

    El hash lo calcula `Block.calculate_hash`, la misma función que usa la
    aplicación: con una fórmula paralela, una prueba que combinara estos bloques con
    la verificación señalaría una alteración que nadie hizo.

    El `id` se genera en la aplicación, no con el valor por defecto del esquema,
    porque el camino real conoce el `id` antes de escribir (decisión 5).
    """

    def build(block_index: int = 0, previous_hash: str = "0" * 64) -> Block:
        creado = Block(
            id=uuid4(),
            block_index=block_index,
            timestamp=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
            previous_hash=previous_hash,
            hash="",
        )
        creado.hash = creado.calculate_hash([])
        return bloques.add(creado)

    return build


@pytest.fixture
def aplicacion(conexion, base_limpia, master_key) -> Flask:
    """La aplicación sobre la base limpia, con el génesis asegurado.

    La fábrica entrega el ledger sobre la conexión de la sesión y no abre otra: lo
    que escribe una ruta queda visible para las aserciones en el mismo instante.
    """

    @contextmanager
    def fabrica():
        chain = open_ledger(conexion, encryption_key=master_key)
        ensure_genesis(chain)
        yield chain

    return crear_app_de_prueba(fabrica)


@pytest.fixture
def cliente(aplicacion) -> FlaskClient:
    """El cliente de Flask de la aplicación de prueba, todavía sin sesión."""
    return aplicacion.test_client()


@pytest.fixture
def administrador(base_limpia, conexion, wallets, master_key) -> Usuario:
    """Un administrador aprobado, con una wallet que el camino del alta exige.

    No es el administrador de la semilla del arranque —ese es `admin` y no tiene
    wallet—: el nombre `adminprueba` evita chocar con él en las pruebas que corren
    el arranque de verdad, y una wallet propia deja el historial del administrador
    alcanzable en las rutas del eje.
    """
    wallet = wallets.add(create_wallet(master_key=master_key))
    return _sembrar_cuenta(
        conexion,
        username="adminprueba",
        role=ADMINISTRADOR,
        contrasena=CONTRASENA_DEL_ADMINISTRADOR,
        wallet_id=wallet.id,
    )


@pytest.fixture
def cliente_admin(cliente, administrador) -> FlaskClient:
    """El cliente con la sesión de administrador ya abierta."""
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    return cliente


@pytest.fixture
def usuario_comun(cuentas) -> Usuario:
    """Un usuario común aprobado, con su wallet y su saldo de bienvenida (REQ-33)."""
    creado = cuentas.registrar("ana", CONTRASENA_DE_PRUEBA)
    return cuentas.aprobar(creado.id)


@pytest.fixture
def cliente_comun(cliente, usuario_comun) -> FlaskClient:
    """El cliente con la sesión de un usuario común ya abierta."""
    ingresar_como(cliente, usuario_comun.username, CONTRASENA_DE_PRUEBA)
    return cliente

