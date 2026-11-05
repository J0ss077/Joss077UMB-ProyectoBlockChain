# Dataset de la proyección — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar un dataset simulado grande y documentado en `dataset/` (CSV, JSON, Parquet, Excel, SQLite), reentrenar con él la red de `red_neuronal/` y quitar de la interfaz la etiqueta de demostración.

**Architecture:** Un paquete `dataset/` con un módulo por capa (perfiles → crudo → limpio → agregado/modelo → exportación → documentación) y un orquestador `python -m dataset.generar`. Las características del modelo se calculan con `red_neuronal.caracteristicas.vector`, la misma función que usa la aplicación. `red_neuronal/entrenar.py` lee `dataset/modelo/` y el modelo incorpora una capa `Normalization`.

**Tech Stack:** Python 3.14 en `.venv-tf` (TensorFlow 2.22rc0, numpy 2.5), pandas, pyarrow, openpyxl, sqlite3 de la biblioteca estándar, pytest.

**Spec:** `docs/superpowers/specs/2026-11-04-dataset-proyeccion-design.md`

## Global Constraints

- Ningún archivo supera **50 MB**; lo que no cabe se parte por año (`*_AAAA.*`).
- Volumen objetivo: **~1.500 cuentas, 96 meses, ~800.000 transacciones**; todas las capas en CSV, JSON (JSON Lines), Parquet y SQLite; Excel sólo para tablas de menos de 1.048.576 filas.
- Semilla fija `SEMILLA = 2026`: dos corridas producen archivos idénticos byte a byte (CSV/JSON).
- La interfaz no dice «simulado», «sintético», «demostración» ni «datos reales». La documentación de `dataset/` sí dice que es una simulación reproducible.
- Montos en la escala de las wallets de demostración (decenas a decenas de miles de pesos), dos decimales.
- Los parámetros de la simulación no se ajustan mirando el error de prueba; las métricas se reportan como salgan.
- Arquitectura 8 → 8 (ReLU) → 2 lineal; se permite una capa `Normalization` al inicio.
- Dependencias nuevas sólo en `red_neuronal/requirements.txt`, nunca en `requirements.txt`.
- Español en nombres, columnas, docstrings y comentarios (estilo del repo: explican el porqué).
- **Sin commits, push ni cambios de rama** (preferencia del usuario): los pasos de commit de esta plantilla se reemplazan por «revisar `git status`».
- Pruebas: sólo `tests/unit` (sin `TEST_DATABASE_URL`, el resto vacía la base de desarrollo). Las del dataset corren con `.venv-tf/bin/python -m pytest`.

## Review Focus

- Una cuenta sin movimientos en los últimos 60 días al momento de corte → características finitas (sin NaN ni inf) y ejemplo válido o descartado con regla documentada.
- Un mes con lo recibido en 0 → la escala cae en `max(saldo, 1)` igual que en la app; los objetivos no explotan.
- Cuentas que se retiran del fondo (dejan de operar) → no generan ejemplos después de su baja.
- Un defecto del crudo que la limpieza no conoce → el reporte de calidad lo cuenta en «descartadas por otra causa» en vez de pasarlo al limpio.
- Proyección sobre las wallets sembradas por `src/historial_demo.py` → cifras ≥ 0 y del orden de lo que esa cuenta mueve al mes.

---

## File Structure

