# Reconstrucción del prototipo transaccional basado en blockchain — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar los 29 requerimientos del eje y sus 5 casos de uso en un prototipo de nodo único con dominio aislado, persistencia PostgreSQL y presentación Flask, explicable línea por línea.

**Architecture:** Tres capas. El dominio (cinco clases) no conoce el motor y se prueba sin base de datos; la persistencia implementa tres protocolos y una unidad de trabajo detrás de los cuales vive PostgreSQL; la presentación Flask llama al ledger y pinta plantillas, sin reglas ni SQL.

**Tech Stack:** Python 3.11+, `cryptography` (ECDSA secp256k1 y Fernet), `psycopg` 3, Flask, PostgreSQL 16 en contenedor, `pytest`.

**Spec:** `docs/superpowers/specs/2026-10-10-blockchain-transaccional-design.md` — el plan argumenta desde el diseño y el diseño cita el eje (`documentacion_proyecto_transaccionales.pdf`); quien ejecute lee los dos.

## Global Constraints

- Python **3.11 o superior** (REQ-20). El código no puede usar sintaxis posterior a 3.11.
- PostgreSQL **16** en contenedor; el `compose.yaml` funciona igual con `docker compose` y con `podman compose`.
- Rutas HTTP exactas del eje y nada más: `POST /wallets`, `POST /transacciones`, `POST /bloques`, `GET /verificar`, `GET /historial/<wallet>` (REQ-24 a REQ-29).
- El esquema vive **solo** en `db/init.sql`; ninguna ruta del código Python contiene DDL (REQ-15).
- Los errores del motor **suben sin traducir**; no se duplican los CHECK en Python (REQ-19).
- Ningún secreto se versiona: `.env` fuera de git, `MASTER_KEY` y `DATABASE_URL` por entorno (REQ-21).
- Dependencias con versión fija en `requirements.txt` (REQ-23).
- Nombres de código en inglés; documentación, docstrings y comentarios **en español**, sin emojis.
- Regla del comentario: se queda el que explica el porqué (una decisión, una restricción del eje, un orden que importa, algo que sorprende); se borra el que repite la línea.
- Cada módulo abre con un docstring que dice qué problema resuelve y qué REQ implementa. Las pruebas se llaman `test_req_NN_*` y llevan el criterio de aceptación en el docstring.
- Sin guiones de shell ni Makefile: los puntos de entrada son módulos de Python (`python -m ...`).
- Lista cerrada de artefactos (decisión 11 del diseño): `README.md`, el diseño, este plan, `docs/recorrido-de-casos-de-uso.md`, docstrings y comentarios, y las pruebas.
- Cada tarea termina en un commit pequeño con mensaje en español.

## Review Focus

Los cinco casos que el eje no menciona y que más probablemente rompan el sistema en manos de alguien. Cada uno tiene su prueba en la tarea que posee el código (marcados abajo como **RF-n**).

1. **Un monto con más de ocho decimales** (`0.000000001`): no cabe en `NUMERIC(18,8)`. Si el dominio lo redondeara en silencio, la firma se calcularía sobre un valor y la base guardaría otro, y la verificación de la cadena señalaría una alteración que nadie hizo. Se rechaza con motivo explícito (tarea 2).
2. **Un monto fuera del rango de `NUMERIC(18,8)`** (diez mil millones o más): el motor lo rechazaría con un error de rango; el dominio lo rechaza antes y con motivo (tarea 2).
3. **Un hueco en los índices de la cadena** (bloques 0, 1 y 3) o un `previous_hash` que apunta a un bloque inexistente: la verificación debe señalar el bloque donde la cadena deja de encadenar, no recorrer el resto en silencio (tarea 8).
4. **El bloque génesis alterado** (su marca de tiempo, con el hash guardado intacto): la verificación debe detectarlo recalculando su hash propio (tarea 8, decisión 13 del diseño).
5. **`GET /historial/<wallet>` con un identificador inválido o de una wallet inexistente**: debe responder con una página clara, no con un error del motor en pantalla (tarea 10).

## Estructura de archivos

| Archivo                                      | Responsabilidad                                                  |
| -------------------------------------------- | ---------------------------------------------------------------- |
| `pyproject.toml`, `requirements.txt`         | Piso de Python y versiones fijas                                 |
| `.gitignore`, `.env.example`, `compose.yaml` | Entorno reproducible y secretos fuera de git                     |
| `db/init.sql`                                | Esquema completo, del modelo relacional del eje                  |
| `src/domain/wallet.py`                       | Par ECDSA, cifrado del material privado, firma y verificación    |
| `src/domain/transaction.py`                  | Entidad, estados, forma canónica y reglas de validación          |
| `src/domain/block.py`                        | Entidad y cálculo del hash sobre el contenido agrupado           |
| `src/domain/blockchain.py`                   | Saldo disponible, fachada del ledger, agrupación y verificación  |
| `src/persistence/ports.py`                   | Los tres protocolos, la unidad de trabajo y sus tipos            |
| `src/persistence/postgres.py`                | Adaptadores PostgreSQL                                           |
| `src/persistence/unit_of_work.py`            | Transacción de base de datos para la agrupación atómica          |
| `src/persistence/factory.py`                 | Ensamblado del ledger desde la configuración del entorno         |
| `src/bootstrap.py`                           | Génesis idempotente y datos de demostración                      |
| `src/web/app.py`, `src/web/templates/`       | Las cinco rutas y sus plantillas                                 |
| `tests/dobles.py`                            | Repositorios en memoria para probar el dominio y la verificación |
| `tests/unit/`, `tests/integration/`          | Pruebas por requerimiento, con y sin base de datos               |
| `tests/test_explicacion.py`                  | Coherencia entre el recorrido y los requerimientos               |
| `docs/recorrido-de-casos-de-uso.md`          | El camino real de cada caso de uso                               |
| `README.md`                                  | Cómo correrlo en los tres sistemas y por dónde empezar a leer    |

---

### Task 1: Entorno reproducible y Wallet

**Files:**

- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `src/__init__.py`, `src/domain/__init__.py`, `src/domain/wallet.py`, `tests/unit/test_req_01_wallet.py`, `tests/unit/test_req_02_firma.py`

**Interfaces:**

- Consumes: nada.
- Produces: `Wallet` y las funciones `create_wallet`, `sign_payload`, `verify`, `public_key_from_hex`, `encrypt_private_key`, `decrypt_private_key` de `src/domain/wallet.py`, con las firmas exactas de abajo.

- [ ] **Step 1: Iniciar el repositorio y el entorno**

```bash
git init
printf '%s\n' '.env' '.venv/' '__pycache__/' '*.pyc' '.reference/' '.legacy-project/' '.pytest_cache/' > .gitignore
python -m venv .venv
.venv/bin/python -m ensurepip
.venv/bin/pip install cryptography psycopg[binary] flask pytest
.venv/bin/pip freeze > requirements.txt
```

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/unit/test_req_01_wallet.py`:

```python
"""REQ-01: la pública queda en claro y única; el material privado nunca en claro."""
from cryptography.fernet import Fernet

from src.domain.wallet import create_wallet, decrypt_private_key


def test_req_01_la_privada_no_esta_en_claro_en_la_wallet():
    master = Fernet.generate_key()
    wallet = create_wallet(master_key=master)
    privada = decrypt_private_key(wallet.private_key_encrypted, master)
    material = privada.private_numbers().private_value.to_bytes(32, "big")
    assert material not in wallet.private_key_encrypted


def test_req_01_dos_wallets_no_comparten_publica():
    master = Fernet.generate_key()
    assert create_wallet(master_key=master).public_key != create_wallet(master_key=master).public_key
```

`tests/unit/test_req_02_firma.py`:

```python
"""REQ-02: una transacción firmada por su emisor verifica; firmada por otra wallet se rechaza."""
from cryptography.fernet import Fernet

from src.domain.wallet import create_wallet, sign_payload, verify


def test_req_02_la_firma_del_emisor_verifica_y_la_ajena_no():
    master = Fernet.generate_key()
    emisora, ajena = create_wallet(master_key=master), create_wallet(master_key=master)
    payload = b"transaccion canonica"
    firma = sign_payload(emisora, payload, master)
    assert verify(emisora.public_key, firma, payload) is True
    assert verify(ajena.public_key, firma, payload) is False
    assert verify(emisora.public_key, firma, payload + b"x") is False
```

- [ ] **Step 3: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/unit -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.domain.wallet'`

- [ ] **Step 4: Implementar `src/domain/wallet.py`**

