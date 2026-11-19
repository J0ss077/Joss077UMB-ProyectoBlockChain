# Recorrido de los casos de uso

Este documento narra la ejecución real del prototipo: qué hace la persona, qué ruta
recibe la petición, qué método del dominio decide, qué tabla se toca, qué consulta
se ejecuta contra PostgreSQL y qué prueba lo demuestra. No repite los requisitos ni
las fichas del eje (`documentacion_proyecto_transaccionales.pdf`, Grupo 1, UMB):
los cita por su identificador y sigue el código.

Cada bloque de SQL es la sentencia que el adaptador envía, con los marcadores `%s`
que reemplaza `psycopg`. Las rutas viven en `src/web/app.py`, las decisiones en
`src/domain/` y las sentencias en `src/persistence/postgres.py`.

Antes de cada petición, la ruta entra en `abrir_cadena()` (`src/web/app.py`), que le
pide una cadena a la fábrica con la que se armó la aplicación —en `python -m src.web`
es `ledger()` de `src/persistence/factory.py`, que resuelve `DATABASE_URL` y
`MASTER_KEY` del entorno o de `.env`, abre la conexión y la cierra al salir— y
asegura el génesis con `ensure_genesis`, que es idempotente: comprueba
`blocks.get_by_index(0)` y solo inserta el eslabón cero si falta. La portada `GET /`
usa `ledger_state()` y hace un `SELECT count(*)` por tabla para mostrar los conteos, y
todas las páginas del administrador piden `available_balance(wallet_id)` de cada wallet
para mostrarlos en el panel.

**La sesión y las puertas por rol.** Las cinco rutas del eje exigen una sesión de
administrador (REQ-38): sin sesión redirigen a `/ingresar`, y con una sesión de usuario
común responden 403. Antes de seguir este recorrido hay que ingresar con una cuenta
administradora —la de demostración está en el README—; las pantallas del usuario común
(su tablero y su historial, que reúne la verificación) no pasan por estas rutas.

La interfaz no explica el proyecto: los títulos nombran la acción —«Registrar wallet»,
«Nueva transacción», «Cerrar bloque», «Verificar cadena», «Historial»— y ninguna página
lleva párrafos sobre el eje ni números de caso de uso. `base.html` pinta una barra
superior con el nombre de la aplicación y dos navegaciones: la del administrador
—Resumen, Pendientes, Wallets, Transacciones, Bloques, Verificar, Estadísticas y
Ayudante— y la del usuario común —Mi tablero, Mi historial, Mis contactos, Estadísticas
y Ayudante—; el nombre de la sesión abre el perfil y el botón «Salir» la cierra. Debajo
va un panel lateral con las wallets —la forma corta de la clave pública en
monoespaciada, el nombre de la cuenta dueña o «Sin dueño», el saldo, el botón que copia
la clave y el enlace a su historial; «Todavía no hay wallets» cuando no hay ninguna— y
el área de contenido.
Todas las páginas del administrador muestran además el saldo disponible de cada wallet:
las páginas del usuario común no llevan panel, a propósito, porque les mostraría wallets
de otros (REQ-35). El panel lo pasa cada ruta del administrador con `datos_del_panel(chain)`
(`src/web/panel.py`), que devuelve la lista y los saldos juntos —una sola fuente— y no
hay procesador de contexto, porque abrir el ledger al pintar la página de error
convertiría un 404 sin base en un 500 y podría escribir el génesis. La cola de
pendientes usa la misma fuente: recibe también la fábrica de cadena desde `create_app`.
`base.html` envuelve el panel en `{% if wallets_del_panel is defined %}` y la página de
error no lo pasa, así que se pinta sin tocar la fachada. Los identificadores, hashes,
montos, fechas y conteos van en `code` o en la clase `.mono`, y los controles del
formulario —`select`, `option` e `input`— usan la misma pila monoespaciada; las claves,
los identificadores y los hashes se ven en forma corta, y el valor completo sigue en el
atributo `title` —también el de cada `option`— y en `data-copiar`, que es lo que copian
los botones con el guion de `base.html`: avisa «copiado» cuando la escritura sale bien y
«no se pudo copiar» cuando el navegador no ofrece el portapapeles o la rechaza.

## CU-01: registrar una wallet con su dueño

**Qué hace la persona.** Entra a `GET /wallets`, elige en el formulario a qué cuenta se
le asigna la wallet —o deja la opción vacía, «Déjala sin dueño»— y lo envía por
`POST /wallets`. Recibe la ficha de la wallet creada con su dueño, su identificador,
su clave pública y su saldo.

**Qué ruta la recibe.** `wallets()` en `src/web/app.py` (REQ-24, REQ-46). El `GET`
llama a `_formulario_de_wallet()`, que abre el ledger para el panel lateral y las
cuentas para el selector (`usuarios_aprobados()`), y pinta `wallet.html` sin wallet.
El `POST` lee el campo `dueno` y lo convierte con `a_uuid`: si viene texto y no es un
UUID, repinta el formulario con `MENSAJE_DUENO_INVALIDO` y no llega al servicio. Si el
texto es válido o vacío, llama a `cuentas.registrar_wallet(dueno_id)`; un
`DuenoInvalido` del servicio repinta el formulario con el motivo del servicio y sin
crear la wallet, y el camino correcto pinta la misma plantilla con la wallet creada,
la lista de cuentas vacía y el panel. La ruta exige sesión de administrador (REQ-38).
La lista de wallets no la pinta esta ruta: vive en el panel lateral, así que el CU-05
queda a un clic desde cualquier página.

