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
    CONSTRAINT chk_transactions_sender_ne_receiver CHECK (sender_id <> receiver_id),
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

-- ---------------------------------------------------------------------------
-- users: cuentas del sistema, con su rol y el estado de la alta moderada
-- (REQ-30, REQ-31). La relación va de `users` hacia `wallets` y no al revés: la
-- wallet nace recién con la aprobación, así que `wallet_id` es nulo mientras la
-- cuenta esté pendiente o haya sido rechazada (diseño §6). El `UNIQUE` de
-- `wallet_id` admite varios nulos, que es justo lo que hace falta, y el
-- `ON DELETE RESTRICT` impide borrar una wallet con dueño.
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    estado TEXT NOT NULL,
    motivo_rechazo TEXT NULL,
    wallet_id UUID NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    aprobado_en TIMESTAMPTZ NULL,

    CONSTRAINT users_username_key UNIQUE (username),
    CONSTRAINT users_wallet_id_key UNIQUE (wallet_id),
    CONSTRAINT users_role_check CHECK (role IN ('administrador', 'usuario')),
    CONSTRAINT users_estado_check CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
    CONSTRAINT fk_users_wallet
        FOREIGN KEY (wallet_id) REFERENCES wallets (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_users_motivo_rechazo_requerido
        CHECK (estado <> 'rechazado' OR motivo_rechazo IS NOT NULL),
    -- El aprobado común tiene wallet y el administrador puede no tenerla: es la
    -- única cuenta que el diseño admite sin wallet (decisión 4 y §6). Pendiente y
    -- rechazado siguen sin wallet, porque la wallet nace recién con la aprobación.
    -- La regla se expresa por rol y no como bicondicional contra `aprobado`: esa
    -- forma obligaba a que el administrador sembrado tuviera una wallet que no usa.
    CONSTRAINT chk_users_wallet_coherente_con_el_estado
        CHECK (
            (estado = 'aprobado' AND (role = 'administrador' OR wallet_id IS NOT NULL))
            OR (estado <> 'aprobado' AND wallet_id IS NULL)
        )
);

-- El `UNIQUE` de `username` distingue mayúsculas. La aplicación normaliza a
-- minúsculas (REQ-30), pero la base también tiene que impedir que dos cuentas se
-- diferencien sólo por la caja cuando alguien escribe por fuera del repositorio:
-- con este índice único, `ana` y `ANA` son la misma cuenta para el motor. Además
-- es el índice que resuelve `get_by_username`, que compara sobre `lower(username)`.
CREATE UNIQUE INDEX users_username_minusculas ON users (lower(username));

COMMENT ON COLUMN users.username IS
    'Nombre único con el que se ingresa, normalizado a minúsculas por la aplicación (REQ-30).';
COMMENT ON COLUMN users.password_hash IS
    'Hash `scrypt` con sal por usuario; la contraseña en claro nunca se guarda (REQ-36).';
COMMENT ON COLUMN users.role IS
    'Rol de autorización: `administrador` o `usuario` (REQ-38).';
COMMENT ON COLUMN users.estado IS
    'Estado del alta moderada: `pendiente`, `aprobado` o `rechazado` (REQ-30, REQ-31).';
COMMENT ON COLUMN users.motivo_rechazo IS
    'Motivo que deja el administrador al rechazar; obligatorio en estado `rechazado` (REQ-31).';
COMMENT ON COLUMN users.wallet_id IS
    'Wallet del usuario, ligada al aprobar; nula mientras el alta no esté aprobada (REQ-33).';
COMMENT ON COLUMN users.aprobado_en IS
    'Momento de la aprobación; nulo mientras el alta no esté aprobada (REQ-33).';

-- ---------------------------------------------------------------------------
-- contactos: la agenda de cada usuario común. Es de un solo sentido —agregar a
-- alguien no lo obliga a agregarte— y la pareja es la clave primaria, así que un
-- contacto no se repite. Nadie se agenda a sí mismo. A diferencia del resto del
-- esquema el borrado va en cascada: una fila de la agenda no tiene sentido sin
-- las dos cuentas y no hay historia que proteger, a diferencia de una wallet.
-- ---------------------------------------------------------------------------
CREATE TABLE contactos (
    usuario_id UUID NOT NULL,
    contacto_id UUID NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_contactos PRIMARY KEY (usuario_id, contacto_id),
    CONSTRAINT fk_contactos_usuario
        FOREIGN KEY (usuario_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_contactos_contacto
        FOREIGN KEY (contacto_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_contactos_no_a_si_mismo CHECK (usuario_id <> contacto_id)
);

COMMENT ON TABLE contactos IS
    'Agenda de cada usuario común: a quién agregó por su nombre de usuario.';

-- ---------------------------------------------------------------------------
-- solicitudes_de_contrasena: el cambio de contraseña del usuario común no se
-- aplica solo; queda pendiente hasta que un administrador lo apruebe. La nueva
-- contraseña se guarda ya hasheada —nunca en claro (REQ-36)— y recién al aprobar
-- reemplaza a `users.password_hash`. Una cuenta tiene a lo sumo una solicitud
-- pendiente a la vez, y el rechazo puede llevar un motivo.
-- ---------------------------------------------------------------------------
CREATE TABLE solicitudes_de_contrasena (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    usuario_id UUID NOT NULL,
    password_hash TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    motivo_rechazo TEXT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resuelto_en TIMESTAMPTZ NULL,

    CONSTRAINT fk_solicitudes_de_contrasena_usuario
        FOREIGN KEY (usuario_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_solicitudes_de_contrasena_estado
        CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
    CONSTRAINT chk_solicitudes_de_contrasena_resuelta
        CHECK ((estado = 'pendiente') = (resuelto_en IS NULL))
);

CREATE UNIQUE INDEX uq_solicitudes_de_contrasena_una_pendiente
    ON solicitudes_de_contrasena (usuario_id) WHERE estado = 'pendiente';

COMMENT ON COLUMN solicitudes_de_contrasena.password_hash IS
    'Hash `scrypt` de la contraseña pedida; reemplaza al de la cuenta sólo al aprobarse.';

-- ---------------------------------------------------------------------------
-- fotos_de_perfil: la foto opcional de cada cuenta. La imagen no vive en la base:
-- es un archivo aparte, en la carpeta de fotos (`FOTOS_DIR`), y esta tabla guarda
-- sólo su nombre, su tipo y cuándo cambió. Sin fila, la interfaz muestra la
-- inicial del nombre. El nombre lo genera la aplicación —32 dígitos hexadecimales
-- y la extensión— y el CHECK impide que una fila apunte a cualquier otra ruta.
-- Sólo se admiten los tres formatos que el navegador pinta sin ejecutar nada
-- (nunca SVG); la aplicación reconoce el tipo por los bytes antes de guardar.
-- ---------------------------------------------------------------------------
CREATE TABLE fotos_de_perfil (
    usuario_id UUID PRIMARY KEY,
    archivo TEXT NOT NULL,
    tipo TEXT NOT NULL,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_fotos_de_perfil_usuario
        FOREIGN KEY (usuario_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uq_fotos_de_perfil_archivo UNIQUE (archivo),
    CONSTRAINT chk_fotos_de_perfil_archivo
        CHECK (archivo ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'),
    CONSTRAINT chk_fotos_de_perfil_tipo
        CHECK (tipo IN ('image/jpeg', 'image/png', 'image/webp'))
);
