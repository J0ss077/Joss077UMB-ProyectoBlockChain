# CONTEXT.md

Glosario del dominio del sistema transaccional basado en blockchain. Es la fuente de verdad del vocabulario: los issues, los ADR, los tests y el resto de la documentación usan estos términos, no sus sinónimos descartados.

## Caso de aplicación

El sistema no es genérico: aplica a una organización del sector solidario que administra recursos aportados periódicamente por sus asociados. Esa es la razón de ser de la verificación de integridad, porque el riesgo no es un atacante externo sino la falta de un mecanismo independiente para comprobar el historial.

| Término      | Definición                                                                                                                                                                       | Sinónimos descartados              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Organización | Entidad del sector solidario que administra recursos aportados por sus asociados: fondos de empleados, asociaciones mutuales y similares. Es el caso de aplicación del proyecto. | empresa, cooperativa, entidad      |
| Asociado     | Persona que aporta periódicamente a la organización y es titular de una wallet.                                                                                                  | usuario, afiliado, cliente, socio  |
| Tesorero     | Figura que hoy concentra el registro y el manejo de los aportes. El sistema no elimina su rol: elimina la necesidad de confiar en su palabra.                                    | administrador, contador, encargado |
| Aporte       | Entrada de recursos de un asociado hacia la organización.                                                                                                                        | consignación, depósito, cuota      |
| Retiro       | Salida de recursos de la organización hacia un asociado.                                                                                                                         | pago, desembolso, devolución       |
| Saldo        | Recursos que la organización reconoce a un asociado. Se deriva de las transacciones confirmadas, no de un campo almacenado. Ver ADR-0004.                                        | balance, cupo, disponible          |

## El sistema

| Término    | Definición                                                                                                                                                     | Sinónimos descartados                                        |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Ledger     | Registro completo de wallets, transacciones y bloques que mantiene el nodo. Es el estado del sistema.                                                          | libro mayor; base de datos (esa es el soporte, no el ledger) |
| Nodo       | Instancia única que mantiene su propio ledger y valida sus propias transacciones. En este proyecto hay exactamente uno, ejecutándose local.                    | peer, servidor, réplica                                      |
| Cadena     | La estructura de datos: secuencia de bloques en la que cada uno guarda el hash del anterior.                                                                   | blockchain (ese nombre está tomado por el componente)        |
| Blockchain | El componente que coordina el ledger: pool de pendientes, agrupación en bloques, verificación de integridad y consulta de historial. Es el nombre de la clase. | ledger manager, coordinador, cadena                          |
| Integridad | Propiedad de que ninguna transacción ya confirmada fue alterada sin que la verificación de la cadena lo detecte.                                               | consistencia                                                 |

## Participantes y llaves

| Término       | Definición                                                                                           | Sinónimos descartados      |
| ------------- | ---------------------------------------------------------------------------------------------------- | -------------------------- |
| Wallet        | Identidad participante, definida por un par de llaves y reconocida por su llave pública.             | billetera, cuenta, usuario |
| Llave pública | Identificador público de una wallet. Es lo que se escribe como emisor o receptor de una transacción. | dirección, address         |
| Llave privada | Material que firma transacciones. Se persiste cifrado y nunca en texto plano.                        | clave privada, secreto     |
| Firma         | Prueba criptográfica de que el emisor autorizó la transacción. Se valida antes de aceptarla.         | firma digital              |

## Transacciones

| Término            | Definición                                                                                                                                                                   | Sinónimos descartados               |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| Transacción        | Transferencia de un monto desde una wallet emisora a una wallet receptora, firmada por el emisor.                                                                            | operación, movimiento, pago         |
| Emisor             | Wallet que origina la transacción y la firma.                                                                                                                                | origen, remitente, sender           |
| Receptor           | Wallet que recibe el monto.                                                                                                                                                  | destino, receiver                   |
| Monto              | Cantidad transferida. Es positiva y admite ocho decimales.                                                                                                                   | importe, valor, cantidad            |
| Estado             | Posición de la transacción en su ciclo de vida: `pending`, `confirmed` o `rejected`.                                                                                         | status (es el nombre de la columna) |
| Pendiente          | Transacción validada que está en el pool sin bloque asignado: `status = 'pending'` y `block_id` nulo.                                                                        | en cola, sin confirmar              |
| Confirmada         | Transacción agrupada en un bloque: `status = 'confirmed'` y `block_id` no nulo.                                                                                              | minada, liquidada                   |
| Rechazada          | Transacción que no superó la validación. Nunca entra a un bloque.                                                                                                            | inválida, fallida                   |
| Pool de pendientes | Conjunto de transacciones pendientes a la espera de ser agrupadas.                                                                                                           | mempool, cola                       |
| Doble gasto        | Intento de disponer dos veces del mismo saldo. El prototipo lo evita ordenando las transacciones de forma secuencial en un solo nodo, no resolviendo conflictos entre nodos. | sobregiro                           |

