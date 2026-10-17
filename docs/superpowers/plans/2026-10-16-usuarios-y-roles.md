# Usuarios y roles — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar al prototipo un sistema de usuarios con dos roles —usuario común y administrador—, alta moderada con aprobación, sesión y pantallas separadas por rol, sin cambiar el comportamiento verificado del ledger.

**Architecture:** Las cuentas son un contexto aparte del ledger: un paquete nuevo `src/accounts/` (modelo, credenciales, puertos, persistencia y servicio) que el dominio no conoce. La autorización vive en la presentación, en puertas por ruta; las reglas del ledger siguen en el dominio. La única operación nueva del dominio es **acreditar saldo en un bloque propio**, que emite desde el constituyente sin pasar por la regla de saldo. La aprobación corre en una sola transacción de base: wallet, bloque de bienvenida y estado del usuario, o nada.

**Tech Stack:** Python 3.11, Flask, psycopg 3, PostgreSQL 16, `hashlib.scrypt` y la cookie firmada de Flask. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-10-16-usuarios-y-roles-design.md`

## Global Constraints

- Python 3.11 o superior; sin dependencias nuevas: `hashlib.scrypt` y la sesión de Flask vienen de la biblioteca estándar y del framework ya instalado.
- Español en documentación, docstrings y comentarios, con la regla del comentario: se queda el que explica el porqué. Sin emojis ni símbolos decorativos.
- Cada requerimiento nuevo (REQ-30 a REQ-39) tiene una prueba llamada `test_req_NN_*` con el criterio de aceptación en el docstring.
- La presentación no ejecuta reglas de negocio ni SQL (REQ-29): no importa `psycopg` ni `src.persistence` desde `src/web/app.py`.
- Las 130 pruebas que existen siguen pasando. Adaptaciones mecánicas admitidas: el conjunto de tablas esperadas suma `users`, y la limpieza de las pruebas borra usuarios antes que wallets. **Ninguna aserción de comportamiento se afloja.**
- El esquema se aplica creando el volumen; un volumen viejo falla con mensaje claro y la salida es recrearlo.
- Los montos son `Decimal`, nunca `float`. Los identificadores son `UUID` generados por la aplicación.
- `ruff check .` limpio y `env -u DATABASE_URL .venv/bin/pytest tests/unit -q` verde en cada tarea.

## Review Focus

Estas son las formas de fallar que el diseño implica y que ninguna prueba de tarea cubre por sí sola. Cada una tiene su prueba en la tarea que la posee.

1. **Un usuario pendiente o rechazado que intenta ingresar no puede distinguirse de uno inexistente** por el mensaje: el ingreso dice «esperando aprobación» o «rechazada» sólo a quien acierta la contraseña. Prueba en Task 5.
2. **El envío de un usuario común ignora un emisor inyectado en el formulario** y nunca escribe una transacción desde la wallet ajena. Prueba en Task 7.
3. **Aprobar dos veces al mismo usuario no crea dos wallets** ni dos créditos: la segunda aprobación falla sin escribir nada. Prueba en Task 5.
4. **La aprobación no arrastra el pool**: si hay transacciones pendientes, el bloque de bienvenida no las incluye. Prueba en Task 4.
5. **El nombre de usuario no distingue mayúsculas**: `Ana` y `ana` son el mismo usuario, y el ingreso funciona con cualquiera de las dos escrituras. Prueba en Task 2 y Task 5.

---

### Task 1: La tabla `users` y la configuración de la sesión

**Files:**

- Modify: `db/init.sql`, `.env.example`, `tests/integration/test_req_15_esquema.py`, `tests/integration/conftest.py`, `src/persistence/factory.py`
- Test: `tests/integration/test_req_15_esquema.py`

**Interfaces:**

- Produces: la tabla `users` con las columnas del diseño; `factory.session_secret() -> bytes`; `factory.admin_password() -> str`. Ambas leen del entorno o de `.env` y fallan con un mensaje que nombra la variable y dice qué hacer.

- [ ] **Step 1: Escribir la prueba del esquema**

```python
def test_req_30_el_esquema_tiene_la_tabla_de_usuarios(conexion):
    """REQ-30: la tabla `users` existe con sus restricciones."""
    columnas = columnas_de(conexion, "users")
    assert set(columnas) == {"id", "username", "password_hash", "role", "estado",
                             "motivo_rechazo", "wallet_id", "creado_en", "aprobado_en"}
    assert indices_y_restricciones(conexion, "users") >= {"users_username_key", "users_wallet_id_key",
                                                          "users_role_check", "users_estado_check"}
