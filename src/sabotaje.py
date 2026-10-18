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
`--destructivos` (agrega los tres casos que borran datos). La aplicación se mira en
`http://127.0.0.1:5000` salvo que la variable `SABOTAJE_APLICACION` diga otra
dirección. La sonda de la comprobación previa pide `/ingresar`, que es pública y no
sigue redirecciones: para mirar `/verificar` hay que tener una sesión de
administrador abierta en el navegador.
"""
from __future__ import annotations

import argparse
import os
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

# Dirección de la aplicación de este prototipo: la que levanta `python -m src.web`. Es
# solo el valor por defecto de la sonda y no una constante de la herramienta: el 5000
# puede estar tomado y un servidor de prueba puede escuchar en otro puerto, así que la
# variable del entorno manda cuando está.
APLICACION_POR_DEFECTO = "http://127.0.0.1:5000"

# Variable con la que se apunta la sonda a otra dirección. Se lee cada vez que hace
# falta y no al importar el módulo, para que se pueda fijar después.
VARIABLE_DE_LA_APLICACION = "SABOTAJE_APLICACION"

# Clase SQLSTATE de las violaciones de restricción: integridad, clave foránea,
# unicidad y CHECK. Es la que el motor levanta cuando rechaza una fila antes de
# guardarla, y es el desenlace esperado de los casos `motor-rechaza`.
VIOLACION_DE_RESTRICCION = "23"

# Veredicto de un error del motor que **no** es una violación de restricción. No está
# en el catálogo a propósito: un caso no puede declarar que espera una herramienta
# rota. La comparación lo trata como desacuerdo y la corrida termina en rojo.
ERROR_INESPERADO = "error-inesperado"

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

    `bloque_esperado` no guarda el índice sino cómo obtenerlo de lo que el caso
    alteró: el bloque donde vive la transacción que toca, el bloque cuyo hash cambia.
    Fijarlo acá ataría los dos casos que lo declaran a la forma del sembrado de
    demostración; derivarlo es lo que los deja coincidir con cualquier forma.
    """

    clave: str
    titulo: str
    que_hace: str
    que_mirar: str
    esperado: str
    bloque_esperado: Callable[[EstadoCaso], int | None] | None
    limite: str | None
    destructivo: bool
    aplicar: Callable[[Herramienta, EstadoCaso], str]
    restaurar: Callable[[Herramienta, EstadoCaso], str]
    comprobar: Callable[[Herramienta, EstadoCaso], None] | None = None


@dataclass(slots=True)
class EstadoCaso:
    """Lo que un caso necesita recordar entre aplicarse y restaurarse.

    Los casos que borran filas no pueden reponerlas desde la base —ya no están—, así
    que guardan aquí lo que sacaron. El estado es de cada caso y se descarta al
    terminar: la restauración repone el contenido original, no una reconstrucción.

    Los valores capturados son también con qué se **comprueba** la restauración: que la
    cadena vuelva a verificar es necesario pero no suficiente —un cambio que ningún
    hash cubre, como la pública de una wallet, pasaría inadvertido—, así que cada caso
    declara además cómo se verifica que su fila volvió a su contenido.
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
    """El resultado de una corrida, para que las pruebas lo lean sin parsear la salida.

    `detectados` y `no_detectados` se cuentan sobre lo **observado**, no sobre lo
    declarado: una corrida donde un caso no coincidió no puede informar el mismo
    veredicto que el catálogo promete. `desacuerdos` los cuenta aparte y gobierna el
    código de salida.
    """

    detenido_por_la_comprobacion_previa: bool
    resultados: tuple[ResultadoCaso, ...]
    detectados: int
    no_detectados: int
    desacuerdos: int


def codigo_de_salida(recorrido: Recorrido) -> int:
    """Código de salida del recorrido: cero solo si todo salió como estaba declarado.

    Un desacuerdo significa que la herramienta, el catálogo o el sistema no se
    comportaron como está escrito, así que la corrida tiene que fallar como falla una
    prueba: de lo contrario un caso roto termina en verde.
    """
    if recorrido.detenido_por_la_comprobacion_previa:
        return 1
    return 1 if recorrido.desacuerdos else 0


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


def _firma_inventada(caso: str) -> str:
    """Una firma con la forma de una real pero imposible, distinta para cada caso.

    No la produjo ninguna privada y lleva el nombre del caso en el prefijo, que es
    texto hexadecimal válido: dos casos que insertan una firma inventada no comparten
    firma, así que la restauración de uno no puede borrar la fila del otro.
    """
    marca = f"{caso[:8]:0<8}".lower()
    return marca + "0" * (128 - len(marca))


def _leer_transaccion(herramienta: Herramienta, transaction_id: UUID) -> tuple:
    """Vuelve a leer una transacción por su identificador, con todas sus columnas."""
    return herramienta.uno(
        SQL_TRANSACCION.format(columnas=", ".join(COLUMNAS_TRANSACCION)) + " WHERE id = %s",
        (transaction_id,),
    )


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
    estado.valores["amount"] = objetivo[3]
    # El bloque que la verificación tiene que señalar es el de esta transacción, y se
    # captura acá: es lo único que sabe cuál es, y el catálogo no puede declararlo sin
    # atarse a la forma del sembrado.
    estado.valores["bloque_esperado"] = herramienta.uno(
        "SELECT block_index FROM blocks WHERE id = %s", (objetivo[6],)
    )[0]
    herramienta.ejecutar(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s", (objetivo[0],)
    )
    return f"el monto de la transacción {objetivo[0]} pasó de {objetivo[3]} a {objetivo[3] + 1}"


def _restaurar_alterar_monto(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Repone el monto capturado, con su valor absoluto.

    Escribe el valor guardado y no `amount - 1`: con una pausa entre aplicar y
    restaurar, una resta sobre lo que haya en la fila deja de ser el inverso seguro
    de la suma —alcanza con que algo más la haya tocado— y reponer el valor original
    es lo único que garantiza el estado de antes.
    """
    if "amount" not in estado.valores:
        # La aplicación del caso no llegó a capturar nada: no hay monto que reponer y
        # tampoco hay nada que haya quedado alterado.
        return "no se había alterado ningún monto"
    herramienta.ejecutar(
        "UPDATE transactions SET amount = %s WHERE id = %s",
        (estado.valores["amount"], estado.valores["id"]),
    )
    return f"la transacción {estado.valores['id']} volvió a {estado.valores['amount']}"