Firmas exactas (el cuerpo lo escribe quien implementa; el docstring del módulo declara que implementa REQ-01 y REQ-02):

```python
CURVE = ec.SECP256K1

@dataclass(slots=True)
class Wallet:
    id: UUID
    public_key: str
    private_key_encrypted: bytes
    created_at: datetime

def generate_private_key() -> ec.EllipticCurvePrivateKey
def public_key_hex(private_key: ec.EllipticCurvePrivateKey) -> str
def public_key_from_hex(value: str) -> ec.EllipticCurvePublicKey
def encrypt_private_key(private_key: ec.EllipticCurvePrivateKey, master_key: bytes) -> bytes
def decrypt_private_key(token: bytes, master_key: bytes) -> ec.EllipticCurvePrivateKey
def create_wallet(*, master_key: bytes, wallet_id: UUID | None = None, created_at: datetime | None = None) -> Wallet
def sign_payload(wallet: Wallet, payload: bytes, master_key: bytes) -> str
def verify(public_key_hex: str, signature_hex: str, payload: bytes) -> bool
```

Notas de implementación que la firma y las pruebas no determinan: la pública se serializa como punto comprimido en hexadecimal (`public_bytes(Encoding.X962, PublicFormat.CompressedPoint).hex()`); la firma es el DER en hexadecimal minúscula; `sign_payload` descifra el material con la clave maestra en cada uso, y eso es deliberado — el texto plano no vive en ningún objeto que se guarde (comentario obligatorio en el código).

- [ ] **Step 5: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests/unit -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add .gitignore pyproject.toml requirements.txt src tests
git commit -m "feat: wallet con par ECDSA, material privado cifrado y firma verificable"
```

---

### Task 2: Transaction, estados y reglas de validación

**Files:**

- Create: `src/domain/transaction.py`, `tests/unit/test_req_02_transaction.py`, `tests/unit/test_req_04_formato.py`
- Modify: `tests/unit/test_req_04_formato.py` incluye **RF-1** y **RF-2** del Review Focus

**Interfaces:**

- Consumes: `src.domain.wallet.verify`.
- Produces: `TransactionStatus`, `RejectionReason`, `ValidationResult`, `Transaction.validate(...)`, `Transaction.is_valid(...)`, `Transaction.signing_payload(...)`, `Transaction.hash_payload()`, y `AMOUNT_SCALE`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/unit/test_req_04_formato.py` (cubre REQ-04, RF-1 y RF-2):

```python
"""REQ-04: las cuatro condiciones se comprueban antes de entrar al pool."""
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.transaction import RejectionReason, Transaction


def test_req_04_monto_no_positivo_se_rechaza(transaccion):
    resultado = transaccion(amount=Decimal("0")).validate(available=Decimal("100"), signature_exists=False)
    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.AMOUNT_NOT_POSITIVE


def test_req_04_emisor_igual_al_receptor_se_rechaza(transaccion):
    mismo = uuid4()
    resultado = transaccion(sender_id=mismo, receiver_id=mismo).validate(available=Decimal("100"), signature_exists=False)
    assert resultado.reason is RejectionReason.SAME_SENDER_AND_RECEIVER


def test_req_04_rf1_monto_con_mas_de_ocho_decimales_se_rechaza(transaccion):
    resultado = transaccion(amount=Decimal("0.000000001")).validate(available=Decimal("100"), signature_exists=False)
    assert resultado.reason is RejectionReason.AMOUNT_PRECISION


def test_req_04_rf2_monto_fuera_del_rango_de_numeric_18_8_se_rechaza(transaccion):
    resultado = transaccion(amount=Decimal("10000000000")).validate(available=Decimal("100"), signature_exists=False)
    assert resultado.reason is RejectionReason.AMOUNT_OUT_OF_RANGE
```

Donde `transaccion` es un fixture de `tests/unit/conftest.py` que arma una `Transaction` válida y permite sobrescribir campos, y `validate` recibe además `sender_public_key`, `receiver_public_key` y `available` (el fixture deja la firma correcta para las pruebas de formato).

`tests/unit/test_req_02_transaction.py` (la firma decide, y el motivo explica):

```python
"""REQ-02: la validación exige que la firma corresponda a la llave pública del emisor."""
def test_req_02_firma_de_otra_wallet_se_rechaza(transaccion_de_otra_wallet):
    resultado = transaccion_de_otra_wallet.validate(available=Decimal("100"), signature_exists=False)
    assert resultado.accepted is False
    assert resultado.reason is RejectionReason.BAD_SIGNATURE


def test_req_02_transaccion_correcta_se_acepta(transaccion):
    assert transaccion().is_valid(available=Decimal("100"), signature_exists=False) is True
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/unit -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.domain.transaction'`

- [ ] **Step 3: Implementar `src/domain/transaction.py`**

Firmas exactas:

```python
AMOUNT_SCALE = Decimal("0.00000001")
AMOUNT_MAX = Decimal("9999999999.99999999")

class TransactionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"

class RejectionReason(StrEnum):
    AMOUNT_NOT_POSITIVE = "el monto debe ser mayor que cero"
    AMOUNT_PRECISION = "el monto no puede tener más de ocho decimales"
    AMOUNT_OUT_OF_RANGE = "el monto no cabe en NUMERIC(18, 8)"
    SAME_SENDER_AND_RECEIVER = "el emisor y el receptor deben ser distintos"
    UNKNOWN_WALLET = "alguna de las wallets no existe"
    BAD_SIGNATURE = "la firma no corresponde a la llave pública del emisor"
    INSUFFICIENT_FUNDS = "el saldo disponible no alcanza"
    DUPLICATE_SIGNATURE = "esa firma ya fue registrada"

@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    reason: RejectionReason | None

@dataclass(slots=True)
class Transaction:
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    amount: Decimal
    status: TransactionStatus
    signature: str
    block_id: UUID | None
    created_at: datetime

    def signing_payload(self, sender_public_key: str, receiver_public_key: str) -> bytes
    def hash_payload(self) -> str
    def validate(self, *, sender_public_key: str | None, receiver_public_key: str | None,
                 available: Decimal, signature_exists: bool) -> ValidationResult
    def is_valid(self, **kwargs) -> bool
```

Notas que la firma y las pruebas no determinan: `signing_payload` es `f"{id}|{sender_public_key}|{receiver_public_key}|{amount:.8f}|{created_at.isoformat()}"` en UTF-8; `hash_payload` es `f"{id}|{sender_id}|{receiver_id}|{amount:.8f}|{signature}|{created_at.isoformat()}"` y **no** incluye `status` ni `block_id`, porque ambos cambian después de calcular el hash del bloque (comentario obligatorio: es el orden que hace posible el encadenamiento). El orden de comprobación es formato → wallets → firma → saldo → firma repetida, y el primer motivo encontrado es el que se informa (RF-1 y RF-2 van dentro del bloque de formato, antes de tocar nada externo).

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests/unit -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/domain/transaction.py tests/unit
git commit -m "feat: transaction con formato, firma, saldo y motivo de rechazo"
```

---

### Task 3: Block y el hash del contenido agrupado

**Files:**

- Create: `src/domain/block.py`, `tests/unit/test_req_07_hash.py`

**Interfaces:**

- Consumes: `Transaction.hash_payload()`.
- Produces: `Block.calculate_hash(transactions) -> str`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""REQ-07: el hash cubre el contenido agrupado; cambiar un dato agrupado lo cambia."""
def test_req_07_el_hash_es_sha256_hex_de_sesenta_y_cuatro(bloque, transacciones):
    valor = bloque.calculate_hash(transacciones)
    assert len(valor) == 64 and valor == valor.lower()
    int(valor, 16)


def test_req_07_cambiar_un_monto_agrupado_cambia_el_hash(bloque, transacciones):
    original = bloque.calculate_hash(transacciones)
    alteradas = [replace(transacciones[0], amount=Decimal("99.00000000")), *transacciones[1:]]
    assert bloque.calculate_hash(alteradas) != original


def test_req_07_el_orden_de_las_transacciones_no_cambia_el_hash(bloque, transacciones):
    assert bloque.calculate_hash(list(reversed(transacciones))) == bloque.calculate_hash(transacciones)
```

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `.venv/bin/pytest tests/unit/test_req_07_hash.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.domain.block'`

- [ ] **Step 3: Implementar `src/domain/block.py`**

```python
@dataclass(slots=True)
class Block:
    id: UUID
    block_index: int
    timestamp: datetime
    previous_hash: str
    hash: str

    def calculate_hash(self, transactions: Sequence[Transaction]) -> str
```

