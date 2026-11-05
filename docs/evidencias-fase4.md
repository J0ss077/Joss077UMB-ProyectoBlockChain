# Evidencias de la Fase 4

Actualización del repositorio: diseño, navegabilidad e integración con la base de datos.
Documento de apoyo de la entrega; las capturas de pantalla se guardan en
`docs/evidencias/capturas/`.

- **Rama de la entrega:** `fase-4`.
- **Fecha de corte:** 4 de noviembre de 2026.
- **Repositorio:** https://github.com/J0ss077/Joss077UMB-ProyectoBlockChain
- **Tecnología:** Python 3.11+, Flask, PostgreSQL y la interfaz web del prototipo
  (tecnología ya aprobada en el eje del proyecto: PostgreSQL está declarado en el
  diseño y el README lo explica en «La conexión con la base de datos»).

## 1. Qué pide la guía y dónde está

| Requisito de la Fase 4 | Dónde está | Cómo se comprueba |
| --- | --- | --- |
| Mejorar la presentación visual y unificar colores, tipografía y tamaños | `src/web/static/css/` (tokens), `docs/sistema-de-diseno.md` | Tema claro y oscuro en todas las pantallas; botón de tema en la barra |
| Organizar formularios, botones, campos, tablas y mensajes | `src/web/templates/` | Cualquier formulario: etiqueta, ayuda, error debajo del campo |
| Mensajes claros de éxito y de error | `src/web/templates/base.html` (bandeja) y `src/web/*.py` (`flash`) | Registrar algo y ver el aviso; enviar un monto inválido y ver el motivo |
| Menú principal y navegación entre módulos | `src/web/templates/base.html` | Barra superior con los enlaces del rol; logo que vuelve al inicio |
| Retorno a la pantalla principal y entre formularios | `base.html`, migas del historial, botones de `error.html` | Botones «Volver», «Ir a mi tablero», «Reintentar» |
| Validar que los enlaces funcionen | `tests/integration/test_navegacion.py` | `pytest tests/integration/test_navegacion.py` |
| Configuración de la conexión desde la aplicación | `src/persistence/conexion.py` y `factory.py`; `.env` | Levantar la app y apagarla base: página 503 explicada |
| Consulta y visualización de registros | Portada, panel de wallets, historial, bloques, transacciones, estadísticas | Abrir cada pantalla con datos sembrados |
| Registro de información mediante formularios | Registro de cuenta, wallet, envío, contacto, foto, cambio de contraseña | Crear una cuenta y verla en `/admin/pendientes` |
| Validación antes de escribir en la base | `src/web/forms.py`, dominio y `CHECK` de `db/init.sql` | Enviar monto negativo o firma repetida y leer el motivo |
| Manejo de errores de conexión y de operaciones | `src/web/app.py` (503), `error.html`, `src/errores.py`, `tests/integration/test_conexion.py` | Apagar PostgreSQL y abrir la aplicación |
| Módulo independiente de conexión | `src/persistence/conexion.py` | Abre, deja la sesión en UTC y traduce el fallo del motor |
| Scripts SQL de tablas y datos | `db/init.sql` (tablas, `CHECK`, índices) y `python -m src.bootstrap` (semilla) | Ver «Por qué la semilla no es un `.sql`» |
| Separación de interfaz, lógica y acceso a datos | `src/domain/`, `src/persistence/`, `src/accounts/`, `src/web/` | La guarda `tests/unit/test_req_29_presentacion.py` lo exige |
| README con requisitos, instalación, configuración y ejecución | `README.md` | Seguirlo desde cero |
| Commits descriptivos | `git log --oneline` | Mensajes por cambio, en español |
| Sin credenciales en el repositorio | `.gitignore`, `.env.example` | `.env` no está versionado; los lectores rechazan los valores de plantilla |

### Por qué la semilla no es un `.sql`

`db/init.sql` **sí** es el script de creación de las tablas: es la única fuente del
esquema (la aplicación nunca ejecuta DDL). Los datos de prueba no están ahí porque el
bloque génesis no es una fila fija: su hash se calcula sobre el índice, la marca de
tiempo y el hash previo, y las wallets necesitan un par de llaves ECDSA cifrado con la
`MASTER_KEY` de cada equipo. Un `INSERT` con hashes y llaves inventados rompería la
verificación de la cadena y no podría firmar transacciones. Por eso la semilla es
`python -m src.bootstrap`, idempotente y con datos que sí verifican; el detalle está en
el encabezado de `src/bootstrap.py` y en el paso 4 del README.

## 2. Evidencias incluidas en el repositorio

1. **Consulta a la base con datos reales:** `docs/evidencias/consulta-en-la-base.txt`.
   Es la salida real de `psql "$DATABASE_URL" -f db/consultas.sql` contra la base que
   usa la aplicación, con el conteo de filas, los saldos, la cadena eslabonada y la
   fila del registro hecho desde la interfaz.
