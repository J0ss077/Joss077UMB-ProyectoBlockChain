"""Sesión y puertas por rol de la presentación (REQ-37, REQ-38).

La cookie guarda **sólo el identificador** de la cuenta: en cada petición el
usuario se relee de la base, así un cambio de estado o de rol se nota sin
reiniciar la aplicación y una cuenta borrada descarta la sesión (diseño §9).

La autorización vive acá y no en el dominio: el decorador de cada ruta declara el
rol que exige y deja el `Usuario` de la sesión en `g.user` para las plantillas.
Este módulo no conoce el motor ni el repositorio; recibe el servicio de cuentas ya
armado, que es lo que mantiene a la presentación sin consultas propias (REQ-29).
"""
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast
from uuid import UUID

from flask import abort, g, redirect, session, url_for

from src.accounts.model import ADMINISTRADOR, APROBADO, Usuario
from src.accounts.service import Cuentas

# La clave de la cookie. No se guardan el rol ni el estado a propósito: se releen
# de la base en cada petición y por eso una degradación de rol surte efecto sin
# reiniciar. `usuario_id` es el único dato que viaja en la cookie firmada.
CLAVE_DEL_USUARIO = "usuario_id"

Vista = TypeVar("Vista", bound=Callable[..., Any])


def usuario_de_la_sesion(cuentas: Cuentas) -> Usuario | None:
    """La cuenta que indica la cookie, recargada de la base, o `None` (REQ-37).

    Un identificador que no es un UUID o que ya no existe no rompe la petición: se
    devuelve `None`, que es lo mismo que no tener sesión. La recarga es la que
    hace visible un cambio de estado o de rol sin reiniciar la aplicación.
    """
    guardado = session.get(CLAVE_DEL_USUARIO)
    if not isinstance(guardado, str):
        return None
    try:
        identificador = UUID(guardado)
    except ValueError:
        return None
    return cuentas.por_id(identificador)


def sesion_vigente(usuario: Usuario | None) -> bool:
    """Indica si la cuenta recargada todavía puede usar el sistema (REQ-37).

    Se exige `aprobado` también en la recarga y no sólo en el ingreso: si la fila
    cambió de estado, la sesión que ya estaba abierta deja de valer.
    """
    return usuario is not None and usuario.estado == APROBADO


def abrir_sesion(usuario: Usuario) -> None:
    """Guarda sólo el identificador y renueva la cookie (REQ-37).

    El `clear` previo descarta cualquier sesión anterior: una cookie que
    sobreviviera a otro ingreso no puede arrastrar el identificador de la cuenta
    que estaba antes.
    """
    session.clear()
    session[CLAVE_DEL_USUARIO] = str(usuario.id)


def cerrar_sesion() -> None:
    """Descarta la cookie de sesión; el navegador deja de entrar (REQ-37)."""
    session.clear()


def requiere_sesion(vista: Vista) -> Vista:
    """Exige una sesión abierta; sin sesión manda al ingreso (REQ-37).

    La puerta no consulta la base: la recarga de `g.user` la hace el
    `before_request` de la aplicación, antes de que la vista se ejecute.
    """

    @wraps(vista)
    def envuelta(*args: Any, **kwargs: Any) -> Any:
        if getattr(g, "user", None) is None:
            return redirect(url_for("ingresar"))
        return vista(*args, **kwargs)

    return cast(Vista, envuelta)


def requiere_administrador(vista: Vista) -> Vista:
    """Exige una cuenta administradora (REQ-38).

    Sin sesión redirige al ingreso; con una sesión de usuario común responde 403
    y no ejecuta la vista. Que el común no pueda reemplazar al administrador es
    justamente lo que mide esta puerta.
    """

    @wraps(vista)
    def envuelta(*args: Any, **kwargs: Any) -> Any:
        usuario = getattr(g, "user", None)
        if usuario is None:
            return redirect(url_for("ingresar"))
        if usuario.role != ADMINISTRADOR:
            abort(403)
        return vista(*args, **kwargs)

    return cast(Vista, envuelta)