Nota que la firma no determina: el mensaje es `f"{block_index}|{timestamp.isoformat()}|{previous_hash}|"` seguido de los `hash_payload()` de las transacciones **ordenados alfabéticamente** y unidos por `|`; el orden ordenado es lo que hace que el hash no dependa del orden de lectura (comentario obligatorio), y el `id` de la transacción va dentro, así que mover una transacción de un bloque a otro también cambia el hash.

- [ ] **Step 4: Correr la prueba y ver que pasa**

Run: `.venv/bin/pytest tests/unit/test_req_07_hash.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/domain/block.py tests/unit/test_req_07_hash.py
git commit -m "feat: hash SHA-256 del bloque sobre su contenido agrupado"
```

---

### Task 4: Saldo disponible y orden secuencial

**Files:**

- Create: `src/domain/blockchain.py` (solo las funciones puras por ahora), `tests/unit/test_req_05_saldo.py`

**Interfaces:**

- Consumes: `TransactionStatus`, `ValidationResult`.
- Produces: `BalanceTerms`, `available_balance(terms) -> Decimal`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""REQ-05 y REQ-06: el saldo disponible descuenta lo comprometido en el pool."""
def test_req_05_solo_las_confirmadas_cuentan_para_el_saldo():
    terms = BalanceTerms(confirmed_in=Decimal("100"), confirmed_out=Decimal("30"), pending_out=Decimal("0"))
    assert available_balance(terms) == Decimal("70")


def test_req_06_el_pool_descuenta_el_disponible():
    terms = BalanceTerms(confirmed_in=Decimal("100"), confirmed_out=Decimal("0"), pending_out=Decimal("80"))
    assert available_balance(terms) == Decimal("20")


def test_req_06_dos_transacciones_que_juntas_exceden_no_pasan_las_dos():
    disponible = available_balance(BalanceTerms(Decimal("100"), Decimal("0"), Decimal("0")))
    primera = transaccion(amount=Decimal("60")).validate(available=disponible, signature_exists=False)
    assert primera.accepted is True
    con_pool = available_balance(BalanceTerms(Decimal("100"), Decimal("0"), Decimal("60")))
    segunda = transaccion(amount=Decimal("60")).validate(available=con_pool, signature_exists=False)
    assert segunda.reason is RejectionReason.INSUFFICIENT_FUNDS
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/unit/test_req_05_saldo.py -v`
Expected: FAIL con `ImportError: cannot import name 'BalanceTerms'`

- [ ] **Step 3: Implementar en `src/domain/blockchain.py`**

```python
@dataclass(frozen=True, slots=True)
class BalanceTerms:
    confirmed_in: Decimal
    confirmed_out: Decimal
    pending_out: Decimal

def available_balance(terms: BalanceTerms) -> Decimal
```

Docstring del módulo: declara que implementa la regla del CU-02 (saldo confirmado menos lo comprometido en el pool) y por qué la validación es secuencial (el eje pone la concurrencia fuera de alcance).

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests/unit -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/domain/blockchain.py tests/unit/test_req_05_saldo.py
git commit -m "feat: saldo disponible con lo comprometido en el pool"
```

---

### Task 5: Esquema, entorno en contenedor y puertos

**Files:**

- Create: `db/init.sql`, `compose.yaml`, `.env.example`, `src/persistence/__init__.py`, `src/persistence/ports.py`, `tests/integration/conftest.py`, `tests/integration/test_req_15_esquema.py`, `tests/unit/test_req_16_dominio_aislado.py`, `tests/integration/test_req_21_secretos.py`

**Interfaces:**

- Consumes: `Wallet`, `Transaction`, `Block`, `BalanceTerms`.
- Produces: los protocolos `WalletRepository`, `BlockRepository`, `TransactionRepository`, `UnitOfWork`, y el fixture `ledger` de las pruebas de integración.

- [ ] **Step 1: Escribir `db/init.sql`**

Tres tablas del modelo relacional del eje —`wallets`, `blocks`, `transactions`— con `uuid-ossp`, hashes `CHAR(64)` con expresión regular, `amount NUMERIC(18,8) CHECK (amount > 0)`, `sender_id <> receiver_id`, `status IN ('pending','confirmed','rejected')`, la coherencia estado/bloque, las claves foráneas `ON DELETE RESTRICT`, los cuatro índices del eje y **el índice único sobre `signature`** (decisión 4). El archivo abre con un comentario que dice que el esquema viene del modelo relacional del eje y que su estructura no la decide el código (REQ-15).

- [ ] **Step 2: Escribir `compose.yaml` y `.env.example`**

`compose.yaml`: imagen `postgres:16-alpine`, `env_file: .env`, el puerto publicado, el volumen de datos, `./db/init.sql` montado de solo lectura en `/docker-entrypoint-initdb.d` y un `healthcheck` con `pg_isready`. `.env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `DATABASE_URL` y `MASTER_KEY`, con un comentario que explique que la clave maestra cifra el material privado y que `.env` no se versiona (REQ-21). Generar la clave con `.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

- [ ] **Step 3: Escribir las pruebas de aislamiento y de esquema**

`tests/unit/test_req_16_dominio_aislado.py` (REQ-16, sin base de datos):

```python
"""REQ-16: cargar el ledger no importa el driver de la base."""
def test_req_16_importar_el_ledger_no_carga_psycopg():
    codigo = "import sys, src.domain.blockchain; assert 'psycopg' not in sys.modules, 'el dominio no debe importar el driver'"
    assert subprocess.run([sys.executable, "-c", codigo]).returncode == 0
```

`tests/integration/test_req_15_esquema.py` (REQ-15):

```python
"""REQ-15: ninguna ruta del código contiene sentencias de definición de datos."""
def test_req_15_no_hay_ddl_en_el_codigo():
    patron = re.compile(r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|EXTENSION|SCHEMA)\b", re.IGNORECASE)
    ofensores = [str(p) for p in pathlib.Path("src").rglob("*.py") if patron.search(p.read_text(encoding="utf-8"))]
    assert ofensores == []
```

`tests/integration/test_req_21_secretos.py` (REQ-21):

```python
"""REQ-21: la cadena de conexión y la clave maestra viven en el entorno, y .env no está en git."""
def test_req_21_env_esta_ignorado_y_no_versionado():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"]).returncode == 0
    assert subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], capture_output=True).returncode != 0
```

- [ ] **Step 4: Escribir los puertos y el fixture de integración**

`src/persistence/ports.py` con las firmas exactas:

```python
class WalletRepository(Protocol):
    def add(self, wallet: Wallet) -> Wallet: ...
    def get(self, wallet_id: UUID) -> Wallet | None: ...
    def get_by_public_key(self, public_key: str) -> Wallet | None: ...
    def list(self, limit: int = 100) -> Sequence[Wallet]: ...
    def count(self) -> int: ...

class BlockRepository(Protocol):
    def add(self, block: Block) -> Block: ...
    def get_by_index(self, block_index: int) -> Block | None: ...
    def last(self) -> Block | None: ...
    def list(self) -> Sequence[Block]: ...
    def count(self) -> int: ...

class TransactionRepository(Protocol):
    def add(self, transaction: Transaction) -> Transaction: ...
    def confirm(self, transaction_ids: Sequence[UUID], block_id: UUID) -> int: ...
    def get(self, transaction_id: UUID) -> Transaction | None: ...
    def list(self, *, status: TransactionStatus | None = None, wallet_id: UUID | None = None,
             limit: int = 100) -> Sequence[Transaction]: ...
    def pending(self) -> Sequence[Transaction]: ...
    def of_block(self, block_id: UUID) -> Sequence[Transaction]: ...
    def balance_terms(self, wallet_id: UUID) -> BalanceTerms: ...
    def signature_exists(self, signature: str) -> bool: ...
    def count(self) -> int: ...

class UnitOfWork(Protocol):
    wallets: WalletRepository
    blocks: BlockRepository
    transactions: TransactionRepository
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exc_info: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

`tests/integration/conftest.py`: lee `DATABASE_URL` del entorno o de `.env`; si falta, falla con un mensaje que dice `docker compose up -d` (mejor fallar que omitir, porque una prueba omitida en silencio no verifica nada — comentario obligatorio). Antes de cada prueba borra las filas en orden inverso a las claves foráneas (`transactions`, `blocks`, `wallets`) con `DELETE`, nunca con `TRUNCATE`, para no ejecutar DDL desde las pruebas. Expone el fixture `ledger` (la fachada armada) y `conexion` (para escribir directo en la base, que es como se prueban REQ-19 y la alteración).

- [ ] **Step 5: Levantar la base y correr las pruebas**

```bash
cp .env.example .env   # y completar MASTER_KEY
docker compose up -d   # o podman compose up -d
.venv/bin/pytest tests -v
```

Expected: las de unidad pasan y las de integración pasan contra PostgreSQL 16

- [ ] **Step 6: Commit**

```bash
git add db compose.yaml .env.example src/persistence tests
git commit -m "feat: esquema del ledger, contenedor de PostgreSQL y puertos de persistencia"
```

---

### Task 6: Adaptadores PostgreSQL

**Files:**

- Create: `src/persistence/postgres.py`, `tests/integration/test_req_01_wallet_en_base.py`, `tests/integration/test_req_03_firma_repetida.py`, `tests/integration/test_req_11_rechazo_en_base.py`, `tests/integration/test_req_13_historial.py`, `tests/integration/test_req_19_errores_del_motor.py`

**Interfaces:**

- Consumes: los protocolos de la tarea 5.
- Produces: `PostgresWalletRepository`, `PostgresBlockRepository`, `PostgresTransactionRepository`, cada uno con `__init__(self, connection: psycopg.Connection)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""REQ-19: una violación de CHECK, clave foránea o unicidad levanta el error del motor."""
def test_req_19_monto_no_positivo_levanta_check_violation(conexion):
    with pytest.raises(psycopg.errors.CheckViolation):
        conexion.execute("INSERT INTO transactions (sender_id, receiver_id, amount, signature) VALUES (%s, %s, %s, %s)",
                         (sender, receiver, Decimal("-1"), "firma-x"))
    conexion.rollback()


