# Prototipo transaccional basado en blockchain — diseño de la reconstrucción

- **Fecha**: 2026-10-10
- **Estado**: aprobado por los desarrolladores el 2026-10-10, con la ampliación de explicabilidad pedida ese mismo día. Pendiente el plan de implementación.
- **Eje del proyecto**: `documentacion_proyecto_transaccionales.pdf` (46 páginas, Grupo 1, Universidad Manuela Beltrán)

## Qué es esto

El eje del proyecto es el documento académico, no este repositorio. Ese documento fija el problema, el alcance, los 29 requerimientos con su criterio de aceptación (REQ), los 5 casos de uso con ficha (CU), las 5 clases del dominio, la arquitectura en capas, las 5 rutas HTTP y el modelo relacional.

**Este repositorio existe para hacer verdadero lo que el eje describe como prototipo.** Hoy el eje afirma en su página 43 que "el núcleo del prototipo ya está implementado y probado", y eso no es cierto en ningún código disponible: no hay criptografía, ni cálculo de hash, ni validación, ni verificación de cadena, ni rutas web, ni una sola prueba. Este repositorio pasa a ser la evidencia que ese párrafo necesita.

Consecuencia de diseño: **nada de lo que el eje ya decide se vuelve a decidir aquí.** Este documento no repite requisitos, casos de uso, clases ni arquitectura; los cita por ID. Si algo de este documento contradice al eje, gana el eje y este documento está mal.

## Regla de admisión del repositorio

Un archivo entra al repositorio solo si cumple al menos una de estas tres condiciones:

1. Sirve a un REQ o a un CU del eje.
2. Es necesario para correr, verificar o explicar el sistema (configuración, esquema, pruebas, los artefactos de la lista cerrada).
3. Es el propio código que implementa un REQ.

**Criterio de fracaso, declarado por adelantado**: si al terminar existe un archivo que no se puede mapear a un REQ, a un CU, a la explicación de un proceso o a la ejecución del sistema, la reconstrucción falló, aunque todas las pruebas pasen.

## Anti-objetivos

- **No reconstruir la ceremonia.** No hay ADRs, ni glosario, ni issue tracker, ni journal, ni un `spec.md` por funcionalidad, ni un índice de documentos, ni un archivo por módulo explicando lo que el módulo ya explica. El eje cumple el papel del glosario y del diseño; los artefactos de explicación son la lista cerrada de la sección siguiente. El repositorio anterior se llenó de esa capa: 1429 líneas de markdown contra 693 de Python, con la lógica central sin escribir.
- **No duplicar el eje.** Ningún documento del repositorio reescribe los requisitos, las fichas de casos de uso ni el modelo relacional. Se citan por ID.
- **No agregar columnas ni tablas** al modelo relacional del eje. La única desviación es el índice único de la decisión 4, aprobado por los desarrolladores el 2026-10-10.
- **No implementar** lo que el eje declara fuera de alcance: consenso distribuido, red P2P, replicación, tolerancia a fallos, inmutabilidad estricta y resolución de doble gasto entre nodos.
- **No prometer más de lo verificado.** Si una prueba no corre, no se afirma que el sistema funciona.

## Alcance

Se implementan los 29 requerimientos del eje, incluidos los de prioridad "Debería" (REQ-03, REQ-13, REQ-14, REQ-23), y los 5 casos de uso. Esto incluye la capa de presentación Flask (REQ-24 a REQ-29), que el eje marca como "Debe".

## Explicabilidad y continuidad

El tutor académico no solo exige que el sistema funcione: exige que el grupo pueda explicar en profundidad cada proceso y cada parte del código. Eso convierte a la explicación en un requisito de verdad, y por eso entra al diseño con un recorte explícito, porque "necesitamos artefactos" sin límite es justamente lo que produjo el repositorio anterior.

**Artefactos de explicación que sí entran** (lista cerrada; agregar uno exige decir qué pregunta responde y quién la hace):

