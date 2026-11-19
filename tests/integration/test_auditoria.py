"""Auditoría del estado sobre el ledger real: hashes, firmas y solo lectura.

Arma la cadena por el camino real, la altera con SQL directo —que es lo que puede
pasar por fuera de la aplicación— y exige que la auditoría enumere el fallo del
bloque y el de la transacción sin escribir nada (REQ-22). El sello se prueba aquí
con un objeto armado a mano: leerlo y fijarlo es de otra tarea.
"""
from datetime import UTC, datetime

from src.domain.auditoria import Sello

SELLADO_EN = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)


def _tablas(conexion) -> dict[str, list[tuple]]:
    """Contenido de las tres tablas con orden fijo, para compararlo tal cual."""
    return {
        "wallets": conexion.execute("SELECT * FROM wallets ORDER BY id").fetchall(),
        "blocks": conexion.execute("SELECT * FROM blocks ORDER BY block_index").fetchall(),
        "transactions": conexion.execute("SELECT * FROM transactions ORDER BY id").fetchall(),
    }


def test_una_cadena_recien_armada_es_limpia(ledger):
    """Con solo el génesis no hay críticos ni avisos y el resumen cuadra."""
    genesis = ledger.blocks.get_by_index(0)

    auditoria = ledger.audit_chain()

    assert auditoria.resumen.bloques == 1
    assert auditoria.resumen.altura == 0
    assert auditoria.resumen.genesis_hash == genesis.hash
    assert auditoria.resumen.valida is True
    assert auditoria.limpia is True
    # El único hallazgo es la nota del sello que todavía no se fijó.
    assert [(h.codigo, h.severidad) for h in auditoria.hallazgos] == [("sello-ausente", "nota")]


def test_alterar_el_monto_por_sql_se_detecta_en_el_bloque_y_la_transaccion(
    ledger, conexion, transaccion
):
    """Un UPDATE directo al monto rompe el hash del bloque y la firma de la fila."""
    fila = ledger.transactions.add(transaccion())
    bloque = ledger.group_pending()
    conexion.execute(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s", (fila.id,)
    )

    auditoria = ledger.audit_chain()

    codigos = {hallazgo.codigo for hallazgo in auditoria.hallazgos}
    assert {"hash", "firma"} <= codigos
    assert auditoria.resumen.valida is False
    assert auditoria.contar("critico") >= 2
    assert any(
        hallazgo.codigo == "hash"
        and hallazgo.ubicacion == f"Bloque {bloque.block_index}"
        and hallazgo.reparacion == "encadenar"
        for hallazgo in auditoria.hallazgos
    )
    assert any(
        hallazgo.codigo == "firma"
        and hallazgo.ubicacion == f"Transacción {str(fila.id)[:8]}…"
        and hallazgo.reparacion == "aislar"
        for hallazgo in auditoria.hallazgos
    )


def test_una_pendiente_con_firma_invalida_es_aviso(ledger, conexion, transaccion):
    """Una pendiente con firma inventada se marca en el pool sin invalidar la cadena."""
    fila = transaccion()
    fila.signature = "ab" * 64
    fila = ledger.transactions.add(fila)

    auditoria = ledger.audit_chain()

    firma = next(hallazgo for hallazgo in auditoria.hallazgos if hallazgo.codigo == "firma")
    assert firma.severidad == "aviso"
    assert firma.reparacion == "rechazar-pendientes"
    assert firma.ubicacion == f"Transacción {str(fila.id)[:8]}…"
    assert auditoria.resumen.valida is True
    assert auditoria.limpia is False


def test_la_auditoria_no_escribe_ninguna_fila(ledger, conexion, transaccion):
    """Auditar no escribe tablas, ni siquiera cuando el sello no coincide (REQ-22)."""
    ledger.transactions.add(transaccion())
    ledger.group_pending()
    antes = _tablas(conexion)

    ledger.audit_chain()
    ledger.audit_chain(sello=Sello(altura=1, hash="f" * 64, fijado_en=SELLADO_EN))

    assert _tablas(conexion) == antes


def test_un_sello_que_coincide_no_reporta_hallazgo(ledger):
    """Un sello que coincide con la cabeza no genera críticos ni avisos."""
    genesis = ledger.blocks.get_by_index(0)
    sello = Sello(altura=0, hash=genesis.hash, fijado_en=SELLADO_EN)

    auditoria = ledger.audit_chain(sello=sello)

    assert auditoria.sello.coincide is True
    assert auditoria.sello.crecio == 0
    assert not any(hallazgo.codigo.startswith("sello") for hallazgo in auditoria.hallazgos)


def test_un_sello_de_un_bloque_borrado_es_critico(ledger, conexion):
    """El sello ancla la cadena fuera de la base: si el bloque se borra, se nota."""
    genesis = ledger.blocks.get_by_index(0)
    sello = Sello(altura=0, hash=genesis.hash, fijado_en=SELLADO_EN)
    conexion.execute("DELETE FROM blocks WHERE block_index = 0")

    auditoria = ledger.audit_chain(sello=sello)

    assert auditoria.sello.coincide is False
    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "sello-no-coincide")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "fijar-sello"
