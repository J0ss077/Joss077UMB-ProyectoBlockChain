"""Las estadísticas: cómo se mueve el dinero de una cuenta, en gráficas con filtros.

Dos rutas sobre la misma página:

- `GET /mis-estadisticas` es la del usuario común y sólo lee la wallet de la
  sesión (REQ-35): el identificador nunca llega de la petición.
- `GET /admin/estadisticas?usuario=<nombre>` es la del administrador, que elige
  en un selector a cuál usuario común mirar. Sin `usuario` la página sólo
  muestra el selector; un nombre que no es de un usuario común aprobado responde
  404.

El servidor arma los movimientos de la wallet —fecha, si entró o salió, estado,
monto y con quién— y los deja en la página como JSON; los filtros (período, tipo,
estado y persona) y las gráficas los resuelve `estadisticas.js` en el navegador,
así cambiar un filtro no recarga la página. El resumen que va pintado desde el
servidor es el de todo el historial, para que la página diga algo aunque el guion
no corra.

Las contrapartes salen con el mismo nombre que ya muestra el historial de la
persona; el saldo de bienvenida lleva su nombre y una wallet sin dueño se dice
«otra cuenta». Como el resto de la presentación (REQ-29), este módulo no consulta
la base: lee la fachada del ledger y el servicio de cuentas con las fábricas que
le pasa `create_app`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, abort, g, render_template, request

from src.accounts.model import ADMINISTRADOR
from src.accounts.service import Cuentas
from src.domain.blockchain import Blockchain
from src.domain.transaction import Transaction, TransactionStatus
from src.emision import CONSTITUYENTE_ID
from src.web.auth import requiere_administrador, requiere_usuario_comun
from src.web.proyeccion import proyectar
from src.web.user import _wallet_de_la_sesion

FabricaDeCadenas = Callable[[], AbstractContextManager[Blockchain]]
FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]

# Cómo se nombran en la página las contrapartes que no son una cuenta.
NOMBRE_DE_LA_BIENVENIDA = "Saldo de bienvenida"
NOMBRE_SIN_DUENO = "otra cuenta"

MENSAJE_USUARIO_SIN_ESTADISTICAS = "No hay un usuario con ese nombre."


@dataclass(frozen=True, slots=True)
class ResumenDeEstadisticas:
    """Lo que se pinta antes de los filtros: lo completado de todo el historial y
    cuántos movimientos hay, en cualquier estado."""

    recibido: Decimal
    enviado: Decimal
    movimientos: int

    @property
    def balance(self) -> Decimal:
        return self.recibido - self.enviado


def crear_blueprint_de_estadisticas(
    abrir_cadena: FabricaDeCadenas, abrir_cuentas: FabricaDeCuentas
) -> Blueprint:
    """Arma las dos rutas de estadísticas con las fábricas que recibe de `create_app`."""
    estadisticas = Blueprint("estadisticas", __name__)

    @estadisticas.get("/mis-estadisticas")
    @requiere_usuario_comun
    def mis_estadisticas() -> str:
        """Las estadísticas de la wallet de la sesión y de ninguna otra (REQ-35)."""
        wallet_id = _wallet_de_la_sesion()
        with abrir_cuentas() as cuentas:
            nombres = cuentas.nombres_por_wallet()
        with abrir_cadena() as chain:
            historial = chain.wallet_history(wallet_id)
            proyeccion = proyectar(historial, chain.available_balance(wallet_id), wallet_id)
        return _pintar(historial, wallet_id, nombres, proyeccion=proyeccion)

    @estadisticas.get("/admin/estadisticas")
    @requiere_administrador
    def estadisticas_de_un_usuario() -> str:
        """El administrador elige un usuario común y ve sus estadísticas.

        El selector lista a quien tiene wallet —las cuentas aprobadas— menos la
        sesión: el administrador de la semilla no tiene wallet, pero uno sembrado
        con ella sí. Igual se revisa el rol del elegido, para que la ruta no
        muestre a un administrador aunque alguien escriba su nombre.
        """
        nombre = request.args.get("usuario", "").strip()
        with abrir_cuentas() as cuentas:
            nombres = cuentas.nombres_por_wallet()
            elegido = cuentas.por_username(nombre) if nombre else None
        usuarios = sorted(
            (n for n in nombres.values() if n != g.user.username), key=str.lower
        )
        if not nombre:
            return render_template(
                "estadisticas.html", usuarios=usuarios, elegido=None, movimientos=[]
            )
        if elegido is None or elegido.wallet_id is None or elegido.role == ADMINISTRADOR:
            abort(404, description=MENSAJE_USUARIO_SIN_ESTADISTICAS)
        with abrir_cadena() as chain:
            historial = chain.wallet_history(elegido.wallet_id)
            proyeccion = proyectar(
                historial, chain.available_balance(elegido.wallet_id), elegido.wallet_id
            )
        return _pintar(
            historial,
            elegido.wallet_id,
            nombres,
            proyeccion=proyeccion,
            usuarios=usuarios,
            elegido=elegido,
        )

    return estadisticas


def _pintar(
    historial: Sequence[Transaction],
    propia: UUID,
    nombres: Mapping[UUID, str],
    **contexto: object,
) -> str:
    return render_template(
        "estadisticas.html",
        movimientos=movimientos_para_graficas(historial, propia, nombres),
        resumen=resumen_de_estadisticas(historial, propia),
        **contexto,
    )


def movimientos_para_graficas(
    historial: Sequence[Transaction], propia: UUID, nombres: Mapping[UUID, str]
) -> list[dict[str, str | None]]:
    """Cada movimiento de la wallet como lo necesitan las gráficas, del más viejo al más nuevo.

    El monto viaja como texto para no perder decimales en el JSON; el guion lo
    convierte para dibujar. `persona` es el nombre que ya se ve en el historial y
    nunca el identificador de la otra wallet: la página no expone wallets ajenas.
    """
    resultado = []
    for transaction in reversed(historial):
        sale = transaction.sender_id == propia
        otra = transaction.receiver_id if sale else transaction.sender_id
        if otra == CONSTITUYENTE_ID:
            persona = NOMBRE_DE_LA_BIENVENIDA
        else:
            persona = nombres.get(otra) or NOMBRE_SIN_DUENO
        resultado.append(
            {
                "fecha": transaction.created_at.astimezone(UTC).isoformat(),
                "tipo": "sale" if sale else "entra",
                "estado": str(transaction.status),
                "monto": format(transaction.amount, "f"),
                "persona": persona,
            }
        )
    return resultado


def resumen_de_estadisticas(
    historial: Sequence[Transaction], propia: UUID
) -> ResumenDeEstadisticas:
    """Suma lo completado de todo el historial: lo que está en espera todavía no se
    movió y lo rechazado nunca movió dinero. La cuenta incluye todos los estados."""
    recibido = enviado = Decimal(0)
    for transaction in historial:
        if transaction.status is not TransactionStatus.CONFIRMED:
            continue
        if transaction.sender_id == propia:
            enviado += transaction.amount
        else:
            recibido += transaction.amount
    return ResumenDeEstadisticas(
        recibido=recibido, enviado=enviado, movimientos=len(historial)
    )
