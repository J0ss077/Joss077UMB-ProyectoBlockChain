# Proceso de construcción y alcance

Cómo se llegó al prototipo que está en este repositorio, qué se entregó en cada etapa, y
qué queda explícitamente afuera. Es el complemento de
[arquitectura-y-decisiones.md](arquitectura-y-decisiones.md): acá está el recorrido, allá
están las decisiones.

## 1. Las etapas

| Etapa | Qué se entregó | Cómo se supo que estaba |
| --- | --- | --- |
| 1. Núcleo del dominio | `Wallet`, `Transaction`, `Block`, `Blockchain` y los estados; firma, validación y hash | Pruebas unitarias por requerimiento, sin base de datos (`REQ-17`) |
| 2. Persistencia | Esquema en `db/init.sql`, adaptadores PostgreSQL detrás de protocolos y unidad de trabajo atómica | Pruebas de integración contra PostgreSQL, incluida la atomicidad de la agrupación (`REQ-18`) |
| 3. Las cinco rutas | `POST /wallets`, `POST /transacciones`, `POST /bloques`, `GET /verificar` y `GET /historial/<wallet>` | Pruebas de rutas y guarda de que la presentación no toca el motor (`REQ-29`) |
| 4. Arranque y demostración | `python -m src.bootstrap`: génesis idempotente, datos del caso del eje y cuentas | El arranque se corre dos veces y no duplica nada |
| 5. Usuarios y roles | Registro moderado, aprobación, ingreso y sesión | Diez requerimientos nuevos (`REQ-30` a `REQ-39`), cada uno con su prueba |
| 6. Perfil, contactos, fotos e idioma | Perfil de la cuenta, foto, agenda de contactos, solicitud de cambio de contraseña e interfaz en español o inglés | `REQ-40` a `REQ-43`, cada uno con su prueba |
| 7. El ayudante | Guía local que responde sin red y, con `ASISTENTE_API_KEY`, un modelo externo en sólo lectura | `REQ-44` y `REQ-45`: sólo consulta y no expone datos de otras cuentas |
| 8. Interfaz | Sistema de diseño «Bloques», tema claro y oscuro, navegación por rol, mensajes de éxito y de error | Capturas de todas las pantallas y pruebas de navegación |
| 9. Fase 4 | Estadísticas con filtros y gráficas, proyección del próximo mes con red neuronal, manejo del error de conexión y evidencias | 22 capturas en esa etapa (hoy son 28), pruebas de navegación, de conexión, de estadísticas y de la proyección |
| 10. Wallet con dueño y varias wallets | La propiedad pasa de `users` a `wallets.owner_id`; el registro pregunta el dueño y el tablero elige con qué wallet se opera | `REQ-46` y `REQ-47`, y la suite corrida sobre el esquema nuevo |
| 11. Auditoría, sello y reparación | Auditoría completa del estado, sello de vigilancia externo, panel en `/verificar` y `POST /verificar/reparar` | Pruebas de auditoría, de sello, de reparación y de persistencia de la reparación |
| 12. Pentest | OWASP WSTG v4.2 sobre las fases de PTES, en una instancia local aislada, con triaje e informe | [informe.md](pentesting/informe.md): cuatro hallazgos abiertos con remediación propuesta |
| 13. Entrega final | Consolidación del acceso local, la evidencia fresca de la suite y las capturas del ayudante | [entrega-final.md](entrega-final.md) y la corrida del 19 de noviembre de 2026 |

El orden no fue casual: cada etapa se apoyó en la anterior y ninguna avanzó sin sus
pruebas. La etapa 5 agregó `users` sin tocar las tres tablas originales del eje; la 6
sumó `contactos`, `solicitudes_de_contrasena` y `fotos_de_perfil`, y la 7 el módulo del
ayudante. Las etapas 10 y 11 no agregaron tablas al eje: movieron la propiedad a
`wallets.owner_id` y sumaron la lectura completa de la cadena sin escribir en ella.

## 2. Cómo se verifica

- **Los requerimientos**: hay **47** (`REQ-01` a `REQ-47`), numerados en bloques: los
  **29 del eje** (`REQ-01` a `REQ-29`), los **diez del sistema de usuarios** (`REQ-30` a
  `REQ-39`), los seis de perfil, contactos, fotos, idioma y ayudante (`REQ-40` a `REQ-45`)
  y los dos de wallet con dueño y varias wallets (`REQ-46` y `REQ-47`).
- **Las pruebas numeradas se llaman por requerimiento** (`test_req_NN_*`) y llevan el
  criterio de aceptación en el docstring: para explicar una regla alcanza con mostrar la
  prueba que la demuestra. Hoy son **525** en la suite completa (más una omitida, la del
  dataset, que se salta cuando no está `pandas`) y **158** en la suite unitaria sin base.