| Archivo | Responsabilidad |
| --- | --- |
| `dataset/__init__.py` | Docstring con el mapa del paquete (como `red_neuronal/__init__.py`) |
| `dataset/configuracion.py` | `Configuracion` (cuentas, meses, fecha de fin, semilla, tasas de defectos) y `COMPLETA` / `PEQUENA` |
| `dataset/perfiles.py` | Perfiles y generación de cuentas y transacciones «verdaderas» |
| `dataset/crudo.py` | Inyecta defectos documentados → tabla cruda (todo texto) |
| `dataset/limpieza.py` | Reglas de limpieza → tabla limpia + conteos por regla |
| `dataset/agregado.py` | Mensual por cuenta y ejemplos del modelo (usa `vector`) + partición + estadísticas de normalización |
| `dataset/exportar.py` | Escribe una tabla en todos los formatos, partiendo por año si supera 50 MB |
| `dataset/documentar.py` | Diccionario de datos, reporte de calidad y README del dataset |
| `dataset/generar.py` | Orquestador `main()` |
| `dataset/README.md`, `diccionario_de_datos.*`, `reporte_de_calidad.*`, `crudo/`, `limpio/`, `agregado/`, `modelo/`, `sqlite/` | Salidas generadas |
| `tests/unit/test_dataset.py` | Pruebas con `PEQUENA` (se saltan si falta pandas) |
| `red_neuronal/entrenar.py`, `modelo.py`, `figuras.py`, `__init__.py`, `requirements.txt` | Entrenar desde el dataset; `serie.py` se borra |
| `src/web/proyeccion.py`, `templates/estadisticas.html`, `traducciones.py`, `estadisticas.py` | Texto nuevo de la tarjeta |
| `docs/red-neuronal.md`, `README.md` | Documentación |

---

### Task 1: Dependencias y configuración

**Files:**
- Modify: `red_neuronal/requirements.txt`
- Create: `dataset/__init__.py`, `dataset/configuracion.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Configuracion: cuentas: int; meses: int; fin: date; semilla: int; tasa_duplicados: float; tasa_nulos: float; tasa_formato: float; tasa_zona: float; tasa_invalidos: float`; constantes `COMPLETA = Configuracion(cuentas=1500, meses=96, fin=date(2026, 10, 31), semilla=2026, ...)` y `PEQUENA` (20 cuentas, 14 meses, misma fecha y semilla). Tasas de defectos de mi elección, entre 0,2 % y 1,5 % cada una. `fin` fijo (no `now()`) para que sea reproducible.

- [ ] **Step 1:** Agregar `pandas`, `pyarrow`, `openpyxl` (versiones exactas que instale pip hoy) a `red_neuronal/requirements.txt` y correr `.venv-tf/bin/python -m pip install -r red_neuronal/requirements.txt`. Esperado: `import pandas, pyarrow, openpyxl` sin error.
- [ ] **Step 2:** Crear `configuracion.py` y el docstring de `dataset/__init__.py` (qué capas hay, que es una simulación reproducible, cómo se regenera).
- [ ] **Step 3:** `.venv-tf/bin/python -c "from dataset.configuracion import COMPLETA, PEQUENA"` sin error.

### Task 2: Perfiles, cuentas y transacciones verdaderas

**Files:**
- Create: `dataset/perfiles.py`
- Test: `tests/unit/test_dataset.py`

**Interfaces:**
- Consumes: `Configuracion`.
- Produces: `generar_cuentas(conf) -> pandas.DataFrame` con columnas `cuenta_id (str "C00001")`, `perfil (str)`, `fecha_alta (date)`, `fecha_baja (date | NaT)`, `ingreso_mensual (float)`, `ciudad (str)`, `edad (int)`; `generar_transacciones(conf, cuentas) -> DataFrame` con `transaccion_id (str "T0000001")`, `fecha (datetime UTC)`, `cuenta_origen`, `cuenta_destino`, `monto (float, 2 decimales, > 0)`, `tipo (str: aporte | retiro | transferencia | prima | prestamo | cuota)`, `canal (str)`. La cuenta especial `FONDO` es la contraparte de aportes y retiros.
- Perfiles (al menos 6): ahorrador, frecuente, esporádico, con primas jun./dic., endeudado que paga en cuotas, que se retira del fondo. Cada cuenta varía sus parámetros alrededor de los del perfil. Cada transacción de salida respeta el saldo de la cuenta en ese momento (se recorta como en `src/historial_demo._mover`).

- [ ] **Step 1: Pruebas que fallan**