1. **Docstrings y comentarios dentro del código.** Cada módulo dice qué problema resuelve y qué REQ implementa; cada clase dice su responsabilidad y su invariante; cada método dice su contrato, las reglas que aplica y qué pasa cuando falla. Van en español, junto al código que explican, y viajan con él: si el código cambia, el comentario está a la vista en el mismo diff.
2. **Las pruebas como explicación ejecutable.** Se llaman `test_req_NN_*`, y cada una lleva en su docstring el criterio de aceptación que comprueba. Para explicar cómo funciona la validación, el grupo muestra la prueba que la demuestra corriendo; no hay que creerle a nadie.
3. **`docs/recorrido-de-casos-de-uso.md`.** Un documento por caso de uso que sigue el camino real de una petición: qué hace el usuario, qué ruta la recibe, qué método del dominio decide, qué tabla se toca, qué consulta SQL se ejecuta y qué prueba lo demuestra. Cierra con las preguntas probables del tutor y dónde vive cada respuesta. No repite requisitos: narra la ejecución del código.
4. **Este diseño y el plan de implementación**, que dan el contexto para continuar el proyecto en el futuro sin depender de la memoria de nadie.

**Regla del comentario**: se queda el que explica _por qué_. Una decisión, una restricción del eje, un orden que importa, algo que sorprende. Se borra el que repite lo que la línea ya dice. Ejemplos que se quedan: por qué el saldo incluye lo comprometido en el pool, por qué el hash cubre las transacciones agrupadas, por qué no se valida en Python lo que el CHECK del esquema ya garantiza.

**Regla de continuidad (git)**: commits pequeños, uno por grupo de requerimientos, con mensajes en español que digan qué se hizo y por qué. El repositorio anterior metió 1168 líneas en un solo commit, y por eso hoy no se puede reconstruir su historia.

## Conducta observable ante una transacción inválida

El eje pide dos cosas que chocan entre sí: que el formato se valide antes de entrar al pool (REQ-04) y que las violaciones de CHECK, clave foránea y unicidad levanten el error del motor sin traducir (REQ-19). Además REQ-11 pide dejar la transacción inválida guardada como `rejected`, pero el propio esquema del eje lo impide en varios casos: `amount > 0`, emisor distinto del receptor y las claves foráneas se aplican a toda fila, sin importar su estado.

Resolución, derivada de las restricciones del eje y no de mi gusto: **el dominio valida primero (REQ-04) y siempre puede decir por qué rechaza; se guarda una fila `rejected` solo cuando el esquema permite esa fila; y cuando no lo permite, el rechazo se informa sin fila, dejando las restricciones del motor como respaldo, que es justamente lo que REQ-19 exige poder comprobar.**

| Caso                               | ¿Queda fila?      | Quién lo detiene                                   |
| ---------------------------------- | ----------------- | -------------------------------------------------- |
| Monto menor o igual a cero         | No                | CHECK del eje                                      |
| Emisor igual al receptor           | No                | CHECK del eje                                      |
| Emisor o receptor inexistente      | No                | Clave foránea del eje                              |
| Firma que no corresponde al emisor | Sí, `rejected`    | Dominio                                            |
| Saldo insuficiente                 | Sí, `rejected`    | Dominio                                            |
| Firma repetida                     | No                | Dominio (motivo) y unicidad del esquema (respaldo) |
| Agrupar con el pool vacío          | No se crea bloque | Dominio (flujo alterno del CU-03)                  |

Consecuencias para el plan: la prueba de REQ-19 escribe directo en la base para provocar la violación, porque el camino de la aplicación nunca la provoca; `POST /transacciones` responde con el motivo del rechazo en todos los casos; y el dominio no captura ni traduce errores del motor, así que en los casos sin fila quien responde el error es la base, como el eje pide.

**REQ-06 no necesita mecanismo nuevo**: el eje pone fuera de alcance la concurrencia y el doble gasto entre nodos, y el compromiso del pool hace que la segunda transacción ya no vea saldo disponible en el momento de crearse. El orden es el de llegada, en un proceso único, y no hay desempate que definir.

## Decisiones del eje (no se rediscuten)