```

La prueba de las tablas públicas (`test_req_15...`) suma `users` al conjunto esperado.

- [ ] **Step 2: Correr y ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_15_esquema.py -v` — Expected: FAIL, la tabla no existe.
- [ ] **Step 3: Agregar la tabla a `db/init.sql`** con las columnas del diseño y dos `CHECK` más: `estado <> 'rechazado' OR motivo_rechazo IS NOT NULL`, y `(estado = 'aprobado') = (wallet_id IS NOT NULL)` —así pendiente y rechazado quedan sin wallet, y sólo el aprobado la tiene—.
- [ ] **Step 4: Cambiar el orden de la limpieza** en `tests/integration/conftest.py`: `DELETE FROM users` antes de wallets.
- [ ] **Step 5: Las dos funciones de configuración** — prueba en `tests/unit/test_req_37_sesion.py` de que sin la variable fallan con el mensaje y de que con ella devuelven el valor; después implementarlas en `factory.py` reusando `_env_value`.
- [ ] **Step 6: Verificar y commitear** — suites completas; `git commit -m "feat: la tabla de usuarios y la configuracion de la sesion"`.

---

### Task 2: Credenciales (REQ-36)

**Files:**

- Create: `src/accounts/__init__.py`, `src/accounts/credentials.py`
- Test: `tests/unit/test_req_36_credenciales.py`

**Interfaces:**

- Produces: `normalizar_usuario(texto: str) -> str` (recorta y pasa a minúsculas); `validar_usuario(texto: str) -> str | None` (None válido, o el motivo); `validar_contrasena(texto: str) -> str | None`; `hashear_contrasena(texto: str) -> str` (formato `scrypt$n$r$p$sal_b64$hash_b64`); `verificar_contrasena(texto: str, guardado: str) -> bool`.
- También: `PATRON_DE_USUARIO = r"[a-z0-9_.-]{3,20}"`, el único lugar donde vive el conjunto de caracteres permitido; la validación y los formularios lo usan desde ahí.

- [ ] **Step 1: Las pruebas**

```python
def test_req_36_dos_usuarios_con_la_misma_contrasena_tienen_hashes_distintos():
    assert hashear_contrasena("secreta1") != hashear_contrasena("secreta1")

def test_req_36_el_hash_no_contiene_la_contrasena():
    assert "secreta1" not in hashear_contrasena("secreta1")

def test_req_36_verifica_la_correcta_y_rechaza_la_equivocada():
    guardado = hashear_contrasena("secreta1")
    assert verificar_contrasena("secreta1", guardado) is True
    assert verificar_contrasena("secreta2", guardado) is False

def test_req_30_el_usuario_se_normaliza_y_se_valida():
    assert normalizar_usuario("  Ana ") == "ana"
    assert validar_usuario("ana") is None
    assert validar_usuario("a") is not None      # demasiado corto
    assert validar_usuario("ana perez") is not None  # espacios


def test_req_30_el_patron_y_la_validacion_dicen_lo_mismo():
    """REQ-30: el patrón de la interfaz acepta exactamente lo que acepta la validación."""
    for nombre in ("ana", "ana.perez", "ana_perez-2", "a1b"):
        assert re.fullmatch(PATRON_DE_USUARIO, nombre) and validar_usuario(nombre) is None
    for nombre in ("Ana", "ana perez", "a", "ana@x", "ñ"):
        assert not (re.fullmatch(PATRON_DE_USUARIO, nombre) and validar_usuario(nombre) is None)
```

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests/unit/test_req_36_credenciales.py -q` — Expected: FAIL, `ModuleNotFoundError`.
- [ ] **Step 3: Implementar** con `hashlib.scrypt(n=2**14, r=8, p=1)`, sal de 16 bytes de `secrets.token_bytes`, y `hmac.compare_digest` para comparar. `verificar_contrasena` devuelve `False` ante un formato inválido, sin lanzar.
- [ ] **Step 4: Verde y commit** — `git commit -m "feat: credenciales con scrypt y sal por usuario"`.

---

### Task 3: El modelo y el repositorio de usuarios

**Files:**

- Create: `src/accounts/model.py`, `src/accounts/ports.py`, `src/accounts/postgres.py`
- Modify: `src/persistence/unit_of_work.py` (exponer `usuarios` y `connection`)
- Test: `tests/integration/test_req_30_usuarios.py`

**Interfaces:**

- Produces: `Usuario` (dataclass congelado con `id, username, password_hash, role, estado, motivo_rechazo, wallet_id, creado_en, aprobado_en`); las constantes `ADMINISTRADOR, USUARIO, PENDIENTE, APROBADO, RECHAZADO`; `RepositorioDeUsuarios` (Protocol) con `add_pendiente(usuario)`, `get_by_username(username)`, `get(id)`, `list_pendientes()`, `aprobar(id, wallet_id)`, `rechazar(id, motivo)`, `count()`; `PostgresAccountsRepository(conexion)`; `PostgresUnitOfWork.usuarios` y `.connection`.
- Consumes: de Task 2, `normalizar_usuario`.

- [ ] **Step 1: Las pruebas de integración**

```python
def test_req_30_el_registro_deja_la_fila_pendiente_sin_wallet(conexion):
    repo = PostgresAccountsRepository(conexion)
    repo.add_pendiente(usuario_nuevo("ana"))
    fila = repo.get_by_username("ana")
    assert fila.estado == PENDIENTE and fila.wallet_id is None

