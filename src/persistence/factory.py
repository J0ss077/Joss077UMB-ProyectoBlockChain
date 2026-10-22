"""Ensamblado del ledger: configuración del entorno y adaptadores (REQ-16, REQ-21).

Resuelve de dónde salen la cadena de conexión, la clave maestra, el secreto de la
sesión y la contraseña del administrador, y arma la fachada del dominio con los
tres repositorios PostgreSQL y la unidad de trabajo de REQ-18. `open_ledger` trabaja
sobre una conexión que no abre —así la reutilizan el arranque y las pruebas—,
`transaction()` abre la conexión que comparten el ledger y las cuentas para la
aprobación atómica (REQ-33) y `ledger()` es el punto de entrada que sí la abre y la
cierra.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from src.accounts.ports import RepositorioDeUsuarios
from src.accounts.postgres import PostgresAccountsRepository
from src.domain.blockchain import Blockchain
from src.persistence.postgres import (
    PostgresBlockRepository,
    PostgresTransactionRepository,
    PostgresWalletRepository,
)
from src.persistence.unit_of_work import PostgresUnitOfWork

# `.env` vive en la raíz del repositorio y está en `.gitignore` (REQ-21): es el
# respaldo local de las variables del entorno, nunca su reemplazo ni un secreto
# versionado.
RAIZ_DEL_PROYECTO = Path(__file__).resolve().parents[2]
ENV_FILE = RAIZ_DEL_PROYECTO / ".env"
# Las fotos de perfil son archivos fuera de la base. Sin `FOTOS_DIR` van a
# `datos/fotos/` dentro del proyecto, que `.gitignore` deja fuera del repositorio.
VARIABLE_DE_LA_CARPETA_DE_FOTOS = "FOTOS_DIR"
# Base exclusiva de las pruebas de integración, que vacían sus tablas en cada caso:
# con ella definida, la suite no toca la base de la aplicación.
VARIABLE_DE_LA_BASE_DE_PRUEBAS = "TEST_DATABASE_URL"
CARPETA_DE_FOTOS_POR_DEFECTO = RAIZ_DEL_PROYECTO / "datos" / "fotos"
# El servicio de IA del ayudante flotante: basta la clave; el resto es opcional.
VARIABLES_DEL_ASISTENTE = (
    "ASISTENTE_API_KEY",
    "ASISTENTE_PROVEEDOR",
    "ASISTENTE_MODELO",
    "ASISTENTE_URL",
)

# Nombre de la variable que trae la cadena de conexión. Es una constante y no un
# literal porque el lector del entorno y la prueba que lo ejercita tienen que nombrar
# la misma variable: el guard de REQ-17 prohíbe el literal en `tests/unit`, así que la
# prueba importa esta constante en vez de escribirlo.
VARIABLE_DE_LA_CADENA_DE_CONEXION = "DATABASE_URL"

# Las tres variables de la configuración sensible van en constantes por la misma
# razón que la cadena de conexión: el lector y su prueba tienen que nombrar la misma
# variable y el guard de REQ-17 prohíbe el literal en `tests/unit`.
VARIABLE_DE_LA_CLAVE_MAESTRA = "MASTER_KEY"
VARIABLE_DEL_SECRETO_DE_SESION = "SESSION_SECRET"
VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR = "ADMIN_PASSWORD"

# Los valores de ejemplo de `.env.example`. Son públicos —viajan en el repositorio—,
# así que aceptarlos deja la aplicación abierta: con la clave de ceros cualquiera
# firma una cookie de sesión, con la contraseña de plantilla cualquiera entra como
# administrador y con la clave maestra de relleno cualquiera descifra las llaves
# privadas de la base. Los lectores los rechazan nombrando la variable y qué hacer.
#
# La clave maestra de relleno son 32 bytes en cero codificados como base64 urlsafe:
# tiene la forma válida que exige Fernet (44 caracteres y el relleno final) y, sin
# embargo, es un valor publicado. `A` es el carácter de base64 que representa seis
# bits en cero, así que 43 `A` más el `=` son los 32 bytes en cero.
CLAVE_MAESTRA_DE_LA_PLANTILLA = "A" * 43 + "="
SECRETO_DE_SESION_DE_LA_PLANTILLA = "0" * 64
CONTRASENA_DEL_ADMINISTRADOR_DE_LA_PLANTILLA = "cambie-esta-contrasena"


def _env_value(name: str) -> str | None:
    """Valor de una variable del entorno o, si no está, del `.env` local.

    Devuelve `None` cuando no está en ninguno de los dos.
    """
    value = os.environ.get(name)
    if value:
        return value
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip().strip("'\"")
    return None


def normalizar_cadena(cadena: str) -> str:
    """Devuelve la cadena de conexión con `connect_timeout` puesto si no lo traía.

    Sin tiempo de espera, cuánto aguantar frente a un puerto que no contesta lo deciden
    la librería y el sistema operativo —y detrás del retransmisor de WSL2 en Windows
    puede ser mucho—, así que un puerto mal puesto se ve como un cuelgue en lugar de
    como un error. Un `connect_timeout` explícito en la cadena se respeta tal cual.

    Las dos entradas de una cadena pasan por acá: el lector del entorno y el argumento
    explícito de `open_ledger`. Normalizar en una sola función es lo que impide que una
    de las dos quede sin el tiempo de espera por olvido.

    La cadena vuelve en la forma canónica de libpq (`host=... port=...
    connect_timeout=5`), no en la forma de URL que se escribe en `.env`: para saber si
    ya traía un tiempo de espera hay que interpretarla, y `conninfo` la vuelve a
    escribir con todos sus parámetros más el que se agrega. `psycopg` acepta las dos
    formas, y de esta función solo sale la cadena con la que se conecta, así que el
    cambio de forma no llega a nadie más.
    """
    parametros = conninfo_to_dict(cadena)
    parametros.setdefault("connect_timeout", "5")
    return make_conninfo(**parametros)


def database_url() -> str:
    """Cadena de conexión del entorno o de `.env`, normalizada antes de devolverla.

    Si falta, falla con la instrucción en vez de adivinar un valor: una
    configuración a medias tiene que doler ahora y no en la primera consulta.

    Normalizar aquí y no en cada conexión cubre las dos que abre el ledger: la de
    `ledger()` y la de la unidad de trabajo, que reciben esta misma cadena.
    """
    url = _env_value(VARIABLE_DE_LA_CADENA_DE_CONEXION)
    if url:
        return normalizar_cadena(url)
    raise RuntimeError(
        f"Falta {VARIABLE_DE_LA_CADENA_DE_CONEXION} en el entorno y en `.env`: levante "
        "la base con `docker compose up -d` (o `podman compose up -d`) y agregue "
        f"{VARIABLE_DE_LA_CADENA_DE_CONEXION} a su `.env` (la plantilla `.env.example` "
        "la trae)."
    )


def master_key() -> bytes:
    """Clave Fernet con la que se cifra el material privado de las wallets (REQ-21).

    La clave de relleno de `.env.example` se rechaza igual que el secreto de sesión
    y la contraseña del administrador: es pública, y cifrar con ella deja las llaves
    privadas legibles para cualquiera que lea el repositorio.
    """
    value = _env_value(VARIABLE_DE_LA_CLAVE_MAESTRA)
    if value:
        if value == CLAVE_MAESTRA_DE_LA_PLANTILLA:
            raise RuntimeError(
                f"{VARIABLE_DE_LA_CLAVE_MAESTRA} sigue siendo el valor de relleno de "
                "la plantilla `.env.example`: genere una clave propia con "
                '`python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"` y reemplácela en su `.env`.'
            )
        return value.encode("ascii")
    raise RuntimeError(
        f"Falta {VARIABLE_DE_LA_CLAVE_MAESTRA} en el entorno y en `.env`: agregue "
        f"{VARIABLE_DE_LA_CLAVE_MAESTRA} a su `.env` y genere una clave propia con "
        '`python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"`; la plantilla `.env.example` la trae '
        "de relleno y el lector la rechaza."
    )


def session_secret() -> bytes:
    """Clave con la que Flask firma la cookie de sesión (REQ-37).

    Se devuelve como bytes porque es lo que espera `app.secret_key`; se lee del
    entorno y, si no está, de `.env`, igual que la clave maestra.
    """
    value = _env_value(VARIABLE_DEL_SECRETO_DE_SESION)
    if value:
        if value == SECRETO_DE_SESION_DE_LA_PLANTILLA:
            raise RuntimeError(
                f"{VARIABLE_DEL_SECRETO_DE_SESION} sigue siendo el valor de la "
                "plantilla `.env.example`: reemplácela por una clave propia con "
                '`.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"`.'
            )
        return value.encode("utf-8")
    raise RuntimeError(
        f"Falta {VARIABLE_DEL_SECRETO_DE_SESION} en el entorno y en `.env`: agregue "
        f"{VARIABLE_DEL_SECRETO_DE_SESION} a su `.env` y genere la clave con "
        '`.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"`.'
    )


def admin_password() -> str:
    """Contraseña de la cuenta de administrador que siembra el arranque (decisión 4)."""
    value = _env_value(VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR)
    if value:
        if value == CONTRASENA_DEL_ADMINISTRADOR_DE_LA_PLANTILLA:
            raise RuntimeError(
                f"{VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR} sigue siendo el valor "
                "de la plantilla `.env.example`: reemplácela por una contraseña propia "
                "en su `.env` antes de sembrar."
            )
        return value
    raise RuntimeError(
        f"Falta {VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR} en el entorno y en "
        f"`.env`: agregue {VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR} a su `.env` y "
        "fije la contraseña del administrador."
    )


def database_url_de_pruebas() -> str | None:
    """La cadena de la base de pruebas, o `None` si no se definió una aparte."""
    return _env_value(VARIABLE_DE_LA_BASE_DE_PRUEBAS)


def configuracion_del_asistente() -> dict[str, str | None]:
    """Las variables del servicio de IA del ayudante, del entorno o de `.env`.

    Se devuelven tal cual: qué servicio es y con qué modelo lo decide
    `src/web/ia.py`. Sin `ASISTENTE_API_KEY` el ayudante usa su guía local.
    """
    return {nombre: _env_value(nombre) for nombre in VARIABLES_DEL_ASISTENTE}


def carpeta_de_fotos() -> Path:
    """La carpeta donde se guardan los archivos de las fotos de perfil.

    Una ruta relativa en `FOTOS_DIR` se toma desde la raíz del proyecto, no desde
    donde se haya lanzado el proceso: el arranque y la aplicación tienen que ver
    la misma carpeta.
    """
    valor = _env_value(VARIABLE_DE_LA_CARPETA_DE_FOTOS)
    if not valor:
        return CARPETA_DE_FOTOS_POR_DEFECTO
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else RAIZ_DEL_PROYECTO / ruta


def _utc_now() -> datetime:
    """Reloj por defecto del ledger, en UTC como la base y las marcas canónicas."""
    return datetime.now(UTC)


def open_ledger(
    connection: psycopg.Connection,
    *,
    encryption_key: bytes,
    clock: Callable[[], datetime] | None = None,
    database_dsn: str | None = None,
) -> Blockchain:
    """Arma el ledger sobre una conexión abierta que este módulo no cierra.

    `encryption_key` es la clave maestra con la que el ledger cifra y firma
    (decisión 3); se llama así aquí para no tapar la función `master_key()`, que es
    la que la lee del entorno.

    `database_dsn` es la cadena con la que se abre la unidad de trabajo; si no se
    pasa, se resuelve del entorno **una sola vez** aquí. Resolverla una vez y no en
    cada agrupación es lo que garantiza que las lecturas y las escrituras apunten a
    la misma base aunque el entorno cambie a mitad de camino. La cadena explícita se
    normaliza igual que la del entorno: es la otra puerta por la que entra una cadena
    y no hay razón para que una llegue con `connect_timeout` y la otra sin él.

    Los tres repositorios de lectura comparten esa conexión; la agrupación no,
    porque REQ-18 exige que sus dos escrituras ocurran en una sola transacción de
    base de datos y para eso la unidad de trabajo abre la suya propia.
    """
    dsn = database_url() if database_dsn is None else normalizar_cadena(database_dsn)
    return Blockchain(
        wallets=PostgresWalletRepository(connection),
        blocks=PostgresBlockRepository(connection),
        transactions=PostgresTransactionRepository(connection),
        unit_of_work=lambda: PostgresUnitOfWork.open(dsn),
        master_key=encryption_key,
        clock=clock if clock is not None else _utc_now,
    )


class TransaccionDeCuentas:
    """El ledger y las cuentas sobre una sola conexión, con un `commit` único (REQ-33).

    La usa la aprobación, que es la única operación que escribe en los dos
    contextos: la wallet, el bloque de bienvenida y el estado del usuario tienen
    que confirmarse juntos o no confirmarse. El `commit` vive acá y no en un
    `with` implícito porque la operación decide cuándo cerró bien: mientras no se
    llame, el cierre de la conexión deshace lo escrito.
    """

    def __init__(
        self,
        *,
        ledger: Blockchain,
        usuarios: RepositorioDeUsuarios,
        connection: psycopg.Connection,
    ) -> None:
        self.ledger = ledger
        self.usuarios = usuarios
        self._connection = connection

    def commit(self) -> None:
        """Confirma de una vez todo lo escrito en esta transacción."""
        self._connection.commit()


@contextmanager
def transaction() -> Iterator[TransaccionDeCuentas]:
    """Abre una transacción de base que compone el ledger y las cuentas (REQ-18, REQ-33).

    Es la pieza que hace atómica la aprobación: `register_wallet`, `acreditar` y
    el `UPDATE` del estado escriben por los repositorios de **esta** conexión, y el
    `commit` único del llamador confirma las tres o ninguna. Por eso la conexión no
    va en autocommit y el `commit` es explícito: lo decide la operación.

    Ante cualquier excepción se deshace lo escrito y el error sigue subiendo sin
    traducir (REQ-19), igual que en la unidad de trabajo de la agrupación. La
    conexión se cierra siempre: es de esta transacción y no de los llamadores.

    Se compone acá y no en `unit_of_work.py` porque ese módulo importar `factory`
    sería circular; la unidad de trabajo sigue siendo la de la agrupación (REQ-18),
    que no necesita el ledger sobre su conexión.
    """
    dsn = database_url()
    connection = psycopg.connect(dsn)
    try:
        connection.execute("SET TIME ZONE 'UTC'")
        yield TransaccionDeCuentas(
            ledger=open_ledger(
                connection, encryption_key=master_key(), database_dsn=dsn
            ),
            usuarios=PostgresAccountsRepository(connection),
            connection=connection,
        )
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def ledger() -> Iterator[Blockchain]:
    """Abre la conexión del entorno, entrega el ledger y la cierra al salir.

    La conexión va en autocommit, igual que la de las pruebas: cada lectura ve lo
    último confirmado, incluido lo que la agrupación confirmó en su transacción
    aparte. Es el punto de entrada de `src.bootstrap` y de la aplicación web, y por
    eso resuelve la cadena una sola vez y se la pasa a la fachada: la conexión que
    abre y la unidad de trabajo usan el mismo destino.
    """
    dsn = database_url()
    with psycopg.connect(dsn, autocommit=True) as connection:
        # La zona de la sesión decide cómo se leen las columnas `TIMESTAMPTZ`, y el
        # hash del bloque cubre `datetime.isoformat()`: sin UTC, la misma fila se
        # leería con otro desplazamiento y una cadena válida se verificaría como
        # alterada. Toda conexión del ledger queda en UTC por esta razón.
        connection.execute("SET TIME ZONE 'UTC'")
        yield open_ledger(connection, encryption_key=master_key(), database_dsn=dsn)
