# Arquitectura y decisiones de diseño

Este documento es el mapa de conjunto: qué piezas tiene el prototipo y qué decisiones las
sostienen. Los requerimientos y su criterio de aceptación viven en
`docs/superpowers/specs/`, que siguen siendo la referencia de cada función. Acá quedan
las decisiones que el eje académico no fija y que el código
necesita justificar: qué se firma, con qué curva, qué cubre el hash de un bloque, por qué
hay una tabla de usuarios y dónde vive cada regla. El detalle de cada caso de uso está en
[recorrido-de-casos-de-uso.md](recorrido-de-casos-de-uso.md) y el de la interfaz en
[sistema-de-diseno.md](sistema-de-diseno.md).

## 1. Qué es el sistema y qué no

Es un **nodo único** de un ledger transaccional: wallets con par de llaves ECDSA,
transacciones firmadas que se validan antes de entrar al pool, agrupación en bloques
encadenados por hash SHA-256 y una verificación de integridad que localiza la primera
alteración. Lo que el proyecto se propone demostrar es que **cualquier modificación del
historial es detectable**, no que haya una red.

No es una blockchain distribuida: no hay nodos pares, ni consenso, ni minado, ni
recompensa. Tampoco es un producto: no hay despliegue, alta de administradores,
recuperación de contraseñas ni bitácora de las acciones del administrador.

Es, en cambio, un **prototipo local y reproducible**: no hay una URL pública ni una
máquina publicada, y lo que se entrega como acceso es el repositorio con los comandos
del `README.md` y los datos que siembra el arranque. El detalle de ese acceso y de las
condiciones de la entrega vive en `docs/entrega-final.md`. La seguridad también es
alcance declarado: el pentest se ejecutó sobre una instancia local desechable, su
informe está en `docs/pentesting/informe.md` y los hallazgos quedan abiertos con
remediación propuesta —el alcance fue evaluar, no corregir—.

## 2. Arquitectura en capas

| Capa | Módulos | Responsabilidad | Lo que no hace |
| --- | --- | --- | --- |
| Presentación | `src/web/` (incluye `asistente.py` e `ia.py`) | Rutas, plantillas Jinja y estáticos. Toma la petición, llama a la fachada y pinta | No escribe SQL ni decide reglas (`REQ-29`) |
| Dominio | `src/domain/` | `Wallet`, `Transaction`, `Block`, `Blockchain`, `TransactionStatus` y `Auditoria` | No conoce el motor (`REQ-16`) |
| Persistencia | `src/persistence/` | Conexión, adaptadores PostgreSQL detrás de protocolos, unidad de trabajo y sello de vigilancia (`SelloDeVigilancia`) | No decide reglas |
| Cuentas | `src/accounts/` | Servicio de usuarios, credenciales, contactos, fotos y solicitudes | No conoce la cadena |
| Composición | `src/web/__main__.py`, `src/bootstrap.py` | Arma las fábricas reales y siembra la demostración | Es el único lugar que cablea todo |
| Proyección | `red_neuronal/`, `src/web/proyeccion.py` | Red neuronal opcional que estima el próximo mes | No toca la cadena ni la base |

La regla que sostiene el diseño es una sola: **la presentación habla con la fachada, la
fachada con los protocolos y los protocolos con PostgreSQL**. Una prueba automática
(`tests/unit/test_req_29_presentacion.py`) falla si `src/web` nombra `psycopg` o la capa de
persistencia, así que la separación no depende de la disciplina de quien escribe.

## 3. Modelo de datos

Siete tablas y veinte índices, todos en `db/init.sql`, que es la única fuente del
esquema. Los veinte índices salen de siete claves primarias, cinco restricciones
`UNIQUE` y ocho índices declarados con `CREATE [UNIQUE] INDEX`; el número se puede
comprobar contra el archivo y conviene citarlo así, con su desglose, para que no quede
como una cifra suelta:

| Tabla | Qué guarda | Restricciones que importan |
| --- | --- | --- |
| `wallets` | Par de llaves y, opcionalmente, la cuenta dueña; la privada cifrada | Pública única y no vacía; el material cifrado no puede ir vacío; `owner_id` nulo es una wallet sin dueño |
| `blocks` | Índice, marca de tiempo y los dos hashes | Índice y hash únicos; los hashes son SHA-256 en hexadecimal |
| `transactions` | Emisor, receptor, monto, estado, firma y bloque | Monto positivo, emisor ≠ receptor, firma no vacía y única, coherencia estado/bloque |
| `users` | Cuenta, rol, estado del alta y motivo de rechazo | Nombre único sin distinguir mayúsculas; rechazado exige motivo; **no guarda wallet** |
| `contactos` | Agenda de cada usuario | No se puede agregar a sí mismo; la pareja es la clave y no se repite |
| `solicitudes_de_contrasena` | Cambio de contraseña propuesto | Una pendiente por usuario; el rechazo exige motivo |
| `fotos_de_perfil` | Nombre del archivo de la foto | Sólo jpg, png o webp, con el patrón de nombre que genera la aplicación |

La propiedad de una wallet **no vive en `users`**: vive en `wallets.owner_id`, que
apunta desde la wallet hacia la cuenta con `ON DELETE RESTRICT`. Una cuenta común
aprobada puede ser dueña de ninguna, una o varias wallets, y el administrador y las
cuentas pendientes o rechazadas no tienen ninguna. El esquema no puede expresar esa
regla como un `CHECK` entre dos tablas, así que la valida el servicio de cuentas; la
llave foránea y el índice `idx_wallets_owner` sí quedan en el motor. El detalle y el
porqué están en §5.6.

La aplicación **nunca ejecuta DDL** (`REQ-15`): el esquema se aplica al crear el volumen.
No hay herramienta de migraciones, y es una decisión, no un olvido: para un prototipo con
datos de demostración, recrear el volumen es una operación de treinta segundos y un sistema
de migraciones sería infraestructura que nadie va a usar. La consecuencia está declarada:
un volumen anterior a una tabla nueva no arranca, y el arranque lo dice.

## 4. Decisiones que vienen del eje

El eje académico fija y este repositorio no rediscute: la arquitectura en capas, las cinco
clases del dominio, los protocolos de persistencia, las tres tablas del modelo relacional,
las cinco rutas HTTP, la fórmula del saldo disponible (recibido confirmado − enviado
confirmado − lo comprometido en el pool), la agrupación atómica (`REQ-18`), la verificación
de sólo lectura (`REQ-22`), los errores del motor sin traducir (`REQ-19`), el génesis en el
índice cero con hash previo de ceros (`REQ-14`) y el stack: Python 3.11+, PostgreSQL 16,
`psycopg` 3, Flask y `pytest`.

## 5. Decisiones propias, declaradas

Ninguna contradice al eje; todas se pueden discutir.

### 5.1 Criptografía

- **Curva `secp256k1`** con la librería `cryptography`. El eje pide ECDSA sin fijar curva, y
  ésta es la del dominio blockchain.
- **Qué se firma**: una cadena canónica con la llave pública del emisor, la del receptor, el
  monto con escala fija, el identificador de la transacción y su marca de tiempo. La
  verificación comprueba esa cadena con la pública del emisor.
- **Cifrado del material privado**: `Fernet` (AES-128-CBC + HMAC) con una clave maestra que
  llega por `MASTER_KEY`. El eje exige el cifrado y la clave en el entorno, sin fijar
  algoritmo.

### 5.2 Integridad registrada

- **Índice único sobre `transactions.signature`**: es la única desviación del modelo
  relacional del eje y existe para que «rechazar una firma repetida» (`REQ-03`) lo garantice
  la base y no sólo el código. La comprobación vive en dos capas: el dominio consulta antes
  para poder informar el motivo, y el índice queda como respaldo del motor. **Aprobada el
  2026-10-10.**
