"""Auditoría del estado de la cadena: códigos, severidades, reparaciones y límites.

Cada prueba arma una cadena sobre los dobles de `tests/dobles.py`, la altera de una
forma concreta y exige que la auditoría enumere lo que encuentra, sin detenerse en
el primer fallo y sin escribir nada. Corre sin base de datos (REQ-17).
"""
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.auditoria import SEVERIDADES, Sello
from src.domain.transaction import AMOUNT_MAX, Transaction, TransactionStatus
from src.domain.wallet import create_wallet, sign_payload
from tests.dobles import BLOCK_AT, build_block, build_chain

# Una sola clave maestra para toda la prueba: las wallets y las firmas se arman con
# ella, así que la verificación de la firma mide el estado del ledger y no la clave.
MASTER_KEY = Fernet.generate_key()

# Instante del sello de las pruebas, posterior a los bloques que se sellan.
SELLADO_EN = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)


@pytest.fixture
def wallets():
    """Una emisora y una receptora con la clave maestra con la que se firma."""
    return {
        "emisora": create_wallet(master_key=MASTER_KEY),
        "receptora": create_wallet(master_key=MASTER_KEY),
    }


def _chain(wallets, *, blocks=(), transactions=()):
    """Ledger sobre dobles con las dos wallets registradas y la cadena que se le pase."""
    return build_chain(
        blocks=blocks,
        transactions=transactions,
        wallets=[wallets["emisora"], wallets["receptora"]],
        master_key=MASTER_KEY,
    )


def _transaccion(
    wallets,
    *,
    status: TransactionStatus = TransactionStatus.PENDING,
    block_id=None,
    amount: Decimal = Decimal("10.00000000"),
    sender_id=None,
    receiver_id=None,
) -> Transaction:
    """Transacción firmada por la emisora con los valores que pida la prueba."""
    emisora = wallets["emisora"]
    receptora = wallets["receptora"]
    transaction = Transaction(
        id=uuid4(),
        sender_id=emisora.id if sender_id is None else sender_id,
        receiver_id=receptora.id if receiver_id is None else receiver_id,
        amount=amount,
        status=status,
        signature="",
        block_id=block_id,
        created_at=BLOCK_AT,
    )
    transaction.signature = sign_payload(
        emisora,
        transaction.signing_payload(emisora.public_key, receptora.public_key),
        MASTER_KEY,
    )
    return transaction


