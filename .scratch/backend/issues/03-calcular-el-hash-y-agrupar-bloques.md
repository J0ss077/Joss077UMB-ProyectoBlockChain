# Calcular el hash del bloque y agrupar transacciones

Status: ready-for-agent

## Contexto

`Block` y `Blockchain` hoy solo transportan datos. El hash no se calcula en ningún punto y no existe la operación de agrupar transacciones pendientes en un bloque.

El esquema exige que `hash` y `previous_hash` sean SHA-256 en hexadecimal minúscula de sesenta y cuatro caracteres, que `hash` y `block_index` sean únicos, que el índice no sea negativo y que `hash` y `previous_hash` difieran salvo en el bloque génesis.

## Qué hacer

- Calcular el hash de un bloque con SHA-256 a partir de su contenido.
- Implementar la agrupación: leer las transacciones pendientes, crear el bloque con el hash del último bloque como `previous_hash`, y pasar las transacciones a `confirmed` ligadas al bloque.
- Confirmar las dos escrituras juntas, porque el esquema exige que el estado y el bloque sean coherentes entre sí.

## Done cuando

Se puede agrupar un bloque desde el ledger y el resultado satisface todas las restricciones del esquema sin ayuda externa.

## Comments