- **Identificadores generados en la aplicación** (`uuid4`), no por el valor por defecto de la
  base: hay que conocer el identificador antes de calcular el hash del bloque.
- **Qué cubre el hash de un bloque**: índice, marca de tiempo, hash previo y la forma
  canónica de cada transacción agrupada, ordenadas por identificador. Como los
  identificadores están incluidos, mover una transacción de un bloque a otro también se
  detecta.
- **El génesis lo crea la aplicación**, de forma idempotente con `python -m src.bootstrap`. No
  se escribe en el SQL porque su hash es un cálculo y porque es un dato, no DDL.
- **La verificación recalcula también el génesis**. El eje describe el recorrido desde el
  índice 1, pero alterar la marca de tiempo del bloque cero sin tocar su hash pasaría
  inadvertido; el objetivo del proyecto es que *todo* cambio se note.

### 5.3 Datos y convenciones

- **Aporte y retiro no tienen columna**: se distinguen por la dirección respecto de la wallet
  del fondo. Agregar una columna habría cambiado el modelo del eje por una convención de
  presentación.
- **Los datos de demostración están reescritos** para representar el caso real: un fondo que
  recibe aportes y gira retiros, sin saldos negativos. La única excepción deliberada es la
  wallet del constituyente, que termina en negativo porque es la puerta por la que entra el
  capital en un modelo sin emisión.
- **La wallet del fondo se identifica por convención** (su llave pública es una constante), no
  por un dato en la base. Es una limitación que viene del modelo del eje.

### 5.4 Usuarios y roles

- **Dos roles**: usuario común (usa el sistema con una o varias wallets) y administrador
  (conserva el control del sistema entero).
- **Alta abierta pero moderada**: la persona se registra sola y queda pendiente; el
  administrador aprueba o rechaza con motivo.
- **Los envíos se identifican por nombre de usuario**, único, y opcionalmente por el
  identificador de la wallet.
- **La propiedad de las wallets** no vive en la cuenta: la cuenta es la identidad y la
  wallet es la custodia. El modelo, el porqué y sus límites están en §5.6.
- **Saldo de bienvenida de 1000** acreditado desde el constituyente en la misma operación
  atómica que crea la wallet y cambia el estado. Como el saldo sólo cuenta transacciones
  confirmadas, el crédito se emite en un **bloque nuevo con esa única transacción**: cada
  aprobación agrega un bloque a la cadena. El costo es despreciable: la verificación es
  lineal en bloques y una medición informal —no versionada como banco reproducible— dio
  del orden de 1,4 ms con 4 bloques y 84 ms con 1.000. Es una **estimación declarada**, no
  una medición reproducible: no hay banco de pruebas de rendimiento en el repositorio.
- **El administrador es una cuenta sembrada** con su contraseña en el entorno: no hay
  auto-registro de administradores.
- **Las rutas del eje quedan del lado del administrador**. El usuario común ve su saldo, su
  historial, su formulario de envío y la verificación de su propio historial.
- **Sesión con la cookie firmada de Flask**; la cookie guarda sólo el identificador y la cuenta
  se relee de la base en cada petición, así un cambio de estado se nota sin reiniciar.
- **Contraseñas con `hashlib.scrypt`** y sal por usuario, guardadas como
  `scrypt$n$r$p$sal$hash`. Sin dependencias nuevas.
- **El arranque siembra al administrador y cinco usuarios de demostración** ligados a las
  wallets de la convención, todos aprobados y con contraseña documentada.

### 5.5 Operación

- **Ningún guion de shell ni `Makefile` como camino único**: todos los puntos de entrada son
  módulos de Python (`python -m ...`), y la composición funciona igual con `docker compose`
  y con `podman compose`.

### 5.6 Wallet con dueño y varias wallets

- **La propiedad vive en `wallets.owner_id`**, no en `users`: la llave foránea apunta desde la
  wallet hacia la cuenta, con `ON DELETE RESTRICT` para que no se borre una cuenta que todavía
  es dueña de alguna, y `idx_wallets_owner` resuelve las consultas por dueño. `NULL` es una
  wallet sin dueño (`REQ-46`, `REQ-47`).
