# Usuarios, roles y alta moderada — diseño

**Proyecto**: _Diseño de la arquitectura de un sistema transaccional basado en blockchain._
**Alcance de este documento**: la funcionalidad del sistema de usuarios. **El rediseño visual no entra acá**: otra persona del equipo va a rehacer y refinar las interfaces, así que este documento define pantallas, datos y reglas, no estética.

---

## 1. Por qué

El prototipo funciona y está verificado, pero se usa como se usa una consola: cualquiera que abra el navegador puede registrar wallets, proponer transacciones, agrupar bloques y verificar la cadena. El tutor pidió que los proyectos funcionen **casi como productos**, y un producto tiene personas con nombre, con permiso para unas cosas y no otras, y una puerta de entrada.

La pieza que convierte esto en producto es un **sistema de usuarios con dos roles y un alta moderada**: alguien se registra, el administrador lo habilita, y desde ese momento la persona entra y usa el sistema como una wallet. De paso, el ingreso por usuario es lo que permite que las interfaces se rehagan por rol, que es lo que necesita la otra persona del equipo para rediseñarlas.

## 2. Lo que ya existe, y no se toca

- Cinco rutas con su contrato: `GET /`, `POST /wallets`, `POST /transacciones`, `POST /bloques`, `GET /verificar`, `GET /historial/<wallet>`.
- Tres capas: presentación (Flask, sin reglas ni SQL), dominio (cinco clases, sin el driver) y persistencia (PostgreSQL detrás de interfaces propias).
- Las llaves privadas se generan en el servidor, se cifran con la `MASTER_KEY` del entorno y viven en `wallets.private_key_encrypted`.
- 130 pruebas en verde, y los 29 requerimientos del documento maestro con su prueba.

**Nada de esto cambia de comportamiento.** Las rutas que existen pasan a exigir sesión de administrador; su lógica no se toca.

## 3. Decisiones que tomó la persona a cargo

1. **Dos roles**: _usuario común_, que usa el sistema como una wallet, y _administrador_, que conserva el control que hoy tiene el sistema entero.
2. **Alta abierta pero moderada**: la persona se registra sola y queda **pendiente**; el administrador la valida y le habilita el ingreso.
3. **Custodia de llaves: la actual**, del lado del servidor. Se considera y se descarta, para esta entrega, que la persona guarde su llave privada.
4. **El destinatario de un envío se identifica por nombre de usuario**, que es único, y opcionalmente por el identificador de la wallet.
5. **La funcionalidad es de quien escribe esto; la estética es de otra persona del equipo.**

## 4. Decisiones que tomé yo, y que se pueden tumbar

1. **Ingreso con usuario y contraseña, sin correo electrónico.** No hay infraestructura de correo y agregarla sería un trámite que nadie usaría. Si algún día hace falta recuperar contraseñas, eso obliga a un correo o a una pregunta de seguridad, y las dos cosas están fuera de alcance.
2. **Una wallet por usuario**, creada en el momento de la aprobación. Un usuario con varias wallets es un producto distinto.
3. **Saldo de bienvenida al aprobar: 1000**, acreditado desde la wallet del **constituyente** —la única que el diseño admite en negativo— en la misma operación atómica que crea la wallet y cambia el estado. Sin saldo, la persona entra y no puede hacer nada, que es peor que no entrar.
   Como el saldo disponible sólo cuenta transacciones **confirmadas**, el crédito no puede ser una fila suelta: la aprobación crea un **bloque nuevo con esa única transacción**, firmada por el constituyente, y no arrastra lo que haya en el pool. Consecuencia: **cada aprobación agrega un bloque a la cadena**. El costo es despreciable: la verificación es lineal en bloques y se midió en 1,4 ms con 4 bloques y unos 84 ms con 1.000, así que harían falta miles de aprobaciones para notarlo.
4. **El administrador es una cuenta sembrada** por el arranque, con su contraseña en el entorno. No hay auto-registro de administradores: si lo hubiera, el control del sistema dejaría de tener sentido.
5. **Las rutas de hoy quedan del lado del administrador.** El usuario común ve su saldo, su historial, el formulario de envío y el estado de sus envíos; nada más.
6. **Sesión con la cookie firmada de Flask** y el usuario recargado desde la base en cada petición, para que un cambio de estado se note sin reiniciar nada.
7. **Las contraseñas se guardan con `hashlib.scrypt` de la biblioteca estándar**, con sal por usuario. Nada de dependencias nuevas.
8. **El arranque siembra al administrador y cinco usuarios de demostración** ligados a las cinco wallets que ya siembra, aprobados, con una contraseña de demostración documentada. Es la diferencia entre un producto que se puede mostrar y un producto vacío.
9. **La conservación de la cadena no cambia**: el usuario común no puede ver la cadena entera, y su verificación es sobre su propio historial.