- Arquitectura en capas: presentación (Flask + Jinja2), dominio (cinco clases), persistencia (Adaptador PostgreSQL), con el dominio aislado del motor (REQ-16).
- Cinco clases de dominio: `Wallet`, `Transaction` (con `is_valid()`), `Block` (con `calculate_hash()`), `Blockchain` (con la verificación de cadena) y `TransactionStatus`.
- Interfaces de persistencia: `WalletRepository`, `BlockRepository`, `TransactionRepository` y una unidad de trabajo.
- Esquema PostgreSQL con tres tablas (`wallets`, `blocks`, `transactions`), del modelo relacional del eje.
- Rutas HTTP exactas: `POST /wallets`, `POST /transacciones`, `POST /bloques`, `GET /verificar`, `GET /historial/<wallet>`.
- Saldo disponible del emisor = confirmado recibido − confirmado enviado − lo comprometido en el pool pendiente (flujo del CU-02).
- `Blockchain` obtiene el saldo disponible y se lo pasa a `Transaction.is_valid()` (diagrama de secuencia del CU-02).
- La agrupación ocurre en una sola transacción de base de datos (REQ-18) y la verificación solo lee (REQ-22).
- Los errores del motor suben sin traducir y las restricciones no se duplican en Python (REQ-19).
- El bloque génesis tiene índice 0 y hash previo de sesenta y cuatro ceros (REQ-14).
- Stack: Python 3.11 o superior (REQ-20), PostgreSQL 16 en contenedor, `psycopg` 3, Flask, `pytest`.

## Decisiones del constructor (mías, vetables)

Cada una se marca como mía; ninguna contradice al eje.