**Qué método decide.** `Cuentas.registrar_wallet()` (`src/accounts/service.py`) es la
puerta de la regla del dueño: `_puede_ser_dueno()` exige que la cuenta exista, esté
aprobada y sea de rol `usuario`; el administrador, una cuenta pendiente, una rechazada
o un identificador inexistente levantan `DuenoInvalido` antes de escribir nada. Con un
dueño válido llama a `Blockchain.register_wallet()` (`src/domain/blockchain.py`), que
delega en `create_wallet()` (`src/domain/wallet.py`): genera el par con
`generate_private_key()` sobre `secp256k1`, serializa la pública como punto comprimido
en hexadecimal (`public_key_hex`), cifra el DER de la privada con `Fernet` y la clave
maestra (`encrypt_private_key`) y fija el identificador con `uuid4` y la marca de
tiempo con el reloj inyectado. La wallet nace sin dueño en la tabla y el servicio le
escribe el dueño con `asignar_wallet()`, que solo actualiza una fila con `owner_id IS
NULL`. Las dos escrituras van dentro de la misma transacción y se confirman una sola
vez; si la asignación fallara, `DuenoInvalido` impide confirmar una wallet que diga
tener dueño y no lo tenga.

**Qué tabla se toca.** `wallets`: una fila nueva y, si se eligió dueño, el `UPDATE`
que le escribe `owner_id`. `users` se lee para el selector y para validar al dueño.

**Qué consultas se ejecutan.**

```sql
SELECT * FROM users
WHERE role = 'usuario' AND estado = 'aprobado'
ORDER BY username
```

```sql
INSERT INTO wallets (id, public_key, private_key_encrypted, created_at)
VALUES (%s, %s, %s, %s)
RETURNING *
```

```sql
UPDATE wallets SET owner_id = %s
WHERE id = %s AND owner_id IS NULL
```

`RETURNING *` devuelve la fila tal como quedó en la base y no la que se propuso. Si
la pública chocara con `uq_wallets_public_key`, el error del motor sube sin traducir
(REQ-19), que es el flujo alterno de la ficha.

**Qué se muestra.** La ficha de resultado saluda con «Wallet registrada a nombre de
{nombre}.» o «Wallet registrada sin dueño.»; el nombre lo resuelve `nombre_de_wallet()`
con `nombres_por_wallet()`, que lee la base una vez por petición. La ficha lleva
Dueño, Identificador, Clave pública —con el valor completo en el `title` y el botón de
copiar— y Saldo disponible, y dos enlaces: «Ver su historial» y «Proponer una
transacción». La captura `24-registro-wallet-con-dueno.png` muestra el formulario con
«¿A quién se la asignas?» y la cuenta `asociado1` elegida, y
`25-wallet-asignada-a-cliente.png` la ficha resultante, «Wallet registrada a nombre de
asociado1.», con el dueño en su campo. La captura `14-flujo-wallet-creada.png` es del
4 de noviembre y muestra la ficha anterior, cuando el formulario todavía no pedía dueño
y la wallet recién creada quedaba «Sin dueño».

**Varias wallets por cuenta (REQ-47).** Una cuenta común aprobada puede tener varias
wallets: la primera la crea la aprobación de la cuenta (REQ-33) y las demás se
registran por esta ruta. La principal es la más antigua. `GET /perfil` las lista todas
y, cuando hay más de una, el tablero pinta el selector «Tus wallets» con el saldo de
cada una; `POST /mi-wallet` valida que la elegida pertenezca a la sesión y la guarda
en `wallet_elegida`, y el envío por nombre de usuario apunta siempre a la principal del
destinatario. La captura `26-multiwallets-tablero.png` muestra el tablero de `asociado1`
con el selector «Tus wallets» y el saldo de la wallet elegida, y
`27-multiwallets-perfil.png` el perfil con los tres códigos de wallet de la cuenta.

**Qué prueba lo demuestra.** `tests/unit/test_req_01_wallet.py`
(`test_req_01_la_privada_no_esta_en_claro_en_la_wallet`,
`test_req_01_dos_wallets_no_comparten_publica`),
`tests/integration/test_req_01_wallet_en_base.py` (la pública queda única y no vacía,
y el texto plano de la privada no aparece en la base),
`tests/integration/test_req_24_rutas.py::test_req_24_post_wallets_devuelve_200_con_la_publica`,
`tests/integration/test_req_46_registro_con_dueno.py` (el dueño aprobado queda en
`owner_id`, la opción vacía lo deja nulo y un dueño que no sirve no crea la wallet),
`tests/integration/test_req_47_varias_wallets.py` (varias wallets de la misma cuenta y
la elección de la activa) y `tests/integration/test_nombres_por_wallet.py` (el panel
muestra el dueño de cada wallet y omite las que no lo tienen).

## CU-02: crear una transacción

**Qué hace la persona.** Entra a `GET /transacciones`, elige la wallet emisora, la
receptora y el monto, y envía el formulario por `POST /transacciones`. Recibe el
estado de la transacción o el motivo por el que no entró al pool.

**Qué ruta la recibe.** `transacciones()` en `src/web/app.py` (REQ-25). El `GET`
lista las wallets para el selector del formulario y para el panel lateral con una sola
llamada (`wallets.list()` → `SELECT * FROM wallets ORDER BY created_at, id LIMIT %s`).
El `POST` convierte los identificadores con `_uuid` y el monto con
`_monto`; si el identificador no es un UUID, informa el error en la misma página sin
llegar a la fachada. Después llama a `Blockchain.create_transaction(...)` y pinta
`transaccion.html` con el resultado, incluido el motivo del rechazo.

