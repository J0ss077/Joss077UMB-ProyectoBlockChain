-- Consultas de consulta y de evidencia sobre la base del ledger (Fase 4).
--
-- No crean ni modifican nada: son las que se pegan en `psql` para mostrar que la
-- interfaz trabaja sobre PostgreSQL y no sobre datos de ejemplo del navegador.
-- Se ejecutan así, desde la raíz del proyecto:
--
--   docker compose exec -T postgres psql -U blockchain_user -d blockchain_db < db/consultas.sql
--
-- o, con el cliente del equipo:
--
--   psql "$DATABASE_URL" -f db/consultas.sql
--
-- El esquema de las tablas lo crea `db/init.sql` y los datos de demostración los
-- siembra `python -m src.bootstrap` (el génesis se calcula y no puede venir en un
-- INSERT fijo).

\echo '=== 1. Cuántas filas hay en cada tabla del ledger ==='
SELECT 'wallets' AS tabla, count(*) FROM wallets
UNION ALL SELECT 'blocks', count(*) FROM blocks
UNION ALL SELECT 'transactions', count(*) FROM transactions
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'contactos', count(*) FROM contactos
UNION ALL SELECT 'solicitudes_de_contrasena', count(*) FROM solicitudes_de_contrasena
ORDER BY tabla;

\echo '=== 2. Wallets con su saldo disponible (la misma cuenta de la aplicación) ==='
SELECT w.public_key,
       COALESCE(SUM(CASE WHEN t.receiver_id = w.id AND t.status = 'confirmed' THEN t.amount END), 0)
     - COALESCE(SUM(CASE WHEN t.sender_id = w.id AND t.status = 'confirmed' THEN t.amount END), 0)
     - COALESCE(SUM(CASE WHEN t.sender_id = w.id AND t.status = 'pending' THEN t.amount END), 0)
       AS disponible
FROM wallets w
LEFT JOIN transactions t ON t.sender_id = w.id OR t.receiver_id = w.id
GROUP BY w.id, w.public_key
ORDER BY disponible;

\echo '=== 3. La cadena: cada bloque con el hash del anterior ==='
SELECT block_index, timestamp, previous_hash, hash
FROM blocks
ORDER BY block_index;

\echo '=== 4. Los bloques eslabonados sin huecos (no debería devolver filas) ==='
-- `lag` necesita su propia consulta: una función de ventana no puede ir en el WHERE.
SELECT block_index, hash_esperado, previous_hash
FROM (
    SELECT b.block_index,
           b.previous_hash,
           lag(b.hash) OVER (ORDER BY b.block_index) AS hash_esperado
    FROM blocks b
) eslabones
WHERE block_index > 0
  AND previous_hash IS DISTINCT FROM hash_esperado;

\echo '=== 5. Transacciones con el nombre de cada lado, la más nueva primero ==='
SELECT t.created_at,
       emisor.username   AS envia,
       receptor.username AS recibe,
       t.amount,
       t.status,
       t.block_id
FROM transactions t
LEFT JOIN users emisor   ON emisor.wallet_id = t.sender_id
LEFT JOIN users receptor ON receptor.wallet_id = t.receiver_id
ORDER BY t.created_at DESC
LIMIT 20;

\echo '=== 6. El pool: lo que está en espera de entrar a un bloque ==='
SELECT t.created_at, t.sender_id, t.receiver_id, t.amount
FROM transactions t
WHERE t.status = 'pending'
ORDER BY t.created_at;

\echo '=== 7. Las cuentas y su estado de alta moderada ==='
SELECT username, role, estado,
       wallet_id IS NOT NULL AS tiene_wallet,
       creado_en, aprobado_en, motivo_rechazo
FROM users
ORDER BY creado_en;

\echo '=== 8. La última fila escrita: la evidencia del registro hecho en la interfaz ==='
SELECT created_at, id, sender_id, receiver_id, amount, status
FROM transactions
ORDER BY created_at DESC
LIMIT 1;

\echo '=== 9. Cuentas pendientes de aprobación y solicitudes de contraseña pendientes ==='
SELECT u.username, u.estado, u.creado_en
FROM users u
WHERE u.estado = 'pendiente'
ORDER BY u.creado_en;

SELECT u.username, s.creado_en AS pedida_en
FROM solicitudes_de_contrasena s
JOIN users u ON u.id = s.usuario_id
WHERE s.estado = 'pendiente'
ORDER BY s.creado_en;