- **Las de perfil y funciones agregadas** viven en archivos con nombre de función
  (`test_perfil.py`, `test_foto.py`, `test_contactos.py`, `test_idioma.py`,
  `test_asistente.py`), además de los `test_req_46_*` y `test_req_47_*`.
- **La evidencia literal** de la corrida del 19 de noviembre de 2026 está en
  [evidencias/pruebas-finales-2026-11-19.txt](evidencias/pruebas-finales-2026-11-19.txt):
  lint sin hallazgos, suite completa y suite unitaria, con el entorno y el commit
  auditado. La cifra vieja de 386 pruebas, que quedó en `docs/evidencias/pruebas.txt` y en
  la evidencia de la Fase 4, es del 4 de noviembre y está desactualizada.
- **Las guardas automáticas** sostienen la arquitectura: una falla si la presentación nombra
  el motor o la capa de datos, y otra si el dominio importa `psycopg`.
- **La herramienta de sabotaje** (`python -m src.sabotaje`) muestra en una sola corrida qué
  detecta la cadena y qué no, incluidos los límites declarados.
- **La prueba de coherencia** falla si el recorrido de casos de uso deja de nombrar un caso o
  un requerimiento.
- **El recorrido de demostración** (`docs/recorrido-de-casos-de-uso.md`) es el camino real de
  cada caso de uso: ruta, método del dominio, tabla y consulta.
- **El pentest** se ejecutó aparte, sobre una instancia local desechable y con su propio
  stack: el resultado y los hallazgos están en
  [pentesting/informe.md](pentesting/informe.md) y la trazabilidad con las pruebas
  funcionales, en [pentesting/matriz-trazabilidad.md](pentesting/matriz-trazabilidad.md).

## 3. Lo que no entra

Está declarado para que no se lea como olvido:

- Cambio de contraseña sin aprobación, baja o suspensión de usuarios, y bitácora de lo que
  hace el administrador.
- Correo electrónico, recuperación de contraseña, verificación por correo y doble factor.
- Que la persona custodie su llave privada.
- Protección CSRF y límite de intentos de ingreso.
- Migraciones de esquema.
- Nodos pares, consenso, minado o cualquier forma de red.
- Un despliegue público: el acceso es local y reproducible, con los comandos del `README.md`.
- Corregir los hallazgos del pentest: el alcance fue evaluar y quedan abiertos con
  remediación propuesta.
- Que la proyección sea una medición: es una estimación entrenada con un dataset generado
  por reglas explícitas.

## 4. Riesgos conocidos

| Riesgo | Qué se hizo |
| --- | --- |
| El clúster del equipo es PostgreSQL 18 y el destino es 16 | El esquema se validó contra 16 en contenedor: `uuid-ossp`, `CHAR(64)`, los CHECK con expresiones regulares y `NUMERIC(18,8)` se comportan igual |
| La explicación se separa del código | Los docstrings viven junto al código, las pruebas se llaman por requerimiento y la prueba de coherencia falla si el recorrido pierde un caso |
| La cadena crece con cada aprobación (un bloque por saldo de bienvenida) | La verificación es lineal en bloques; una medición informal (no versionada como banco reproducible) dio del orden de 1,4 ms con 4 bloques y 84 ms con 1.000. Es una estimación declarada, no una medición reproducible |
| La proyección se apoya en un dataset generado con reglas explícitas | Lo dice `docs/red-neuronal.md` y las cifras de la tarjeta salen de `resultados.json`; con historial real se reentrena |
| El recorte de la cola deja una cadena internamente coherente | El sello de vigilancia, un archivo firmado fuera de la base, lo delata si se fijó antes del recorte; sin sello previo no se detecta |
| El pentest deja cuatro hallazgos abiertos | El alcance fue evaluar, no corregir; el informe los deja con remediación propuesta y procedimiento de retest ([pentesting/informe.md](pentesting/informe.md)) |

## 5. Por dónde empezar a leer

1. `README.md`: qué es, cómo se instala y cómo se corre.
2. `docs/arquitectura-y-decisiones.md`: las capas y por qué cada decisión.
3. `db/init.sql`: el esquema completo, con sus CHECK e índices.
4. `docs/recorrido-de-casos-de-uso.md`: el camino de cada caso de uso.
5. `src/domain/`: las reglas, que es donde está lo interesante del proyecto.
6. `tests/`: la explicación ejecutable, requerimiento por requerimiento.
7. `docs/red-neuronal.md` y `docs/presupuesto-y-cronograma.md`: la red de la proyección y
   los números del proyecto.
8. `docs/pentesting/informe.md`: el pentest, sus hallazgos y su alcance.
9. [entrega-final.md](entrega-final.md): el acceso, la evidencia de la entrega y lo que
   queda pendiente antes de entregar.