def test_req_30_el_nombre_es_unico_sin_distinguir_mayusculas(conexion):
    repo = PostgresAccountsRepository(conexion)
    repo.add_pendiente(usuario_nuevo("ana"))
    with pytest.raises(UsuarioDuplicado):
        repo.add_pendiente(usuario_nuevo("ANA"))

def test_req_31_aprobar_liga_la_wallet_y_cambia_el_estado(conexion):
    ...

def test_req_31_rechazar_guarda_el_motivo_y_el_esquema_no_lo_admite_vacio(conexion):
    ...
```

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_30_usuarios.py -q`.
- [ ] **Step 3: Implementar** `model.py`, `ports.py` y `postgres.py`; en el repositorio, `get_by_username` compara sobre el nombre ya normalizado y traduce la violación de unicidad (`psycopg.errors.UniqueViolation` sobre `users_username_key`) a `UsuarioDuplicado`, que se define en `model.py`.
- [ ] **Step 4: Exponer en la unidad de trabajo** `self.usuarios = PostgresAccountsRepository(connection)` y una propiedad `connection`.
- [ ] **Step 5: Verde y commit** — `git commit -m "feat: el modelo y el repositorio de usuarios"`.

---

### Task 4: El dominio acredita el saldo de bienvenida

**Files:**

- Create: `src/emision.py`
- Modify: `src/domain/blockchain.py`, `src/bootstrap.py`
- Test: `tests/unit/test_req_33_emision.py`, `tests/integration/test_req_33_emision.py`

**Interfaces:**

- Produces: `src/emision.py` con `CONSTITUYENTE_ID`, `CONSTITUYENTE_SEED` y `SALDO_DE_BIENVENIDA = Decimal("1000.00000000")`, importados también por `bootstrap.py` (que deja de definirlos); `Blockchain.acreditar(*, emisor_id: UUID, destino_id: UUID, monto: Decimal) -> Block`, que firma con la llave del emisor, crea la transacción **confirmada en un bloque propio** (índice siguiente, `previous_hash` del último) y **no arrastra el pool**.
- Consumes: `create_wallet`/`sign_payload` del dominio, `Block`, los tres repositorios del ledger.

- [ ] **Step 1: Las pruebas**

