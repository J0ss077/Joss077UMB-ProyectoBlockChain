# Arquitectura

Diseño del prototipo de sistema transaccional basado en blockchain. El vocabulario de este documento es el de `CONTEXT.md`; las decisiones cerradas están en `docs/adr/`.

## Caso de aplicación

El sistema se plantea para una organización del sector solidario —un fondo de empleados, una asociación mutual— que administra recursos aportados periódicamente por sus asociados. En organizaciones pequeñas o medianas ese registro suele recaer en una sola figura, el tesorero, sobre hojas de cálculo o un aplicativo cerrado al que los asociados no acceden.

El problema no es que el tesorero sea deshonesto: es que hoy no existe un mecanismo independiente para comprobar el historial. Si alguien altera un aporte, no hay forma de detectarlo desde afuera. El sistema no reemplaza al tesorero ni elimina su rol; lo que aporta es que su palabra deje de ser la única garantía.

Por eso el criterio de éxito del prototipo no es impedir la alteración, sino volverla detectable. Esa es la propiedad que el caso de aplicación necesita y la que el diseño persigue.

## Propósito

Un sistema transaccional tradicional confía la validación de cada operación a una entidad central, lo que crea un punto único de fallo. Este proyecto propone una arquitectura alternativa: wallets con par de llaves, transacciones firmadas, validación automática y bloques enlazados por hash.

La diferencia con un sistema central no está en quién guarda los datos, sino en cómo se detecta la manipulación. Cada bloque guarda el hash del bloque anterior. Si alguien altera una transacción ya confirmada, el hash de ese bloque deja de coincidir con el que registró el bloque siguiente y la verificación de la cadena lo delata. La integridad no se impone con permisos, se detecta por aritmética.

## Diagrama de arquitectura

```
                Usuario
                   │
                   ▼
   ┌───────────────────────────────┐
   │           Aplicación          │
   │  ┌────────┐      ┌──────────┐ │
   │  │   UI   │ ───▶ │ Lógica de│ │
   │  │        │      │ negocio  │ │
   │  └────────┘      └──────────┘ │
   └───────────────┬───────────────┘
                    │
                    ▼
   ┌───────────────────────────────┐
   │          Persistencia         │
   │  ┌────────────┐  ┌──────────┐ │
   │  │ Acceso a   │─▶│ Base de  │ │
   │  │ datos      │  │ datos    │ │
   │  └────────────┘  └──────────┘ │
   └───────────────────────────────┘
```

Los diagramas UML del sistema —casos de uso, clases y modelo relacional— se mantienen fuera del repositorio. Su ubicación está registrada en `referencias.md`.

## Alcance: qué se implementa y qué queda teórico

La delimitación es explícita, porque el conjunto de mecanismos que se asocian a blockchain opera en niveles distintos y solo dos de ellos entran en el prototipo.

Características que el proyecto implementa:

- **Encadenamiento criptográfico**: cada bloque almacena el hash del bloque anterior. Una modificación invalida todos los hashes posteriores, lo que permite localizar el punto exacto de la alteración.
- **Evidencia de manipulación**: el sistema no evita que alguien con acceso modifique un registro, pero garantiza que esa modificación sea computacionalmente detectable. Es la característica principal del proyecto.
- **Autenticación de origen mediante firma digital**: cada transacción se firma con la llave privada del emisor y se verifica con su llave pública.
- **Validación automática mediante reglas**: la admisión de una transacción depende de verificar firma, saldo y formato, sin intervención humana.

Características fuera del alcance:

- **Consenso distribuido**: no hay mecanismos de acuerdo entre nodos.
- **Descentralización y tolerancia a fallos**: sin replicación, el prototipo conserva el punto único de fallo que critica.
- **Resistencia a la manipulación**: un actor con control del nodo puede recalcular la totalidad de la cadena y mostrar un historial distinto del real.
- **Inmutabilidad estricta**: es una propiedad que surge de la red, no de un archivo local. El proyecto va hacia inmutabilidad verificable, no garantizada.
- **Prevención de doble gasto bajo concurrencia**: se evita por ordenamiento secuencial local, no por resolución de conflictos en la cadena.
- **Red P2P**: sin propagación de bloques, sin resolución de bifurcaciones y sin finalidad probabilística.
- **Validación legal y valor real**: las transacciones son simuladas.

