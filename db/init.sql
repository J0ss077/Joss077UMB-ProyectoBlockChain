-- Esquema del ledger (REQ-15).
-- Sale del modelo relacional del eje (wallets, blocks, transactions) y su
-- estructura no la decide el código: la aplicación nunca ejecuta DDL, así que
-- este archivo es la única fuente de las tablas, los CHECK, las claves foráneas
-- y los índices. Los valores por defecto de `id`, `status` y `created_at` son
-- respaldo de la base; la aplicación los genera para poder calcular el hash del
-- bloque antes de escribirlo (decisión 5 del diseño).

-- `uuid_generate_v4()` es el valor por defecto del modelo del eje.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- wallets: par de llaves ECDSA. La pública identifica y la privada solo vive
-- cifrada (REQ-01), así que la columna es BYTEA y el CHECK exige que no vaya vacía.
-- ---------------------------------------------------------------------------
CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    public_key TEXT NOT NULL,
    private_key_encrypted BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_wallets_public_key UNIQUE (public_key),
    CONSTRAINT chk_wallets_public_key_not_blank CHECK (length(trim(public_key)) > 0),
    CONSTRAINT chk_wallets_private_key_encrypted_not_empty
        CHECK (octet_length(private_key_encrypted) > 0)
);

COMMENT ON COLUMN wallets.private_key_encrypted IS
    'Material cifrado de la llave privada ECDSA; el texto plano de la privada nunca se guarda (REQ-01).';

-- ---------------------------------------------------------------------------
-- blocks: índice, marca de tiempo y los dos hashes del encadenamiento (REQ-07,
-- REQ-14). El índice y los hashes son únicos para que dos bloques no puedan
-- ocupar el mismo eslabón, y el génesis es el único que puede repetir hash
-- previo y hash propio, porque no tiene predecesor real.
-- ---------------------------------------------------------------------------
CREATE TABLE blocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    block_index INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    previous_hash CHAR(64) NOT NULL,
    hash CHAR(64) NOT NULL,

    CONSTRAINT uq_blocks_block_index UNIQUE (block_index),
    CONSTRAINT uq_blocks_hash UNIQUE (hash),
    CONSTRAINT chk_blocks_index_non_negative CHECK (block_index >= 0),
    CONSTRAINT chk_blocks_previous_hash_sha256 CHECK (previous_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_blocks_hash_sha256 CHECK (hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_blocks_hash_differs_from_previous
        CHECK (hash <> previous_hash OR block_index = 0)
);

-- ---------------------------------------------------------------------------
-- transactions: emisor, receptor, monto, estado, firma y bloque opcional.
-- La coherencia estado/bloque (REQ-12) es un CHECK porque vale para toda fila,
-- la escriba el camino de la aplicación o una prueba: `confirmed` exige bloque y
-- `pending` o `rejected` lo dejan nulo. La fila inválida que REQ-11 permite
-- guardar es la que este CHECK admite: sin bloque. Los errores de estas
-- restricciones suben sin traducir (REQ-19).
-- ---------------------------------------------------------------------------
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sender_id UUID NOT NULL,
    receiver_id UUID NOT NULL,
    amount NUMERIC(18, 8) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    signature TEXT NOT NULL,
    block_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_transactions_sender
        FOREIGN KEY (sender_id) REFERENCES wallets (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_transactions_receiver
        FOREIGN KEY (receiver_id) REFERENCES wallets (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_transactions_block
        FOREIGN KEY (block_id) REFERENCES blocks (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT chk_transactions_amount_positive CHECK (amount > 0),
    -- Segunda desviación del modelo relacional del eje, aprobada el 2026-10-10: el
    -- eje prohíbe que el emisor y el receptor coincidan, y esa regla impide la única
    -- fila con la que el ledger puede recibir valor de fuera, porque el modelo de
    -- saldos no tiene emisión y toda transacción descuenta el saldo del emisor
    -- (REQ-05). El capital de constitución de la demostración se acredita con esa
    -- fila; el resto de las reglas de formato se aplican igual.
    CONSTRAINT chk_transactions_status CHECK (status IN ('pending', 'confirmed', 'rejected')),
    CONSTRAINT chk_transactions_signature_not_blank CHECK (length(trim(signature)) > 0),
    CONSTRAINT chk_transactions_block_status_consistency CHECK (
        (status = 'confirmed' AND block_id IS NOT NULL)
        OR (status IN ('pending', 'rejected') AND block_id IS NULL)
    )
);

-- Los cuatro índices del eje: las dos direcciones del historial de una wallet,
-- el bloque que agrupa cada transacción y el estado del pool.
CREATE INDEX idx_transactions_sender_id ON transactions (sender_id);
CREATE INDEX idx_transactions_receiver_id ON transactions (receiver_id);
CREATE INDEX idx_transactions_block_id ON transactions (block_id);
CREATE INDEX idx_transactions_status ON transactions (status);

-- Única desviación del modelo relacional del eje, aprobada el 2026-10-10
-- (decisión 4): el índice único sobre la firma. Es el respaldo del motor para
-- REQ-03, porque dos filas con la misma firma son la misma transacción
-- presentada dos veces, y el dominio consulta antes para poder dar el motivo.
CREATE UNIQUE INDEX uq_transactions_signature ON transactions (signature);
