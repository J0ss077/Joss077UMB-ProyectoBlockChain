# Registro de la socialización y la demostración en vivo

Registro de la actividad de socialización y demostración en vivo del prototipo
transaccional basado en blockchain. Este archivo documenta qué se presentó y con qué
evidencias cuenta el repositorio; el acta y la grabación se completan en el apartado 6.

| Campo | Valor |
| --- | --- |
| Actividad | Socialización y demostración en vivo del proyecto |
| Proyecto | Joss077UMB-ProyectoBlockChain |
| Fecha | 19 de noviembre de 2026 |
| Modalidad | Demostración en vivo sobre el prototipo local |
| Prototipo presentado | Nodo único de un ledger transaccional con wallets, transacciones firmadas, bloques encadenados, verificación, auditoría y reparación |
| Documento de la entrega | [docs/entrega-final.md](../../entrega-final.md) |
| Estado del acta y la grabación | PENDIENTE de anexar (véase el apartado 6) |

## 1. Qué se presentó

La actividad cubrió los tres componentes que evalúa la entrega final:

1. **El prototipo final.** Se mostró la aplicación levantada en local sobre PostgreSQL:
   registro y aprobación de cuentas, wallet con par de llaves, envío firmado, pool de
   pendientes, agrupación en bloque encadenado, verificación de integridad, detección de
   una alteración hecha por fuera de la aplicación y reparación explícita desde el panel
   de auditoría. Los comandos de puesta en marcha están en el
   [README](../../../README.md), sección «Puesta en marcha».
2. **Las pruebas realizadas.** Se presentó la evidencia fresca del 19 de noviembre de
   2026: lint sin hallazgos (`All checks passed!`), suite completa en `525 passed,
   1 skipped` en 171,57 s y suite unitaria sin base en `158 passed, 1 skipped` en
   1,96 s. La salida literal está en
   [pruebas-finales-2026-11-19.txt](../pruebas-finales-2026-11-19.txt), y los
   requerimientos y casos de uso con su archivo de prueba, en la sección 2 de
   [docs/entrega-final.md](../../entrega-final.md).
3. **El servicio de Inteligencia Artificial.** Se mostraron sus dos componentes: la
   proyección del próximo mes con red neuronal, que aparece en la tarjeta de la página
   de estadísticas, y el ayudante en lenguaje natural, que en el entorno entregado
   responde con su guía local porque no hay proveedor externo configurado. La ficha de
   cinco puntos de cada componente está en la sección 3 de
   [docs/entrega-final.md](../../entrega-final.md); el detalle de la red está en
   [docs/red-neuronal.md](../../red-neuronal.md).

La fecha de la actividad coincide con la de la evidencia fresca de pruebas y con la de
las capturas del ayudante (11 y 23), tomadas ese mismo día.

## 2. Guion de la demostración

El guion completo, con las rutas y el resultado esperado de cada paso, es la sección 4 de
[docs/entrega-final.md](../../entrega-final.md). La secuencia presentada fue la
siguiente; todas las rutas y los comandos existen en el código y en el README.

### 2.1 Preparación

```text
docker compose up -d
.venv/bin/python -m src.bootstrap
.venv/bin/python -m src.historial_demo
.venv/bin/python -m src.demo_social
.venv/bin/python -m src.web
```

Se abre `http://127.0.0.1:5000`. Para mostrar la tarjeta de proyección la aplicación se
levanta con `.venv-tf/bin/python -m src.web`, porque TensorFlow vive en
`red_neuronal/requirements.txt` y no en el `requirements.txt` del proyecto.

### 2.2 Recorrido del usuario común

