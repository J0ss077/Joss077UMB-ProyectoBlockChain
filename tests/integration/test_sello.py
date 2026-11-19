"""La suite no escribe el sello real de la aplicación (hallazgo de la revisión).

El arranque que las pruebas corren en un subproceso fija el sello de vigilancia.
Con la ruta fija de `datos/sello-de-vigilancia.json`, cada corrida de la suite
dejaba en la aplicación un sello con la cabeza de la base de pruebas, y
`/verificar` mostraba un `sello-no-coincide` crítico que las pruebas habían
provocado. La suite define `SELLO_DE_VIGILANCIA` a un archivo de una carpeta
temporal antes de cualquier arranque; estas pruebas comprueban el desvío y que el
archivo real queda intacto.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from src.persistence.factory import (
    RAIZ_DEL_PROYECTO,
    RUTA_DEL_SELLO_DE_VIGILANCIA,
    VARIABLE_DEL_SELLO,
    sello_de_vigilancia,
)
from tests.integration.conftest import ARCHIVO_DEL_SELLO_DE_PRUEBA


def _sha256(ruta: Path) -> str | None:
    """Hash del archivo, o `None` si no existe (el sello puede no estar fijado)."""
    if not ruta.exists():
        return None
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_la_suite_apunta_el_sello_a_una_carpeta_temporal():
    """El adaptador que arma la suite escribe fuera de `datos/` y del archivo real."""
    ruta = sello_de_vigilancia().ruta
    configurada = Path(os.environ[VARIABLE_DEL_SELLO])

    assert ruta == configurada == ARCHIVO_DEL_SELLO_DE_PRUEBA
    assert ruta != RUTA_DEL_SELLO_DE_VIGILANCIA
    assert not ruta.is_relative_to(RAIZ_DEL_PROYECTO / "datos")


def test_el_arranque_de_pruebas_no_toca_el_sello_real(base_limpia):
    """Correr el arranque como en producción deja igual el sello real de la aplicación."""
    antes = _sha256(RUTA_DEL_SELLO_DE_VIGILANCIA)

    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)

    assert _sha256(RUTA_DEL_SELLO_DE_VIGILANCIA) == antes
    # El arranque sí fijó un sello: lo hizo en la copia temporal de la sesión.
    assert sello_de_vigilancia().leer().sello is not None