**Qué método del dominio decide.** `Blockchain.create_transaction()`
(`src/domain/blockchain.py`), en este orden:

1. Resuelve las dos wallets (`wallets.get`); sin ellas no hay nada que firmar.
2. Arma la `Transaction` en estado `pending`, sin bloque, con `uuid4` y el reloj.
3. Firma: descifra la privada del emisor con la clave maestra y firma la cadena
   canónica de `Transaction.signing_payload` (identificador, las dos públicas, el
   monto con ocho decimales y la marca de tiempo) con ECDSA sobre SHA-256; la firma
   queda como DER en hexadecimal.
4. Consulta `transactions.signature_exists(transaction.signature)`.
5. Calcula `available_balance(transactions.balance_terms(sender_id))`, es decir
   confirmado recibido menos confirmado enviado menos lo comprometido en el pool.
6. `Transaction.validate(...)` aplica las reglas y devuelve el primer motivo
   encontrado: monto positivo, rango de `NUMERIC(18, 8)`, precisión de ocho
   decimales, emisor distinto del receptor, wallets conocidas, firma del emisor,
   saldo disponible y firma repetida (REQ-02, REQ-04, REQ-05, REQ-06).
7. Decide la fila: si se acepta, se guarda `pending`; si el motivo es firma ajena o
   saldo insuficiente, se guarda `rejected` y sin bloque (REQ-11); si es firma
   repetida, monto inválido, emisor igual al receptor o wallet inexistente, **no se
   escribe nada** porque el esquema no admitiría esa fila, y el rechazo se informa
   igual (el CHECK, la clave foránea y el índice único quedan como respaldo de
   REQ-19).

    Desde las rutas, dos de esos motivos no se alcanzan (decisión P12 de la revisión):
    el ledger firma siempre con la llave del emisor, así que la página nunca produce
    una firma ajena (`BAD_SIGNATURE`), y para repetir una firma habría que presentar
    dos veces la misma forma canónica exacta, cosa que la web no permite porque genera
    un identificador nuevo en cada envío. El par admisión/rechazo de REQ-03 se produce
    en el nivel del repositorio o con un firmante fijo, que es como lo prueban
    `test_req_03_firma_repetida.py` y
    `test_req_11_la_firma_repetida_se_informa_sin_fila`.

**Qué tabla se toca.** `wallets` (lecturas) y `transactions` (la fila nueva).

**Qué consultas se ejecutan.**

```sql
SELECT * FROM wallets WHERE id = %s                -- una vez por cada parte
SELECT 1 FROM transactions WHERE signature = %s LIMIT 1
```

```sql
SELECT
    COALESCE(SUM(CASE WHEN t.receiver_id = %s AND t.status = 'confirmed' THEN t.amount END), 0)
        AS confirmed_in,
    COALESCE(SUM(CASE WHEN t.sender_id = %s AND t.status = 'confirmed' THEN t.amount END), 0)
        AS confirmed_out,
    COALESCE(SUM(CASE WHEN t.sender_id = %s AND t.status = 'pending' THEN t.amount END), 0)
        AS pending_out
FROM transactions t
WHERE t.sender_id = %s OR t.receiver_id = %s
```

```sql
INSERT INTO transactions (id, sender_id, receiver_id, amount, status, signature, block_id, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING *
```

**Qué prueba lo demuestra.** `tests/unit/test_req_02_firma.py`,
`tests/unit/test_req_02_transaction.py`, `tests/unit/test_req_04_formato.py` (incluye
RF-1 y RF-2), `tests/unit/test_req_05_saldo.py`,
`tests/integration/test_req_03_firma_repetida.py`,
`tests/integration/test_req_11_rechazo_en_base.py` (los cinco desenlaces de la tabla
de conducta del diseño), `tests/integration/test_req_19_errores_del_motor.py` y
`tests/integration/test_req_24_rutas.py::test_req_25_post_transacciones_devuelve_el_estado`.

## CU-03: agrupar las transacciones en un bloque

**Qué hace la persona.** Entra a `GET /bloques` y envía el formulario por
`POST /bloques`. Recibe el bloque creado con su índice, su marca de tiempo, su hash
previo y su hash, o el aviso de que el pool estaba vacío.

**Qué ruta la recibe.** `bloques()` en `src/web/app.py` (REQ-26). Pregunta
`bool(chain.transactions.pending())` para poder distinguir el flujo alterno y luego
llama a `Blockchain.group_pending()`, que devuelve el bloque o `None`.

**Qué método del dominio decide.** `Blockchain.group_pending()`
(`src/domain/blockchain.py`):

1. Lee el pool (`transactions.pending()`); si está vacío no crea bloque, que es el
   flujo alterno del CU-03.
2. Lee el último bloque (`blocks.last()`) y arma el nuevo con el índice siguiente y
   `previous_hash` igual al hash del último; sin cadena previa usa índice 0 y sesenta
   y cuatro ceros, la forma del génesis (REQ-14).
3. `Block.calculate_hash(transactions)` calcula el SHA-256 del mensaje formado por la
   cabecera `índice|marca de tiempo|hash previo|` y los `hash_payload()` de las
   transacciones **ordenados alfabéticamente**, unidos por `|` (REQ-07). Ordenarlos
   hace que el hash no dependa del orden de lectura, y como cada payload lleva el
   identificador, mover una transacción de bloque cambia el hash. El payload no
   incluye `status` ni `block_id` a propósito: ambos cambian justo al confirmar.
