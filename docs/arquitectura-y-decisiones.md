# Arquitectura y decisiones de diseño

Este documento reemplaza los documentos de diseño que se usaban durante la construcción
del prototipo. Acá quedan las decisiones que el eje académico no fija y que el código
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
recuperación de contraseñas ni auditoría de acciones.

## 2. Arquitectura en capas

| Capa | Módulos | Responsabilidad | Lo que no hace |
| --- | --- | --- | --- |
| Presentación | `src/web/` | Rutas, plantillas Jinja y estáticos. Toma la petición, llama a la fachada y pinta | No escribe SQL ni decide reglas (`REQ-29`) |
| Dominio | `src/domain/` | `Wallet`, `Transaction`, `Block`, `Blockchain` y `TransactionStatus` | No conoce el motor (`REQ-16`) |
| Persistencia | `src/persistence/` | Conexión, adaptadores PostgreSQL detrás de protocolos y unidad de trabajo | No decide reglas |
| Cuentas | `src/accounts/` | Servicio de usuarios, credenciales, contactos, fotos y solicitudes | No conoce la cadena |
| Composición | `src/web/__main__.py`, `src/bootstrap.py` | Arma las fábricas reales y siembra la demostración | Es el único lugar que cablea todo |
| Proyección | `red_neuronal/`, `src/web/proyeccion.py` | Red neuronal opcional que estima el próximo mes | No toca la cadena ni la base |

La regla que sostiene el diseño es una sola: **la presentación habla con la fachada, la
fachada con los protocolos y los protocolos con PostgreSQL**. Una prueba automática
(`tests/unit/test_req_29_presentacion.py`) falla si `src/web` nombra `psycopg` o la capa de
persistencia, así que la separación no depende de la disciplina de quien escribe.

## 3. Modelo de datos

Siete tablas, todas en `db/init.sql`, que es la única fuente del esquema:

| Tabla | Qué guarda | Restricciones que importan |
| --- | --- | --- |
| `wallets` | Par de llaves; la privada cifrada | Pública única y no vacía; el material cifrado no puede ir vacío |
| `blocks` | Índice, marca de tiempo y los dos hashes | Índice y hash únicos; los hashes son SHA-256 en hexadecimal |
| `transactions` | Emisor, receptor, monto, estado, firma y bloque | Monto positivo, emisor ≠ receptor, firma no vacía y única, coherencia estado/bloque |
| `users` | Cuenta, rol, estado y wallet | Nombre único sin distinguir mayúsculas; wallet única y nula mientras no esté aprobado |
| `contactos` | Agenda de cada usuario | No se puede agregar a sí mismo |
| `solicitudes_de_contrasena` | Cambio de contraseña propuesto | Una pendiente por usuario; el rechazo exige motivo |
| `fotos_de_perfil` | Nombre del archivo de la foto | Sólo jpg, png o webp, con el patrón de nombre que genera la aplicación |

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

- **Dos roles**: usuario común (usa el sistema como una wallet) y administrador (conserva el
  control del sistema entero).
- **Alta abierta pero moderada**: la persona se registra sola y queda pendiente; el
  administrador aprueba o rechaza con motivo.
- **Los envíos se identifican por nombre de usuario**, único, y opcionalmente por el
  identificador de la wallet.
- **Una wallet por usuario**, creada al aprobar. Varias wallets por persona es otro producto.
- **Saldo de bienvenida de 1000** acreditado desde el constituyente en la misma operación
  atómica que crea la wallet y cambia el estado. Como el saldo sólo cuenta transacciones
  confirmadas, el crédito se emite en un **bloque nuevo con esa única transacción**: cada
  aprobación agrega un bloque a la cadena. El costo es despreciable (la verificación se midió
  en 1,4 ms con 4 bloques y 84 ms con 1.000).
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

## 7. Matriz de permisos

| Ruta o acción | Usuario común | Administrador |
| --- | --- | --- |
| Ver su saldo, sus transacciones y su verificación | sí | sí |
| Ver el saldo o el historial de otros | **no** | sí |
| Proponer un envío | sí, sólo desde su wallet | sí, desde cualquiera |
| Agrupar las pendientes en un bloque | **no** | sí |
| Verificar la cadena completa | **no** | sí |
| Registrar wallets | **no** | sí |
| Aprobar o rechazar usuarios | **no** | sí |
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
