"""El dataset de la proyección, generado en pequeño.

Corre con el entorno de la red (`.venv-tf/bin/python -m pytest tests/unit/test_dataset.py`):
necesita pandas, que no está en el entorno de la aplicación, y por eso se salta allá.
Las pruebas usan `PEQUENA`, el mismo generador que el dataset publicado pero con pocas
cuentas y meses, para que corran en segundos.
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from dataset import perfiles  # noqa: E402
from dataset.configuracion import PEQUENA  # noqa: E402


@pytest.fixture(scope="module")
def cuentas():
    return perfiles.generar_cuentas(PEQUENA)


@pytest.fixture(scope="module")
def verdaderas(cuentas):
    return perfiles.generar_transacciones(PEQUENA, cuentas)


def test_el_generador_es_determinista(cuentas, verdaderas):
    """Dos corridas con la misma semilla dan las mismas cuentas y transacciones."""
    otra_vez = perfiles.generar_cuentas(PEQUENA)
    pd.testing.assert_frame_equal(cuentas, otra_vez)
    pd.testing.assert_frame_equal(verdaderas, perfiles.generar_transacciones(PEQUENA, otra_vez))


def test_ninguna_cuenta_queda_en_negativo(verdaderas):
    """Ninguna cuenta gasta más de lo que tiene: el fondo es la única contraparte sin tope."""
    entradas = verdaderas[["fecha", "cuenta_destino", "monto"]].rename(
        columns={"cuenta_destino": "cuenta"}
    )
    salidas = verdaderas[["fecha", "cuenta_origen", "monto"]].rename(
        columns={"cuenta_origen": "cuenta"}
    )
    salidas = salidas.assign(monto=-salidas["monto"])
    libro = pd.concat([entradas, salidas]).sort_values(["fecha"], kind="stable")
    libro = libro[libro["cuenta"] != perfiles.FONDO]
    saldo = libro.groupby("cuenta")["monto"].cumsum()
    assert saldo.min() >= -0.005


def test_no_hay_movimientos_fuera_de_la_vida_de_la_cuenta(cuentas, verdaderas):
    """Nadie opera antes de su alta ni después de su baja."""
    vida = cuentas.set_index("cuenta_id")
    for columna in ("cuenta_origen", "cuenta_destino"):
        propias = verdaderas[verdaderas[columna] != perfiles.FONDO]
        alta = propias[columna].map(vida["fecha_alta"])
        baja = propias[columna].map(vida["fecha_baja"])
        dia = propias["fecha"].dt.date
        assert (dia >= alta).all()
        assert ((baja.isna()) | (dia <= baja)).all()


def test_hay_seis_perfiles_y_montos_en_escala(cuentas, verdaderas):
    """Los perfiles son variados y los montos están en la escala de las wallets de la app."""
    assert cuentas["perfil"].nunique() >= 6
    assert verdaderas["monto"].min() >= 1
    assert verdaderas["monto"].max() <= 50_000
    assert (verdaderas["monto"].round(2) == verdaderas["monto"]).all()
    assert verdaderas["transaccion_id"].is_unique


# ── Capa cruda y limpieza ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def crudo(verdaderas):
    from dataset import crudo as capa_cruda

    return capa_cruda.ensuciar(verdaderas, PEQUENA)


@pytest.fixture(scope="module")
def limpieza(crudo, cuentas):
    from dataset import limpieza as reglas

    return reglas.limpiar(crudo, cuentas)


def test_el_crudo_es_texto_y_trae_los_defectos(crudo, verdaderas):
    """La capa cruda llega como texto, con duplicados y filas inválidas agregadas."""
    assert all(crudo[columna].dtype == object for columna in crudo.columns)
    assert len(crudo) > len(verdaderas)
    assert crudo.duplicated().sum() == round(len(verdaderas) * PEQUENA.tasa_duplicados)


def test_el_limpio_no_tiene_duplicados_ni_nulos(limpieza):
    limpio, _ = limpieza
    assert not limpio.duplicated().any()
    assert limpio["transaccion_id"].is_unique
    assert not limpio.isna().any().any()
    assert str(limpio["fecha"].dt.tz) == "UTC"


def test_cada_regla_cuenta_lo_que_inyecto_el_crudo(limpieza, verdaderas):
    """El reporte de limpieza dice exactamente cuántas filas tocó cada defecto."""
    _, conteos = limpieza
    n = len(verdaderas)
    assert conteos["duplicados_eliminados"] == round(n * PEQUENA.tasa_duplicados)
    assert conteos["canal_imputado"] == round(n * PEQUENA.tasa_nulos)
    assert conteos["monto_normalizado"] == round(n * PEQUENA.tasa_formato)
    assert conteos["fecha_convertida_a_utc"] == round(n * PEQUENA.tasa_zona)
    invalidas = round(n * PEQUENA.tasa_invalidos)
    assert (
        conteos["monto_invalido_descartado"] + conteos["cuenta_inexistente_descartada"] == invalidas
    )
    assert conteos["descartadas_por_otra_causa"] == 0


def test_el_limpio_recupera_las_transacciones_verdaderas(limpieza, verdaderas):
    """Limpiar devuelve exactamente las transacciones que se generaron, con su monto y fecha."""
    limpio, _ = limpieza
    columnas = ["transaccion_id", "fecha", "cuenta_origen", "cuenta_destino", "monto", "tipo"]
    esperado = verdaderas[columnas].sort_values("transaccion_id").reset_index(drop=True)
    obtenido = limpio[columnas].sort_values("transaccion_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(obtenido, esperado, check_dtype=False)


def test_un_defecto_desconocido_se_descarta_y_se_cuenta(crudo, cuentas):
    """Una fila con una fecha ilegible no pasa al limpio: queda en «otra causa»."""
    from dataset import limpieza as reglas

    roto = crudo.copy()
    roto.loc[roto.index[0], "fecha"] = "ayer por la tarde"
    _, conteos = reglas.limpiar(roto, cuentas)
    assert conteos["descartadas_por_otra_causa"] == 1


# ── Agregado mensual y ejemplos del modelo ───────────────────────────────────


@pytest.fixture(scope="module")
def ejemplos(limpieza, cuentas):
    from dataset import agregado

    limpio, _ = limpieza
    return agregado.ejemplos(limpio, cuentas, PEQUENA)


def test_el_mensual_tiene_una_fila_por_cuenta_y_mes_activo(limpieza, cuentas):
    from dataset import agregado

    limpio, _ = limpieza
    mensual = agregado.mensual(limpio, cuentas, PEQUENA)
    assert not mensual.duplicated(["cuenta_id", "anio", "mes"]).any()
    assert (mensual["saldo_cierre"] >= -0.005).all()
    # Lo recibido y lo enviado del mensual cuadran con el limpio.
    propias = limpio[limpio["cuenta_destino"] != "FONDO"]
    assert mensual["recibido"].sum() == pytest.approx(propias["monto"].sum())


def test_las_caracteristicas_son_las_de_la_aplicacion(limpieza, ejemplos):
    """Cada ejemplo se puede recalcular con `vector()`, la función que usa la aplicación."""
    from datetime import timedelta
    from decimal import Decimal

    from red_neuronal.caracteristicas import CAMPOS, Movimiento, vector

    limpio, _ = limpieza
    fila = ejemplos.iloc[len(ejemplos) // 2]
    corte = fila["fecha_corte"].to_pydatetime()
    propia = fila["cuenta_id"]
    suyas = limpio[
        ((limpio["cuenta_origen"] == propia) | (limpio["cuenta_destino"] == propia))
        & (limpio["fecha"] < corte)
    ]
    movimientos = [
        Movimiento(
            fecha=t.fecha.to_pydatetime(),
            signo=1 if t.cuenta_destino == propia else -1,
            monto=Decimal(str(t.monto)),
            confirmada=True,
        )
        for t in suyas.itertuples()
    ]
    saldo = sum(float(m.monto) * m.signo for m in movimientos)
    esperado, escala = vector(movimientos, Decimal(f"{saldo:.2f}"), corte)
    assert [fila[c] for c in CAMPOS] == pytest.approx(esperado)
    assert fila["escala"] == pytest.approx(escala)
    siguientes = limpio[(limpio["fecha"] >= corte) & (limpio["fecha"] < corte + timedelta(days=30))]
    recibido = siguientes.loc[siguientes["cuenta_destino"] == propia, "monto"].sum()
    assert fila["objetivo_recibido"] == pytest.approx(min(recibido / escala, 5.0))


def test_los_objetivos_estan_acotados(ejemplos):
    """Un corte con escala de un peso no puede pedirle a la red un objetivo de miles."""
    from dataset.agregado import TOPE_DEL_OBJETIVO

    assert TOPE_DEL_OBJETIVO == 5.0
    assert ejemplos["objetivo_recibido"].max() <= TOPE_DEL_OBJETIVO
    assert ejemplos["objetivo_enviado"].max() <= TOPE_DEL_OBJETIVO


def test_no_hay_nan_ni_infinitos(ejemplos):
    import numpy as np

    numericas = ejemplos.select_dtypes("number")
    assert np.isfinite(numericas.to_numpy()).all()


def test_la_particion_es_temporal(ejemplos):
    """Entrenamiento antes que validación y validación antes que prueba, sin solaparse."""
    por_particion = ejemplos.groupby("particion")["fecha_corte"]
    assert por_particion.max()["entrenamiento"] < por_particion.min()["validacion"]
    assert por_particion.max()["validacion"] < por_particion.min()["prueba"]


def test_la_normalizacion_usa_solo_entrenamiento(ejemplos):
    from dataset import agregado
    from red_neuronal.caracteristicas import CAMPOS

    estadisticas = agregado.normalizacion(ejemplos)
    entrenamiento = ejemplos[ejemplos["particion"] == "entrenamiento"]
    for campo in CAMPOS:
        assert estadisticas[campo]["media"] == pytest.approx(entrenamiento[campo].mean())
        assert estadisticas[campo]["desviacion"] == pytest.approx(entrenamiento[campo].std(ddof=0))


def test_una_cuenta_dormida_da_caracteristicas_finitas():
    """Sin movimientos en los últimos sesenta días, la escala cae en el saldo y nada explota."""
    from dataclasses import replace
    from datetime import date

    import numpy as np

    from dataset import agregado

    conf = replace(PEQUENA, cuentas=1, meses=6, fin=date(2026, 6, 30))
    cuentas_ = pd.DataFrame(
        [
            {
                "cuenta_id": "C00001",
                "perfil": "esporadico",
                "fecha_alta": date(2026, 1, 1),
                "fecha_baja": None,
                "ingreso_mensual": 1000.0,
                "ciudad": "Pasto",
                "edad": 30,
            }
        ]
    )
    limpio = pd.DataFrame(
        [
            {
                "transaccion_id": "T0000001",
                "fecha": pd.Timestamp("2026-01-05T10:00:00Z"),
                "cuenta_origen": "FONDO",
                "cuenta_destino": "C00001",
                "monto": 500.0,
                "tipo": "retiro",
                "canal": "app",
            }
        ]
    )
    tabla = agregado.ejemplos(limpio, cuentas_, conf)
    assert len(tabla) > 0
    assert np.isfinite(tabla.select_dtypes("number").to_numpy()).all()


# ── Exportación ──────────────────────────────────────────────────────────────


def _tabla_de_prueba():
    from datetime import UTC, datetime, timedelta

    inicio = datetime(2019, 1, 1, tzinfo=UTC)
    return pd.DataFrame(
        {
            "transaccion_id": [f"T{i:07d}" for i in range(3000)],
            "fecha": pd.to_datetime([inicio + timedelta(days=i) for i in range(3000)], utc=True),
            "monto": [round(10 + i * 0.37, 2) for i in range(3000)],
        }
    )


def test_ningun_archivo_pasa_el_limite(tmp_path):
    """Con un límite chico la tabla se parte por año y cada archivo queda por debajo."""
    from dataset.exportar import exportar

    # Un año de la tabla de prueba pesa unos 25 KB en JSON Lines y la tabla entera más de
    # 200 KB: con este límite se parte, y cada año cabe.
    limite = 40_000
    archivos = exportar(
        _tabla_de_prueba(),
        "movimientos",
        tmp_path,
        columna_fecha="fecha",
        limite_bytes=limite,
        excel=False,
    )
    assert any("_2019" in a.name for a in archivos)
    assert all(a.stat().st_size <= limite for a in archivos if a.suffix in (".csv", ".jsonl"))


def test_csv_json_y_parquet_tienen_las_mismas_filas(tmp_path):
    from dataset.exportar import exportar, leer

    tabla = _tabla_de_prueba()
    exportar(tabla, "movimientos", tmp_path, columna_fecha="fecha", excel=True)
    for formato in ("csv", "jsonl", "parquet", "xlsx"):
        assert len(leer(tmp_path, "movimientos", formato)) == len(tabla)


def test_dos_exportaciones_dan_archivos_identicos(tmp_path):
    import hashlib

    from dataset.exportar import exportar

    tabla = _tabla_de_prueba()
    a = exportar(tabla, "movimientos", tmp_path / "a", columna_fecha="fecha", excel=False)
    b = exportar(tabla, "movimientos", tmp_path / "b", columna_fecha="fecha", excel=False)
    resumen = lambda archivos: sorted(  # noqa: E731
        (x.name, hashlib.sha256(x.read_bytes()).hexdigest())
        for x in archivos
        if x.suffix != ".parquet"
    )
    assert resumen(a) == resumen(b)


def test_sqlite_tiene_las_tablas_con_sus_filas(tmp_path):
    import sqlite3

    from dataset.exportar import escribir_sqlite

    archivos = escribir_sqlite({"movimientos": _tabla_de_prueba()}, tmp_path / "base.sqlite")
    with sqlite3.connect(archivos[0]) as conexion:
        assert conexion.execute("SELECT count(*) FROM movimientos").fetchone()[0] == 3000


# ── Generación completa en pequeño ───────────────────────────────────────────


def test_generar_en_pequeno_deja_todas_las_capas(tmp_path):
    import json

    from dataset.generar import generar

    resumen = generar(PEQUENA, tmp_path)

    for ruta in (
        "README.md",
        "diccionario_de_datos.md",
        "diccionario_de_datos.csv",
        "diccionario_de_datos.json",
        "diccionario_de_datos.xlsx",
        "reporte_de_calidad.md",
        "reporte_de_calidad.json",
        "crudo/transacciones_crudas.csv",
        "limpio/transacciones.parquet",
        "limpio/cuentas.xlsx",
        "agregado/cuentas_mensual.jsonl",
        "modelo/ejemplos_entrenamiento.csv",
        "modelo/ejemplos_prueba.parquet",
        "modelo/normalizacion.json",
        "sqlite/limpio.sqlite",
    ):
        assert (tmp_path / ruta).exists(), ruta
    assert "simulación" in (tmp_path / "README.md").read_text(encoding="utf-8")
    calidad = json.loads((tmp_path / "reporte_de_calidad.json").read_text(encoding="utf-8"))
    assert calidad["limpieza"]["duplicados_eliminados"] > 0
    assert resumen["filas"]["transacciones"] == calidad["filas"]["transacciones"]
    # Cada columna de cada tabla publicada está en el diccionario.
    diccionario = pd.read_csv(tmp_path / "diccionario_de_datos.csv")
    assert {"tabla", "columna", "tipo", "unidad", "descripcion"} <= set(diccionario.columns)
    assert diccionario["descripcion"].str.len().min() > 10


# ── Revisión final: defectos desconocidos y objetivos sin tope ───────────────


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("monto", "1,234.56"),  # formato estadounidense: no se adivina
        ("monto", "1.234"),  # ¿mil doscientos o uno coma dos? ambiguo
        ("monto", "inf"),
        ("monto", "nan"),
        ("tipo", None),
        ("tipo", "regalo"),
        ("transaccion_id", None),
    ],
)
def test_un_valor_desconocido_va_a_otra_causa(crudo, cuentas, columna, valor):
    """Lo que la limpieza no sabe interpretar se descarta y se cuenta, no se adivina."""
    from dataset import limpieza as reglas

    roto = crudo.copy()
    fila = roto.index[roto["monto"].str.match(r"^\d+\.\d{2}$")][0]
    roto.loc[fila, columna] = valor
    limpio, conteos = reglas.limpiar(roto, cuentas)
    assert conteos["descartadas_por_otra_causa"] == 1
    assert crudo.loc[fila, "transaccion_id"] not in set(limpio["transaccion_id"])


def test_un_identificador_repetido_con_otro_contenido_se_descarta(crudo, cuentas):
    """Dos filas con el mismo id y distinto monto no son un duplicado: no se sabe cuál vale."""
    from dataset import limpieza as reglas

    roto = crudo.copy()
    fila = roto.index[roto["monto"].str.match(r"^\d+\.\d{2}$")][0]
    otra = roto.loc[[fila]].copy()
    otra["monto"] = "999.99"
    roto = pd.concat([roto, otra], ignore_index=True)
    limpio, conteos = reglas.limpiar(roto, cuentas)
    assert limpio["transaccion_id"].is_unique
    assert crudo.loc[fila, "transaccion_id"] not in set(limpio["transaccion_id"])
    assert conteos["descartadas_por_otra_causa"] == 2


def test_los_ejemplos_guardan_el_monto_real_sin_tope(limpieza, ejemplos):
    """El objetivo se acota para entrenar, pero el monto real del mes siguiente se conserva."""
    from datetime import timedelta

    limpio, _ = limpieza
    for _, fila in ejemplos.sample(20, random_state=0).iterrows():
        corte = fila["fecha_corte"]
        siguientes = limpio[
            (limpio["fecha"] >= corte) & (limpio["fecha"] < corte + timedelta(days=30))
        ]
        recibido = siguientes.loc[siguientes["cuenta_destino"] == fila["cuenta_id"], "monto"].sum()
        enviado = siguientes.loc[siguientes["cuenta_origen"] == fila["cuenta_id"], "monto"].sum()
        assert fila["real_recibido"] == pytest.approx(recibido)
        assert fila["real_enviado"] == pytest.approx(enviado)
