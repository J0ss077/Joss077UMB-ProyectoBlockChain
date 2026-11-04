"""La proyección del próximo mes, calculada dentro de la aplicación.

La página de estadísticas cuenta lo que ya pasó. Esta pieza agrega lo que el modelo
entrenado estima para el mes que viene, y lo hace **en el proceso de la aplicación**:
no hay servicio aparte ni llamada a ninguna API.

El modelo se carga una sola vez y se guarda en memoria. La primera visita a la página
paga la importación de TensorFlow (unos segundos); las siguientes sólo hacen la
predicción, que es instantánea. La precarga se puede adelantar al arrancar con
`precargar()`.

Si TensorFlow no está instalado, el modelo no está en su ruta o falla al cargarse, la
función devuelve `None` y la página muestra sólo lo descriptivo: el prototipo sigue
funcionando sin la proyección. Es la misma degradación que el ayudante tiene sin clave
de IA.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from red_neuronal.caracteristicas import Movimiento, vector
from src.domain.transaction import Transaction, TransactionStatus

# El modelo entrenado viaja con el repositorio. La ruta es la misma que usa el
# entrenamiento, así que no hay dos nombres para el mismo archivo.
RUTA_DEL_MODELO = "red_neuronal/modelos/proyeccion.keras"

# El modelo se cachea en el proceso. `_no_disponible` evita reintentar la carga en cada
# petición cuando falta TensorFlow o el archivo: sin esa bandera, cada visita pagaría
# el mismo error.
_modelo: Any | None = None
_no_disponible = False


def precargar() -> bool:
    """Carga el modelo antes de la primera visita. Devuelve si quedó disponible."""
    return _cargar() is not None


def _cargar() -> Any | None:
    """Carga el modelo la primera vez; después devuelve el que ya está en memoria."""
    global _modelo, _no_disponible
    if _modelo is not None or _no_disponible:
        return _modelo
    try:
        from red_neuronal.modelo import cargar_modelo

        _modelo = cargar_modelo()
    except (ImportError, OSError, ValueError):
        # Sin TensorFlow, sin archivo o con un modelo de otra versión: la página sigue
        # sin proyección en vez de romperse.
        _no_disponible = True
        _modelo = None
    return _modelo


def movimientos_de(historial: list[Transaction], propia: UUID) -> list[Movimiento]:
    """El historial de la wallet en la forma mínima que la proyección necesita."""
    return [
        Movimiento(
            fecha=transaction.created_at,
            signo=1 if transaction.receiver_id == propia else -1,
            monto=transaction.amount,
            confirmada=transaction.status is TransactionStatus.CONFIRMED,
        )
        for transaction in historial
    ]


def _entrada(caracteristicas: list[float]):
    """La fila que espera Keras: un arreglo de una sola muestra y de tipo float32.

    `predict` no acepta una lista de Python —la rechaza con «Unrecognized data type»—,
    así que la conversión vive acá y no en la ruta. NumPy llega con TensorFlow: si no
    está instalado, el modelo tampoco se pudo cargar y esta función no se llama.
    """
    import numpy as np

    return np.array([caracteristicas], dtype="float32")


def proyectar(
    historial: list[Transaction],
    saldo: Decimal,
    propia: UUID,
    *,
    ahora: datetime | None = None,
) -> dict[str, str] | None:
    """Lo que el modelo estima para los próximos treinta días, o `None` si no hay red.

    Los montos salen como `Decimal` con dos decimales porque es lo que espera la macro
    `cantidad` de las plantillas, la misma que pinta el saldo y las cifras del resumen:
    así la proyección se ve igual que el resto de los montos de la página.
    """
    modelo = _cargar()
    if modelo is None:
        return None
    ahora = ahora or datetime.now(UTC)
    # Las proporciones se vuelven a pesos con la escala de esta cuenta, que es lo que
    # permite que el mismo modelo sirva para un fondo y para una persona.
    caracteristicas, escala = vector(movimientos_de(historial, propia), saldo, ahora)
    prediccion = modelo.predict(_entrada(caracteristicas), verbose=0)[0]
    recibido = max(0.0, float(prediccion[0]) * escala)
    enviado = max(0.0, float(prediccion[1]) * escala)
    # La misma regla que aplica el envío (REQ-05): no se puede girar más de lo que hay.
    # Sin este tope, la red puede estimar un envío mayor que el saldo y la tarjeta
    # mostraría algo que el sistema nunca permitiría.
    enviado = min(enviado, float(saldo) + recibido)
    return {
        "recibido": Decimal(f"{recibido:.2f}"),
        "enviado": Decimal(f"{enviado:.2f}"),
        "neto": Decimal(f"{recibido - enviado:.2f}"),
    }
