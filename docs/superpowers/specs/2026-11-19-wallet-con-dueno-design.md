# Wallet con dueño y varias wallets por cuenta — diseño

**Proyecto**: _Diseño de la arquitectura de un sistema transaccional basado en blockchain._
**Alcance**: el registro de wallets deja de crear cuentas huérfanas: el administrador elige a
quién se la asigna. Una cuenta común pasa a poder tener **una o varias** wallets. No entra el
rediseño visual: se reutilizan los componentes del sistema de diseño.

---

## 1. Por qué

Hoy toda wallet registrada desde «Registrar wallet» queda «Sin dueño» y es inerte: no tiene
saldo ni forma de usarse, porque el dueño se guarda en `users.wallet_id` y esa ligadura sólo la
escribe la aprobación de cuentas, una wallet por cuenta y con `UNIQUE`.

Se quiere que el administrador, al registrar, **pregunte a quién se la asigna**, y que una
cuenta pueda acumular varias wallets (por ejemplo, una para operar y otra para ahorrar).

## 2. Decisiones

1. **La propiedad vive en la wallet**: `wallets.owner_id UUID NULL`, con `NULL` = «sin dueño».
   Es el único lugar de la verdad; `users.wallet_id`, su índice único y su CHECK se eliminan.
2. **Una wallet tiene como máximo un dueño** (una columna, una llave foránea); **una cuenta
   puede tener 0, 1 o muchas wallets**.
3. **El dueño se elige al registrar y queda fijo.** No hay reasignación en esta entrega: la
   acción de cambiar dueño de una wallet existente queda fuera de alcance.
4. **La aprobación sigue creando la primera wallet con el saldo de bienvenida** (REQ-33 se
   conserva). Las wallets adicionales nacen con saldo 0 y se mueven con transacciones.
5. **Sólo una cuenta común aprobada puede ser dueña.** El administrador no tiene wallet;
   pendientes y rechazados tampoco. La regla se valida en el servicio, porque el esquema ya no
   puede expresarla como CHECK entre dos tablas.
6. **El registro por nombre de usuario apunta a la wallet principal**: la más antigua de la
   cuenta. Las demás se direccionan por su identificador. Esto conserva el envío por nombre de
   REQ-34 sin inventar un selector de destino en el formulario de envío.
7. El registro de wallet sigue siendo **sólo del administrador** (matriz de permisos, §8 del
   diseño de usuarios).

## 3. Modelo de datos (`db/init.sql`)

En `wallets`:

```sql
owner_id UUID NULL,
-- ...
CONSTRAINT fk_wallets_owner
    FOREIGN KEY (owner_id) REFERENCES users (id)
    ON DELETE RESTRICT ON UPDATE CASCADE
```

- La FK se agrega con `ALTER TABLE wallets` después de crear `users`, porque `wallets` se crea
  antes y `users` ya no apunta a `wallets`.
- `CREATE INDEX idx_wallets_owner ON wallets (owner_id);`
- Comentario de columna: «Cuenta dueña de la wallet; `NULL` es una wallet sin dueño.»

En `users` se elimina `wallet_id`, `users_wallet_id_key`, `fk_users_wallet` y
`chk_users_wallet_coherente_con_el_estado`; el comentario del bloque se actualiza para explicar
que la relación ahora va de `wallets` hacia `users`.

## 4. Cuentas

### Puerto `RepositorioDeUsuarios` (`src/accounts/ports.py`)

Cambian o aparecen:

- `aprobar(id: UUID) -> Usuario | None` — ya no recibe wallet; sólo pasa a `aprobado`.
- `list_aprobados() -> Sequence[Usuario]` — cuentas `role='usuario' AND estado='aprobado'`,
  ordenadas por `username`; es la lista del selector.
- `wallets_de(usuario_id: UUID) -> Sequence[UUID]` — identificadores de sus wallets, ordenados
  por `created_at, id` (la primera es la principal).
- `wallet_principal(usuario_id: UUID) -> UUID | None` — la más antigua.
- `asignar_wallet(wallet_id: UUID, usuario_id: UUID) -> bool` — `UPDATE wallets SET owner_id`
  con `WHERE id = %s AND owner_id IS NULL`; `False` si la wallet no existe o ya tiene dueño.
- `nombres_por_wallet()` — ahora `SELECT w.id, u.username FROM wallets w JOIN users u ON
  u.id = w.owner_id`.
- `sembrar(usuario)` y `add_pendiente(usuario)` dejan de escribir `wallet_id`.

### Servicio `Cuentas` (`src/accounts/service.py`)

- `aprobar(id)`: registra la wallet, acredita el saldo de bienvenida, pasa la cuenta a
  `aprobado` y le asigna la wallet como dueña, todo en la misma transacción (`commit` único).
- `registrar_wallet(dueno_id: UUID | None) -> Wallet`: valida el dueño si viene (existe, está
  aprobado y es `role='usuario'`; si no, `DuenoInvalido`), registra la wallet, la asigna y
  confirma. Con `None` deja la wallet sin dueño.
