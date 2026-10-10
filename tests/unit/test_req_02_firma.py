"""REQ-02: una transacción firmada por su emisor verifica; firmada por otra wallet se rechaza."""
from cryptography.fernet import Fernet

from src.domain.wallet import create_wallet, sign_payload, verify


def test_req_02_la_firma_del_emisor_verifica_y_la_ajena_no():
    """Criterio: la firma del emisor verifica; la misma firmada por otra wallet se rechaza.

    El contenido alterado también deja de verificar, que es lo que hace
    detectable el cambio de un dato firmado.
    """
    master = Fernet.generate_key()
    emisora, ajena = create_wallet(master_key=master), create_wallet(master_key=master)
    payload = b"transaccion canonica"
    firma = sign_payload(emisora, payload, master)
    assert verify(emisora.public_key, firma, payload) is True
    assert verify(ajena.public_key, firma, payload) is False
    assert verify(emisora.public_key, firma, payload + b"x") is False


def test_req_02_la_firma_es_der_en_hexadecimal_minuscula():
    """Criterio: la firma viaja como DER en hexadecimal minúscula y verifica tal cual.

    Se fija la codificación igual que se fija la forma canónica: cambiarla dejaría de
    verificar las firmas ya guardadas en la base.
    """
    master = Fernet.generate_key()
    emisora = create_wallet(master_key=master)
    payload = b"transaccion canonica"
    firma = sign_payload(emisora, payload, master)

    assert firma == firma.lower()
    # DER de una firma ECDSA: una SEQUENCE (0x30) con dos INTEGER; sobre secp256k1
    # mide entre 68 y 72 bytes según el relleno de los dos enteros.
    assert firma.startswith("30")
    assert 68 <= len(bytes.fromhex(firma)) <= 72
    assert verify(emisora.public_key, firma, payload) is True
