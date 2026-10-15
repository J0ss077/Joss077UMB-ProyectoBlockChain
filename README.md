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

El host de `DATABASE_URL` es `127.0.0.1` y no `localhost`, y no es un detalle: en
Windows `localhost` puede resolverse primero a IPv6 (`::1`) mientras el contenedor
publica en IPv4 (`compose.yaml` publica el puerto en `127.0.0.1`, no en todas las
interfaces).

Si después cambia `POSTGRES_PORT`, **hay que recrear el contenedor** para que publique
el puerto nuevo: editar `.env` no lo recrea, el contenedor que ya está corriendo sigue
con el puerto viejo. Vuelva a levantarlo con `docker compose up -d` (o `podman compose
up -d`): Compose detecta que cambió la definición del servicio y lo recrea. El paso
siguiente es el que levanta el contenedor por primera vez.

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

Abra `http://127.0.0.1:5000`. La portada muestra los conteos de las tres tablas; la
barra superior con los enlaces y el panel lateral con las wallets están a la vista en
todas las páginas de trabajo. La aplicación arranca sin el depurador interactivo ni el
recargador de código; se activan con `FLASK_DEBUG=1` en el entorno, solo para desarrollo
local.

## Problemas conocidos

**La aplicación parece quedarse pensando.** El arranque imprime al final, así que una
conexión que espera se ve igual que un cuelgue. Si el arranque se queda callado, revise
el host de `DATABASE_URL`: use `127.0.0.1` en lugar de `localhost`. En Windows
`localhost` puede resolverse primero a IPv6 (`::1`) mientras el contenedor publica en
IPv4 (el `compose.yaml` publica el puerto en `127.0.0.1`), y la conexión se queda
esperando una dirección donde nadie escucha.

Desde esta versión, una conexión imposible falla en cinco segundos con el mensaje del
motor en vez de esperar lo que decida el sistema operativo. El tiempo de espera lo pone
`database_url()` cuando la cadena no lo trae; si usted pasa su propia cadena con otro
`connect_timeout`, ese manda.

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

`GET /wallets` es la misma ruta del CU-01, y el panel lateral de las páginas de trabajo
lista las wallets registradas: la clave pública en forma corta y monoespaciada, con el
valor completo en el atributo `title` y un botón que lo copia, además del enlace a su
historial. El CU-05 se alcanza desde ese panel: no hay que teclear el identificador a
mano.

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
capital. Por eso `_entrega_de_capital` escribe **las cuatro filas de capital directo
por el repositorio** (`transactions.add`) y no por `create_transaction`: la emisión
fundacional del constituyente al fondo no podría pasar esa puerta —valida el saldo del
emisor (REQ-05) y el constituyente nace sin saldo—, y los tres capitales de asociación
del fondo a los asociados van por el mismo camino porque son la misma clase de fila:
capital colocado, no una operación del ciclo. Todo lo demás de la demostración —los
aportes y los retiros, los que se confirman y los tres que quedan pendientes en el
pool— se mueve por el camino normal.

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

**Reglas sin base de datos (REQ-17).** Estas pruebas no abren ninguna conexión, así que
corren con el contenedor apagado y con `DATABASE_URL` sin definir en el entorno:

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

## Sabotaje guiado

`python -m src.sabotaje` es una herramienta de verificación y demostración: altera el
ledger a propósito, por SQL directo, y narra cada caso para que se vea en el navegador
qué detecta la cadena y qué no. No es parte del camino de la aplicación —ninguna ruta
la usa ni la importa (REQ-29)— y no cambia el comportamiento del sistema: existe para
mostrar en una sola corrida lo que las pruebas afirman por separado, incluidos los
límites.

**Antes de empezar**, la aplicación tiene que estar corriendo en otra terminal
(`<venv> -m src.web`) y la cadena tiene que estar válida. La herramienta lo comprueba
primero: si la cadena ya viene alterada, o si `/verificar` no responde, lo dice y no
corre ningún caso, porque el veredicto de cada caso dejaría de significar algo.

**Los dos modos.**

```text
<venv> -m src.sabotaje
```

