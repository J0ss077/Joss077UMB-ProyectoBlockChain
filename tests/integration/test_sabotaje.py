"""El catálogo de sabotaje y su recorrido, comprobados sobre datos reales.

Dos cosas se prueban aquí, y ninguna depende de un humano: que cada caso del
catálogo declare su veredicto —y el porqué cuando el sistema no lo detecta—, y que
el recorrido completo, caso por caso, aplique la alteración, coincida con lo
declarado, restaure y deje la cadena válida otra vez. Los casos destructivos se
marcan y no se tocan sin pedirlos: borran datos y el recorrido por defecto no los
incluye.

Estas pruebas viven en `tests/integration/` porque abren la base y siembran con el
arranque real del proyecto: la herramienta sabotea por SQL directo y la suite
unitaria no puede nombrar el driver (REQ-17).
"""
import pathlib
import subprocess
import sys

import pytest

from src.sabotaje import CASOS, abrir, casos_no_detectados, esperado_de


def test_el_catalogo_declara_los_once_casos_con_su_veredicto():
    """Cada caso declara qué hace, qué mirar en el navegador y qué se espera."""
    claves = [caso.clave for caso in CASOS]

    assert len(CASOS) == 11
    assert len(set(claves)) == 11
    assert {
        "alterar-monto",
        "alterar-hash",
        "mover-transaccion",
        "borrar-transaccion",
        "insertar-confirmada-falsa",
        "reutilizar-firma",
        "violar-regla",
        "cambiar-llave-wallet",
        "pendiente-firma-invalida",
        "borrar-genesis",
        "truncar-cola",
    } == set(claves)

    for caso in CASOS:
        assert caso.titulo.strip(), f"{caso.clave} no declara su título"
        assert caso.que_hace.strip(), f"{caso.clave} no declara qué hace"
        assert caso.que_mirar.strip(), f"{caso.clave} no declara qué mirar"
        assert caso.esperado in {"cadena-valida", "cadena-invalida", "motor-rechaza"}
        assert callable(caso.aplicar) and callable(caso.restaurar)


def test_el_catalogo_declara_el_limite_de_lo_que_no_se_detecta():
    """Un caso no detectado es un límite declarado, no un olvido: trae el porqué.

    Los tres veredictos se leen del catálogo y no de una copia: la prueba exige la
    coherencia entre lo que el caso dice que se espera y lo que declara de sí mismo,
    y que ningún caso detectable se escude detrás de un "límite".
    """
    no_detectados = casos_no_detectados()

    assert len(no_detectados) == 3
    for caso in no_detectados:
        assert caso.limite is not None and caso.limite.strip(), f"{caso.clave} no declara el porqué"

    for caso in CASOS:
        if caso.esperado != "cadena-valida":
            continue
        assert caso.limite is not None, f"{caso.clave} no puede ser válido sin decir por qué"

    for caso in CASOS:
        if caso.clave in {c.clave for c in no_detectados}:
            continue
        assert esperado_de(caso.clave) != "cadena-valida"
        assert caso.limite is None, f"{caso.clave} declara un límite que no le corresponde"


def test_los_destructivos_estan_marcados_y_son_tres():
    """Los tres casos que borran datos se declaran destructivos, y solo esos tres."""
    destructivos = {caso.clave for caso in CASOS if caso.destructivo}

    assert destructivos == {"borrar-genesis", "truncar-cola", "borrar-transaccion"}


def test_la_comprobacion_previa_impide_empezar_sobre_una_cadena_alterada(
    base_limpia, conexion, con_sabotaje, web_simulada
):
    """Sobre una cadena ya alterada no se corre ningún caso: se pide resembrar o restaurar.

    La comprobación previa mira la cadena y la aplicación antes del primer caso, y las
    dos tienen que estar bien. Empezar sobre una cadena rota haría que cada caso
    informara un veredicto que no es suyo.
    """
    with con_sabotaje as sabotaje:
        conexion.execute(
            "UPDATE transactions SET amount = amount + 1 WHERE status = 'confirmed'"
        )

        recorrido = sabotaje.recorrido(web=web_simulada)

    assert recorrido.detenido_por_la_comprobacion_previa is True
    assert recorrido.resultados == ()


def test_el_recorrido_headless_recorre_los_casos_no_destructivos(
    base_limpia, conexion, con_sabotaje, web_simulada
):
    """Cada caso aplicado coincide con su declaración, restaura y deja la cadena válida.

    El recorrido es el camino real de la herramienta, sin pausas y con la aplicación
    simulada: los destructivos quedan afuera porque borran datos, y el resto se
    aplica, se compara con `esperado` —incluido el bloque señalado cuando se
    declara—, se restaura y se comprueba que la cadena vuelve a verificar como
    válida. Es la prueba de que el catálogo dice lo que dice y de que la herramienta
    puede volver atrás.
    """
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(web=web_simulada)

    assert recorrido.detenido_por_la_comprobacion_previa is False
    assert [resultado.clave for resultado in recorrido.resultados] == [
        caso.clave for caso in CASOS if not caso.destructivo
    ]

    for resultado in recorrido.resultados:
        assert resultado.coincide is True, f"{resultado.clave}: {resultado.detalle}"
        assert resultado.restaurado is True, f"{resultado.clave} no restauró"

    # La comprobación de cada caso ya verifica la cadena después de restaurar; esto la
    # vuelve a mirar con la conexión de la prueba, que es una conexión distinta a la
    # del recorrido.
    assert conexion.execute("SELECT count(*) FROM blocks").fetchone()[0] == 4
    assert conexion.execute("SELECT count(*) FROM transactions").fetchone()[0] == 10


