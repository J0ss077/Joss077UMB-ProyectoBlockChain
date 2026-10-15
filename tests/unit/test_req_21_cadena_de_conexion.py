"""REQ-21: la cadena de conexión vive en el entorno y no deja la aplicación esperando."""
import re

from src.persistence import factory

# Las dos cadenas del caso: una sin tiempo de espera y otra con uno explícito.
SIN_TIEMPO_DE_ESPERA = "postgresql://u:p@127.0.0.1:55432/db"
CON_TIEMPO_DE_ESPERA = "postgresql://u:p@127.0.0.1:55432/db?connect_timeout=30"

# Un parámetro de la forma canónica de libpq: `clave=valor`, con el valor entre
# comillas simples cuando lo necesita.
PARAMETRO = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(?:'((?:[^'\\]|\\.)*)'|(\S+))")


def _parametros(cadena: str) -> dict[str, str]:
    """Parámetros de la forma canónica de libpq, que es la que devuelve `database_url()`.

    No es una URL: es `clave=valor` separado por espacios, con comillas simples
    alrededor de los valores que las necesitan. Se interpreta acá y sin `psycopg`
    porque el guard de REQ-17 prohíbe importar el driver desde `tests/unit`.
    """
    parametros = {}
    for clave, entre_comillas, suelto in PARAMETRO.findall(cadena):
        parametros[clave] = re.sub(r"\\(.)", r"\1", entre_comillas or suelto)
    return parametros


def _cadena_del_entorno(monkeypatch, cadena: str) -> None:
    """Hace que la fábrica lea `cadena` como si viniera del entorno.

    Se sustituye el lector y no la variable: el nombre de esa variable no puede
    aparecer en `tests/unit` (REQ-17 lo prohíbe para que la suite de reglas no
    dependa de una cadena real), y esta prueba mide la normalización de la cadena,
    no de dónde sale el valor.
    """
    monkeypatch.setattr(factory, "_env_value", lambda name: cadena)


def test_req_21_la_cadena_sin_tiempo_de_espera_recibe_cinco_segundos(monkeypatch):
    """REQ-21: una cadena sin tiempo de espera no puede dejar la aplicación esperando."""
    _cadena_del_entorno(monkeypatch, SIN_TIEMPO_DE_ESPERA)
    parametros = _parametros(factory.database_url())
    assert parametros["host"] == "127.0.0.1"
    assert parametros["port"] == "55432"
    assert parametros["connect_timeout"] == "5"


def test_req_21_un_tiempo_de_espera_explicito_se_respeta(monkeypatch):
    """REQ-21: un tiempo de espera explícito en la cadena manda sobre el valor por defecto."""
    _cadena_del_entorno(monkeypatch, CON_TIEMPO_DE_ESPERA)
    parametros = _parametros(factory.database_url())
    assert parametros["host"] == "127.0.0.1"
    assert parametros["port"] == "55432"
    assert parametros["connect_timeout"] == "30"
