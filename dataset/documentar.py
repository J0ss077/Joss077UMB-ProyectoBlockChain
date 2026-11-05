"""La documentación del dataset: README, diccionario de datos y reporte de calidad.

Se genera con los datos y no a mano, para que las cifras que cita (filas, rangos,
nulos, filas que tocó cada regla de limpieza) sean siempre las de los archivos que
están al lado. Si alguien regenera el dataset con otra configuración, la documentación
cambia con él.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dataset.limpieza import CANAL_DESCONOCIDO
from dataset.perfiles import FONDO, PERFILES
from red_neuronal.caracteristicas import ESCALA_DE_CUENTA, ESCALA_DE_MONTO

# Tipo, unidad y descripción de cada columna publicada. Es la única parte escrita a
# mano: el rango, los nulos y los valores distintos se calculan de los datos.
COLUMNAS: dict[str, dict[str, tuple[str, str, str]]] = {
    "cuentas": {
        "cuenta_id": ("texto", "—", "Identificador de la cuenta (C00001…). Clave primaria."),
        "perfil": (
            "categoría",
            "—",
            "Perfil de comportamiento con que se simuló la cuenta: " + ", ".join(PERFILES) + ".",
        ),
        "fecha_alta": ("fecha", "AAAA-MM-DD", "Día en que la cuenta se afilió al fondo."),
        "fecha_baja": (
            "fecha",
            "AAAA-MM-DD",
            "Día en que la cuenta se retiró del fondo; vacío si sigue activa.",
        ),
        "ingreso_mensual": (
            "decimal",
            "pesos",
            "Ingreso mensual base de la cuenta al inicio; crece entre 2 % y 8 % por año.",
        ),
        "ciudad": ("categoría", "—", "Ciudad de la cuenta."),
        "edad": ("entero", "años", "Edad de la persona titular al afiliarse."),
    },
    "transacciones": {
        "transaccion_id": (
            "texto",
            "—",
            "Identificador de la transacción (T0000001…). Clave primaria.",
        ),
        "fecha": (
            "fecha y hora",
            "ISO 8601, UTC",
            "Momento en que se hizo la transacción, en UTC.",
        ),
        "cuenta_origen": (
            "texto",
            "—",
            f"Cuenta que envía el dinero, o {FONDO} si sale del fondo.",
        ),
        "cuenta_destino": (
            "texto",
            "—",
            f"Cuenta que recibe el dinero, o {FONDO} si entra al fondo.",
        ),
        "monto": ("decimal", "pesos", "Monto movido, con dos decimales. Siempre positivo."),
        "tipo": (
            "categoría",
            "—",
            "aporte, retiro, transferencia, prima, prestamo, cuota o liquidacion.",
        ),
        "canal": (
            "categoría",
            "—",
            f"app, web, oficina o programada; {CANAL_DESCONOCIDO} si el crudo no lo traía.",
        ),
    },
    "transacciones_crudas": {
        "transaccion_id": (
            "texto",
            "—",
            "Identificador tal como llega del sistema; puede repetirse (duplicados).",
        ),
        "fecha": (
            "texto",
            "ISO 8601",
            "Fecha con su zona: casi siempre UTC (+00:00), a veces hora de Colombia (-05:00).",
        ),
        "cuenta_origen": ("texto", "—", "Cuenta que envía, sin validar."),
        "cuenta_destino": ("texto", "—", "Cuenta que recibe, sin validar: puede no existir."),
        "monto": (
            "texto",
            "pesos",
            "Monto sin normalizar: 1234.56, 1.234,56 o $1234.56; puede ser cero o negativo.",
        ),
        "tipo": ("texto", "—", "Tipo de movimiento."),
        "canal": ("texto", "—", "Canal; puede venir vacío."),
    },
    "cuentas_mensual": {
        "cuenta_id": ("texto", "—", "Cuenta. Junto con anio y mes forma la clave primaria."),
        "anio": ("entero", "año", "Año calendario."),
        "mes": ("entero", "1–12", "Mes calendario."),
        "recibido": ("decimal", "pesos", "Suma de lo que la cuenta recibió en el mes."),
        "enviado": ("decimal", "pesos", "Suma de lo que la cuenta envió en el mes."),
        "movimientos": (
            "entero",
            "transacciones",
            "Cuántas transacciones tocaron la cuenta en el mes.",
        ),
        "saldo_cierre": (
            "decimal",
            "pesos",
            "Saldo de la cuenta al terminar el mes. Nunca negativo.",
        ),
        "mes_seno": (
            "decimal",
            "−1 a 1",
            "sen(2π·mes/12): el mes como posición en un círculo, para que diciembre quede junto a enero.",
        ),
        "mes_coseno": (
            "decimal",
            "−1 a 1",
            "cos(2π·mes/12), la otra coordenada del mes en el círculo.",
        ),
    },
    "ejemplos": {
        "cuenta_id": ("texto", "—", "Cuenta del ejemplo."),
        "fecha_corte": (
            "fecha y hora",
            "ISO 8601, UTC",
            "Instante de corte: las entradas miran los 60 días anteriores y los objetivos los 30 siguientes.",
        ),
        "gasto_relativo": (
            "decimal",
            "proporción",
            "Lo enviado en los últimos 30 días sobre la escala (tope 3).",
        ),
        "movimientos_30d": (
            "decimal",
            f"conteo / {ESCALA_DE_CUENTA:g}",
            "Movimientos de los últimos 30 días, divididos por 10 (tope 3).",
        ),
        "neto_relativo": (
            "decimal",
            "proporción",
            "Neto (recibido − enviado) de los 30 días anteriores a esos, sobre la escala (entre −3 y 3).",
        ),
        "colchon": ("decimal", "proporción", "Saldo al corte sobre la escala (tope 5)."),
        "movimientos_previos": (
            "decimal",
            f"conteo / {ESCALA_DE_CUENTA:g}",
            "Movimientos de los 30 días anteriores a esos, divididos por 10 (tope 3).",
        ),
        "recibido_escala": (
            "decimal",
            f"pesos / {ESCALA_DE_MONTO:,.0f}",
            "La escala dividida por 10.000: el tamaño de la cuenta.",
        ),
        "mes_seno": ("decimal", "−1 a 1", "sen(2π·mes/12) del mes de corte."),
        "mes_coseno": ("decimal", "−1 a 1", "cos(2π·mes/12) del mes de corte."),
        "objetivo_recibido": (
            "decimal",
            "proporción",
            "Objetivo: lo recibido en los 30 días siguientes, sobre la escala (tope 5).",
        ),
        "objetivo_enviado": (
            "decimal",
            "proporción",
            "Objetivo: lo enviado en los 30 días siguientes, sobre la escala (tope 5).",
        ),
        "escala": (
            "decimal",
            "pesos",
            "Lo recibido en los últimos 30 días (o el saldo, si no recibió nada): multiplica los objetivos para volver a pesos.",
        ),
        "real_recibido": (
            "decimal",
            "pesos",
            "Lo que la cuenta recibió de verdad en los 30 días siguientes, sin tope: contra esto se mide el error.",
        ),
        "real_enviado": (
            "decimal",
            "pesos",
            "Lo que la cuenta envió de verdad en los 30 días siguientes, sin tope.",
        ),
        "particion": (
            "categoría",
            "—",
            "entrenamiento, validacion o prueba, según el lugar del corte en el tiempo.",
        ),
    },
}

ARCHIVO_DE_TABLA = {
    "cuentas": "limpio/cuentas",
    "transacciones": "limpio/transacciones",
    "transacciones_crudas": "crudo/transacciones_crudas",
    "cuentas_mensual": "agregado/cuentas_mensual",
    "ejemplos": "modelo/ejemplos_{entrenamiento,validacion,prueba}",
}


def _rango(serie: pd.Series) -> str:
    presentes = serie.dropna()
    if presentes.empty:
        return "—"
    if pd.api.types.is_numeric_dtype(presentes) and not pd.api.types.is_bool_dtype(presentes):
        return f"{presentes.min():,.6g} a {presentes.max():,.6g}"
    if pd.api.types.is_datetime64_any_dtype(presentes):
        return f"{presentes.min():%Y-%m-%d} a {presentes.max():%Y-%m-%d}"
    distintos = presentes.astype(str).nunique()
    if distintos <= 12:
        return ", ".join(sorted(presentes.astype(str).unique()))
    return f"{distintos:,} valores distintos"


def diccionario(tablas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Una fila por columna publicada, con su tipo, unidad, rango observado y nulos."""
    filas = []
    for tabla, columnas in COLUMNAS.items():
        datos = tablas[tabla]
        for columna, (tipo, unidad, descripcion) in columnas.items():
            serie = datos[columna]
            filas.append(
                {
                    "tabla": tabla,
                    "archivo": ARCHIVO_DE_TABLA[tabla],
                    "columna": columna,
                    "tipo": tipo,
                    "unidad": unidad,
                    "rango_observado": _rango(serie),
                    "nulos": int(
                        serie.isna().sum() + (serie.astype(str).str.strip() == "").sum()
                        if serie.dtype == object
                        else serie.isna().sum()
                    ),
                    "descripcion": descripcion,
                }
            )
    return pd.DataFrame(filas)


