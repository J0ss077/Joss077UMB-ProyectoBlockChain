# Probar el camino de escritura y el rechazo de los CHECK

Status: ready-for-agent

## Contexto

La conexión y la lectura están comprobadas contra una base real. Ninguna operación de creación, actualización o borrado se ejecutó todavía, y tampoco se provocó un error de constraint.

El diseño de la capa de persistencia no repite las reglas del esquema: los errores de PostgreSQL se propagan tal cual. Eso es lo que hay que confirmar.

## Qué hacer

Con el contenedor arriba, ejercitar el CRUD completo desde `open_ledger()` y comprobar al menos dos rechazos:

- Confirmar una transacción sin bloque debe fallar por `chk_transactions_block_status_consistency`.
- Borrar una wallet con transacciones debe fallar por la clave foránea con `ON DELETE RESTRICT`.

## Done cuando

Las operaciones de escritura funcionan y los rechazos levantan el error del motor, no uno propio. El resultado queda anotado en el historial de la sesión.

## Comments
