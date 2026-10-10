"""Fixtures de la suite unitaria: transacciones con la firma de su emisor ya cableada.

Las pruebas de formato y de saldo llaman `validate(available=..., signature_exists=...)`
sin pasar llaves públicas: esta fábrica resuelve la pública del emisor y la del
receptor a partir de los identificadores de la transacción y firma con la privada
correspondiente, de modo que la firma verifique y lo que se mida sea el formato o
el saldo, no la firma. `Transaction.validate` conserva sus parámetros
`sender_public_key` y `receiver_public_key` para las pruebas de firma ajena (REQ-02).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.transaction import Transaction, TransactionStatus, ValidationResult
from src.domain.wallet import Wallet, create_wallet, sign_payload

# Marca de tiempo fija: el payload firmado la incluye, y fijarla hace
# reproducibles las transacciones que arman las pruebas.
CREATED_AT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
DEFAULT_AMOUNT = Decimal("10.00000000")


@dataclass(frozen=True, slots=True)
class SignedTransaction:
    """Una `Transaction` con la pública de su emisor y la de su receptor resueltas."""

    transaction: Transaction
    sender_public_key: str
    receiver_public_key: str

    def validate(self, *, available: Decimal, signature_exists: bool) -> ValidationResult:
        """Valida con la pública del emisor y la del receptor ya cableadas."""
        return self.transaction.validate(
            sender_public_key=self.sender_public_key,
            receiver_public_key=self.receiver_public_key,
            available=available,
            signature_exists=signature_exists,
        )

    def is_valid(self, **kwargs) -> bool:
        """Igual que `validate`, pero solo responde si fue aceptada."""
        return self.validate(**kwargs).accepted


def _transaction(*, sender_id: UUID, receiver_id: UUID, **fields) -> Transaction:
    """Transacción con los valores por defecto de una operación válida."""
    defaults = {
        "id": uuid4(),
        "amount": DEFAULT_AMOUNT,
        "status": TransactionStatus.PENDING,
        "signature": "",
        "block_id": None,
        "created_at": CREATED_AT,
    }
    defaults.update(fields)
    return Transaction(sender_id=sender_id, receiver_id=receiver_id, **defaults)


def _public_key_for(wallet_id: UUID, sender: Wallet, receiver: Wallet, fallback: str) -> str:
    """Resuelve la pública de un identificador conocido; si no lo es, usa la de referencia."""
    if wallet_id == sender.id:
        return sender.public_key
    if wallet_id == receiver.id:
        return receiver.public_key
    return fallback


def _signed_transaction(
    transaction: Transaction,
    sender: Wallet,
    receiver: Wallet,
    master_key: bytes,
    signer: Wallet | None = None,
) -> SignedTransaction:
    """Firma la transacción y devuelve el objeto con sus dos públicas cableadas."""
    sender_public_key = _public_key_for(
        transaction.sender_id, sender, receiver, sender.public_key
    )
    receiver_public_key = _public_key_for(
        transaction.receiver_id, sender, receiver, receiver.public_key
    )
    # Por defecto firma quien dice ser el emisor, para que la firma verifique.
    signer = signer or (receiver if sender_public_key == receiver.public_key else sender)
    transaction.signature = sign_payload(
        signer,
        transaction.signing_payload(sender_public_key, receiver_public_key),
        master_key,
    )
    return SignedTransaction(transaction, sender_public_key, receiver_public_key)


@pytest.fixture
def transaccion():
    """Fábrica de transacciones válidas y firmadas por el emisor que declaran."""

    master_key = Fernet.generate_key()
    emisora = create_wallet(master_key=master_key)
    receptora = create_wallet(master_key=master_key)

    def build(**fields) -> SignedTransaction:
        ids = {"sender_id": emisora.id, "receiver_id": receptora.id}
        ids.update(fields)
        sender_id = ids.pop("sender_id")
        receiver_id = ids.pop("receiver_id")
        return _signed_transaction(
            _transaction(sender_id=sender_id, receiver_id=receiver_id, **ids),
            emisora,
            receptora,
            master_key,
        )

    return build


@pytest.fixture
def transaccion_de_otra_wallet():
    """Transacción firmada por una wallet distinta de la que declara ser su emisora."""
    master_key = Fernet.generate_key()
    emisora = create_wallet(master_key=master_key)
    receptora = create_wallet(master_key=master_key)
    ajena = create_wallet(master_key=master_key)
    return _signed_transaction(
        _transaction(sender_id=emisora.id, receiver_id=receptora.id),
        emisora,
        receptora,
        master_key,
        signer=ajena,
    )
