# Prototipo transaccional basado en blockchain

Nodo único de un ledger transaccional: wallets con par de llaves ECDSA, transacciones
firmadas que se validan antes de entrar al pool, agrupación en bloques encadenados por
hash SHA-256, verificación de integridad que localiza una alteración y una aplicación
web con las cinco rutas del eje.

## Qué es y de dónde viene

El eje del proyecto es el documento académico **`documentacion_proyecto_transaccionales.pdf`**
(46 páginas, Grupo 1, Universidad Manuela Beltrán). Ese documento fija el problema, los
29 requerimientos (REQ) con su criterio de aceptación, los 5 casos de uso (CU), las
clases del dominio, la arquitectura en capas, las rutas HTTP y el modelo relacional.
**Este repositorio no vuelve a decidir nada de eso: existe para hacer verdadero lo que
el eje describe como prototipo.** Su página 43 afirma que "el núcleo del prototipo ya
está implementado y probado"; este repositorio es la evidencia de ese párrafo.

Toda decisión que el eje no fija (curva, cifrado, contenido del hash, datos de
demostración) está declarada y numerada en
`docs/superpowers/specs/2026-10-10-blockchain-transaccional-design.md`, y el orden en
que se construyó, en `docs/superpowers/plans/2026-10-10-blockchain-transaccional-plan.md`.
La explicación de cómo se ejecuta cada caso de uso está en
`docs/recorrido-de-casos-de-uso.md`.

## Requisitos previos

- **Python 3.11 o superior** (REQ-20; el piso lo declara `pyproject.toml`).
- **Docker con `docker compose`** o **Podman con `podman compose`**. El mismo
  `compose.yaml` sirve para los dos.
- No hace falta tener `psql` instalado: se puede usar el que trae el contenedor.

Los comandos usan el intérprete del entorno virtual y nunca un guion de shell ni un
`Makefile`: todos los puntos de entrada son módulos de Python (`python -m ...`). En los
pasos, `<venv>` significa `.venv\Scripts\python` en Windows y `.venv/bin/python` en
macOS y Linux.

## Puesta en marcha

### 1. Crear el entorno virtual e instalar las dependencias

```text
python -m venv .venv
```

Windows:

```text
.venv\Scripts\python -m pip install -r requirements.txt
```

macOS y Linux:

```text
.venv/bin/python -m pip install -r requirements.txt
```

Si su instalación de Python no dejó `pip` dentro del entorno virtual, ejecute una vez
`<venv> -m ensurepip --upgrade` y repita la instalación.

### 2. Crear el archivo `.env`

`.env` no se versiona: guarda los secretos de verdad (REQ-21). Se parte de la
plantilla y se genera una clave maestra propia.

Windows:

```text
copy .env.example .env
```

macOS y Linux:

```text
cp .env.example .env
```

Genere una clave `MASTER_KEY` y reemplácela en `.env` (la de la plantilla es un
ejemplo, no la use):

```text
<venv> -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Revise que `POSTGRES_PORT` y el puerto de `DATABASE_URL` sean el mismo: el primero es
el puerto que se publica en el equipo y el segundo es el que usa la aplicación para
conectarse. Los valores de la plantilla funcionan tal cual.

### 3. Levantar PostgreSQL 16

```text
docker compose up -d
```

o, con Podman:

```text
podman compose up -d
```

El esquema de `db/init.sql` se aplica solo la primera vez que se crea el volumen. Para
volver a aplicarlo desde cero hay que borrar el volumen, lo que **borra los datos**:

```text
docker compose down -v
docker compose up -d
```

(con Podman, `podman compose down -v` y `podman compose up -d`).

Para comprobar que el contenedor está sano:

```text
docker compose ps
```

Si el contenedor no llega a estar sano, revise que `db/init.sql` sea legible por el
usuario `postgres` del contenedor: el punto de entrada lee el guion con ese usuario y,
si el archivo quedó con permisos `600` (un `git checkout` bajo un `umask` restrictivo
los reproduce), falla con `psql: error: /docker-entrypoint-initdb.d/01_init.sql:
Permission denied` y la base nunca arranca. En Linux o Podman se corrige con
`chmod 644 db/init.sql`.

### 4. Crear el génesis y cargar los datos de demostración

```text
<venv> -m src.bootstrap
```

El comando asegura el bloque génesis (es idempotente: correrlo dos veces no lo
duplica) y, si la base no tiene wallets, siembra la demostración. Imprime el hash del
génesis y el estado del ledger.

### 5. Levantar la aplicación

```text
<venv> -m src.web
```

Abra `http://127.0.0.1:5000`. La portada muestra los conteos de las tres tablas y los
enlaces a los cinco casos de uso.

