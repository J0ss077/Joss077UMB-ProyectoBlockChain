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

    Se fija la variable que la fábrica lee y no se sustituye el lector: el camino
    que se ejercita es el real —`os.environ` primero y `.env` después—, así que lo
    que la prueba mide es la normalización de una cadena que entra por donde entra
    en producción. El nombre de la variable va por la constante del módulo: el
    guard de REQ-17 prohíbe el literal en `tests/unit`.
    """
    monkeypatch.setenv(factory.VARIABLE_DE_LA_CADENA_DE_CONEXION, cadena)


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


def test_req_21_la_normalizacion_es_una_funcion_del_modulo():
    """REQ-21: la normalización se puede probar sola, sin pasar por el entorno.

    El lector del entorno y el argumento explícito de `open_ledger` tienen que pasar
    por la misma función: si cada uno normalizara por su cuenta, una de las dos
    entradas podría quedar sin `connect_timeout` y la espera volvería a decidirla el
    sistema operativo.
    """
    sin = _parametros(factory.normalizar_cadena(SIN_TIEMPO_DE_ESPERA))
    assert sin["host"] == "127.0.0.1"
    assert sin["connect_timeout"] == "5"

    con = _parametros(factory.normalizar_cadena(CON_TIEMPO_DE_ESPERA))
    assert con["connect_timeout"] == "30"


def test_req_21_el_argumento_explicito_de_open_ledger_tambien_se_normaliza(monkeypatch):
    """REQ-21: la cadena que entra por `database_dsn` sale con `connect_timeout`.

    `open_ledger` es la segunda puerta por la que entra una cadena —la primera es el
    entorno— y es la que se queda la unidad de trabajo. La prueba la captura en el
    punto en que la fábrica se la pasa, sin abrir ninguna conexión: lo que mide es la
    normalización, no el motor.
    """
    capturadas = []

    class UnidadDeTrabajoFalsa:
        """Recibe la cadena en el mismo punto en que la recibe la unidad real."""

        @classmethod
        def open(cls, cadena):
            capturadas.append(cadena)
            return object()

    monkeypatch.setattr(factory, "PostgresUnitOfWork", UnidadDeTrabajoFalsa)
    ledger = factory.open_ledger(
        object(), encryption_key=b"clave", database_dsn=SIN_TIEMPO_DE_ESPERA
    )
    # La unidad de trabajo es diferida: la cadena se pasa al pedirla, y ahí se mira.
    ledger._unit_of_work()

    assert len(capturadas) == 1
    parametros = _parametros(capturadas[0])
    assert parametros["host"] == "127.0.0.1"
    assert parametros["connect_timeout"] == "5"
