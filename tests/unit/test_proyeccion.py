"""La proyección que muestra la página de estadísticas, sin TensorFlow.

La red se entrena y se evalúa aparte (`red_neuronal/entrenar.py`). Lo que se prueba acá
es la pieza que la aplicación usa en cada visita: cómo resume el historial en las ocho
características, cómo vuelve de proporciones a pesos y qué hace cuando el modelo no
está. Esa última parte es la que garantiza que el prototipo siga funcionando en una
máquina sin TensorFlow.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from red_neuronal.caracteristicas import CAMPOS, Movimiento, resumen, vector
from src.web import proyeccion

AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _movimiento(dias: int, signo: int, monto: str, confirmada: bool = True) -> Movimiento:
    return Movimiento(
        fecha=AHORA - timedelta(days=dias),
        signo=signo,
        monto=Decimal(monto),
        confirmada=confirmada,
    )


def test_el_resumen_separa_lo_que_entra_de_lo_que_sale():
    """Recibido y enviado van por separado: dos cuentas con el mismo neto no se mueven igual."""
    movimientos = [
        _movimiento(2, 1, "900.00"),
        _movimiento(5, -1, "300.00"),
        _movimiento(40, -1, "50.00"),
    ]

    datos = resumen(movimientos, Decimal("1000.00"), AHORA)

    assert datos.recibido == 900.0
    assert datos.enviado == 300.0
    assert datos.movimientos == 2.0
    assert datos.neto_previo == -50.0
    assert datos.movimientos_previos == 1.0


def test_las_pendientes_y_las_rechazadas_no_cuentan():
    """Lo que está en espera no movió nada y lo rechazado nunca lo movió."""
    movimientos = [
        _movimiento(1, 1, "500.00", confirmada=False),
        _movimiento(2, -1, "500.00", confirmada=False),
    ]

    datos = resumen(movimientos, Decimal(0), AHORA)

    assert (datos.recibido, datos.enviado, datos.movimientos) == (0.0, 0.0, 0.0)


def test_la_ventana_no_mira_mas_alla_de_sesenta_dias():
    """Las dos ventanas son de treinta días: lo de hace 61 días no entra en ninguna."""
    movimientos = [_movimiento(61, 1, "999.00")]

    datos = resumen(movimientos, Decimal(0), AHORA)

    assert datos.recibido == 0.0
    assert datos.movimientos == 0.0
    assert datos.neto_previo == 0.0


def test_la_entrada_son_proporciones_y_el_mes_del_anio():
    """Las ocho posiciones: seis proporciones y conteos, más el mes como seno y coseno."""
    movimientos = [_movimiento(3, 1, "2000.00"), _movimiento(4, -1, "1000.00")]

    caracteristicas, escala = vector(movimientos, Decimal("3000.00"), AHORA)

    assert len(caracteristicas) == len(CAMPOS) == 8
    assert escala == 2000.0
    assert round(caracteristicas[0], 3) == 0.5  # gastó la mitad de lo que recibió
    assert round(caracteristicas[1], 3) == 0.2  # dos movimientos sobre diez
    assert abs(caracteristicas[6] ** 2 + caracteristicas[7] ** 2 - 1) < 1e-9


def test_sin_recibido_la_escala_es_el_saldo():
    """Una cuenta que sólo tiene saldo se proyecta sobre eso: no puede dividir por cero."""
    _caracteristicas, escala = vector([], Decimal("1500.00"), AHORA)

    assert escala == 1500.0


def test_sin_modelo_la_pagina_se_queda_sin_proyeccion(monkeypatch):
    """Sin TensorFlow o sin archivo, `proyectar` devuelve `None` y la página no se rompe."""
    monkeypatch.setattr(proyeccion, "_cargar", lambda: None)

    assert proyeccion.proyectar([], Decimal("1000.00"), uuid4(), ahora=AHORA) is None


def _sin_numpy(monkeypatch):
    """La conversión a arreglo se reemplaza: estas pruebas corren sin NumPy.

    En la aplicación la hace `proyeccion._entrada` con NumPy, que llega junto con
    TensorFlow. Acá el modelo es un doble, así que alcanza con pasarle la fila tal cual.
    """
    monkeypatch.setattr(proyeccion, "_entrada", lambda valores: [valores])


def test_con_modelo_devuelve_los_tres_montos_como_decimal(monkeypatch):
    """Las proporciones se vuelven a pesos con la escala de la cuenta."""
    _sin_numpy(monkeypatch)

    class Modelo:
        def predict(self, entradas, verbose=0):
            assert len(entradas[0]) == 8
            return [[1.8, 1.2]]

    monkeypatch.setattr(proyeccion, "_cargar", lambda: Modelo())

    salida = proyeccion.proyectar([], Decimal("1000.00"), uuid4(), ahora=AHORA)

    assert salida == {
        "recibido": Decimal("1800.00"),
        "enviado": Decimal("1200.00"),
        "neto": Decimal("600.00"),
    }


def test_el_envio_estimado_no_supera_lo_que_hay(monkeypatch):
    """La proyección respeta la regla del envío: no se gira más que el saldo más lo que entra."""
    _sin_numpy(monkeypatch)

    class Modelo:
        def predict(self, entradas, verbose=0):
            return [[1.8, 9.0]]

    monkeypatch.setattr(proyeccion, "_cargar", lambda: Modelo())

    salida = proyeccion.proyectar([], Decimal("500.00"), uuid4(), ahora=AHORA)

    assert salida["recibido"] == Decimal("900.00")
    assert salida["enviado"] == Decimal("1400.00")
    assert salida["neto"] == Decimal("-500.00")


def test_con_saldo_negativo_el_envio_no_se_vuelve_negativo(monkeypatch):
    """El constituyente tiene saldo negativo y es una cuenta común elegible.

    El tope del envío es «saldo + lo que entra», y con saldo negativo ese tope es
    negativo: sin recortarlo, la tarjeta mostraba un envío de menos tres mil y un
    neto positivo, que es justo lo contrario de lo que el sistema permitiría.
    """
    _sin_numpy(monkeypatch)

    class Modelo:
        def predict(self, entradas, verbose=0):
            return [[1.8, 9.0]]

    monkeypatch.setattr(proyeccion, "_cargar", lambda: Modelo())

    salida = proyeccion.proyectar([], Decimal("-3000.00"), uuid4(), ahora=AHORA)

    assert salida["enviado"] >= 0, salida
    assert salida["neto"] == salida["recibido"] - salida["enviado"]


def test_una_prediccion_negativa_se_recorta_a_cero(monkeypatch):
    """El modelo puede devolver un valor negativo; un monto recibido no puede serlo."""
    _sin_numpy(monkeypatch)

    class Modelo:
        def predict(self, entradas, verbose=0):
            return [[-0.01, -0.01]]

    monkeypatch.setattr(proyeccion, "_cargar", lambda: Modelo())

    salida = proyeccion.proyectar([], Decimal(0), uuid4(), ahora=AHORA)

    assert salida == {
        "recibido": Decimal("0.00"),
        "enviado": Decimal("0.00"),
        "neto": Decimal("0.00"),
    }


def test_origen_del_modelo_lee_cuentas_y_meses(tmp_path, monkeypatch):
    """La tarjeta cita cuántas cuentas y meses tiene el dataset con que se entrenó la red."""
    resultados = tmp_path / "resultados.json"
    resultados.write_text(
        '{"cuentas": 2500, "meses": 96, "transacciones": 800000}', encoding="utf-8"
    )
    monkeypatch.setattr(proyeccion, "RUTA_DE_RESULTADOS", resultados)
    monkeypatch.setattr(proyeccion, "_origen", None)

    assert proyeccion.origen_del_modelo() == {"cuentas": 2500, "meses": 96}


def test_origen_del_modelo_sin_archivo_devuelve_none(tmp_path, monkeypatch):
    """Sin resultados del entrenamiento, la tarjeta usa el texto sin cifras."""
    monkeypatch.setattr(proyeccion, "RUTA_DE_RESULTADOS", tmp_path / "no-existe.json")
    monkeypatch.setattr(proyeccion, "_origen", None)

    assert proyeccion.origen_del_modelo() is None