- **Por qué**: la cuenta es la identidad de la persona y la wallet es la custodia del par de
  llaves. Separarlas permite que una misma cuenta opere con varias wallets y que el
  administrador registre una wallet sin dueño o se la asigne a una cuenta.
- **Cómo se usa**: la aprobación crea la primera wallet y le acredita el saldo de bienvenida; el
  administrador registra las adicionales desde «Wallets» eligiendo su dueño o dejándolas sin
  dueño; el tablero deja elegir con qué wallet se opera. La primera es la principal: es la que
  recibe un envío dirigido por nombre de usuario, y las demás se direccionan por su
  identificador.
- **Límite**: el esquema no puede expresar como `CHECK` entre dos tablas que sólo una cuenta
  común aprobada sea dueña; esa regla la valida el servicio de cuentas, que rechaza la
  asignación a una cuenta no aprobada. El administrador no tiene wallets propias.

### 5.7 Auditoría del estado y sello de vigilancia

- **La auditoría** (`src/domain/auditoria.py`) recorre todos los bloques, todas las
  transacciones confirmadas y el pool en una sola pasada —lee las transacciones una vez y las
  agrupa en memoria, sin una consulta por bloque—, recalcula hashes y encadenamiento y
  comprueba además coherencia estado/bloque, montos, wallets y firmas contra la llave pública
  **actual** del emisor. Clasifica los hallazgos en `critico`, `aviso` y `nota`; `valida` se
  calcula sobre los críticos y `limpia` sobre críticos y avisos. No escribe (`REQ-22`) ni
  depende de Flask o de `psycopg` (`REQ-16`), y se pinta en el panel de `/verificar`, del lado
  del administrador.
- **Por qué además de la verificación del eje**: la verificación localiza la primera alteración
  y se detiene; la auditoría es la lectura completa y explicada que el panel necesita para
  decir qué está mal, dónde y qué reparación lo atiende.
- **El sello de vigilancia** (`src/persistence/sello.py`) guarda en un archivo JSON fuera de la
  base la altura y el hash de la cabeza, con el momento en que se fijó, firmados con
  HMAC-SHA256 sobre la forma canónica del JSON. Vive en `datos/sello-de-vigilancia.json`, la
  variable `SELLO_DE_VIGILANCIA` lo reubica, la escritura es atómica y la lectura nunca levanta:
  informa `ausente` o `ilegible`. No se actualiza solo: lo fija el arranque y la acción
  `fijar-sello`.
- **Por qué**: sin un ancla externa, recortar la cola de la cadena deja una cadena
  internamente coherente, indistinguible de una que nunca tuvo esos bloques; el hash previo no
  lo delata porque no hay predecesor que lo contradiga.
- **Límites, que el panel declara**: quien pueda escribir en la base y en el archivo del sello
  puede falsificar los dos; el recorte de la cola sólo se nota con un sello fijado antes del
  recorte; reencadenar devuelve coherencia, no el contenido original; un hueco de índices o un
  bloque borrado en medio no se reparan desde la interfaz.

### 5.8 Reparación de la cadena

- **`POST /verificar/reparar`** es la única ruta que escribe por la verificación, exige rol de
  administrador, exige `confirmar=si` y una acción de la lista, y responde 303 hacia
  `/verificar` (POST-redirect-GET) para que el panel vuelva a pintar el estado real. La
  verificación de sólo lectura sigue siendo `REQ-22`: reparar es un acto explícito y aparte.
- **Acciones**: `reparar-todo` (rechaza las pendientes inválidas, aísla las confirmadas
  inválidas y reencadena), `encadenar`, `aislar`, `rechazar-pendientes`, `reagrupar` —que usa
  `group_pending`— y `fijar-sello`. La plantilla ofrece sólo las que cierran algún hallazgo
  encontrado.
