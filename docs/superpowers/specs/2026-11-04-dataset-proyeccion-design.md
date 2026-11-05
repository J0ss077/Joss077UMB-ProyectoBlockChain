# Dataset de la proyección del próximo mes — diseño

Fecha: 2026-11-04

## Para qué

La tarjeta «Proyección del próximo mes» de la página de estadísticas usa una red de
TensorFlow (`red_neuronal/`) que hoy se entrena con **una sola serie sintética de 240
meses generada en memoria** (`red_neuronal/serie.py`): 238 ejemplos y ningún archivo
de datos. Por eso la tarjeta dice «modelo de demostración» y «entrenada con datos
sintéticos… no para predecir el dinero real».

El usuario quiere que el profesor abra la carpeta del dataset y piense «qué buen
dataset»: **muchos datos, limpios, normalizados, documentados**, entregado en CSV, JSON
y otros formatos, todo dentro del repositorio. La red se reentrena con ese dataset y la
interfaz deja de presentarla como demostración.

## Decisiones del usuario

1. **Los datos los genera Claude** con una simulación de un fondo de empleados (no se usa
   un dataset público como Berka).
2. **En la interfaz no aparece «simulado» ni «sintético» ni «demostración».** El texto
   nuevo es neutro y cierto, del estilo: *«Lo estima una red neuronal (TensorFlow)
   entrenada con el dataset del proyecto: N cuentas y N meses de movimientos.»* La
   interfaz tampoco dice que los datos sean reales.
3. **La documentación del dataset sí dice que es una simulación** reproducible (semilla
   fija, generador incluido). Esto fue parte del trato.
4. **Todo el dataset va en el repositorio**, no sólo una muestra.

## Objetivos

- Una carpeta `dataset/` en la raíz que se vea profesional: capas claras (crudo →
  limpio → agregado → listo para el modelo), un README propio, un diccionario de datos,
  un reporte de calidad y el generador que la reproduce.
- Volumen grande: del orden de **1.500 cuentas, 8 años (96 meses) y ~800.000
  transacciones**, que dan más de 100.000 ejemplos para la red (hoy son 238). El número
  exacto lo ajusta el builder para respetar el límite de tamaño de archivo (ver
  restricciones).
- Cada tabla en **CSV, JSON, Parquet** y, además, el dataset completo en una base
  **SQLite**; las tablas chicas (cuentas, diccionario, métricas y la vista mensual si
  cabe) también en **Excel (.xlsx)**.
- La red se entrena desde los archivos del dataset y reporta su error en un conjunto de
  prueba que nunca vio.
- La tarjeta de la interfaz cambia su texto según la decisión 2.

## No objetivos

- No se usan datos reales ni se afirma en ningún lugar que lo sean.
- La aplicación no lee el dataset en tiempo de ejecución: sigue cargando sólo el modelo
  `.keras` y calculando las características desde el historial de la wallet.
- No se toca el ledger, la cadena de bloques ni los datos de demostración de la base
  (`src/historial_demo.py`).
- No se cambia la arquitectura que pide la actividad (8 entradas → 8 ocultas ReLU → 2
  salidas lineales); sí se puede agregar una capa de normalización al inicio.

## Anti-objetivos (fallaría aunque funcione)

- Un archivo de más de 100 MB: GitHub lo rechaza y el repositorio no se puede subir.
- La interfaz diciendo «datos reales», o el README del dataset escondiendo que es
  simulado.
- Que las características con las que se entrena se calculen distinto de como las
  calcula la aplicación (desfase entre entrenamiento y uso). Hoy `serie.ejemplos()`
  reimplementa a mano lo que hace `caracteristicas.vector()`; el dataset nuevo debe
  usar **la misma función** que usa la aplicación.
- Un dataset «limpio» sin evidencia de limpieza: si no se ve qué se limpió, no
  impresiona.
- Un dataset que cambie en cada corrida: la semilla es fija y dos corridas dan archivos
  idénticos.

## Restricciones

- Ningún archivo del repositorio supera **50 MB** (GitHub advierte desde 50 MB y rechaza
  desde 100 MB). Para la tabla grande se parte por año
  (`transacciones_2019.csv`, …) en CSV y JSON; Parquet y SQLite pueden ir enteros si
  caben.
- Excel tiene un tope de 1.048.576 filas por hoja: las transacciones no van en Excel.
- El generador y el entrenamiento corren con `.venv-tf` (Python con TensorFlow 2.22 y
  numpy ya instalados). Si hace falta pandas, pyarrow u openpyxl, se agregan a
  `red_neuronal/requirements.txt` (o a un `dataset/requirements.txt`), no al
  `requirements.txt` de la aplicación.
- Textos, nombres de columnas y comentarios en español, con el estilo del resto del
  repositorio (docstrings que explican el porqué).
- No hacer commits, push ni cambios de rama (preferencia del usuario).
- `pytest` sin `TEST_DATABASE_URL` vacía la base de desarrollo: sólo correr
  `tests/unit` y pruebas que no toquen la base.

## Cómo se arma (lo decidido)

### Estructura propuesta de `dataset/`

```
dataset/
  README.md                 qué es, cómo se generó (simulación, semilla), cómo se usa
  diccionario_de_datos.md   cada columna: tipo, unidad, rango, significado
  diccionario_de_datos.{csv,json,xlsx}
  reporte_de_calidad.md     nulos, duplicados, rangos y outliers antes y después de limpiar
  reporte_de_calidad.json
  generar.py                el generador (python -m dataset.generar)
  crudo/                    las transacciones como "salen del sistema", con defectos
  limpio/                   transacciones y cuentas ya validadas
  agregado/                 una fila por cuenta y mes
  modelo/                   las 8 características + 2 objetivos, partidas en
                            entrenamiento / validación / prueba, y las estadísticas
                            de normalización
  fondo.sqlite              todas las tablas en una sola base
```

