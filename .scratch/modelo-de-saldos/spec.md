# Modelo de saldos, aportes y retiros

## Problema

El diseño del proyecto define la validación automática como la verificación de firma, saldo y formato, y el caso de aplicación es el registro de aportes y retiros de una organización del sector solidario. El esquema de la Fase 2 no tiene noción de saldo ni de organización, y sus datos de prueba son transferencias entre personas.

## Restricción

La estructura del esquema SQL está congelada. No se agregan ni se modifican tablas, columnas, constraints ni índices. El caso se resuelve con lo que ya existe.

## Cómo se resuelve

El saldo se deriva de las transacciones confirmadas en lugar de almacenarse, la organización se representa con una wallet identificada por convención, y la regla de saldo vive en la lógica de negocio porque depende de una agregación que el esquema no puede expresar. El razonamiento completo está en el ADR-0004.

## Issues

- `issues/01-definir-la-regla-de-saldo.md`
