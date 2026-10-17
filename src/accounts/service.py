"""Servicio de cuentas: registro, ingreso y aprobación (REQ-30 a REQ-33).

Es el punto donde las credenciales, el repositorio de usuarios y el ledger se
encuentran. El servicio no conoce el driver: recibe una fábrica de transacciones
que rinde el ledger y el repositorio de cuentas sobre una misma conexión, y es esa
composición la que hace atómica la aprobación (REQ-33). Las cuentas no importan
Flask ni `src.web`: la autorización es de la presentación y acá no vive (REQ-29).

Las dos reglas delicadas del ingreso están acá y en ningún otro lado: la
contraseña se verifica **antes** de informar el estado de la cuenta, y una
contraseña equivocada da el mismo mensaje exista o no el usuario (REQ-32).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from src.accounts.credentials import (
    hashear_contrasena,
    normalizar_usuario,
    validar_contrasena,
    validar_usuario,
    verificar_contrasena,
)
from src.accounts.model import (
    APROBADO,
    PENDIENTE,
    RECHAZADO,
    USUARIO,
    Usuario,
    UsuarioDuplicado,
)
from src.accounts.ports import RepositorioDeUsuarios
from src.domain.blockchain import Blockchain
from src.emision import CONSTITUYENTE_ID, SALDO_DE_BIENVENIDA

# El único texto que ve quien no acierta la contraseña. No dice cuál de las dos
# cosas falló ni si el nombre existe: el ingreso no puede ser un oráculo de
# cuentas (REQ-32, §9 del diseño).
MENSAJE_DE_CREDENCIALES_INVALIDAS = "Usuario o contraseña incorrectos."

# Hash de una contraseña que ninguna cuenta usa. Se verifica cuando el nombre no
# existe para que ese camino pague el mismo scrypt que uno existente: el tiempo de
# respuesta tampoco tiene que delatar la existencia de la cuenta (REQ-36).
_HASH_DE_RELLENO = hashear_contrasena("contrasena-de-relleno")


class Transaccion(Protocol):
    """Lo que el servicio necesita de una transacción de cuentas (REQ-33)."""

    ledger: Blockchain
    usuarios: RepositorioDeUsuarios

    def commit(self) -> None: ...


FabricaDeTransacciones = Callable[[], AbstractContextManager[Transaccion]]


class CredencialesInvalidas(Exception):
    """El nombre no existe o la contraseña no es la suya (REQ-32).

    El mismo tipo y el mismo texto para los dos casos: el ingreso no puede decir
    cuál de los dos falló, ni siquiera a través del mensaje.
    """


class UsuarioInexistente(Exception):
    """No hay una cuenta con ese identificador (REQ-31)."""


class UsuarioNoPendiente(Exception):
    """La cuenta ya no está pendiente, así que la operación no corresponde (REQ-31).

    `estado` es el que tenía la fila al intentarlo, o `None` si la fila
    desapareció entre la lectura y la escritura.
    """

    def __init__(self, estado: str | None) -> None:
        self.estado = estado
        if estado is None:
            mensaje = "La cuenta ya no está pendiente."
        else:
            mensaje = f"La cuenta ya no está pendiente: su estado es {estado}."
        super().__init__(mensaje)


class NoAprobado(Exception):
    """La contraseña es correcta pero la cuenta no está habilitada (REQ-32)."""

    def __init__(self, estado: str, motivo: str | None = None) -> None:
        self.estado = estado
        self.motivo = motivo
        super().__init__(_mensaje_de_estado(estado, motivo))


def _mensaje_de_estado(estado: str, motivo: str | None) -> str:
    """Texto del ingreso según el estado; el rechazo lleva el motivo que dejó el administrador."""
    if estado == PENDIENTE:
        return "Tu cuenta está esperando aprobación."
    if estado == RECHAZADO:
        if motivo:
            return f"Tu cuenta fue rechazada: {motivo}."
        return "Tu cuenta fue rechazada."
    return "Tu cuenta no está habilitada para ingresar."


def _estado_actual(usuarios: RepositorioDeUsuarios, id: UUID) -> str | None:
    """Estado de la fila para informar una segunda aprobación que perdió la carrera."""
    usuario = usuarios.get(id)
    return None if usuario is None else usuario.estado


class Cuentas:
    """Registro, ingreso y alta moderada de las cuentas (REQ-30 a REQ-33).

    Invariante: cada operación abre su propia transacción con la fábrica recibida
    y sólo confirma si terminó bien; un error en el medio se deshace entero y sube
    sin traducir (REQ-19). El servicio no conoce el driver ni la sesión.
    """

    def __init__(self, transaction: FabricaDeTransacciones) -> None:
        self._transaction = transaction

    def registrar(self, username: str, contrasena: str) -> Usuario:
        """Registra una cuenta pendiente y la devuelve (REQ-30).

        Se normaliza antes de validar porque `validar_usuario` no normaliza y su
        patrón sólo admite minúsculas: sin ese orden, `Ana` sería un nombre
        inválido en vez del mismo usuario que `ana`.

        Levanta `ValueError` con el motivo si la forma del usuario o el largo de
        la contraseña no cumplen, y `UsuarioDuplicado` si el nombre ya está.
        """
        nombre = normalizar_usuario(username)
        motivo = validar_usuario(nombre)
        if motivo is None:
            motivo = validar_contrasena(contrasena)
        if motivo is not None:
            raise ValueError(motivo)

        usuario = Usuario(
            id=uuid4(),
            username=nombre,
            password_hash=hashear_contrasena(contrasena),
            role=USUARIO,
            estado=PENDIENTE,
            motivo_rechazo=None,
            wallet_id=None,
            creado_en=datetime.now(UTC),
            aprobado_en=None,
        )
        with self._transaction() as actual:
            creado = actual.usuarios.add_pendiente(usuario)
            actual.commit()
        return creado

    def autenticar(self, username: str, contrasena: str) -> Usuario:
        """Devuelve la cuenta aprobada que acierta la contraseña (REQ-32).

        El orden es deliberado: primero se verifica la contraseña y sólo después
        se dice el estado. Así «esperando aprobación» y el motivo del rechazo no
        son un oráculo para descubrir cuentas sin credenciales.

        Con contraseña equivocada —o con un nombre que no existe— levanta
        `CredencialesInvalidas` con el mismo texto; con la contraseña correcta de
        una cuenta que no está aprobada levanta `NoAprobado` con su estado.
        """
        nombre = normalizar_usuario(username)
        with self._transaction() as actual:
            usuario = actual.usuarios.get_by_username(nombre)
            guardado = _HASH_DE_RELLENO if usuario is None else usuario.password_hash
            if not verificar_contrasena(contrasena, guardado) or usuario is None:
                raise CredencialesInvalidas(MENSAJE_DE_CREDENCIALES_INVALIDAS)
            if usuario.estado != APROBADO:
                raise NoAprobado(usuario.estado, usuario.motivo_rechazo)
            return usuario

    def pendientes(self) -> Sequence[Usuario]:
        """Las cuentas que esperan aprobación, de la más antigua a la más nueva (REQ-31)."""
        with self._transaction() as actual:
            return actual.usuarios.list_pendientes()

    def aprobar(self, id: UUID) -> Usuario:
        """Abre la cuenta: wallet, saldo de bienvenida y estado en una sola transacción.

        El `commit` va al final y es único: si `acreditar` falla, el ROLLBACK del
        contexto deshace también la wallet recién insertada y la cuenta sigue
        pendiente (REQ-33). Se lee la cuenta antes de escribir para que una que no
        está pendiente falle sin crear wallet, y si la fila cambió de estado entre
        la lectura y el `UPDATE`, el `None` del repositorio también es error y no
        éxito silencioso: así una segunda aprobación no crea otra wallet (REQ-31).
        """
        with self._transaction() as actual:
            usuario = actual.usuarios.get(id)
            if usuario is None:
                raise UsuarioInexistente(
                    f"No existe una cuenta con el identificador {id}."
                )
            if usuario.estado != PENDIENTE:
                raise UsuarioNoPendiente(usuario.estado)

            wallet = actual.ledger.register_wallet()
            actual.ledger.acreditar(
                emisor_id=CONSTITUYENTE_ID,
                destino_id=wallet.id,
                monto=SALDO_DE_BIENVENIDA,
            )
            aprobado = actual.usuarios.aprobar(id, wallet.id)
            if aprobado is None:
                raise UsuarioNoPendiente(_estado_actual(actual.usuarios, id))
            actual.commit()
            return aprobado

    def rechazar(self, id: UUID, motivo: str) -> Usuario:
        """Rechaza una cuenta pendiente y guarda el motivo (REQ-31).

        Un motivo en blanco no se guarda: el rechazo tiene que decir por qué, y el
        esquema exige el motivo no nulo. Igual que la aprobación, sólo toca una
        fila pendiente y trata el `None` del repositorio como error de la
        operación.
        """
        texto = motivo.strip()
        if not texto:
            raise ValueError("El rechazo necesita un motivo.")

        with self._transaction() as actual:
            usuario = actual.usuarios.get(id)
            if usuario is None:
                raise UsuarioInexistente(
                    f"No existe una cuenta con el identificador {id}."
                )
            if usuario.estado != PENDIENTE:
                raise UsuarioNoPendiente(usuario.estado)

            rechazado = actual.usuarios.rechazar(id, texto)
            if rechazado is None:
                raise UsuarioNoPendiente(_estado_actual(actual.usuarios, id))
            actual.commit()
            return rechazado


# `UsuarioDuplicado` se reexporta porque es la excepción que documenta la
# interfaz del servicio (REQ-30) y quien lo consume no tiene que conocer el modelo.
__all__ = [
    "CredencialesInvalidas",
    "Cuentas",
    "NoAprobado",
    "UsuarioDuplicado",
    "UsuarioInexistente",
    "UsuarioNoPendiente",
]