- `usuarios_aprobados() -> Sequence[Usuario]` — para el selector.
- `wallets_de(usuario_id) -> Sequence[UUID]` y `wallet_principal(usuario_id) -> UUID | None`.
- Excepción nueva `DuenoInvalido`, reexportada en `__all__`.
- `Usuario` pierde `wallet_id` (`src/accounts/model.py`).

### Semilla (`src/bootstrap.py`)

- `_cuenta_aprobada(...)` deja de recibir `wallet_id`.
- `sembrar_usuarios()` inserta la cuenta y, si la wallet de demostración existe y no tiene
  dueño, la asigna. Es idempotente: una segunda corrida no reescribe nada.

## 5. Presentación

### Registro (`src/web/app.py`, `wallet.html`)

- `GET /wallets` pasa `usuarios=cuentas.usuarios_aprobados()` y `error=None`.
- `POST /wallets` lee el campo `dueno` (identificador de cuenta o vacío) y llama
  `cuentas.registrar_wallet(...)`. Si el dueño no sirve, vuelve a pintar el formulario con el
  motivo; si sirve, pinta el resultado de hoy.
- El formulario es un `select` con «Déjala sin dueño» como opción vacía y las cuentas aprobadas
  como opciones (`value` = id, texto = nombre de usuario). Botón «Registrar wallet» debajo.
- La ficha de resultado sigue mostrando Dueño / Identificador / Clave pública / Saldo.

### Tablero del usuario (`src/web/user.py`, `tablero.html`, `mi_historial.html`, `perfil.html`)

- `_wallets_de_la_sesion()` devuelve las wallets de `g.user`; `_wallet_de_la_sesion()` devuelve
  la elegida en `session["wallet_elegida"]` si pertenece a la cuenta y, si no, la principal.
  Sin wallets: 403 (estado imposible, igual que hoy).
- Ruta nueva `POST /mi-wallet` (`usuario.elegir_wallet`): valida que la wallet sea de la
  sesión, guarda la elección y redirige a `volver` si es una ruta interna, o al tablero.
- El tablero muestra, cuando la cuenta tiene más de una wallet, un selector «Tus wallets» con
  cada wallet, su código corto y su saldo; el resto de la página (saldo, envío, historial,
  contactos, estadísticas) opera sobre la elegida.
- `perfil` lista las wallets de la cuenta en lugar de `wallet_id`.
- `_wallet_del_destinatario` resuelve el nombre de usuario a su **wallet principal**.
- `_contactos_con_movimientos` compara contra la wallet principal de cada contacto.

### Textos (tuteo, con su clave en `traducciones.py`)

- «Déjala sin dueño», «¿A quién se la asignas?», «Elige la cuenta que va a usar esta wallet.»
- «Wallet registrada a nombre de {nombre}.», «Wallet registrada sin dueño.»
- «Esa cuenta no puede ser dueña de una wallet.», «No hay cuentas aprobadas todavía.»
- «Tus wallets», «Elegir», «Wallet elegida.»
Todas necesitan su entrada en inglés en `src/web/traducciones.py` (test_idioma).

## 6. Requerimientos

- **REQ-40 — Registro con dueño.** Al registrar una wallet el administrador elige la cuenta
  dueña o la deja sin dueño. _Criterio_: se elige una cuenta aprobada y la wallet queda con
  `owner_id`; con la opción vacía queda `owner_id NULL`; elegir una cuenta no aprobada, al
  administrador o un identificador inexistente se rechaza sin crear la wallet.
- **REQ-41 — Varias wallets por cuenta.** Una cuenta común aprobada puede tener varias wallets
  y operar con la que elija. _Criterio_: tres wallets asignadas a la misma cuenta aparecen en
  su selector; cambiar la elegida cambia saldo e historial; el envío sale de la elegida; una
  wallet de otra cuenta no se puede elegir.

Los REQ-33, 34, 35 y 39 se conservan en su criterio; cambia sólo cómo se resuelve la wallet de
la sesión (la elegida en lugar de `users.wallet_id`).

## 7. Pruebas

- `test_req_15_esquema`: el conjunto de tablas no cambia; sí las columnas: `wallets.owner_id`
  existe, `users.wallet_id` no.
- `test_req_30_usuarios`, `test_req_30_semilla`, `test_req_33_aprobacion`: la aprobación liga la
  wallet como dueña; la semilla deja las cinco wallets con sus cuentas.
- `test_nombres_por_wallet`: una wallet sin dueño no aparece; con dueño sí.
- `test_req_34_envio`, `test_req_35_alcance`, `test_req_39_verificacion`: la wallet de la sesión
  es la elegida.
- Nuevos: `test_req_40_registro_con_dueno.py`, `test_req_41_varias_wallets.py`.
- `tests/test_explicacion.py`: `REQUERIMIENTOS = range(1, 42)`.

## 8. Operación

El proyecto no tiene migraciones: el esquema nuevo obliga a recrear el volumen y volver a
sembrar (`docker compose down -v`, `docker compose up -d --wait`, `python -m src.bootstrap`).

## 9. Lo que queda fuera

- Reasignar el dueño de una wallet existente.
- Que el dueño sea una regla criptográfica: las llaves siguen en el servidor y el administrador
  puede firmar por cualquier wallet (límite ya declarado en el diseño de usuarios).
- Varias wallets para el administrador.
