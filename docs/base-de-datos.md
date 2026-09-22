# Base de datos

Modelo de datos del ledger local. La fuente de verdad es `database/init/01_schema.sql`, aplicado automáticamente al crear el volumen del contenedor. Los comandos para levantar el motor están en `puesta-en-marcha.md`.

## Modelo

| Tabla          | Contenido                                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| `wallets`      | Par de llaves de cada participante. La pública identifica; la privada firma y se guarda cifrada en `BYTEA`. |
| `blocks`       | Bloques de la cadena: índice, timestamp, hash del bloque anterior y hash propio.                            |
| `transactions` | Transferencias firmadas. `block_id` nulo significa que la transacción sigue en el pool de pendientes.       |

## `wallets`

| Columna                 | Tipo          | Restricción                                       |
| ----------------------- | ------------- | ------------------------------------------------- |
| `id`                    | `UUID`        | Clave primaria, generada con `uuid_generate_v4()` |
| `public_key`            | `TEXT`        | Única y no vacía                                  |
| `private_key_encrypted` | `BYTEA`       | No vacía. Nunca texto plano.                      |
| `created_at`            | `TIMESTAMPTZ` | Por defecto `NOW()`                               |

## `blocks`

| Columna         | Tipo          | Restricción                                       |
| --------------- | ------------- | ------------------------------------------------- |
| `id`            | `UUID`        | Clave primaria, generada con `uuid_generate_v4()` |
| `block_index`   | `INTEGER`     | Único, no negativo                                |
| `timestamp`     | `TIMESTAMPTZ` | Por defecto `NOW()`                               |
| `previous_hash` | `CHAR(64)`    | SHA-256 en hexadecimal minúscula                  |
| `hash`          | `CHAR(64)`    | Único, SHA-256 en hexadecimal minúscula           |

Además de las restricciones por columna, un `CHECK` de tabla exige que `hash` y `previous_hash` difieran, salvo en el bloque génesis, donde el índice es cero y ambos podrían coincidir.

## `transactions`

| Columna       | Tipo             | Restricción                                                           |
| ------------- | ---------------- | --------------------------------------------------------------------- |
| `id`          | `UUID`           | Clave primaria, generada con `uuid_generate_v4()`                     |
| `sender_id`   | `UUID`           | Clave foránea a `wallets`, con `ON DELETE RESTRICT`                   |
| `receiver_id` | `UUID`           | Clave foránea a `wallets`, con `ON DELETE RESTRICT`                   |
| `amount`      | `NUMERIC(18, 8)` | Positivo                                                              |
| `status`      | `VARCHAR(20)`    | `pending`, `confirmed` o `rejected`. Por defecto `pending`.           |
| `signature`   | `TEXT`           | No vacía                                                              |
| `block_id`    | `UUID`           | Clave foránea a `blocks`, nula mientras la transacción está pendiente |
| `created_at`  | `TIMESTAMPTZ`    | Por defecto `NOW()`                                                   |

Un `CHECK` de tabla amarra el estado con el bloque: `confirmed` exige `block_id` no nulo, y `pending` o `rejected` exigen `block_id` nulo. La coherencia no depende de la aplicación.

Otro `CHECK` impide que emisor y receptor sean la misma wallet, lo que descarta la auto-transferencia.

## Índices

| Índice                         | Sobre                        | Para qué                                            |
| ------------------------------ | ---------------------------- | --------------------------------------------------- |
| `idx_transactions_sender_id`   | `transactions (sender_id)`   | Consultar las transacciones emitidas por una wallet |
| `idx_transactions_receiver_id` | `transactions (receiver_id)` | Consultar las transacciones recibidas               |
| `idx_transactions_block_id`    | `transactions (block_id)`    | Reconstruir el contenido de un bloque               |
| `idx_transactions_status`      | `transactions (status)`      | Leer el pool de pendientes                          |

`blocks.block_index` y las restricciones de unicidad ya quedan indexados por sus propias restricciones.

## Datos de prueba

`02_seed.sql` es idempotente: se puede aplicar sobre una base ya poblada sin duplicar filas. Inserta, en este orden:

1. **Tres wallets**: Alice, Bob y Carol, con identificadores fijos y llaves privadas que son material cifrado simulado.
2. **Dos bloques**: el génesis, de índice cero, cuyo `previous_hash` son sesenta y cuatro ceros, y un bloque de índice uno encadenado a él.
3. **Tres transacciones**: dos confirmadas dentro del bloque uno y una pendiente en el pool, sin bloque asignado.

La intención es que el seed cubra los tres estados posibles y las dos situaciones de `block_id`, de modo que cualquier consulta de prueba tenga datos en ambos lados.

## Verificación del esquema

Con el contenedor arriba, `make tables`, `make schema` y `make counts` listan las tablas, describen sus columnas y cuentan sus filas. Los comandos equivalentes de `psql` están en `puesta-en-marcha.md`.

## Estructura congelada

La estructura del esquema no se modifica: no se agregan ni se alteran tablas, columnas, constraints ni índices. Lo que está documentado arriba es lo que hay, y el caso de aplicación se resuelve con eso; el ADR-0004 explica cómo.

La razón de la restricción es que `01_schema.sql` y `02_seed.sql` son scripts de inicialización, no de migración: el contenedor solo los ejecuta al crear el volumen, y un cambio aplicado a mano en una base que ya existe quedaría sin reflejo en los scripts. Cualquier cambio en `database/` requiere confirmación explícita de los desarrolladores antes de escribirse.