- **Límite**: repara coherencia y deja el aviso de lo que hizo, pero no recupera el contenido
  alterado ni borrado, ni cierra los huecos. Después de reparar hay que volver a fijar el
  sello.

### 5.9 El ayudante de IA

- **Dos respuestas y una sola pestaña**: `src/web/asistente.py` sirve `GET /asistente`,
  `GET /asistente/ahora` —la explicación de la página en la que está la persona— y
  `POST /asistente/preguntar`.
- **Sin proveedor, guía local**: busca el tema de la pregunta por palabras clave y contesta en
  español o en inglés. Es lo que hace que el ayudante sirva en una máquina sin red (`REQ-44`).
- **Con proveedor, un modelo externo**: `src/web/ia.py` reconoce el proveedor por el comienzo
  de `ASISTENTE_API_KEY`; `ASISTENTE_PROVEEDOR`, `ASISTENTE_MODELO` y `ASISTENTE_URL` cubren
  las claves que no se distinguen por su prefijo y los servicios locales. Habla con Anthropic
  por su SDK y con el resto por la API compatible con OpenAI usando la biblioteca estándar, sin
  sumar dependencias. Si la llamada falla, contesta la guía local y la persona no ve el error
  técnico.
- **Sólo lectura**: lee la fachada del ledger y el servicio de cuentas; no firma, no crea
  transacciones ni bloques y no escribe en la base. El contexto del usuario común es sólo el
  suyo —saldo y últimos movimientos— y el del administrador son los conteos de su portada; sin
  sesión, la pestaña no se pinta y las rutas de datos responden 401 (`REQ-35`).
- **Privacidad y límite**: cuando hay proveedor externo viajan la pregunta y un resumen de la
  cuenta —saldo y últimos movimientos, con los nombres que el historial ya muestra—, nunca las
  llaves privadas; la página lo avisa antes de preguntar y los botones de sugerencia no salen
  del equipo (`REQ-45`). La calidad de la respuesta depende de un servicio de terceros: sin
  red, sin clave o con error, el ayudante degrada a la guía local.

### 5.10 La proyección con red neuronal

- **Dónde vive**: el paquete `red_neuronal/` y `src/web/proyeccion.py`. Corre **en el proceso
  de la aplicación**, sin servicio aparte ni llamada a una API; carga el modelo una vez y lo
  guarda en memoria. Si TensorFlow o el modelo faltan, devuelve `None` y la página de
  estadísticas queda sólo descriptiva: el prototipo sigue funcionando.
- **Qué aporta y qué no**: la aritmética de la página —saldo, sumas, gráficas— sigue saliendo
  de la base y es exacta; la red sólo estima dos montos del mes siguiente. Recibe ocho
  características de los últimos sesenta días y devuelve dos proporciones sobre lo recibido,
  que la aplicación vuelve a pesos.
- **Límite**: se entrenó con un dataset generado por reglas explícitas y la tarjeta cita el
  resumen del entrenamiento (`resultados.json`); con historial real se reentrena. El ayudante
  no usa esta red: un modelo de lenguaje redacta, esta red estima números. El detalle del
  diseño, las entradas y las figuras está en [red-neuronal.md](red-neuronal.md).

## 6. Seguridad: dónde vive cada regla