4. Abre una unidad de trabajo propia (`PostgresUnitOfWork.open`) y dentro de ella
   escribe el bloque, confirma las transacciones del pool y hace **un solo
   `COMMIT`** (REQ-18). Si la segunda escritura falla, el `ROLLBACK` del contexto
   deshace la primera y las transacciones siguen `pending`. El estado y el bloque se
   mueven juntos, así que no queda una confirmada sin bloque ni una pendiente con
   bloque (REQ-12, REQ-09).

**Qué tablas se tocan.** `transactions` (lectura del pool y `UPDATE` a confirmadas) y
`blocks` (la fila nueva).

**Qué consultas se ejecutan.**

```sql
SELECT * FROM transactions WHERE status = 'pending' ORDER BY created_at, id
SELECT * FROM blocks ORDER BY block_index DESC LIMIT 1
```

```sql
INSERT INTO blocks (id, block_index, timestamp, previous_hash, hash)
VALUES (%s, %s, %s, %s, %s)
RETURNING *
```

```sql
UPDATE transactions
SET status = 'confirmed', block_id = %s
WHERE id = ANY(%s) AND status = 'pending'
```

El `UPDATE` solo toca las `pending`: una confirmada no se mueve de su bloque y una
`rejected` tampoco entra a la cadena. Las dos escrituras van por la conexión de la
unidad de trabajo, abierta sin autocommit, y recién el `commit` las aplica.

**Qué prueba lo demuestra.** `tests/integration/test_req_09_agrupacion.py` (las del
pool quedan confirmadas y ligadas al bloque, y con el pool vacío no se crea bloque),
`tests/integration/test_req_08_encadenamiento.py` (el hash previo del bloque nuevo es
el del último), `tests/integration/test_req_18_atomicidad.py` (si falla la
confirmación no queda el bloque), `tests/integration/test_req_12_coherencia.py`,
`tests/integration/test_req_14_genesis.py` y
`tests/integration/test_req_24_rutas.py::test_req_26_post_bloques_devuelve_el_bloque_creado`.

## CU-04: verificar la integridad de la cadena y auditarla

**Qué hace la persona.** Entra a `GET /verificar` y recibe dos lecturas del mismo
estado. Arriba, el dictamen de siempre: la cadena es válida o el índice del primer
bloque que no encaja. Debajo, el panel de auditoría: las cifras del ledger, la cabeza,
el sello de vigilancia, los hallazgos con su severidad, la revisión de cada bloque, los
límites de la auditoría y las reparaciones que se pueden aplicar. La página no repara
nada; reparar es una acción aparte y explícita.

**Qué ruta la recibe.** `verificar()` en `src/web/app.py` (REQ-27). Primero lee el
sello inyectado con `leer_sello()` —sin adaptador configurado devuelve `ausente`— y
después abre la cadena y pinta `verificar.html` con `dictamen=chain.verify_chain()`,
`auditoria=chain.audit_chain(sello=..., problema_del_sello=...)` y el panel de wallets.
La ruta exige sesión de administrador (REQ-38).

**Qué método del dominio decide.** `Blockchain.verify_chain()`
(`src/domain/blockchain.py`):

1. Lee todos los bloques ordenados por índice (`blocks.list()`).
2. Comprueba la cabeza: el primer bloque tiene que ser el génesis (índice 0 y hash
   previo de sesenta y cuatro ceros). Sin esa comprobación, borrar el eslabón cero
   dejaría una cadena 1..n con todos sus hashes intactos y la alteración pasaría
   inadvertida.
3. Para cada bloque recalcula `Block.calculate_hash` con las transacciones que tiene
   ligadas (`transactions.of_block`) y lo compara con el hash guardado. El génesis
   también se recalcula: así se detecta que le cambien la marca de tiempo dejando su
   hash intacto.
4. Compara el `previous_hash` de cada bloque con el hash del anterior **y** que el
   índice sea el siguiente; un hueco en los índices no cambia ningún hash (RF-3).
5. Ante la primera discrepancia detiene el recorrido y devuelve su índice; si todo
   encaja, devuelve `valid=True` y `altered_block_index=None`.

Ese dictamen se detiene en el primer fallo. La auditoría que lo acompaña es otra
lectura más profunda: `Blockchain.audit_chain()` delega en `src/domain/auditoria.py`
(`auditar`), que recorre **todos** los bloques y **todas** las transacciones sin
detenerse, y calcula un `Resumen` (bloques, altura, hash y fecha de la cabeza, génesis,
confirmadas, pendientes, rechazadas y wallets). Sus comprobaciones:

1. Encadenamiento, índices, cabeza y hash recalculado de cada bloque; una revisión por
   bloque con estado `correcto`, `cabeza`, `hueco`, `encadenamiento` o `alterado`.
2. Coherencia de estado y bloque de cada transacción, wallets inexistentes y montos
   fuera de la escala.
3. Firma de cada confirmada y de cada pendiente contra la llave pública **actual** del
   emisor con `verify` y el `signing_payload`; así se detecta el cambio de llave de una
   wallet o una firma inventada sin depender solo del hash del bloque.
4. Firmas repetidas, sin importar el estado de las filas.
5. El sello de vigilancia ya leído, que se compara con la cadena.

Cada hallazgo lleva un código estable, una severidad —`critico`, `aviso` o `nota`—,
una ubicación, el detalle técnico sin traducir y, si existe, la reparación que lo
atendería. `Auditoria.limpia` es verdadera sin críticos ni avisos; una nota no ensucia
el dictamen. La auditoría declara además sus `limites`: el del recorte de la cola solo
aparece sin un sello utilizable, y siempre están el origen del sello, el alcance del
reencadenado y los huecos o borrados que la interfaz no repara.