1. **Curva y librería**: ECDSA sobre `secp256k1`, con la librería `cryptography`. El eje pide ECDSA sin fijar curva; `secp256k1` es la curva del dominio blockchain y `cryptography` ya hace falta para el cifrado.
2. **Qué se firma**: la llave privada firma una cadena canónica con la llave pública del emisor, la del receptor, el monto con escala fija, el identificador de la transacción y su marca de tiempo. Así la firma es verificable y única por transacción.
3. **Cifrado del material privado**: `Fernet` (AES-128-CBC + HMAC) con una clave maestra que llega por el entorno (`MASTER_KEY`), nunca versionada (REQ-21). El eje exige que el material privado esté cifrado y que la clave maestra viva en el entorno, sin fijar algoritmo.
4. **Índice único sobre `transactions.signature`**: es la única desviación del modelo relacional del eje, y existe para que REQ-03 ("rechazar la repetición de una firma ya registrada") quede garantizado por la base y no solo por el código. **Aprobada por los desarrolladores el 2026-10-10.** La comprobación vive en dos capas: el dominio consulta antes de escribir para poder informar el motivo del rechazo, y el índice queda como respaldo del motor.
5. **Identificadores generados en la aplicación** (`uuid4`) y no por el valor por defecto de la base, para poder calcular el hash del bloque antes de escribirlo. El valor por defecto del esquema queda como respaldo.
6. **Contenido del hash de bloque**: índice, marca de tiempo, hash previo y la forma canónica de cada transacción agrupada, ordenadas por identificador. Los identificadores van incluidos, así que mover una transacción confirmada de un bloque a otro también altera el hash y se detecta.
7. **El génesis lo crea la aplicación**, de forma idempotente, mediante un arranque explícito (`python -m src.bootstrap`). No se escribe en el SQL porque su hash es un cálculo, y REQ-15 prohíbe DDL desde la aplicación (el génesis es un dato, no DDL).
8. **La distinción aporte/retiro no tiene columna** en el modelo relacional del eje, y no se le agrega ninguna: se resuelve por la dirección respecto de la wallet del fondo, y se documenta en el README junto con los datos de demostración. El eje nunca resuelve esta convención; aquí queda declarada.
9. **Datos de demostración reescritos desde cero**: representan el caso de aplicación (una wallet de fondo que recibe aportes de los asociados y les gira retiros), con saldos que cumplen la regla del REQ-05. No se copian los del repositorio anterior, que hacen que una wallet gaste sin haber recibido nunca nada. **Una excepción deliberada**: la wallet del constituyente —identificador y llave fijos en `src/bootstrap.py`— termina en −3000 porque es la puerta por la que el capital entra a un modelo que no tiene emisión. Su fila de emisión se escribe directo por el repositorio, aunque con firma real (REQ-02), y las otras tres filas de capital —el fondo a cada asociado— usan el mismo camino; todas las demás (aportes y retiros) se mueven por el camino normal y ningún otro saldo queda negativo. La alternativa —no representar la emisión— dejaría a la demostración sin ningún saldo con el que mostrar aportes ni retiros, que es justamente el caso del eje. El límite queda documentado en el README junto con los datos de demostración.
10. **Portabilidad**: ningún guion de shell y ningún Makefile como camino único. Todos los puntos de entrada son módulos de Python (`python -m ...`) y el archivo de composición funciona igual con `docker compose` y con `podman compose`.
11. **Lista cerrada de artefactos**: `README.md`, este diseño, el plan de implementación, `docs/recorrido-de-casos-de-uso.md`, `src/sabotaje.py`, los docstrings y comentarios dentro del código, y las pruebas. `src/sabotaje.py` entra a la lista por decisión del humano del 2026-10-10 y con su justificación: es una **herramienta de verificación y demostración**, no parte del camino de la aplicación —ninguna ruta la usa ni la importa (REQ-29)—, y responde a una pregunta que hoy no responde ningún artefacto: muestra en una sola corrida, delante de una persona que mira el navegador, qué detecta la cadena y qué no, con los límites declarados. Nada más se versiona sin decir qué pregunta responde; el material de referencia (`.legacy-project/`, `.reference/`) queda fuera del repositorio.
12. **El eje no se copia dentro del repositorio**: el README lo cita por nombre. Si el grupo prefiere que el repositorio sea autosuficiente, copiarlo es un cambio de una línea.
13. **La verificación recalcula también el hash del bloque génesis**: CU-04 dice "para cada bloque desde el índice 1", pero esa frase describe el recorrido de encadenamiento, y el génesis no tiene predecesor. El objetivo específico tercero del eje pide que _todo tipo_ de modificación del historial sea detectable, así que la verificación recalcula el hash propio de todos los bloques, índice 0 incluido, y además compara el `previous_hash` de cada uno con el hash guardado del anterior. Sin esto, alterar la marca de tiempo del génesis dejando su hash intacto pasaría inadvertido.
14. **El repositorio se construye desde cero en la raíz del workspace**, con su propio `git init` y un `.gitignore` que excluye `.env` (REQ-21), el entorno virtual y el material de referencia. `.legacy-project/` queda solo como referencia, nunca se importa y se puede borrar: la regla de `database/` congelado vive en el `AGENTS.md` de ese repositorio anterior y no gobierna a este.
15. **`db/init.sql` se escribe desde el modelo relacional del eje**, no se copia del repositorio anterior: la fuente es el eje, y el esquema anterior no expresa la unicidad de la firma de la decisión 4.

Las decisiones 1, 2 y 3 ya están comprobadas contra la librería instalada, `cryptography` 50.0.1: se genera el par en `secp256k1`, la firma verifica con la llave pública del emisor y falla con cualquier otra, el contenido alterado también falla, y el material privado no aparece en claro dentro del token cifrado (que sí descifra con la clave maestra y falla con otra).

## Cómo se corre (Windows, macOS, Linux)

1. Copiar `.env.example` a `.env` y completar credenciales y `MASTER_KEY`.
2. Levantar PostgreSQL 16: `docker compose up -d` o `podman compose up -d`. El esquema de `db/init.sql` se aplica en la primera creación del volumen.
3. Crear el génesis: `python -m src.bootstrap`.
4. Levantar la aplicación: `python -m src.web`.
5. Verificar la integridad desde el navegador: `GET /verificar`.

## Cómo se verifica