def _aplicar_alterar_hash(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Escribe sesenta y cuatro ceros como hash del segundo bloque de la demostración.

    El objetivo es el segundo bloque, no «el bloque de índice 1»: la comprobación de
    forma garantiza que hay al menos dos, y el índice que se espera sale de la fila que
    se altera y no de una constante.
    """
    bloque = herramienta.todos(SQL_BLOQUES)[1]
    estado.valores["bloque"] = bloque
    # El índice esperado es el del bloque que se altera, no el de una constante: si el
    # caso cambiara de eslabón, la comparación tiene que seguir apuntando al que tocó.
    estado.valores["bloque_esperado"] = bloque[1]
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
    estado.valores["id"] = uuid.uuid4()
    estado.valores["amount"] = Decimal("1.50000000")
    fila = (
        estado.valores["id"],
        emisor[0],
        receptor[0],
        estado.valores["amount"],
        "confirmed",
        _firma_inventada("confirmada"),
        bloque[0],
        datetime.now(UTC),
    )
    _insertar_transaccion(herramienta, fila)
    return f"se confirmó una transacción con firma inventada dentro del bloque {bloque[1]}"


def _restaurar_insertar_confirmada_falsa(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra la fila inventada por su identificador, que es lo que la identifica.

    La firma también es única, pero borrar por identificador no depende de que la
    firma se haya escrito como se pensaba: el `INSERT` pudo fallar y la fila no existir.
    """
    herramienta.ejecutar("DELETE FROM transactions WHERE id = %s", (estado.valores["id"],))
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
            _firma_inventada("violar"),
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
    estado.valores["id"] = uuid.uuid4()
    _insertar_transaccion(
        herramienta,
        (
            estado.valores["id"],
            emisor[0],
            receptor[0],
            Decimal("4.00000000"),
            "pending",
            _firma_inventada("pendiente"),
            None,
            datetime.now(UTC),
        ),
    )
    return "se insertó una transacción pendiente con firma inventada"


def _restaurar_pendiente_firma_invalida(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra la fila del pool por su identificador, que es lo que la identifica."""
    herramienta.ejecutar("DELETE FROM transactions WHERE id = %s", (estado.valores["id"],))
    return "se borró la pendiente de firma inventada"


def _aplicar_borrar_genesis(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Borra el bloque índice 0, con las transacciones que agrupara.

    La clave foránea de `transactions.block_id` es `ON DELETE RESTRICT`: si el génesis
    tuviera transacciones propias y se intentara borrarlo solo a él, el motor rechazaría
    el `DELETE` y el caso terminaría informando un `motor-rechaza` falso. Se capturan y
    se borran primero, como en el truncado de la cola.
    """
    genesis = herramienta.todos(SQL_BLOQUES)[0]
    estado.valores["bloque"] = genesis
    estado.valores["filas"] = _transacciones_de(herramienta, genesis[0])
    herramienta.ejecutar("DELETE FROM transactions WHERE block_id = %s", (genesis[0],))
    herramienta.ejecutar("DELETE FROM blocks WHERE id = %s", (genesis[0],))
    return "se borró el bloque génesis, la cabeza de la cadena"


def _restaurar_borrar_genesis(herramienta: Herramienta, estado: EstadoCaso) -> str:
    """Reinserta el génesis con sus valores y las transacciones que agrupaba."""
    _insertar_bloque(herramienta, estado.valores["bloque"])
    for fila in estado.valores["filas"]:
        _insertar_transaccion(herramienta, fila)
    return "se reinsertó el bloque génesis y sus transacciones"


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


# ---------------------------------------------------------------------------
# La comprobación de cada restauración: no alcanza con que la cadena verifique
# ---------------------------------------------------------------------------


def _comprobar_alterar_monto(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """El monto volvió al valor absoluto que se capturó."""
    fila = _leer_transaccion(herramienta, estado.valores["id"])
    if fila[3] != estado.valores["amount"]:
        raise LookupError(f"el monto quedó en {fila[3]} y era {estado.valores['amount']}")


def _comprobar_alterar_hash(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """El hash del bloque volvió al que estaba guardado."""
    bloque = estado.valores["bloque"]
    fila = herramienta.uno("SELECT hash FROM blocks WHERE id = %s", (bloque[0],))
    if fila[0] != bloque[4]:
        raise LookupError(f"el hash quedó en {fila[0]} y era {bloque[4]}")


def _comprobar_mover_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """La transacción volvió a su bloque original."""
    fila = _leer_transaccion(herramienta, estado.valores["id"])
    if fila[6] != estado.valores["block_id"]:
        raise LookupError(f"la transacción quedó en el bloque {fila[6]}")


def _comprobar_borrar_transaccion(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """La fila borrada volvió con su contenido, no solo con su identificador."""
    fila = _leer_transaccion(herramienta, estado.valores["fila"][0])
    if fila != estado.valores["fila"]:
        raise LookupError("la fila reinsertada no es la que se había borrado")


def _comprobar_insertar_confirmada_falsa(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """La fila inventada ya no está."""
    existe = herramienta.uno(
        "SELECT count(*) FROM transactions WHERE id = %s", (estado.valores["id"],)
    )[0]
    if existe:
        raise LookupError("la transacción de firma inventada sigue en la base")


def _comprobar_cambiar_llave_wallet(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """La pública volvió a ser la de antes.

    Es el caso donde mirar la cadena no alcanza: ningún hash cubre el registro de
    wallets, así que una restauración rota de esta fila pasaría con la cadena válida.
    """
    fila = herramienta.uno(
        "SELECT public_key FROM wallets WHERE id = %s", (estado.valores["id"],)
    )
    if fila[0] != estado.valores["public_key"]:
        raise LookupError("la pública de la wallet no volvió a su valor")


def _comprobar_pendiente_firma_invalida(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """La fila del pool ya no está."""
    existe = herramienta.uno(
        "SELECT count(*) FROM transactions WHERE id = %s", (estado.valores["id"],)
    )[0]
    if existe:
        raise LookupError("la pendiente de firma inventada sigue en el pool")


def _comprobar_borrar_genesis(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """El génesis volvió con su contenido, incluida su marca de tiempo."""
    bloque = estado.valores["bloque"]
    fila = herramienta.uno(
        "SELECT id, block_index, timestamp, previous_hash, hash FROM blocks WHERE id = %s",
        (bloque[0],),
    )
    if fila != bloque:
        raise LookupError("el bloque génesis reinsertado no es el que se había borrado")


def _comprobar_truncar_cola(herramienta: Herramienta, estado: EstadoCaso) -> None:
    """El bloque y sus transacciones volvieron con su contenido."""
    bloque = estado.valores["bloque"]
    fila = herramienta.uno(
        "SELECT id, block_index, timestamp, previous_hash, hash FROM blocks WHERE id = %s",
        (bloque[0],),
    )
    if fila != bloque:
        raise LookupError("el bloque reinsertado no es el que se había borrado")
    repuestas = _transacciones_de(herramienta, bloque[0])
    if sorted(repuestas) != sorted(estado.valores["filas"]):
        raise LookupError("las transacciones reinsertadas no son las que se habían borrado")


def _bloque_alterado(estado: EstadoCaso) -> int | None:
    """El índice del bloque que el caso alteró, capturado al aplicarlo.

    Es lo que declaran los dos casos que esperan un bloque concreto: el valor sale de
    lo que el caso tocó y no de un número escrito en el catálogo, así que una forma
    distinta de la demostración no los hace desacordar.

    Devuelve `None` cuando la aplicación del caso no llegó a capturarlo —falló antes
    de tocar nada—: no hay bloque que comparar y el desacuerdo ya lo marca el
    veredicto observado.
    """
    return estado.valores.get("bloque_esperado")


CASOS: tuple[Caso, ...] = (
    Caso(
        clave="alterar-monto",
        titulo="Alterar el monto de una transacción confirmada",
        que_hace="suma uno al monto de una transacción confirmada, por SQL directo",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=_bloque_alterado,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_alterar_monto,
        restaurar=_restaurar_alterar_monto,
        comprobar=_comprobar_alterar_monto,
    ),
    Caso(
        clave="alterar-hash",
        titulo="Alterar el hash de un bloque",
        que_hace="escribe sesenta y cuatro ceros como hash de un bloque",
        que_mirar="el bloque que /verificar señala como alterado",
        esperado=CADENA_INVALIDA,
        bloque_esperado=_bloque_alterado,
        limite=None,
        destructivo=False,
        aplicar=_aplicar_alterar_hash,
        restaurar=_restaurar_alterar_hash,
        comprobar=_comprobar_alterar_hash,
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
        comprobar=_comprobar_mover_transaccion,
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
        comprobar=_comprobar_borrar_transaccion,
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
        comprobar=_comprobar_insertar_confirmada_falsa,
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
        comprobar=_comprobar_cambiar_llave_wallet,
    ),
    Caso(
        clave="pendiente-firma-invalida",
        titulo="Insertar una pendiente con firma inventada",
        que_hace="inserta en el pool una transacción pendiente con firma inventada",
        que_mirar="que /verificar sigue diciendo que la cadena es válida",
        esperado=CADENA_VALIDA,
        bloque_esperado=None,
        limite=(
            "la verificación mira los bloques, no el pool, y la agrupación confirma las "
            "filas del pool sin volver a validar las firmas: una pendiente falsificada "
            "puede terminar agrupada en un bloque cuyo hash recalcula sin error"
        ),
        destructivo=False,
        aplicar=_aplicar_pendiente_firma_invalida,
        restaurar=_restaurar_pendiente_firma_invalida,
        comprobar=_comprobar_pendiente_firma_invalida,
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
        comprobar=_comprobar_borrar_genesis,
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
        comprobar=_comprobar_truncar_cola,
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


def _exigir_forma_de_la_demostracion(herramienta: Herramienta) -> None:
    """Falla temprano si el ledger no tiene la forma que los casos esperan.

    Los casos eligen sus objetivos por posición: el primer bloque con contenido, la
    punta de la cadena, una transacción confirmada. Sobre un ledger de otra forma
    —vacío, o con un solo bloque— el recorrido caería con un `IndexError` a mitad de
    camino, posiblemente con un caso ya aplicado y sin restaurar. Es preferible decirlo
    antes del primer caso y no tocar nada.
    """
    bloques = herramienta.todos(SQL_BLOQUES)
    if len(bloques) < 2:
        raise LookupError(
            f"hay {len(bloques)} bloques y hacen falta por lo menos dos para tener qué agrupar"
        )
    confirmadas = herramienta.uno(
        "SELECT count(*) FROM transactions WHERE status = 'confirmed'"
    )[0]
    if not confirmadas:
        raise LookupError("no hay ninguna transacción confirmada que sabotear")


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


def direccion_de_verificacion() -> str:
    """La dirección de `/verificar` que se le muestra a la persona.

    Sale de la variable del entorno y, si no está, de la dirección por defecto. Se
    resuelve en cada llamada y no al importar el módulo: el valor puede fijarse
    después, y la dirección que se muestra tiene que ser la que se va a mirar.
    Mirar esa página exige una sesión de administrador abierta en el navegador
    (REQ-38); la sonda, en cambio, pide `/ingresar`, que es pública.
    """
    base = os.environ.get(VARIABLE_DE_LA_APLICACION) or APLICACION_POR_DEFECTO
    return f"{base.rstrip('/')}/verificar"


def direccion_de_ingreso() -> str:
    """La dirección pública que sondea `probar_web`: la página de ingreso.

    `/verificar` quedó detrás de la puerta del administrador (REQ-38), así que un
    pedido anónimo ya no dice si la aplicación está en pie: redirige al ingreso.
    `/ingresar` responde 200 sin sesión y es la señal correcta de que hay algo
    corriendo que mirar.
    """
    base = os.environ.get(VARIABLE_DE_LA_APLICACION) or APLICACION_POR_DEFECTO
    return f"{base.rstrip('/')}/ingresar"


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Convierte una redirección en el error que es, en vez de seguirla.

    `urlopen` sigue los 302 por su cuenta y termina devolviendo el 200 de la página
    de ingreso como si la ruta sondeada hubiera respondido: con la puerta de sesión
    eso convertía un `/verificar` protegido en un falso éxito. Devolver `None` de
    `redirect_request` hace que la librería levante el `HTTPError` del código, que
    es lo que la sonda necesita para informarlo como lo que es.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Los códigos con los que la aplicación dice «pasa por el ingreso»: una redirección
# o una negativa por credenciales. Ninguno es un éxito de la sonda, y confundirlos
# con uno hacía que la comprobación previa dejara sabotear sin nada que mirar.
CODIGOS_QUE_PIDEN_SESION = frozenset({301, 302, 303, 307, 308, 401, 403})


@dataclass(frozen=True, slots=True)
class Sonda:
    """Lo que devolvió pedirle una página a la aplicación, con su significado.

    `pide_sesion` distingue la redirección o la negativa por credenciales de un
    fallo de conexión: los dos desenlaces impiden empezar, pero no son lo mismo y
    el mensaje tiene que decir cuál fue.
    """

    responde: bool
    detalle: str
    pide_sesion: bool


def _sondear(url: str, tiempo_de_espera: float) -> Sonda:
    """Pide `url` sin seguir redirecciones y traduce la respuesta a una `Sonda`."""
    try:
        with urllib.request.build_opener(_SinRedirecciones()).open(
            url, timeout=tiempo_de_espera
        ) as respuesta:
            if respuesta.status == 200:
                return Sonda(True, f"la aplicación respondió HTTP 200 en {url}", False)
            return Sonda(
                False, f"la aplicación respondió HTTP {respuesta.status} en {url}", False
            )
    except urllib.error.HTTPError as error:
        if error.code in CODIGOS_QUE_PIDEN_SESION:
            return Sonda(
                False,
                f"la aplicación respondió HTTP {error.code} en {url}: no es un éxito, "
                "la respuesta manda al ingreso o pide credenciales",
                True,
            )
        return Sonda(False, f"la aplicación respondió HTTP {error.code} en {url}", False)
    except (urllib.error.URLError, OSError) as error:
        return Sonda(False, f"la aplicación no respondió en {url}: {error}", False)


def probar_web(
    url: str | None = None, tiempo_de_espera: float = 3.0
) -> tuple[bool, str]:
    """Pide `/ingresar` y devuelve si respondió HTTP 200, con la descripción del desenlace.

    Es la comprobación de que hay algo que mirar: la pausa de cada caso existe para
    que alguien vea el dictamen en el navegador, así que sin aplicación corriendo la
    herramienta se detiene y dice cómo levantarla, en vez de sabotear a ciegas.

    La sonda pide la página de ingreso y **no sigue redirecciones**: un 302, un 401
    o un 403 se informan como lo que son y nunca como éxito. Para mirar `/verificar`
    hace falta tener una sesión de administrador abierta en el navegador; esta
    sonda sólo comprueba que la aplicación esté en pie.

    Todos los fracasos nombran la dirección que se intentó: si la sonda mira un puerto
    donde no hay nada, el mensaje tiene que decir cuál fue, no solo que no respondió.
    """
    url = direccion_de_ingreso() if url is None else url
    sonda = _sondear(url, tiempo_de_espera)
    return sonda.responde, sonda.detalle


def _texto_del_esperado(caso: Caso) -> str:
    """Lo que tiene que pasar, en palabras, según el veredicto declarado."""
    if caso.esperado == MOTOR_RECHAZA:
        return "el motor rechaza la fila y no queda nada escrito"
    if caso.esperado == CADENA_INVALIDA:
        esperado = "la cadena queda inválida"
        if caso.bloque_esperado is not None:
            # El índice no se nombra acá: sale de lo que el caso altera y todavía no
            # pasó. Nombrarlo antes de tiempo obligaría a fijarlo en el catálogo.
            esperado += " y el bloque señalado es el que el caso altera"
        return esperado
    return "la cadena sigue válida: este caso no se detecta"


def _mostrar_caso(caso: Caso, indice: int, total: int, salida: Salida) -> None:
    """Narra el encabezado de un caso: qué hace, qué mirar y qué se espera."""
    salida.linea(f"[{indice}/{total}] {caso.titulo} ({caso.clave})")
    salida.linea(f"{'que hace':<{ANCHO_ETIQUETA}}: {caso.que_hace}")
    # La dirección de la verificación solo se agrega cuando el caso pide mirarla: los
    # casos que rechaza el motor se ven en esta misma consola y nombrar la página
    # mandaría a mirar donde no pasa nada. La sesión se nombra porque `/verificar`
    # quedó detrás de la puerta del administrador (REQ-38).
    donde = (
        f" en {direccion_de_verificacion()} (con sesión de administrador abierta)"
        if caso.esperado != MOTOR_RECHAZA
        else ""
    )
    salida.linea(f"{'que mirar':<{ANCHO_ETIQUETA}}: {caso.que_mirar}{donde}")
    salida.linea(f"{'se espera':<{ANCHO_ETIQUETA}}: {_texto_del_esperado(caso)}")
    if caso.limite is not None:
        salida.linea(f"{'limite':<{ANCHO_ETIQUETA}}: {caso.limite}")


def _esperar_enter(pausa: bool, mensaje: str, entrada, salida: Salida) -> None:
    """Espera un Enter para que la persona mire el navegador antes de seguir.

    Solo espera si la entrada es un terminal. En una corrida con guion o desde la
    suite no hay nadie que pueda pulsar Enter, y esperar de todos modos colgaría el
    proceso para siempre; en ese caso se dice y se sigue sin pausas.
    """
    if not pausa:
        return
    flujo = sys.stdin if entrada is None else entrada
    if not flujo.isatty():
        salida.linea("pausa: no hay terminal donde esperar un Enter; sigo sin pausas")
        return
    salida.linea(f"pausa: {mensaje}")
    try:
        flujo.readline()
    except EOFError:
        # La entrada se cerró entre la comprobación y la lectura: es el mismo caso sin
        # nadie enfrente, así que se sigue en vez de caer.
        salida.linea("pausa: la entrada se cerró; sigo sin pausas")


def descripcion_del_error(sqlstate: str | None) -> str:
    """Traduce el SQLSTATE de un error del motor al veredicto del catálogo.

    Solo las violaciones de restricción son «el motor rechazó»: son las que el motor
    levanta al rechazar una fila antes de guardarla, que es lo que los dos casos
    declaran. Cualquier otro error —una consulta mal escrita de esta herramienta, un
    tipo equivocado, una columna que no existe— es un error inesperado de la
    herramienta, no algo que el sistema haga, y daría por buena una fila que nunca se
    intentó escribir.
    """
    if sqlstate is not None and sqlstate.startswith(VIOLACION_DE_RESTRICCION):
        return MOTOR_RECHAZA
    return ERROR_INESPERADO


def _texto_de_la_primera_pausa(observado: str, escrito: bool) -> str:
    """Qué se le pide mirar a la persona antes de observar la cadena.

    No es el mismo daño en los tres desenlaces: una fila alterada se mira en
    `/verificar`, un rechazo del motor se mira en esta consola —el error acaba de
    salir— y un fallo de la herramienta no se demuestra, solo se informa.
    """
    if observado == MOTOR_RECHAZA:
        return "pulsa Enter cuando hayas visto el rechazo del motor"
    if not escrito:
        return "pulsa Enter para seguir"
    return "pulsa Enter cuando hayas mirado el daño"


def _detectar_veredicto(herramienta: Herramienta) -> tuple[str, int | None]:
    """Observa la base y traduce el reporte de la verificación a un veredicto del catálogo."""
    reporte = herramienta.reporte()
    if reporte.valid:
        return CADENA_VALIDA, None
    return CADENA_INVALIDA, reporte.altered_block_index


def _comparar(
    caso: Caso,
    observado: str,
    indice: int | None,
    bloque_esperado: int | None,
    error_del_motor: str = "",
) -> tuple[bool, str]:
    """Compara lo observado con lo que el caso declara; devuelve si coincide y el detalle.

    `bloque_esperado` llega calculado desde lo que el caso alteró —no se lee del
    catálogo— porque el índice verdadero solo se conoce después de aplicarlo. El
    catálogo dice **cómo** obtenerlo y esta comparación lo usa.
    """
    if observado == MOTOR_RECHAZA:
        if caso.esperado == MOTOR_RECHAZA:
            return True, f"el motor rechazó la fila ({error_del_motor}), como estaba declarado"
        return False, f"el motor rechazó una fila que tenía que entrar ({error_del_motor})"
    if observado == ERROR_INESPERADO:
        return False, f"error inesperado de la herramienta: {error_del_motor}"
    if observado != caso.esperado:
        return False, f"se observó {observado} y se esperaba {caso.esperado}"
    if bloque_esperado is not None and indice != bloque_esperado:
        return False, f"el bloque señalado fue {indice} y se esperaba {bloque_esperado}"
    return True, "coincide con lo declarado"


def _siguiente(
    herramienta: Herramienta,
    estado: EstadoCaso,
    caso: Caso,
    pausa: bool,
    entrada,
    salida: Salida,
) -> ResultadoCaso:
    """Aplica, deja mirar, observa, dictamina, restaura y deja mirar la vuelta.

    El orden es el de la demostración y no el del código más corto: el daño tiene que
    estar en la base **mientras** la persona mira `/verificar`, y la restauración tiene
    que estar hecha **y comprobada** antes de la segunda pausa, que es la que muestra que
    la herramienta deja el ledger como estaba. Aplicar y restaurar entre dos pausas, sin
    pausa en el medio, dejaría el estado alterado milisegundos y no habría nada que ver.

    Los casos que el motor rechaza piden un solo Enter: no hubo alteración, así que no
    hay vuelta que mirar y pedir la segunda pausa sería decir algo que no pasó.

    El error del motor no se traduce: el mensaje de PostgreSQL es la demostración
    (REQ-19). La restauración con los valores capturados y la comprobación posterior se
    hacen en los dos desenlaces, para que la herramienta no deje el ledger roto aunque
    un caso no haya salido como estaba declarado.
    """
    observado = CADENA_VALIDA
    bloque: int | None = None
    detalle_del_error = ""
    escrito = False
    try:
        hecho = caso.aplicar(herramienta, estado)
        escrito = True
        salida.linea(f"{'se aplico':<{ANCHO_ETIQUETA}}: {hecho}")
    except psycopg.errors.Error as error:
        detalle_del_error = f"{error.diag.sqlstate} {error.diag.message_primary}"
        observado = descripcion_del_error(error.diag.sqlstate)
        salida.linea(f"{'se aplico':<{ANCHO_ETIQUETA}}: el motor levantó un error")
        salida.linea(f"{'el motor':<{ANCHO_ETIQUETA}}: {detalle_del_error}")
    except Exception as error:  # noqa: BLE001 - la herramienta no puede caer por un caso
        # Un fallo de la herramienta no es un desenlace del sistema: se informa, se
        # cuenta como desacuerdo y se sigue, para que la corrida no se detenga a mitad
        # de camino dejando una alteración sin restaurar.
        salida.linea(f"{'se aplico':<{ANCHO_ETIQUETA}}: falló la herramienta: {error!r}")

    # La pausa va con el efecto ya escrito en la base. Su texto depende del desenlace:
    # lo que hay para mirar no es lo mismo cuando la fila quedó alterada, cuando el
    # motor la rechazó —queda el error en la consola— o cuando falló la herramienta.
    _esperar_enter(pausa, _texto_de_la_primera_pausa(observado, escrito), entrada, salida)
    if escrito:
        observado, bloque = _detectar_veredicto(herramienta)
        salida.linea(f"{'observado':<{ANCHO_ETIQUETA}}: {observado}")

    coincide, detalle = _comparar(
        caso,
        observado,
        bloque,
        caso.bloque_esperado(estado) if escrito and caso.bloque_esperado else None,
        detalle_del_error,
    )
    marca = "coincide" if coincide else "no coincide"
    salida.linea(f"{'veredicto':<{ANCHO_ETIQUETA}}: {marca} ({detalle})")

    restaurado = False
    try:
        repuesto = caso.restaurar(herramienta, estado)
        salida.linea(f"{'restaurado':<{ANCHO_ETIQUETA}}: {repuesto}")
    except psycopg.errors.Error as error:
        salida.linea(f"{'restaurado':<{ANCHO_ETIQUETA}}: falló: {error}")
        return ResultadoCaso(
            clave=caso.clave,
            esperado=caso.esperado,
            observado=observado,
            bloque_observado=bloque,
            coincide=coincide,
            restaurado=False,
            detalle=detalle,
        )

    # La restauración se comprueba **antes** de la segunda pausa: a la persona se le
    # pide mirar que volvió a la normalidad cuando la herramienta ya lo verificó, no
    # antes. La pausa, además, solo tiene sentido si algo se había alterado: en los
    # casos que el motor rechaza no hubo nada que restaurar, así que piden un solo Enter.
    restaurado = _comprobar_restauracion(herramienta, estado, caso, salida)
    if escrito:
        _esperar_enter(
            pausa, "pulsa Enter cuando hayas visto que volvió a la normalidad", entrada, salida
        )
    return ResultadoCaso(
        clave=caso.clave,
        esperado=caso.esperado,
        observado=observado,
        bloque_observado=bloque,
        coincide=coincide,
        restaurado=restaurado,
        detalle=detalle,
    )


def _comprobar_restauracion(
    herramienta: Herramienta, estado: EstadoCaso, caso: Caso, salida: Salida
) -> bool:
    """Comprueba que el ledger volvió a su estado: la fila del caso y la cadena.

    La cadena por sí sola no alcanza: hay alteraciones que ningún hash cubre —la
    pública de una wallet es el caso— y una restauración rota pasaría con la cadena
    válida. Por eso cada caso declara con qué se comprueba, además.
    """
    if caso.comprobar is not None:
        try:
            caso.comprobar(herramienta, estado)
        except LookupError as error:
            salida.linea(f"{'restauracion':<{ANCHO_ETIQUETA}}: no volvió: {error}")
            return False
    valida = herramienta.cadena_valida()
    salida.linea(
        f"{'cadena':<{ANCHO_ETIQUETA}}: "
        + ("ok, vuelve a ser válida" if valida else "no volvió a ser válida")
    )
    return valida


def _resumen(recorrido: Recorrido, salida: Salida) -> None:
    """El cierre: cuántos se detectaron, cuáles no, y qué no coincidió con lo declarado.

    Los desacuerdos se listan aparte y con su detalle: son los casos donde el sistema o
    la herramienta no hicieron lo que el catálogo dice, y son la razón de que la corrida
    termine con código distinto de cero.
    """
    salida.linea("")
    salida.linea("resumen")
    salida.linea(f"casos corridos: {len(recorrido.resultados)}")
    salida.linea(f"detectados: {recorrido.detectados}")
    salida.linea(f"no detectados: {recorrido.no_detectados}")
    salida.linea(f"desacuerdos: {recorrido.desacuerdos}")
    for resultado in recorrido.resultados:
        if resultado.coincide:
            continue
        salida.linea(f"- {resultado.clave}: no coincide. {resultado.detalle}")
    for resultado in recorrido.resultados:
        if not resultado.coincide or resultado.esperado != CADENA_VALIDA:
            continue
        caso = caso_de(resultado.clave)
        salida.linea(f"- {caso.clave}: no se detecta. {caso.limite}")


def _instrucciones_de_resembrado(salida: Salida) -> None:
    """Cómo volver a los datos de demostración, en orden, y qué tiene que decir la pantalla."""
    salida.linea("")
    salida.linea("para volver a los datos de demostración (resembrado)")
    salida.linea("1. baja los contenedores borrando el volumen de datos:")
    salida.linea("   docker compose down -v")
    salida.linea("   con Podman: podman compose down -v")
    salida.linea("2. vuelve a levantar los contenedores:")
    salida.linea("   docker compose up -d")
    salida.linea("   con Podman: podman compose up -d")
    salida.linea("3. siembra la demostración con el arranque del proyecto:")
    salida.linea("   <venv> -m src.bootstrap")
    salida.linea("4. levanta la aplicación y mira la verificación:")
    salida.linea("   <venv> -m src.web")
    salida.linea(f"   {direccion_de_verificacion()} tiene que decir: La cadena es válida")


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

    def publica_de_una_wallet(self) -> str:
        """La pública de la wallet que el caso de la llave usa como objetivo.

        Se lee con la misma consulta que el caso para que la prueba compare la misma
        fila que la herramienta cambia, y no una elegida aparte.
        """
        return self._herramienta.uno(SQL_UNA_WALLET)[1]

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
        `/ingresar`, que es pública, sin seguir redirecciones— y `entrada` es de
        dónde se lee el Enter: las pruebas inyectan las dos para correr sin servidor
        y sin terminal. La comprobación previa va primero: sobre una cadena ya
        alterada o sin aplicación que responda no se corre ningún caso, porque el
        veredicto de cada uno dejaría de significar algo.
        """
        destino = Salida(salida)
        if not self._comprobar(destino, web):
            # Las instrucciones de recuperación van en el camino de fallo, que es donde
            # hacen falta: decir que están «al final» y volver antes de imprimirlas
            # manda a buscar algo que no está.
            _instrucciones_de_resembrado(destino)
            return Recorrido(True, (), 0, 0, 0)

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

        # La forma de la demostración se comprueba antes del primer caso: los casos
        # eligen sus objetivos por posición —el primer bloque con contenido, la punta—
        # y un ledger con otra forma haría que el recorrido cayera a mitad de camino,
        # posiblemente con una alteración sin restaurar.
        try:
            _exigir_forma_de_la_demostracion(self._herramienta)
        except LookupError as error:
            destino.linea(f"la demostración no tiene la forma esperada: {error}")
            destino.linea(
                "siembra la demostración con `python -m src.bootstrap` sobre una base "
                "vacía y vuelve a correr esto."
            )
            _instrucciones_de_resembrado(destino)
            return Recorrido(True, (), 0, 0, 0)

        resultados = []
        total = len(elegidos)
        for indice, caso in enumerate(elegidos, start=1):
            permiso_de_pausa = pausas and (entrada is not None or sys.stdin.isatty())
            _mostrar_caso(caso, indice, total, destino)
            estado = self._estados.setdefault(caso.clave, EstadoCaso(valores={}))
            resultados.append(
                _siguiente(self._herramienta, estado, caso, permiso_de_pausa, entrada, destino)
            )
            destino.linea("")

        # Los conteos salen de lo **observado**. Un caso que no coincidió con lo que
        # declara no puede sumar como detectado ni como límite: es un desacuerdo.
        detectados = sum(1 for resultado in resultados if resultado.observado != CADENA_VALIDA)
        limites = sum(
            1
            for resultado in resultados
            if resultado.coincide and resultado.esperado == CADENA_VALIDA
        )
        desacuerdos = sum(1 for resultado in resultados if not resultado.coincide)
        recorrido = Recorrido(
            detenido_por_la_comprobacion_previa=False,
            resultados=tuple(resultados),
            detectados=detectados,
            no_detectados=limites,
            desacuerdos=desacuerdos,
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
        salida.linea("comprobación previa")
        try:
            reporte = self._herramienta.reporte()
            capturas = self._herramienta.capturas()
            transacciones = self._herramienta.transacciones()
        except psycopg.Error as error:
            # El rastro del driver no dice qué hacer: se informa el desenlace y se
            # corta antes del primer caso, que es lo que evita dejar una alteración
            # aplicada a medias.
            salida.linea(f"la base de datos no responde: {error}")
            salida.linea(
                "levanta PostgreSQL (`docker compose up -d` o `podman compose up -d`) y "
                "vuelve a correr esto."
            )
            return False
        salida.linea(f"{'capturas':<{ANCHO_ETIQUETA}}: {capturas}")
        salida.linea(f"{'transacciones':<{ANCHO_ETIQUETA}}: {transacciones}")
        if not reporte.valid:
            salida.linea(
                "la cadena ya viene alterada: el bloque señalado es el "
                f"{reporte.altered_block_index}. Restaura o resiembra antes de sabotear; "
                "las instrucciones de resembrado están abajo."
            )
            return False
        salida.linea("la cadena verifica como válida")

        if web is None:
            sonda = _sondear(direccion_de_ingreso(), 3.0)
            responde, detalle, pide_sesion = (
                sonda.responde,
                sonda.detalle,
                sonda.pide_sesion,
            )
        else:
            responde, detalle = web(), "la prueba respondió por la aplicación"
            pide_sesion = False
        salida.linea(f"{'aplicacion':<{ANCHO_ETIQUETA}}: {detalle}")
        if not responde:
            if pide_sesion:
                salida.linea(
                    f"la aplicación responde en {direccion_de_ingreso()}, pero /verificar "
                    "exige una sesión de administrador: abre el navegador, ingresa con una "
                    "cuenta administradora y vuelve a correr esto."
                )
            else:
                salida.linea(
                    f"la aplicación no responde en {direccion_de_ingreso()}: levántala con "
                    f"`python -m src.web` en otra terminal, abre {direccion_de_verificacion()} "
                    "con una sesión de administrador abierta y vuelve a correr esto."
                )
            return False
        # El aviso va aunque la sonda haya dado bien: `/ingresar` responde sin sesión,
        # pero el dictamen que cada pausa pide mirar vive detrás de la puerta del
        # administrador (REQ-38), y sin esa sesión no hay nada que ver.
        salida.linea(
            "para mirar /verificar en cada pausa, ten una sesión de administrador "
            "abierta en el navegador"
        )
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

    try:
        with abrir() as sabotaje:
            recorrido = sabotaje.recorrido(
                con_destructivos=opciones.destructivos, pausas=not opciones.sin_pausas
            )
    except psycopg.Error as error:
        # La conexión de la herramienta no se pudo abrir: sin motor no hay nada que
        # sabotear ni que verificar, y el rastro de la librería no dice qué hacer.
        print(f"la base de datos no responde: {error}", file=sys.stderr)
        print(
            "levanta PostgreSQL (`docker compose up -d` o `podman compose up -d`), "
            "revisa DATABASE_URL y vuelve a correr esto.",
            file=sys.stderr,
        )
        return 2
    return codigo_de_salida(recorrido)


if __name__ == "__main__":
    sys.exit(main())