## Bloques

| Término                   | Definición                                                                                                                                | Sinónimos descartados                                             |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Bloque                    | Agrupación de transacciones confirmadas, con índice, timestamp, hash previo y hash propio.                                                | página, lote                                                      |
| Bloque génesis            | Bloque de índice cero, cuyo hash previo son sesenta y cuatro ceros.                                                                       | bloque inicial                                                    |
| Índice de bloque          | Posición del bloque en la cadena. Es entero, no negativo y único.                                                                         | altura, número de bloque                                          |
| Hash previo               | Hash del bloque anterior, que encadena la estructura.                                                                                     | parent hash                                                       |
| Hash propio               | SHA-256 del contenido del bloque, en hexadecimal minúscula de sesenta y cuatro caracteres.                                                | digest, checksum                                                  |
| Agrupar                   | Reunir transacciones pendientes en un bloque nuevo.                                                                                       | minar (descartado: este nodo no compite por resolver un acertijo) |
| Verificación de la cadena | Recorrido que comprueba que cada hash previo coincide con el hash real del bloque anterior y que los hashes respetan el formato esperado. | auditoría, validación de integridad                               |

## Propiedades que el sistema sí garantiza

Estas son las propiedades que el proyecto demuestra. La distinción importa: son de detección, no de prevención.

| Propiedad                    | Qué significa                                                                                                                            |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Encadenamiento criptográfico | Una modificación en un bloque invalida todos los hashes posteriores, lo que además localiza el punto exacto de la alteración.            |
| Evidencia de manipulación    | El sistema no impide que alguien con acceso modifique un registro, pero garantiza que la modificación sea computacionalmente detectable. |
| Autenticación de origen      | Cada transacción se firma con la llave privada del emisor y se verifica con su llave pública.                                            |
| Validación automática        | La admisión de una transacción depende de verificar firma, saldo y formato, sin intervención humana.                                     |
| Inmutabilidad verificable    | El historial no se puede alterar sin dejar rastro comprobable. No es inmutabilidad garantizada: ver la sección siguiente.                |

## Fuera de alcance

Términos que la documentación menciona solo para descartarlos. Que aparezcan en una propuesta es señal de que el alcance se está corriendo.

| Término                                     | Por qué está fuera                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Consenso distribuido                        | El nodo es único: no hay pares con los que acordar un orden. Ver ADR-0001.                                                                                                      |
| Red P2P                                     | No hay descubrimiento de pares, propagación de bloques, resolución de bifurcaciones ni finalidad probabilística. Ver ADR-0001.                                                  |
| Minería y proof of work                     | No hay competencia por el derecho a producir el bloque siguiente. Por eso el verbo del proyecto es agrupar.                                                                     |
| Descentralización y tolerancia a fallos     | Sin replicación, el prototipo conserva el punto único de fallo que critica.                                                                                                     |
| Resistencia a la manipulación               | Quien controla el nodo puede recalcular la cadena completa y presentar un historial distinto del real. El sistema detecta alteraciones parciales, no una reescritura total.     |
| Inmutabilidad garantizada                   | Surge de la red distribuida, no de un archivo local. El proyecto va hacia inmutabilidad verificable, no garantizada.                                                            |
| Prevención de doble gasto bajo concurrencia | Se evita por ordenamiento secuencial local, no por resolución de conflictos en la cadena.                                                                                       |
| Wallet no custodial                         | El nodo guarda el material cifrado de todas las llaves privadas, así que la firma ocurre dentro del nodo. Que cada asociado custodie su propia llave queda fuera del prototipo. |
| Token o criptomoneda                        | El monto es una cantidad simulada, sin valor ni emisión.                                                                                                                        |
| Validación legal                            | Las transacciones son simuladas y no representan obligaciones reales.                                                                                                           |
