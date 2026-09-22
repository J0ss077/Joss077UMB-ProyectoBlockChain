# Arquitectura

Diseño del prototipo de sistema transaccional basado en blockchain. El vocabulario de este documento es el de `CONTEXT.md`; las decisiones cerradas están en `docs/adr/`.

## Caso de aplicación

El sistema se plantea para una organización del sector solidario, como un fondo de empleados o una asociación mutual, que administra recursos aportados periódicamente por sus asociados. En organizaciones pequeñas o medianas ese registro suele recaer en una sola figura, el tesorero, sobre hojas de cálculo o un aplicativo cerrado al que los asociados no acceden.

El problema no es que el tesorero sea deshonesto, sino que hoy no existe un mecanismo independiente para comprobar el historial. Si alguien altera un aporte, no hay forma de detectarlo desde afuera. El sistema no reemplaza al tesorero: hace que su palabra deje de ser la única garantía.

Por eso el criterio de éxito del prototipo no es impedir la alteración, sino volverla detectable.

## Propósito

Un sistema transaccional tradicional confía la validación de cada operación a una entidad central, lo que crea un punto único de fallo. Este proyecto propone una arquitectura alternativa: wallets con par de llaves, transacciones firmadas, validación automática y bloques enlazados por hash.

La diferencia con un sistema central no está en quién guarda los datos, sino en cómo se detecta la manipulación. Cada bloque guarda el hash del bloque anterior. Si se altera una transacción ya confirmada, el hash de ese bloque deja de coincidir con el que registró el bloque siguiente, y la verificación de la cadena lo detecta. La integridad no se impone con permisos, se detecta por aritmética.

## Tipo de arquitectura

Se adoptó una arquitectura en capas, con el núcleo de dominio separado de la persistencia. El razonamiento completo está en el ADR-0005.

- **Presentación**: expone los casos de uso al usuario. Su forma todavía no está definida.
- **Dominio**: las cinco clases del sistema y las reglas de firma, saldo, formato y encadenamiento. No importa nada de PostgreSQL.
- **Persistencia**: la única capa que conoce el motor, detrás de una interfaz propia que el dominio consume.

La separación admite dos lecturas. La primera corresponde a los niveles de blockchain que distingue la sección de alcance. La segunda corresponde al software que implementa esos niveles.

| Nivel de blockchain                                     | Capa de software | Estado        |
| ------------------------------------------------------- | ---------------- | ------------- |
| Capa criptográfica (hash encadenado y firmas digitales) | Dominio          | Se implementa |
| Capa de reglas de validación (firma, saldo y formato)   | Dominio          | Se implementa |
| Capa de red (propagación, consenso y bifurcaciones)     | No aplica        | Queda teórica |

Las dos primeras capas están dentro del núcleo de dominio porque comparten los mismos datos. La capa de red no se implementa, y eso define el alcance de un solo nodo.

La comunicación entre capas es una llamada dentro del mismo proceso, porque el sistema es un nodo único y no hay red que diseñar. El único límite real es el de persistencia.

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

El usuario interactúa con la capa de presentación, que llama a la lógica de negocio. La lógica de negocio aplica las reglas y decide si la operación se admite. Cuando necesita leer o escribir, pasa a la capa de acceso a datos, que consulta PostgreSQL.

La lógica de negocio no depende del motor que está del otro lado del límite. Esa separación es la que permite probar las reglas de integridad sin usar la base de datos.

Los diagramas UML del sistema, es decir los de casos de uso, clases y modelo relacional, se mantienen fuera del repositorio. Su ubicación está registrada en `referencias.md`.

## Alcance: qué se implementa y qué queda teórico

La delimitación es explícita, porque los mecanismos que se asocian a blockchain operan en niveles distintos y solo dos de ellos entran en el prototipo.

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

## Principales componentes

El sistema tiene tres componentes de dominio y dos de soporte. Los tres primeros cumplen funciones que en un sistema centralizado ejerce la autoridad central.