```python
pd = pytest.importorskip("pandas")
from dataset.configuracion import PEQUENA
from dataset import perfiles

def test_el_generador_es_determinista():
    a = perfiles.generar_transacciones(PEQUENA, perfiles.generar_cuentas(PEQUENA))
    b = perfiles.generar_transacciones(PEQUENA, perfiles.generar_cuentas(PEQUENA))
    pd.testing.assert_frame_equal(a, b)

def test_ninguna_cuenta_queda_en_negativo():
    # saldo acumulado por cuenta (sin FONDO) ordenado por fecha nunca < 0
    ...

def test_no_hay_movimientos_despues_de_la_baja_ni_antes_del_alta(): ...
def test_hay_al_menos_seis_perfiles_y_montos_en_escala():  # 1 <= monto <= 50_000
```

- [ ] **Step 2:** `.venv-tf/bin/python -m pytest tests/unit/test_dataset.py -q` → FAIL (módulo no existe).
- [ ] **Step 3:** Implementar `perfiles.py` con `numpy.random.default_rng(conf.semilla)`; generar por cuenta y mes, saldo llevado en un dict.
- [ ] **Step 4:** Pruebas → PASS.

### Task 3: Capa cruda y limpieza

**Files:**
- Create: `dataset/crudo.py`, `dataset/limpieza.py`
- Test: `tests/unit/test_dataset.py`

**Interfaces:**
- Consumes: `generar_transacciones`, `Configuracion`.
- Produces: `ensuciar(transacciones, conf) -> DataFrame` (todas las columnas como texto; defectos: filas duplicadas, `canal` nulo, montos con coma decimal o símbolo `$`, fechas con offset `-05:00` en vez de UTC, montos 0 o negativos, `cuenta_destino` inexistente); `limpiar(crudo, cuentas) -> tuple[DataFrame, dict[str, int]]` que devuelve el limpio con los tipos de Task 2 y `{"regla": filas_afectadas}` con las claves `duplicados_eliminados`, `canal_imputado`, `monto_normalizado`, `fecha_convertida_a_utc`, `monto_invalido_descartado`, `cuenta_inexistente_descartada`, `descartadas_por_otra_causa`.

- [ ] **Step 1: Pruebas que fallan** — `test_el_limpio_no_tiene_duplicados_ni_nulos`, `test_cada_regla_cuenta_lo_que_inyecto_el_crudo` (conteo de duplicados del reporte == duplicados inyectados), `test_el_limpio_recupera_las_transacciones_validas` (las transacciones verdaderas sin las descartadas a propósito coinciden con el limpio, comparando por `transaccion_id`, monto y fecha).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar. Los descartes a propósito (monto inválido, cuenta inexistente) se inyectan como filas **nuevas**, no corrompiendo filas verdaderas, para que el limpio conserve todas las verdaderas.
- [ ] **Step 4:** Correr → PASS.

### Task 4: Agregado mensual y ejemplos del modelo

**Files:**
- Create: `dataset/agregado.py`
- Test: `tests/unit/test_dataset.py`

**Interfaces:**
- Consumes: limpio, cuentas, `red_neuronal.caracteristicas.vector`, `Movimiento`, `CAMPOS`.
- Produces:
  - `mensual(limpio, cuentas) -> DataFrame`: `cuenta_id, anio, mes, recibido, enviado, movimientos, saldo_cierre, mes_seno, mes_coseno`.
  - `ejemplos(limpio, cuentas, conf) -> DataFrame`: `cuenta_id, fecha_corte (fin de cada mes), *CAMPOS, objetivo_recibido, objetivo_enviado, escala, particion ("entrenamiento"|"validacion"|"prueba")`. Las características salen de `vector(movimientos_hasta_corte, Decimal(saldo_al_corte), fecha_corte)`; objetivos = lo recibido y enviado en `(corte, corte + 30 días]` dividido por `escala`. Sólo cortes con la cuenta activa y al menos 60 días de antigüedad. Partición temporal: los primeros 70 % de los meses → entrenamiento, el siguiente 15 % → validación, el último 15 % → prueba.
  - `normalizacion(ejemplos) -> dict[str, dict[str, float]]`: `{campo: {"media": m, "desviacion": d}}` sólo con entrenamiento.

