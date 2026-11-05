"""Dibuja las dos figuras del apartado de la red, con los datos del modelo.

La segunda no es un dibujo decorativo: se arma con las ocho características, las ocho
activaciones ocultas y las dos salidas que el modelo entrenado produce para un mes de
la partición de prueba del dataset. Si el modelo se reentrena, las figuras se regeneran y siguen
contando la verdad.

Uso:

    .venv-tf/bin/python -m red_neuronal.figuras

Deja `docs/figuras/red-neuronal-general.svg` y `docs/figuras/red-neuronal-capas.svg`.
"""
from __future__ import annotations

from pathlib import Path

from red_neuronal.caracteristicas import CAMPOS

RUTA_DE_FIGURAS = Path("docs") / "figuras"

COBALTO = "#1b3bd8"
COBALTO_CLARO = "#c7d2fe"
TINTA = "#10131a"
GRIS = "#6b7280"
LIMA = "#b8e000"
FONDO = "#ffffff"

NOMBRES = {
    "gasto_relativo": "gasto / recibido",
    "movimientos_30d": "movimientos (30 d)",
    "neto_relativo": "neto del mes previo",
    "colchon": "saldo / recibido",
    "movimientos_previos": "movimientos previos",
    "recibido_escala": "recibido (escala)",
    "mes_seno": "mes (seno)",
    "mes_coseno": "mes (coseno)",
}


def _cabecera(ancho: int, alto: int, titulo: str, subtitulo: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
        f'viewBox="0 0 {ancho} {alto}" font-family="DejaVu Sans, Arial, sans-serif">',
        f'<rect width="{ancho}" height="{alto}" fill="{FONDO}"/>',
        f'<text x="60" y="72" font-size="34" font-weight="700" fill="{TINTA}">{titulo}</text>',
        f'<text x="60" y="108" font-size="20" fill="{GRIS}">{subtitulo}</text>',
    ]


def _conexiones(
    origen: list[tuple[float, float]], destino: list[tuple[float, float]]
) -> list[str]:
    """Una línea por par de neuronas: las capas densas están todas conectadas."""
    return [
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COBALTO_CLARO}" '
        'stroke-width="1.1"/>'
        for x1, y1 in origen
        for x2, y2 in destino
    ]


def figura_general() -> str:
    """Las tres capas y el camino de los movimientos a la proyección."""
    lineas = _cabecera(
        1600,
        900,
        "Red neuronal de la proyección",
        "8 entradas · 8 neuronas ocultas con ReLU · 2 salidas lineales",
    )
    entrada = [(380, 270 + 64 * i) for i in range(8)]
    oculta = [(840, 270 + 64 * i) for i in range(8)]
    salida = [(1270, 340 + 160 * i) for i in range(2)]

    lineas += [
        f'<rect x="60" y="430" width="230" height="120" rx="16" fill="#f4f6ff" '
        f'stroke="{COBALTO_CLARO}" stroke-width="2"/>',
        f'<text x="82" y="470" font-size="17" fill="{GRIS}">movimientos</text>',
        f'<text x="82" y="500" font-size="18" font-weight="600" fill="{TINTA}">'
        "de los últimos</text>",
        f'<text x="82" y="526" font-size="18" font-weight="600" fill="{TINTA}">'
        "30 y 60 días</text>",
        f'<line x1="296" y1="490" x2="358" y2="490" stroke="{COBALTO}" '
        'stroke-width="2.5" marker-end="url(#flecha)"/>',
        '<defs><marker id="flecha" markerWidth="10" markerHeight="10" refX="8" '
        f'refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{COBALTO}"/></marker></defs>',
    ]

    lineas += _conexiones(entrada, oculta) + _conexiones(oculta, salida)
    lineas += [
        f'<circle cx="{x}" cy="{y}" r="14" fill="{COBALTO}" opacity="0.85"/>'
        for x, y in entrada
    ] + [f'<circle cx="{x}" cy="{y}" r="15" fill="{COBALTO}"/>' for x, y in oculta] + [
        f'<circle cx="{x}" cy="{y}" r="17" fill="{LIMA}" stroke="{TINTA}" stroke-width="2"/>'
        for x, y in salida
    ]

    for x, texto, sub in [
        (380, "Entrada", "8 características"),
        (840, "Capa oculta", "8 neuronas · ReLU"),
        (1270, "Salida", "2 montos"),
    ]:
        lineas += [
            f'<text x="{x}" y="190" text-anchor="middle" font-size="24" '
            f'font-weight="700" fill="{TINTA}">{texto}</text>',
            f'<text x="{x}" y="222" text-anchor="middle" font-size="17" '
            f'fill="{GRIS}">{sub}</text>',
        ]

    lineas += [
        f'<text x="1310" y="348" font-size="20" fill="{TINTA}">recibido</text>',
        f'<text x="1310" y="508" font-size="20" fill="{TINTA}">enviado</text>',
        f'<text x="60" y="836" font-size="18" fill="{GRIS}">Cada línea es un peso: '
        "8 × 8 = 64 en la primera capa y 8 × 2 = 16 en la segunda.</text>",
    ]
    lineas.append("</svg>")
    return "\n".join(lineas)


