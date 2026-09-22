-- Datos de prueba mínimos y coherentes (orden: wallets → blocks → transactions).
-- Las llaves privadas son BYTEA de material cifrado simulado (no texto plano).
-- Idempotente: no duplica si ya existen por public_key / hash / ids fijos.

-- Wallets de prueba (Alice, Bob, Carol)
INSERT INTO wallets (id, public_key, private_key_encrypted)
VALUES
    (
        '11111111-1111-1111-1111-111111111111',
        'alice_ecdsa_pubkey_hex_demo_01',
        decode('656e633a616c6963655f707269765f64656d6f', 'hex')  -- enc:alice_priv_demo
    ),
    (
        '22222222-2222-2222-2222-222222222222',
        'bob_ecdsa_pubkey_hex_demo_02',
        decode('656e633a626f625f707269765f64656d6f', 'hex')        -- enc:bob_priv_demo
    ),
    (
        '33333333-3333-3333-3333-333333333333',
        'carol_ecdsa_pubkey_hex_demo_03',
        decode('656e633a6361726f6c5f707269765f64656d6f', 'hex')  -- enc:carol_priv_demo
    )
ON CONFLICT (public_key) DO NOTHING;

-- Bloque génesis (índice 0) y un bloque con transacciones confirmadas
INSERT INTO blocks (id, block_index, timestamp, previous_hash, hash)
VALUES
    (
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        0,
        '2026-09-01 10:00:00+00',
        '0000000000000000000000000000000000000000000000000000000000000000',
        'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0'
    ),
    (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        1,
        '2026-09-01 10:05:00+00',
        'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
        'f0e1d2c3b4a5968778695a4b3c2d1e0f1234567890abcdef1234567890abcdef'
    )
ON CONFLICT (hash) DO NOTHING;

-- Transacciones: dos confirmadas en el bloque 1, una pendiente en el pool
INSERT INTO transactions (
    id, sender_id, receiver_id, amount, status, signature, block_id, created_at
)
VALUES
    (
        '44444444-4444-4444-4444-444444444401',
        '11111111-1111-1111-1111-111111111111',
        '22222222-2222-2222-2222-222222222222',
        50.00000000,
        'confirmed',
        'sig_alice_to_bob_50_demo',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '2026-09-01 10:04:00+00'
    ),
    (
        '44444444-4444-4444-4444-444444444402',
        '22222222-2222-2222-2222-222222222222',
        '33333333-3333-3333-3333-333333333333',
        15.50000000,
        'confirmed',
        'sig_bob_to_carol_15_5_demo',
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        '2026-09-01 10:04:30+00'
    ),
    (
        '44444444-4444-4444-4444-444444444403',
        '11111111-1111-1111-1111-111111111111',
        '33333333-3333-3333-3333-333333333333',
        10.00000000,
        'pending',
        'sig_alice_to_carol_10_demo',
        NULL,
        '2026-09-01 10:06:00+00'
    )
ON CONFLICT (id) DO NOTHING;