- [ ] **Step 1: Pruebas que fallan**
  - `test_las_caracteristicas_son_las_de_la_aplicacion`: para una fila de `ejemplos`, recomputar con `vector(...)` y `assert` igualdad con `pytest.approx`.
  - `test_no_hay_nan_ni_infinitos`.
  - `test_la_particion_es_temporal`: `max(fecha_corte entrenamiento) < min(validacion) < ...`.
  - `test_la_normalizacion_usa_solo_entrenamiento`.
  - `test_cuenta_dormida_produce_caracteristicas_finitas` (Review Focus 1 y 2).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar; agrupar el limpio por cuenta una vez (no filtrar el DataFrame completo en cada corte).
- [ ] **Step 4:** Correr → PASS.

### Task 5: Exportar en todos los formatos

**Files:**
- Create: `dataset/exportar.py`
- Test: `tests/unit/test_dataset.py`

**Interfaces:**
- Produces: `exportar(tabla: DataFrame, nombre: str, carpeta: Path, *, columna_fecha: str | None, limite_bytes: int = 50 * 1024**2, excel: bool) -> list[Path]`. Escribe `nombre.csv` (UTF-8, coma, punto decimal, fechas ISO 8601), `nombre.jsonl`, `nombre.parquet` (zstd), y `nombre.xlsx` si `excel` y la tabla cabe en una hoja. Si un archivo pasaría `limite_bytes`, lo escribe partido por año de `columna_fecha` (`nombre_2019.csv`, …). `escribir_sqlite(tablas: dict[str, DataFrame], carpeta: Path, limite_bytes) -> list[Path]`: una base por capa (`sqlite/crudo.sqlite`, …) con índices por cuenta y fecha, partida por año si una pasa el límite.

- [ ] **Step 1: Pruebas que fallan** — `test_ningun_archivo_pasa_el_limite` (con `limite_bytes` chico forzar la partición y verificar tamaños), `test_csv_json_y_parquet_tienen_las_mismas_filas`, `test_dos_exportaciones_dan_csv_identicos` (hash).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Correr → PASS.

### Task 6: Documentación generada y orquestador