def test_req_19_wallet_inexistente_levanta_foreign_key_violation(conexion): ...


def test_req_03_firma_repetida_levanta_unique_violation(transacciones, conexion):
    """REQ-03: presentar dos veces la misma firma produce una admisión y un rechazo."""
```

Además: REQ-01 (la pública queda única y no vacía; el material en claro de la privada no aparece en la base), REQ-11 (una fila `rejected` se guarda con `block_id` nulo; una `confirmed` sin bloque levanta `CheckViolation`), REQ-13 (listados con filtro por estado y por wallet, y conteos).

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/integration -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.persistence.postgres'`

- [ ] **Step 3: Implementar `src/persistence/postgres.py`**

Tres clases con `__init__(self, connection: psycopg.Connection)`, filas como diccionarios, y **sin** `except` que traduzca errores (comentario obligatorio: REQ-19 exige que el error del motor llegue crudo). La conexión no se cierra desde los repositorios: la cierra quien la abrió. `balance_terms` resuelve las tres sumas con una sola consulta agregada sobre `transactions` filtrando `wallet_id` y `status`.

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests -v`
Expected: todas pasan

- [ ] **Step 5: Commit**

```bash
git add src/persistence/postgres.py tests/integration
git commit -m "feat: adaptadores PostgreSQL con los errores del motor sin traducir"
```

---

### Task 7: Unidad de trabajo, génesis y agrupación atómica

**Files:**

- Create: `src/persistence/unit_of_work.py`, `src/persistence/factory.py`, `src/bootstrap.py`, `tests/integration/test_req_08_encadenamiento.py`, `tests/integration/test_req_09_agrupacion.py`, `tests/integration/test_req_12_coherencia.py`, `tests/integration/test_req_14_genesis.py`, `tests/integration/test_req_18_atomicidad.py`
- Modify: `src/domain/blockchain.py` (se le agrega la clase `Blockchain`)

**Interfaces:**

- Consumes: los tres repositorios, `available_balance`, `Block.calculate_hash`, `Transaction.validate`.
- Produces: `Blockchain` con `register_wallet()`, `create_transaction(...)`, `group_pending()`, `verify_chain()` (tarea 8), `wallet_history(...)`, `ledger_state()`; `ensure_genesis(...)`; `TransactionResult`; `VerificationReport`; `ledger()` y `open_ledger()` en `factory.py`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""REQ-18: si falla una de las dos escrituras, ninguna queda aplicada."""
def test_req_18_si_falla_la_confirmacion_no_queda_el_bloque(ledger, repositorio_que_falla):
    with pytest.raises(FalloForzado):
        ledger.group_pending()
    assert ledger.blocks.count() == 1          # solo el génesis
    assert all(t.status is not TransactionStatus.CONFIRMED for t in ledger.transactions.list())
```

`repositorio_que_falla` envuelve el repositorio real de transacciones y levanta `FalloForzado` al confirmar: es la forma de provocar el fallo de la segunda escritura sin depender de la suerte (comentario obligatorio). Las demás pruebas cubren REQ-08 (el `previous_hash` del bloque nuevo es el hash del último), REQ-09 (tras agrupar, las del pool quedan confirmadas y ligadas al bloque), REQ-12 (ninguna escritura deja una confirmada sin bloque ni una pendiente con bloque), REQ-14 (existe el bloque de índice cero con hash previo de sesenta y cuatro ceros, y `ensure_genesis` es idempotente).

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/integration -v`
Expected: FAIL con `ImportError: cannot import name 'Blockchain'`

- [ ] **Step 3: Implementar**

```python
@dataclass(frozen=True, slots=True)
class TransactionResult:
    accepted: bool
    reason: RejectionReason | None
    stored: Transaction | None

class Blockchain:
    def __init__(self, *, wallets: WalletRepository, blocks: BlockRepository,
                 transactions: TransactionRepository, unit_of_work: Callable[[], UnitOfWork],
                 master_key: bytes, clock: Callable[[], datetime]) -> None
    def register_wallet(self) -> Wallet
    def create_transaction(self, *, sender_id: UUID, receiver_id: UUID, amount: Decimal,
                           transaction_id: UUID | None = None, created_at: datetime | None = None) -> TransactionResult
    def group_pending(self) -> Block | None
    def wallet_history(self, wallet_id: UUID) -> Sequence[Transaction]
    def ledger_state(self) -> dict[str, int]

def ensure_genesis(chain: Blockchain) -> Block
```

Notas que la firma y las pruebas no determinan: `register_wallet` genera el par y guarda el material cifrado; `create_transaction` resuelve las llaves públicas, calcula el saldo con `balance_terms`, valida, firma y decide la fila según la tabla del diseño (con fila `rejected` solo cuando el esquema la admite); `group_pending` lee el pool, arma el bloque con el hash del último, calcula el suyo y hace **las dos escrituras dentro de una sola unidad de trabajo** (comentario obligatorio: es la razón del `COMMIT` único que exige REQ-18); `clock` se inyecta para que las pruebas sean deterministas.

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests -v`
Expected: todas pasan

- [ ] **Step 5: Commit**

```bash
git add src/domain/blockchain.py src/persistence src/bootstrap.py tests/integration
git commit -m "feat: agrupacion atomica, encadenamiento por hash y bloque genesis"
```

---

### Task 8: Verificación de la cadena y localización de la alteración

**Files:**

- Modify: `src/domain/blockchain.py` (se le agrega `verify_chain`)
- Create: `tests/dobles.py`, `tests/unit/test_req_10_verificacion.py`, `tests/integration/test_req_10_alteracion.py`, `tests/integration/test_req_22_solo_lee.py`

**Interfaces:**

- Consumes: `Block.calculate_hash`, los repositorios.
- Produces: `VerificationReport(valid: bool, altered_block_index: int | None)` y `Blockchain.verify_chain() -> VerificationReport`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/unit/test_req_10_verificacion.py` con los dobles en memoria de `tests/dobles.py` (**RF-3** y **RF-4**):

```python
"""REQ-10: alterar un eslabón o una transacción confirmada señala desde dónde."""
def test_req_10_cadena_intacta_es_valida(cadena_de_tres_bloques): ...


def test_req_10_monto_alterado_señala_ese_bloque(cadena_de_tres_bloques): ...


def test_req_10_rf3_hueco_en_los_indices_señala_donde_deja_de_encadenar():
    bloques = [bloque(0), bloque(1), bloque(3)]
    assert chain.verify_chain().altered_block_index == 3


def test_req_10_rf3_previous_hash_huerfano_señala_ese_bloque(): ...


def test_req_10_rf4_marca_de_tiempo_del_genesis_alterada_se_detecta(cadena_de_tres_bloques): ...
```

`tests/integration/test_req_10_alteracion.py` es la demostración del proyecto: arma la cadena con la aplicación, altera una transacción confirmada con `UPDATE` directo y pide la verificación. `tests/integration/test_req_22_solo_lee.py` guarda el contenido de las tres tablas antes y después y exige que no cambie.

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests -v`
Expected: FAIL con `ImportError: cannot import name 'VerificationReport'`

