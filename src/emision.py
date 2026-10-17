"""Identidad y monto de la emisión: la puerta por la que entra el capital (REQ-33).

Las constantes viven acá y no en `bootstrap.py` porque la semilla y la aprobación
de usuarios tienen que hablar del mismo emisor: si el identificador se definiera
en el arranque, el servicio de cuentas dependería de un script. El monto de
bienvenida acompaña a la identidad porque es el capital que esa misma puerta
emite en cada aprobación.
"""
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

# Semilla e identificador del constituyente, la wallet por la que el capital de
# constitución entra al ledger. Son fijos para que el arranque sea el mismo en
# cada corrida, igual que los del fondo: la wallet se reconoce por su clave
# pública, y esa no puede cambiar entre corridas.
CONSTITUYENTE_SEED = b"blockchain-transaccional/constituyente"
CONSTITUYENTE_ID: UUID = uuid5(NAMESPACE_URL, "blockchain-transaccional/constituyente")

# Saldo de bienvenida de cada usuario aprobado (decisión 3 del diseño de
# usuarios): sin saldo la persona entra y no puede hacer nada, y el constituyente
# es la única wallet a la que el diseño le permite quedar en negativo.
SALDO_DE_BIENVENIDA = Decimal("1000.00000000")
