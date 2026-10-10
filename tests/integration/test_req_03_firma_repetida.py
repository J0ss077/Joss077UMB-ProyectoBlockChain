"""REQ-03: rechazar la repetición de una firma ya registrada.

El respaldo es el índice único de la decisión 4: dos filas con la misma firma
son la misma transacción presentada dos veces, así que la base admite la primera
y rechaza la segunda por ese índice. El dominio consulta `signature_exists`
antes para poder dar el motivo del rechazo, y esa consulta también se prueba
aquí.
"""
import dataclasses
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from src.domain.transaction import TransactionStatus
from src.persistence.postgres import PostgresTransactionRepository


@pytest.fixture
def transacciones(conexion):
    """El repositorio de transacciones contra la conexión de la sesión."""
    return PostgresTransactionRepository(conexion)


def test_req_03_firma_repetida_levanta_unique_violation(transacciones, base_limpia, transaccion):
    """Una firma se registra una vez; la segunda presentación levanta el error del motor."""
    presentada = transaccion()
    primera = transacciones.add(presentada)
    # La misma firma con otro identificador: así lo único que puede colisionar es
    # el índice único sobre `signature` y no la clave primaria.
    repetida = dataclasses.replace(presentada, id=uuid4(), signature=primera.signature)

    with pytest.raises(psycopg.errors.UniqueViolation) as error:
        transacciones.add(repetida)

    # El nombre de la restricción es lo que ata la prueba al respaldo del motor:
    # cualquier otra unicidad haría pasar la prueba sin comprobar la decisión 4.
    assert error.value.diag.constraint_name == "uq_transactions_signature"
    assert transacciones.count() == 1


def test_req_03_la_firma_guardada_se_encuentra_por_su_valor(transacciones, base_limpia, transaccion):
    """`signature_exists` distingue la firma registrada de una que no lo está."""
    firmada = transaccion()
    transacciones.add(firmada)

    assert transacciones.signature_exists(firmada.signature) is True
    assert transacciones.signature_exists("firma-que-nadie-presento") is False


def test_req_03_la_fila_guardada_conserva_su_estado(transacciones, conexion, base_limpia, transaccion):
    """La firma admitida queda pendiente y es la única de su valor en la tabla."""
    primera = transacciones.add(transaccion())

    guardada = transacciones.get(primera.id)
    assert guardada is not None
    assert guardada.status is TransactionStatus.PENDING

    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT count(*) AS total, count(DISTINCT signature) AS distintas FROM transactions"
        )
        conteo = cursor.fetchone()
    assert conteo["total"] == 1
    assert conteo["distintas"] == 1