- [ ] **Step 3: Implementar `verify_chain`**

Recorre los bloques por índice; para cada uno recalcula `calculate_hash` con sus transacciones y lo compara con el hash guardado; para cada bloque desde el índice 1 compara su `previous_hash` con el hash guardado del anterior. Ante la primera discrepancia detiene el recorrido y devuelve el índice. Recalcula también el génesis (decisión 13 del diseño: sin eso, alterar su marca de tiempo pasaría inadvertido — comentario obligatorio).

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests -v`
Expected: todas pasan

- [ ] **Step 5: Commit**

```bash
git add src/domain/blockchain.py tests/dobles.py tests/unit tests/integration
git commit -m "feat: verificacion de la cadena que localiza la alteracion"
```

---

### Task 9: Arranque y datos de demostración

**Files:**

- Modify: `src/bootstrap.py`
- Create: `tests/integration/test_bootstrap.py`

**Interfaces:**

- Consumes: `ledger()`, `ensure_genesis`, `Blockchain`.
- Produces: `python -m src.bootstrap` idempotente que asegura el génesis y, si la base está vacía de wallets, carga la demostración.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""Los datos de demostración representan el caso del eje y cumplen la regla de saldo."""
def test_los_aportes_financian_los_retiros(base_vacia_ejecutando_bootstrap):
    fondo = base_vacia_ejecutando_bootstrap.wallets.get_by_public_key(FONDO)
    asociados = [w for w in base_vacia_ejecutando_bootstrap.wallets.list() if w.public_key != FONDO]
    assert asociados, "la demostración tiene que tener asociados"
    for asociado in asociados:
        assert base_vacia_ejecutando_bootstrap.available_balance(asociado.id) >= 0


def test_el_bootstrap_es_idempotente(base_vacia_ejecutando_bootstrap):
    antes = base_vacia_ejecutando_bootstrap.ledger_state()
    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)
    assert base_vacia_ejecutando_bootstrap.ledger_state() == antes
```

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `.venv/bin/pytest tests/integration/test_bootstrap.py -v`
Expected: FAIL porque `src.bootstrap` solo asegura el génesis

- [ ] **Step 3: Implementar la demostración**

Un módulo con `main()` que: asegura el génesis; si no hay wallets, crea la wallet del fondo y tres asociados; registra los aportes de cada asociado hacia el fondo; agrupa; y deja los retiros del fondo hacia los asociados como transacciones. El identificador del fondo es una constante del módulo, y el comentario que la acompaña explica que la distinción aporte/retiro no tiene columna y vive en la dirección respecto de esa wallet (decisión 8 del diseño). Los montos se eligen para que **ningún saldo quede negativo**, que es el defecto que el eje heredaba en sus datos.

- [ ] **Step 4: Correr la prueba y ver que pasa**

Run: `.venv/bin/pytest tests/integration/test_bootstrap.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/bootstrap.py tests/integration/test_bootstrap.py
git commit -m "feat: datos de demostracion de aportes y retiros con saldos validos"
```

---

### Task 10: Aplicación Flask con las cinco rutas

**Files:**

- Create: `src/web/__init__.py`, `src/web/app.py`, `src/web/templates/base.html`, `index.html`, `wallet.html`, `transaccion.html`, `bloque.html`, `verificar.html`, `historial.html`, `tests/integration/test_req_24_rutas.py`, `tests/unit/test_req_29_presentacion.py`

**Interfaces:**

- Consumes: `ledger()`, `Blockchain`.
- Produces: `create_app(chain_factory) -> Flask` y las cinco rutas del eje.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""REQ-24 a REQ-28: cada ruta hace su caso de uso y devuelve una página con el resultado."""
def test_req_24_post_wallets_devuelve_200_con_la_publica(cliente): ...


def test_req_25_post_transacciones_devuelve_el_estado(cliente): ...


def test_req_26_post_bloques_devuelve_el_bloque_creado(cliente): ...


def test_req_27_get_verificar_devuelve_el_dictamen_y_el_bloque_alterado(cliente, cadena_alterada): ...


def test_req_28_get_historial_devuelve_las_transacciones_con_su_estado(cliente): ...


def test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara(cliente):
    assert cliente.get("/historial/no-es-un-uuid").status_code == 404
    assert cliente.get(f"/historial/{uuid4()}").status_code == 404
```

`tests/unit/test_req_29_presentacion.py` (REQ-29, sin base de datos):

```python
"""REQ-29: ninguna ruta decide reglas ni ejecuta consultas."""
def test_req_29_la_presentacion_no_importa_persistencia_ni_psycopg():
    fuente = (pathlib.Path("src/web/app.py")).read_text(encoding="utf-8")
    assert "psycopg" not in fuente and "persistence" not in fuente
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.web'`

- [ ] **Step 3: Implementar la aplicación y las plantillas**

Una ruta por caso de uso; ninguna decide reglas ni ejecuta SQL: toman el formulario, llaman a `Blockchain` o a `Wallet` y pintan la plantilla con el resultado y, cuando hay rechazo, con su motivo (comentario obligatorio: el motivo se muestra porque el CU-02 lo pide). La portada `GET /` muestra los conteos del ledger y enlaces a los cinco casos de uso. El `404` de `historial` se logra validando el UUID en la ruta y devolviendo la plantilla de error, no un error del motor (RF-5).

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `.venv/bin/pytest tests -v`
Expected: todas pasan

- [ ] **Step 5: Commit**

```bash
git add src/web tests
git commit -m "feat: aplicacion Flask con las cinco rutas del eje"
```

---

### Task 11: Explicación, corrida en el piso y aceptación

**Files:**

- Create: `docs/recorrido-de-casos-de-uso.md`, `README.md`, `tests/test_explicacion.py`
- Modify: `requirements.txt` (versiones fijas definitivas)

**Interfaces:**

- Consumes: todo lo anterior.
- Produces: el recorrido, el README y la prueba de coherencia.

- [ ] **Step 1: Escribir la prueba de coherencia que falla**

```python
"""La explicación no puede quedar huérfana: cada caso de uso en el recorrido, cada REQ con su prueba."""
def test_cada_caso_de_uso_aparece_en_el_recorrido():
    recorrido = pathlib.Path("docs/recorrido-de-casos-de-uso.md").read_text(encoding="utf-8")
    faltantes = [cu for cu in ("CU-01", "CU-02", "CU-03", "CU-04", "CU-05") if cu not in recorrido]
    assert faltantes == []


def test_cada_requerimiento_tiene_su_prueba():
    nombres = "\n".join(p.name for p in pathlib.Path("tests").rglob("test_*.py"))
    faltantes = [f"REQ-{n:02d}" for n in range(1, 30) if f"req_{n:02d}" not in nombres]
    assert faltantes == []
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/pytest tests/test_explicacion.py -v`
Expected: FAIL porque el recorrido no existe

- [ ] **Step 3: Escribir el recorrido y el README**

`docs/recorrido-de-casos-de-uso.md`: una sección por caso de uso que sigue la petición real —qué hace el usuario, qué ruta la recibe, qué método del dominio decide, qué tabla se toca, qué consulta se ejecuta y qué prueba lo demuestra— y cierra con las preguntas probables del tutor y dónde vive cada respuesta.

`README.md`: qué es y de dónde viene (cita el eje por nombre), cómo correrlo paso a paso en Windows, macOS y Linux con `docker compose` o `podman compose`, cómo correr las pruebas de reglas sin base de datos y las de integración, cómo reproducir la demostración de alteración, y por dónde empezar a leer el código.

- [ ] **Step 4: Correr todo y ver que pasa**

Run: `.venv/bin/pytest tests -v`
Expected: todas pasan, incluida la coherencia

- [ ] **Step 5: Correr las pruebas de reglas con la base apagada (REQ-17)**

```bash
docker compose down   # o podman compose down
.venv/bin/pytest tests/unit -v
```

Expected: todas pasan sin base de datos

- [ ] **Step 6: Correr la suite contra PostgreSQL 16 y dentro del piso de Python (REQ-20, REQ-23)**

```bash
docker compose up -d
.venv/bin/pytest tests -v
.venv/bin/pip freeze > requirements.txt
# y una vez contra el contenedor del piso, montando el código en solo lectura
```

Expected: verde en los tres entornos; el veredicto dentro del contenedor es el código de salida de `pytest`

- [ ] **Step 7: Reproducir la demostración de alteración a mano**

```bash
psql "$DATABASE_URL" -c "UPDATE transactions SET amount = amount + 1 WHERE status = 'confirmed' LIMIT 1;"  # el LIMIT va en un CTE
curl -s localhost:5000/verificar | grep -i alterad
```

Expected: la verificación señala el bloque donde empieza la alteración

- [ ] **Step 8: Commit**

```bash
git add README.md docs tests/test_explicacion.py requirements.txt
git commit -m "docs: recorrido de casos de uso, README y coherencia de la explicacion"
```

---

## Autoevaluación del plan

- **Cobertura del eje**: REQ-01 y REQ-23 (tareas 1 y 11); REQ-02 y REQ-04 (tarea 2); REQ-07 (tarea 3); REQ-05 y REQ-06 (tarea 4); REQ-15, REQ-16 y REQ-21 (tarea 5); REQ-03, REQ-11, REQ-13 y REQ-19 (tarea 6); REQ-08, REQ-09, REQ-12, REQ-14 y REQ-18 (tarea 7); REQ-10 y REQ-22 (tarea 8); REQ-24 a REQ-29 (tarea 10); REQ-17 y REQ-20 (tarea 11). Los cinco casos de uso quedan cubiertos por las pruebas de recorrido de las tareas 6, 7, 8 y 10.
- **Review Focus**: RF-1 y RF-2 en la tarea 2; RF-3 y RF-4 en la tarea 8; RF-5 en la tarea 10.
- **Consistencia de tipos**: `validate` recibe `available` y `signature_exists` en las tareas 2, 4 y 7; `calculate_hash(transactions)` en 3 y 8; `balance_terms` en 5, 6 y 7; `VerificationReport` en 7 y 8.
- **Explicabilidad**: cada tarea incluye los docstrings y los comentarios del porqué, y la tarea 11 los verifica contra el recorrido.

---

### Task 12: Entrada visible al CU-05 y cierre del proyecto en el README

Surgió al probar la aplicación: el CU-05 funciona, pero para demostrarlo hay que teclear a mano una llave pública de 66 caracteres que no aparece en ningún listado, porque `GET /wallets` solo muestra el formulario y las wallets existentes únicamente se ven dentro del formulario de transacciones, donde no se pueden copiar.

**Files:**

- Modify: `src/web/app.py` (solo la rama `GET` de la ruta `wallets`), `src/web/templates/wallet.html`, `src/web/templates/index.html`, `src/web/templates/historial.html`, `README.md`
- Create: `tests/integration/test_req_28_historial_desde_la_lista.py`

**Interfaces:**

- Consumes: `Blockchain.wallets.list()`, `Blockchain.wallet_history(wallet_id)`, `Blockchain.register_wallet()`.
- Produces: la ruta `GET /wallets` renderiza además `wallets=<secuencia de Wallet>`. **No se agregan rutas**: las cinco del eje se mantienen, y la lista va dentro de una que ya existe.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""REQ-28 y CU-05: el historial de cualquier wallet se alcanza desde la lista de wallets."""
def test_req_28_la_lista_de_wallets_lleva_al_historial(cliente, wallet_de_prueba):
    listado = cliente.get("/wallets")
    assert listado.status_code == 200
    cuerpo = listado.get_data(as_text=True)
    assert wallet_de_prueba.public_key in cuerpo      # la llave completa, copiable
    enlace = f"/historial/{wallet_de_prueba.id}"
    assert enlace in cuerpo                            # el enlace directo
    assert cliente.get(enlace).status_code == 200       # y el enlace funciona