def _cadena_valida(wallets, *, pendientes=()):
    """Génesis y un bloque con una confirmada bien firmada; opcionalmente, filas del pool."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    genesis = build_block(0)
    bloque = build_block(1, genesis, transactions=[confirmada])
    confirmada.block_id = bloque.id
    chain = _chain(
        wallets,
        blocks=[genesis, bloque],
        transactions=[confirmada, *pendientes],
    )
    return chain, genesis, bloque, confirmada


def test_las_severidades_son_las_tres_del_spec():
    """El orden y los valores de las severidades son los que fija el diseño."""
    assert SEVERIDADES == ("critico", "aviso", "nota")


def test_una_cadena_recien_armada_es_limpia(wallets):
    """Sin alteraciones no hay críticos ni avisos, y el resumen cuenta lo que hay."""
    chain, genesis, bloque, _ = _cadena_valida(wallets)

    auditoria = chain.audit_chain()

    assert auditoria.limpia is True
    assert auditoria.resumen.valida is True
    assert auditoria.resumen.bloques == 2
    assert auditoria.resumen.altura == bloque.block_index == 1
    assert auditoria.resumen.cabeza_hash == bloque.hash
    assert auditoria.resumen.cabeza_en == bloque.timestamp
    assert auditoria.resumen.genesis_hash == genesis.hash
    assert auditoria.resumen.confirmadas == 1
    assert auditoria.resumen.pendientes == 0
    assert auditoria.resumen.rechazadas == 0
    assert auditoria.resumen.wallets == 2
    assert [(r.indice, r.transacciones, r.estado) for r in auditoria.bloques] == [
        (0, 0, "correcto"),
        (1, 1, "correcto"),
    ]
    # El único hallazgo es la nota del sello que todavía no se fijó.
    assert [(h.codigo, h.severidad) for h in auditoria.hallazgos] == [("sello-ausente", "nota")]
    assert auditoria.reparaciones == ("fijar-sello",)


def test_alterar_el_monto_detecta_hash_y_firma_en_el_bloque_uno(wallets):
    """Un monto cambiado rompe el hash del bloque y la firma que lo cubría."""
    chain, _, bloque, confirmada = _cadena_valida(wallets)
    confirmada.amount += Decimal("1.00000000")

    auditoria = chain.audit_chain()

    codigos = {hallazgo.codigo for hallazgo in auditoria.hallazgos}
    assert {"hash", "firma"} <= codigos
    assert auditoria.contar("critico") >= 2
    assert auditoria.resumen.valida is False
    assert auditoria.bloques[1].estado == "alterado"
    assert any(
        hallazgo.codigo == "hash"
        and hallazgo.ubicacion == f"Bloque {bloque.block_index}"
        and hallazgo.reparacion == "encadenar"
        for hallazgo in auditoria.hallazgos
    )
    short_id = str(confirmada.id)[:8]
    assert any(
        hallazgo.codigo == "firma"
        and hallazgo.ubicacion == f"Transacción {short_id}…"
        and hallazgo.reparacion == "aislar"
        for hallazgo in auditoria.hallazgos
    )


def test_cambiar_la_publica_de_una_wallet_se_detecta_por_la_firma(wallets):
    """La firma se comprueba contra la pública actual: cambiar la llave se nota."""
    chain, _, _, _ = _cadena_valida(wallets)
    wallets["emisora"].public_key = create_wallet(master_key=MASTER_KEY).public_key

    auditoria = chain.audit_chain()

    firmas = [hallazgo for hallazgo in auditoria.hallazgos if hallazgo.codigo == "firma"]
    assert len(firmas) == 1
    assert firmas[0].severidad == "critico"
    assert firmas[0].reparacion == "aislar"
    # Ningún hash cambió: el caso solo se ve por la firma.
    assert "hash" not in {hallazgo.codigo for hallazgo in auditoria.hallazgos}


def test_pendiente_con_firma_invalida_se_marca_aviso_y_ofrece_rechazo(wallets):
    """Una firma inválida en el pool es aviso y se repara rechazando la pendiente."""
    pendiente = _transaccion(wallets)
    pendiente.signature = "ab" * 64
    chain, *_ = _cadena_valida(wallets, pendientes=[pendiente])

    auditoria = chain.audit_chain()

    firma = next(hallazgo for hallazgo in auditoria.hallazgos if hallazgo.codigo == "firma")
    assert firma.severidad == "aviso"
    assert firma.reparacion == "rechazar-pendientes"
    assert firma.ubicacion == f"Transacción {str(pendiente.id)[:8]}…"
    assert auditoria.resumen.valida is True
    assert auditoria.limpia is False
    assert "rechazar-pendientes" in auditoria.reparaciones


def test_un_hueco_de_indices_se_reporta_sin_romper(wallets):
    """Un salto en los índices se declara y no se ofrece renumerar."""
    genesis = build_block(0)
    segundo = build_block(1, genesis)
    # El bloque 2 no existe; el 3 se encadena bien al 1, así que solo falta el índice.
    salteado = build_block(3, segundo)
    chain = _chain(wallets, blocks=[genesis, segundo, salteado])

    auditoria = chain.audit_chain()

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "indice")
    assert hallazgo.severidad == "critico"
    assert hallazgo.ubicacion == "Bloque 3"
    assert hallazgo.reparacion is None
    assert auditoria.bloques[2].estado == "hueco"
    assert auditoria.resumen.valida is False


def test_la_auditoria_no_escribe_ninguna_fila(wallets):
    """Auditar dos veces no cambia bloques, transacciones ni wallets (REQ-22)."""
    pendiente = _transaccion(wallets)
    pendiente.signature = "ab" * 64
    chain, *_ = _cadena_valida(wallets, pendientes=[pendiente])

    def foto():
        return (
            [
                (b.id, b.block_index, b.timestamp, b.previous_hash, b.hash)
                for b in chain.blocks.rows
            ],
            [
                (t.id, t.status, t.block_id, t.signature, t.amount)
                for t in chain.transactions.rows
            ],
            [(w.id, w.public_key, w.private_key_encrypted) for w in chain.wallets.rows],
        )

    antes = foto()
    chain.audit_chain()
    chain.audit_chain(
        sello=Sello(altura=1, hash="f" * 64, fijado_en=SELLADO_EN),
        problema_del_sello=None,
    )

    assert foto() == antes


def test_sin_sello_declara_el_limite_del_recorte(wallets):
    """Sin sello, el recorte de la cola queda declarado como límite."""
    chain, *_ = _cadena_valida(wallets)

    auditoria = chain.audit_chain()

    assert any(limite.titulo == "Recorte de la cola" for limite in auditoria.limites)
    assert len(auditoria.limites) == 4
    assert auditoria.sello.sello is None
    assert auditoria.sello.problema == "ausente"
    assert auditoria.sello.coincide is False
    assert auditoria.sello.crecio is None


def test_un_sello_que_coincide_cuenta_los_bloques_nuevos_y_quita_el_limite(wallets):
    """Si el bloque sellado está intacto solo se informa cuánto creció la cadena."""
    chain, genesis, _, _ = _cadena_valida(wallets)
    sello = Sello(altura=0, hash=genesis.hash, fijado_en=SELLADO_EN)

    auditoria = chain.audit_chain(sello=sello)

    assert auditoria.sello.sello == sello
    assert auditoria.sello.problema is None
    assert auditoria.sello.coincide is True
    assert auditoria.sello.crecio == 1
    assert not any(hallazgo.codigo.startswith("sello") for hallazgo in auditoria.hallazgos)
    assert all(limite.titulo != "Recorte de la cola" for limite in auditoria.limites)
    assert len(auditoria.limites) == 3


def test_un_sello_que_no_coincide_es_critico_y_ofrece_fijarlo(wallets):
    """Un sello que apunta a otro hash delata recorte o reescritura por debajo."""
    chain, _, _, _ = _cadena_valida(wallets)
    sello = Sello(altura=1, hash="f" * 64, fijado_en=SELLADO_EN)

    auditoria = chain.audit_chain(sello=sello)

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "sello-no-coincide")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "fijar-sello"
    assert hallazgo.ubicacion == "Sello"
    assert auditoria.sello.coincide is False
    assert auditoria.sello.crecio is None

    # El bloque sellado también puede haber desaparecido: es el mismo hallazgo.
    perdido = Sello(altura=5, hash="f" * 64, fijado_en=SELLADO_EN)
    auditoria = chain.audit_chain(sello=perdido)
    assert any(h.codigo == "sello-no-coincide" for h in auditoria.hallazgos)
    assert auditoria.sello.coincide is False


def test_un_sello_ilegible_es_aviso_y_no_una_excepcion(wallets):
    """Un sello que no se puede leer se informa como aviso, no como error (REQ-19)."""
    chain, *_ = _cadena_valida(wallets)

    auditoria = chain.audit_chain(problema_del_sello="ilegible")

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "sello-ilegible")
    assert hallazgo.severidad == "aviso"
    assert hallazgo.reparacion == "fijar-sello"
    assert hallazgo.ubicacion == "Sello"
    assert auditoria.sello.problema == "ilegible"
    assert auditoria.sello.sello is None
    assert not any(h.codigo == "sello-ausente" for h in auditoria.hallazgos)
    assert auditoria.resumen.valida is True
    assert auditoria.limpia is False
    # Sin sello utilizable, el límite del recorte sigue declarado.
    assert any(limite.titulo == "Recorte de la cola" for limite in auditoria.limites)


def test_una_cadena_vacia_es_critica_y_ofrece_encadenar(wallets):
    """Sin ningún bloque falta el génesis: crítico y reparable encadenando."""
    chain = _chain(wallets)

    auditoria = chain.audit_chain()

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "cadena-vacia")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "encadenar"
    assert auditoria.resumen.bloques == 0
    assert auditoria.resumen.altura is None
    assert auditoria.resumen.cabeza_hash is None
    assert auditoria.resumen.cabeza_en is None
    assert auditoria.resumen.genesis_hash is None
    assert auditoria.bloques == ()
    assert auditoria.resumen.valida is False


def test_la_cabeza_tiene_que_ser_el_genesis(wallets):
    """Un primer bloque que no es el génesis se declara; solo el índice cero se repara."""
    ajeno = build_block(0, previous_hash="b" * 64)
    auditoria = _chain(wallets, blocks=[ajeno]).audit_chain()
    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "cabeza")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "encadenar"
    assert hallazgo.ubicacion == "Bloque 0"
    assert auditoria.bloques[0].estado == "cabeza"

    # Una cadena que empieza en el índice 1 no se renumera.
    sin_genesis = build_block(1, previous_hash="a" * 64)
    auditoria = _chain(wallets, blocks=[sin_genesis]).audit_chain()
    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "cabeza")
    assert hallazgo.reparacion is None
    assert hallazgo.ubicacion == "Bloque 1"


def test_un_previous_hash_que_no_encadena_es_critico_y_ofrece_encadenar(wallets):
    """Un `previous_hash` ajeno se detecta sin confundirlo con un hash alterado."""
    genesis = build_block(0)
    huerfano = build_block(1, previous_hash="a" * 64)
    chain = _chain(wallets, blocks=[genesis, huerfano])

    auditoria = chain.audit_chain()

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "encadenamiento")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "encadenar"
    assert hallazgo.ubicacion == "Bloque 1"
    assert auditoria.bloques[1].estado == "encadenamiento"
    assert "hash" not in {h.codigo for h in auditoria.hallazgos}


@pytest.mark.parametrize("block_id", [None, uuid4()], ids=["sin-bloque", "bloque-inexistente"])
def test_una_confirmada_sin_bloque_ofrece_aislarla(wallets, block_id):
    """Una confirmada sin bloque, o con uno que no existe, se aísla."""
    huerfana = _transaccion(wallets, status=TransactionStatus.CONFIRMED, block_id=block_id)
    genesis = build_block(0)
    chain = _chain(wallets, blocks=[genesis], transactions=[huerfana])

    auditoria = chain.audit_chain()

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "transaccion-sin-bloque")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "aislar"
    assert hallazgo.ubicacion == f"Transacción {str(huerfana.id)[:8]}…"


def test_la_coherencia_entre_estado_y_bloque_se_revisa(wallets):
    """Una pendiente o una rechazada con bloque se declaran; la reparación va por estado."""
    pendiente = _transaccion(wallets)
    rechazada = _transaccion(wallets)
    rechazada.status = TransactionStatus.REJECTED
    genesis = build_block(0, transactions=[pendiente, rechazada])
    pendiente.block_id = genesis.id
    rechazada.block_id = genesis.id
    chain = _chain(wallets, blocks=[genesis], transactions=[pendiente, rechazada])

    auditoria = chain.audit_chain()

    coherencias = [h for h in auditoria.hallazgos if h.codigo == "coherencia-de-estado"]
    assert len(coherencias) == 2
    assert {hallazgo.severidad for hallazgo in coherencias} == {"critico"}
    assert {hallazgo.reparacion for hallazgo in coherencias} == {
        "rechazar-pendientes",
        None,
    }


def test_una_wallet_que_no_esta_se_repara_segun_el_estado(wallets):
    """El emisor o el receptor ausente se marca; la firma no se reclama sin sus públicas."""
    desconocida = uuid4()
    confirmada = _transaccion(
        wallets, status=TransactionStatus.CONFIRMED, sender_id=desconocida
    )
    pendiente = _transaccion(wallets, receiver_id=uuid4())
    genesis = build_block(0, transactions=[confirmada])
    confirmada.block_id = genesis.id
    chain = _chain(wallets, blocks=[genesis], transactions=[confirmada, pendiente])

    auditoria = chain.audit_chain()

    hallazgos = [h for h in auditoria.hallazgos if h.codigo == "wallet-inexistente"]
    assert len(hallazgos) == 2
    assert {hallazgo.severidad for hallazgo in hallazgos} == {"critico"}
    assert {hallazgo.reparacion for hallazgo in hallazgos} == {
        "aislar",
        "rechazar-pendientes",
    }
    assert not any(h.codigo == "firma" for h in auditoria.hallazgos)


@pytest.mark.parametrize(
    ("monto", "mencion"),
    [
        (Decimal("NaN"), "finito"),
        (Decimal("Infinity"), "finito"),
        (Decimal("0"), "positivo"),
        (Decimal("-1.00000000"), "positivo"),
        (AMOUNT_MAX + Decimal("1"), "NUMERIC"),
        (Decimal("1.000000001"), "decimales"),
    ],
    ids=["nan", "infinito", "cero", "negativo", "fuera-de-rango", "precision"],
)
def test_un_monto_fuera_de_la_escala_es_critico(wallets, monto, mencion):
    """Un monto no finito, no positivo o fuera de la escala del esquema se marca."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED, amount=monto)
    genesis = build_block(0, transactions=[confirmada])
    confirmada.block_id = genesis.id
    chain = _chain(wallets, blocks=[genesis], transactions=[confirmada])

    auditoria = chain.audit_chain()

    hallazgos = [h for h in auditoria.hallazgos if h.codigo == "monto"]
    assert len(hallazgos) == 1
    assert hallazgos[0].severidad == "critico"
    assert hallazgos[0].reparacion == "aislar"
    assert mencion in hallazgos[0].detalle


