"""Wallet ECDSA con la pública en claro y el material privado cifrado (REQ-01).

Aquí vive también la firma del origen de una transacción y su verificación
(REQ-02). La privada nunca se guarda en claro: se cifra con una clave maestra
que llega por el entorno (REQ-21), así que firmar implica descifrarla.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_der_private_key,
)

# `SECP256K1` es la clase de la curva; la librería pide una instancia en cada uso.
CURVE = ec.SECP256K1

SIGNATURE_ALGORITHM = ec.ECDSA(hashes.SHA256())


@dataclass(slots=True)
class Wallet:
    """Wallet registrada: pública en claro, privada cifrada.

    Invariante: ningún campo guarda el material en claro de la privada;
    `private_key_encrypted` contiene solo el token cifrado.
    """

    id: UUID
    public_key: str
    private_key_encrypted: bytes
    created_at: datetime


def generate_private_key() -> ec.EllipticCurvePrivateKey:
    """Genera el par sobre secp256k1 (decisión 1 del diseño)."""
    return ec.generate_private_key(CURVE())


def public_key_hex(private_key: ec.EllipticCurvePrivateKey) -> str:
    """Serializa la pública como punto comprimido en hexadecimal."""
    return private_key.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint).hex()


def public_key_from_hex(value: str) -> ec.EllipticCurvePublicKey:
    """Reconstruye la pública desde el hexadecimal con que se guardó."""
    return ec.EllipticCurvePublicKey.from_encoded_point(CURVE(), bytes.fromhex(value))


def encrypt_private_key(private_key: ec.EllipticCurvePrivateKey, master_key: bytes) -> bytes:
    """Cifra el DER de la privada con Fernet; la clave maestra viene del entorno."""
    der = private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return Fernet(master_key).encrypt(der)


def decrypt_private_key(token: bytes, master_key: bytes) -> ec.EllipticCurvePrivateKey:
    """Descifra el token y reconstruye la privada; con otra clave maestra falla."""
    return load_der_private_key(Fernet(master_key).decrypt(token), password=None)


def create_wallet(
    *,
    master_key: bytes,
    wallet_id: UUID | None = None,
    created_at: datetime | None = None,
) -> Wallet:
    """Registra una wallet nueva, con identificador generado aquí (decisión 5)."""
    private_key = generate_private_key()
    return Wallet(
        id=wallet_id if wallet_id is not None else uuid4(),
        public_key=public_key_hex(private_key),
        private_key_encrypted=encrypt_private_key(private_key, master_key),
        created_at=created_at if created_at is not None else datetime.now(UTC),
    )


def sign_payload(wallet: Wallet, payload: bytes, master_key: bytes) -> str:
    """Firma el payload con la privada de la wallet y devuelve el DER en hexadecimal.

    Se descifra la privada en cada firma a propósito: el texto plano no vive en
    ningún objeto que se guarde, así que una wallet en memoria no lo expone.
    """
    private_key = decrypt_private_key(wallet.private_key_encrypted, master_key)
    return private_key.sign(payload, SIGNATURE_ALGORITHM).hex()


def verify(public_key_hex: str, signature_hex: str, payload: bytes) -> bool:
    """Comprueba la firma contra la pública; cualquier material ajeno no verifica."""
    try:
        public_key_from_hex(public_key_hex).verify(
            bytes.fromhex(signature_hex), payload, SIGNATURE_ALGORITHM
        )
    except (InvalidSignature, ValueError):
        # Una firma o una pública mal formadas no son un fallo del programa.
        return False
    return True