**El sello de vigilancia.** Es un archivo JSON fuera de la base
(`datos/sello-de-vigilancia.json` por defecto, o `SELLO_DE_VIGILANCIA`) con la altura y
el hash de la cabeza, firmados con HMAC-SHA256 usando la clave maestra
(`src/persistence/sello.py`). Como el ancla vive fuera de la base, un recorte de la
cola deja de ser indistinguible de una cadena que nunca tuvo esos bloques. La lectura
nunca levanta: un archivo ausente da `ausente` y uno ilegible —JSON roto, forma
equivocada o firma que no cuadra— da `ilegible`, y el panel lo muestra como «Sin
fijar» o «Ilegible». El sello no se actualiza solo: lo fija la persona. La escritura va
primero a un temporal y se reemplaza con `os.replace`, que es atómico en el mismo
sistema de archivos, así que un corte a mitad no deja un JSON truncado.

**La reparación (`POST /verificar/reparar`).** El panel ofrece las acciones que
sugieren los hallazgos, y cada formulario lleva la casilla `confirmar` con valor `si`.
La ruta valida antes de tocar la cadena: sin `confirmar=si` o con una acción que no
existe, no se escribe nada y la bandeja lo avisa; después redirige con 303 a
`/verificar` (POST-redirect-GET) y el panel vuelve a pintar el estado real. Acepta seis
claves estables:

| Acción                | Qué hace                                                                                                                                                                | Dónde                                       |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `reparar-todo`        | Rechaza las pendientes inválidas, aísla las confirmadas inválidas y reencadena, en ese orden; es idempotente                                                            | `Blockchain.repair_all()`                   |
| `encadenar`           | Recalcula `previous_hash` y `hash` desde el bloque 0 sin tocar índices ni marcas de tiempo; sin bloques crea el génesis y, si el primer bloque no es el 0, no se aplica | `Blockchain.repair_chain()`                 |
| `aislar`              | Pasa a `rejected` las confirmadas que no pertenecen a la cadena y reencadena si la cadena empieza en el génesis                                                         | `Blockchain.isolate_invalid_transactions()` |
| `rechazar-pendientes` | Pasa a `rejected` las filas del pool que no serían admitidas; no reencadena                                                                                             | `Blockchain.reject_invalid_pending()`       |
| `reagrupar`           | Cierra el pool en un bloque nuevo, que es la agrupación de siempre                                                                                                      | `Blockchain.group_pending()`                |
| `fijar-sello`         | Escribe el sello en la cabeza actual; sin adaptador o sin bloques avisa y no escribe                                                                                    | `SelloDeVigilancia.fijar()`                 |

El panel solo pinta tres botones —`reparar-todo`, `reagrupar` y `fijar-sello`—, que
son los que resuelven los hallazgos que la interfaz puede ofrecer; las tres claves
restantes de la ruta se ejercitan en las pruebas de integración. Cada reparación que
reencadena o cambia estados va dentro de una sola unidad de trabajo: o se aplican
todas sus escrituras o ninguna. Reencadenar devuelve la coherencia, no el contenido
original de un dato alterado o borrado; un hueco de índices o un bloque borrado en
medio no se repara desde la interfaz.

**Qué tablas se tocan.** La verificación y la auditoría, ninguna: `verify_chain` solo
lee `blocks` y `transactions` (REQ-22), y `auditar` lee `blocks`, `transactions` y
`wallets` y no escribe ni tablas ni el archivo del sello. La ruta de verificación sí
puede insertar una fila antes de verificar, porque `abrir_cadena()` asegura el génesis
con `ensure_genesis`: si la cadena no tiene eslabón cero, lo inserta. Es el único caso,
y es idempotente: con el génesis ya presente solo consulta `blocks.get_by_index(0)`.
Las reparaciones escriben `blocks` (`UPDATE` de los dos hashes), `transactions`
(`UPDATE` de estado y `block_id`) y, al reagrupar, las dos tablas de la agrupación.

**Qué consultas se ejecutan.** La verificación y la auditoría leen:

```sql
SELECT * FROM blocks ORDER BY block_index
SELECT * FROM transactions WHERE block_id = %s ORDER BY created_at, id
SELECT * FROM transactions ORDER BY created_at, id
SELECT * FROM wallets WHERE id = %s
SELECT count(*) FROM wallets
```

El `SELECT` de `transactions` de la auditoría es único y completo: las filas se
agrupan por bloque en memoria y una caché evita repetir la lectura de la misma wallet,
así que no hay una consulta por bloque. Las reparaciones escriben:

```sql
UPDATE blocks SET previous_hash = %s, hash = %s
WHERE id = %s
RETURNING *
```

```sql
UPDATE transactions
SET status = 'rejected', block_id = NULL
WHERE id = ANY(%s)
```

**Qué prueba lo demuestra.** `tests/unit/test_req_10_verificacion.py` (con los dobles
en memoria de `tests/dobles.py`: cadena intacta, monto alterado, hueco en los
índices, hash previo huérfano, génesis alterado y génesis borrado),
`tests/integration/test_req_10_alteracion.py` (altera una confirmada con `UPDATE`
directo y comprueba que la verificación señala su bloque),
`tests/integration/test_req_22_solo_lee.py` (el contenido de las tres tablas es el
mismo antes y después),
`tests/integration/test_req_24_rutas.py::test_req_27_get_verificar_devuelve_el_dictamen_y_el_bloque_alterado`
y, para la auditoría y las reparaciones, `tests/unit/test_auditoria.py`,
`tests/integration/test_auditoria.py`, `tests/unit/test_sello.py`,
`tests/integration/test_sello.py`, `tests/unit/test_reparacion.py`,
`tests/integration/test_reparacion.py`,
`tests/integration/test_persistencia_de_reparacion.py` y
`tests/integration/test_verificar_auditoria.py` (el panel, la confirmación obligatoria,
la acción desconocida, el reencadenado, el aislamiento, el reagrupado y el sellado).