| Paso | Acción | Ruta | Qué se mostró |
| --- | --- | --- | --- |
| 1 | Registro de una cuenta nueva | `GET,POST /registrarme` | La cuenta queda pendiente de aprobación y no abre sesión (REQ-30) |
| 2 | Aprobación desde el administrador | `GET /admin/pendientes`, `POST /admin/pendientes/<id>/aprobar` | La aprobación crea la wallet y acredita el saldo de bienvenida en un bloque nuevo (REQ-33) |
| 3 | Ingreso de la cuenta | `GET,POST /ingresar` | Tablero con el saldo de bienvenida y el crédito confirmado |
| 4 | Envío a otra cuenta | `POST /mi-envio` | El envío queda en el pool y el saldo disponible baja |
| 5 | Historial del usuario | `GET /mi-historial` | La transacción con su estado y el dictamen de la cadena |
| 6 | Elección de wallet, si la cuenta tiene varias | `POST /mi-wallet` | La sesión opera con la wallet elegida de la propia cuenta (REQ-47) |
| 7 | Agenda de contactos | `GET /mis-contactos` | Contactos por nombre, con los movimientos en común (REQ-42) |
| 8 | Perfil, foto e idioma | `GET /perfil`, `POST /perfil/foto`, `POST /idioma` | Datos de la cuenta, foto opcional e interfaz en español o inglés (REQ-40, REQ-43) |
| 9 | Estadísticas de la cuenta | `GET /mis-estadisticas` | Gráficas, filtros y, con TensorFlow, la tarjeta «Proyección del próximo mes» |
| 10 | Ayudante en palabras simples | `GET /asistente` | «Lo que pasa ahora», preguntas sugeridas y respuesta de la guía local |

### 2.3 Recorrido del administrador

| Paso | Acción | Ruta | Qué se mostró |
| --- | --- | --- | --- |
| 11 | Cierre de la sesión del usuario e ingreso del administrador | `POST /salir`, `GET,POST /ingresar` | Sesión de administrador con su menú |
| 12 | Agrupación del pool en un bloque | `POST /bloques` | La transacción pendiente pasa a confirmada en un bloque nuevo (CU-03) |
| 13 | Verificación completa de la cadena | `GET /verificar` | Dictamen, panel de auditoría y estado del sello de vigilancia (CU-04) |
| 14 | Historial del usuario después del bloque | `GET /mi-historial` | La transacción confirmada con el índice del bloque que la agrupa (REQ-39) |
| 15 | Estadísticas desde el administrador | `GET /admin/estadisticas?usuario=<nombre>` | El administrador elige a qué usuario común mirar |

### 2.4 Alteración y reparación

Se presentó el argumento central del proyecto: toda modificación del historial es
detectable. Con la cadena válida y una sesión de administrador abierta en `/verificar`,
se ejecutó el recorrido guiado:

```text
.venv/bin/python -m src.sabotaje
```

El modo interactivo aplica cada alteración, espera a que la persona mire `/verificar`,
informa el veredicto, restaura y comprueba la vuelta. Los once casos incluyen los que el
motor rechaza y los límites declarados; los tres destructivos solo corren con
`--destructivos`. La alteración manual con SQL directo y las acciones de
`POST /verificar/reparar` (`reparar-todo`, `encadenar`, `aislar`,
`rechazar-pendientes`, `reagrupar` y `fijar-sello`) se explican en la sección 4.4 de
[docs/entrega-final.md](../../entrega-final.md).

### 2.5 Cierre

La sesión terminó con `http://127.0.0.1:5000/verificar` en «La cadena es válida»,
después de restaurar la alteración de la demostración. El apagado se hace con `Ctrl+C`
en la terminal de la aplicación y `docker compose down` conserva los datos, mientras
que `docker compose down -v` borra el volumen.

## 3. Cuentas de demostración

Las cuentas y las contraseñas usadas son las que documenta el
[README](../../../README.md), sección «Las cuentas de demostración». No se repiten aquí
credenciales que no estén ya publicadas:

| Usuario | Rol | Uso en la demostración |
| --- | --- | --- |
| `admin` | administrador | Aprobar altas, agrupar bloques, verificar y reparar la cadena |
| `asociado1` | usuario común | Cuenta con la que se tomaron las capturas 11 y 23 del ayudante |
| `constituyente`, `fondo`, `asociado2`, `asociado3` | usuario común | Datos sembrados para mostrar saldos, aportes, retiros e historial |

