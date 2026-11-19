# Plan: wallet con dueño y varias wallets por cuenta

**Diseño**: `docs/superpowers/specs/2026-11-19-wallet-con-dueno-design.md`
**Rama**: `wallet-con-dueno` (worktree `.agents/worktrees/wallet-con-dueno`).

## Tareas

1. **Esquema y cuentas.** `wallets.owner_id` con FK a `users` e índice; quitar de `users` la
   columna `wallet_id`, su `UNIQUE`, su FK y su CHECK. Modelo `Usuario` sin `wallet_id`. Puerto
   y adaptador de cuentas con `aprobar(id)`, `list_aprobados`, `wallets_de`,
   `wallet_principal`, `asignar_wallet` y `nombres_por_wallet` por `owner_id`. Servicio con
   `registrar_wallet(dueno_id)` y `DuenoInvalido`, y `aprobar` que liga la wallet nueva. Semilla
   idempotente que asigna las wallets de demostración.
2. **Presentación.** Registro con `select` de dueño y resultado con el nombre. Sesión del común
   con wallet elegida (`POST /mi-wallet`), selector «Tus wallets» en el tablero, perfil con la
   lista, estadísticas y ayudante sobre la principal cuando corresponda. Textos en tuteo con su
   entrada en inglés.
3. **Pruebas.** Actualizar las que usan `users.wallet_id`; agregar REQ-46 (registro con dueño) y
   REQ-47 (varias wallets); `(*range(1, 40), 46, 47)` en `test_explicacion`.

## Verificación

```bash
cd .agents/worktrees/wallet-con-dueno
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest tests/unit -q
# después de recrear el volumen con el esquema nuevo:
docker compose down -v && docker compose up -d --wait
.venv/bin/python -m src.bootstrap
.venv/bin/python -m pytest tests -q
```

Y en el navegador: admin → Wallets → registrar con dueño y sin dueño; entrar como la cuenta
dueña, cambiar de wallet y enviar desde la elegida.
