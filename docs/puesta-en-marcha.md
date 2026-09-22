# Puesta en marcha

Cómo levantar el entorno local y verificar que quedó bien. El modelo de datos está en `base-de-datos.md`; la estructura del código en `arquitectura.md`.

## Requisitos

- Docker y Docker Compose. En esta máquina el binario `docker` es un alias a `podman`.
- `make`, para los atajos del `Makefile`. Todos los comandos tienen su equivalente directo de Docker Compose, así que `make` es opcional.
- Cliente `psql` solo si se quiere conectar desde el anfitrión. El contenedor ya trae uno.
- Python 3.11 o superior, para el backend de `src/`.

## Configuración

```bash
cp .env.example .env
```

`.env` no se versiona. Si se cambia el usuario, la contraseña, el nombre de la base o el puerto, hay que hacerlo en ese archivo. Cualquier variable nueva se refleja también en `.env.example`, que sí es la plantilla de referencia del repositorio.

## Levantar la base

```bash
make up
# Equivalente: docker compose up -d
```

Postgres inicializa el volumen la primera vez y ejecuta en orden los scripts montados desde `database/init/`:

1. `01_schema.sql`, que crea la extensión `uuid-ossp` y las tablas.
2. `02_seed.sql`, que inserta los datos de prueba.

## Verificar

```bash
make tables   # lista las tablas
make schema   # describe wallets, blocks y transactions
make counts   # cuenta las filas de las tres tablas
make psql     # abre una sesión interactiva
```

Los mismos comandos, sin `make`:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"

docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT
     (SELECT count(*) FROM wallets) AS wallets,
     (SELECT count(*) FROM blocks) AS blocks,
     (SELECT count(*) FROM transactions) AS transactions;"
```

Con el seed aplicado, el conteo debe dar tres wallets, dos bloques y tres transacciones.

Desde el anfitrión, si hay `psql` instalado y las variables del `.env` están cargadas en la sesión:

```bash
set -a && . ./.env && set +a
psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
```

## Detener y reiniciar

```bash
make down    # detiene el contenedor conservando los datos
make logs    # sigue los logs del contenedor
make reset   # destruye el volumen y vuelve a aplicar esquema y seed
```

`make reset` es la única forma de que los scripts de `database/init/` se vuelvan a ejecutar, porque el contenedor solo los corre al crear el volumen. Equivale a `docker compose down -v` seguido de `docker compose up -d`.

## Problemas conocidos

- **La base no tiene las tablas**: el volumen ya existía de un intento anterior y los scripts de init no se volvieron a ejecutar. `make reset` lo resuelve.
- **El puerto está ocupado**: cambiar `POSTGRES_PORT` en `.env`. El contenedor siempre escucha en 5432 internamente; esa variable solo mueve el puerto publicado en el anfitrión.
- **`docker compose` falla al arrancar el motor de contenedores**: como `docker` es un alias a `podman` sin demonio, un fallo de configuración de podman aparece como un fallo de Docker. `podman info` muestra la causa real.

## Backend

El código vive en `src/`. El primer corte implementa la capa de persistencia y el acceso a datos: conexión, entidades y operaciones CRUD sobre las tres tablas. Las reglas de validación, la firma, el cálculo del hash y la verificación de la cadena todavía no están implementados.

### Preparar el entorno

```bash
make venv
```

Crea `.venv/` e instala las dependencias declaradas en `pyproject.toml`. Sin `make`:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Comprobar la conexión

```bash
make backend
# Equivalente: .venv/bin/python -m src.main
```

Se conecta, informa la versión del servidor y cuenta las filas de las tres tablas. No acepta argumentos ni ejecuta operaciones. Con el contenedor arriba y el seed aplicado, la salida es:

```
PostgreSQL: 16.15
wallets: 3
blocks: 2
transactions: 3
```

La versión del servidor cambia si se actualiza la imagen. Los conteos son los del seed de `02_seed.sql`: tres wallets, dos bloques y tres transacciones.

### Operar la base a mano

El CRUD se hace desde una sesión interactiva de Python. `open_ledger()` abre la conexión y arma los repositorios.

```bash
.venv/bin/python -i -c "from src.persistence.factory import open_ledger; chain = open_ledger()"
```

Dentro de la sesión:

```python
chain.counts()                                  # conteo de las tres tablas
chain.wallets.list()                            # lee todas las wallets
chain.blocks.list()                             # lee todos los bloques
chain.transactions.list()                       # lee todas las transacciones
chain.transactions.list(status=TransactionStatus.CONFIRMED)
chain.wallets.get(<uuid>)                       # una wallet, o None
chain.wallets.delete(<uuid>)                    # True si borró algo
```

Para crear una transacción pendiente hacen falta dos wallets distintas:

```python
from decimal import Decimal

wallets = chain.wallets.list()
chain.transactions.create(
    sender_id=wallets[0].id,
    receiver_id=wallets[1].id,
    amount=Decimal("10.00"),
    signature="firma_de_prueba",
)
```

Confirmar una transacción exige crear antes un bloque y asociarlo. El esquema rechaza una transacción confirmada sin bloque, y también una pendiente con bloque:

```python
from src.transaction import TransactionStatus

bloques = chain.blocks.list()
bloque = chain.blocks.create(
    block_index=len(bloques),
    previous_hash=bloques[-1].hash,
    block_hash="0" * 64,
)

transaccion = chain.transactions.get(<uuid>)
transaccion.status = TransactionStatus.CONFIRMED
transaccion.block_id = bloque.id
chain.transactions.update(transaccion)
```

La capa de persistencia no repite las reglas del esquema. Si una escritura viola un `CHECK`, una clave foránea o una restricción de unicidad, el error de PostgreSQL se muestra tal cual. Por eso crear un bloque con un `block_index` repetido, o borrar una wallet con transacciones asociadas, falla con el mensaje del motor y no con uno propio.

## Alcance de esta etapa

Hay contenedor, esquema, datos de prueba y un backend que se conecta y opera la base. Todavía no hay reglas de negocio: no se calculan hashes, no se firma, no se valida el saldo y no se verifica la integridad de la cadena. La base no se modifica desde el código: no hay DDL, porque la estructura del esquema está congelada.