**Evidencia visual.** La captura `06-verificar.png` muestra el panel completo: «La
cadena es válida», las cifras de la auditoría, el sello de vigilancia en «Coincide»,
cero hallazgos, la reparación sugerida y la tabla de bloques.
`28-auditoria-detecta-sello-no-coincide.png` muestra el mismo panel con el sello en
«No coincide» y un hallazgo crítico («El sello no coincide con la cadena») junto con la
reparación de fijarlo. Las capturas `17-flujo-cadena-verificada.png`,
`18-alteracion-detectada.png` y `19-alteracion-revertida.png` son del 4 de noviembre y
muestran el dictamen y el ida y vuelta de la alteración en la versión anterior de la
página, sin panel de auditoría.

## CU-05: consultar el historial de una wallet

**Qué hace la persona.** Abre `/historial/<identificador>` con el identificador que
muestra el panel lateral —la forma corta; el valor completo viaja en el `title` y en el
botón de copiar— y recibe sus movimientos con el estado de cada uno.

**Qué ruta la recibe.** `historial(wallet)` en `src/web/app.py` (REQ-28). Convierte
el texto a `UUID`: si no lo es, responde la página de error con 404 (RF-5). Después
busca la wallet en la fachada; si no existe, también responde 404 y nunca un error
del motor en pantalla.

**Qué método del dominio decide.** `Blockchain.wallet_history(wallet_id)`
(`src/domain/blockchain.py`) delega en `transactions.list(wallet_id=...)`, que mira
las dos direcciones: el historial de una wallet son sus envíos y sus recepciones
(REQ-13). La ruta solo pinta `historial.html` con el identificador, el emisor, el
receptor, el monto, el estado y el bloque de cada transacción, en forma corta y
monoespaciada con el valor completo en el marcado; si no hay ninguna, muestra el
historial vacío.

**Qué tabla se toca.** Ninguna: solo lee `wallets` y `transactions`.

**Qué consultas se ejecutan.**

```sql
SELECT * FROM wallets WHERE id = %s
```

```sql
SELECT * FROM transactions
WHERE (sender_id = %s OR receiver_id = %s)
ORDER BY created_at, id
LIMIT %s
```

**Qué prueba lo demuestra.** `tests/integration/test_req_13_historial.py` (listados y
conteos de las tres tablas, filtro por estado, filtro por wallet en las dos
direcciones y wallet sin movimientos),
`tests/integration/test_req_24_rutas.py::test_req_28_get_historial_devuelve_las_transacciones_con_su_estado`
y `...::test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara`.

## El perfil, los contactos y el ayudante

Estas funciones no son casos de uso del eje: son lo que convierte el sistema en algo que
se usa como producto. El camino es el mismo para todas: alguien se registra, el
administrador aprueba su cuenta y entra.

**El perfil (`GET /perfil`).** Muestra el nombre de usuario, el tipo de cuenta, la fecha
de alta, la foto y, en las cuentas comunes, todas sus wallets (REQ-47). La foto es
opcional: se acepta un JPEG, PNG o WebP de hasta 2 MB, el servidor reconoce el
tipo por los primeros bytes (un SVG se rechaza porque puede llevar código) y guarda el
archivo en `FOTOS_DIR` mientras la base apunta a él. Sin foto —o si el archivo ya no
está— la interfaz pinta la inicial del nombre.

**El cambio de contraseña (`POST /perfil/contrasena`).** El usuario común escribe su
contraseña actual y la nueva; el sistema guarda la nueva **hasheada y pendiente**, y el
administrador la aprueba o la rechaza con un motivo desde `GET /admin/pendientes`. Hasta
que se apruebe, sigue valiendo la anterior. El administrador, que no tiene a quién
pedírselo, la aplica de inmediato.

**Los contactos (`GET /mis-contactos`).** La agenda se arma por nombre de usuario, sólo de
cuentas comunes aprobadas, sin poder agregarse a uno mismo ni repetir. Es de un solo
sentido: agregar a alguien no lo obliga a agregarte. Cada contacto muestra cuántos
movimientos tienen en común y cuándo fue el último.

**El idioma (`POST /idioma`).** La interfaz se ve en español o en inglés, y la elección se
guarda en una cookie que dura un año: vale también en el ingreso y el registro, antes de
que haya sesión. El español es la clave del catálogo, así que una frase sin traducir se ve
en español en vez de romper la página.

**El ayudante (`GET /asistente`).** Es una pestaña, no una ventana flotante: el tutor pidió
que el módulo sirviera para analítica, y una ventana no da espacio. Hoy explica en palabras
simples qué pasa con la cuenta y con la pantalla, y contesta preguntas con una guía local
que funciona sin red. Con `ASISTENTE_API_KEY` configurada, una pregunta escrita a mano la
responde un servicio de IA, con el resumen de la cuenta de la sesión y un aviso visible de
que esos datos salen del equipo. No escribe, no firma y no mueve dinero.

Estas funciones cubren del REQ-40 al REQ-45 del diseño de perfil, contactos, fotos y
ayudante, y la wallet con dueño añade el REQ-46 y el REQ-47. La captura
`22-mis-contactos.png` muestra la agenda con el número de movimientos y la última fecha de
cada contacto; `11-asistente.png` y `23-asistente-conversacion.png` muestran el ayudante en
modo guía local, sin proveedor de IA configurado. `26-multiwallets-tablero.png` y
`27-multiwallets-perfil.png` muestran la elección entre varias wallets y el perfil con
todas ellas; el cambio de contraseña aparece en su formulario dentro de
`27-multiwallets-perfil.png`, aunque no hay captura del flujo de aprobación.