2. **Registro desde la interfaz:** la cuenta `evidencia-fase4` se creó con el
   formulario público (`POST /registrarme`, 4 de noviembre de 2026, 17:53) y quedó en
   la base como `pendiente`, sin wallet. Después se aprobó desde
   `GET /admin/pendientes` —por eso hoy figura `aprobado` y con wallet, con su saldo de
   bienvenida en un bloque propio—, y para la captura de la cola se registró una
   segunda cuenta, `pendiente-demo`, que quedó esperando. Las dos filas están en la
   sección de registro de `consulta-en-la-base.txt`.
3. **Pruebas automáticas:** `pytest` completo en verde (ver la sección 6) y, en
   particular, `tests/integration/test_navegacion.py` y
   `tests/integration/test_conexion.py`, que cubren la navegación y el error de
   conexión sin depender de que la base esté caída para siempre.
4. **Recorrido real por HTTP:** `docs/evidencias/recorrido-http.txt`. Es la salida
   de pedir la aplicación levantada como lo haría un navegador —ingreso como
   administrador, cada pantalla de su menú, cierre de sesión, ingreso como usuario
   común y sus pantallas— con el código HTTP de cada una. Sirve como respaldo de las
   capturas: si una pantalla cambia, el archivo dice cómo estaba el 4 de noviembre de
   2026.
5. **Flujo completo y alteración:** `docs/evidencias/flujo.txt`. El paso a paso de
   wallet → transacción → bloque → verificación, con los identificadores, el hash del
   bloque y el ida y vuelta de la alteración (ver la sección 7).
6. **Resultados de las pruebas ejecutadas:** `docs/evidencias/pruebas.txt`. La salida
   real de `pytest` contra una base aparte, con el resumen de la suite y el detalle de
   las pruebas de firma, firma repetida y alteración (ver la sección 8).

> **Cómo se toma la evidencia.** La suite vacía las tablas que usa (ver la
> dificultad 7), así que la evidencia se toma **después** de correr las pruebas, o con
> `TEST_DATABASE_URL` apuntando a una base aparte.

## 3. Capturas de pantalla

Están en `docs/evidencias/capturas/` y son la aplicación de este repositorio
funcionando contra PostgreSQL, no un diseño aparte. Las diecinueve de la interfaz se
tomaron con un navegador sin interfaz sobre las páginas que sirve la propia aplicación,
con las animaciones de entrada detenidas para que se vea el estado final; las dos de
terminal son capturas de pantalla de una sesión real de `psql` contra la base de la
aplicación. Las veintidós están hechas.

| Archivo | Qué muestra | Estado |
| --- | --- | --- |
| `01-ingreso.png` | La pantalla de ingreso con el tema de la aplicación | ✅ |
| `02-portada-admin.png` | Portada del administrador: conteos, cadena, últimas transacciones y panel de wallets con saldos | ✅ |
| `03-wallets.png` | La gestión de wallets con la clave pública y el botón de copiar | ✅ |
| `04-transacciones-rechazo.png` | El formulario de transacción con un monto inválido y el mensaje que explica el rechazo | ✅ |
| `05-bloques.png` | El cierre de bloque con el pool en espera | ✅ |
| `06-verificar.png` | El dictamen de integridad de la cadena | ✅ |
| `07-pendientes.png` | La cola de aprobación con una cuenta pendiente y su fecha de registro | ✅ |
| `08-tablero-comun.png` | El tablero del usuario común: saldo y envío | ✅ |
| `09-estadisticas-comun.png` | Las estadísticas propias: filtros, cifras, gráficas y la tarjeta de proyección del próximo mes | ✅ |
| `10-estadisticas-admin.png` | El selector del administrador y las estadísticas de un usuario, con su proyección | ✅ |
| `11-asistente.png` | La pestaña del ayudante | ✅ |
| `12-tema-oscuro.png` | La misma pantalla de estadísticas con el tema oscuro | ✅ |
| `13-error-503.png` | La página de error cuando la base no responde | ✅ |
| `14-flujo-wallet-creada.png` | Una wallet recién registrada, con su identificador y su clave pública | ✅ |
| `15-flujo-transaccion-pool.png` | La transacción recién propuesta, «En el pool» | ✅ |
| `16-flujo-bloque-creado.png` | El bloque #146 creado y encadenado al hash del #145 | ✅ |
| `17-flujo-cadena-verificada.png` | La verificación: «La cadena es válida» | ✅ |
| `18-alteracion-detectada.png` | La misma verificación con una fila alterada por `psql`: «no es válida», bloque #146 | ✅ |
| `19-alteracion-revertida.png` | Vuelta a «La cadena es válida» después de reponer el dato | ✅ |
| `20-consulta-psql.png` | La terminal con `psql -f db/consultas.sql`: conteos por tabla, saldos por wallet y la cadena eslabonada | ✅ |
| `21-registro-en-bd.png` | `SELECT` de la cuenta `evidencia-fase4` con su estado y su fecha de registro | ✅ |
| `22-mis-contactos.png` | La agenda del usuario común con sus contactos y el movimiento de cada uno | ✅ |