La contraseña de las cuentas comunes de demostración y la del administrador están en el
README y en el `.env` local, respectivamente; no se escriben en este archivo.

## 4. Evidencias de la actividad

### 4.1 Evidencias visuales del prototipo

| Evidencia | Qué muestra |
| --- | --- |
| [01-ingreso.png](../capturas/01-ingreso.png) | Pantalla de ingreso |
| [02-portada-admin.png](../capturas/02-portada-admin.png) | Portada del administrador con conteos, cadena y panel de wallets |
| [03-wallets.png](../capturas/03-wallets.png) | Registro y clave pública de una wallet |
| [05-bloques.png](../capturas/05-bloques.png) | Cierre de bloque con el pool en espera |
| [06-verificar.png](../capturas/06-verificar.png) | Dictamen de integridad (captura del 4 de noviembre; anterior al panel de auditoría) |
| [07-pendientes.png](../capturas/07-pendientes.png) | Cola de aprobación del administrador |
| [08-tablero-comun.png](../capturas/08-tablero-comun.png) | Tablero del usuario común |
| [14-flujo-wallet-creada.png](../capturas/14-flujo-wallet-creada.png) | Wallet recién registrada con su identificador |
| [15-flujo-transaccion-pool.png](../capturas/15-flujo-transaccion-pool.png) | Transacción en el pool |
| [16-flujo-bloque-creado.png](../capturas/16-flujo-bloque-creado.png) | Bloque creado y encadenado |
| [17-flujo-cadena-verificada.png](../capturas/17-flujo-cadena-verificada.png) | Cadena válida |
| [18-alteracion-detectada.png](../capturas/18-alteracion-detectada.png) | Alteración detectada con el bloque señalado |
| [19-alteracion-revertida.png](../capturas/19-alteracion-revertida.png) | Vuelta a la cadena válida |
| [20-consulta-psql.png](../capturas/20-consulta-psql.png) | Consulta de evidencia contra la base |
| [22-mis-contactos.png](../capturas/22-mis-contactos.png) | Agenda de contactos del usuario común |

### 4.2 Evidencias de las pruebas

| Evidencia | Qué demuestra |
| --- | --- |
| [pruebas-finales-2026-11-19.txt](../pruebas-finales-2026-11-19.txt) | Salida literal de ruff y de las dos corridas de pytest del 19 de noviembre de 2026, con el entorno, los comandos y el conteo por archivo |
| [junit.xml](../../pentesting/evidencias/kiwi/junit.xml) | JUnit de Kiwi TCMS: `tests=526, failures=0, errors=0, skipped=1` |
| [docs/entrega-final.md](../../entrega-final.md) | Tablas de CU-01 a CU-05 y REQ-01 a REQ-47 con su archivo de prueba y su resultado |

### 4.3 Evidencias del servicio de IA

| Evidencia | Qué muestra |
| --- | --- |
| [09-estadisticas-comun.png](../capturas/09-estadisticas-comun.png) | Estadísticas del usuario común con la tarjeta «Proyección del próximo mes» |
| [10-estadisticas-admin.png](../capturas/10-estadisticas-admin.png) | Estadísticas desde el administrador con la proyección |
| [11-asistente.png](../capturas/11-asistente.png) | El ayudante con «Lo que pasa ahora», preguntas sugeridas y una respuesta de la guía local (19 de noviembre) |
| [23-asistente-conversacion.png](../capturas/23-asistente-conversacion.png) | Conversación del ayudante con pregunta escrita y respuesta, en modo guía local (19 de noviembre) |
| [red-neuronal-general.png](../../figuras/red-neuronal-general.png) | Figura 1: la red de la proyección, 8 → 8 → 2 |
| [red-neuronal-capas.png](../../figuras/red-neuronal-capas.png) | Figura 2: un mes de ejemplo capa por capa |
| [red-neuronal-entrenamiento.txt](../red-neuronal-entrenamiento.txt) | Salida cruda del entrenamiento del modelo de la proyección |
| [docs/red-neuronal.md](../../red-neuronal.md) | Apartado completo de la red: dataset, métricas, límites y reproducción |

