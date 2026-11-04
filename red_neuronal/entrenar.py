"""Entrena la proyección del próximo mes y reporta cuánto se equivoca.

Uso:

    .venv-tf/bin/python -m red_neuronal.entrenar

Entrena sobre la serie sintética de `serie.py`, aparta los últimos meses para validar
—meses que el modelo no ve al entrenar— y reporta el error medio en pesos, que es la
única cifra que se puede interpretar en un problema de regresión: decir «0,08 de error»
no dice nada; decir «se equivoca en 190 pesos» sí.

Al final deja el modelo en `red_neuronal/modelos/proyeccion.keras` y el resumen en
`red_neuronal/resultados.json`. La semilla es fija: dos corridas dan las mismas cifras.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from red_neuronal.caracteristicas import CAMPOS
from red_neuronal.modelo import (
    NEURONAS_OCULTAS,
    RUTA_DEL_MODELO,
    SALIDAS,
    construir_modelo,
)
from red_neuronal.serie import ejemplos, serie

SEMILLA = 2026
EPOCAS = 600
PACIENCIA = 40
LOTE = 16
PROPORCION_DE_VALIDACION = 0.2

RUTA_DE_RESULTADOS = Path("red_neuronal") / "resultados.json"


def main() -> None:
    """Entrena, evalúa y deja el modelo y el resumen en disco."""
    import numpy as np
    import tensorflow as tf

    tf.keras.utils.set_random_seed(SEMILLA)

    filas = serie()
    entradas, salidas, escalas = ejemplos(filas)
    x = np.array(entradas, dtype="float32")
    # La salida son dos proporciones sobre lo recibido, así que ya está en orden uno:
    # no hace falta escalarla, y es lo que permite que el modelo sirva para cuentas de
    # tamaños muy distintos.
    y = np.array(salidas, dtype="float32")
    bases = np.array(escalas, dtype="float32")

    # La partición es por tiempo y no al azar: los últimos meses se validan con el
    # modelo entrenado con los primeros. Es lo que va a pasar al usarlo de verdad.
    corte = int(len(x) * (1 - PROPORCION_DE_VALIDACION))
    x_entrenamiento, y_entrenamiento = x[:corte], y[:corte]
    x_validacion, y_validacion = x[corte:], y[corte:]

    modelo = construir_modelo()
    historia = modelo.fit(
        x_entrenamiento,
        y_entrenamiento,
        epochs=EPOCAS,
        batch_size=LOTE,
        validation_data=(x_validacion, y_validacion),
        verbose=0,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=PACIENCIA, restore_best_weights=True
            )
        ],
    )

    perdida, _ = modelo.evaluate(x_validacion, y_validacion, verbose=0)
    # La predicción viene en proporciones; se vuelve a pesos con la escala de cada mes
    # para poder informar el error en la unidad que se entiende.
    proporciones = modelo.predict(x_validacion, verbose=0)
    predicciones = proporciones * bases[corte:, None]
    reales = y_validacion * bases[corte:, None]
    error_absoluto = float(np.mean(np.abs(predicciones - reales)))
    error_por_salida = [
        float(np.mean(np.abs(predicciones[:, i] - reales[:, i]))) for i in range(SALIDAS)
    ]

    # Dos predicciones ingenuas, en pesos y por salida: sin esto un error de cien pesos
    # no dice si el modelo aporta o si la serie es tan ruidosa que no hay nada que
    # aprender. La primera repite el valor del mes anterior; la segunda usa el promedio
    # del entrenamiento para todos los meses.
    anterior = np.array([entradas[i][0:2] for i in range(corte, len(x))], dtype="float32")
    anterior = anterior * bases[corte:, None]
    promedio = np.mean(y_entrenamiento * bases[:corte, None], axis=0)
    error_ingenuo = [
        float(np.mean(np.abs(anterior[:, i] - reales[:, i]))) for i in range(SALIDAS)
    ]
    error_promedio = [
        float(np.mean(np.abs(np.full(reales.shape[0], promedio[i]) - reales[:, i])))
        for i in range(SALIDAS)
    ]

    print(f"red: {len(CAMPOS)} entradas -> {NEURONAS_OCULTAS} ocultas -> {SALIDAS} salidas")
    print(f"meses de la serie: {len(filas)} | ejemplos: {len(x)}")
    print(
        f"entrenamiento: {len(x_entrenamiento)} | validación: {len(x_validacion)}"
    )
    print(f"épocas corridas: {len(historia.history['loss'])} de {EPOCAS}")
    print(f"error absoluto medio en validación: {error_absoluto:.2f} pesos")
    for salida, nombre in enumerate(("recibido", "enviado")):
        print(
            f"  {nombre:>8s}: modelo {error_por_salida[salida]:7.2f} | "
            f"mes anterior {error_ingenuo[salida]:7.2f} | "
            f"promedio {error_promedio[salida]:7.2f} pesos"
        )
    relativo = 100 * error_absoluto / float(np.mean(np.abs(reales)))
    print(f"error relativo del modelo: {relativo:.0f} %")

    RUTA_DEL_MODELO.parent.mkdir(parents=True, exist_ok=True)
    modelo.save(RUTA_DEL_MODELO)
    resumen = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "campos": list(CAMPOS),
        "neuronas_ocultas": NEURONAS_OCULTAS,
        "meses_de_la_serie": len(filas),
        "ejemplos": len(x),
        "ejemplos_de_entrenamiento": len(x_entrenamiento),
        "ejemplos_de_validacion": len(x_validacion),
        "epocas": EPOCAS,
        "epocas_corridas": len(historia.history["loss"]),
        "lote": LOTE,
        "semilla": SEMILLA,
        "perdida_validacion": round(float(perdida), 4),
        "error_absoluto_medio_pesos": round(error_absoluto, 2),
        "error_recibido_pesos": round(error_por_salida[0], 2),
        "error_enviado_pesos": round(error_por_salida[1], 2),
        "error_ingenuo_mes_anterior": [round(v, 2) for v in error_ingenuo],
        "error_ingenuo_promedio": [round(v, 2) for v in error_promedio],
        "monto_medio_validacion_pesos": round(float(np.mean(np.abs(reales))), 2),
        "error_relativo": round(error_absoluto / float(np.mean(np.abs(reales))), 3),
        "modelo": str(RUTA_DEL_MODELO),
    }
    RUTA_DE_RESULTADOS.write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nmodelo guardado en {RUTA_DEL_MODELO}")
    print(f"resumen guardado en {RUTA_DE_RESULTADOS}")


if __name__ == "__main__":
    main()