## 4. Dificultades técnicas encontradas

1. **La base caída se veía como un 500 genérico.** El acceso a PostgreSQL vive en
   `before_request` (cada petición relee la cuenta de la sesión), así que sin motor
   fallaba cualquier página y el navegador mostraba el error de servidor en inglés.
   La guarda de REQ-29 impide que `src/web` nombre `psycopg`, así que la solución no
   podía ser un `try/except` en las rutas: se creó `src/errores.py` con
   `NoHayConexion`, `src/persistence/conexion.py` traduce ahí el `OperationalError` y
   la aplicación registra un manejador de 503. Así la presentación sigue sin conocer
   el motor y la página de error tampoco abre la base para pintarse.
2. **Las conexiones estaban repetidas en tres lugares** (el ledger, la transacción de
   la aprobación y la unidad de trabajo) y cada una repetía el `SET TIME ZONE 'UTC'`.
   Unificarlas en `conexion.py` era necesario para tener una sola traducción del
   error, y de paso dejó un módulo de conexión con nombre propio, que es lo que pide
   la entrega.
3. **Probar la navegación sin copiar el menú.** Los dos roles ven menús distintos y el
   enlace del ayudante viaja con `?desde=` la pantalla de origen, así que una lista de
   rutas escrita en la prueba se habría desactualizado al primer cambio de la barra.
   La prueba lee los `href` del `<nav>` que la aplicación pinta y abre cada uno con la
   sesión de su rol; además exige que el menú del común no ofrezca rutas del
   administrador y que ninguna pantalla se quede sin barra.
4. **Los filtros y las gráficas de estadísticas** se resuelven en el navegador para no
   recargar la página, pero el servidor tiene que seguir diciendo algo sin JavaScript:
   la página pinta el resumen de todo el historial y el JSON de movimientos por
   separado. Los montos viajan como texto para no perder los ocho decimales del
   `NUMERIC(18, 8)`.
5. **La rama de trabajo llevaba semanas separada de `main`** (el asistente, el perfil
   y el estado del arte por un lado; la documentación y las correcciones de registro
   por otro). Esta rama `fase-4` parte del trabajo de interfaz y deja `main` intacta
   hasta que el equipo decida el merge.
6. **La semilla no puede ser SQL.** El génesis se calcula y las llaves se cifran con
   la clave maestra de cada equipo; se documentó por qué en vez de inventar filas que
   romperían la verificación de la cadena.
7. **`TEST_DATABASE_URL` sin definir vacía la base de la aplicación.** El `conftest`
   de integración usa esa variable para no tocar la base real, pero si no está
   definida cae en `DATABASE_URL` y borra las tablas antes de cada caso. Mientras se
   preparaba esta entrega la suite se corrió sin esa variable y se perdió la cuenta
   que se había registrado como evidencia (se volvió a registrar). Queda como
   recomendación concreta: definir `TEST_DATABASE_URL` en el `.env` y aplicarle
   `db/init.sql` a esa base, tal como deja dicho `.env.example`. El README también lo
   advierte en «Cómo correr las pruebas».

## 5. Demostración en cinco pasos

```text
docker compose up -d
<venv> -m src.bootstrap
<venv> -m src.web
```

1. Abrir `http://127.0.0.1:5000/registrarme`, crear una cuenta y ver el aviso de que
   queda pendiente.
2. Entrar como administrador (`admin` y la contraseña de `ADMIN_PASSWORD`) y aprobar
   la cuenta en `/admin/pendientes`.
3. Entrar con la cuenta nueva: el tablero muestra su saldo de bienvenida y puede
   enviar dinero.
4. Con el administrador, `GET /verificar` da el dictamen de la cadena y el botón de
   `POST /bloques` agrupa lo que está pendiente en un bloque nuevo.
5. En la terminal:

```text
psql "$DATABASE_URL" -f db/consultas.sql
```

La consulta 8 muestra la última fila escrita y la 7 el estado de las cuentas.

## 6. Cómo correr las pruebas

```text
<venv> -m pytest -q
```

Las de integración necesitan PostgreSQL y vacían las tablas que usan; con
`TEST_DATABASE_URL` definida usan esa base y no la de la aplicación (ver la dificultad
7). La suite cubre el dominio, los adaptadores, las rutas, la navegación y el error de
conexión, y la guarda `tests/unit/test_req_29_presentacion.py` exige que la presentación
no toque el motor. Los resultados de la corrida de esta entrega están en la sección 8.

