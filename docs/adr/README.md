# Decisiones de arquitectura (ADR)

Un ADR registra una decisión difícil de revertir, junto con su contexto y sus consecuencias. Antes de contradecir uno, hay que leerlo y dejar constancia explícita del conflicto en lugar de sobrescribirlo en silencio.

## Índice

| ADR                                                        | Decisión                                        | Estado    |
| ---------------------------------------------------------- | ----------------------------------------------- | --------- |
| [0001](0001-nodo-unico-sin-consenso-distribuido.md)        | Nodo único, sin red P2P ni consenso distribuido | aceptado  |
| [0002](0002-postgresql-como-persistencia.md)               | PostgreSQL como persistencia                    | aceptado  |
| [0003](0003-estructura-del-repositorio-y-documentacion.md) | Estructura del repositorio y documentación      | aceptado  |
| [0004](0004-modelo-de-saldos-aportes-y-retiros.md)         | Modelo de saldos, aportes y retiros             | propuesto |

El ADR-0004 está en estado `propuesto`: todavía no está refrendado por el equipo. No bloquea el trabajo sobre la base de datos, porque la estructura del esquema está congelada.

## Cuándo escribir uno

Cuando la decisión sea costosa de revertir: motor de persistencia, alcance del sistema, estructura del repositorio. No cuando sea un detalle de implementación. Ante la duda, la pregunta es cuánto costaría deshacerla.

## Formato

El archivo se llama `NNNN-titulo-en-kebab-case.md`, numerado desde `0001`, y no se renumera nunca. El estado puede ser `propuesto`, `aceptado`, `reemplazado por ADR-NNNN` u `obsoleto`.

```markdown
# ADR-NNNN: Título

- **Estado**: propuesto
- **Fecha**: AAAA-MM-DD

## Contexto

Qué situación obliga a decidir.

## Decisión

Qué se decide, en presente y en voz activa.

## Consecuencias

Qué se gana, qué se pierde y qué queda obligado por esta decisión.

## Alternativas consideradas

Qué se descartó y por qué.
```