## 5. Requerimientos nuevos

Se numeran a continuación de los 29 del documento maestro y siguen la misma forma: criterio de aceptación verificable, y una prueba por requerimiento.

- **REQ-30 — Registro.** Una persona se registra con usuario y contraseña, y queda en estado `pendiente`, sin wallet y sin poder ingresar. _Criterio_: el registro responde 200 con el estado «pendiente»; la fila existe con `estado = 'pendiente'`; un usuario repetido se rechaza con motivo. El campo de usuario, en el registro y en el ingreso, sólo admite minúsculas, dígitos, punto, guion y guion bajo, entre 3 y 20 caracteres.
- **REQ-31 — Aprobación.** El administrador ve la lista de pendientes y aprueba o rechaza. El rechazo es final: ese usuario no puede volver a registrarse con el mismo nombre. _Criterio_: al aprobar, el estado pasa a `aprobado`; al rechazar, a `rechazado` con motivo; un rechazado que intenta ingresar recibe el motivo y no entra.
- **REQ-32 — Ingreso.** Sólo ingresa quien está aprobado. El pendiente y el rechazado reciben un mensaje que dice su estado, no un error genérico. _Criterio_: con `estado = 'pendiente'` el ingreso no abre sesión y muestra «esperando aprobación»; con `aprobado` abre sesión; con contraseña equivocada no dice si el usuario existe.
- **REQ-33 — Wallet y saldo al aprobar.** Al aprobar se crea la wallet del usuario y se le acredita el saldo de bienvenida desde el constituyente, **en una sola operación**: si falla cualquiera de las dos, no queda ninguna escrita. _Criterio_: tras la aprobación existe exactamente una wallet ligada al usuario, con 1000 disponibles; el constituyente bajó 1000; y la cadena ganó un bloque con esa única transacción.
- **REQ-34 — El emisor lo pone la sesión.** En el envío del usuario común, el emisor sale de la sesión y **nunca** del formulario: si el formulario trae un emisor, se ignora. _Criterio_: un envío con un emisor ajeno en el formulario se registra con la wallet de la sesión, o se rechaza; nunca con la ajena.
- **REQ-35 — Alcance de la vista.** El usuario común ve sólo su saldo, su historial y la verificación de su historial. El administrador ve todo. _Criterio_: el usuario común que pide el historial de otra wallet recibe 403 o 404, nunca el contenido; el administrador sí lo recibe.
- **REQ-36 — Contraseñas.** Se guardan con `hashlib.scrypt` y sal por usuario, nunca en claro, y la comparación no filtra por tiempo. _Criterio_: en la base no aparece la contraseña; dos usuarios con la misma contraseña tienen hashes distintos; la comparación usa `hmac.compare_digest`.
- **REQ-37 — Sesión.** El ingreso abre una sesión y la salida la cierra. Sin sesión, ninguna ruta de trabajo responde con datos. _Criterio_: sin sesión, las rutas de trabajo redirigen al ingreso; después de la salida, el mismo navegador ya no entra.
- **REQ-38 — Autorización por rol.** Cada ruta declara el rol que exige, y el administrador no puede ser reemplazado por un usuario común. _Criterio_: un usuario común que intenta agrupar un bloque o aprobar a otro usuario recibe 403; la matriz de permisos del punto 8 se cumple ruta por ruta.
- **REQ-39 — Verificación del historial propio.** La página del usuario común corre la verificación de la cadena y muestra su dictamen junto con las transacciones confirmadas de **su** wallet, sin mostrar las de otros. _Criterio_: con la cadena alterada, su página dice que no puede verificar; con la cadena válida, dice que su historial está respaldado y lista sólo sus transacciones.

## 6. Modelo de datos

Una tabla nueva, `users`, y ninguna columna nueva en `wallets`: la relación va de `users` hacia `wallets`.