```python
def test_req_33_acreditar_sube_el_saldo_del_destino_y_baja_el_del_emisor(ledger, ...):
    bloque = ledger.acreditar(emisor_id=CONSTITUYENTE_ID, destino_id=destino.id, monto=SALDO_DE_BIENVENIDA)
    assert ledger.available_balance(destino.id) == SALDO_DE_BIENVENIDA
    assert ledger.verify_chain().valid is True
    assert len(ledger.transactions.of_block(bloque.id)) == 1

def test_req_33_la_emision_no_arrastra_las_pendientes(ledger_con_pendientes):
    bloque = ledger_con_pendientes.acreditar(...)
    assert len(ledger_con_pendientes.transactions.of_block(bloque.id)) == 1
```

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests -k emision -q`.
- [ ] **Step 3: Implementar `acreditar`** en `blockchain.py` con el mismo camino de firma que `create_transaction` pero **sin** la comprobación de saldo, y con un bloque nuevo que contiene sólo esa transacción. Mover los dos constantes a `src/emision.py` y ajustar los imports de `bootstrap.py`.
- [ ] **Step 4: Verde y commit** — `git commit -m "feat: el dominio emite saldo de bienvenida en un bloque propio"`.

---

### Task 5: El servicio de cuentas (REQ-30, REQ-31, REQ-32, REQ-33)

**Files:**

- Create: `src/accounts/service.py`
- Modify: `src/persistence/factory.py` (la transacción que compone ledger y cuentas)
- Test: `tests/integration/test_req_30_registro.py`, `tests/integration/test_req_32_ingreso.py`, `tests/integration/test_req_33_aprobacion.py`

**Interfaces:**

- Produces: `Cuentas` con `registrar(username, contrasena) -> Usuario`, `autenticar(username, contrasena) -> Usuario`, `pendientes() -> Sequence[Usuario]`, `aprobar(id) -> Usuario`, `rechazar(id, motivo) -> Usuario`; excepciones `UsuarioDuplicado`, `CredencialesInvalidas`, `NoAprobado(estado: str, motivo: str | None)`, `UsuarioInexistente`; `factory.transaction()` que rinde un objeto con `.ledger`, `.usuarios` y `.commit()` sobre **una sola conexión**.
- Consumes: Task 2 (credenciales), Task 3 (repositorio), Task 4 (`acreditar`).

- [ ] **Step 1: Las pruebas**

```python
def test_req_30_registrar_deja_pendiente_sin_wallet(cuentas): ...
def test_req_30_no_se_puede_registrar_dos_veces_el_mismo_nombre(cuentas): ...
def test_req_32_el_pendiente_no_ingresa_y_se_le_dice_su_estado(cuentas): ...
def test_req_32_el_rechazado_ingresa_con_el_motivo(cuentas): ...
def test_req_32_con_contrasena_equivocada_el_mensaje_no_distingue_si_existe(cuentas): ...
def test_req_33_aprobar_crea_wallet_saldo_y_un_bloque(cuentas, ledger): ...
def test_req_33_aprobar_dos_veces_no_crea_dos_wallets(cuentas): ...
def test_req_33_si_falla_el_credito_no_queda_la_wallet(cuentas, monkeypatch): ...
```

La última inyecta un fallo en el crédito y exige que no exista ni la wallet ni el cambio de estado: es la atomicidad de REQ-33.

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_3{0,2,3}_*.py -q`.
- [ ] **Step 3: Implementar `Cuentas`**; `aprobar` abre `factory.transaction()`, crea la wallet con `ledger.register_wallet()`, llama a `ledger.acreditar(...)` con el constituyente, actualiza la fila del usuario con `usuarios.aprobar(...)` y hace `commit()`. Un usuario que no está pendiente hace fallar la operación antes de escribir.
- [ ] **Step 4: Verde y commit** — `git commit -m "feat: registro, ingreso y aprobacion de usuarios"`.

---

### Task 6: La sesión y las puertas (REQ-37, REQ-38)

**Files:**

- Create: `src/web/auth.py`
- Modify: `src/web/app.py` (`create_app(chain_factory, cuentas_factory)`, decorar las rutas de hoy)
- Test: `tests/integration/test_req_37_sesion.py`, `tests/integration/test_req_38_autorizacion.py`; adaptar `tests/integration/conftest.py` con un cliente que ya ingresó como administrador.

**Interfaces:**

- Produces: `crear_app_de_prueba(...)`; decoradores `requiere_sesion` y `requiere_administrador`; rutas `GET/POST /ingresar`, `POST /salir`, `GET/POST /registrarme`; `g.user` (el `Usuario` de la sesión, recargado por petición).

- [ ] **Step 1: Las pruebas**

```python
def test_req_37_sin_sesion_las_rutas_de_trabajo_redirigen(cliente): ...
def test_req_37_ingresar_abre_sesion_y_salir_la_cierra(cliente): ...
def test_req_38_el_usuario_comun_no_puede_agrupar_un_bloque(cliente_comun): ...  # 403
def test_req_38_el_usuario_comun_no_puede_aprobar_usuarios(cliente_comun): ...   # 403
def test_req_32_el_registro_muestra_la_pantalla_de_pendiente(cliente): ...
def test_req_30_el_formulario_limita_el_usuario_a_los_caracteres_permitidos(cliente): ... # pattern, maxlength y la ayuda visible, tomados de PATRON_DE_USUARIO
```

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_3{7,8}_*.py -q`.
- [ ] **Step 3: Implementar** la sesión (guardar el `id`, recargar el usuario por petición, `SESSION_SECRET` en `app.secret_key`, cookie `HttpOnly`, `SameSite=Lax`, no permanente) y las puertas. Adaptar las pruebas de rutas existentes para ingresar como administrador.
- [ ] **Step 4: Verde y commit** — `git commit -m "feat: sesion con cookie firmada y puertas por rol"`.

---

### Task 7: El tablero del usuario común (REQ-34, REQ-35, REQ-39)

**Files:**

- Create: `src/web/user.py`, `src/web/templates/tablero.html`
- Modify: `src/web/app.py`
- Test: `tests/integration/test_req_34_envio.py`, `tests/integration/test_req_35_alcance.py`, `tests/integration/test_req_39_verificacion.py`

**Interfaces:**

- Produce: `GET /mi-tablero`, `POST /mi-envio`, `GET /mi-historial`, `GET /mi-verificacion`.

- [ ] **Step 1: Las pruebas**

```python
def test_req_34_el_emisor_sale_de_la_sesion_y_no_del_formulario(cliente_comun, ...): ...
def test_req_34_el_destinatario_puede_ser_usuario_o_identificador_de_wallet(cliente_comun, ...): ...
def test_req_35_el_usuario_comun_no_ve_el_historial_de_otro(cliente_comun, ...): ...  # 403
def test_req_39_mi_verificacion_lista_solo_sus_transacciones(cliente_comun, ...): ...
def test_req_39_con_la_cadena_alterada_mi_verificacion_dice_que_no_puede_verificar(cliente_comun, ...): ...
```

- [ ] **Step 2: Ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_3{4,5,9}_*.py -q`.
- [ ] **Step 3: Implementar** las cuatro rutas. El emisor sale de `g.user.wallet_id`; el destinatario se resuelve por nombre de usuario y, si no existe, por identificador de wallet. `mi-verificacion` corre `verify_chain()` y filtra por la wallet de la sesión.
- [ ] **Step 4: Verde y commit** — `git commit -m "feat: el tablero del usuario comun con envio e historial propio"`.

