"""La red de proyección: ocho entradas, una capa oculta y dos salidas.

Arquitectura mínima, la misma que pide la actividad: **8 entradas** (las características
de los últimos sesenta días), una capa que las estandariza con la media y la
desviación del entrenamiento, **una capa oculta de 8 neuronas con ReLU** y **dos salidas
lineales**: lo que se espera recibir y enviar el mes siguiente. No es un modelo de
lenguaje ni un clasificador: es una regresión, y por eso la última capa no lleva activación.

TensorFlow se importa dentro de las funciones y no al cargar el módulo. La aplicación
funciona sin él —la página de estadísticas muestra lo descriptivo y esconde la
tarjeta de proyección—, y las pruebas corren sin el motor. Es la misma regla que usa el
dominio con PostgreSQL: la dependencia pesada se pide donde se usa.
"""

from __future__ import annotations

from pathlib import Path

from red_neuronal.caracteristicas import CAMPOS

# Neuronas de la capa oculta. Ocho alcanzan para una regresión de ocho variables y
# dejan la red fácil de dibujar.
NEURONAS_OCULTAS = 8

# Dos salidas: recibido y enviado del próximo mes.
SALIDAS = 2

TASA_DE_APRENDIZAJE = 0.003
TASA_DE_ABANDONO = 0.05

# El modelo entrenado viaja con el repositorio: es chico y así la aplicación puede
# proyectar sin que nadie tenga que entrenar antes. La ruta se arma desde este archivo
# y no desde el directorio de trabajo: lanzada desde otra carpeta, la proyección
# desaparecía en silencio.
RUTA_DEL_MODELO = (
    Path(__file__).resolve().parents[1] / "red_neuronal" / "modelos" / "proyeccion.keras"
)


def construir_modelo(
    *,
    entradas: int = len(CAMPOS),
    ocultas: int = NEURONAS_OCULTAS,
    media: list[float] | None = None,
    varianza: list[float] | None = None,
):
    """Arma y compila la red 8 → 8 → 2 con error absoluto medio.

    Si recibe `media` y `varianza` (las de `dataset/modelo/normalizacion.json`, sacadas
    sólo de entrenamiento), la primera capa estandariza cada entrada. La estandarización
    queda **dentro** del modelo guardado: la aplicación le sigue pasando las ocho
    proporciones sin saber nada de medias ni desviaciones.
    """
    import tensorflow as tf

    capas = [tf.keras.layers.Input(shape=(entradas,), name="entrada")]
    if media is not None and varianza is not None:
        capas.append(
            tf.keras.layers.Normalization(mean=media, variance=varianza, name="normalizacion")
        )
    modelo = tf.keras.Sequential(
        [
            *capas,
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
        # Error absoluto y no cuadrático: con el peso de cada ejemplo igual a su escala
        # (ver `entrenar.py`), minimizarlo es minimizar el error en pesos, que es la
        # cifra que se informa. El cuadrático dejaba que unos pocos meses raros mandaran.
        loss="mae",
        metrics=["mae"],
    )
    return modelo


def cargar_modelo(ruta: Path | None = None):
    """Carga el modelo entrenado de `red_neuronal/modelos/proyeccion.keras`.

    `safe_mode=True` se declara en vez de confiar en el valor por defecto de Keras:
    el archivo es un zip con pesos y configuración, y esta llamada no debe aceptar
    capas que ejecuten código. Es el único lugar del proyecto que abre el modelo.
    """
    import tensorflow as tf

    return tf.keras.models.load_model(ruta or RUTA_DEL_MODELO, safe_mode=True)