def _tabla_md(tabla: pd.DataFrame) -> str:
    columnas = list(tabla.columns)
    lineas = ["| " + " | ".join(columnas) + " |", "| " + " | ".join("---" for _ in columnas) + " |"]
    for fila in tabla.itertuples(index=False):
        lineas.append("| " + " | ".join(str(v).replace("|", "\\|") for v in fila) + " |")
    return "\n".join(lineas)


def calidad(resumen: dict, tablas: dict[str, pd.DataFrame], verdaderas: pd.DataFrame) -> dict:
    """Lo que había en el crudo, lo que hizo la limpieza y cómo quedó cada capa."""
    crudo, limpio = tablas["transacciones_crudas"], tablas["transacciones"]
    ejemplos, mensual = tablas["ejemplos"], tablas["cuentas_mensual"]
    vacios_crudo = {
        c: int(crudo[c].isna().sum() + (crudo[c].astype(str).str.strip() == "").sum())
        for c in crudo.columns
    }
    return {
        "filas": resumen["filas"],
        "limpieza": resumen["limpieza"],
        "crudo": {
            "filas": len(crudo),
            "duplicadas": int(crudo.duplicated().sum()),
            "vacios_por_columna": vacios_crudo,
        },
        "limpio": {
            "filas": len(limpio),
            "duplicadas": int(limpio.duplicated().sum()),
            "nulos_por_columna": {c: int(limpio[c].isna().sum()) for c in limpio.columns},
            "transacciones_verdaderas_recuperadas": int(
                limpio["transaccion_id"].isin(verdaderas["transaccion_id"]).sum()
            ),
            "transacciones_verdaderas": len(verdaderas),
            "monto": {k: round(float(v), 2) for k, v in limpio["monto"].describe().items()},
            "por_tipo": {k: int(v) for k, v in limpio["tipo"].value_counts().items()},
            "por_canal": {k: int(v) for k, v in limpio["canal"].value_counts().items()},
            "desde": limpio["fecha"].min().isoformat(),
            "hasta": limpio["fecha"].max().isoformat(),
        },
        "cuentas": {
            "total": len(tablas["cuentas"]),
            "por_perfil": {
                k: int(v) for k, v in tablas["cuentas"]["perfil"].value_counts().items()
            },
            "con_baja": int(tablas["cuentas"]["fecha_baja"].notna().sum()),
        },
        "mensual": {
            "filas": len(mensual),
            "meses_sin_movimiento": int((mensual["movimientos"] == 0).sum()),
            "saldo_cierre_minimo": round(float(mensual["saldo_cierre"].min()), 2),
        },
        "ejemplos": {
            "por_particion": {k: int(v) for k, v in ejemplos["particion"].value_counts().items()},
            "cortes_por_particion": {
                k: {"desde": g.min().isoformat(), "hasta": g.max().isoformat()}
                for k, g in ejemplos.groupby("particion")["fecha_corte"]
            },
            "nulos": int(ejemplos.isna().sum().sum()),
            "con_objetivo_en_el_tope": resumen["objetivos_en_el_tope"],
            "objetivos": {
                c: {k: round(float(v), 4) for k, v in ejemplos[c].describe().items()}
                for c in ("objetivo_recibido", "objetivo_enviado")
            },
        },
    }


