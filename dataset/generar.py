"""Genera el dataset completo: cuentas, crudo, limpio, agregado, modelo y documentación.

Uso:

    .venv-tf/bin/python -m dataset.generar

Corre las capas en orden y las deja en `dataset/`. La semilla es fija, así que dos
corridas producen los mismos CSV y JSON. Tarda unos minutos: la parte lenta es calcular
las características de cada cuenta en cada corte, que se hace con la misma función de
la aplicación a propósito (ver `agregado.py`).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from dataset import agregado, crudo, documentar, limpieza, perfiles
from dataset.configuracion import COMPLETA, Configuracion
from dataset.exportar import escribir_sqlite, exportar

CARPETA = Path("dataset")


def generar(conf: Configuracion, carpeta: Path) -> dict:
    """Genera todas las capas en `carpeta` y devuelve un resumen de lo que escribió."""
    inicio = time.monotonic()
    paso = lambda texto: print(f"[{time.monotonic() - inicio:6.1f} s] {texto}", flush=True)  # noqa: E731

    paso("cuentas y transacciones")
    cuentas = perfiles.generar_cuentas(conf)
    verdaderas = perfiles.generar_transacciones(conf, cuentas)
    paso(f"capa cruda ({len(verdaderas):,} transacciones verdaderas)")
    tabla_cruda = crudo.ensuciar(verdaderas, conf)
    paso("limpieza")
    limpio, conteos = limpieza.limpiar(tabla_cruda, cuentas)
    paso("agregado mensual")
    mensual = agregado.mensual(limpio, cuentas, conf)
    paso("ejemplos del modelo")
    ejemplos = agregado.ejemplos(limpio, cuentas, conf)
    normalizacion = agregado.normalizacion(ejemplos)
    particiones = {
        nombre: ejemplos[ejemplos["particion"] == nombre].reset_index(drop=True)
        for nombre in (agregado.ENTRENAMIENTO, agregado.VALIDACION, agregado.PRUEBA)
    }

    paso("exportando")
    archivos: list[Path] = []
    archivos += exportar(
        tabla_cruda, "transacciones_crudas", carpeta / "crudo", columna_fecha="fecha", excel=False
    )
    archivos += exportar(
        limpio, "transacciones", carpeta / "limpio", columna_fecha="fecha", excel=False
    )
    archivos += exportar(cuentas, "cuentas", carpeta / "limpio", columna_fecha=None, excel=True)
    archivos += exportar(
        mensual, "cuentas_mensual", carpeta / "agregado", columna_fecha=None, excel=True
    )
    for nombre, tabla in particiones.items():
        archivos += exportar(
            tabla,
            f"ejemplos_{nombre}",
            carpeta / "modelo",
            columna_fecha="fecha_corte",
            excel=False,
        )
    ruta_normalizacion = carpeta / "modelo" / "normalizacion.json"
    ruta_normalizacion.write_text(
        json.dumps(normalizacion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    archivos.append(ruta_normalizacion)

    paso("bases SQLite")
    sqlite = carpeta / "sqlite"
    archivos += escribir_sqlite(
        {"transacciones_crudas": tabla_cruda},
        sqlite / "crudo.sqlite",
        columnas_fecha={"transacciones_crudas": "fecha"},
    )
    archivos += escribir_sqlite(
        {"cuentas": cuentas, "transacciones": limpio},
        sqlite / "limpio.sqlite",
        columnas_fecha={"transacciones": "fecha"},
    )
    archivos += escribir_sqlite({"cuentas_mensual": mensual}, sqlite / "agregado.sqlite")
    archivos += escribir_sqlite(
        {"ejemplos": ejemplos}, sqlite / "modelo.sqlite", columnas_fecha={"ejemplos": "fecha_corte"}
    )

    tablas = {
        "transacciones_crudas": tabla_cruda,
        "transacciones": limpio,
        "cuentas": cuentas,
        "cuentas_mensual": mensual,
        "ejemplos": ejemplos,
    }
    resumen = {
        "configuracion": {
            "cuentas": conf.cuentas,
            "meses": conf.meses,
            "fin": conf.fin.isoformat(),
            "semilla": conf.semilla,
        },
        "filas": {nombre: len(tabla) for nombre, tabla in tablas.items()}
        | {f"ejemplos_{n}": len(t) for n, t in particiones.items()},
        "limpieza": conteos,
        # Ejemplos con algún objetivo recortado al tope (ver `agregado.TOPE_DEL_OBJETIVO`).
        "objetivos_en_el_tope": int(
            (ejemplos[["objetivo_recibido", "objetivo_enviado"]] >= agregado.TOPE_DEL_OBJETIVO)
            .any(axis=1)
            .sum()
        ),
    }
    paso("documentación")
    archivos += documentar.escribir(resumen, tablas, verdaderas, carpeta)
    resumen["archivos"] = len(archivos)
    resumen["bytes"] = sum(ruta.stat().st_size for ruta in carpeta.rglob("*") if ruta.is_file())
    paso("listo")
    return resumen


def main() -> None:
    """Genera el dataset publicado en `dataset/` e informa qué dejó."""
    resumen = generar(COMPLETA, CARPETA)
    print()
    for nombre, filas in resumen["filas"].items():
        print(f"  {nombre:>24s}: {filas:>10,} filas")
    print(f"  {'archivos':>24s}: {resumen['archivos']:>10,}")
    print(f"  {'tamaño':>24s}: {resumen['bytes'] / 1024**2:>10,.1f} MB")


if __name__ == "__main__":
    main()
