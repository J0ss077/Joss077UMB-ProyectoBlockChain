"""Arranque explícito del ledger: génesis, datos de demostración y cuentas (REQ-14, REQ-05).

El génesis es un dato calculado, no DDL, así que no vive en `db/init.sql`: lo crea
la aplicación con este punto de entrada y de forma idempotente, para que correrlo
dos veces no duplique el eslabón cero (decisión 7). Sobre esa base siembra la
demostración del caso del eje —una wallet de fondo que recibe aportes de los
asociados y les gira retiros—, con montos elegidos para que ningún saldo quede
negativo (REQ-05), que es el defecto que arrastraban los datos del repositorio
anterior (decisión 9).

Después siembra las cuentas (decisión 8): el administrador aprobado y sin wallet,
y un usuario de demostración por cada wallet de la convención, todos aprobados. La
semilla de las cuentas también es idempotente: correr el arranque dos veces no
duplica ninguna.

Uso: `python -m src.bootstrap`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
from cryptography.hazmat.primitives.asymmetric import ec

from src.accounts.credentials import hashear_contrasena
from src.accounts.model import ADMINISTRADOR, APROBADO, USUARIO, Usuario
from src.domain.block import Block
from src.domain.blockchain import Blockchain, ensure_genesis
from src.domain.transaction import Transaction, TransactionStatus
from src.domain.wallet import CURVE, Wallet, encrypt_private_key, public_key_hex, sign_payload
from src.emision import CONSTITUYENTE_ID, CONSTITUYENTE_SEED
from src.persistence.factory import admin_password, ledger, transaction

# Semilla del par de llaves del fondo: fijarla hace que su clave pública sea la
# misma en cada corrida. Sin eso, el fondo quedaría con una pública distinta cada
# vez y la convención de la decisión 8 —reconocerlo por su pública— solo valdría
# dentro de una misma corrida.
FONDO_SEED = b"blockchain-transaccional/fondo"
# Identificador fijo del fondo, por la misma razón que la semilla: es un dato de la
# convención y no un valor que se pueda elegir al azar en cada arranque.
FONDO_ID = uuid5(NAMESPACE_URL, "blockchain-transaccional/fondo")

# Montos de la demostración. El constituyente dota al fondo con el capital de
# constitución; el fondo entrega de ahí el capital de asociación a cada asociado,
# con el que cada uno hace su primer aporte; y el fondo gira retiros por menos de lo
# que cobró en aportes, así que retiene fondos propios. El constituyente es la
# puerta por la que el capital entra al ledger —el modelo del eje no tiene emisión—
# y por eso es la única wallet de la demostración que termina con saldo disponible
# negativo; el fondo y los asociados quedan todos en positivo (REQ-05).
CAPITAL_CONSTITUCION = Decimal("3000.00000000")
CAPITAL_ASOCIACION = Decimal("1000.00000000")
APORTE = Decimal("700.00000000")
RETIRO = Decimal("600.00000000")

ASOCIADOS = 3

# Cuentas de la semilla. El administrador es la cuenta fija `admin` y su
# contraseña sale del entorno (decisión 4): no se escribe acá porque es un secreto
# y vive en `.env`. Los cinco usuarios de demostración comparten la contraseña
# documentada en el README; son cuentas para mostrar el producto, no de personas.
USERNAME_DEL_ADMINISTRADOR = "admin"
CONTRASENA_DE_DEMOSTRACION = "demostracion"

# Un usuario de demostración por cada wallet sembrada, en el orden en que la
# semilla las crea: el constituyente, el fondo y los tres asociados. El nombre es
# el del actor de la convención, así la cuenta y la wallet que maneja se reconocen
# sin una tabla de equivalencias.
NOMBRES_DE_DEMOSTRACION = (
    "constituyente",
    "fondo",
    "asociado1",
    "asociado2",
    "asociado3",
)

# Mensaje del arranque sobre un volumen anterior a las cuentas. El proyecto no
# tiene migraciones (§6): la tabla `users` llega con `db/init.sql` al crear el
# volumen, así que la única salida es recrearlo. El texto nombra los comandos
# exactos porque el error del motor no le dice a la persona qué hacer.
MENSAJE_DE_VOLUMEN_VIEJO = (
    "La base no tiene la tabla `users`: el volumen es anterior a las cuentas y "
    "este proyecto no tiene migraciones. Recrea el volumen y vuelve a sembrar: "
    "`docker compose down -v`, `docker compose up -d` y `python -m src.bootstrap` "
    "(con Podman, los mismos comandos con `podman compose`)."
)


def _llave(semilla: bytes) -> ec.EllipticCurvePrivateKey:
    """Deriva un par de llaves de una semilla fija (decisión 8).

    El escalar de la curva se toma del hash de la semilla, en vez de dejar que la
    librería lo genere al azar, porque las wallets de la convención se reconocen por
    su clave pública y esa no puede cambiar entre corridas. `CURVE` valida el rango
    del escalar: un hash fuera del orden del grupo no se puede usar como privada.
    """
    escalar = int.from_bytes(sha256(semilla).digest(), "big")
    return ec.derive_private_key(escalar, CURVE())


# Clave pública del fondo de la demostración. La distinción aporte/retiro **no tiene
# columna** en el modelo relacional del eje (decisión 8): un aporte es una
# transacción de un asociado hacia esta wallet y un retiro es una transacción de esta
# wallet hacia un asociado, así que el sentido del movimiento respecto de ella es lo
# único que los separa. Se deriva de `FONDO_SEED`, igual que la wallet que se
# registra, para que la convención y el dato no puedan divergir.
FONDO = public_key_hex(_llave(FONDO_SEED))


def _wallet(wallet_id: UUID, semilla: bytes, master_key: bytes) -> Wallet:
    """Arma una wallet de la convención: identificador y pública fijos, privada cifrada."""
    privada = _llave(semilla)
    return Wallet(
        id=wallet_id,
        public_key=public_key_hex(privada),
        private_key_encrypted=encrypt_private_key(privada, master_key),
        created_at=datetime.now(UTC),
    )


def wallet_del_fondo(master_key: bytes) -> Wallet:
    """Arma la wallet del fondo, que se reconoce por su pública constante `FONDO`."""
    return _wallet(FONDO_ID, FONDO_SEED, master_key)


def wallet_del_constituyente(master_key: bytes) -> Wallet:
    """Arma la wallet del constituyente, la puerta por la que el capital entra al ledger."""
    return _wallet(CONSTITUYENTE_ID, CONSTITUYENTE_SEED, master_key)


def run(chain: Blockchain) -> Block | None:
    """Siembra la demostración sobre una base vacía de wallets y devuelve su bloque.

    Idempotente: con wallets ya registradas no escribe nada y devuelve el bloque
    nulo, porque el arranque se puede repetir. El bloque nulo es también el flujo
    alterno del CU-03: sin aportes en el pool no hay nada que agrupar.

    El ciclo del eje se reproduce en tres tiempos, y cada uno se confirma antes del
    siguiente porque el saldo disponible de REQ-05 solo suma lo confirmado a favor:
    sin ese orden, la validación de la pata siguiente vería saldo cero.

    Primero, el constituyente emite el capital de constitución a favor del fondo: es
    la única entrada de valor externo, porque el modelo del eje no tiene emisión.
    Segundo, el fondo gira el capital de asociación a los asociados y se confirma.
    Tercero, los asociados aportan con cargo a ese capital y sus aportes se
    confirman, que es lo que deja al fondo con fondos propios; después el fondo gira
    los retiros, que quedan en el pool como el ciclo que `POST /bloques` agruparía a
    continuación.
    """
    if chain.wallets.count() > 0:
        return None

    constituyente = chain.wallets.add(wallet_del_constituyente(chain._master_key))
    fondo = chain.wallets.add(wallet_del_fondo(chain._master_key))
    asociados = [chain.register_wallet() for _ in range(ASOCIADOS)]

    chain.transactions.add(
        _entrega_de_capital(chain, constituyente.id, fondo.id, CAPITAL_CONSTITUCION)
    )
    chain.group_pending()

    for asociado in asociados:
        chain.transactions.add(
            _entrega_de_capital(chain, fondo.id, asociado.id, CAPITAL_ASOCIACION)
        )
    chain.group_pending()

    for asociado in asociados:
        chain.create_transaction(sender_id=asociado.id, receiver_id=fondo.id, amount=APORTE)
    bloque = chain.group_pending()

    for asociado in asociados:
        chain.create_transaction(sender_id=fondo.id, receiver_id=asociado.id, amount=RETIRO)
    return bloque


def _entrega_de_capital(
    chain: Blockchain, emisor_id: UUID, receptor_id: UUID, monto: Decimal
) -> Transaction:
    """Arma una entrega de capital ya firmada por su emisor.

    Este camino escribe por el repositorio y no por `create_transaction` porque el
    capital se coloca y no se gira contra un saldo. Son dos filas de esa clase: la
    entrega del constituyente al fondo —la emisión fundacional— no podría pasar esa
    puerta, porque valida el saldo del emisor (REQ-05) y el modelo del eje no tiene
    emisión, así que el constituyente nace sin saldo; y la entrega del fondo a cada
    asociado usa el mismo camino por ser la misma clase de fila, capital de asociación
    colocado, aunque quepa en el saldo ya confirmado del fondo. Todas las demás filas
    de la demostración —los aportes y los retiros, los que se confirman y los tres que
    quedan pendientes en el pool— se mueven por el camino normal. Como consecuencia,
    el constituyente queda con saldo disponible negativo: es la única wallet de la
    demostración a la que se le permite, porque es la puerta por la que el capital
    entra al ledger.

    La firma sí es la real: se calcula con `sign_payload` sobre la misma forma
    canónica que usa el camino normal (`signing_payload`), de modo que toda fila de
    la base queda verificable contra la pública de su emisor (REQ-02). Firmar no es
    validar, así que saltarse la regla de saldo no exime de la firma.
    """
    emisor = chain.wallets.get(emisor_id)
    receptor = chain.wallets.get(receptor_id)
    transaction = Transaction(
        id=uuid4(),
        sender_id=emisor_id,
        receiver_id=receptor_id,
        amount=monto,
        status=TransactionStatus.PENDING,
        signature="",
        block_id=None,
        created_at=chain._clock(),
    )
    payload = transaction.signing_payload(emisor.public_key, receptor.public_key)
    transaction.signature = sign_payload(emisor, payload, chain._master_key)
    return transaction


def _cuenta_aprobada(
    username: str, contrasena: str, role: str, wallet_id: UUID | None
) -> Usuario:
    """Arma una fila ya aprobada: la semilla no pasa por el alta moderada.

    La fecha de alta y la de aprobación son el mismo instante porque la cuenta
    nace sembrada; el repositorio escribe la fila tal cual, sin inventar una
    pendiente que nadie va a aprobar.
    """
    ahora = datetime.now(UTC)
    return Usuario(
        id=uuid4(),
        username=username,
        password_hash=hashear_contrasena(contrasena),
        role=role,
        estado=APROBADO,
        motivo_rechazo=None,
        wallet_id=wallet_id,
        creado_en=ahora,
        aprobado_en=ahora,
    )


def _wallets_de_la_demostracion(chain: Blockchain) -> list[UUID]:
    """Las cinco wallets sembradas, en el orden de `NOMBRES_DE_DEMOSTRACION`.

    El fondo y el constituyente se reconocen por sus constantes; los asociados son
    los receptores de los capitales de asociación que el fondo les colocó. No se
    usa `wallets.list()` porque incluiría cualquier wallet que se registre después:
    la convención es una cuenta por cada wallet de la semilla, no por wallet viva.
    """
    fondo = chain.wallets.get_by_public_key(FONDO)
    if fondo is None:
        return []
    asociados = [
        fila.receiver_id
        for fila in chain.wallet_history(fondo.id)
        if fila.sender_id == fondo.id and fila.amount == CAPITAL_ASOCIACION
    ]
    return [CONSTITUYENTE_ID, fondo.id, *asociados]


def sembrar_usuarios() -> int:
    """Crea las cuentas que falten y devuelve cuántas escribió.

    Idempotente por nombre: se puede correr en cada arranque sin duplicar cuentas.
    El administrador y los de demostración se escriben ya aprobados por el
    repositorio, que es el único camino para un administrador —el servicio siempre
    registra rol `usuario`— y para el aprobado sin wallet que el CHECK admite solo
    para ese rol. El commit es único para las cuentas: o quedan todas las que
    faltaban o no queda ninguna.

    Las cuentas se leen por la conexión de la transacción y no por la del ledger
    porque el repositorio de usuarios necesita una conexión propia; las wallets
    ya están confirmadas por el arranque, así que esa transacción las ve.
    """
    creadas = 0
    with transaction() as actual:
        administrador = actual.usuarios.get_by_username(USERNAME_DEL_ADMINISTRADOR)
        if administrador is None:
            actual.usuarios.sembrar(
                _cuenta_aprobada(
                    USERNAME_DEL_ADMINISTRADOR,
                    admin_password(),
                    ADMINISTRADOR,
                    None,
                )
            )
            creadas += 1
        elif administrador.role != ADMINISTRADOR or administrador.estado != APROBADO:
            # El nombre por sí solo no dice que la cuenta sea el administrador: una
            # persona pudo registrarse como `admin` antes del primer arranque. La
            # semilla no la convierte ni la saltea en silencio; sin esto el sistema
            # quedaba sin administrador y nadie podía aprobar a nadie.
            raise SystemExit(_mensaje_de_admin_ocupado(administrador))

        wallets = _wallets_de_la_demostracion(actual.ledger)
        # Sin `strict`: si una wallet de la convención ya no está por una
        # alteración, el arranque no puede fallar por una cuenta de demostración
        # que ya existe; la prueba de la semilla es la que exige las cinco.
        for nombre, wallet_id in zip(NOMBRES_DE_DEMOSTRACION, wallets, strict=False):
            if actual.usuarios.get_by_username(nombre) is not None:
                continue
            actual.usuarios.sembrar(
                _cuenta_aprobada(
                    nombre, CONTRASENA_DE_DEMOSTRACION, USUARIO, wallet_id
                )
            )
            creadas += 1
        actual.commit()
    return creadas


def _mensaje_de_admin_ocupado(usuario: Usuario) -> str:
    """Qué hacer cuando `admin` ya existe y no es un administrador aprobado.

    El nombre lo pudo tomar una persona por el registro abierto antes del primer
    arranque. Convertir esa cuenta en administrador sería regalar el control del
    sistema a quien eligió el nombre, y saltearla dejaría el sistema sin nadie que
    apruebe; por eso el arranque se detiene y nombra las dos salidas.
    """
    return (
        f"El nombre `{USERNAME_DEL_ADMINISTRADOR}` ya está tomado por una cuenta con "
        f"rol `{usuario.role}` y estado `{usuario.estado}`, que no es un administrador "
        "aprobado: la semilla no la puede convertir. Recrea el volumen "
        "(`docker compose down -v`, `docker compose up -d`) y vuelve a sembrar, o "
        "borra esa cuenta de `users` y vuelve a correr el arranque."
    )


def main() -> None:
    """Asegura el génesis, siembra la demostración si hace falta e informa el estado."""
    with ledger() as chain:
        genesis = ensure_genesis(chain)
        bloque = run(chain)
        try:
            cuentas = sembrar_usuarios()
        except psycopg.errors.UndefinedTable as error:
            # Un volumen anterior a las cuentas no tiene la tabla y no hay
            # migraciones: se informa la salida en vez de mostrar el error del motor.
            raise SystemExit(MENSAJE_DE_VOLUMEN_VIEJO) from error
        estado = chain.ledger_state()
        accion = "sembrada ahora" if bloque is not None else "sin cambios, ya estaba sembrada"
        print(f"génesis listo: índice {genesis.block_index}, hash {genesis.hash}")
        print(
            f"demostración {accion}: {estado['wallets']} wallets, "
            f"{estado['blocks']} bloques, {estado['transactions']} transacciones"
        )
        if cuentas:
            print(
                f"cuentas: {cuentas} creadas ahora ({USERNAME_DEL_ADMINISTRADOR} y "
                f"{len(NOMBRES_DE_DEMOSTRACION)} usuarios de demostración)"
            )
        else:
            print("cuentas: sin cambios, ya estaban")


if __name__ == "__main__":
    main()