def test_el_recorrido_headless_tambien_recorre_los_destructivos(
    base_limpia, conexion, con_sabotaje, web_simulada
):
    """Con los destructivos pedidos, los once casos se aplican, coinciden y restauran.

    El recorrido destructivo se prueba aquí porque es el único lugar donde puede
    correr sin arriesgar los datos de una demostración: sobre una base desechable
    sembrada por el arranque. Al terminar, cada caso tiene que haber restaurado lo
    que borró y la cadena tiene que volver a verificar como válida.
    """
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(web=web_simulada, con_destructivos=True)

    assert recorrido.detenido_por_la_comprobacion_previa is False
    assert len(recorrido.resultados) == 11
    for resultado in recorrido.resultados:
        assert resultado.coincide is True, f"{resultado.clave}: {resultado.detalle}"
        assert resultado.restaurado is True, f"{resultado.clave} no restauró"

    assert conexion.execute("SELECT count(*) FROM blocks").fetchone()[0] == 4
    assert conexion.execute("SELECT count(*) FROM transactions").fetchone()[0] == 10
    # El contenido también vuelve: la restauración repone los valores, no solo las filas.
    with abrir() as sabotaje:
        assert sabotaje.cadena_valida() is True


def test_la_herramienta_no_esta_en_el_camino_de_la_presentacion():
    """`src/sabotaje.py` no es parte de la aplicación: existe para verificar y demostrar.

    Es una herramienta de verificación, no de petición: la presentación no puede
    importarla (REQ-29) ni el recorrido de la aplicación pasar por ella. Se lee el
    fuente de la capa web para exigirlo sin importar nada.
    """
    fuente = pathlib.Path("src/web/app.py").read_text(encoding="utf-8")

    assert "sabotaje" not in fuente


@pytest.fixture
def con_sabotaje(base_limpia, master_key):
    """Base limpia, la demostración sembrada como se siembra de verdad, y la herramienta.

    El arranque corre en un subproceso —su contrato es el punto de entrada
    (`python -m src.bootstrap`) y no una función interna— y después se abre la
    herramienta, que trae su propia conexión desde `factory.database_url()`: la
    misma cadena que usa el ledger, pero otra conexión, que es como la herramienta
    sabotea por SQL directo mientras la verificación lee.
    """
    subprocess.run([sys.executable, "-m", "src.bootstrap"], check=True)
    with abrir() as sabotaje:
        yield sabotaje


@pytest.fixture
def web_simulada():
    """La comprobación previa de la aplicación, sin servidor: para el recorrido headless.

    La sonda real pide HTTP 200 en `/verificar`; en la suite no hay aplicación
    levantada y lo que se prueba es el recorrido, no el sondeo. La sonda real tiene
    su propia prueba negativa, que es donde se comprueba que su veredicto manda.
    """
    return lambda: True


def test_la_comprobacion_previa_avisa_cuando_la_aplicacion_no_responde(
    base_limpia, con_sabotaje
):
    """Sin aplicación que responda en `/verificar`, la herramienta no corre ningún caso.

    La pausa de cada caso existe para que alguien mire el navegador: sin aplicación
    no hay nada que mirar, así que la comprobación previa lo dice y se detiene. La
    prueba no levanta el servidor: solo comprueba que el veredicto del sondeo manda.
    """
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(web=lambda: False)

    assert recorrido.detenido_por_la_comprobacion_previa is True
    assert recorrido.resultados == ()


def test_el_recorrido_sin_terminal_no_espera_a_nadie(base_limpia, con_sabotaje, web_simulada):
    """Sin terminal donde alguien pulse Enter, el recorrido no se cuelga: lo dice y sigue.

    La consola de la suite no es interactiva. Si la herramienta esperara de todos
    modos, cualquier corrida automatizada se quedaría esperando para siempre.
    """

    class SinEnter:
        """Un flujo de entrada que no es un terminal, como el de una corrida con guion."""

        def isatty(self) -> bool:
            return False

        def readline(self) -> str:  # pragma: no cover - no debería llamarse nunca
            raise AssertionError("sin terminal no se puede esperar un Enter")

    salida = []
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(
            web=web_simulada, pausas=True, entrada=SinEnter(), salida=salida.append
        )

    assert len(recorrido.resultados) == len(CASOS) - 3
    assert any("no hay terminal" in linea for linea in salida)
