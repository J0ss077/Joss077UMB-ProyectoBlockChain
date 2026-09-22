# Definir la regla de saldo en la lógica de negocio

Status: needs-info

## Contexto

El diseño del proyecto define la validación automática como la verificación de firma, saldo y formato. Como la estructura del esquema no se modifica, el saldo se deriva de las transacciones confirmadas y la regla vive en la lógica de negocio. El razonamiento está en el ADR-0004.

Nada de esto se implementa todavía, porque no existe código de aplicación.

## Qué falta

- Confirmar con los desarrolladores que el saldo se deriva y no se almacena.
- Definir el tratamiento de las transacciones pendientes en el cálculo.
- Definir el orden de validación que evita el doble gasto.

## Fuera de este ticket

Cualquier cambio en `database/`. La estructura del esquema está congelada: no se agregan ni se modifican tablas, columnas ni constraints.

## Done cuando

El ADR-0004 pasa de `propuesto` a `aceptado` y la lógica de negocio implementa la regla.

## Comments
