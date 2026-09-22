# ADR-0002: PostgreSQL como persistencia

- **Estado**: aceptado
- **Fecha**: 2026-09-21

## Contexto

La documentación inicial dejaba la persistencia abierta entre SQLite y JSON, "por definir según volumen de datos". La entrega de la Fase 2 ya implementó un esquema relacional sobre PostgreSQL 16, aplicado por `database/init/01_schema.sql` y `database/init/02_seed.sql`, con constraints, índices y tipos específicos.

Mantener la decisión abierta en el README mientras el esquema ya está escrito deja al lector sin saber cuál es la fuente de verdad.

## Decisión

La persistencia es PostgreSQL 16, provisto por el contenedor de `docker-compose.yml` y levantado con Docker Compose. Los scripts de `database/init/` se aplican solos al crear el volumen.

El esquema usa el modelo relacional para hacer cumplir en la base reglas que de otro modo vivirían solo en el código de aplicación:

- `NUMERIC(18, 8)` para el monto, que evita el error de redondeo de la aritmética de punto flotante en valores monetarios.
- `BYTEA` para `private_key_encrypted`, que impide guardar la llave privada en texto plano por accidente.
- Un `CHECK` sobre el formato SHA-256 de `blocks.hash` y `blocks.previous_hash`.
- Un `CHECK` que amarra `transactions.status` con `transactions.block_id`: confirmada exige bloque, pendiente y rechazada exigen bloque nulo.
- Claves foráneas con `ON DELETE RESTRICT`, que impiden borrar una wallet o un bloque que tenga transacciones asociadas.

## Consecuencias

- Levantar el entorno exige Docker Compose. No hay modo de ejecutar el sistema sin contenedor.
- El backend futuro consume la variable `DATABASE_URL` del archivo `.env`.
- Los scripts de `database/` son de inicialización, no de migración: solo corren al crear el volumen. La estructura del esquema está congelada, así que el diseño se apoya en lo que ya está definido y ninguna decisión posterior puede ampliarla sin confirmación explícita de los desarrolladores.
- La coherencia entre estado y bloque queda garantizada por la base, así que la aplicación no necesita duplicar esa validación.
- Queda descartado el soporte de SQLite o JSON que mencionaba la documentación inicial.

## Alternativas consideradas

- **SQLite**: suficiente para un nodo único, pero no ofrece el mismo nivel de constraints y tipos, y no encaja con el contenedor que la Fase 2 ya entrega.
- **JSON en disco**: descartado. Sin transacciones ni constraints, la integridad del ledger dependería de código propio y no habría forma de auditar el estado.