def _reporte_md(datos: dict) -> str:
    limpieza = pd.DataFrame([{"regla": k, "filas": f"{v:,}"} for k, v in datos["limpieza"].items()])
    nulos = pd.DataFrame(
        [
            {
                "columna": c,
                "vacíos en el crudo": f"{v:,}",
                "nulos en el limpio": f"{datos['limpio']['nulos_por_columna'].get(c, 0):,}",
            }
            for c, v in datos["crudo"]["vacios_por_columna"].items()
        ]
    )
    monto = pd.DataFrame(
        [{"estadístico": k, "monto": f"{v:,.2f}"} for k, v in datos["limpio"]["monto"].items()]
    )
    tipos = pd.DataFrame(
        [{"tipo": k, "transacciones": f"{v:,}"} for k, v in datos["limpio"]["por_tipo"].items()]
    )
    perfiles = pd.DataFrame(
        [{"perfil": k, "cuentas": f"{v:,}"} for k, v in datos["cuentas"]["por_perfil"].items()]
    )
    particiones = pd.DataFrame(
        [
            {
                "partición": k,
                "ejemplos": f"{v:,}",
                "desde": datos["ejemplos"]["cortes_por_particion"][k]["desde"][:10],
                "hasta": datos["ejemplos"]["cortes_por_particion"][k]["hasta"][:10],
            }
            for k, v in datos["ejemplos"]["por_particion"].items()
        ]
    )
    recuperadas = datos["limpio"]["transacciones_verdaderas_recuperadas"]
    verdaderas = datos["limpio"]["transacciones_verdaderas"]
    return f"""# Reporte de calidad

Generado por `dataset/documentar.py` con los mismos datos que están en esta carpeta.
La versión para máquinas está en `reporte_de_calidad.json`.

## Resumen

- Crudo: **{datos["crudo"]["filas"]:,}** filas, de las cuales {datos["crudo"]["duplicadas"]:,} son duplicadas.
- Limpio: **{datos["limpio"]["filas"]:,}** transacciones, **{datos["limpio"]["duplicadas"]}** duplicadas y
  **{sum(datos["limpio"]["nulos_por_columna"].values())}** nulos.
- La limpieza recuperó **{recuperadas:,} de {verdaderas:,}** transacciones generadas
  ({100 * recuperadas / verdaderas:.2f} %) y descartó sólo filas inválidas.
- Período: {datos["limpio"]["desde"][:10]} a {datos["limpio"]["hasta"][:10]}.
- Cuentas: **{datos["cuentas"]["total"]:,}**, de las cuales {datos["cuentas"]["con_baja"]:,} se retiraron del fondo.
- Panel mensual: **{datos["mensual"]["filas"]:,}** filas cuenta-mes, {datos["mensual"]["meses_sin_movimiento"]:,} sin
  movimientos; saldo de cierre mínimo {datos["mensual"]["saldo_cierre_minimo"]:,.2f} (ninguna cuenta en negativo).
- Ejemplos para la red: **{sum(datos["ejemplos"]["por_particion"].values()):,}**, con {datos["ejemplos"]["nulos"]} nulos;
  {datos["ejemplos"]["con_objetivo_en_el_tope"]:,} tienen un objetivo recortado al tope de 5 veces la escala.

## Reglas de limpieza y filas que tocó cada una

{_tabla_md(limpieza)}

## Vacíos por columna, antes y después

{_tabla_md(nulos)}

## Monto de las transacciones limpias (pesos)

{_tabla_md(monto)}

## Transacciones por tipo

{_tabla_md(tipos)}

## Cuentas por perfil

{_tabla_md(perfiles)}

## Partición temporal de los ejemplos

{_tabla_md(particiones)}
"""


