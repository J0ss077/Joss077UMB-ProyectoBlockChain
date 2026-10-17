"""La explicación no puede quedar huérfana.

Cada caso de uso en el recorrido y cada uno de los 39 requerimientos con su
prueba. Si el recorrido se separa del código, o si un criterio de aceptación se
queda sin prueba, esta suite lo dice: la trazabilidad del eje es mecánica y no se
interpreta.
"""
import pathlib
import re
import sys
import tomllib

RECORRIDO = pathlib.Path("docs/recorrido-de-casos-de-uso.md")
CASOS_DE_USO = ("CU-01", "CU-02", "CU-03", "CU-04", "CU-05")
REQUERIMIENTOS = range(1, 40)


def test_cada_caso_de_uso_aparece_en_el_recorrido():
    """Los cinco casos de uso del eje están narrados en el recorrido."""
    recorrido = RECORRIDO.read_text(encoding="utf-8")
    faltantes = [cu for cu in CASOS_DE_USO if cu not in recorrido]
    assert faltantes == []


def test_cada_requerimiento_tiene_su_prueba():
    """Los 39 requerimientos tienen una prueba `test_req_NN_` en el contenido de `tests/`."""
    contenido = "\n".join(
        fuente.read_text(encoding="utf-8") for fuente in pathlib.Path("tests").rglob("test_*.py")
    )
    faltantes = [
        f"REQ-{numero:02d}"
        for numero in REQUERIMIENTOS
        if f"test_req_{numero:02d}_" not in contenido
    ]
    assert faltantes == []


def test_req_17_las_pruebas_unitarias_no_dependen_de_la_base():
    """REQ-17: las pruebas de reglas corren con el contenedor apagado y no importan el driver.

    Se mira la sentencia de importación y no la palabra suelta, porque
    `test_req_16_dominio_aislado.py` nombra `psycopg` justamente para comprobar que
    el dominio no lo carga.
    """
    fuentes = sorted(pathlib.Path("tests/unit").rglob("*.py"))
    assert fuentes, "tests/unit tiene que tener las pruebas de reglas"
    importa_el_driver = re.compile(r"^\s*(?:import|from)\s+psycopg\b", re.MULTILINE)
    ofensores = [
        str(fuente)
        for fuente in fuentes
        if importa_el_driver.search(fuente.read_text(encoding="utf-8"))
        or "DATABASE_URL" in fuente.read_text(encoding="utf-8")
    ]
    assert ofensores == []


def test_req_20_el_interprete_cumple_el_piso_declarado():
    """REQ-20: el piso de Python está declarado y el intérprete de esta corrida lo cumple.

    La declaración se lee de `pyproject.toml` en vez de repetirla aquí, para que
    declaración y comprobación no puedan divergir.
    """
    declaracion = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
    piso = declaracion["project"]["requires-python"]
    minimo = tuple(int(parte) for parte in piso.removeprefix(">=").split("."))
    assert minimo == (3, 11), f"el piso declarado tiene que ser 3.11: {piso}"
    assert sys.version_info[: len(minimo)] >= minimo


def test_req_23_toda_dependencia_esta_fijada_con_version_exacta():
    """REQ-23: cada dependencia de `requirements.txt` viaja con su versión exacta.

    Sin la fijación, una instalación nueva podría resolver otras versiones y el
    prototipo dejaría de ser el mismo que se probó.
    """
    lineas = [
        linea.strip()
        for linea in pathlib.Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    ]
    dependencias = [linea for linea in lineas if linea and not linea.startswith("#")]
    assert dependencias, "requirements.txt no puede estar vacío"
    fijada = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][A-Za-z0-9._+!-]*$")
    sin_fijar = [linea for linea in dependencias if not fijada.match(linea)]
    assert sin_fijar == []
