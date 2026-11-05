"""Los fallos que la presentación tiene que saber nombrar sin conocer el motor.

`NoHayConexion` es el único error de infraestructura que llega hasta una ruta:
`src/persistence/conexion.py` lo levanta cuando PostgreSQL no responde y la
aplicación lo pinta como una página 503 con el texto de acá. Vive en la raíz del
paquete, junto a `emision.py`, porque lo comparten la capa de persistencia y la
presentación, y esta última no puede nombrar `psycopg` ni `persistence` (REQ-29).

El mensaje no repite el error crudo del motor —lo que la persona necesita es saber
qué revisar— y el error original viaja encadenado (`raise ... from`) para que siga
en la traza de los registros.
"""
from __future__ import annotations

MENSAJE_SIN_CONEXION = (
    "No se pudo conectar con la base de datos. Revisa que el contenedor de "
    "PostgreSQL esté arriba (`docker compose up -d` o `podman compose up -d`) y "
    "que `DATABASE_URL` de tu `.env` apunte a esa base. Cuando responda, el botón "
    "de reintentar trae la página de nuevo."
)


class NoHayConexion(RuntimeError):
    """El motor no respondió al abrir la conexión.

    Se distingue de cualquier otro fallo del motor a propósito: es el único que la
    aplicación puede explicar sin enseñar una traza, porque su causa casi siempre
    está en el entorno —el contenedor apagado, el puerto cambiado, la cadena mal
    escrita— y no en los datos que la persona está enviando.
    """
