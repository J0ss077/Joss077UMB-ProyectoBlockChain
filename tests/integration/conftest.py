"""Fixtures de las pruebas de integración: una conexión viva, una base limpia y
los datos que casi todas las pruebas de adaptadores necesitan.

El esquema se aplica con `db/init.sql` sobre el contenedor o sobre el clúster
nativo del equipo, así que estas pruebas no crean ni modifican tablas: solo
borran filas. El fixture `ledger` (la fachada armada) no vive aquí porque nace
en la tarea 7, junto con `src/persistence/factory.py`.
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from src.domain.block import Block
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import Wallet, create_wallet, sign_payload
from src.persistence.ports import BlockRepository, WalletRepository
from src.persistence.postgres import PostgresBlockRepository, PostgresWalletRepository

# Marca de tiempo fija: el payload firmado la incluye, y fijarla hace
# reproducibles las transacciones que arman las pruebas.
CREATED_AT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
DEFAULT_AMOUNT = Decimal("10.00000000")

# Raíz del repositorio: la suite se corre desde aquí, y las pruebas que invocan
# `git` o que buscan `src` dependen de este directorio de trabajo.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _valor_de_entorno(clave: str) -> str | None:
    """Valor de una variable del entorno o de `.env`, o `None` si no está en ninguno."""
    valor = os.environ.get(clave)
    if valor:
        return valor
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for linea in env_file.read_text(encoding="utf-8").splitlines():
        nombre, separador, dato = linea.partition("=")
        if separador and nombre.strip() == clave:
            return dato.strip().strip("'\"")
    return None


def _database_url() -> str:
    """Cadena de conexión del entorno o de `.env`; si falta, falla con la instrucción."""
    url = _valor_de_entorno("DATABASE_URL")
    if url:
        return url
    raise RuntimeError(
        "Falta DATABASE_URL en el entorno y en `.env`: levante la base con "
        "`docker compose up -d` (o `podman compose up -d`) y copie `.env.example` a `.env`. "
        "Una prueba omitida en silencio no verifica nada, así que esto falla en vez de saltarse."
    )


@pytest.fixture(scope="session")
def conexion():
    """Conexión abierta a la base del entorno, en UTC y sin cierre automático por sentencia.

    El alcance es de sesión porque PostgreSQL es un recurso caro de abrir por
    prueba; la limpieza de filas la hace `base_limpia` antes de cada una.
    """
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        connection.execute("SET TIME ZONE 'UTC'")
        yield connection


@pytest.fixture
def base_limpia(conexion):
    """Vacía las tres tablas antes de cada prueba, en orden inverso a las claves foráneas.

    Se borra con `DELETE` y no con `TRUNCATE`: `TRUNCATE` es DDL y REQ-15 lo
    prohíbe desde las pruebas. No es `autouse` a propósito: una prueba sin base
    (REQ-15 y REQ-21) no debe arrastrar la conexión y, con ella, la exigencia de
    `DATABASE_URL`; cada prueba que toca la base lo pide.
    """
    conexion.execute("DELETE FROM transactions")
    conexion.execute("DELETE FROM blocks")
    conexion.execute("DELETE FROM wallets")
    yield


@pytest.fixture
def master_key():
    """Clave Fernet del entorno; los adaptadores solo guardan su resultado cifrado."""
    valor = _valor_de_entorno("MASTER_KEY")
    if not valor:
        raise RuntimeError(
            "Falta MASTER_KEY en el entorno y en `.env`: copie `.env.example` a `.env`."
        )
    return valor.encode("ascii")


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

    El `id` se genera en la aplicación, no con el valor por defecto del esquema,
    porque el camino real conoce el `id` antes de escribir (decisión 5).
    """

    def build(block_index: int = 0, previous_hash: str = "0" * 64) -> Block:
        hash_propio = sha256(f"{block_index}|{previous_hash}".encode("utf-8")).hexdigest()
        return bloques.add(
            Block(
                id=uuid4(),
                block_index=block_index,
                timestamp=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
                previous_hash=previous_hash,
                hash=hash_propio,
            )
        )

    return build

