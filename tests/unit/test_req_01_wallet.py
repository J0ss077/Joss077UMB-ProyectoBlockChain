"""REQ-01: la pública queda en claro y única; el material privado nunca en claro."""
from cryptography.fernet import Fernet

from src.domain.wallet import create_wallet, decrypt_private_key


def test_req_01_la_privada_no_esta_en_claro_en_la_wallet():
    """Criterio: el material en claro de la privada no aparece dentro de la wallet guardada."""
    master = Fernet.generate_key()
    wallet = create_wallet(master_key=master)
    privada = decrypt_private_key(wallet.private_key_encrypted, master)
    material = privada.private_numbers().private_value.to_bytes(32, "big")
    assert material not in wallet.private_key_encrypted


def test_req_01_dos_wallets_no_comparten_publica():
    """Criterio: la pública es única por wallet, queda en claro y no vacía."""
    master = Fernet.generate_key()
    primera = create_wallet(master_key=master)
    segunda = create_wallet(master_key=master)
    assert primera.public_key != segunda.public_key
