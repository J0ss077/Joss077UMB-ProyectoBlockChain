# ADR-0005: Arquitectura en capas con el núcleo de dominio aislado

- **Estado**: propuesto
- **Fecha**: 2026-09-21

## Contexto

El diseño del proyecto deja abierto el tipo de arquitectura. El dominio tiene cinco clases —`Wallet`, `Transaction`, `Block`, `Blockchain` y `TransactionStatus`— y una sola dependencia externa, PostgreSQL.

La afirmación central del proyecto es que toda modificación del historial resulta detectable. Comprobarla exige una prueba que altere un registro ya confirmado por fuera de la aplicación, es decir, escribiendo directamente en la base, y luego pida a `Blockchain` que dictamine sobre la integridad de la cadena. Si las reglas de integridad viven mezcladas con el acceso a datos, esa prueba no se puede escribir sin depender del motor de persistencia.

A esto se suma que `Blockchain` concentra el pool de pendientes, la agrupación, la verificación y la consulta de historial. Es una clase con muchas responsabilidades, y el riesgo es que además absorba el SQL.

## Decisión

Se adopta una arquitectura en capas con tres niveles:

- **Presentación**: expone los casos de uso al usuario. Su forma todavía no está definida.
- **Dominio**: las cinco clases, con las reglas de firma, saldo, formato y encadenamiento. No importa nada de PostgreSQL.
- **Persistencia**: la única capa que habla SQL, detrás de una interfaz propia que el dominio consume.

Las capas criptográfica y de reglas de validación de la delimitación del proyecto viven ambas dentro del núcleo de dominio, porque comparten los mismos datos y no tienen motivo para separarse.

La comunicación es una llamada en memoria: el sistema es un proceso único y no hay protocolo de red que diseñar. `Blockchain` orquesta el dominio y cruza el límite de persistencia a través del puerto, sin conocer el motor que hay del otro lado.

## Consecuencias

- Las reglas de firma, saldo y encadenamiento se prueban sin base de datos, y la prueba de detección de alteración puede escribir un cambio a mano y comprobar que el sistema lo delata.
- Reemplazar PostgreSQL exige un adaptador nuevo, no tocar el dominio.
- El puerto de persistencia es lo que impide que `Blockchain` termine haciendo SQL. Si esa interfaz no se respeta, la separación queda solo en el diagrama.
- Una operación simple atraviesa una indirección más. Es el costo aceptado a cambio de poder probar las reglas de forma aislada.
- La capa de presentación queda deliberadamente sin definir. Su forma no cambia el núcleo de dominio, así que puede decidirse después.
- Este ADR queda en estado `propuesto`: la arquitectura es la que se documenta en `docs/arquitectura.md`, pero todavía no está refrendada por el equipo.

## Alternativas consideradas

- **Modelos activos que se persisten a sí mismos**: descartada porque ata el dominio al esquema relacional y hace que la prueba de detección de alteración dependa del mecanismo de persistencia en lugar de la base real.
- **Microservicios o arquitectura orientada a eventos**: descartada por el ADR-0001. El sistema es un nodo único sin concurrencia distribuida, así que añadiría infraestructura para resolver problemas que no tiene.
- **Un script único sin capas**: descartada porque mezcla el SQL con las reglas y vuelve imposible comprobar la integridad sin ensuciar la base.
- **Arquitectura hexagonal completa, con puertos para toda dependencia**: descartada por sobre-ingeniería. Solo hay un límite externo real, que es la persistencia.