## Las cinco rutas

| Ruta                      | Caso de uso | Qué hace                                                           |
| ------------------------- | ----------- | ------------------------------------------------------------------ |
| `POST /wallets`           | CU-01       | Registra una wallet y muestra su clave pública (REQ-24)            |
| `POST /transacciones`     | CU-02       | Firma, admite o rechaza, y devuelve el estado o el motivo (REQ-25) |
| `POST /bloques`           | CU-03       | Agrupa el pool en un bloque y muestra el eslabón creado (REQ-26)   |
| `GET /verificar`          | CU-04       | Devuelve el dictamen y, si falla, el bloque alterado (REQ-27)      |
| `GET /historial/<wallet>` | CU-05       | Lista las transacciones de una wallet con su estado (REQ-28)       |

`GET /historial/<wallet>` con un identificador que no es un UUID, o de una wallet que
no existe, responde la página de error con `404` y nunca un error del motor en
pantalla (RF-5).

## Los datos de demostración

`python -m src.bootstrap` deja **5 wallets, 4 bloques y 10 transacciones** (7
confirmadas y 3 pendientes, que son los retiros que `POST /bloques` agruparía a
continuación). El ciclo es el del eje: el capital de constitución entra al ledger, el
fondo reparte el capital de asociación, los asociados aportan y el fondo les gira
retiros.

| Actor          | Movimiento                                                                                               | Resultado                   |
| -------------- | -------------------------------------------------------------------------------------------------------- | --------------------------- |
| Constituyente  | Entrega 3000 al fondo                                                                                    | Saldo disponible `-3000`    |
| Fondo          | Recibe 3000 + tres aportes de 700; entrega tres capitales de 1000; giró tres retiros de 600 (pendientes) | `5100 - 3000 - 1800 = 300`  |
| Tres asociados | Reciben 1000 cada uno y aportan 700                                                                      | `1000 - 700 = 300` cada uno |

### La wallet del constituyente

**Quién es.** La wallet con identificador y llave fijos que `src/bootstrap.py` deriva
de `CONSTITUYENTE_SEED` y `CONSTITUYENTE_ID`. Es la contraparte de la primera fila del
ledger: la entrega del capital de constitución a favor del fondo.

**Por qué es la puerta por la que el capital entra al ledger.** El modelo relacional
del eje no tiene emisión: no hay una operación que cree moneda, y toda transacción
nace con un emisor que ya tiene saldo. Eso deja dos opciones: que el ledger arranque
sin valor, o que una wallet haga la primera entrega sin haber recibido nada. La
segunda es la del eje, y el constituyente es esa wallet: la puerta de entrada del
capital. Por eso `_entrega_de_capital` escribe su fila **directo por el repositorio**
(`transactions.add`) y no por `create_transaction`: esa puerta valida el saldo del
emisor (REQ-05) y la emisión fundacional no podría pasar esa validación. La dispensa
vale solo para esa fila; todo lo demás de la demostración se mueve por el camino
normal.