```

El `cliente` y su forma de sembrar datos ya existen en `tests/integration/test_req_24_rutas.py`; replica esa forma con `base_limpia` y una wallet registrada por la fachada.

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `.venv/bin/pytest tests/integration/test_req_28_historial_desde_la_lista.py -v`
Expected: FAIL porque la lista no aparece en la página

- [ ] **Step 3: Implementar**

`GET /wallets` pasa también `wallets=chain.wallets.list()`. `wallet.html` lista las wallets registradas con la llave pública **completa** dentro de `<code>` (para poder seleccionarla y copiarla), su identificador y un enlace «Ver su historial». `historial.html` enlaza de vuelta a `/wallets`. `index.html` reemplaza la frase que manda a teclear el identificador por el enlace a la lista. Nada de reglas ni consultas en la ruta (REQ-29).

- [ ] **Step 4: Correr la suite completa**

Run: `.venv/bin/pytest tests -q`
Expected: verde, con una prueba más

- [ ] **Step 5: README — apagar y limpiar**

Agregar una sección que cubra: detener la aplicación (Ctrl+C); `docker compose down` conserva los datos y `docker compose down -v` borra el volumen, tras lo cual el esquema se reaplica solo en el próximo `up` y hay que volver a sembrar con `python -m src.bootstrap`; cómo deshacer la alteración de la demostración; y qué se puede borrar sin miedo (`.venv/`, `.reference/`, `.superpowers/`, `.legacy-project/` y `.env`, advirtiendo que borrar `.env` obliga a generar otra `MASTER_KEY` y volver a sembrar, porque las wallets ya guardadas quedan ilegibles).

- [ ] **Step 6: Commit**

```bash
git add src/web README.md tests/integration/test_req_28_historial_desde_la_lista.py
git commit -m "feat: el historial de cada wallet se alcanza desde la lista, y el README explica como apagar y limpiar"
```

---

### Task 13: Redistribución de la interfaz (opción B)

Aprobado por el humano sobre una maqueta. Tres cambios: la lista de wallets pasa a un panel lateral visible en todas las páginas; los identificadores y los valores numéricos se muestran en monoespaciada y en forma corta, con botón de copiar y el valor completo a un clic; y la interfaz deja de explicar el proyecto —nada de «CU-0X» ni de párrafos sobre el eje—. Prioridad a lo funcional sobre lo bonito.

**Files:**

- Modify: `src/web/app.py`, `src/web/templates/base.html`, `src/web/templates/index.html`, `src/web/templates/wallet.html`, `src/web/templates/transaccion.html`, `src/web/templates/bloque.html`, `src/web/templates/verificar.html`, `src/web/templates/historial.html`, `tests/integration/test_req_24_rutas.py`, `tests/integration/test_req_28_historial_desde_la_lista.py`, `docs/recorrido-de-casos-de-uso.md`
- Create: `src/web/templates/_macros.html`

**Interfaces:**

- `create_app` gana un procesador de contexto que expone `wallets_del_panel` —la lista de wallets de la fachada— a todas las plantillas, para que el panel lateral no dependa de que cada ruta lo pase.
- `_macros.html` expone `dato(valor)` (forma corta de ocho y cuatro caracteres separados por puntos suspensivos) y `copiar(valor)` (el botón con `data-copiar`), reutilizables por las siete plantillas.
- `base.html` define la pila monoespaciada (`ui-monospace, "Cascadia Code", Consolas, monospace`) para `code` y para la clase `.mono`, y el guion de ocho líneas que conecta los botones `[data-copiar]` con `navigator.clipboard`.
- Ninguna ruta nueva: siguen siendo las cinco del eje (REQ-24 a REQ-29).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""REQ-29: la interfaz no explica el proyecto. Sin «CU-0X» ni prosa sobre el eje."""
def test_req_29_la_interfaz_no_explica_el_proyecto(cliente):
    for ruta in ("/", "/wallets", "/transacciones", "/bloques", "/verificar"):
        cuerpo = cliente.get(ruta).get_data(as_text=True)
        assert "CU-0" not in cuerpo


"""REQ-29: el panel lateral lista las wallets en todas las páginas."""
def test_req_29_el_panel_lateral_aparece_en_todas_las_paginas(cliente, wallet_de_prueba):
    for ruta in ("/", "/transacciones", "/verificar", f"/historial/{wallet_de_prueba.id}"):
        cuerpo = cliente.get(ruta).get_data(as_text=True)
        assert f"/historial/{wallet_de_prueba.id}" in cuerpo
        assert wallet_de_prueba.public_key in cuerpo          # el valor completo sigue disponible
        assert wallet_de_prueba.public_key[:8] in cuerpo      # y la forma corta es la que se ve


"""REQ-29: los identificadores y los montos van en monoespaciada."""
def test_req_29_los_datos_numericos_van_en_monoespaciada(cliente, wallet_de_prueba):
    cuerpo = cliente.get(f"/historial/{wallet_de_prueba.id}").get_data(as_text=True)
    assert 'class="mono"' in cuerpo
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `.venv/bin/pytest tests/integration -k "explica or panel or monoespaciada" -v`
Expected: FAIL las tres

- [ ] **Step 3: Implementar el armazón y las plantillas**

`base.html`: barra superior con el nombre de la aplicación y cuatro enlaces —Registrar wallet, Nueva transacción, Cerrar bloque, Verificar cadena—; debajo, dos columnas: el panel lateral con «Wallets» y una fila por wallet (forma corta en monoespaciada, botón de copiar, enlace a su historial; «Todavía no hay wallets» si la lista está vacía) y el área de contenido. Nada de párrafos explicativos ni de números de caso de uso en los títulos: «Registrar wallet», «Nueva transacción», «Cerrar bloque», «Verificar cadena», «Historial». La portada muestra solo los tres conteos del ledger. Sin perseguir estética: legible y predecible.

`_macros.html` con `dato(valor)` y `copiar(valor)`; toda aparición de un identificador, hash, monto, fecha o conteo usa `code`/`.mono` y, si es un identificador, la forma corta con el valor completo en el atributo `title` y en `data-copiar`.

`app.py`: procesador de contexto para `wallets_del_panel`; las rutas siguen llamando solo a la fachada (REQ-29).

- [ ] **Step 4: Correr la suite completa**

Run: `.venv/bin/pytest tests -q`
Expected: verde. Si alguna prueba de las tareas 10 o 12 afirmaba el texto «CU-0» o el identificador completo _visible_, actualizala a la nueva presentación sin perder la afirmación: el valor completo sigue en el marcado y la forma corta es la que se ve.

- [ ] **Step 5: Poner al día el recorrido**

`docs/recorrido-de-casos-de-uso.md` describe la interfaz para la sustentación: donde diga cómo se titula o se ve una página, tiene que coincidir con lo que la interfaz muestra ahora. Los nombres de caso de uso siguen en el documento —es el documento, no la interfaz—, pero no puede describir textos que ya no existen.

- [ ] **Step 6: Verificación y commit**

Run: `.venv/bin/ruff check .` y `.venv/bin/pytest tests -q`
Run: `.venv/bin/env -u DATABASE_URL .venv/bin/pytest tests/unit -q`

```bash
git add src/web tests docs/recorrido-de-casos-de-uso.md
git commit -m "feat: panel lateral con las wallets y datos en monoespaciada, sin textos explicativos en la interfaz"
```

---

### Task 14: La conexión falla rápido, y el ejemplo no usa `localhost`

Surgió probando en Windows: el compañero movió el puerto de la base porque otro motor lo ocupaba, y el arranque «parecía congelado». Dos causas del código y de la plantilla, no del compañero: `psycopg.connect` no lleva tiempo de espera, así que un puerto que no contesta espera lo que tarde el sistema operativo; y `.env.example` usa `localhost`, que en Windows puede resolverse primero a IPv6 (`::1`) mientras el contenedor publica en IPv4. Además, el arranque no imprime nada hasta el final, así que una demora se ve igual que un cuelgue.

**Files:**

- Modify: `src/persistence/factory.py`, `.env.example`, `README.md`
- Create: `tests/unit/test_req_21_cadena_de_conexion.py`

**Interfaces:**

- `factory.database_url()` sigue devolviendo la cadena de conexión, pero **normalizada**: si la cadena no trae `connect_timeout`, le pone `5`. Como la cadena se resuelve una sola vez y se comparte con la unidad de trabajo, las dos conexiones del ledger quedan cubiertas.
- Nada más cambia de comportamiento: un `connect_timeout` explícito en la cadena se respeta.

- [ ] **Step 1: Escribir la prueba que falla**

El snippet original —`monkeypatch.setenv("DATABASE_URL", …)` y afirmar con `psycopg.conninfo.conninfo_to_dict`— **es inviable**: el guard de REQ-17 (`tests/test_explicacion.py::test_req_17_las_pruebas_unitarias_no_dependen_de_la_base`) prohíbe en `tests/unit/` tanto el import de `psycopg` como el substring `DATABASE_URL` en el contenido de cualquier archivo. La prueba se escribió sin importar el driver, alimentando la fábrica por su lector del entorno y afirmando los parámetros de la cadena devuelta:

```python
def _cadena_del_entorno(monkeypatch, cadena: str) -> None:
    """Hace que la fábrica lea `cadena` como si viniera del entorno."""
    monkeypatch.setattr(factory, "_env_value", lambda name: cadena)