```
users
  id                 UUID PRIMARY KEY (uuid_generate_v4())
  username           TEXT NOT NULL UNIQUE
  password_hash      TEXT NOT NULL
  role               TEXT NOT NULL CHECK (role IN ('administrador', 'usuario'))
  estado             TEXT NOT NULL CHECK (estado IN ('pendiente', 'aprobado', 'rechazado'))
  motivo_rechazo     TEXT NULL
  wallet_id          UUID NULL UNIQUE REFERENCES wallets(id) ON DELETE RESTRICT
  creado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
  aprobado_en        TIMESTAMPTZ NULL
```

- `wallet_id` es nulo mientras el usuario no esté aprobado, y único: una wallet no puede pertenecer a dos usuarios.
- La `UNIQUE` de `wallet_id` admite varios nulos en PostgreSQL, que es justo lo que hace falta.
- `password_hash` guarda un texto autodescriptivo: `scrypt$n$r$p$sal_b64$hash_b64`. Así se puede cambiar el costo sin invalidar las contraseñas viejas.
- El administrador sembrado también es una fila de esta tabla, con `role = 'administrador'` y sin wallet.
- **La tabla entra en el conjunto esperado del esquema**: la prueba que hoy exige tres tablas públicas suma `users`, y la limpieza de las pruebas borra usuarios antes que wallets. Son adaptaciones mecánicas, declaradas: ninguna aserción de comportamiento se afloja.

**El esquema se aplica creando el volumen.** El proyecto no tiene herramienta de migraciones: después de este cambio, un volumen que ya exista no tendrá la tabla, y el arranque fallará con un mensaje claro. La salida documentada es recrear el volumen y volver a sembrar. El mensaje de error del arranque tiene que decir exactamente eso.

## 7. Flujos

**Registro.** Formulario (usuario, contraseña, repetir contraseña) → validaciones (usuario único; **sólo minúsculas, dígitos, punto, guion y guion bajo, entre 3 y 20 caracteres**, con el campo restringido desde la propia interfaz y una ayuda visible; contraseña con un largo mínimo; las dos iguales) → se crea la fila `pendiente` → pantalla «tu cuenta está esperando aprobación», con el usuario para que sepa qué ingresar cuando lo aprueben.

**Aprobación.** El administrador ve la lista de pendientes con el usuario y la fecha de registro, y dos acciones: aprobar o rechazar (con motivo). Aprobar crea la wallet, acredita el saldo en un bloque nuevo y cambia el estado, todo en una sola operación. Rechazar guarda el motivo. Las dos acciones son irreversibles desde la interfaz: no hay «volver a aprobar» ni «des-rechazar».

**Ingreso.** Usuario y contraseña → si no está aprobado, se le dice su estado; si está aprobado, se abre la sesión y va a su tablero; si las credenciales no sirven, un solo mensaje, sin decir cuál de las dos falló.

**Tablero del usuario común.** Su nombre, su wallet (identificador corto con botón de copiar), su saldo, sus transacciones con estado y motivo de rechazo, y el formulario de envío: **destinatario por nombre de usuario, o por el identificador de la wallet si lo tiene a mano**, y monto. El emisor no aparece en el formulario. Debajo, la verificación de su historial y un enlace a la salida.

**Tablero del administrador.** Los pendientes por aprobar; las wallets con sus saldos; las acciones de hoy (registrar wallet, agrupar bloque, verificar la cadena) y el historial de cualquier wallet.

## 8. Matriz de permisos

| Ruta o acción                                     | Usuario común            | Administrador        |
| ------------------------------------------------- | ------------------------ | -------------------- |
| Ver su saldo, sus transacciones y su verificación | sí                       | sí                   |
| Ver el saldo o el historial de otros              | **no**                   | sí                   |
| Proponer un envío                                 | sí, sólo desde su wallet | sí, desde cualquiera |
| Agrupar las pendientes en un bloque               | **no**                   | sí                   |
| Verificar la cadena completa                      | **no**                   | sí                   |
| Registrar wallets                                 | **no**                   | sí                   |
| Aprobar o rechazar usuarios                       | **no**                   | sí                   |
| Cambiar llaves                                    | no existe                | no existe            |

## 9. Seguridad, y dónde vive cada regla

Esto es lo más delicado del diseño, porque el proyecto tiene una prueba que exige que la presentación no ejecute reglas de negocio ni SQL (REQ-29). Hay que distinguir dos cosas:

- **Decidir quién puede llamar** es autorización, y vive en la presentación: un decorador por ruta declara el rol, y el formulario no elige el emisor.
- **Decidir si la operación es válida** sigue viviendo en el dominio, sin cambios: saldo, firma, formato, encadenamiento.

La autorización no es una regla de negocio: es la puerta. El dominio no sabe que existen usuarios, y no debe saberlo. Las pruebas de REQ-29 siguen valiendo porque la presentación no gana ninguna consulta ni ninguna regla de saldo.

La única regla nueva del dominio es la del punto 4.3: acreditar el saldo inicial en un bloque nuevo, firmado por el constituyente y sin arrastrar el pool. Es una operación de emisión, del mismo tipo que el arranque ya usa para sembrar el capital, y el dominio la expone como operación propia para que la aprobación no tenga que escribir transacciones por fuera.

Puntos concretos:

- **Contraseñas**: `hashlib.scrypt` con sal de 16 bytes y costo documentado; comparación con `hmac.compare_digest`.
- **Sesión**: cookie firmada por Flask, `HttpOnly` y `SameSite=Lax`; la clave de firma es una variable nueva del entorno, `SESSION_SECRET`, con su generador en el `.env.example`. La cookie no es permanente: muere al cerrar el navegador.
- **Usuario recargado por petición**: la sesión guarda el identificador; el rol y el estado se leen de la base en cada petición, así una aprobación o un rechazo se notan sin reiniciar.
- **Mensajes de error**: el ingreso fallido no distingue usuario inexistente de contraseña equivocada.

## 10. Lo que no entra en esta entrega

Cambio de contraseña; suspender o dar de baja un usuario; bitácora de lo que hace el administrador; correo, recuperación de contraseña y verificación de correo; 2FA; que la persona custodie su llave; usuarios con varias wallets; protección CSRF; límite de intentos de ingreso; internacionalización.

Los dos que más se van a notar son CSRF y el límite de intentos: son cosas que un producto real necesita y que este prototipo académico no tiene. Van declaradas, igual que la truncación de la cola.

## 11. Anti-metas

Aunque todo funcione, esto sería un fracaso si: alguna contraseña queda en claro; el usuario común puede agrupar bloques o ver datos de otros; se rompe alguna de las 130 pruebas que ya pasan; la presentación gana SQL o reglas de saldo; el arranque requiere cirugía manual de la base sin que el mensaje lo diga; o la sesión sobrevive a la salida.

## 12. El límite que se declara

Las llaves privadas siguen en el servidor, cifradas con la `MASTER_KEY`. Consecuencia: **el administrador puede firmar en nombre de cualquier usuario**. La integridad del registro no depende de eso —una transacción confirmada que se altere se detecta, firme quien firme—, pero la _autoría_ sí. Se declara en el README y en la sustentación, junto a los otros límites.

## 13. Cómo se verifica

- Una prueba por requerimiento nuevo, con el nombre `test_req_NN_*` y el criterio de aceptación en el docstring, en la carpeta que corresponda: unitarias para las reglas de contraseña y de forma, de integración para los flujos con base.
- Las 130 pruebas existentes siguen pasando. Se admiten dos adaptaciones mecánicas, declaradas acá: la prueba del esquema suma `users` a las tablas esperadas, y la limpieza de las pruebas borra usuarios antes que wallets. Las de rutas se adaptan para ingresar con una sesión de administrador. **Ninguna aserción de comportamiento se afloja**: si una prueba deja de afirmar lo que afirmaba, es un error, no una adaptación.
- La herramienta de sabotaje no se toca: opera sobre wallets y transacciones, no sobre usuarios.
- Un recorrido de demostración: el administrador aprueba a una persona, esa persona ingresa, ve su saldo de bienvenida, manda un envío a otra wallet, lo ve confirmado en su historial, y verifica su historial.

## 14. Lo que queda a criterio de quien construya

- La estructura visual y el estilo de las pantallas: los define la otra persona del equipo; acá sólo están el contenido y las acciones.
- Los textos exactos, dentro del registro llano del proyecto.
- Los parámetros de costo de `scrypt`, dentro de un rango razonable, y el largo mínimo de contraseña.
- La duración de la sesión y los detalles de la cookie, dentro de lo dicho en el punto 9.
- Cómo se lee la contraseña del administrador del entorno y qué pasa si falta.
