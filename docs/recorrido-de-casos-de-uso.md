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
usa `ledger_state()` y hace un `SELECT count(*)` por tabla para mostrar los conteos.

La interfaz no explica el proyecto: los títulos nombran la acción —«Registrar wallet»,
«Nueva transacción», «Cerrar bloque», «Verificar cadena», «Historial»— y ninguna página
lleva párrafos sobre el eje ni números de caso de uso. `base.html` pinta una barra
superior con el nombre de la aplicación y los cuatro enlaces a las rutas, un panel
lateral con las wallets —forma corta en monoespaciada, botón que copia la clave y
enlace a su historial; «Todavía no hay wallets» cuando no hay ninguna— y el área de
contenido. El panel lo pasa cada ruta con `wallets_del_panel=chain.wallets.list()`, una
sola vez por página: no hay procesador de contexto, porque abrir el ledger al pintar la
página de error convertiría un 404 sin base en un 500 y podría escribir el génesis.
`base.html` envuelve el panel en `{% if wallets_del_panel is defined %}` y la página de
error no lo pasa, así que se pinta sin tocar la fachada. Los identificadores, hashes,
montos, fechas y conteos van en `code` o en la clase `.mono`; las claves, los
identificadores y los hashes se ven en forma corta, y el valor completo sigue en el
atributo `title` y en `data-copiar`, que es lo que copian los botones con el guion de
`base.html`.

## CU-01: registrar una wallet

**Qué hace la persona.** Entra a `GET /wallets`, ve el formulario, lo envía por
`POST /wallets` y recibe la clave pública con la que su wallet queda identificada.

**Qué ruta la recibe.** `wallets()` en `src/web/app.py` (REQ-24). El `GET` pinta
`wallet.html` sin wallet; el `POST` llama a la fachada y pinta la misma plantilla con
la wallet creada. La lista de wallets no la pinta esta ruta: vive en el panel lateral,
así que el CU-05 queda a un clic desde cualquier página.

**Qué método del dominio decide.** `Blockchain.register_wallet()`
(`src/domain/blockchain.py`) llama a `create_wallet()` (`src/domain/wallet.py`), que
genera el par con `generate_private_key()` sobre `secp256k1`, serializa la pública
como punto comprimido en hexadecimal (`public_key_hex`), cifra el DER de la privada
con `Fernet` y la clave maestra (`encrypt_private_key`) y fija el identificador con
`uuid4` y la marca de tiempo con el reloj inyectado. Ninguna capa decide reglas: solo
se generan llaves y se guardan.

**Qué tabla se toca.** `wallets`, con una fila nueva.

**Qué consulta se ejecuta.**

```sql
INSERT INTO wallets (id, public_key, private_key_encrypted, created_at)
VALUES (%s, %s, %s, %s)
RETURNING *
```

`RETURNING *` devuelve la fila tal como quedó en la base y no la que se propuso. Si
la pública chocara con `uq_wallets_public_key`, el error del motor sube sin traducir
(REQ-19), que es el flujo alterno de la ficha.

**Qué prueba lo demuestra.** `tests/unit/test_req_01_wallet.py`
(`test_req_01_la_privada_no_esta_en_claro_en_la_wallet`,
`test_req_01_dos_wallets_no_comparten_publica`),
`tests/integration/test_req_01_wallet_en_base.py` (la pública queda única y no vacía,
y el texto plano de la privada no aparece en la base) y
`tests/integration/test_req_24_rutas.py::test_req_24_post_wallets_devuelve_200_con_la_publica`.

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

## CU-04: verificar la integridad de la cadena

**Qué hace la persona.** Entra a `GET /verificar` y recibe el dictamen: la cadena es
válida o el índice del primer bloque que no encaja.

**Qué ruta la recibe.** `verificar()` en `src/web/app.py` (REQ-27) llama a
`Blockchain.verify_chain()` y pinta `verificar.html`.

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

**Qué tabla se toca.** Ninguna por la verificación: `verify_chain` solo lee `blocks` y
`transactions` (REQ-22). La ruta sí puede escribir una fila antes de verificar, porque
`abrir_cadena()` asegura el génesis con `ensure_genesis`: si la cadena no tiene eslabón
cero, lo inserta. Es el único caso, y es idempotente: con el génesis ya presente solo
consulta `blocks.get_by_index(0)`.

**Qué consultas se ejecutan.**

```sql
SELECT * FROM blocks ORDER BY block_index
SELECT * FROM transactions WHERE block_id = %s ORDER BY created_at, id
```

**Qué prueba lo demuestra.** `tests/unit/test_req_10_verificacion.py` (con los dobles
en memoria de `tests/dobles.py`: cadena intacta, monto alterado, hueco en los
índices, hash previo huérfano, génesis alterado y génesis borrado),
`tests/integration/test_req_10_alteracion.py` (altera una confirmada con `UPDATE`
directo y comprueba que la verificación señala su bloque),
`tests/integration/test_req_22_solo_lee.py` (el contenido de las tres tablas es el
mismo antes y después) y
`tests/integration/test_req_24_rutas.py::test_req_27_get_verificar_devuelve_el_dictamen_y_el_bloque_alterado`.
El procedimiento manual, con la aplicación corriendo, está en el README.

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

## Preguntas probables del tutor y dónde vive cada respuesta