Es el modo interactivo, el que se usa para una demostración en vivo. Por caso: imprime el
encabezado, **aplica** la alteración, **espera un Enter** —ahí es donde la persona mira
`http://127.0.0.1:5000/verificar` y ve la cadena en rojo—, informa el veredicto,
**restaura**, **espera un segundo Enter** —ahí es donde mira que la cadena volvió a ser
válida— y sigue con el caso siguiente. La alteración queda escrita en la base entre las
dos pausas, que es lo que hace que haya algo para ver; sin la segunda pausa, la vuelta al
estado original pasaría sin que nadie la mire. Si la entrada no es un terminal —una
corrida con guion, o la suite— no espera y lo avisa, así que nunca se queda colgado
esperando a alguien que no está.

```text
<venv> -m src.sabotaje --sin-pausas
```

Es el mismo recorrido sin esperar a nadie, para la suite o para un guion cerrado.

**Los once casos, y los tres destructivos.** El recorrido normal corre ocho casos: los
que alteran una fila, los que el motor rechaza y los tres límites. Los otros tres
borran datos y **no se tocan sin pedirlo**; se agregan con la bandera `--destructivos`:

```text
<venv> -m src.sabotaje --destructivos
```

| Caso                        | Qué hace                                                           | Qué se espera                                                             |
| --------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `alterar-monto`             | suma uno al monto de una transacción confirmada                    | cadena inválida, bloque 1                                                 |
| `alterar-hash`              | escribe sesenta y cuatro ceros como hash de un bloque              | cadena inválida, bloque 1                                                 |
| `mover-transaccion`         | mueve una confirmada al bloque génesis                             | cadena inválida                                                           |
| `insertar-confirmada-falsa` | confirma, dentro de un bloque, una transacción con firma inventada | cadena inválida                                                           |
| `reutilizar-firma`          | inserta con una firma ya registrada                                | el motor rechaza: índice único de la firma                                |
| `violar-regla`              | inserta con el mismo emisor y receptor                             | el motor rechaza: CHECK del esquema                                       |
| `cambiar-llave-wallet`      | cambia la pública de una wallet                                    | **no se detecta**: el hash cubre transacciones, no el registro de wallets |
| `pendiente-firma-invalida`  | inserta una pendiente con firma inventada                          | **no se detecta**: la verificación mira bloques, no el pool               |
| `borrar-transaccion`        | borra una confirmada (destructivo)                                 | cadena inválida                                                           |
| `borrar-genesis`            | borra el bloque índice 0 (destructivo)                             | cadena inválida                                                           |
| `truncar-cola`              | borra el último bloque y sus transacciones (destructivo)           | **no se detecta**: sin ancla externa no hay con qué comparar              |

Cada caso declara su veredicto como un dato, y el recorrido restaura lo que tocó antes
de pasar al siguiente: al final de la corrida, `/verificar` tiene que volver a decir
"La cadena es válida". El cierre del recorrido imprime el resumen —cuántos se
detectaron, cuántos no y por qué— y las instrucciones de resembrado, por si alguna
corrida quedó a medias.

**Recuperación.** La herramienta restaura cada caso, pero si una corrida se interrumpe
a la mitad la base queda alterada y la aplicación no tiene una operación que lo
deshaga. El camino de vuelta es el reinicio limpio, en este orden:

```text
docker compose down -v
docker compose up -d
<venv> -m src.bootstrap
<venv> -m src.web
```

Con Podman, `podman compose down -v` y `podman compose up -d` con el mismo resto. La
primera línea baja los contenedores **borrando el volumen** (sin `-v` los datos
siguen ahí), la segunda los vuelve a levantar —`db/init.sql` se aplica solo al crear
el volumen de nuevo—, la tercera siembra los datos de demostración y la cuarta levanta
la aplicación. Al final, `http://127.0.0.1:5000/verificar` tiene que decir "La cadena
es válida".

## Apagar y limpiar

**Detener la aplicación.** En la terminal donde corre `<venv> -m src.web`, `Ctrl+C`. No
queda nada a medias: cada petición abre su conexión y la cierra al terminar, y la
agrupación de un bloque es una sola transacción de base de datos (REQ-18), así que o se
confirmó completa o no ocurrió.

