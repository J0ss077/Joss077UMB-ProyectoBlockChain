# Verificar la integridad de la cadena

Status: ready-for-agent
Blocked by: 03

## Contexto

Es la propiedad central del proyecto: que toda modificación del historial resulte detectable. `Blockchain` todavía no la implementa.

Depende de que los bloques tengan hashes reales, y por eso queda bloqueada por el ticket 03.

## Qué hacer

Recorrer la cadena comparando el `previous_hash` de cada bloque con el `hash` real del anterior, y dictaminar. La verificación solo lee: no modifica nada.

## Done cuando

Alterar a mano una transacción confirmada, o el hash de un bloque, hace que la verificación lo detecte y señale dónde ocurrió. Es la prueba que justifica el proyecto entero, así que conviene dejarla escrita como test.

## Comments
