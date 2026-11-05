# Reporte de calidad

Generado por `dataset/documentar.py` con los mismos datos que están en esta carpeta.
La versión para máquinas está en `reporte_de_calidad.json`.

## Resumen

- Crudo: **823,791** filas, de las cuales 6,512 son duplicadas.
- Limpio: **814,023** transacciones, **0** duplicadas y
  **0** nulos.
- La limpieza recuperó **814,023 de 814,023** transacciones generadas
  (100.00 %) y descartó sólo filas inválidas.
- Período: 2018-11-01 a 2026-10-31.
- Cuentas: **2,500**, de las cuales 347 se retiraron del fondo.
- Panel mensual: **194,392** filas cuenta-mes, 8,725 sin
  movimientos; saldo de cierre mínimo 0.00 (ninguna cuenta en negativo).
- Ejemplos para la red: **188,111**, con 0 nulos;
  9,735 tienen un objetivo recortado al tope de 5 veces la escala.

## Reglas de limpieza y filas que tocó cada una

| regla | filas |
| --- | --- |
| duplicados_eliminados | 6,512 |
| descartadas_por_otra_causa | 0 |
| monto_invalido_descartado | 1,628 |
| cuenta_inexistente_descartada | 1,628 |
| monto_normalizado | 12,210 |
| fecha_convertida_a_utc | 8,140 |
| canal_imputado | 9,768 |

## Vacíos por columna, antes y después

| columna | vacíos en el crudo | nulos en el limpio |
| --- | --- | --- |
| transaccion_id | 0 | 0 |
| fecha | 0 | 0 |
| cuenta_origen | 0 | 0 |
| cuenta_destino | 0 | 0 |
| monto | 0 | 0 |
| tipo | 0 | 0 |
| canal | 9,892 | 0 |

## Monto de las transacciones limpias (pesos)

| estadístico | monto |
| --- | --- |
| count | 814,023.00 |
| mean | 1,029.02 |
| std | 2,139.09 |
| min | 1.07 |
| 25% | 173.77 |
| 50% | 439.70 |
| 75% | 1,108.17 |
| max | 50,000.00 |

## Transacciones por tipo

| tipo | transacciones |
| --- | --- |
| aporte | 287,355 |
| transferencia | 269,452 |
| retiro | 234,320 |
| cuota | 15,867 |
| prima | 5,255 |
| prestamo | 1,583 |
| liquidacion | 191 |

## Cuentas por perfil

| perfil | cuentas |
| --- | --- |
| ahorrador | 590 |
| con_primas | 393 |
| frecuente | 352 |
| esporadico | 333 |
| endeudado | 328 |
| que_se_retira | 269 |
| comerciante | 235 |

## Partición temporal de los ejemplos

| partición | ejemplos | desde | hasta |
| --- | --- | --- | --- |
| entrenamiento | 125,667 | 2019-01-01 | 2024-06-01 |
| validacion | 31,782 | 2024-07-01 | 2025-08-01 |
| prueba | 30,662 | 2025-09-01 | 2026-10-01 |