| Regla | Dónde vive | Por qué ahí |
| --- | --- | --- |
| Quién puede llamar a una ruta | `src/web/auth.py`, un decorador por ruta | La autorización es la puerta, no una regla de negocio: el dominio no sabe que existen usuarios |
| Si una operación es válida | `src/domain/` | Saldo, firma, formato y encadenamiento son reglas del dominio |
| Contraseñas | `src/accounts/credentials.py` | `scrypt` con sal y comparación con `compare_digest` |
| Secretos | `.env` + `src/persistence/factory.py` | El lector rechaza los valores de plantilla: con la clave de ceros cualquiera descifra las llaves privadas |
| Firma de la cookie | `SESSION_SECRET` | Sin firma, el navegador podría elegir su propio usuario |
| Sesión de sólo lectura | `g.user` recargado por petición | Un cambio de estado o de rol se nota sin reiniciar |
| Mensajes de ingreso | Un único mensaje | No distingue usuario inexistente de contraseña equivocada |
| Errores de conexión | `src/persistence/conexion.py` + página 503 | El fallo del motor no se filtra al navegador ni revienta la página |
| Sello de vigilancia | `src/persistence/sello.py` | HMAC-SHA256 con la `MASTER_KEY` sobre la forma canónica y escritura atómica: un archivo alterado a mano no cuadra |
| Reparaciones de la cadena | `POST /verificar/reparar` con `confirmar=si` y lista cerrada de acciones | Reparar es un acto explícito del administrador, separado de la verificación de sólo lectura |
| Contexto del ayudante | `src/web/asistente.py` | Sólo se arma el de la cuenta de la sesión; el modelo externo no recibe llaves ni puede escribir |

## 7. Matriz de permisos

| Ruta o acción | Usuario común | Administrador |
| --- | --- | --- |
| Ver su saldo, sus transacciones y su verificación | sí | sí |
| Ver el saldo o el historial de otros | **no** | sí |
| Proponer un envío | sí, sólo desde sus wallets | sí, desde cualquiera |
| Agrupar las pendientes en un bloque | **no** | sí |
| Verificar la cadena completa | **no** | sí |
| Auditar el estado y ver el panel de sello y hallazgos | **no** | sí |
| Aplicar una reparación de la cadena | **no** | sí |
| Registrar wallets | **no** | sí |
| Aprobar o rechazar usuarios | **no** | sí |
| Elegir con qué wallet opera y ver las suyas | sí | sí |
| Usar el ayudante | sí, sólo con su cuenta | sí |
| Cambiar llaves | no existe | no existe |

## 8. Límites declarados

Son parte del diseño, no defectos escondidos:

1. **Las llaves privadas viven en el servidor**, cifradas con la `MASTER_KEY`. Consecuencia:
   el administrador puede firmar en nombre de cualquier usuario. La *integridad* del registro
   no depende de eso —una transacción confirmada que se altere se detecta, firme quien
   firme—, pero la *autoría* sí.
2. **Un solo nodo**: no hay consenso ni pares, así que la cadena no prueba resistencia a un
   atacante con control del servidor; prueba detección de alteraciones.
3. **Sin protección CSRF, sin límite de intentos de ingreso y sin bitácora** del
   administrador. Un producto real las necesita; este prototipo académico no las tiene y lo
   declara.
4. **Sin migraciones**: un volumen viejo no arranca; se recrea y se vuelve a sembrar.
5. **El fondo se identifica por convención**, y la distinción aporte/retiro no está en la
   base.
6. **El saldo de bienvenida sale del constituyente**, que por eso queda en negativo: es la
   emisión del modelo, no un error de datos.
7. **El ayudante y la proyección no pueden modificar nada**: el asistente sólo consulta y la
   red sólo estima; ninguna de las dos escribe en la cadena.
8. **El sello de vigilancia es un archivo local**: sirve contra un recorte de la cola en la
   base, no contra quien pueda escribir en la base y en el archivo a la vez; y sin un sello
   fijado antes, el recorte no se detecta.
9. **La reparación devuelve coherencia, no contenido**: reencadenar no recupera un dato
   alterado o borrado, y los huecos de índices no se reparan desde la interfaz. Después de
   reparar hay que volver a fijar el sello.
10. **La proyección es una estimación**: se entrenó con un dataset generado por reglas
    explícitas y no es una medición de lo que va a pasar; sus cifras se citan con la fuente
    del entrenamiento y con historial real se reentrena.
11. **No hay despliegue público**: el acceso es el repositorio y los comandos del `README.md`,
    y los hallazgos del pentest quedan abiertos con remediación propuesta, porque el alcance
    fue evaluar y no corregir.