### 4.4 Evidencias de seguridad

| Evidencia | Qué contiene |
| --- | --- |
| [informe.md](../../pentesting/informe.md) / [informe.pdf](../../pentesting/informe.pdf) | Informe de pentesting con la metodología, los cuatro hallazgos y su remediación |
| [matriz-trazabilidad.md](../../pentesting/matriz-trazabilidad.md) | Trazabilidad de requerimientos, pruebas funcionales y categorías de OWASP |

## 5. Relación con el cronograma

La actividad corresponde a la actividad 27 del
[presupuesto y cronograma](../../presupuesto-y-cronograma.md): «Entrega final y
sustentación del proyecto», cerrada el 19 de noviembre de 2026. El mismo documento deja
constancia de que la grabación y el acta todavía no se anexan.

## 6. Acta y grabación

**Estado: PENDIENTE.** La demostración se realizó en vivo, pero el acta y la grabación
no están anexadas al repositorio. Los campos de la tabla siguiente se completan a mano
cuando el equipo los tenga; mientras digan PENDIENTE no debe afirmarse que el acta o el
video existen.

| Campo del acta | Valor |
| --- | --- |
| Fecha y hora exacta de la actividad | PENDIENTE |
| Duración | PENDIENTE |
| Modalidad y lugar o enlace de la sesión | PENDIENTE |
| Integrantes del equipo que sustentaron | PENDIENTE |
| Enlace a la grabación | PENDIENTE |
| Ruta del archivo de la grabación, si se guarda en el repositorio | PENDIENTE |
| Acta firmada (ruta o enlace) | PENDIENTE |
| Observaciones y compromisos | PENDIENTE |

### 6.1 Lista de asistencia

Se diligencia con los nombres de quienes participaron en la actividad. La columna de
asistencia se marca como «Asistió», «No asistió» o «Excusa»; las filas se agregan o se
quitan según el caso.

| Nombre | Rol en el equipo | Asistencia | Firma |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |

### 6.2 Instructivo para completar el registro

1. Reunir la grabación de la sesión y el acta firmada. Si la grabación se guarda en el
   repositorio, crear la carpeta correspondiente y anotar aquí la ruta relativa; si se
   aloja en un servicio externo, pegar el enlace y comprobar que sea accesible para
   quien evalúa. No se versionan videos pesados: conviene enlazarlos.
2. Completar la tabla del apartado 6 con la fecha y hora exactas, la duración, la
   modalidad, los integrantes y las observaciones. Reemplazar cada PENDIENTE por el dato
   real.
3. Diligenciar la lista de asistencia del apartado 6.1 y, si hay acta firmada, anotar su
   ruta o enlace en la tabla del apartado 6.
4. Actualizar el enlace de este registro en la sección 6 de
   [docs/entrega-final.md](../../entrega-final.md) para que quede marcado como cerrado.
5. No escribir credenciales, claves ni datos personales en este archivo. Si el acta
   incluye datos de contacto, se guarda como documento aparte y se referencia.

## 7. Declaración de alcance

La socialización y la demostración en vivo se realizaron el 19 de noviembre de 2026
sobre el prototipo local, con el guion de la sección 2. Este archivo es el registro de la
actividad y reúne las evidencias visuales y de pruebas que la respaldan. El repositorio
no contiene la grabación ni el acta firmada: esos dos elementos están declarados como
PENDIENTES en el apartado 6 y no deben presentarse como si existieran. La entrega del
prototipo, de las pruebas y del servicio de IA se sostiene con la evidencia enlazada en
este registro y en [docs/entrega-final.md](../../entrega-final.md).
