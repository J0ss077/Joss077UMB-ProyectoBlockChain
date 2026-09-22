# Backend

## Estado

El primer corte está implementado y comprobado contra una base real: conexión, entidades y CRUD sobre las tres tablas. La conexión, la resolución de `DATABASE_URL` desde `.env` y la lectura quedaron verificadas con `make backend`. El camino de escritura todavía no se ejercitó.

## Qué falta

Las reglas de negocio que convierten el CRUD en un sistema transaccional: el hash del bloque, la firma de las transacciones, la agrupación en bloques, la validación de saldo y la verificación de la integridad de la cadena. También queda por definir la forma de la capa de presentación.

La restricción que atraviesa todo: la estructura del esquema SQL está congelada, según el ADR-0004.

## Issues

- `issues/01-refrendar-los-adr-0004-y-0005.md`
- `issues/02-probar-el-camino-de-escritura-y-los-check.md`
- `issues/03-calcular-el-hash-y-agrupar-bloques.md`
- `issues/04-firmar-transacciones-y-verificar-firmas.md`
- `issues/05-verificar-la-integridad-de-la-cadena.md`
- `issues/06-definir-la-capa-de-presentacion.md`

La validación de saldo tiene su propio ticket en `.scratch/modelo-de-saldos/`.
