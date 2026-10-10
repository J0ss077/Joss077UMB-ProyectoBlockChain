"""REQ-01: registrar una wallet con el par ECDSA en la tabla.

La pública queda única y no vacía, el material privado se guarda cifrado y el
texto plano de la privada no aparece por ninguna parte de la base.
"""
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from psycopg.rows import dict_row

from src.domain.wallet import create_wallet, decrypt_private_key


def _indices_unicos_de_public_key(conexion) -> list[dict]:
    """Las definiciones de índice único sobre `wallets.public_key`."""
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'wallets'
              AND indexdef ILIKE '%unique%' AND indexdef ILIKE '%(public_key)%'
            """
        )
        return cursor.fetchall()


def test_req_01_la_publica_queda_unica_y_no_vacia(conexion, base_limpia, wallets, master_key):
    """La pública de una wallet registrada se lee igual, no está vacía y es única en la tabla."""
    cartera = wallets.add(create_wallet(master_key=master_key))

    guardada = wallets.get(cartera.id)
    assert guardada is not None
    assert guardada.public_key == cartera.public_key
    assert guardada.public_key != ""

    unicos = _indices_unicos_de_public_key(conexion)
    assert len(unicos) == 1, "la pública debe quedar única en la tabla"


def test_req_01_el_texto_plano_de_la_privada_no_aparece_en_la_base(
    conexion, base_limpia, wallets, master_key
):
    """Lo que se guarda es el token cifrado: el DER de la privada no está en la fila."""
    cartera = wallets.add(create_wallet(master_key=master_key))

    # El DER de la privada es el material en claro; descifrar el token vuelve a
    # dar ese DER, así que compararlo contra lo guardado es comprobar que el
    # texto plano no quedó en la base.
    en_claro = decrypt_private_key(cartera.private_key_encrypted, master_key).private_bytes(
        Encoding.DER, PrivateFormat.PKCS8, NoEncryption()
    )
    assert en_claro != cartera.private_key_encrypted

    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT public_key, private_key_encrypted FROM wallets WHERE id = %s",
            (cartera.id,),
        )
        fila = cursor.fetchone()

    assert fila["public_key"] == cartera.public_key
    assert bytes(fila["private_key_encrypted"]) == cartera.private_key_encrypted
    assert en_claro.hex() not in fila["public_key"]
    assert en_claro not in bytes(fila["private_key_encrypted"])