| Componente                          | Clases                             | Responsabilidad                                                  | Función central que reemplaza         |
| ----------------------------------- | ---------------------------------- | ---------------------------------------------------------------- | ------------------------------------- |
| Cadena de bloques enlazada por hash | `Block`, `Blockchain`              | Encadenar los bloques por hash y sellar el contenido de cada uno | Garantizar la integridad de los datos |
| Wallets identificadas por llaves    | `Wallet`                           | Identificar a cada participante y firmar sus operaciones         | Verificar la identidad del emisor     |
| Validación automática               | `Transaction`, `TransactionStatus` | Aceptar o rechazar cada transacción antes de que entre al bloque | Autorizar cada operación              |
| Persistencia                        | Adaptador PostgreSQL               | Guardar y leer wallets, transacciones y bloques                  | No aplica                             |
| Presentación                        | Por definir                        | Dar al usuario acceso a los casos de uso                         | No aplica                             |

## Función de cada componente

**Cadena de bloques enlazada por hash.** Cada bloque guarda el hash del bloque anterior, el suyo propio y el índice que lo ubica en la cadena. Si se modifica un bloque, todos los hashes posteriores dejan de coincidir: eso detecta la alteración y permite ubicarla. La clase `Block` representa el bloque y calcula su hash con SHA-256. La clase `Blockchain` mantiene el pool de transacciones pendientes, agrupa las transacciones en bloques, verifica la integridad de la cadena y responde las consultas de historial.

**Wallets identificadas por llaves.** Cada participante tiene un par de llaves. La llave pública lo identifica y es la que se escribe como emisor o receptor de una transacción. La llave privada firma las operaciones y no se guarda en texto plano. La clase `Wallet` encapsula el par de llaves y la operación de firma. Con esto, la autenticidad de una operación no depende de que alguien la autorice, sino de que la firma corresponda a la llave pública del emisor.

**Validación automática.** Decide si una transacción se admite, siempre antes de entrar al bloque. Verifica tres cosas: que la firma corresponda al emisor, que el emisor tenga saldo suficiente y que el formato sea válido. La clase `Transaction` representa la transferencia firmada, con su monto, su estado y su firma, y su método `isValid()` aplica esas reglas. La clase `TransactionStatus` define los tres estados: `pending` mientras la transacción espera en el pool, `confirmed` cuando ya está agrupada en un bloque y `rejected` cuando no pasó la validación. Una transacción rechazada no entra a ningún bloque, y una confirmada no vuelve atrás.

**Persistencia.** Guarda el ledger en PostgreSQL detrás de una interfaz propia, para que la lógica de negocio no dependa del motor ni del esquema. Esta separación permite comprobar la detección de alteración: la prueba modifica un registro confirmado y después le pide a `Blockchain` que verifique la cadena. Si las reglas estuvieran mezcladas con el acceso a datos, esa prueba no se podría escribir sin depender del motor.

**Presentación.** Expone los casos de uso al usuario: registrar wallets, crear transacciones, agrupar bloques, verificar la integridad de la cadena y consultar el historial. Su forma todavía no está definida y no afecta al núcleo de dominio.

Las relaciones entre las clases del dominio son tres. Una wallet emite y otra recibe muchas transacciones. Un bloque agrupa cero o más transacciones confirmadas. La clase `Blockchain` compone la cadena de bloques y mantiene el pool de pendientes.

## Comunicación entre componentes

La comunicación ocurre dentro de un solo proceso, mediante llamadas en memoria. No hay mensajes entre nodos ni protocolo de red. Los recorridos relevantes son tres.

**Creación y admisión de una transacción.** La capa de presentación invoca el caso de uso. La lógica de negocio construye la transacción con emisor, receptor, monto y firma, y llama a `isValid()`. Si la validación pasa, la transacción se guarda con estado `pending` y sin bloque asociado, y queda en el pool. Si no pasa, se guarda con estado `rejected`.

**Agrupación de un bloque.** La lógica de negocio lee las transacciones pendientes y arma un bloque nuevo. El bloque toma como hash previo el del último bloque de la cadena y calcula el suyo. Después se guarda el bloque y se actualizan las transacciones del pool, que pasan a estado `confirmed` y quedan ligadas al bloque. Las dos escrituras se confirman juntas, porque el esquema exige que el estado y el bloque sean coherentes entre sí.