| Pregunta                                                                 | Respuesta                                                                                                                                                        | Dónde vive                                                                                                                                                     |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ¿Dónde se comprueba que el monto sea positivo y de ocho decimales?       | En el dominio, antes de escribir, con motivo explícito; el `CHECK` del esquema queda como respaldo                                                               | `Transaction.validate`, `tests/unit/test_req_04_formato.py`, `db/init.sql`                                                                                     |
| ¿Por qué el saldo disponible descuenta lo que está en el pool?           | Porque lo comprometido ya no se puede gastar dos veces: es lo que hace que dos transacciones que juntas exceden no pasen las dos (REQ-06)                        | `available_balance`, `tests/unit/test_req_05_saldo.py`, `test_req_06_dos_transacciones_que_juntas_exceden_no_pasan_las_dos`                                    |
| ¿Cómo se detecta un cambio hecho con `UPDATE` directo en la base?        | El hash del bloque cubre la forma canónica de sus transacciones; al recalcularlo no coincide con el guardado y la verificación señala ese índice                 | `Block.calculate_hash`, `verify_chain`, `tests/integration/test_req_10_alteracion.py`                                                                          |
| ¿Por qué el hash de la transacción no incluye el estado ni el bloque?    | Porque ambos cambian al agrupar y el hash se calcula antes; incluirlos rompería el encadenamiento                                                                | `Transaction.hash_payload`, `test_req_07_el_payload_del_hash_es_la_cadena_canonica`                                                                            |
| ¿Qué pasa si falla la segunda escritura de la agrupación?                | El `ROLLBACK` deshace el bloque insertado y las transacciones siguen pendientes                                                                                  | `PostgresUnitOfWork`, `tests/integration/test_req_18_atomicidad.py`                                                                                            |
| ¿Los errores de PostgreSQL se traducen a mensajes propios?               | No: suben crudos, y los `CHECK` no se duplican en Python (REQ-19)                                                                                                | `src/persistence/postgres.py` (no hay ningún `except`), `tests/integration/test_req_19_errores_del_motor.py`                                                   |
| ¿La verificación modifica algo?                                          | `verify_chain` no: compara hashes y solo lee. La ruta `GET /verificar` puede insertar el génesis si falta, porque `abrir_cadena()` lo asegura antes de verificar | `tests/integration/test_req_22_solo_lee.py`, `ensure_genesis`                                                                                                  |
| ¿De dónde sale el dinero si el modelo del eje no tiene emisión?          | De la wallet del constituyente, que es la puerta de entrada del capital y la única que puede quedar en negativo                                                  | README, `src/bootstrap.py`, `tests/integration/test_bootstrap.py::test_req_02_la_emision_fundacional_esta_firmada_por_el_constituyente`                        |
| ¿Cuál es la wallet del fondo y cómo se distingue un aporte de un retiro? | Por la constante `FONDO`; un aporte va hacia ella y un retiro sale de ella, porque el modelo no tiene columna para esa distinción                                | README, `src/bootstrap.py` (decisión 8 del diseño)                                                                                                             |
| ¿El dominio depende de PostgreSQL?                                       | No: habla con los protocolos de `ports.py`, y cargarlo no importa `psycopg`                                                                                      | `src/persistence/ports.py`, `tests/unit/test_req_16_dominio_aislado.py`, `tests/test_explicacion.py::test_req_17_las_pruebas_unitarias_no_dependen_de_la_base` |
| ¿Por qué hay un índice único sobre la firma si el eje no lo trae?        | Es la única desviación, aprobada el 2026-10-10: el dominio informa el motivo y el esquema garantiza la unicidad                                                  | `db/init.sql`, `tests/integration/test_req_03_firma_repetida.py`                                                                                               |
| ¿La presentación decide reglas de negocio?                               | No: cada ruta toma el formulario, llama a la fachada y pinta una plantilla (REQ-29)                                                                              | `src/web/app.py`, `tests/unit/test_req_29_presentacion.py`                                                                                                     |
| ¿De dónde sale la lista de wallets que se ve en todas las páginas?       | Cada ruta pasa `wallets_del_panel=chain.wallets.list()`, una sola vez por página; la presentación no consulta por su cuenta (REQ-29)                             | `src/web/app.py`, `src/web/templates/base.html`, `tests/integration/test_req_24_rutas.py::test_req_29_el_panel_lateral_aparece_en_todas_las_paginas`           |
| ¿La página de error depende de la base de datos?                         | No: no recibe el panel y `base.html` lo omite si no está definido, así que un 404 se pinta aunque el ledger no abra y nunca escribe el génesis                   | `src/web/app.py`, `base.html`, `tests/integration/test_req_24_rutas.py::test_req_28_rf5_la_pagina_de_error_no_depende_del_ledger`                              |
| ¿Cómo se sabe que corre en el piso de Python 3.11?                       | `pyproject.toml` declara `requires-python = ">=3.11"`; la corrida dentro del contenedor del piso es la que lo confirma                                           | `pyproject.toml`, `tests/test_explicacion.py::test_req_20_el_interprete_cumple_el_piso_declarado`, README                                                      |
| ¿Qué pasa si se pide el historial de una wallet que no existe?           | La ruta valida el identificador y responde la página de error con 404 (RF-5)                                                                                     | `src/web/app.py`, `tests/integration/test_req_24_rutas.py::test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara`                |
| ¿Cómo se sabe que la explicación no se separó del código?                | Una prueba exige que los cinco casos de uso estén en este recorrido y que los 29 requerimientos tengan su `test_req_NN_`                                         | `tests/test_explicacion.py`                                                                                                                                    |