def _readme(resumen: dict, datos: dict, tamanos: dict[str, float]) -> str:
    conf = resumen["configuracion"]
    filas = resumen["filas"]
    peso = "\n".join(f"| `{c}/` | {mb:,.1f} MB |" for c, mb in tamanos.items())
    return f"""# Dataset del fondo de empleados

Dataset para entrenar la **proyección del próximo mes** de la aplicación: cuánto va a
recibir y cuánto va a enviar una cuenta en los treinta días siguientes.

| | |
| --- | --- |
| Cuentas | {filas["cuentas"]:,} |
| Transacciones limpias | {filas["transacciones"]:,} |
| Filas cuenta-mes | {filas["cuentas_mensual"]:,} |
| Ejemplos para la red | {filas["ejemplos"]:,} (entrenamiento {filas["ejemplos_entrenamiento"]:,} · validación {filas["ejemplos_validacion"]:,} · prueba {filas["ejemplos_prueba"]:,}) |
| Período | {conf["meses"]} meses, hasta {conf["fin"]} |
| Formatos | CSV, JSON Lines, Parquet, Excel (tablas chicas) y SQLite |

## Origen de los datos

Es una **simulación reproducible** de un fondo de empleados. No existe un historial
real del fondo que se pueda publicar, así que las cuentas y sus movimientos se generan
con reglas explícitas (`dataset/perfiles.py`): siete perfiles de comportamiento
(ahorrador, frecuente, esporádico, con primas, endeudado, comerciante y que se retira),
parámetros propios por cuenta, estacionalidad anual, aumentos de ingreso y la regla
del ledger de que ninguna cuenta gira más de lo que tiene. La semilla es fija
(`{conf["semilla"]}`): regenerarlo da los mismos archivos.

## Capas

| Carpeta | Qué hay | Tablas |
| ------- | ------- | ------ |
| `crudo/` | Las transacciones como saldrían de un sistema real: texto, con duplicados, nulos, montos en formatos mezclados, fechas en otra zona y filas inválidas | `transacciones_crudas` |
| `limpio/` | Lo mismo después de las reglas de limpieza: tipos correctos, UTC, sin duplicados ni nulos | `transacciones`, `cuentas` |
| `agregado/` | Panel completo cuenta-mes (también los meses sin movimientos) | `cuentas_mensual` |
| `modelo/` | Las 8 entradas normalizadas de la red y sus 2 objetivos, partidos por tiempo; la media y la desviación de entrenamiento | `ejemplos_entrenamiento`, `ejemplos_validacion`, `ejemplos_prueba`, `normalizacion.json` |
| `sqlite/` | Cada capa en una base SQLite con índices por cuenta y fecha | una base por capa |

Las tablas que en un formato pasarían de 50 MB se parten por año
(`transacciones_2019.csv`, …), para que el repositorio se pueda subir a GitHub.

| Carpeta | Peso |
| ------- | ---- |
{peso}

## Calidad

`reporte_de_calidad.md` detalla cada regla de limpieza y cuántas filas tocó. En corto:
la limpieza recuperó {datos["limpio"]["transacciones_verdaderas_recuperadas"]:,} de
{datos["limpio"]["transacciones_verdaderas"]:,} transacciones generadas y descartó sólo las
filas inválidas ({resumen["limpieza"]["monto_invalido_descartado"]:,} con monto cero o
negativo y {resumen["limpieza"]["cuenta_inexistente_descartada"]:,} hacia cuentas que no existen).
El limpio no tiene duplicados ni nulos y ninguna cuenta cierra un mes en negativo.

## Normalización

Las ocho entradas son proporciones sobre lo que la cuenta recibe, no pesos: así una
cuenta de mil pesos y una de cincuenta mil se comparan en la misma escala. Se calculan
con `red_neuronal/caracteristicas.py`, la misma función que usa la aplicación con el
historial de cada wallet. Además, `modelo/normalizacion.json` trae la media y la
desviación de cada entrada **calculadas sólo con entrenamiento**; la red las aplica en
su primera capa. En las tablas, «normalizado» también en el sentido de base de datos:
cuentas y transacciones van en tablas separadas, unidas por `cuenta_id`.

## Cómo usarlo

```python
from pathlib import Path

from dataset.exportar import leer

entrenamiento = leer(Path("dataset/modelo"), "ejemplos_entrenamiento")       # Parquet
transacciones = leer(Path("dataset/limpio"), "transacciones", "csv")         # junta los años
```

```sql
-- sqlite3 dataset/sqlite/agregado.sqlite
SELECT anio, SUM(recibido), SUM(enviado) FROM cuentas_mensual GROUP BY anio;
```

Cada columna está explicada en `diccionario_de_datos.md` (también en CSV, JSON y Excel).

## Regenerarlo

```text
.venv-tf/bin/python -m pip install -r red_neuronal/requirements.txt
.venv-tf/bin/python -m dataset.generar
.venv-tf/bin/python -m red_neuronal.entrenar
```

Licencia: uso académico, con el resto del proyecto.
"""