def test_un_monto_invalido_en_el_pool_ofrece_rechazar_la_pendiente(wallets):
    """La reparación de un monto inválido depende del estado de la transacción."""
    pendiente = _transaccion(wallets, amount=Decimal("0"))
    chain, *_ = _cadena_valida(wallets, pendientes=[pendiente])

    auditoria = chain.audit_chain()

    hallazgo = next(h for h in auditoria.hallazgos if h.codigo == "monto")
    assert hallazgo.severidad == "critico"
    assert hallazgo.reparacion == "rechazar-pendientes"


def test_dos_filas_con_la_misma_firma_se_reportan_sin_reparacion(wallets):
    """La firma repetida es un crítico que ninguna reparación de la interfaz arregla."""
    firma = _transaccion(wallets).signature
    primera = _transaccion(wallets)
    primera.signature = firma
    segunda = _transaccion(wallets)
    segunda.signature = firma
    chain, *_ = _cadena_valida(wallets, pendientes=[primera, segunda])

    auditoria = chain.audit_chain()

    repetida = next(h for h in auditoria.hallazgos if h.codigo == "firma-repetida")
    assert repetida.severidad == "critico"
    assert repetida.reparacion is None
    assert str(primera.id)[:8] in repetida.detalle
    assert str(segunda.id)[:8] in repetida.detalle