**Trazabilidad mecánica**: cada criterio de aceptación tiene al menos una prueba cuyo nombre empieza con `test_req_NN_`, y cada caso de uso tiene su prueba de recorrido completo. No hay que interpretar nada para saber si un requisito está cubierto: se busca su número en `tests/`.

**Coherencia de la explicación**: una prueba comprueba que los cinco casos de uso aparecen en el recorrido y que los 29 requerimientos aparecen en el nombre de al menos una prueba. La explicación no puede quedar huérfana sin que la suite lo diga.

**Pruebas de reglas sin base de datos** (REQ-17): la suite de `tests/unit/` corre con el contenedor apagado y sin `DATABASE_URL`. El dominio no importa el driver (REQ-16), lo que se comprueba importando el módulo del ledger en un intérprete limpio y verificando que `psycopg` no quedó cargado.

**Pruebas contra PostgreSQL** (`tests/integration/`): atomicidad de la agrupación (REQ-18), propagación cruda de los errores del motor (REQ-19), coherencia entre estado y bloque (REQ-12), y que la verificación no modifica ninguna fila (REQ-22, comparando el contenido de las tres tablas antes y después).

**La demostración central del proyecto** (REQ-10, objetivo específico tercero del eje): alterar a mano una transacción confirmada con `UPDATE` directo en la base y pedir la verificación, que debe señalar el bloque donde empieza la alteración. Vive como prueba de integración y además como procedimiento manual documentado, porque es lo que el eje promete demostrar.

**La capa que muestra los límites** (`src/sabotaje.py`): es el artefacto que muestra en una corrida lo que las pruebas afirman por separado, incluidos los tres casos que el sistema **no** detecta —cambiar la pública de una wallet, insertar una pendiente con firma inventada y truncar la cola—, cada uno con su porqué declarado como dato. No reemplaza a las pruebas: las pone a la vista, con la pausa que le deja a la persona mirar el navegador entre caso y caso.

**REQ-20 en el piso declarado**: la suite completa se corre una vez dentro de un contenedor `python:3.11`, que es el piso que declara el eje, montando el código en solo lectura. Correrla solo en el Python de este equipo no probaría REQ-20, porque aquí hay una versión más nueva. Ya está comprobado que ese intérprete es alcanzable: el contenedor `python:3.11-slim` se creó y arrancó por el socket del servicio de podman, y salió con código 0 al afirmar por dentro que su versión es 3.11. Como el sandbox no ve lo que el contenedor escribe dentro del workspace, el veredicto de esa corrida es el código de salida de `pytest`, no su informe.

### Definición de terminado

Se considera terminado cuando se cumplen las seis condiciones: la suite corre verde contra el clúster PostgreSQL nativo; corre verde contra PostgreSQL 16 en contenedor; corre verde dentro del contenedor `python:3.11`; el procedimiento manual de alteración se reprodujo y la verificación señaló el bloque alterado; la prueba de coherencia de la explicación pasa, con el recorrido cubriendo los cinco casos de uso; y no queda ningún archivo que no se pueda mapear a un REQ, a un CU, a la explicación de un proceso o a la ejecución del sistema.

**Verificación en el entorno de desarrollo del agente**: las pruebas de integración necesitan un PostgreSQL. En este equipo el CLI de podman no puede crear contenedores (el sandbox deja de solo lectura su runtime y su almacén, y no puede configurar los espacios de nombres de usuario), pero el servicio de podman responde por su socket y existe PostgreSQL 18.6 nativo. Ya está comprobado de punta a punta: se creó y arrancó por el socket un `postgres:16-alpine`, respondió como PostgreSQL 16.15, ejecutó un guion de inicialización montado por bind y se eliminó sin residuo. El ciclo rápido de desarrollo usará un clúster nativo temporal; la corrida de aceptación usará el contenedor 16, que es la versión que verá el grupo.

**Entorno de Python**: aquí no hay binario `pip`, pero `python -m ensurepip` funciona (pip 26.2.1) y PyPI responde. El entorno del proyecto es un `venv` dentro del workspace, creado y aprovisionado por el propio repo, sin depender de gestores del sistema.