---

### Task 8: La cola de pendientes del administrador (REQ-31)

**Files:**

- Create: `src/web/admin.py`, `src/web/templates/pendientes.html`
- Modify: `src/web/app.py`
- Test: `tests/integration/test_req_31_cola.py`

**Interfaces:**

- Produce: `GET /admin/pendientes`, `POST /admin/pendientes/<id>/aprobar`, `POST /admin/pendientes/<id>/rechazar`.

- [ ] **Step 1: Las pruebas**

```python
def test_req_31_el_administrador_ve_los_pendientes(cliente_admin, ...): ...
def test_req_31_aprobar_desde_la_cola_crea_la_wallet_y_saca_al_usuario_de_la_lista(cliente_admin, ...): ...
def test_req_31_rechazar_desde_la_cola_pide_motivo_y_lo_guarda(cliente_admin, ...): ...
def test_req_38_el_usuario_comun_no_entra_a_la_cola(cliente_comun): ...  # 403
```

- [ ] **Step 2: Correr y ver el rojo** — Run: `.venv/bin/pytest tests/integration/test_req_31_cola.py -q` — Expected: FAIL, las rutas no existen.
- [ ] **Step 3: Implementar las tres rutas** en `src/web/admin.py` con `requiere_administrador`; aprobar llama a `cuentas.aprobar`, y rechazar exige un motivo no vacío antes de llamar a `cuentas.rechazar`.
- [ ] **Step 4: Correr y ver el verde** — Run: `.venv/bin/pytest tests/integration/test_req_31_cola.py -q` — Expected: PASS.
- [ ] **Step 5: Suite completa y commit** — Run: `.venv/bin/pytest tests -q` y `.venv/bin/ruff check .`; `git commit -m "feat: la cola de pendientes del administrador"`.

---

### Task 9: La semilla, el README y el recorrido de demostración

**Files:**

- Modify: `src/bootstrap.py`, `README.md`
- Test: `tests/integration/test_req_30_semilla.py`

**Interfaces:**

- Produce: el arranque crea el administrador (con `ADMIN_PASSWORD`) y cinco usuarios de demostración aprobados, ligados a las cinco wallets; el README documenta las cuentas de demostración, el recorrido y el límite de autoría declarado.

- [ ] **Step 1: Las pruebas**

```python
def test_req_30_la_semilla_crea_el_administrador_y_cinco_usuarios(base_limpia): ...
def test_req_30_la_semilla_es_idempotente(base_limpia): ...
def test_req_33_el_recorrido_de_demostracion_completo(base_limpia, cliente): ...
```

El tercero es el recorrido del diseño: el administrador aprueba a una persona, esa persona ingresa, ve su saldo, manda un envío, lo ve confirmado y verifica su historial.

- [ ] **Step 2: Ver el rojo**, **Step 3: implementar** (incluido el mensaje de arranque cuando el volumen es viejo), **Step 4: verde**.
- [ ] **Step 5: README** — una sección: cuentas de demostración, recorrido, y los límites declarados (autoría del administrador, CSRF e intentos, tal como dice el diseño).
- [ ] **Step 6: Verificación final y commit** — suite completa, `ruff`, unitarias sin base, la herramienta de sabotaje sigue corriendo; `git commit -m "feat: semilla con administrador y usuarios de demostracion"`.
