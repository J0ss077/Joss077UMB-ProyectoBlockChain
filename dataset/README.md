# Dataset del fondo de empleados

Dataset para entrenar la **proyección del próximo mes** de la aplicación: cuánto va a
recibir y cuánto va a enviar una cuenta en los treinta días siguientes.

| | |
| --- | --- |
| Cuentas | 2,500 |
| Transacciones limpias | 814,023 |
| Filas cuenta-mes | 194,392 |
| Ejemplos para la red | 188,111 (entrenamiento 125,667 · validación 31,782 · prueba 30,662) |
| Período | 96 meses, hasta 2026-10-31 |
| Formatos | CSV, JSON Lines, Parquet, Excel (tablas chicas) y SQLite |

## Origen de los datos

Es una **simulación reproducible** de un fondo de empleados. No existe un historial
real del fondo que se pueda publicar, así que las cuentas y sus movimientos se generan
con reglas explícitas (`dataset/perfiles.py`): siete perfiles de comportamiento
(ahorrador, frecuente, esporádico, con primas, endeudado, comerciante y que se retira),
parámetros propios por cuenta, estacionalidad anual, aumentos de ingreso y la regla
del ledger de que ninguna cuenta gira más de lo que tiene. La semilla es fija
(`2026`): regenerarlo da los mismos archivos.

## Capas

| Carpeta | Qué hay | Tablas |
| ------- | ------- | ------ |
| `crudo/` | Las transacciones como saldrían de un sistema real: texto, con duplicados, nulos, montos en formatos mezclados, fechas en otra zona y filas inválidas | `transacciones_crudas` |
| `limpio/` | Lo mismo después de las reglas de limpieza: tipos correctos, UTC, sin duplicados ni nulos | `transacciones`, `cuentas` |
| `agregado/` | Panel completo cuenta-mes (también los meses sin movimientos) | `cuentas_mensual` |
| `modelo/` | Las 8 entradas normalizadas de la red y sus 2 objetivos, partidos por tiempo; la media y la desviación de entrenamiento | `ejemplos_entrenamiento`, `ejemplos_validacion`, `ejemplos_prueba`, `normalizacion.json` |
| `sqlite/` | Cada capa en una base SQLite con índices por cuenta y fecha | una base por capa |

Las tablas que en un formato pasarían de 50 MB se parten por año
(`transacciones_2019.csv`, …), para que el repositorio se pueda subir a GitHub.

| Carpeta | Peso |
| ------- | ---- |
| `crudo/` | 201.8 MB |
| `limpio/` | 187.5 MB |
| `agregado/` | 50.0 MB |
| `modelo/` | 103.5 MB |
| `sqlite/` | 271.0 MB |

## Calidad

`reporte_de_calidad.md` detalla cada regla de limpieza y cuántas filas tocó. En corto:
la limpieza recuperó 814,023 de
814,023 transacciones generadas y descartó sólo las
filas inválidas (1,628 con monto cero o
negativo y 1,628 hacia cuentas que no existen).
El limpio no tiene duplicados ni nulos y ninguna cuenta cierra un mes en negativo.

## Normalización

Las ocho entradas son proporciones sobre lo que la cuenta recibe, no pesos: así una
cuenta de mil pesos y una de cincuenta mil se comparan en la misma escala. Se calculan
con `red_neuronal/caracteristicas.py`, la misma función que usa la aplicación con el
historial de cada wallet. Además, `modelo/normalizacion.json` trae la media y la
desviación de cada entrada **calculadas sólo con entrenamiento**; la red las aplica en
su primera capa. En las tablas, «normalizado» también en el sentido de base de datos:
cuentas y transacciones van en tablas separadas, unidas por `cuenta_id`.

## Cómo usarlo

```python
from pathlib import Path

from dataset.exportar import leer

entrenamiento = leer(Path("dataset/modelo"), "ejemplos_entrenamiento")       # Parquet
transacciones = leer(Path("dataset/limpio"), "transacciones", "csv")         # junta los años
```

```sql
-- sqlite3 dataset/sqlite/agregado.sqlite
SELECT anio, SUM(recibido), SUM(enviado) FROM cuentas_mensual GROUP BY anio;
```

Cada columna está explicada en `diccionario_de_datos.md` (también en CSV, JSON y Excel).

## Regenerarlo

```text
.venv-tf/bin/python -m pip install -r red_neuronal/requirements.txt
.venv-tf/bin/python -m dataset.generar
.venv-tf/bin/python -m red_neuronal.entrenar
```

Licencia: uso académico, con el resto del proyecto.