def figura_capas(
    caracteristicas: list[float], ocultas: list[float], salidas: list[float], escala: float
) -> str:
    """Las tres capas con los números reales de un ejemplo de prueba del dataset."""
    lineas = _cabecera(
        1600,
        820,
        "Un mes de ejemplo, capa por capa",
        "las ocho características, las ocho activaciones ocultas y los dos montos estimados",
    )

    # Panel 1: las ocho características con su nombre y su valor.
    for indice, (nombre, valor) in enumerate(zip(CAMPOS, caracteristicas, strict=True)):
        y0 = 250 + indice * 68
        ancho = max(2.0, min(220.0, 60 + abs(valor) * 40))
        opacidad = 0.35 + min(0.65, abs(valor) / 4)
        lineas += [
            f'<text x="80" y="{y0 + 24}" font-size="18" fill="{TINTA}">'
            f"{NOMBRES[nombre]}</text>",
            f'<rect x="520" y="{y0}" width="220" height="34" rx="8" fill="#eef2ff"/>',
            f'<rect x="520" y="{y0}" width="{ancho:.0f}" height="34" rx="8" '
            f'fill="{COBALTO}" opacity="{opacidad:.2f}"/>',
            f'<text x="760" y="{y0 + 24}" font-size="16" fill="{GRIS}">{valor:+.3f}</text>',
        ]
    lineas += [
        f'<text x="80" y="212" font-size="21" font-weight="700" fill="{TINTA}">'
        "Entrada · 8</text>",
    ]

    # Panel 2: las ocho activaciones ocultas.
    maximo = max(ocultas) or 1.0
    for indice, valor in enumerate(ocultas):
        fila, columna = divmod(indice, 4)
        x0 = 900 + columna * 82
        y0 = 280 + fila * 82
        opacidad = round(0.10 + 0.9 * (valor / maximo), 3) if valor else 0.06
        lineas += [
            f'<rect x="{x0}" y="{y0}" width="70" height="70" rx="14" fill="{COBALTO}" '
            f'opacity="{opacidad}"/>',
        ]
    lineas += [
        f'<text x="900" y="212" font-size="21" font-weight="700" fill="{TINTA}">'
        "Oculta · 8 (ReLU)</text>",
        f'<text x="900" y="600" font-size="16" fill="{GRIS}">lo que la red combina '
        "antes de estimar</text>",
    ]

    # Panel 3: los dos montos estimados, en pesos.
    for indice, (nombre, valor) in enumerate(zip(("recibido", "enviado"), salidas, strict=True)):
        y0 = 280 + indice * 150
        monto = valor * escala
        lineas += [
            f'<text x="1300" y="{y0 + 24}" font-size="19" fill="{TINTA}">{nombre}</text>',
            f'<text x="1300" y="{y0 + 62}" font-size="26" font-weight="700" '
            f'fill="{COBALTO}">{monto:,.0f}</text>',
            f'<text x="1300" y="{y0 + 86}" font-size="15" fill="{GRIS}">'
            f"{valor:.2f} × escala</text>",
        ]
    lineas += [
        f'<text x="1300" y="212" font-size="21" font-weight="700" fill="{TINTA}">'
        "Salida · 2</text>",
        f'<text x="1300" y="600" font-size="16" fill="{GRIS}">montos del próximo mes</text>',
    ]
    lineas.append("</svg>")
    return "\n".join(lineas)


def main() -> None:
    """Carga el modelo, calcula un mes de ejemplo y escribe las dos figuras."""
    import numpy as np
    import tensorflow as tf

    from dataset.exportar import leer
    from red_neuronal.modelo import RUTA_DEL_MODELO, cargar_modelo

    if not RUTA_DEL_MODELO.exists():
        raise SystemExit(
            f"No hay modelo entrenado en {RUTA_DEL_MODELO}: "
            "corra `.venv-tf/bin/python -m red_neuronal.entrenar` primero."
        )

    modelo = cargar_modelo()
    # El último ejemplo de prueba: un mes que el modelo no vio al entrenar.
    prueba = leer(Path("dataset") / "modelo", "ejemplos_prueba")
    entradas = prueba[list(CAMPOS)].to_numpy(dtype="float32").tolist()
    escalas = prueba["escala"].tolist()
    ejemplo = np.array([entradas[-1]], dtype="float32")
    # La capa oculta recibe las entradas ya estandarizadas: se lee su salida desde la
    # entrada del modelo y no aplicándola sola a las proporciones crudas.
    hasta_la_oculta = tf.keras.Model(modelo.inputs, modelo.get_layer("oculta").output)
    ocultas = hasta_la_oculta(ejemplo).numpy()[0]
    salidas = modelo.predict(ejemplo, verbose=0)[0]

    RUTA_DE_FIGURAS.mkdir(parents=True, exist_ok=True)
    (RUTA_DE_FIGURAS / "red-neuronal-general.svg").write_text(
        figura_general(), encoding="utf-8"
    )
    (RUTA_DE_FIGURAS / "red-neuronal-capas.svg").write_text(
        figura_capas(entradas[-1], ocultas.tolist(), salidas.tolist(), escalas[-1]),
        encoding="utf-8",
    )
    print(f"escala del ejemplo: {escalas[-1]:.2f}")
    print(f"salidas: {salidas.round(3).tolist()}")
    print(f"figuras en {RUTA_DE_FIGURAS}/")


if __name__ == "__main__":
    main()