**Verificación de la integridad.** La lógica de negocio recorre la cadena y compara el hash previo de cada bloque con el hash real del bloque anterior. La verificación solo lee: no modifica nada.

En los tres recorridos, el acceso a PostgreSQL pasa siempre por el mismo límite. Ningún componente del dominio ejecuta SQL, y ningún componente de persistencia decide reglas de negocio.

## Por qué esta arquitectura

La primera razón es que lo que se quiere demostrar son las reglas de integridad, no la infraestructura que las rodea. El dominio tiene pocas clases y una sola dependencia externa, así que separarlo mantiene esas reglas fáciles de entender y de probar.

La segunda razón es que la propiedad central del proyecto solo se puede comprobar si el dominio está separado de la base. La afirmación es que toda modificación del historial se detecta, y para comprobarlo hay que alterar un registro confirmado por fuera de la aplicación y pedirle al sistema que verifique la cadena.

La tercera razón es el alcance. Al ser un nodo único sin concurrencia distribuida, el sistema no tiene los problemas que justifican arquitecturas más complejas: no hay servicios que escalar por separado, ni procesos que tolerar fallos, ni eventos que propagar entre nodos.

El contraste con las alternativas descartadas está en el ADR-0005. En resumen, un modelo activo ataría el dominio al esquema relacional, los microservicios agregarían infraestructura para problemas que el sistema no tiene, un script único mezclaría el SQL con las reglas y una arquitectura hexagonal completa sería innecesaria, porque solo hay un límite externo real.

## Ciclo de vida de una transacción

1. **Creación**: una wallet emisora construye una transacción con receptor, monto y firma.
2. **Validación**: se comprueba el formato, que el emisor y el receptor existen, que el monto es positivo, que emisor y receptor difieren, que la firma corresponde al emisor y que el emisor tiene saldo suficiente. Una transacción que falla acá queda rechazada y nunca entra a un bloque.
3. **Pool**: la transacción validada entra al pool de pendientes con estado `pending` y sin bloque asociado.
4. **Agrupación**: las transacciones pendientes se reúnen en un bloque nuevo, que toma el hash del último bloque de la cadena como `previous_hash` y calcula su propio hash. Las transacciones pasan a `confirmed` y quedan ligadas al bloque.
5. **Verificación**: el recorrido de la cadena comprueba que cada `previous_hash` coincide con el hash real del bloque anterior. Cualquier discrepancia marca la cadena como inválida a partir de ese punto.

La regla de saldo del paso 2 es la que el esquema de la base no puede garantizar por sí solo. Su razonamiento está en el ADR-0004.

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
├── persistence/      # acceso a PostgreSQL, detrás de una interfaz propia
└── main.py           # punto de entrada
```

El criterio de fondo es que la lógica de validación y de encadenamiento no dependa de la base de datos: son reglas del dominio que deben poder probarse sin levantar PostgreSQL.

## Diseño pendiente

Los siguientes puntos todavía no están resueltos y no deben darse por cerrados por inferencia. Cualquier propuesta sobre ellos se confirma con los desarrolladores antes de implementarse.

- La integración de los tres modelos: casos de uso, clases y modelo relacional.
- La forma que tomará la capa de presentación.

## Límites conocidos

Además de lo que queda fuera del alcance, hay dos consecuencias del diseño que conviene tener presentes.

La primera es que el nodo custodia las llaves. Como persiste el material cifrado de todas las llaves privadas, la firma ocurre dentro del nodo y no en un cliente que el asociado controle. Un modelo no custodial está fuera del prototipo, y es la limitación más seria frente a un caso de uso real.

La segunda es que el sistema supone que la base de datos no se reescribe por completo. La verificación de la cadena detecta que un bloque fue alterado, pero no detecta que alguien con control del nodo haya recalculado todos los hashes después de modificar el historial. Es la diferencia entre inmutabilidad verificable e inmutabilidad garantizada.