Los nombres exactos de archivos y subcarpetas los decide el builder; la idea de capas,
no.

### Las capas

1. **Cuentas** (dimensión): identificador, perfil de comportamiento, fecha de alta,
   rango de ingreso, etc. Los perfiles se inspiran en los de `src/historial_demo.py`
   (ahorrador, frecuente con montos chicos, esporádico de montos grandes, con primas en
   junio y diciembre, que se endeuda y paga en cuotas, que se retira del fondo…) más
   variación dentro de cada perfil, para que no haya dos cuentas iguales.
2. **Crudo:** las transacciones con defectos realistas y en proporción baja y
   documentada: duplicados, nulos en campos no críticos, montos con formato
   inconsistente, fechas en otra zona horaria, montos negativos o cero, cuentas
   inexistentes. Existe para que la limpieza se vea.
3. **Limpio:** las mismas transacciones validadas, con tipos correctos, en UTC, sin
   duplicados. Cada regla de limpieza queda en el reporte de calidad con cuántas filas
   afectó.
4. **Agregado mensual:** por cuenta y mes, lo recibido, lo enviado, el número de
   movimientos, el saldo de cierre y el mes del año.
5. **Modelo:** por cuenta y fecha de corte, las ocho características de
   `red_neuronal/caracteristicas.CAMPOS` calculadas con
   `caracteristicas.vector(...)` (la misma función que la aplicación) sobre las
   transacciones limpias hasta ese corte, más los dos objetivos (lo recibido y lo
   enviado en los 30 días siguientes, como proporción de la escala) y la escala para
   volver a pesos. La partición es **temporal**: los primeros años son entrenamiento,
   el siguiente tramo validación y el último prueba.

### «Normalizado»

- Las características ya son proporciones acotadas por diseño
  (`caracteristicas.py`); se mantienen así porque la aplicación las arma igual.
- Además se publican las estadísticas de estandarización (media y desviación por
  característica, calculadas **sólo con el conjunto de entrenamiento**) en un archivo
  del dataset, y la red incorpora esa estandarización como una capa
  `tf.keras.layers.Normalization` al inicio. Así la aplicación no cambia: le sigue
  pasando las ocho proporciones y el modelo estandariza adentro.
- En el agregado y el limpio, «normalizado» también se entiende en el sentido de base
  de datos: cuentas en una tabla, transacciones en otra, sin columnas repetidas.

### Entrenamiento

- `red_neuronal/entrenar.py` lee los archivos de `dataset/modelo/` en lugar de llamar a
  `serie()`. `serie.py` deja de ser la fuente (el builder decide si se borra o queda
  como referencia).
- Se reporta el error en pesos sobre **prueba** (no sólo validación), comparado con las
  dos predicciones ingenuas que ya existen (mes anterior y promedio).
- `red_neuronal/resultados.json` y el modelo `.keras` se regeneran; también las figuras
  de `red_neuronal/figuras.py` si dependen de la serie.

### Interfaz

- `src/web/templates/estadisticas.html`: se quita la píldora «modelo de demostración» y
  se reemplaza la frase de ayuda por el texto neutro de la decisión 2, con las cifras
  reales del dataset (cuentas y meses), idealmente leídas de `resultados.json` para que
  no queden desactualizadas.
- `src/web/traducciones.py`: las traducciones al inglés de los textos nuevos.

### Documentación

- `docs/red-neuronal.md` y el `README.md` raíz se actualizan: de dónde salen los datos,
  cuántos son, cómo regenerarlos, y las métricas nuevas. Ahí también se dice que el
  dataset es simulado.

## Decisiones de Claude (revisar)

- **Escala de los montos:** los montos simulados están en la misma escala que las
  wallets de demostración (de decenas a unas decenas de miles de pesos), porque la
  aplicación corre el modelo sobre esas wallets. El plan incluye una verificación que
  corre `src/web/proyeccion.proyectar` sobre las wallets sembradas por
  `src/historial_demo.py` y revisa que las cifras sean plausibles (no negativas, del
  orden de lo que esas cuentas mueven al mes).
- **Métricas sin maquillar:** los parámetros de la simulación se fijan antes de
  entrenar y **no** se ajustan mirando el error de prueba. Las cifras contra las dos
  predicciones ingenuas se reportan como salgan; si el modelo pierde en alguna salida,
  se dice en `docs/red-neuronal.md`.
- **Presupuesto de tamaño (decisión del usuario):** volumen completo (~800.000
  transacciones) y todas las capas en todos los formatos, aunque la carpeta pese
  alrededor de 0,5 GB. Sigue valiendo el tope de 50 MB por archivo, así que la base
  SQLite también se parte (por ejemplo, una por capa o por año) si no cabe.

## Lo que queda al builder

- Cantidades exactas (cuentas, años, transacciones) dentro del límite de tamaño.
- Los perfiles concretos, sus parámetros y la tasa de cada defecto en la capa cruda.
- Librerías para escribir Parquet y Excel (pyarrow, openpyxl o lo que ya esté).
- Si el JSON grande va como JSON Lines o como arreglo; la frecuencia de las fechas de
  corte (fin de mes, cada 15 días…).
- Si se agregan figuras del dataset (distribuciones, correlaciones) al reporte.
- Las pruebas unitarias: como mínimo, que el generador sea determinista, que el limpio
  no tenga duplicados ni nulos críticos, y que las características del dataset
  coincidan con `caracteristicas.vector()` para una cuenta de ejemplo.
