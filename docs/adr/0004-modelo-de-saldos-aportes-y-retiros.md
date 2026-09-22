# ADR-0004: Modelo de saldos, aportes y retiros

- **Estado**: propuesto
- **Fecha**: 2026-09-21

## Contexto

El diseño del proyecto define la validación automática como la verificación de firma, saldo y formato, y ubica esas reglas en `Transaction.isValid()`. El caso de aplicación es una organización del sector solidario que administra aportes y retiros de sus asociados.

El esquema de la Fase 2 no tiene noción de saldo ni de organización. `wallets` no tiene columna de saldo, `transactions` no distingue un aporte de un retiro, y nada impide que un emisor transfiera más de lo que ha recibido. Los datos de prueba tampoco representan el caso: son transferencias entre personas, no aportes ni retiros.

Hay entonces una brecha entre el diseño documentado y el esquema implementado. Este ADR decide de qué lado se cierra, con una restricción explícita: la estructura del esquema SQL no se modifica. No se agregan ni se alteran tablas, columnas, constraints ni índices.

## Decisión

1. **El esquema SQL queda congelado.** El caso de aplicación se resuelve sin tocar su estructura.
2. **El saldo se deriva, no se almacena.** El saldo de una wallet es la suma de los montos de las transacciones confirmadas que recibió, menos la suma de los que envió. No se agrega una columna de saldo.
3. **La organización se representa con una wallet más, identificada por convención.** El fondo se siembra con un identificador conocido y el código lo referencia. Un aporte es una transacción asociado a fondo; un retiro es una transacción fondo a asociado.
4. **Solo las transacciones confirmadas cuentan para el saldo.** Una pendiente todavía no es historia y una rechazada nunca lo será.
5. **La validación de saldo es una regla de negocio, no un constraint.** Depende de una agregación sobre otras filas, y PostgreSQL no puede expresar eso como restricción de fila. Vivirá en `Transaction.isValid()`, y esa es la razón por la que la base no alcanza como garantía de integridad: el diseño necesita la regla y el esquema.
6. **La validación de saldo obliga a un orden secuencial.** Dos transacciones que por separado caben en el saldo pueden excederlo juntas, así que el nodo debe validarlas en serie. Esa es la razón por la que el doble gasto se evita localmente en lugar de resolverse entre nodos.

## Consecuencias

- El esquema actual admite el caso de aplicación sin ningún cambio estructural.
- El saldo deja de ser un dato y pasa a ser una consulta. Los índices ya existentes sobre `sender_id`, `receiver_id` y `status` son los que la sostienen.
- La integridad del saldo depende de la lógica de negocio y del orden de validación. Una inserción directa en la base que confirme una transacción sin pasar por `Blockchain` puede dejar un saldo negativo que ningún constraint detectará. Es el límite real de esta decisión, y conviene tenerlo presente al escribir pruebas.
- `ON DELETE RESTRICT` en las claves foráneas ya protege el cálculo: no se puede borrar una wallet con historial.
- Identificar el fondo por un identificador fijo deja la distinción en un acuerdo no declarado en los datos: quien consulte la base sin leer el código no puede saber cuál wallet es la organización.
- Los datos de prueba actuales no representan el caso de aplicación. Alinearlos toca `database/`, así que requiere confirmación explícita de los desarrolladores.
- Este ADR contradice en parte la expectativa de que la base garantiza la integridad: la coherencia entre estado y bloque sí la garantiza el esquema, pero el saldo no. La distinción es deliberada.

## Alternativas consideradas

- **Columna `wallets.balance` mantenida por la aplicación**: descartada por dos razones. Exigiría modificar la estructura del esquema, y además crearía un dato que puede divergir del ledger, que es lo que este proyecto existe para evitar.
- **Columna `wallets.kind`** para distinguir asociados de fondos: descartada porque exigiría modificar la estructura del esquema.
- **Columna `transactions.type`** con valores como `aporte`, `retiro` o `transferencia`: descartada por la misma razón, y porque la dirección respecto a la wallet del fondo ya determina el tipo.
- **Tablas separadas para aportes y retiros**: descartada porque duplicaría la lógica de validación, de encadenamiento y de saldo en dos caminos paralelos.
- **Una caja externa sin wallet**: descartada porque un aporte sin wallet emisora no tiene firma, y sin firma se pierde la autenticación de origen.