**Por qué su saldo queda negativo.** Porque entrega 3000 y no recibe nada. El saldo
disponible es lo confirmado a favor menos lo confirmado en contra menos lo
comprometido en el pool, así que queda en `-3000`. Es **la única wallet de la
demostración a la que se le permite el negativo**, precisamente porque es la puerta
de entrada; el fondo y los tres asociados quedan en `300`. La regla de REQ-05 se sigue
aplicando a todas las demás.

**Por qué su fila, aun así, lleva firma real.** `_entrega_de_capital` calcula la firma
con `sign_payload` sobre la misma cadena canónica que usa el camino normal
(`Transaction.signing_payload`), de modo que la fila se verifica contra la pública del
constituyente como cualquier otra. Firmar no es validar: saltarse la regla de saldo no
exime de la firma. Lo comprueba
`tests/integration/test_bootstrap.py::test_req_02_la_emision_fundacional_esta_firmada_por_el_constituyente`.

### Aportes y retiros

El modelo relacional del eje **no tiene una columna** que distinga un aporte de un
retiro, y no se le agregó ninguna (decisión 8 del diseño). La convención es la
dirección respecto de la wallet del fondo, cuya clave pública es la constante `FONDO`
de `src/bootstrap.py`:

- **Aporte**: transacción de un asociado **hacia** la wallet del fondo.
- **Retiro**: transacción **desde** la wallet del fondo hacia un asociado.

Para verlo en la base, esta consulta reproduce la misma cuenta del saldo disponible y
muestra al constituyente en negativo:

```sql
SELECT w.public_key,
       COALESCE(SUM(CASE WHEN t.receiver_id = w.id AND t.status = 'confirmed' THEN t.amount END), 0)
     - COALESCE(SUM(CASE WHEN t.sender_id = w.id AND t.status = 'confirmed' THEN t.amount END), 0)
     - COALESCE(SUM(CASE WHEN t.sender_id = w.id AND t.status = 'pending' THEN t.amount END), 0)
       AS disponible
FROM wallets w
LEFT JOIN transactions t ON t.sender_id = w.id OR t.receiver_id = w.id
GROUP BY w.id, w.public_key
ORDER BY disponible;
```

La clave pública del fondo se imprime con:

```text
<venv> -c "from src.bootstrap import FONDO; print(FONDO)"
```

## Cómo correr las pruebas

**Reglas del dominio, sin base de datos (REQ-17).** Estas pruebas no abren conexión ni
importan el driver, así que corren con el contenedor apagado y sin `DATABASE_URL`:

```text
<venv> -m pytest tests/unit -v
```

**Toda la suite.** Necesita el contenedor levantado y el `.env` con `DATABASE_URL`;
las de integración fallan con un mensaje claro si falta, en vez de omitirse en
silencio:

```text
<venv> -m pytest tests -v
```

La suite incluye las pruebas de reglas, las de integración contra PostgreSQL y
`tests/test_explicacion.py`, que comprueba que cada caso de uso está en el recorrido y
que cada uno de los 29 requerimientos tiene una prueba `test_req_NN_` (REQ-17, REQ-20
y REQ-23 incluidos).

Si prefiere correr solo la integración:

```text
<venv> -m pytest tests/integration -v
```

Las dependencias están fijadas con `==` en `requirements.txt` (REQ-23) y el lint se
configura en `pyproject.toml` (ruff, `line-length = 100`). Para correrlo:

```text
<venv> -m ruff check .
```

## Reproducir la demostración de alteración

El objetivo específico tercero del eje es que **toda** modificación del historial sea
detectable. La prueba automática es
`tests/integration/test_req_10_alteracion.py`; esto es el mismo procedimiento a mano.

**La aplicación tiene que estar corriendo en otra terminal** antes del último paso:

```text
<venv> -m src.web
```

1. Alterar a mano una transacción confirmada, sin pasar por la aplicación. El
   `LIMIT` va dentro de una CTE porque `UPDATE ... LIMIT` no es válido en PostgreSQL:

```text
docker compose exec postgres psql -U blockchain_user -d blockchain_db -c "WITH objetivo AS (SELECT id FROM transactions WHERE status = 'confirmed' LIMIT 1) UPDATE transactions SET amount = amount + 1 WHERE id IN (SELECT id FROM objetivo);"
```

