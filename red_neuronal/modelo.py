"""La red de proyección: seis entradas, una capa oculta y una salida.

Arquitectura mínima, la misma que pide la actividad: **6 entradas** (las características
de los últimos treinta días), **una capa oculta de 8 neuronas con ReLU** y **una salida
lineal** con el neto esperado del mes siguiente. No es un modelo de lenguaje ni un
clasificador: es una regresión, y por eso la última capa no lleva activación.

TensorFlow se importa dentro de las funciones y no al cargar el módulo. La aplicación
funciona sin él —la página de estadísticas muestra lo descriptivo y esconde la
tarjeta de proyección—, y las pruebas corren sin el motor. Es la misma regla que usa el
dominio con PostgreSQL: la dependencia pesada se pide donde se usa.
"""
from __future__ import annotations

from pathlib import Path

from red_neuronal.caracteristicas import CAMPOS

# Neuronas de la capa oculta. Ocho alcanzan para una regresión de seis variables y
# dejan la red fácil de dibujar.
NEURONAS_OCULTAS = 8

# Dos salidas: recibido y enviado del próximo mes.
SALIDAS = 2

TASA_DE_APRENDIZAJE = 0.01
TASA_DE_ABANDONO = 0.05

# El modelo entrenado viaja con el repositorio: es chico y así la aplicación puede
# proyectar sin que nadie tenga que entrenar antes.
RUTA_DEL_MODELO = Path("red_neuronal") / "modelos" / "proyeccion.keras"


def construir_modelo(
    *,
    entradas: int = len(CAMPOS),
    ocultas: int = NEURONAS_OCULTAS,
):
    """Arma y compila la red 6 → 8 → 1 con error cuadrático medio."""
    import tensorflow as tf

    modelo = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(entradas,), name="entrada"),
            tf.keras.layers.Dense(ocultas, activation="relu", name="oculta"),
            tf.keras.layers.Dropout(TASA_DE_ABANDONO, name="abandono"),
            # Sin activación: las dos salidas son montos, no probabilidades.
            # Una es lo que se espera recibir el próximo mes y la otra lo que se
            # espera enviar.
            tf.keras.layers.Dense(SALIDAS, name="salida"),
        ]
    )
    modelo.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=TASA_DE_APRENDIZAJE),
        loss="mse",
        metrics=["mae"],
    )
    return modelo


def cargar_modelo(ruta: Path | None = None):
    """Carga el modelo entrenado de `red_neuronal/modelos/proyeccion.keras`."""
    import tensorflow as tf

    return tf.keras.models.load_model(ruta or RUTA_DEL_MODELO)