def test_req_21_la_cadena_sin_tiempo_de_espera_recibe_cinco_segundos(monkeypatch):
    """REQ-21: una cadena sin tiempo de espera no puede dejar la aplicación esperando."""
    _cadena_del_entorno(monkeypatch, SIN_TIEMPO_DE_ESPERA)
    parametros = _parametros(factory.database_url())
    assert parametros["host"] == "127.0.0.1"
    assert parametros["port"] == "55432"
    assert parametros["connect_timeout"] == "5"


def test_req_21_un_tiempo_de_espera_explicito_se_respeta(monkeypatch):
    """REQ-21: un tiempo de espera explícito en la cadena manda sobre el valor por defecto."""
    _cadena_del_entorno(monkeypatch, CON_TIEMPO_DE_ESPERA)
    parametros = _parametros(factory.database_url())
    assert parametros["connect_timeout"] == "30"
```

`_parametros` separa la forma canónica de libpq (`clave=valor`) que devuelve `database_url()`, y lo hace sin `psycopg`. El archivo completo es `tests/unit/test_req_21_cadena_de_conexion.py`.

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `.venv/bin/pytest tests/unit/test_req_21_cadena_de_conexion.py -v`
Expected: FAIL con `KeyError: 'host'`: sin la normalización la cadena cruda es una URL, no la forma canónica de libpq, así que no hay parámetros que interpretar.

- [ ] **Step 3: Implementar en `database_url()`**

Normalizar con `psycopg.conninfo.conninfo_to_dict` y `make_conninfo`, aplicando `params.setdefault("connect_timeout", "5")`. El comentario explica el porqué: sin tiempo de espera, librería y sistema operativo deciden cuánto aguantar, y un puerto mal puesto parece un cuelgue en lugar de un error.

- [ ] **Step 4: `.env.example`**

`127.0.0.1` en lugar de `localhost`, y `?connect_timeout=5` al final de la cadena, con un comentario que diga por qué: en Windows `localhost` puede resolverse primero a IPv6 y el contenedor publica en IPv4.

- [ ] **Step 5: README**

En la puesta en marcha: que **cambiar el puerto obliga a recrear el contenedor** (`docker compose up -d`); editar `.env` no lo recrea. En los problemas conocidos: que si la aplicación parece quedarse pensando, se use `127.0.0.1` en lugar de `localhost`; y que ahora una conexión imposible falla en cinco segundos con el mensaje del motor.

- [ ] **Step 6: Suite completa, y commit**

Run: `.venv/bin/pytest tests -q` y `.venv/bin/ruff check .` y `env -u DATABASE_URL .venv/bin/pytest tests/unit -q`

```bash
git add src/persistence/factory.py tests/unit .env.example README.md
git commit -m "fix: la conexion falla rapido cuando el puerto no responde, y el ejemplo usa 127.0.0.1"
```

---

### Task 15: Sabotaje guiado del ledger

Herramienta de verificación y demostración, aprobada por el humano: `python -m src.sabotaje` sabotea el ledger a propósito, narra cada paso, espera a que el humano mire el navegador, y dice en cada caso qué se esperaba y qué pasó. No es parte del camino de la aplicación; entra a la lista cerrada de artefactos con esa justificación.

**Files:**

- Create: `src/sabotaje.py`, `tests/integration/test_sabotaje.py`
- Modify: `README.md`, `docs/superpowers/specs/2026-10-10-blockchain-transaccional-design.md`, este plan

**Interfaces:**

- `python -m src.sabotaje` — modo interactivo por defecto: imprime cada caso, lo aplica, dice qué mirar en el navegador y **espera un Enter**.
- `--sin-pausas` — lo mismo sin esperar a nadie, para la suite o un guion cerrado.
- `--destructivos` — agrega los tres casos que borran datos; sin esta bandera no se tocan.
- Cada caso se declara como un dato (`clave`, `titulo`, `que_hace`, `que_mirar`, `esperado`, `bloque_esperado`, `limite`, `destructivo`, `aplicar`, `restaurar`), separado de la narración, para que se pueda correr sin humano y para que una prueba pueda exigir que todo caso declare su veredicto.
- `esperado` es uno de tres valores: `cadena-valida`, `cadena-invalida`, `motor-rechaza`. Los casos que el sistema **no** detecta se declaran `cadena-valida` y traen `limite` con el porqué.
- Verificación de la cadena con `factory.ledger()`; sabotaje con SQL directo sobre una conexión propia que sale de `factory.database_url()`.
- Marcas de texto planas (`ok`, `coincide`, `no coincide`), sin emojis ni símbolos decorativos: las consolas de Windows no los renderizan.

**Los once casos**

| #   | Clave                       | Qué hace                                                         | Esperado                                                                             | Restaura                         |
| --- | --------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------- |
| 1   | `alterar-monto`             | `amount + 1` a una transacción confirmada                        | `cadena-invalida`, bloque 1                                                          | repone el monto                  |
| 2   | `alterar-hash`              | el hash de un bloque a sesenta y cuatro ceros                    | `cadena-invalida`, bloque 1                                                          | repone el hash                   |
| 3   | `mover-transaccion`         | una confirmada a otro bloque                                     | `cadena-invalida`                                                                    | repone `block_id`                |
| 4   | `borrar-transaccion`        | borra una confirmada                                             | `cadena-invalida`                                                                    | reinserta la fila                |
| 5   | `insertar-confirmada-falsa` | confirma una transacción con firma inventada dentro de un bloque | `cadena-invalida`                                                                    | borra la fila                    |
| 6   | `reutilizar-firma`          | inserta con una firma ya registrada                              | `motor-rechaza`                                                                      | no escribe nada                  |
| 7   | `violar-regla`              | inserta con emisor igual al receptor                             | `motor-rechaza`                                                                      | no escribe nada                  |
| 8   | `cambiar-llave-wallet`      | cambia la pública de una wallet                                  | `cadena-valida` — **límite**: el hash cubre transacciones, no el registro de wallets | repone la pública                |
| 9   | `pendiente-firma-invalida`  | inserta una pendiente con firma inventada                        | `cadena-valida` — **límite**: la verificación mira bloques, no el pool               | borra la fila                    |
| 10  | `borrar-genesis`            | borra el bloque índice 0 (destructivo)                           | `cadena-invalida`                                                                    | reinserta el bloque              |
| 11  | `truncar-cola`              | borra el último bloque y sus transacciones (destructivo)         | `cadena-valida` — **límite**: sin ancla externa no hay con qué comparar              | reinserta bloque y transacciones |

**Salida esperada** (por caso, con `[1/11]` y las líneas alineadas): qué hace, qué mirar en el navegador (`http://127.0.0.1:5000/verificar`), qué se espera, la espera del Enter, el resultado, y si restauró. Al final: un resumen con cuántos se detectaron y cuántos no, la lista de los no detectados con su porqué, y **las instrucciones de resembrado**, explícitas y en orden —bajar los contenedores borrando el volumen, volver a levantarlos, sembrar de nuevo con el arranque del proyecto— y qué tiene que decir la pantalla después: `http://127.0.0.1:5000/verificar` → «La cadena es válida».

