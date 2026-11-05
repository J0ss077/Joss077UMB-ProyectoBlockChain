"""El dataset con el que se entrena la proyección del próximo mes.

Es una **simulación reproducible** de un fondo de empleados: cuentas con perfiles de
comportamiento distintos que aportan, retiran, se transfieren entre sí, cobran primas,
se endeudan y pagan en cuotas, durante ocho años. No hay un historial real del fondo,
así que los datos se generan con reglas explícitas y una semilla fija: dos corridas dan
los mismos archivos, y cualquiera puede regenerarlos y revisar cómo se hicieron.

El paquete está partido por capa, en el mismo orden en que se arma el dataset:

| Módulo | Qué hace |
| ------ | -------- |
| `configuracion.py` | Cuántas cuentas, cuántos meses, la semilla y la tasa de cada defecto |
| `perfiles.py` | Las cuentas y sus transacciones «verdaderas» |
| `crudo.py` | La capa cruda: las mismas transacciones con defectos de un sistema real |
| `limpieza.py` | Las reglas que dejan la capa limpia, con cuántas filas tocó cada una |
| `agregado.py` | El resumen mensual por cuenta y los ejemplos que entran a la red |
| `exportar.py` | Cada tabla en CSV, JSON Lines, Parquet, Excel y SQLite |
| `documentar.py` | El README, el diccionario de datos y el reporte de calidad |
| `generar.py` | Corre todo: `.venv-tf/bin/python -m dataset.generar` |
"""
