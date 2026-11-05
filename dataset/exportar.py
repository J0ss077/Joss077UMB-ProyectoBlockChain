"""Cada tabla del dataset en varios formatos, sin que ningún archivo pase de 50 MB.

| Formato | Para qué |
| ------- | -------- |
| CSV | Abrir en cualquier herramienta: UTF-8, coma, punto decimal, fechas ISO 8601 en UTC |
| JSON Lines (`.jsonl`) | Un objeto JSON por línea: se lee por partes, sin cargar todo en memoria |
| Parquet | Columnar y comprimido (zstd), con los tipos guardados: el formato de trabajo |
| Excel (`.xlsx`) | Revisar a mano las tablas que caben en una hoja |
| SQLite | Consultar con SQL sin instalar un motor |

GitHub rechaza archivos de más de 100 MB y advierte desde 50 MB. Si una tabla pasaría
de `limite_bytes` en un formato, ese formato se escribe **partido por año**
(`transacciones_2019.csv`, `transacciones_2020.csv`, …); los demás formatos de la misma
tabla pueden quedar enteros. `leer` junta las partes de vuelta.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pandas as pd

LIMITE = 50 * 1024**2
FILAS_DE_EXCEL = 1_048_575
FORMATO_DE_FECHA = "%Y-%m-%dT%H:%M:%SZ"


def _texto_de_fechas(tabla: pd.DataFrame) -> pd.DataFrame:
    """Las fechas como texto ISO en UTC, que es como las guardan CSV, JSON, Excel y SQLite."""
    copia = tabla.copy()
    for columna in copia.columns:
        serie = copia[columna]
        if pd.api.types.is_datetime64_any_dtype(serie):
            copia[columna] = serie.dt.strftime(FORMATO_DE_FECHA)
        elif serie.dtype == object:
            # Las fechas sin hora (alta y baja de las cuentas) llegan como `date`.
            presentes = serie.dropna()
            if len(presentes) and hasattr(presentes.iloc[0], "isoformat"):
                copia[columna] = serie.map(lambda v: None if pd.isna(v) else v.isoformat())
    return copia


def _csv(tabla: pd.DataFrame, ruta: Path) -> None:
    _texto_de_fechas(tabla).to_csv(ruta, index=False, lineterminator="\n")


def _jsonl(tabla: pd.DataFrame, ruta: Path) -> None:
    _texto_de_fechas(tabla).to_json(ruta, orient="records", lines=True, force_ascii=False)


def _parquet(tabla: pd.DataFrame, ruta: Path) -> None:
    tabla.to_parquet(ruta, index=False, compression="zstd")


def _xlsx(tabla: pd.DataFrame, ruta: Path) -> None:
    _texto_de_fechas(tabla).to_excel(ruta, index=False, sheet_name=ruta.stem[:31])


ESCRITORES: dict[str, Callable[[pd.DataFrame, Path], None]] = {
    "csv": _csv,
    "jsonl": _jsonl,
    "parquet": _parquet,
}


def _anios(tabla: pd.DataFrame, columna_fecha: str) -> pd.Series:
    fechas = tabla[columna_fecha]
    if not pd.api.types.is_datetime64_any_dtype(fechas):
        fechas = pd.to_datetime(fechas.astype(str), utc=True)
    return fechas.dt.year


def _escribir_con_limite(
    tabla: pd.DataFrame,
    carpeta: Path,
    nombre: str,
    extension: str,
    escritor: Callable[[pd.DataFrame, Path], None],
    columna_fecha: str | None,
    limite_bytes: int,
) -> list[Path]:
    """Escribe la tabla entera y, si pasa el límite, la reescribe partida por año."""
    entero = carpeta / f"{nombre}.{extension}"
    escritor(tabla, entero)
    if entero.stat().st_size <= limite_bytes or columna_fecha is None:
        return [entero]
    entero.unlink()
    partes = []
    for anio, parte in tabla.groupby(_anios(tabla, columna_fecha), sort=True):
        ruta = carpeta / f"{nombre}_{anio}.{extension}"
        escritor(parte, ruta)
        if ruta.stat().st_size > limite_bytes:
            # Un solo año que no cabe es un dataset que GitHub rechazaría: mejor fallar
            # al generarlo que al subirlo.
            raise ValueError(f"{ruta} pesa más de {limite_bytes} bytes aun partido por año")
        partes.append(ruta)
    return partes


def exportar(
    tabla: pd.DataFrame,
    nombre: str,
    carpeta: Path,
    *,
    columna_fecha: str | None,
    limite_bytes: int = LIMITE,
    excel: bool,
) -> list[Path]:
    """La tabla en CSV, JSON Lines, Parquet y, si cabe en una hoja, Excel."""
    carpeta.mkdir(parents=True, exist_ok=True)
    archivos: list[Path] = []
    for extension, escritor in ESCRITORES.items():
        archivos += _escribir_con_limite(
            tabla, carpeta, nombre, extension, escritor, columna_fecha, limite_bytes
        )
    if excel and len(tabla) <= FILAS_DE_EXCEL:
        archivos += _escribir_con_limite(
            tabla, carpeta, nombre, "xlsx", _xlsx, columna_fecha, limite_bytes
        )
    return archivos


def leer(carpeta: Path, nombre: str, formato: str = "parquet") -> pd.DataFrame:
    """Lee una tabla exportada, entera o en partes por año, en el formato pedido."""
    entero = carpeta / f"{nombre}.{formato}"
    rutas = (
        [entero]
        if entero.exists()
        else sorted(carpeta.glob(f"{nombre}_[0-9][0-9][0-9][0-9].{formato}"))
    )
    if not rutas:
        raise FileNotFoundError(f"no hay {nombre}.{formato} en {carpeta}")
    lectores: dict[str, Callable[[Path], pd.DataFrame]] = {
        "csv": pd.read_csv,
        "jsonl": lambda ruta: pd.read_json(ruta, lines=True),
        "parquet": pd.read_parquet,
        "xlsx": pd.read_excel,
    }
    return pd.concat([lectores[formato](ruta) for ruta in rutas], ignore_index=True)


def escribir_sqlite(
    tablas: dict[str, pd.DataFrame],
    ruta: Path,
    *,
    columnas_fecha: dict[str, str] | None = None,
    limite_bytes: int = LIMITE,
) -> list[Path]:
    """Las tablas en una base SQLite con índices; partida por año si pasa el límite.

    Los índices van sobre las columnas por las que se consulta: la cuenta y la fecha.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)

    def escribir(destino: Path, partes: dict[str, pd.DataFrame]) -> None:
        destino.unlink(missing_ok=True)
        with sqlite3.connect(destino) as conexion:
            for nombre, tabla in partes.items():
                _texto_de_fechas(tabla).to_sql(nombre, conexion, index=False)
                for columna in tabla.columns:
                    if (
                        columna.startswith("cuenta")
                        or columna.startswith("fecha")
                        or columna == "particion"
                    ):
                        conexion.execute(
                            f'CREATE INDEX "ix_{nombre}_{columna}" ON "{nombre}" ("{columna}")'
                        )
        # Sin VACUUM el archivo guarda páginas libres y pesa más de lo necesario.
        with sqlite3.connect(destino) as conexion:
            conexion.execute("VACUUM")

    escribir(ruta, tablas)
    if ruta.stat().st_size <= limite_bytes or not columnas_fecha:
        return [ruta]
    ruta.unlink()
    anios = sorted(
        {
            int(a)
            for nombre, columna in columnas_fecha.items()
            for a in _anios(tablas[nombre], columna).unique()
        }
    )
    archivos = []
    for anio in anios:
        partes = {}
        for nombre, tabla in tablas.items():
            columna = columnas_fecha.get(nombre)
            partes[nombre] = tabla if columna is None else tabla[_anios(tabla, columna) == anio]
        destino = ruta.with_name(f"{ruta.stem}_{anio}{ruta.suffix}")
        escribir(destino, partes)
        archivos.append(destino)
    return archivos