def test_la_revision_marca_el_estado_de_cada_bloque(wallets):
    """La tabla de bloques distingue el correcto del que tiene el hash alterado."""
    confirmada = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    genesis = build_block(0)
    bloque = build_block(1, genesis, transactions=[confirmada])
    confirmada.block_id = bloque.id
    bloque.hash = "f" * 64
    chain = _chain(wallets, blocks=[genesis, bloque], transactions=[confirmada])

    auditoria = chain.audit_chain()

    assert [(r.indice, r.transacciones, r.estado) for r in auditoria.bloques] == [
        (0, 0, "correcto"),
        (1, 1, "alterado"),
    ]
    assert auditoria.bloques[0].detalle is None
    assert auditoria.bloques[1].detalle is not None
    assert auditoria.bloques[1].hash == "f" * 64


def test_las_reparaciones_son_unicas_y_ordenadas(wallets):
    """Cada reparación aparece una sola vez y en orden alfabético."""
    confirmada_sin_bloque = _transaccion(wallets, status=TransactionStatus.CONFIRMED)
    pendiente = _transaccion(wallets)
    pendiente.signature = "ab" * 64
    genesis = build_block(0)
    huerfano = build_block(1, previous_hash="a" * 64)
    chain = _chain(
        wallets,
        blocks=[genesis, huerfano],
        transactions=[confirmada_sin_bloque, pendiente],
    )

    auditoria = chain.audit_chain()

    assert auditoria.reparaciones == (
        "aislar",
        "encadenar",
        "fijar-sello",
        "rechazar-pendientes",
    )


def test_importar_la_auditoria_no_carga_flask_ni_psycopg():
    """El módulo del dominio no arrastra Flask ni el driver, como exige REQ-16."""
    codigo = (
        "import sys, src.domain.auditoria; "
        "assert 'flask' not in sys.modules, 'la auditoría no debe importar Flask'; "
        "assert 'psycopg' not in sys.modules, 'la auditoría no debe importar el driver'"
    )
    assert subprocess.run([sys.executable, "-c", codigo]).returncode == 0