## 7. Flujo completo: wallet, transacción, bloque y verificación

Lo que pidió la revisión: la ejecución completa, con la pantalla de cada paso. Se hizo
sobre la aplicación levantada y su PostgreSQL, en este orden, y el detalle con los
identificadores está en `docs/evidencias/flujo.txt`.

| Paso | Ruta | Qué quedó | Captura |
| --- | --- | --- | --- |
| Registrar wallet | `POST /wallets` | Wallet `ffa65493…` con su clave pública `034d25fe…` y saldo 0 | `14-flujo-wallet-creada.png` |
| Proponer transacción | `POST /transacciones` | 25 desde `fondo` hacia la wallet nueva, estado «En el pool» | `15-flujo-transaccion-pool.png` |
| Cerrar bloque | `POST /bloques` | Bloque **#146**, hash `b6f747ce…`, encadenado al `73e55de1…` del #145 | `16-flujo-bloque-creado.png` |
| Verificar | `GET /verificar` | «La cadena es válida. Cada hash coincide con su contenido y con el del bloque anterior.» | `17-flujo-cadena-verificada.png` |

Y la respuesta ante una alteración hecha **por fuera de la aplicación** (un `UPDATE` con
`psql`, como el administrador de la base haría):

| Paso | Qué se hizo | Qué respondió el sistema | Captura |
| --- | --- | --- | --- |
| Alterar | `UPDATE transactions SET amount = amount + 100 …` (25 → 125) sobre una confirmada del bloque #146 | «La cadena no es válida. El primer bloque que no encaja es el de índice 146.» | `18-alteracion-detectada.png` |
| Reponer | `UPDATE … SET amount = 25 …` | «La cadena es válida» otra vez | `19-alteracion-revertida.png` |

Ese ida y vuelta es lo que demuestra que la verificación recalcula de verdad: con el
dato alterado falla, con el original vuelve a pasar, sin reiniciar la aplicación.

**Transacciones inválidas y firmas.** La captura `04-transacciones-rechazo.png` muestra
el rechazo en pantalla con su motivo («el monto debe ser mayor que cero»). Las firmas
no se pueden falsear desde la interfaz —las firma el servidor con la llave de la
wallet—, así que su defensa está en las pruebas: `19` pruebas de firma, firma repetida,
alteración y rechazos, todas en verde (sección 8).

## 8. Resultados de las pruebas ejecutadas

`docs/evidencias/pruebas.txt` guarda la salida real de la corrida del 4 de noviembre de
2026, contra una base PostgreSQL aparte (no la de la aplicación) con el esquema de
`db/init.sql`:

| Prueba | Resultado |
| --- | --- |
| Suite completa (`pytest -q`) | **350 passed en 110 s** (incluye las 9 de la proyección) |
| Firma del emisor contra una ajena (`test_req_02_firma.py`) | Pasa |
| Firma repetida rechazada por el motor (`test_req_03_firma_repetida.py`) | Pasa (3) |
| Alteración y borrado directos detectados (`test_req_10_alteracion.py`) | Pasa (3) |
| Rechazos del motor y del dominio (`test_req_11_rechazo_en_base.py`) | Pasa (13) |

Para reproducirlas sin tocar los datos de la aplicación hace falta una base aparte:
`TEST_DATABASE_URL` en el `.env` (ver la dificultad 7).

## 9. Checklist de la entrega

- [x] Código fuente actualizado en la rama `fase-4`.
- [x] Módulo independiente de conexión (`src/persistence/conexion.py`).
- [x] Scripts SQL de tablas (`db/init.sql`) y de consultas de evidencia
      (`db/consultas.sql`).
- [x] Semilla de datos de prueba (`python -m src.bootstrap`) con su justificación.
- [x] Separación interfaz / lógica / acceso a datos, con guarda automática.
- [x] README actualizado: rutas, capas, conexión, consultas y problemas conocidos.
- [x] Commits descriptivos por cambio.
- [x] Sin credenciales versionadas: `.env` en `.gitignore`, lectores que rechazan la
      plantilla.
- [x] Navegación y conexión caída cubiertas por pruebas.
- [x] Evidencia de consulta y de registro hecha desde la interfaz
      (`docs/evidencias/consulta-en-la-base.txt`).
- [x] Recorrido real por HTTP de las pantallas de los dos roles
      (`docs/evidencias/recorrido-http.txt`).
- [x] Flujo completo ejecutado y capturado: wallet, transacción, bloque y
      verificación (`docs/evidencias/flujo.txt`, capturas 14 a 17).
- [x] Alteración por fuera de la aplicación detectada y luego revertida (capturas 18 y
      19).
- [x] Resultados de las pruebas documentados (`docs/evidencias/pruebas.txt`).
- [x] Capturas de la aplicación en `docs/evidencias/capturas/` (22 de 22).
