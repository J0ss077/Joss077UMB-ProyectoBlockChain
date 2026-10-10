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
