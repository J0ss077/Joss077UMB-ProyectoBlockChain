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
import dataclasses
import pathlib
import re
import subprocess
import sys

import pytest

from src.sabotaje import (
    CASOS,
    MOTOR_RECHAZA,
    abrir,
    caso_de,
    casos_no_detectados,
    codigo_de_salida,
    descripcion_del_error,
    esperado_de,
)


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

    Es una herramienta de verificación, no de petición (REQ-29). No alcanza con mirar
    una subcadena de `app.py`: la guarda recorre **todos** los fuentes de la capa de
    presentación —el paquete entero, no un archivo— y mira las sentencias de
    importación, que es donde una dependencia prohibida aparecería. Las plantillas
    quedan afuera porque no son Python.
    """
    fuentes = sorted(pathlib.Path("src/web").rglob("*.py"))
    assert fuentes, "la capa de presentación tiene que tener fuentes"

    importacion = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
    ofensores = []
    for fuente in fuentes:
        texto = fuente.read_text(encoding="utf-8")
        for modulo in importacion.findall(texto):
            raiz = modulo.split(".")[0]
            if raiz in {"psycopg", "sabotaje"} or modulo == "src.persistence":
                ofensores.append(f"{fuente}: {modulo}")

    assert ofensores == []


def test_el_recorrido_interactivo_aplica_antes_de_la_primera_pausa(
    base_limpia, con_sabotaje, web_simulada
):
    """El humano tiene que ver el daño y su reversión, no solo el encabezado.

    Con pausas simuladas, el orden por caso es: se aplica, **pausa** para que la
    persona mire `/verificar` en rojo, se observa y se dicta el veredicto, se restaura
    y **segunda pausa** para que vea que la cadena volvió a la normalidad. Sin esa
    segunda pausa, la mitad de lo que hay que demostrar —que la herramienta deja el
    ledger como estaba— pasa sin que nadie la mire.
    """

    class Registro:
        """El diario de la corrida: las líneas impresas y una marca por cada Enter."""

        def __init__(self) -> None:
            self.lineas: list[str] = []

        def escribir(self, linea: str) -> None:
            self.lineas.append(linea)

        def _etiqueta(self, linea: str) -> str:
            return linea.split(":", 1)[0].strip()

        def posiciones(self, etiqueta: str) -> list[int]:
            return [i for i, linea in enumerate(self.lineas) if self._etiqueta(linea) == etiqueta]

        def pausas(self) -> list[int]:
            return [i for i, linea in enumerate(self.lineas) if linea.startswith("pausa:")]

    class EntradaConPausas:
        """Un terminal simulado: cada `readline` es un Enter que la persona pulsa."""

        def __init__(self, registro: Registro) -> None:
            self._registro = registro
            self.enteres = 0

        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            # El terminal simulado solo cuenta los Enteres: el orden de la corrida se
            # lee de las líneas que la herramienta imprime, no del flujo de entrada.
            self.enteres += 1
            return "\n"

    registro = Registro()
    entrada = EntradaConPausas(registro)
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(
            web=web_simulada,
            claves=["alterar-monto"],
            pausas=True,
            entrada=entrada,
            salida=registro.escribir,
        )

    assert [resultado.clave for resultado in recorrido.resultados] == ["alterar-monto"]
    assert entrada.enteres == 2, "cada caso tiene que esperar dos veces: el daño y la vuelta"

    aplicado = registro.posiciones("se aplico")
    observado = registro.posiciones("observado")
    veredicto = registro.posiciones("veredicto")
    restaurado = registro.posiciones("restaurado")
    pausas = registro.pausas()

    assert len(aplicado) == len(observado) == len(veredicto) == len(restaurado) == 1
    assert len(pausas) == 2
    # Aplicar va antes de la primera pausa: es lo que se mira en el navegador.
    assert aplicado[0] < pausas[0]
    # La observación y el veredicto van entre las dos pausas, con el daño a la vista.
    assert pausas[0] < observado[0] < pausas[1]
    assert observado[0] < veredicto[0] < restaurado[0]
    # La restauración va antes de la segunda pausa: lo que se mira es la vuelta.
    assert restaurado[0] < pausas[1]


def test_la_primera_pausa_pide_mirar_lo_que_corresponde(con_sabotaje, web_simulada):
    """Lo que hay para mirar cambia con el desenlace, y el texto de la pausa lo dice.

    Una fila alterada se mira en `/verificar`; un rechazo del motor se mira en la
    consola, porque no queda nada escrito en la base. Una pausa que pidiera mirar «el
    daño» cuando el motor rechazó la fila mandaría a buscar algo que no existe.
    """
    from src.sabotaje import _texto_de_la_primera_pausa

    assert "daño" in _texto_de_la_primera_pausa("cadena-invalida", True)
    assert "rechazo del motor" in _texto_de_la_primera_pausa(MOTOR_RECHAZA, False)
    assert "seguir" in _texto_de_la_primera_pausa("error-inesperado", False)

    class Entrada:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return "\n"

    salida = []
    with con_sabotaje as sabotaje:
        sabotaje.recorrido(
            web=web_simulada,
            claves=["reutilizar-firma"],
            pausas=True,
            entrada=Entrada(),
            salida=salida.append,
        )

    assert any("rechazo del motor" in linea for linea in salida)


def test_la_restauracion_tiene_comprobacion_propia_cuando_la_cadena_no_la_ve(
    con_sabotaje, web_simulada
):
    """Cambiar la pública de una wallet no la ve ningún hash: hay que comparar la fila.

    Para ese caso, «la cadena vuelve a ser válida» es trivialmente cierto aunque la
    restauración no haya repuesto nada, así que el caso declara su propia comprobación
    y la prueba exige que la pública quede otra vez la de antes.
    """
    with con_sabotaje as sabotaje:
        antes = sabotaje.publica_de_una_wallet()
        recorrido = sabotaje.recorrido(
            web=web_simulada, claves=["cambiar-llave-wallet"], pausas=False
        )

    assert recorrido.resultados[0].coincide is True
    assert recorrido.resultados[0].restaurado is True
    with abrir() as sabotaje:
        assert sabotaje.publica_de_una_wallet() == antes


def test_el_resumen_cuenta_los_desacuerdos_y_la_corrida_falla_si_los_hay(
    con_sabotaje, web_simulada, monkeypatch
):
    """Un caso que no coincide con lo declarado no puede terminar en verde.

    `detectados` se cuenta desde lo **observado**, no desde lo declarado, y los
    desacuerdos se cuentan aparte: una corrida con un caso en «no coincide» tiene que
    decirlo en el resumen y salir con código distinto de cero. Si no, una herramienta
    rota informa que todo está bien. El desacuerdo se provoca saboteando el caso —su
    aplicación no hace nada— para no depender de una alteración real que sí coincida.
    """
    from src.sabotaje import CASOS

    original = next(caso for caso in CASOS if caso.clave == "alterar-monto")
    tramposo = dataclasses.replace(original, aplicar=lambda herramienta, estado: "no hizo nada")
    monkeypatch.setattr(
        "src.sabotaje.CASOS",
        tuple(tramposo if caso.clave == "alterar-monto" else caso for caso in CASOS),
    )

    salida = []
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(
            web=web_simulada, claves=["alterar-monto"], pausas=False, salida=salida.append
        )

    assert [resultado.coincide for resultado in recorrido.resultados] == [False]
    assert recorrido.detectados == 0
    assert recorrido.desacuerdos == 1
    assert codigo_de_salida(recorrido) == 1
    assert any(linea.startswith("desacuerdos: 1") for linea in salida)
    assert any(linea.startswith("- alterar-monto") and "no coincide" in linea for linea in salida)


def test_el_motor_rechaza_exige_una_violacion_de_restriccion(con_sabotaje, web_simulada):
    """Un error de sintaxis propio no es «el motor rechazó», es un error inesperado.

    Los dos casos que el motor rechaza lo hacen por una violación de restricción
    (SQLSTATE 23xxx): el índice único de la firma y el CHECK del emisor distinto del
    receptor. Cualquier otro error —una consulta mal escrita de esta herramienta, por
    ejemplo— tiene que informarse como inesperado y **no** contar como coincidencia,
    que es exactamente el defecto que la evidencia roja del reporte mostró con un
    `42601`.
    """
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(
            web=web_simulada, claves=["reutilizar-firma", "violar-regla"], pausas=False
        )

    assert [resultado.observado for resultado in recorrido.resultados] == [
        MOTOR_RECHAZA,
        MOTOR_RECHAZA,
    ]
    for resultado in recorrido.resultados:
        assert resultado.coincide is True
        assert "23" in resultado.detalle

    # El caso tramposo: una consulta rota tiene que salir del veredicto esperado.
    assert descripcion_del_error("42601") != MOTOR_RECHAZA


def test_el_limite_de_la_pendiente_falsificada_dice_que_puede_terminar_agrupada(
    con_sabotaje, web_simulada
):
    """El límite del pool no es solo que la verificación lo ignore: se puede agrupar.

    `group_pending` confirma las filas del pool sin volver a validar la firma, así que
    una pendiente falsificada puede terminar dentro de un bloque y su hash recalcularse
    sin error. El límite tiene que decir eso, no solo que la verificación mira bloques.
    """
    limite = caso_de("pendiente-firma-invalida").limite

    assert "agrup" in limite

    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(
            web=web_simulada, claves=["pendiente-firma-invalida"], pausas=False
        )

    assert recorrido.resultados[0].coincide is True


def test_la_comprobacion_previa_imprime_el_resembrado_cuando_falla(base_limpia, con_sabotaje):
    """Si el recorrido no arranca, las instrucciones de recuperación se imprimen igual.

    El camino de fallo es justo donde la persona las necesita: decir «están al final» y
    volver antes de imprimirlas manda a buscar algo que no está.
    """
    salida = []
    with con_sabotaje as sabotaje:
        recorrido = sabotaje.recorrido(web=lambda: False, salida=salida.append)

    assert recorrido.detenido_por_la_comprobacion_previa is True
    assert any("resembrado" in linea for linea in salida)
    assert any("docker compose down -v" in linea for linea in salida)


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


def test_la_comprobacion_previa_falla_temprano_si_la_base_no_responde(
    base_limpia, con_sabotaje, web_simulada
):
    """Una base que no responde se informa antes del primer caso, sin rastro del driver.

    Sin la comprobación previa, un `psycopg.OperationalError` subiría desde el medio
    del recorrido —posiblemente con un caso ya aplicado y sin restaurar— y la persona
    vería un volcado de la librería en vez de qué hacer.
    """
    salida = []
    with con_sabotaje as sabotaje:
        sabotaje._herramienta._connection.close()
        recorrido = sabotaje.recorrido(web=web_simulada, salida=salida.append)

    assert recorrido.detenido_por_la_comprobacion_previa is True
    assert recorrido.resultados == ()
    assert any("base de datos" in linea for linea in salida)
    assert not any("Traceback" in linea for linea in salida)


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
