-- Esquema del ledger local (nodo único).
-- Entidades alineadas con la documentación de Fase 1/2:
-- wallets (par de llaves), transacciones (emisor, receptor, monto, estado, firma)
-- y bloques (índice, timestamp, hash anterior, hash propio, transacciones agrupadas).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- wallets
-- Par de llaves ECDSA: la pública identifica; la privada firma y NUNCA se
-- almacena en texto plano (solo material cifrado en BYTEA).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wallets (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    public_key              TEXT NOT NULL,
    private_key_encrypted   BYTEA NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_wallets_public_key UNIQUE (public_key),
    CONSTRAINT chk_wallets_public_key_not_blank
        CHECK (length(trim(public_key)) > 0),
    CONSTRAINT chk_wallets_private_key_encrypted_not_empty
        CHECK (octet_length(private_key_encrypted) > 0)
);

COMMENT ON COLUMN wallets.private_key_encrypted IS
    'Material cifrado de la llave privada ECDSA; nunca texto plano.';

-- ---------------------------------------------------------------------------
-- blocks
-- Estructura documentada: índice, timestamp, hash del bloque anterior,
-- hash propio (SHA-256) y relación con las transacciones que agrupa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blocks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    block_index     INTEGER NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    previous_hash   CHAR(64) NOT NULL,
    hash            CHAR(64) NOT NULL,

    CONSTRAINT uq_blocks_block_index UNIQUE (block_index),
    CONSTRAINT uq_blocks_hash UNIQUE (hash),
    CONSTRAINT chk_blocks_index_non_negative
        CHECK (block_index >= 0),
    CONSTRAINT chk_blocks_previous_hash_sha256
        CHECK (previous_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_blocks_hash_sha256
        CHECK (hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_blocks_hash_differs_from_previous
        CHECK (hash <> previous_hash OR block_index = 0)
);

-- ---------------------------------------------------------------------------
-- transactions
-- Emisor/receptor = wallets; monto; estado del flujo (pool pendiente /
-- confirmada en bloque / rechazada); firma digital del emisor.
-- block_id NULL = pendiente en el pool (aún no agrupada en un bloque).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sender_id       UUID NOT NULL,
    receiver_id     UUID NOT NULL,
    amount          NUMERIC(18, 8) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    signature       TEXT NOT NULL,
    block_id        UUID NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_transactions_sender
        FOREIGN KEY (sender_id) REFERENCES wallets (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_transactions_receiver
        FOREIGN KEY (receiver_id) REFERENCES wallets (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_transactions_block
        FOREIGN KEY (block_id) REFERENCES blocks (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT chk_transactions_amount_positive
        CHECK (amount > 0),
    CONSTRAINT chk_transactions_sender_ne_receiver
        CHECK (sender_id <> receiver_id),
    CONSTRAINT chk_transactions_status
        CHECK (status IN ('pending', 'confirmed', 'rejected')),
    CONSTRAINT chk_transactions_signature_not_blank
        CHECK (length(trim(signature)) > 0),
    CONSTRAINT chk_transactions_block_status_consistency
        CHECK (
            (status = 'confirmed' AND block_id IS NOT NULL)
            OR (status IN ('pending', 'rejected') AND block_id IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_transactions_sender_id
    ON transactions (sender_id);

CREATE INDEX IF NOT EXISTS idx_transactions_receiver_id
    ON transactions (receiver_id);

CREATE INDEX IF NOT EXISTS idx_transactions_block_id
    ON transactions (block_id);

CREATE INDEX IF NOT EXISTS idx_transactions_status
    ON transactions (status);