## Estructura del repositorio y a qué sirve cada archivo

```text
README.md                             cómo correrlo en los tres sistemas y por dónde empezar a leer
compose.yaml                          PostgreSQL 16 (REQ-20, REQ-23)
.gitignore                            excluye .env, el entorno virtual y el material de referencia (REQ-21)
.env.example                          credenciales y MASTER_KEY (REQ-21)
pyproject.toml                        piso de Python, configuración de pytest y lint (REQ-20)
requirements.txt                      versiones fijas (REQ-23)
db/init.sql                           esquema del modelo relacional del eje (REQ-15)
src/domain/wallet.py                  Wallet: par de llaves, firma, cifrado (REQ-01, REQ-02)
src/domain/transaction.py             Transaction y TransactionStatus: is_valid() (REQ-02..06, REQ-11)
src/domain/block.py                   Block: calculate_hash() (REQ-07)
src/domain/blockchain.py              Blockchain: pool, agrupar, verificar, historial (REQ-06..14)
src/persistence/ports.py              protocolos de persistencia (REQ-16)
src/persistence/postgres.py           adaptadores PostgreSQL (REQ-16, REQ-19)
src/persistence/unit_of_work.py       unidad de trabajo (REQ-18)
src/persistence/factory.py            ensamblado del ledger
src/web/app.py                        Flask: las cinco rutas (REQ-24..29)
src/web/templates/                    una plantilla por caso de uso (REQ-24..29)
src/bootstrap.py                      génesis idempotente y datos de demostración (REQ-14)
src/sabotaje.py                       sabotaje guiado: verificación y demostración de los límites
tests/unit/test_req_NN_*.py           reglas, sin base de datos (REQ-17)
tests/integration/test_req_NN_*.py    atomicidad, esquema, coherencia, alteración (REQ-10..12, REQ-18, REQ-19, REQ-22)
tests/test_explicacion.py             coherencia entre el recorrido y los requerimientos
docs/recorrido-de-casos-de-uso.md     el camino real de cada caso de uso y las preguntas del tutor
docs/specs/                           este diseño
docs/plans/                           el plan de implementación
```

## Riesgos y límites conocidos

- **Brecha de versión**: el clúster nativo de este equipo es PostgreSQL 18.6 y el destino es 16. El DDL que usa el eje (`uuid-ossp`, `CHAR(64)`, expresiones regulares en CHECK, `NUMERIC(18,8)`) se comporta igual, pero se confirma con una corrida contra 16 antes de dar por terminado.
- **El eje no fija el algoritmo de cifrado** ni la curva: las decisiones 1 y 3 son mías y están declaradas arriba para que se puedan rechazar.
- **La wallet del fondo se identifica por convención**, no por un dato. Quien consulte la base sin leer el README no puede saber cuál es, y esta limitación viene del modelo relacional del eje, no de esta reconstrucción.
- **El riesgo de la explicación es la deriva**: un recorrido que se separa del código engaña más de lo que ayuda. Por eso los docstrings viven junto al código, las pruebas se llaman por requerimiento, y la prueba de coherencia falla si el recorrido pierde un caso de uso.
- **El eje afirma algo que no era cierto** al momento de escribirlo. Cuando el prototipo esté terminado y verificado, ese párrafo debería corregirse o confirmarse con evidencia; no es tarea de este repositorio, pero es la razón de existir del repositorio.

## Consultas resueltas durante el diseño

1. **Índice único sobre `signature`** (decisión 4): aprobado por los desarrolladores el 2026-10-10, con la comprobación repartida en dos capas: el dominio informa el motivo y el esquema garantiza la unicidad.
2. **Clave maestra** (decisión 3): clave `Fernet` en el entorno, `MASTER_KEY` en `.env.example`, nunca versionada.
3. **El eje en el repositorio** (decisión 12): no se copia; el README lo cita por nombre.
4. **Artefactos y comentarios para la sustentación** (2026-10-10): se aceptan como requisito, con la lista cerrada de la decisión 11 y la regla del comentario que explica el porqué.