**Comprobación previa antes del primer caso**: que la cadena esté válida (si ya viene alterada, se detiene y pide resembrar o restaurar) y que la aplicación responda con HTTP 200 en `/verificar`; si no responde, imprime el comando para levantarla y no sigue.

- [ ] **Step 1: Pruebas que fallan** — el catálogo declara veredicto, `que_hace`, `que_mirar` y, si no se detecta, el porqué; los destructivos están marcados. Y un recorrido headless que, para cada caso no destructivo: aplica, verifica contra lo declarado, restaura y comprueba que la cadena vuelve a ser válida.
- [ ] **Step 2: Ver el rojo.**
- [ ] **Step 3: Implementar `src/sabotaje.py`.**
- [ ] **Step 4: Suite completa en verde.**
- [ ] **Step 5: README** — una sección «Sabotaje guiado» con qué hace, los dos modos, los tres destructivos y las instrucciones de recuperación.
- [ ] **Step 6: Enmendar el diseño** — agregar `src/sabotaje.py` a la lista cerrada de artefactos de la decisión 11 con su justificación, y una línea en «Cómo se verifica»: es la capa que muestra en una corrida lo que las pruebas afirman por separado, incluidos los límites.
- [ ] **Step 7: Commit**

```bash
git add src/sabotaje.py tests/integration/test_sabotaje.py README.md docs
git commit -m "feat: sabotaje guiado del ledger, con los limites declarados y la recuperacion explicita"
```

---

### Task 16: Cierre de los menores diferidos

Siete cabos sueltos que quedaron anotados en las revisiones de las tareas 11 a 15, y dos que se cierran con un ruling de «no se arregla» en vez de con código. No cambia el comportamiento de la aplicación y no agrega funcionalidad: el objetivo es que el registro quede sin deudas y que dos pruebas dejen de afirmar de menos.

**Files:**
- Modify: `src/persistence/factory.py`, `src/web/templates/*`, `tests/unit/test_req_21_cadena_de_conexion.py`, `tests/test_explicacion.py`, `tests/integration/test_sabotaje.py`, `src/sabotaje.py`, `docs/recorrido-de-casos-de-uso.md`
- Sin archivos nuevos.

**Los siete arreglos**

1. **La frase «en todas las páginas».** En `docs/recorrido-de-casos-de-uso.md` y en el nombre de una prueba sigue diciendo que el panel de wallets aparece en todas las páginas. Ya no es cierto: el panel lo pasa explícitamente cada ruta de trabajo y la portada de error no lo lleva. Buscar la frase con `grep -rn "todas las páginas"`, mirar qué rutas pasan `wallets_del_panel` y escribir la verdad.
2. **La prueba del copiado lee la plantilla y no el JavaScript.** Hoy afirma que el atributo está en el marcado, pero no que el guion lo use. Convertirla en una prueba de contrato: el selector que busca el JavaScript y el atributo que escribe la macro tienen que ser el mismo, y la prueba falla si cualquiera de los dos lados cambia solo.
3. **El nombre de la variable de entorno en una constante.** En `factory.py`, el nombre de la variable hoy aparece como literal. Ponerlo en una constante del módulo, usarla en el lector, y que la prueba de la cadena de conexión vuelva a `monkeypatch.setenv(constante, …)`: así ejercita el camino real del entorno en vez de sustituir el lector privado. El guard de REQ-17 sigue igual: el literal no puede aparecer en `tests/unit/`.
4. **`open_ledger(..., database_dsn=...)` no se normaliza.** Extraer la normalización a una función del módulo y aplicarla en los dos lugares donde entra una cadena —el lector del entorno y el argumento explícito—, con una prueba de la función y otra de que el argumento explícito también sale con `connect_timeout`.
5. **El bloque esperado está fijo en 1.** En los casos `alterar-monto` y `alterar-hash`, `bloque_esperado: 1` depende de la forma del sembrado de demostración. Que el valor esperado salga del objeto que el caso altera —el bloque donde vive la transacción, el bloque cuyo hash se cambia—, y que la comparación use ese valor. Si la forma del ledger cambia, el caso tiene que seguir coincidiendo.
6. **La sonda de la aplicación usa el puerto fijo 5000.** Que la dirección se pueda fijar por variable de entorno, con `http://127.0.0.1:5000` como valor por defecto, y que el mensaje de fallo diga cuál se intentó.
7. **Los conteos de la prueba están fijados al sembrado.** Las pruebas del sabotaje afirman `5|4|10`. Que capturen los conteos antes de la corrida y exijan que al terminar sean **los mismos**, en vez de afirmar números mágicos.

**Los dos que no se arreglan, con su razón**

- **La restauración del sabotaje no es transaccional.** No se arregla con una transacción: el daño tiene que verse desde la aplicación, que abre su propia conexión, así que la alteración **debe** quedar confirmada. Envolverla en una transacción haría invisible lo que la herramienta existe para mostrar. La mitigación ya está y es la correcta: el cierre imprime el resembrado y la segunda pausa muestra la vuelta.
- **El formateador de Markdown del workspace.** Reformatea los `.md` al guardar (el `*visible*` → `_visible_` de Prettier). No es un defecto del repositorio y no se toca desde acá; queda como nota de entorno.

- [ ] **Step 1: Las pruebas primero**, donde aplique (2, 3, 4, 5, 6, 7): escribir la que falla, verla fallar, arreglar.
- [ ] **Step 2: Los arreglos de documentación** (1).
- [ ] **Step 3: Suite completa** con base propia, `ruff` limpio, 119 pruebas que no deben encogerse.
- [ ] **Step 4: Commit**

```bash
git add src tests docs
git commit -m "refactor: cierra los menores diferidos de las revisiones anteriores"
```
