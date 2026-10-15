"""Sabotaje guiado: altera el ledger a propósito y narra qué detecta la cadena.

Es una herramienta de verificación y demostración, no parte del camino de la
aplicación: nadie que use el sistema pasa por aquí. Existe para mostrar en una sola
corrida lo que las pruebas afirman por separado —incluidos los límites, que son los
casos que el sistema **no** detecta— y para que el grupo pueda pararse en cada caso,
mirar el navegador y ver el dictamen antes de seguir.

Cada caso está declarado como un dato: qué hace, qué mirar, qué se espera, si detecta
o no y por qué, si es destructivo, cómo se aplica y cómo se restaura. La narración es
una consecuencia del catálogo y no al revés, así que el mismo recorrido sirve para una
persona que mira el navegador y para una corrida sin nadie enfrente.

Uso: `python -m src.sabotaje` (interactivo), `--sin-pausas` (sin esperar a nadie),
`--destructivos` (agrega los tres casos que borran datos).
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from src.persistence.factory import database_url, ledger

# Los tres veredictos posibles. Los dos primeros los dicta la verificación de la
# cadena; el tercero lo dicta el motor, que ni siquiera deja entrar la fila.
CADENA_VALIDA = "cadena-valida"
CADENA_INVALIDA = "cadena-invalida"
MOTOR_RECHAZA = "motor-rechaza"

# Dirección que la persona tiene que mirar en el navegador entre caso y caso.
VERIFICACION = "http://127.0.0.1:5000/verificar"

# Clase SQLSTATE de las violaciones de restricción: integridad, clave foránea,
# unicidad y CHECK. Es la que el motor levanta cuando rechaza una fila antes de
# guardarla, y es el desenlace esperado de los casos `motor-rechaza`.
VIOLACION_DE_RESTRICCION = "23"

# Las marcas de la narración son texto plano (`ok`, `coincide`, `no coincide`), sin
# emojis ni símbolos decorativos: la consola de Windows no los dibuja.

# Las columnas de `transactions`, en el orden en que las arman las consultas de este
# módulo. Tenerlas en un solo lugar es lo que permite capturar una fila y volver a
# insertarla tal cual.
COLUMNAS_TRANSACCION = (
    "id",
    "sender_id",
    "receiver_id",
    "amount",
    "status",
    "signature",
    "block_id",
    "created_at",
)

SQL_TRANSACCION = (
    "SELECT {columnas} FROM transactions"
)
# Las columnas con su tabla, para las consultas que unen transacciones con bloques: el
# `ORDER BY` tiene que ir sobre `block_index` y no sobre `block_id`, porque los
# identificadores son aleatorios y no siguen el orden de la cadena.
COLUMNAS_CON_TABLA = (
    "t.id, t.sender_id, t.receiver_id, t.amount, t.status, t.signature, t.block_id, t.created_at"
)
SQL_TRANSACCION_CON_BLOQUE = (
    "SELECT {columnas} FROM transactions t JOIN blocks b ON b.id = t.block_id"
)
# El bloque con su marca de tiempo: el hash la cubre, así que reponer un bloque exige
# reponer también el instante con el que se calculó. Dejarlo en el valor por defecto
# del esquema reinsertaría un bloque con otro hash recalculado.
SQL_BLOQUES = (
    "SELECT id, block_index, timestamp, previous_hash, hash FROM blocks ORDER BY block_index"
)
SQL_UNA_WALLET = "SELECT id, public_key FROM wallets ORDER BY id LIMIT 1"
SQL_DOS_WALLETS = "SELECT id, public_key FROM wallets ORDER BY id LIMIT 2"


@dataclass(frozen=True, slots=True)
class Caso:
    """Un caso de sabotaje, declarado como dato y separado de la narración.

    `aplicar` devuelve la descripción de lo que hizo, o levanta el error del motor,
    que es el resultado esperado de los casos `motor-rechaza`; `restaurar` deja la
    base como estaba. `limite` es obligatorio cuando el caso no se detecta: un caso
    que el sistema no ve sin decir por qué es un olvido, no un límite.
    """

    clave: str
    titulo: str
    que_hace: str
    que_mirar: str
    esperado: str
    bloque_esperado: int | None
    limite: str | None
    destructivo: bool
    aplicar: Callable[[Herramienta, EstadoCaso], str]
    restaurar: Callable[[Herramienta, EstadoCaso], str]


@dataclass(slots=True)
class EstadoCaso:
    """Lo que un caso necesita recordar entre aplicarse y restaurarse.

    Los casos que borran filas no pueden reponerlas desde la base —ya no están—, así
    que guardan aquí lo que sacaron. El estado es de cada caso y se descarta al
    terminar: la restauración repone el contenido original, no una reconstrucción.
    """

    valores: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResultadoCaso:
    """Lo que pasó con un caso: si coincidió con lo declarado y si restauró."""

    clave: str
    esperado: str
    observado: str
    bloque_observado: int | None
    coincide: bool
    restaurado: bool
    detalle: str


@dataclass(frozen=True, slots=True)
class Recorrido:
    """El resultado de una corrida, para que las pruebas lo lean sin parsear la salida."""

    detenido_por_la_comprobacion_previa: bool
    resultados: tuple[ResultadoCaso, ...]
    detectados: int
    no_detectados: int


class Herramienta:
    """La conexión propia de la herramienta: el SQL directo y la verificación del ledger.

    La conexión sale de `factory.database_url()` —la misma cadena que usa la
    aplicación— pero es otra conexión, y va en autocommit: el sabotaje tiene que estar
    escrito cuando la verificación lea, porque son dos conexiones distintas. La
    verificación de la cadena sí pasa por `factory.ledger()`, que es el camino real de
    la aplicación (REQ-10, REQ-22).
    """

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def uno(self, consulta: Any, parametros: tuple = ()) -> tuple:
        """Ejecuta una consulta que devuelve una fila; falla si no hay ninguna."""
        fila = self._connection.execute(consulta, parametros).fetchone()
        if fila is None:
            raise LookupError("la consulta no encontró ninguna fila")
        return fila

    def todos(self, consulta: Any, parametros: tuple = ()) -> list[tuple]:
        """Ejecuta una consulta que devuelve varias filas."""
        return self._connection.execute(consulta, parametros).fetchall()

    def ejecutar(self, consulta: Any, parametros: tuple = ()) -> None:
        """Ejecuta una escritura directa; el error del motor sube sin traducir (REQ-19)."""
        self._connection.execute(consulta, parametros)

    def capturas(self) -> int:
        """Cuántos bloques hay, para informar el estado antes y después."""
        return self.uno("SELECT count(*) FROM blocks")[0]

    def transacciones(self) -> int:
        """Cuántas transacciones hay, para informar el estado antes y después."""
        return self.uno("SELECT count(*) FROM transactions")[0]

    def reporte(self):
        """La verificación de la cadena por el camino real de la aplicación (REQ-10, REQ-22)."""
        with ledger() as chain:
            return chain.verify_chain()

    def cadena_valida(self) -> bool:
        """Si la cadena verifica como válida ahora mismo."""
        return self.reporte().valid


@contextmanager
def abrir() -> Iterator[Sabotaje]:
    """Abre la herramienta con su propia conexión, lista para sabotear y verificar.

    Devuelve el recorrido armado y no la conexión suelta: quien la abre quiere correr
    casos, y cerrar la conexión es responsabilidad de este contexto.
    """
    with psycopg.connect(database_url(), autocommit=True) as connection:
        # La marca de tiempo de los bloques se lee como `TIMESTAMPTZ` y el hash cubre
        # su `isoformat()`: sin UTC, la misma fila se leería con otro desplazamiento y
        # una cadena válida se vería alterada. La conexión del ledger hace lo mismo.
        connection.execute("SET TIME ZONE 'UTC'")
        yield Sabotaje(Herramienta(connection))


def _firma_inventada() -> str:
    """Una firma con la forma de una real pero imposible: no la produjo ninguna privada."""
    return "0" * 128


def _insertar_transaccion(herramienta: Herramienta, valores: Sequence) -> None:
    """Inserta una fila completa de `transactions` con los valores capturados."""
    herramienta.ejecutar(
        sql.SQL("INSERT INTO transactions ({}) VALUES ({})").format(
            sql.SQL(", ").join(sql.Identifier(columna) for columna in COLUMNAS_TRANSACCION),
            sql.SQL(", ").join(sql.Placeholder() for _ in COLUMNAS_TRANSACCION),
        ),
        tuple(valores),
    )


def _insertar_bloque(herramienta: Herramienta, valores: Sequence) -> None:
    """Inserta un bloque tal como se capturó, marca de tiempo incluida.

    La marca de tiempo no puede quedar en el valor por defecto del esquema: el hash
    del bloque cubre su `isoformat()`, así que un bloque repuesto sin su instante
    original deja de coincidir con el hash que ya estaba guardado.
    """
    herramienta.ejecutar(
        "INSERT INTO blocks (id, block_index, timestamp, previous_hash, hash) "
        "VALUES (%s, %s, %s, %s, %s)",
        tuple(valores),
    )


def _transacciones_de(herramienta: Herramienta, block_id: UUID) -> list[tuple]:
    """Las filas completas de las transacciones de un bloque, para poder reponerlas.

    Se filtra por estado en vez de por `block_id`: una transacción movida a otro
    bloque no cumple la coherencia estado/bloque del esquema —`confirmed` exige
    bloque y lo conserva—, así que la columna no sirve para reconocer la fila que el
    caso tocó. El único estado coherente con un bloque es `confirmed`.
    """
    return herramienta.todos(
        SQL_TRANSACCION.format(columnas=", ".join(COLUMNAS_TRANSACCION))
        + " WHERE status = 'confirmed' AND block_id IS NOT NULL AND block_id = %s ORDER BY id",
        (block_id,),
    )


def _una_confirmada(herramienta: Herramienta) -> tuple:
    """Una transacción confirmada: la del primer bloque que agrupó, que es la del índice 1.

    El orden es por bloque ascendente y no por el más reciente para que el caso caiga
    siempre en el mismo eslabón de la demostración —el bloque 1, el primero con
    contenido— y no dependa de cuántos aportes y retiros sembró el arranque.

    La coherencia estado/bloque del esquema garantiza que una fila `confirmed` tiene
    bloque y una `pending` no, así que el predicado del estado alcanza para leer las
    transacciones que un bloque agrupa.
    """
    return herramienta.uno(
        SQL_TRANSACCION_CON_BLOQUE.format(columnas=COLUMNAS_CON_TABLA)
        + " WHERE t.status = 'confirmed' ORDER BY b.block_index, t.id LIMIT 1"
    )


# ---------------------------------------------------------------------------
# Los once casos: qué hace cada uno y cómo se deshace
# ---------------------------------------------------------------------------


def _aplicar_alterar_monto(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Suma uno al monto de una transacción confirmada."""
    objetivo = _una_confirmada(herramienta)
    estado.valores["id"] = objetivo[0]
    herramienta.ejecutar(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s", (objetivo[0],)
    )
    return f"el monto de la transacción {objetivo[0]} pasó de {objetivo[3]} a {objetivo[3] + 1}"


