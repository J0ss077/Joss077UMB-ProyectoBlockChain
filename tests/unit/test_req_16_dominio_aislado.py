"""REQ-16: cargar el ledger no importa el driver de la base.

La prueba corre el dominio en un intérprete limpio y comprueba que `psycopg` no
quedó cargado: si el dominio importara el driver, este aparecería en
`sys.modules`. No necesita base de datos (REQ-17).
"""
import subprocess
import sys


def test_req_16_importar_el_ledger_no_carga_psycopg():
    """Cargar el módulo del ledger no importa el driver de la base."""
    codigo = "import sys, src.domain.blockchain; assert 'psycopg' not in sys.modules, 'el dominio no debe importar el driver'"
    assert subprocess.run([sys.executable, "-c", codigo]).returncode == 0