Con Podman, `podman compose exec postgres psql ...` con el mismo resto del comando. Si
tiene `psql` instalado, el equivalente es
`psql "$DATABASE_URL" -c "WITH objetivo AS (...) UPDATE ...;"` (en PowerShell,
`psql $env:DATABASE_URL -c "..."`).

2. Pedir la verificación y buscar el dictamen:

```text
curl -s http://127.0.0.1:5000/verificar
```

En Windows use `curl.exe`, o abra `http://127.0.0.1:5000/verificar` en el navegador.

**Resultado esperado.** La página dice "La cadena no es válida" y muestra el índice
del primer bloque que no encaja: el bloque donde está la transacción alterada. La
verificación recalcula el hash de cada bloque con sus transacciones y lo compara con
el guardado (REQ-10), y no escribe nada (REQ-22).

La alteración deja la base modificada a propósito. Para volver a los datos de
demostración, borre el volumen y vuelva a sembrar: `docker compose down -v`,
`docker compose up -d` (o con Podman) y `<venv> -m src.bootstrap`.

## Qué está verificado

- **El esquema en PostgreSQL 16**, la versión del piso: `db/init.sql` se aplicó como
  guion de inicialización de un contenedor `postgres:16-alpine` (PostgreSQL 16.15) y
  quedaron las tres tablas, `uuid-ossp`, los once índices y todos los `CHECK` del eje,
  incluido `chk_transactions_sender_ne_receiver`: un intento de transacción de una
  wallet a sí misma lo rechazó el motor.
- **Las reglas sin base de datos (REQ-17)**: `pytest tests/unit` pasa con
  `DATABASE_URL` sin definir y sin contenedor, porque el dominio no importa el driver.
- **La suite completa contra el clúster PostgreSQL del equipo de desarrollo**: 84
  pruebas (28 de reglas, 51 de integración y 5 de coherencia de la explicación).
- El piso de Python lo declara `pyproject.toml` (`requires-python = ">=3.11"`); la
  corrida de la suite dentro del contenedor del piso forma parte de la aceptación y no
  se afirma aquí.

## Por dónde empezar a leer el código

1. `docs/recorrido-de-casos-de-uso.md`: el camino real de cada caso de uso, con la
   ruta, el método del dominio, la tabla y la consulta.
2. `db/init.sql`: el esquema del modelo relacional del eje, con los `CHECK`, las
   claves foráneas y el índice único de la firma. Es la única fuente de las tablas: la
   aplicación nunca ejecuta DDL (REQ-15).
3. `src/domain/wallet.py`: par ECDSA sobre `secp256k1`, cifrado del material privado
   con `Fernet` y firma (REQ-01, REQ-02).
4. `src/domain/transaction.py`: la entidad, los estados, las dos cadenas canónicas
   (la de la firma y la del hash) y las reglas de admisión al pool (REQ-02 a REQ-06,
   REQ-11).
5. `src/domain/block.py` y `src/domain/blockchain.py`: el hash del contenido agrupado,
   el saldo disponible, el pool, la agrupación atómica, la verificación que localiza
   la alteración y el génesis (REQ-05 a REQ-10, REQ-14, REQ-18, REQ-22).
6. `src/persistence/ports.py` y `src/persistence/postgres.py`: los protocolos que
   aíslan al dominio del motor (REQ-16) y los adaptadores que no traducen los errores
   de PostgreSQL (REQ-19).
7. `src/web/app.py` y `src/web/templates/`: las cinco rutas y sus plantillas, sin
   reglas de negocio ni SQL (REQ-24 a REQ-29).
8. `tests/`: la explicación ejecutable. Cada prueba se llama `test_req_NN_*` y lleva
   el criterio de aceptación en su docstring, así que para explicar una regla alcanza
   con mostrar la prueba que la demuestra.