def _restaurar_alterar_monto(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Repone el monto, que es el único valor que la alteración tocó.

    La resta se aplica a la fila capturada y no a una relectura: la transacción sigue
    teniendo estado `confirmed`, así que nada la confunde con otra.
    """
    herramienta.ejecutar(
        "UPDATE transactions SET amount = amount - 1 WHERE id = %s", (estado.valores["id"],)
    )
    return f"la transacción {estado.valores['id']} volvió a su monto original"



def _aplicar_alterar_hash(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Escribe sesenta y cuatro ceros como hash de un bloque."""
    bloque = herramienta.todos(SQL_BLOQUES)[1]
    estado.valores["bloque"] = bloque
    herramienta.ejecutar("UPDATE blocks SET hash = %s WHERE id = %s", ("0" * 64, bloque[0]))
    return f"el hash del bloque {bloque[1]} pasó a sesenta y cuatro ceros"


def _restaurar_alterar_hash(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Repone el hash capturado antes de alterarlo: el original ya no está en la base."""
    bloque = estado.valores["bloque"]
    herramienta.ejecutar("UPDATE blocks SET hash = %s WHERE id = %s", (bloque[4], bloque[0]))
    return f"el hash del bloque {bloque[1]} volvió a su valor"


def _aplicar_mover_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Mueve una transacción confirmada al bloque génesis."""
    objetivo = _una_confirmada(herramienta)
    genesis = herramienta.todos(SQL_BLOQUES)[0]
    estado.valores["id"] = objetivo[0]
    estado.valores["block_id"] = objetivo[6]
    herramienta.ejecutar(
        "UPDATE transactions SET block_id = %s WHERE id = %s", (genesis[0], objetivo[0])
    )
    return f"la transacción {objetivo[0]} se movió del bloque {objetivo[6]} al {genesis[1]}"


def _restaurar_mover_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Devuelve la transacción a su bloque original, que el caso capturó."""
    herramienta.ejecutar(
        "UPDATE transactions SET block_id = %s WHERE id = %s",
        (estado.valores["block_id"], estado.valores["id"]),
    )
    return f"la transacción {estado.valores['id']} volvió a su bloque original"


def _aplicar_borrar_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra una transacción confirmada."""
    objetivo = _una_confirmada(herramienta)
    estado.valores["fila"] = objetivo
    herramienta.ejecutar("DELETE FROM transactions WHERE id = %s", (objetivo[0],))
    return f"se borró la transacción confirmada {objetivo[0]} del bloque {objetivo[6]}"


def _restaurar_borrar_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Reinserta la fila borrada con los valores que se capturaron antes de borrarla."""
    _insertar_transaccion(herramienta, estado.valores["fila"])
    return "se reinsertó la transacción borrada"


def _aplicar_insertar_confirmada_falsa(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Confirma una transacción con firma inventada dentro de un bloque."""
    bloque = herramienta.todos(SQL_BLOQUES)[-1]
    emisor, receptor = herramienta.todos(SQL_DOS_WALLETS)
    fila = (
        uuid.uuid4(),
        emisor[0],
        receptor[0],
        Decimal("1.50000000"),
        "confirmed",
        _firma_inventada(),
        bloque[0],
        datetime.now(UTC),
    )
    _insertar_transaccion(herramienta, fila)
    return f"se confirmó una transacción con firma inventada dentro del bloque {bloque[1]}"


def _restaurar_insertar_confirmada_falsa(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra la fila inventada, que se reconoce por su firma: ninguna otra la tiene."""
    herramienta.ejecutar("DELETE FROM transactions WHERE signature = %s", (_firma_inventada(),))
    return "se borró la transacción de firma inventada"


def _aplicar_reutilizar_firma(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Inserta con una firma que ya está registrada."""
    firma = herramienta.uno(
        "SELECT signature FROM transactions WHERE signature <> '' LIMIT 1"
    )[0]
    emisor, receptor = herramienta.todos(SQL_DOS_WALLETS)
    _insertar_transaccion(
        herramienta,
        (
            uuid.uuid4(),
            emisor[0],
            receptor[0],
            Decimal("2.00000000"),
            "pending",
            firma,
            None,
            datetime.now(UTC),
        ),
    )
    return "se intentó insertar una transacción con una firma ya registrada"


def _restaurar_reutilizar_firma(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """No hay nada que restaurar: el motor rechazó la fila y no quedó nada escrito."""
    return "no se escribió nada"


def _aplicar_violar_regla(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Inserta con el mismo emisor y receptor."""
    wallet = herramienta.uno(SQL_UNA_WALLET)
    _insertar_transaccion(
        herramienta,
        (
            uuid.uuid4(),
            wallet[0],
            wallet[0],
            Decimal("3.00000000"),
            "pending",
            _firma_inventada(),
            None,
            datetime.now(UTC),
        ),
    )
    return "se intentó insertar una transacción con el mismo emisor y receptor"


def _restaurar_violar_regla(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """No hay nada que restaurar: el CHECK del esquema rechazó la fila."""
    return "no se escribió nada"


def _aplicar_cambiar_llave_wallet(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Cambia la pública de una wallet."""
    wallet = herramienta.uno(SQL_UNA_WALLET)
    estado.valores["id"] = wallet[0]
    estado.valores["public_key"] = wallet[1]
    # La pública nueva no puede coincidir con ninguna registrada porque el esquema
    # tiene un índice único sobre ella: sesenta y seis ceros no son la de nadie.
    herramienta.ejecutar("UPDATE wallets SET public_key = %s WHERE id = %s", ("0" * 66, wallet[0]))
    return f"la pública de la wallet {wallet[0]} pasó a sesenta y seis ceros"


def _restaurar_cambiar_llave_wallet(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Repone la pública original, que el caso capturó antes de cambiarla."""
    herramienta.ejecutar(
        "UPDATE wallets SET public_key = %s WHERE id = %s",
        (estado.valores["public_key"], estado.valores["id"]),
    )
    return "la pública de la wallet volvió a su valor"


def _aplicar_pendiente_firma_invalida(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Inserta en el pool una pendiente con firma inventada."""
    emisor, receptor = herramienta.todos(SQL_DOS_WALLETS)
    _insertar_transaccion(
        herramienta,
        (
            uuid.uuid4(),
            emisor[0],
            receptor[0],
            Decimal("4.00000000"),
            "pending",
            _firma_inventada(),
            None,
            datetime.now(UTC),
        ),
    )
    return "se insertó una transacción pendiente con firma inventada"


def _restaurar_pendiente_firma_invalida(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra la fila del pool, que se reconoce por su firma inventada."""
    herramienta.ejecutar("DELETE FROM transactions WHERE signature = %s", (_firma_inventada(),))
    return "se borró la pendiente de firma inventada"


def _aplicar_borrar_genesis(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra el bloque índice 0."""
    genesis = herramienta.todos(SQL_BLOQUES)[0]
    estado.valores["bloque"] = genesis
    herramienta.ejecutar("DELETE FROM blocks WHERE id = %s", (genesis[0],))
    return "se borró el bloque génesis, la cabeza de la cadena"


def _restaurar_borrar_genesis(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Reinserta el génesis con su índice, su hash previo y su hash propios."""
    _insertar_bloque(herramienta, estado.valores["bloque"])
    return "se reinsertó el bloque génesis"


def _aplicar_truncar_cola(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra el último bloque y sus transacciones."""
    punta = herramienta.todos(SQL_BLOQUES)[-1]
    estado.valores["bloque"] = punta
    estado.valores["filas"] = _transacciones_de(herramienta, punta[0])
    herramienta.ejecutar("DELETE FROM transactions WHERE block_id = %s", (punta[0],))
    herramienta.ejecutar("DELETE FROM blocks WHERE id = %s", (punta[0],))
    return f"se borró el bloque {punta[1]}, la punta de la cadena, y sus transacciones"


def _restaurar_truncar_cola(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Reinserta el bloque y sus transacciones, con los valores capturados."""
    _insertar_bloque(herramienta, estado.valores["bloque"])
    for fila in estado.valores["filas"]:
        _insertar_transaccion(herramienta, fila)
    return "se reinsertaron el bloque y sus transacciones"


CASOS: tuple[Caso, ...] = (
    Caso(
        clave="alterar-monto",
        titulo="Alterar el monto de una transacción confirmada",
        que_hace="suma uno al monto de una transacción confirmada, por SQL directo",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=1,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_alterar_monto,
        restaurar=_restaurar_alterar_monto,
    ),
    Caso(
        clave="alterar-hash",
        titulo="Alterar el hash de un bloque",
        que_hace="escribe sesenta y cuatro ceros como hash de un bloque",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=1,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_alterar_hash,
        restaurar=_restaurar_alterar_hash,
    ),
    Caso(
        clave="mover-transaccion",
        titulo="Mover una transacción confirmada a otro bloque",
        que_hace="mueve una transacción confirmada al bloque génesis",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=None,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_mover_transaccion,
        restaurar=_restaurar_mover_transaccion,
    ),
    Caso(
        clave="borrar-transaccion",
        titulo="Borrar una transacción confirmada",
        que_hace="borra una transacción confirmada, que era parte del contenido de su bloque",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=None,
        limite=None,
        destructivo=True,
        aplicar=_aplicar_borrar_transaccion,
        restaurar=_restaurar_borrar_transaccion,
    ),
    Caso(
        clave="insertar-confirmada-falsa",
        titulo="Confirmar una transacción con firma inventada",
        que_hace="inserta una transacción confirmada, con firma inventada, dentro de un bloque",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=None,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_insertar_confirmada_falsa,
        restaurar=_restaurar_insertar_confirmada_falsa,
    ),
    Caso(
        clave="reutilizar-firma",
        titulo="Reutilizar una firma ya registrada",
        que_hace="intenta insertar una transacción con una firma que ya existe",
        que_mirar="el error del motor en esta consola: el índice único de la firma",
        esperado=MOTOR_RECHAZA,
        bloque_esperado=None,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_reutilizar_firma,
        restaurar=_restaurar_reutilizar_firma,
    ),
    Caso(
        clave="violar-regla",
        titulo="Insertar con el mismo emisor y receptor",
        que_hace="intenta insertar una transacción con el mismo emisor y receptor",
        que_mirar="el error del motor en esta consola: el CHECK del esquema",
        esperado=MOTOR_RECHAZA,
        bloque_esperado=None,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_violar_regla,
        restaurar=_restaurar_violar_regla,
    ),
    Caso(
        clave="cambiar-llave-wallet",
        titulo="Cambiar la llave pública de una wallet",
        que_hace="cambia la pública de una wallet registrada",
        que_mirar="que /verificar sigue diciendo que la cadena es válida",
        esperado=CADENA_VALIDA,
        bloque_esperado=None,
        limite=(
            "el hash del bloque cubre las transacciones agrupadas, no el registro de "
            "wallets: cambiar una pública no cambia ningún hash, así que la verificación "
            "no tiene con qué notarlo"
        ),
        destructivo=False,
        aplicar=_aplicar_cambiar_llave_wallet,
        restaurar=_restaurar_cambiar_llave_wallet,
    ),
    Caso(
        clave="pendiente-firma-invalida",
        titulo="Insertar una pendiente con firma inventada",
        que_hace="inserta en el pool una transacción pendiente con firma inventada",
        que_mirar="que /verificar sigue diciendo que la cadena es válida",
        esperado=CADENA_VALIDA,
        bloque_esperado=None,
        limite=(
            "la verificación mira los bloques, no el pool: lo que no está agrupado no "
            "está en ningún hash que recalcular"
        ),
        destructivo=False,
        aplicar=_aplicar_pendiente_firma_invalida,
        restaurar=_restaurar_pendiente_firma_invalida,
    ),
    Caso(
        clave="borrar-genesis",
        titulo="Borrar el bloque génesis",
        que_hace="borra el bloque índice 0, que es la cabeza de la cadena",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=None,
        limite=None,
        destructivo=True,
        aplicar=_aplicar_borrar_genesis,
        restaurar=_restaurar_borrar_genesis,
    ),
    Caso(
        clave="truncar-cola",
        titulo="Truncar la cola de la cadena",
        que_hace="borra el último bloque y todas sus transacciones",
        que_mirar="que /verificar sigue diciendo que la cadena es válida",
        esperado=CADENA_VALIDA,
        bloque_esperado=None,
        limite=(
            "sin un ancla externa no hay con qué comparar: el historial no guarda cuál "
            "era el último bloque, así que una cadena recortada por la cola es "
            "indistinguible de una que nunca tuvo esos bloques"
        ),
        destructivo=True,
        aplicar=_aplicar_truncar_cola,
        restaurar=_restaurar_truncar_cola,
    ),
)


def casos_no_detectados() -> tuple[Caso, ...]:
    """Los casos que el sistema no detecta: son `cadena-valida` y traen su porqué."""
    return tuple(caso for caso in CASOS if caso.esperado == CADENA_VALIDA)


def caso_de(clave: str) -> Caso:
    """El caso del catálogo con esa clave."""
    for caso in CASOS:
        if caso.clave == clave:
            return caso
    raise KeyError(f"no hay ningún caso con la clave {clave}")


def esperado_de(clave: str) -> str:
    """El veredicto declarado de un caso, por su clave."""
    return caso_de(clave).esperado


# ---------------------------------------------------------------------------
# La narración: la salida se arma con el catálogo, no se escribe a mano por caso
# ---------------------------------------------------------------------------

# Ancho de la etiqueta de cada línea, para que los valores queden alineados.
ANCHO_ETIQUETA = 10


class Salida:
    """A dónde va la narración: a la consola o a un colector de pruebas.

    Se envuelve en un objeto y no en una función suelta porque la pausa y el resultado
    escriben en el mismo destino, y el destino por defecto —la consola— tiene que
    seguir siendo el de `print`.
    """

    def __init__(self, escribir: Callable[[str], None] | None = None) -> None:
        self._escribir = escribir

    def linea(self, mensaje: str) -> None:
        """Escribe una línea; con el destino por defecto, por la salida estándar."""
        if self._escribir is None:
            print(mensaje, file=sys.stdout)
        else:
            self._escribir(mensaje)


def probar_web(url: str = VERIFICACION, tiempo_de_espera: float = 3.0) -> tuple[bool, str]:
    """Pide `/verificar` y devuelve si respondió HTTP 200, con la descripción del desenlace.

    Es la comprobación de que hay algo que mirar: la pausa de cada caso existe para
    que alguien vea el dictamen en el navegador, así que sin aplicación corriendo la
    herramienta se detiene y dice cómo levantarla, en vez de sabotear a ciegas.
    """
    try:
        with urllib.request.urlopen(url, timeout=tiempo_de_espera) as respuesta:
            if respuesta.status == 200:
                return True, "la aplicación respondió HTTP 200 en /verificar"
            return False, f"la aplicación respondió HTTP {respuesta.status} en /verificar"
    except urllib.error.HTTPError as error:
        return False, f"la aplicación respondió HTTP {error.code} en /verificar"
    except (urllib.error.URLError, OSError) as error:
        return False, f"la aplicación no respondió en {url}: {error}"


def _texto_del_esperado(caso: Caso) -> str:
    """Lo que tiene que pasar, en palabras, según el veredicto declarado."""
    if caso.esperado == MOTOR_RECHAZA:
        return "el motor rechaza la fila y no queda nada escrito"
    if caso.esperado == CADENA_INVALIDA:
        esperado = "la cadena queda inválida"
        if caso.bloque_esperado is not None:
            esperado += f" y el bloque señalado es el {caso.bloque_esperado}"
        return esperado
    return "la cadena sigue válida: este caso no se detecta"


def _mostrar_caso(
    caso: Caso, indice: int, total: int, pausa: bool, entrada, salida: Salida
) -> None:
    """Narra un caso: qué hace, qué mirar, qué se espera y, si corresponde, la pausa."""
    salida.linea(f"[{indice}/{total}] {caso.titulo} ({caso.clave})")
    salida.linea(f"{'que hace':<{ANCHO_ETIQUETA}}: {caso.que_hace}")
    # La dirección de la verificación solo se agrega cuando el caso pide mirarla: los
    # casos que rechaza el motor se ven en esta misma consola y nombrar la página
    # mandaría a mirar donde no pasa nada.
    donde = f" en {VERIFICACION}" if caso.esperado != MOTOR_RECHAZA else ""
    salida.linea(f"{'que mirar':<{ANCHO_ETIQUETA}}: {caso.que_mirar}{donde}")
    salida.linea(f"{'se espera':<{ANCHO_ETIQUETA}}: {_texto_del_esperado(caso)}")
    if caso.limite is not None:
        salida.linea(f"{'limite':<{ANCHO_ETIQUETA}}: {caso.limite}")
    if pausa:
        _esperar_enter(entrada, salida)


def _esperar_enter(entrada, salida: Salida) -> None:
    """Espera un Enter para que la persona mire el navegador antes de seguir.

    Solo espera si la entrada es un terminal. En una corrida con guion o desde la
    suite no hay nadie que pueda pulsar Enter, y esperar de todos modos colgaría el
    proceso para siempre; en ese caso se dice y se sigue sin pausas.
    """
    flujo = sys.stdin if entrada is None else entrada
    if not flujo.isatty():
        salida.linea("pausa: no hay terminal donde esperar un Enter; sigo sin pausas")
        return
    salida.linea("pausa: pulse Enter cuando haya mirado el navegador")
    try:
        flujo.readline()
    except EOFError:
        # La entrada se cerró entre la comprobación y la lectura: es el mismo caso sin
        # nadie enfrente, así que se sigue en vez de caer.
        salida.linea("pausa: la entrada se cerró; sigo sin pausas")


def _detectar_veredicto(herramienta: Herramienta) -> tuple[str, int | None]:
    """Observa la base y traduce el reporte de la verificación a un veredicto del catálogo."""
    reporte = herramienta.reporte()
    if reporte.valid:
        return CADENA_VALIDA, None
    return CADENA_INVALIDA, reporte.altered_block_index


def _comparar(caso: Caso, observado: str, indice: int | None) -> tuple[bool, str]:
    """Compara lo observado con lo que el caso declara; devuelve si coincide y el detalle."""
    if observado == MOTOR_RECHAZA:
        if caso.esperado == MOTOR_RECHAZA:
            return True, "el motor rechazó la fila, como estaba declarado"
        return False, "el motor rechazó una fila que tenía que entrar"
    if observado != caso.esperado:
        return False, f"se observó {observado} y se esperaba {caso.esperado}"
    if caso.bloque_esperado is not None and indice != caso.bloque_esperado:
        return False, f"el bloque señalado fue {indice} y se esperaba {caso.bloque_esperado}"
    return True, "coincide con lo declarado"


def _siguiente(
    herramienta: Herramienta, estado: EstadoCaso, caso: Caso, salida: Salida
) -> ResultadoCaso:
    """Aplica, observa, compara y restaura un caso; devuelve lo que pasó.

    El error del motor no se traduce: para los casos `motor-rechaza` es el desenlace
    esperado y el mensaje de PostgreSQL es la demostración (REQ-19). La restauración
    con los valores capturados y la comprobación posterior de que la cadena vuelve a
    ser válida se hacen en los dos desenlaces, para que la herramienta no deje el
    ledger roto aunque un caso no haya salido como estaba declarado.
    """
    observado = CADENA_VALIDA
    bloque: int | None = None
    try:
        hecho = caso.aplicar(herramienta, estado)
        salida.linea(f"{'se aplico':<{ANCHO_ETIQUETA}}: {hecho}")
    except psycopg.errors.Error as error:
        observado = MOTOR_RECHAZA
        salida.linea(f"{'se aplico':<{ANCHO_ETIQUETA}}: el motor rechazó la fila")
        salida.linea(
            f"{'el motor':<{ANCHO_ETIQUETA}}: {error.diag.sqlstate} {error.diag.message_primary}"
        )
    else:
        observado, bloque = _detectar_veredicto(herramienta)
        salida.linea(f"{'observado':<{ANCHO_ETIQUETA}}: {observado}")

    coincide, detalle = _comparar(caso, observado, bloque)
    marca = "coincide" if coincide else "no coincide"
    salida.linea(f"{'veredicto':<{ANCHO_ETIQUETA}}: {marca} ({detalle})")

    restaurado = False
    try:
        repuesto = caso.restaurar(herramienta, estado)
        salida.linea(f"{'restaurado':<{ANCHO_ETIQUETA}}: {repuesto}")
        restaurado = herramienta.cadena_valida()
        salida.linea(
            f"{'cadena':<{ANCHO_ETIQUETA}}: "
            + ("ok, vuelve a ser válida" if restaurado else "no volvió a ser válida")
        )
    except psycopg.errors.Error as error:
        salida.linea(f"{'restaurado':<{ANCHO_ETIQUETA}}: falló: {error}")
    return ResultadoCaso(
        clave=caso.clave,
        esperado=caso.esperado,
        observado=observado,
        bloque_observado=bloque,
        coincide=coincide,
        restaurado=restaurado,
        detalle=detalle,
    )


def _resumen(recorrido: Recorrido, salida: Salida) -> None:
    """El cierre: cuántos se detectaron, cuáles no y por qué."""
    salida.linea("")
    salida.linea("resumen")
    salida.linea(f"casos corridos: {len(recorrido.resultados)}")
    salida.linea(f"detectados: {recorrido.detectados}")
    salida.linea(f"no detectados: {recorrido.no_detectados}")
    for resultado in recorrido.resultados:
        if resultado.esperado != CADENA_VALIDA:
            continue
        caso = caso_de(resultado.clave)
        salida.linea(f"- {caso.clave}: no se detecta. {caso.limite}")


def _instrucciones_de_resembrado(salida: Salida) -> None:
    """Cómo volver a los datos de demostración, en orden, y qué tiene que decir la pantalla."""
    salida.linea("")
    salida.linea("para volver a los datos de demostración (resembrado)")
    salida.linea("1. baje los contenedores borrando el volumen de datos:")
    salida.linea("   docker compose down -v")
    salida.linea("   con Podman: podman compose down -v")
    salida.linea("2. vuelva a levantar los contenedores:")
    salida.linea("   docker compose up -d")
    salida.linea("   con Podman: podman compose up -d")
    salida.linea("3. siembre la demostración con el arranque del proyecto:")
    salida.linea("   <venv> -m src.bootstrap")
    salida.linea("4. levante la aplicación y mire la verificación:")
    salida.linea("   <venv> -m src.web")
    salida.linea(f"   {VERIFICACION} tiene que decir: La cadena es válida")


class Sabotaje:
    """El recorrido guiado: la comprobación previa, los casos y el cierre.

    Se arma con la herramienta abierta y ofrece `recorrido`, que es el camino que
    usan el punto de entrada y las pruebas: la única diferencia es si hay pausas y
    quién responde por la aplicación.
    """

    def __init__(self, herramienta: Herramienta) -> None:
        self._herramienta = herramienta
        self._estados: dict[str, EstadoCaso] = {}

    def __enter__(self) -> Sabotaje:
        """Se puede usar en un `with` como la herramienta que envuelve."""
        return self

    def __exit__(self, *excepcion) -> None:
        """No cierra nada: la conexión la cierra `abrir`, que es quien la abrió."""
        return None

    def cadena_valida(self) -> bool:
        """Si la cadena verifica como válida ahora mismo."""
        return self._herramienta.cadena_valida()

    def recorrido(
        self,
        *,
        claves: Sequence[str] | None = None,
        con_destructivos: bool = False,
        pausas: bool = True,
        web: Callable[[], bool] | None = None,
        entrada=None,
        salida: Callable[[str], None] | None = None,
    ) -> Recorrido:
        """Corre los casos pedidos, con o sin pausas, y devuelve lo que pasó.

        `web` responde por la aplicación —la sonda real pide HTTP 200 en
        `/verificar`— y `entrada` es de dónde se lee el Enter: las pruebas inyectan
        las dos para correr sin servidor y sin terminal. La comprobación previa va
        primero: sobre una cadena ya alterada o sin aplicación que responda no se
        corre ningún caso, porque el veredicto de cada uno dejaría de significar algo.
        """
        destino = Salida(salida)
        if not self._comprobar(destino, web):
            return Recorrido(True, (), 0, 0)

        elegidos = [
            caso
            for caso in CASOS
            if (claves is None or caso.clave in claves)
            and (con_destructivos or not caso.destructivo)
        ]
        if not con_destructivos:
            destructivos = ", ".join(caso.clave for caso in CASOS if caso.destructivo)
            destino.linea(f"los casos destructivos no se corren sin --destructivos: {destructivos}")
        # El aviso va una sola vez, antes del primer caso: sin terminal donde esperar
        # un Enter, la herramienta no puede quedarse esperando a nadie.
        if pausas and entrada is None and not sys.stdin.isatty():
            destino.linea("pausa: no hay terminal donde esperar un Enter; sigo sin pausas")

        resultados = []
        total = len(elegidos)
        for indice, caso in enumerate(elegidos, start=1):
            permiso_de_pausa = pausas and (entrada is not None or sys.stdin.isatty())
            _mostrar_caso(caso, indice, total, permiso_de_pausa, entrada, destino)
            estado = self._estados.setdefault(caso.clave, EstadoCaso(valores={}))
            resultados.append(_siguiente(self._herramienta, estado, caso, destino))
            destino.linea("")

        detectados = sum(1 for resultado in resultados if resultado.esperado != CADENA_VALIDA)
        recorrido = Recorrido(
            detenido_por_la_comprobacion_previa=False,
            resultados=tuple(resultados),
            detectados=detectados,
            no_detectados=len(resultados) - detectados,
        )
        _resumen(recorrido, destino)
        _instrucciones_de_resembrado(destino)
        return recorrido

    def _comprobar(self, salida: Salida, web: Callable[[], bool] | None) -> bool:
        """La comprobación previa: la cadena válida y la aplicación en pie.

        Devuelve si se puede empezar. Las dos condiciones se informan antes del primer
        caso: con una cadena ya alterada, el veredicto de los casos siguientes
        mezclaría la alteración ajena con la propia; sin aplicación, no hay nada que
        mirar en el navegador y la pausa no tendría sentido.
        """
        reporte = self._herramienta.reporte()
        salida.linea("comprobación previa")
        salida.linea(f"{'capturas':<{ANCHO_ETIQUETA}}: {self._herramienta.capturas()}")
        salida.linea(f"{'transacciones':<{ANCHO_ETIQUETA}}: {self._herramienta.transacciones()}")
        if not reporte.valid:
            salida.linea(
                "la cadena ya viene alterada: el bloque señalado es el "
                f"{reporte.altered_block_index}. Restaure o resiembre antes de sabotear; "
                "las instrucciones de resembrado están al final."
            )
            return False
        salida.linea("la cadena verifica como válida")

        if web is None:
            responde, detalle = probar_web()
        else:
            responde, detalle = web(), "la prueba respondió por la aplicación"
        salida.linea(f"{'aplicacion':<{ANCHO_ETIQUETA}}: {detalle}")
        if not responde:
            salida.linea(
                "la aplicación no responde en /verificar: levántela con "
                "`python -m src.web` en otra terminal y vuelva a correr esto."
            )
            return False
        return True


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada: `python -m src.sabotaje` y sus dos banderas.

    Interactivo por defecto: cada caso espera un Enter para que la persona mire el
    navegador. `--sin-pausas` corre el recorrido entero de una vez y `--destructivos`
    agrega los tres casos que borran datos.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.sabotaje",
        description=(
            "Sabotea el ledger a propósito, narra cada caso y dice qué se esperaba y "
            "qué pasó. No es parte del camino de la aplicación: es una herramienta de "
            "verificación y demostración."
        ),
    )
    parser.add_argument(
        "--sin-pausas",
        action="store_true",
        help="no espera un Enter entre caso y caso (para la suite o un guion cerrado)",
    )
    parser.add_argument(
        "--destructivos",
        action="store_true",
        help="agrega los tres casos que borran datos; sin esta bandera no se tocan",
    )
    opciones = parser.parse_args(argv)

    with abrir() as sabotaje:
        recorrido = sabotaje.recorrido(
            con_destructivos=opciones.destructivos, pausas=not opciones.sin_pausas
        )
    return 1 if recorrido.detenido_por_la_comprobacion_previa else 0


if __name__ == "__main__":
    sys.exit(main())