**Qué prueba lo demuestra.** `tests/integration/test_perfil.py`, `test_foto.py`,
`test_contactos.py`, `test_idioma.py` y `test_asistente.py`; el diseño con sus
requerimientos está en `docs/superpowers/specs/2026-10-31-perfil-contactos-fotos-asistente-design.md`.

## Preguntas probables del tutor y dónde vive cada respuesta

| Pregunta                                                                 | Respuesta                                                                                                                                                                                                                                | Dónde vive                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ¿Dónde se comprueba que el monto sea positivo y de ocho decimales?       | En el dominio, antes de escribir, con motivo explícito; el `CHECK` del esquema queda como respaldo                                                                                                                                       | `Transaction.validate`, `tests/unit/test_req_04_formato.py`, `db/init.sql`                                                                                                                                                                                                   |
| ¿Por qué el saldo disponible descuenta lo que está en el pool?           | Porque lo comprometido ya no se puede gastar dos veces: es lo que hace que dos transacciones que juntas exceden no pasen las dos (REQ-06)                                                                                                | `available_balance`, `tests/unit/test_req_05_saldo.py`, `test_req_06_dos_transacciones_que_juntas_exceden_no_pasan_las_dos`                                                                                                                                                  |
| ¿Cómo se detecta un cambio hecho con `UPDATE` directo en la base?        | El hash del bloque cubre la forma canónica de sus transacciones; al recalcularlo no coincide con el guardado y la verificación señala ese índice                                                                                         | `Block.calculate_hash`, `verify_chain`, `tests/integration/test_req_10_alteracion.py`                                                                                                                                                                                        |
| ¿Por qué el hash de la transacción no incluye el estado ni el bloque?    | Porque ambos cambian al agrupar y el hash se calcula antes; incluirlos rompería el encadenamiento                                                                                                                                        | `Transaction.hash_payload`, `test_req_07_el_payload_del_hash_es_la_cadena_canonica`                                                                                                                                                                                          |
| ¿Qué pasa si falla la segunda escritura de la agrupación?                | El `ROLLBACK` deshace el bloque insertado y las transacciones siguen pendientes                                                                                                                                                          | `PostgresUnitOfWork`, `tests/integration/test_req_18_atomicidad.py`                                                                                                                                                                                                          |
| ¿Los errores de PostgreSQL se traducen a mensajes propios?               | No: suben crudos, y los `CHECK` no se duplican en Python (REQ-19)                                                                                                                                                                        | `src/persistence/postgres.py` (no hay ningún `except`), `tests/integration/test_req_19_errores_del_motor.py`                                                                                                                                                                 |
| ¿La verificación modifica algo?                                          | `verify_chain` no: compara hashes y solo lee. La ruta `GET /verificar` puede insertar el génesis si falta, porque `abrir_cadena()` lo asegura antes de verificar                                                                         | `tests/integration/test_req_22_solo_lee.py`, `ensure_genesis`                                                                                                                                                                                                                |
| ¿De dónde sale el dinero si el modelo del eje no tiene emisión?          | De la wallet del constituyente, que es la puerta de entrada del capital y la única que puede quedar en negativo                                                                                                                          | README, `src/bootstrap.py`, `tests/integration/test_bootstrap.py::test_req_02_la_emision_fundacional_esta_firmada_por_el_constituyente`                                                                                                                                      |
| ¿Cuál es la wallet del fondo y cómo se distingue un aporte de un retiro? | Por la constante `FONDO`; un aporte va hacia ella y un retiro sale de ella, porque el modelo no tiene columna para esa distinción                                                                                                        | README, `src/bootstrap.py` (decisión 8 del diseño)                                                                                                                                                                                                                           |
| ¿El dominio depende de PostgreSQL?                                       | No: habla con los protocolos de `ports.py`, y cargarlo no importa `psycopg`                                                                                                                                                              | `src/persistence/ports.py`, `tests/unit/test_req_16_dominio_aislado.py`, `tests/test_explicacion.py::test_req_17_las_pruebas_unitarias_no_dependen_de_la_base`                                                                                                               |
| ¿Por qué hay un índice único sobre la firma si el eje no lo trae?        | Es la única desviación, aprobada el 2026-10-10: el dominio informa el motivo y el esquema garantiza la unicidad                                                                                                                          | `db/init.sql`, `tests/integration/test_req_03_firma_repetida.py`                                                                                                                                                                                                             |
| ¿La presentación decide reglas de negocio?                               | No: cada ruta toma el formulario, llama a la fachada y pinta una plantilla (REQ-29)                                                                                                                                                      | `src/web/app.py`, `tests/unit/test_req_29_presentacion.py`                                                                                                                                                                                                                   |
| ¿De dónde sale el panel de wallets con saldos del administrador?         | Cada ruta del administrador pasa `datos_del_panel(chain)` (`src/web/panel.py`), que devuelve la lista y los saldos juntos; la cola de pendientes usa la misma fuente y la página de error no la recibe porque no abre el ledger (REQ-29) | `src/web/panel.py`, `src/web/app.py`, `src/web/admin.py`, `tests/integration/test_req_24_rutas.py::test_req_29_el_panel_con_saldos_aparece_en_todas_las_paginas_del_administrador`, `tests/integration/test_req_31_cola.py::test_req_31_la_cola_muestra_el_panel_con_saldos` |
| ¿La página de error depende de la base de datos?                         | No: no recibe el panel y `base.html` lo omite si no está definido, así que un 404 se pinta aunque el ledger no abra y nunca escribe el génesis                                                                                           | `src/web/app.py`, `base.html`, `tests/integration/test_req_24_rutas.py::test_req_28_rf5_la_pagina_de_error_no_depende_del_ledger`                                                                                                                                            |
| ¿Cómo se sabe que corre en el piso de Python 3.11?                       | `pyproject.toml` declara `requires-python = ">=3.11"`; la corrida dentro del contenedor del piso es la que lo confirma                                                                                                                   | `pyproject.toml`, `tests/test_explicacion.py::test_req_20_el_interprete_cumple_el_piso_declarado`, README                                                                                                                                                                    |
| ¿Qué pasa si se pide el historial de una wallet que no existe?           | La ruta valida el identificador y responde la página de error con 404 (RF-5)                                                                                                                                                             | `src/web/app.py`, `tests/integration/test_req_24_rutas.py::test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara`                                                                                                                              |
| ¿Quién puede ser dueño de una wallet?                                    | Solo una cuenta común aprobada; el servicio valida existencia, estado y rol antes de escribir, y un dueño que no sirve no crea la wallet (REQ-46)                                                                                        | `Cuentas.registrar_wallet`, `_puede_ser_dueno`, `tests/integration/test_req_46_registro_con_dueno.py`                                                                                                                                                                        |
| ¿Puede una cuenta tener varias wallets y cómo elige con cuál opera?      | Sí (REQ-47): la propiedad vive en `wallets.owner_id`; la principal es la más antigua y el tablero guarda la elegida en `wallet_elegida` (`POST /mi-wallet`)                                                                              | `src/web/user.py`, `src/web/templates/perfil.html`, `tests/integration/test_req_47_varias_wallets.py`                                                                                                                                                                        |
| ¿Qué es el sello de vigilancia y qué detecta?                            | Un archivo JSON fuera de la base con la altura y el hash de la cabeza, firmado con HMAC-SHA256; detecta el recorte de la cola                                                                                                            | `src/persistence/sello.py`, `src/domain/auditoria.py`, `tests/unit/test_sello.py`                                                                                                                                                                                            |
| ¿Qué pasa si no hay un sello fijado?                                     | La auditoría lo declara como nota, muestra «Sin fijar» y añade el límite del recorte: sin ancla externa, un recorte es indistinguible de una cadena que nunca tuvo esos bloques                                                          | `_revisar_sello`, `_limites`, `tests/unit/test_auditoria.py`, `tests/integration/test_verificar_auditoria.py`                                                                                                                                                                |
| ¿La auditoría de `/verificar` repara algo?                               | No: solo lee y enumera hallazgos; reparar es `POST /verificar/reparar` con la casilla `confirmar=si` y una redirección 303 al panel                                                                                                      | `verificar()`, `reparar()`, `tests/integration/test_verificar_auditoria.py`                                                                                                                                                                                                  |
| ¿Qué repara «reparar todo» y qué deja sin resolver?                      | Rechaza el pool inválido, aísla las confirmadas inválidas y reencadena; no recupera el contenido alterado ni borrado, no cierra huecos de índices y no renumera                                                                          | `Blockchain.repair_all`, `src/domain/reparacion.py`, `tests/unit/test_reparacion.py`                                                                                                                                                                                         |
| ¿Cómo se sabe que la auditoría no escribe nada?                          | Una prueba compara el contenido de las tablas antes y después, y la de `/verificar` comprueba además que no se escribe el archivo del sello (REQ-22)                                                                                     | `tests/integration/test_auditoria.py`, `tests/integration/test_verificar_auditoria.py::test_verificar_sigue_sin_escribir_filas`                                                                                                                                              |
| ¿El ayudante usa inteligencia artificial?                                | Siempre responde la guía local sin red; con `ASISTENTE_API_KEY` configurada, una pregunta escrita a mano la contesta el proveedor con el resumen de la cuenta de la sesión y el aviso de privacidad visible                              | `src/web/asistente.py`, `src/web/ia.py`, `tests/integration/test_asistente.py`, `tests/unit/test_asistente_ia.py`                                                                                                                                                            |
| ¿Qué encontró el pentest?                                                | Cuatro hallazgos abiertos con remediación propuesta —tres de severidad media y uno baja—, ninguno alto ni crítico; no apareció inyección de SQL ni XSS                                                                                   | `docs/pentesting/informe.md`, `docs/pentesting/informe.pdf`, `docs/pentesting/matriz-trazabilidad.md`                                                                                                                                                                        |
| ¿Cuántos requerimientos y casos de uso tiene el proyecto?                | Cinco casos de uso y cuarenta y siete requerimientos (REQ-01 a REQ-47); la guarda exige los cinco CU y los 39 numerados (REQ-01 a REQ-39) más REQ-46/REQ-47, y REQ-40 a REQ-45 se verifican en sus archivos por caso                     | `tests/test_explicacion.py`, `docs/entrega-final.md`                                                                                                                                                                                                                         |
| ¿Cómo se sabe que la explicación no se separó del código?                | Una prueba exige que los cinco casos de uso estén en este recorrido y que cada requerimiento tenga su prueba: los 39 numerados (REQ-01 a REQ-39) y REQ-46/REQ-47 con `test_req_NN_`, y REQ-40 a REQ-45 en sus archivos por caso          | `tests/test_explicacion.py`                                                                                                                                                                                                                                                  |
