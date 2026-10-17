"""El panel de wallets del administrador, con el saldo disponible de cada una.

Es la única fuente del panel que comparten la portada y el resto de las páginas del
administrador. La lista y los saldos salen de la fachada del ledger, que es la
misma cuenta que usa el envío para decidir (REQ-05): la presentación no consulta la
base ni recalcula el saldo (REQ-29).

El usuario común no recibe este panel a propósito: la matriz de permisos le niega
ver las wallets de otros (REQ-35), así que su tablero y su historial no lo piden.
"""
from __future__ import annotations

from src.domain.blockchain import Blockchain


def datos_del_panel(chain: Blockchain) -> dict[str, object]:
    """Las wallets y su saldo disponible, listos para `base.html`.

    Se devuelven juntos y no por separado para que ninguna página pueda pintar la
    lista sin los saldos: el panel del administrador siempre muestra las dos cosas.
    """
    wallets = chain.wallets.list()
    return {
        "wallets_del_panel": wallets,
        "saldos_de_las_wallets": {
            wallet.id: chain.available_balance(wallet.id) for wallet in wallets
        },
    }
