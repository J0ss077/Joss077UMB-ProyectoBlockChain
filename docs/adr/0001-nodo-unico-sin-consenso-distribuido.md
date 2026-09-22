# ADR-0001: Nodo único, sin red P2P ni consenso distribuido

- **Estado**: aceptado
- **Fecha**: 2026-09-21

## Contexto

El proyecto parte de una pregunta de la asignatura de sistemas transaccionales: cómo validar e integrar transacciones sin depender de una autoridad central. La respuesta completa a esa pregunta es una red de nodos con consenso distribuido, pero su costo de implementación —descubrimiento de pares, propagación de bloques, resolución de bifurcaciones, tolerancia a fallos bizantinos— es enorme frente al tiempo de una fase.

A la vez, los mecanismos que se quieren estudiar y demostrar —hash encadenado, validación automática de transacciones firmadas, inmutabilidad del historial— son independientes del consenso. Se pueden aislar y observar en un solo proceso.

## Decisión

El prototipo corre como un único nodo local. Hay un solo ledger, un solo pool de pendientes y una sola autoridad de agrupación. No hay red P2P, ni descubrimiento de pares, ni consenso distribuido, ni proof of work.

El verbo del dominio para producir un bloque es agrupar, no minar: no existe competencia por el derecho a producir el bloque siguiente.

## Consecuencias

- La integridad depende por completo del nodo. Si el proceso o su base de datos se corrompen, no hay otra copia que corrija el estado, así que el prototipo no es un sistema de producción. Sin replicación, se conserva el punto único de fallo que el proyecto critica.
- Un actor con control del nodo puede modificar el historial y recalcular todos los hashes posteriores, con lo que la verificación de la cadena no detectaría nada. El prototipo ofrece inmutabilidad verificable, no garantizada, y no pretende resistencia a la manipulación.
- `previous_hash` puede ser cualquier SHA-256 válido. No hace falta que cumpla una dificultad, porque no hay acertijo que resolver.
- La prevención de doble gasto depende del orden secuencial local, no de resolver conflictos en la cadena. Ver el ADR-0004.
- `CONTEXT.md` y el resto de la documentación tratan consenso distribuido, red P2P y minería como términos fuera de alcance, para que su aparición en una propuesta sea la señal de que el alcance se está corriendo.
- Escalar a varios nodos exige reabrir esta decisión, no extenderla.

## Alternativas consideradas

- **Red P2P con consenso real**: descartada por costo de implementación frente al valor didáctico en esta etapa.
- **Proof of work con dificultad ajustable**: descartada porque el acertijo es un mecanismo para asignar turnos de producción, y un nodo único no necesita asignar turnos.
- **Varios nodos sobre una base de datos compartida**: descartada porque simularía el consenso sin estudiarlo, dando complejidad sin fidelidad.