El glosario de `CONTEXT.md` repite estos mismos límites como términos descartados, para que su aparición en una propuesta sea la señal de que el alcance se está corriendo.

## Ciclo de vida de una transacción

1. **Creación**: una wallet emisora construye una transacción con receptor, monto y firma.
2. **Validación**: se comprueba el formato, que el emisor y el receptor existen, que el monto es positivo, que emisor y receptor difieren, que la firma corresponde al emisor y que el emisor tiene saldo suficiente. Una transacción que falla acá queda rechazada y nunca entra a un bloque.
3. **Pool**: la transacción validada entra al pool de pendientes con estado `pending` y sin bloque asociado.
4. **Agrupación**: las transacciones pendientes se reúnen en un bloque nuevo, que toma el hash del último bloque de la cadena como `previous_hash` y calcula su propio hash. Las transacciones pasan a `confirmed` y quedan ligadas al bloque.
5. **Verificación**: el recorrido de la cadena comprueba que cada `previous_hash` coincide con el hash real del bloque anterior. Cualquier discrepancia marca la cadena como inválida a partir de ese punto.

La regla de saldo que aparece en el paso 2 es la que el esquema de la base no puede garantizar por sí solo. Su razonamiento está en el ADR-0004.

## Modelo de datos

Tres entidades, con las transacciones como entidad central.

| Entidad        | Qué representa                              | Clave de su integridad                                   |
| -------------- | ------------------------------------------- | -------------------------------------------------------- |
| `wallets`      | El par de llaves de cada participante       | La llave privada se guarda cifrada, nunca en texto plano |
| `blocks`       | Una agrupación de transacciones confirmadas | `previous_hash` encadena; `hash` sella el contenido      |
| `transactions` | Una transferencia firmada entre dos wallets | `block_id` y `status` deben ser coherentes entre sí      |

El detalle de columnas, constraints e índices está en `base-de-datos.md`. La estructura del esquema está congelada: cualquier cambio requiere confirmación explícita de los desarrolladores.

## Estructura de módulos prevista

Todavía no existe código de aplicación. Esta es la forma que la implementación debería tomar, sujeta a revisión cuando se diseñe la fase de backend.

```
src/
├── wallet.py         # par de llaves, firma y verificación
├── transaction.py    # la transacción y sus reglas de validación
├── block.py          # estructura del bloque y cálculo del hash
├── blockchain.py     # el componente Blockchain: pool, agrupación y verificación
├── persistence/      # acceso a PostgreSQL
└── main.py           # punto de entrada
```

El criterio de fondo es que la lógica de validación y de encadenamiento no dependa de la base de datos: son reglas del dominio que deben poder probarse sin levantar PostgreSQL. La persistencia queda detrás de una interfaz propia.

## Diseño pendiente

Los siguientes puntos del diseño todavía no están resueltos y no deben darse por cerrados por inferencia. Cualquier propuesta sobre ellos se confirma con los desarrolladores antes de implementarse.

- El tipo de arquitectura y la justificación de su elección.
- El desglose de componentes del sistema y la función de cada uno.
- La comunicación entre componentes.
- La integración de los tres modelos: casos de uso, clases y modelo relacional.
- La forma que tomará la capa de presentación.

## Límites conocidos

Además de lo que queda fuera del alcance, hay dos consecuencias del diseño que conviene tener presentes.

La primera es que el nodo custodia las llaves: como persiste el material cifrado de todas las llaves privadas, la firma ocurre dentro del nodo y no en un cliente que el asociado controle. Un modelo no custodial está fuera del prototipo, y es la limitación más seria frente a un caso de uso real.

La segunda es que el sistema supone que la base de datos no se reescribe por completo. La verificación de la cadena detecta que un bloque fue alterado, pero no detecta que alguien con control del nodo haya recalculado todos los hashes después de modificar el historial. Es la diferencia entre inmutabilidad verificable e inmutabilidad garantizada.