**Apagar PostgreSQL 16.** `docker compose down` (o `podman compose down`) quita el
contenedor **y conserva los datos**: el volumen `postgres_data` sigue en el equipo, así
que el próximo `docker compose up -d` levanta el mismo ledger. `docker compose down -v`
es el que borra el volumen y, con él, las tres tablas. Tras borrarlo, el esquema de
`db/init.sql` se vuelve a aplicar solo en el próximo `up` (el punto de entrada de la
imagen lo lee al crear el volumen de nuevo), la base queda vacía y hay que volver a
sembrar la demostración:

```text
docker compose down -v
docker compose up -d
<venv> -m src.bootstrap
```

**Deshacer la alteración de la demostración.** La alteración a mano del apartado anterior
cambia una fila sin pasar por la cadena, y la aplicación no tiene una operación que la
deshaga: el camino de vuelta es el reinicio limpio de arriba —borrar el volumen, `up` y
`<venv> -m src.bootstrap`—. Si lo que quiere es ver el dictamen sin ensuciar la
demostración, `tests/integration/test_req_10_alteracion.py` hace la misma alteración
sobre una base desechable.

**Qué se puede borrar sin miedo.** Nada de esto está versionado (`.gitignore`), así que
borrarlo no ensucia el repositorio:

| Ruta               | Qué es                                                            | Si la borra                                                                                               |
| ------------------ | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `.venv/`           | El entorno virtual con las dependencias fijadas                   | Se recrea con `python -m venv .venv` y la instalación de `requirements.txt`.                              |
| `.reference/`      | El extracto del documento del eje y el material de consulta       | No rompe nada: no lo importan el código ni las pruebas. Se pierde la copia local del extracto del eje.    |
| `.superpowers/`    | Los planes y los informes de las tareas, sin versionar            | No rompe nada: no lo importa nadie. Se pierden los planes y los informes, que no están en el repositorio. |
| `.legacy-project/` | El prototipo anterior, que solo se conserva como referencia       | No rompe nada: no lo importa nadie. Se pierde el prototipo anterior, que no es el entregable.             |
| `.env`             | Los secretos locales: `DATABASE_URL`, `POSTGRES_*` y `MASTER_KEY` | Obliga a copiar `.env.example` otra vez y a generar una `MASTER_KEY` nueva; lea la advertencia de abajo.  |

**Antes de borrar `.env`.** `.env` guarda la `MASTER_KEY` con la que se cifra el material
privado de las wallets (decisión 3 del diseño). Con otra clave, las wallets ya guardadas
quedan ilegibles: su llave privada no se puede descifrar y no pueden volver a firmar. Por
eso, después de cambiar la clave hay que reiniciar los datos —`docker compose down -v`,
`docker compose up -d` y `<venv> -m src.bootstrap`—, que siembra wallets nuevas cifradas
con la clave nueva. El arranque solo siembra cuando la tabla de wallets está vacía: un
`.env` nuevo con los datos viejos deja un ledger que no puede firmar.

## Qué está verificado

- **El esquema en PostgreSQL 16**, la versión del piso: `db/init.sql` se aplicó como
  guion de inicialización de un contenedor `postgres:16-alpine` (PostgreSQL 16.15) y
  quedaron las tres tablas, `uuid-ossp`, los once índices y todos los `CHECK` del eje;
  una transacción de una wallet a sí misma la rechazó el motor.
- **Las reglas sin base de datos (REQ-17)**: `pytest tests/unit` pasa con
  `DATABASE_URL` sin definir y sin contenedor, porque el dominio no importa el driver.
- **La suite completa** contra el clúster PostgreSQL del equipo de desarrollo: las
  reglas, la integración y la coherencia de la explicación. La cobertura de los 29
  requerimientos no se cuenta a mano: la exige `tests/test_explicacion.py`.
- **La suite completa dentro del contenedor del piso de Python** (`python:3.11-slim`):
  con el repositorio montado en solo lectura, `requirements.txt` instalado y `pytest`
  corriendo contra el contenedor PostgreSQL 16, el veredicto fue el código de salida 0.
  El piso lo declara `pyproject.toml` (`requires-python = ">=3.11"`).

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