def escribir(
    resumen: dict, tablas: dict[str, pd.DataFrame], verdaderas: pd.DataFrame, carpeta: Path
) -> list[Path]:
    """Escribe el diccionario, el reporte de calidad y el README; devuelve sus rutas."""
    archivos = []
    tabla = diccionario(tablas)
    for extension, escribir_ in (
        ("csv", lambda r: tabla.to_csv(r, index=False, lineterminator="\n")),
        (
            "json",
            lambda r: r.write_text(
                tabla.to_json(orient="records", force_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            ),
        ),
        ("xlsx", lambda r: tabla.to_excel(r, index=False, sheet_name="diccionario")),
    ):
        ruta = carpeta / f"diccionario_de_datos.{extension}"
        escribir_(ruta)
        archivos.append(ruta)
    ruta = carpeta / "diccionario_de_datos.md"
    ruta.write_text(
        "# Diccionario de datos\n\nUna fila por columna publicada. El rango y los nulos se "
        "calculan de los datos de esta carpeta.\n\n"
        + _tabla_md(tabla.drop(columns=["archivo"]))
        + "\n",
        encoding="utf-8",
    )
    archivos.append(ruta)

    datos = calidad(resumen, tablas, verdaderas)
    ruta = carpeta / "reporte_de_calidad.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archivos.append(ruta)
    ruta = carpeta / "reporte_de_calidad.md"
    ruta.write_text(_reporte_md(datos), encoding="utf-8")
    archivos.append(ruta)

    tamanos = {
        sub: sum(f.stat().st_size for f in (carpeta / sub).rglob("*") if f.is_file()) / 1024**2
        for sub in ("crudo", "limpio", "agregado", "modelo", "sqlite")
        if (carpeta / sub).exists()
    }
    ruta = carpeta / "README.md"
    ruta.write_text(_readme(resumen, datos, tamanos), encoding="utf-8")
    archivos.append(ruta)
    return archivos
