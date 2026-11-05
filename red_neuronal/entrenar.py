"""Entrena la proyección del próximo mes con el dataset y reporta cuánto se equivoca.

Uso:

    .venv-tf/bin/python -m dataset.generar      # si el dataset no está
    .venv-tf/bin/python -m red_neuronal.entrenar

Lee los ejemplos de `dataset/modelo/` ya partidos por tiempo: con **entrenamiento** se
ajustan los pesos, con **validación** se decide cuándo parar (EarlyStopping) y con
**prueba** —meses posteriores que el modelo nunca vio, ni para elegir cuándo parar— se
reporta el error final. Ese error se da en pesos, que es la única cifra que se entiende
en una regresión: decir «0,08 de error» no dice nada; decir «se equivoca en 190 pesos»
sí.

El error se compara con dos predicciones ingenuas: repetir lo de los últimos treinta
días y usar el promedio de entrenamiento. Sin esa comparación un error de cien pesos no
dice si el modelo aporta. Las cifras se reportan como salgan.

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

SEMILLA = 2026
EPOCAS = 200
PACIENCIA = 15
LOTE = 256

CARPETA_DEL_DATASET = Path("dataset")
RUTA_DE_RESULTADOS = Path("red_neuronal") / "resultados.json"
OBJETIVOS = ("objetivo_recibido", "objetivo_enviado")


def _cargar(particion: str):
    """Las entradas, los objetivos y la escala de una partición, como arreglos float32."""
    import numpy as np

    from dataset.exportar import leer

    tabla = leer(CARPETA_DEL_DATASET / "modelo", f"ejemplos_{particion}")
    return (
        tabla[list(CAMPOS)].to_numpy(dtype=np.float32),
        tabla[list(OBJETIVOS)].to_numpy(dtype=np.float32),
        tabla["escala"].to_numpy(dtype=np.float32),
    )


def _reales(particion: str):
    """Lo recibido y enviado de verdad en los 30 días siguientes, en pesos y sin tope."""
    import numpy as np

    from dataset.exportar import leer

    tabla = leer(CARPETA_DEL_DATASET / "modelo", f"ejemplos_{particion}")
    return tabla[["real_recibido", "real_enviado"]].to_numpy(dtype=np.float32)


def _error_en_pesos(prediccion, escala, reales) -> list[float]:
    """El error absoluto medio de cada salida en pesos, contra el monto **real** sin tope.

    La red aprende objetivos acotados (ver `dataset/agregado.py`), pero lo que pasa de
    verdad el mes siguiente no tiene tope: el error se mide contra eso, así los meses de
    primas o de montos grandes cuentan con todo lo que la red no alcanzó a estimar.
    """
    import numpy as np

    diferencia = np.abs(prediccion * escala[:, None] - reales)
    return [float(v) for v in diferencia.mean(axis=0)]


def main() -> None:
    """Entrena, evalúa en prueba y deja el modelo y el resumen en disco."""
    import numpy as np
    import tensorflow as tf

    if not (CARPETA_DEL_DATASET / "modelo" / "normalizacion.json").exists():
        raise SystemExit(
            "No está el dataset: corra `.venv-tf/bin/python -m dataset.generar` primero."
        )
    tf.keras.utils.set_random_seed(SEMILLA)

    x_entrenamiento, y_entrenamiento, escala_entrenamiento = _cargar("entrenamiento")
    x_validacion, y_validacion, escala_validacion = _cargar("validacion")
    x_prueba, y_prueba, escala_prueba = _cargar("prueba")
    reales = _reales("prueba")
    estadisticas = json.loads(
        (CARPETA_DEL_DATASET / "modelo" / "normalizacion.json").read_text(encoding="utf-8")
    )
    media = [estadisticas[c]["media"] for c in CAMPOS]
    # Una entrada constante tendría varianza cero y la estandarización dividiría por
    # cero; con varianza uno queda como está.
    varianza = [
        estadisticas[c]["desviacion"] ** 2 if estadisticas[c]["desviacion"] > 0 else 1.0
        for c in CAMPOS
    ]

    # Cada ejemplo pesa según su escala: un error de 0,1 en proporción son 10 pesos en
    # una cuenta de cien y 1.000 en una de diez mil. Sin el peso, la red aprende a
    # acertar en proporciones y se equivoca justo en las cuentas que más dinero mueven.
    media_de_escala = float(escala_entrenamiento.mean())
    modelo = construir_modelo(media=media, varianza=varianza)
    historia = modelo.fit(
        x_entrenamiento,
        y_entrenamiento,
        sample_weight=escala_entrenamiento / media_de_escala,
        epochs=EPOCAS,
        batch_size=LOTE,
        validation_data=(x_validacion, y_validacion, escala_validacion / media_de_escala),
        verbose=0,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=PACIENCIA, restore_best_weights=True
            )
        ],
    )

    perdida_validacion, _ = modelo.evaluate(x_validacion, y_validacion, verbose=0)
    perdida_prueba, _ = modelo.evaluate(x_prueba, y_prueba, verbose=0)
    prediccion = modelo.predict(x_prueba, verbose=0, batch_size=4096)
    error_modelo = _error_en_pesos(prediccion, escala_prueba, reales)

    # Ingenua 1: repetir los últimos treinta días. Lo recibido en esa ventana es la
    # escala misma (proporción 1) y lo enviado es la primera entrada, `gasto_relativo`.
    # Cuando la cuenta no recibió nada, la escala es su saldo y esta ingenua predice de
    # más: es una comparación aproximada y así se documenta.
    repetir = np.stack([np.ones(len(x_prueba)), x_prueba[:, 0]], axis=1).astype(np.float32)
    # Ingenua 2: el promedio de entrenamiento, en pesos, para todos.
    promedio_en_pesos = _reales("entrenamiento").mean(axis=0)
    promedio = np.tile(promedio_en_pesos, (len(x_prueba), 1)) / escala_prueba[:, None]
    error_repetir = _error_en_pesos(repetir, escala_prueba, reales)
    error_promedio = _error_en_pesos(promedio, escala_prueba, reales)

    monto_medio = float(np.mean(np.abs(reales)))
    error_absoluto = float(np.mean(error_modelo))
    calidad = json.loads(
        (CARPETA_DEL_DATASET / "reporte_de_calidad.json").read_text(encoding="utf-8")
    )

    print(
        f"red: {len(CAMPOS)} entradas -> normalización -> "
        f"{NEURONAS_OCULTAS} ocultas -> {SALIDAS} salidas"
    )
    print(
        f"ejemplos: entrenamiento {len(x_entrenamiento):,} | validación {len(x_validacion):,} "
        f"| prueba {len(x_prueba):,}"
    )
    print(f"épocas corridas: {len(historia.history['loss'])} de {EPOCAS}")
    print(f"error absoluto medio en prueba: {error_absoluto:.2f} pesos")
    for salida, nombre in enumerate(("recibido", "enviado")):
        print(
            f"  {nombre:>8s}: modelo {error_modelo[salida]:8.2f} | "
            f"últimos 30 días {error_repetir[salida]:8.2f} | "
            f"promedio {error_promedio[salida]:8.2f} pesos"
        )
    print(f"error relativo del modelo: {100 * error_absoluto / monto_medio:.0f} %")

    RUTA_DEL_MODELO.parent.mkdir(parents=True, exist_ok=True)
    modelo.save(RUTA_DEL_MODELO)
    resumen = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "campos": list(CAMPOS),
        "neuronas_ocultas": NEURONAS_OCULTAS,
        "dataset": str(CARPETA_DEL_DATASET),
        "cuentas": calidad["cuentas"]["total"],
        "meses": _meses_del_dataset(),
        "transacciones": calidad["limpio"]["filas"],
        "ejemplos": len(x_entrenamiento) + len(x_validacion) + len(x_prueba),
        "ejemplos_de_entrenamiento": len(x_entrenamiento),
        "ejemplos_de_validacion": len(x_validacion),
        "ejemplos_de_prueba": len(x_prueba),
        "epocas": EPOCAS,
        "epocas_corridas": len(historia.history["loss"]),
        "lote": LOTE,
        "semilla": SEMILLA,
        "perdida_validacion": round(float(perdida_validacion), 4),
        "perdida_prueba": round(float(perdida_prueba), 4),
        "error_prueba_pesos": round(error_absoluto, 2),
        "error_recibido_pesos": round(error_modelo[0], 2),
        "error_enviado_pesos": round(error_modelo[1], 2),
        "error_ingenuo_prueba": {
            "ultimos_30_dias": [round(v, 2) for v in error_repetir],
            "promedio_de_entrenamiento": [round(v, 2) for v in error_promedio],
        },
        "monto_medio_prueba_pesos": round(monto_medio, 2),
        "error_relativo": round(error_absoluto / monto_medio, 3),
        "modelo": str(RUTA_DEL_MODELO),
    }
    RUTA_DE_RESULTADOS.write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nmodelo guardado en {RUTA_DEL_MODELO}")
    print(f"resumen guardado en {RUTA_DE_RESULTADOS}")


def _meses_del_dataset() -> int:
    """Los meses que cubre el dataset, según la configuración con que se generó."""
    from dataset.configuracion import COMPLETA

    return COMPLETA.meses


if __name__ == "__main__":
    main()