**Files:**
- Create: `dataset/documentar.py`, `dataset/generar.py`
- Test: `tests/unit/test_dataset.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `generar(conf: Configuracion, carpeta: Path) -> dict` (resumen: filas por tabla, archivos, tamaño total, conteos de limpieza) y `main()` que llama `generar(COMPLETA, Path("dataset"))` e imprime el resumen. `documentar.escribir(resumen, tablas, carpeta)` produce:
  - `README.md`: qué es, que es **una simulación reproducible** de un fondo de empleados (semilla, generador), capas, conteos, cómo regenerar, cómo usarlo con pandas, licencia de uso académico.
  - `diccionario_de_datos.md/.csv/.json/.xlsx`: tabla, columna, tipo, unidad, rango observado (min/max reales), nulos, descripción.
  - `reporte_de_calidad.md/.json`: antes/después de limpiar por regla, nulos por columna, duplicados, estadísticas descriptivas, distribución por perfil y por partición.

- [ ] **Step 1: Prueba que falla** — `test_generar_en_pequeno_deja_todas_las_capas(tmp_path)`: tras `generar(PEQUENA, tmp_path)` existen `README.md`, `diccionario_de_datos.csv`, `reporte_de_calidad.json`, `cuentas.csv`, `crudo/`, `limpio/`, `agregado/`, `modelo/normalizacion.json`, `sqlite/`, y el README contiene «simulación».
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Correr → PASS.
- [ ] **Step 5:** Generar el completo: `.venv-tf/bin/python -m dataset.generar`. Esperado: ~800.000 transacciones, ningún archivo > 50 MB (`find dataset -size +50M` vacío), tamaño total ~0,5 GB. Correrlo dos veces y comparar `sha256sum dataset/limpio/*.csv` → iguales.

### Task 7: Entrenar desde el dataset

**Files:**
- Modify: `red_neuronal/entrenar.py`, `red_neuronal/modelo.py`, `red_neuronal/figuras.py`, `red_neuronal/__init__.py`
- Delete: `red_neuronal/serie.py`

**Interfaces:**
- Consumes: `dataset/modelo/ejemplos*.parquet`, `dataset/modelo/normalizacion.json`.
- Produces: `construir_modelo(*, entradas=len(CAMPOS), ocultas=NEURONAS_OCULTAS, media=None, varianza=None)` que, si recibe media y varianza, antepone `tf.keras.layers.Normalization(mean=..., variance=...)`. `resultados.json` agrega `"cuentas"`, `"meses"`, `"transacciones"`, `"ejemplos_de_prueba"`, `"error_prueba_pesos"`, `"error_ingenuo_prueba"` y conserva las claves existentes.

- [ ] **Step 1:** Cambiar `entrenar.main()` para leer las particiones del dataset (entrenamiento/validación para `fit` con EarlyStopping; prueba sólo para el reporte final), con lote 256 y las mismas comparaciones ingenuas calculadas sobre prueba.
- [ ] **Step 2:** `figuras.py` toma un ejemplo de la partición de prueba en vez de `serie.ejemplos()`; borrar `serie.py` y su fila en `__init__.py`.
- [ ] **Step 3:** `.venv-tf/bin/python -m red_neuronal.entrenar` y `.venv-tf/bin/python -m red_neuronal.figuras` sin error; `resultados.json` con las claves nuevas. Las cifras se reportan como salgan.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q tests/unit` → todo PASS (la app no depende del dataset).

### Task 8: Interfaz y verificación sobre las wallets de demostración

**Files:**
- Modify: `src/web/proyeccion.py`, `src/web/estadisticas.py`, `src/web/templates/estadisticas.html:110-124`, `src/web/traducciones.py`
- Test: `tests/unit/test_proyeccion.py`

**Interfaces:**
- Produces: `proyeccion.origen_del_modelo() -> dict[str, int] | None` que lee `red_neuronal/resultados.json` (cacheado) y devuelve `{"cuentas": n, "meses": m}` o `None` si falta el archivo o las claves.

- [ ] **Step 1: Pruebas que fallan** — `test_origen_del_modelo_lee_cuentas_y_meses(tmp_path, monkeypatch)` y `test_origen_del_modelo_sin_archivo_devuelve_none`.
- [ ] **Step 2:** Correr con `.venv/bin/python -m pytest tests/unit/test_proyeccion.py -q` → FAIL.
- [ ] **Step 3:** Implementar; en la plantilla quitar la píldora y poner, exactamente: `Lo estima una red neuronal (TensorFlow) entrenada con el dataset del proyecto: {cuentas} cuentas y {meses} meses de movimientos.` (si `origen` es `None`: `Lo estima una red neuronal (TensorFlow) entrenada con el dataset del proyecto.`). Traducción inglesa: `Estimated by a TensorFlow neural network trained on the project dataset: {cuentas} accounts and {meses} months of activity.` Quitar las dos claves viejas de `traducciones.py`.
- [ ] **Step 4:** Correr → PASS; `grep -rn "demostración\|sintétic" src/web/templates/estadisticas.html` vacío.
- [ ] **Step 5:** Reiniciar la app (`.venv-tf/bin/python -m src.web`) y, logueado como `asociado1`, `asociado2` y `asociado3`, abrir `/mis-estadisticas`: la tarjeta muestra cifras ≥ 0 del orden de lo que mueve cada cuenta al mes, y el texto nuevo.

### Task 9: Documentación del proyecto

**Files:**
- Modify: `docs/red-neuronal.md`, `README.md`

- [ ] **Step 1:** En `docs/red-neuronal.md`, reemplazar la sección de la serie sintética por: el dataset (capas, volumen, que es una simulación reproducible y por qué), la normalización, la partición temporal y las métricas nuevas de `resultados.json` (incluidas las de prueba contra las ingenuas, como salgan).
- [ ] **Step 2:** En `README.md`, una sección «El dataset» con cómo regenerarlo (`.venv-tf/bin/python -m dataset.generar`) y reentrenar, y el peso de la carpeta.
- [ ] **Step 3:** `git status` para revisar los cambios; sin commit.
