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

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from src.accounts.credentials import (
    hashear_contrasena,
    normalizar_usuario,
    validar_contrasena,
    validar_usuario,
    verificar_contrasena,
)
from src.accounts.fotos import tipo_de_imagen, validar_foto
from src.accounts.model import (
    ADMINISTRADOR,
    APROBADO,
    PENDIENTE,
    RECHAZADO,
    USUARIO,
    SolicitudDeContrasena,
    SolicitudYaPendiente,
    Usuario,
    UsuarioDuplicado,
)
from src.accounts.ports import AlmacenDeFotos, RepositorioDeUsuarios
from src.domain.blockchain import Blockchain
from src.emision import CONSTITUYENTE_ID, SALDO_DE_BIENVENIDA

# Los motivos con los que la agenda se niega a agregar a alguien. Una cuenta
# pendiente, rechazada o de administrador da el mismo texto que una que no existe:
# la agenda sólo admite a quien puede recibir un envío, y no tiene por qué contar
# en qué estado está la cuenta de otro.
MENSAJE_CONTACTO_INEXISTENTE = "No hay un usuario con ese nombre."
MENSAJE_CONTACTO_PROPIO = "No puedes agregarte a ti mismo."
MENSAJE_CONTACTO_REPETIDO = "Ya está en tus contactos."

# Cuántos nombres trae la vista previa de un campo de destinatario: los suficientes
# para elegir y no tantos que la lista sirva para recorrer todas las cuentas.
LIMITE_DE_SUGERENCIAS = 6

# Los motivos del cambio de contraseña desde el perfil. La contraseña actual se
# pide siempre: una sesión abierta en una computadora ajena no alcanza para
# cambiarla.
MENSAJE_CONTRASENA_ACTUAL_INCORRECTA = "La contraseña actual no es correcta."
MENSAJE_CONTRASENA_IGUAL = "La contraseña nueva tiene que ser distinta de la actual."
MENSAJE_SOLICITUD_YA_PENDIENTE = (
    "Ya tienes un cambio de contraseña esperando aprobación."
)
MENSAJE_SOLICITUD_YA_RESUELTA = "Esa solicitud ya no está pendiente."

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


class ContactoInvalido(Exception):
    """La cuenta no se puede agendar: no existe, no es un usuario común aprobado o es la propia."""


class CambioDeContrasenaInvalido(Exception):
    """El cambio de contraseña no se puede pedir; el texto dice por qué."""


class FotoInvalida(Exception):
    """La imagen no se puede usar como foto de perfil; el texto dice por qué."""


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

    def __init__(
        self, transaction: FabricaDeTransacciones, *, fotos: AlmacenDeFotos | None = None
    ) -> None:
        self._transaction = transaction
        self._fotos = fotos

    def _almacen(self) -> AlmacenDeFotos:
        """El almacén de fotos; sin él, el servicio no puede tocar una foto."""
        if self._fotos is None:
            raise RuntimeError("Este servicio de cuentas se armó sin almacén de fotos.")
        return self._fotos

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

    def por_id(self, id: UUID) -> Usuario | None:
        """La cuenta con ese identificador, o `None` si ya no existe (REQ-37).

        Es la lectura que hace la sesión en cada petición: la cookie guarda sólo
        el identificador y el rol y el estado se releen de la base, así un cambio
        se nota sin reiniciar y una cuenta borrada descarta la sesión. No escribe,
        así que la transacción se cierra sin confirmar nada.
        """
        with self._transaction() as actual:
            return actual.usuarios.get(id)

    def por_username(self, username: str) -> Usuario | None:
        """La cuenta con ese nombre, o `None` si no existe (REQ-34).

        Es la lectura con la que el envío del usuario común resuelve el
        destinatario por nombre de usuario antes de probar con el identificador
        de wallet. El repositorio normaliza, así que «Ana» y «ana» son la misma
        cuenta. No escribe, igual que `por_id`.
        """
        with self._transaction() as actual:
            return actual.usuarios.get_by_username(username)

    def nombres_por_wallet(self) -> Mapping[UUID, str]:
        """El nombre de usuario de cada wallet con dueño, para mostrarlo junto al código.

        Es una lectura de presentación: no escribe y la transacción se cierra sin
        confirmar, igual que `por_id`. Quien la use decide qué nombres mostrar; el
        tablero del usuario común filtra a sus contrapartes (REQ-35).
        """
        with self._transaction() as actual:
            return actual.usuarios.nombres_por_wallet()

    def contactos(self, usuario_id: UUID) -> Sequence[Usuario]:
        """La agenda de esa cuenta, ordenada por nombre de usuario. No escribe."""
        with self._transaction() as actual:
            return actual.usuarios.contactos_de(usuario_id)

    def sugerir_destinatarios(
        self, usuario_id: UUID, texto: str, *, sin_contactos: bool = False
    ) -> Sequence[str]:
        """Los nombres que coinciden con lo tecleado, para la vista previa de un campo.

        Sólo aparece quien puede recibir un envío —un usuario común aprobado— y
        nunca la cuenta que pregunta, que es la misma regla de `agregar_contacto`:
        la vista previa no ofrece a nadie que el formulario después rechace. Viaja
        sólo el nombre, que es lo que cualquiera ya puede teclear. Un texto vacío
        no lista a nadie. No escribe.
        """
        if not texto.strip():
            return []
        with self._transaction() as actual:
            return actual.usuarios.destinatarios_parecidos(
                texto, usuario_id, sin_contactos, LIMITE_DE_SUGERENCIAS
            )

    def agregar_contacto(self, usuario_id: UUID, username: str) -> Usuario:
        """Agenda por su nombre de usuario a otra cuenta común aprobada y la devuelve.

        Sólo se admite a quien puede recibir un envío: un usuario común aprobado,
        que es el único con wallet propia. Levanta `ContactoInvalido` con el motivo
        si el nombre no es de una cuenta así, si es la propia o si ya estaba.
        """
        with self._transaction() as actual:
            contacto = actual.usuarios.get_by_username(username.strip())
            if (
                contacto is None
                or contacto.role != USUARIO
                or contacto.estado != APROBADO
            ):
                raise ContactoInvalido(MENSAJE_CONTACTO_INEXISTENTE)
            if contacto.id == usuario_id:
                raise ContactoInvalido(MENSAJE_CONTACTO_PROPIO)
            if not actual.usuarios.agregar_contacto(usuario_id, contacto.id):
                raise ContactoInvalido(MENSAJE_CONTACTO_REPETIDO)
            actual.commit()
            return contacto

    def quitar_contacto(self, usuario_id: UUID, contacto_id: UUID) -> bool:
        """Saca la cuenta de la agenda; `False` si ya no estaba (otra pestaña, doble clic)."""
        with self._transaction() as actual:
            quitado = actual.usuarios.quitar_contacto(usuario_id, contacto_id)
            actual.commit()
            return quitado

    def cambiar_contrasena(
        self, usuario_id: UUID, actual: str, nueva: str
    ) -> SolicitudDeContrasena | None:
        """Cambia la contraseña desde el perfil, o la deja pendiente de aprobación.

        El usuario común no la cambia por su cuenta: se guarda una solicitud con el
        hash nuevo y un administrador la aprueba o la rechaza; se devuelve esa
        solicitud. El administrador no tiene a quién pedírsela, así que la suya se
        aplica de una vez y se devuelve `None`. En los dos casos se verifica antes
        la contraseña actual y la nueva cumple la misma regla que el registro.

        Levanta `CambioDeContrasenaInvalido` con el motivo.
        """
        motivo = validar_contrasena(nueva)
        if motivo is not None:
            raise CambioDeContrasenaInvalido(motivo)
        with self._transaction() as actual_tx:
            usuario = actual_tx.usuarios.get(usuario_id)
            if usuario is None or not verificar_contrasena(actual, usuario.password_hash):
                raise CambioDeContrasenaInvalido(MENSAJE_CONTRASENA_ACTUAL_INCORRECTA)
            if verificar_contrasena(nueva, usuario.password_hash):
                raise CambioDeContrasenaInvalido(MENSAJE_CONTRASENA_IGUAL)
            if usuario.role == ADMINISTRADOR:
                actual_tx.usuarios.cambiar_hash(usuario_id, hashear_contrasena(nueva))
                actual_tx.commit()
                return None
            try:
                solicitud = actual_tx.usuarios.crear_solicitud(
                    usuario_id, hashear_contrasena(nueva)
                )
            except SolicitudYaPendiente as error:
                raise CambioDeContrasenaInvalido(MENSAJE_SOLICITUD_YA_PENDIENTE) from error
            actual_tx.commit()
            return solicitud

    def ultima_solicitud(self, usuario_id: UUID) -> SolicitudDeContrasena | None:
        """El último cambio de contraseña pedido por la cuenta, para su perfil."""
        with self._transaction() as actual:
            return actual.usuarios.ultima_solicitud(usuario_id)

    def solicitudes_pendientes(self) -> Sequence[SolicitudDeContrasena]:
        """Los cambios de contraseña que esperan al administrador."""
        with self._transaction() as actual:
            return actual.usuarios.solicitudes_pendientes()

    def resolver_solicitud(
        self, id: UUID, *, aprobada: bool, motivo: str = ""
    ) -> SolicitudDeContrasena:
        """Aprueba (la contraseña nueva pasa a la cuenta) o rechaza una solicitud.

        El motivo del rechazo es opcional: a diferencia del alta, la persona sigue
        entrando con su contraseña de siempre. Una solicitud que ya no está
        pendiente levanta `CambioDeContrasenaInvalido`.
        """
        with self._transaction() as actual:
            resuelta = actual.usuarios.resolver_solicitud(
                id, aprobada=aprobada, motivo=motivo.strip() or None
            )
            if resuelta is None:
                raise CambioDeContrasenaInvalido(MENSAJE_SOLICITUD_YA_RESUELTA)
            actual.commit()
            return resuelta

    def poner_foto(self, usuario_id: UUID, datos: bytes) -> None:
        """Pone o reemplaza la foto de perfil. Levanta `FotoInvalida` con el motivo.

        La imagen va al almacén como un archivo aparte y la base guarda sólo su
        nombre. El orden evita que la base apunte a un archivo que no está: primero
        se escribe el archivo nuevo, después se confirma la referencia —si eso
        falla, el archivo recién escrito se borra— y recién entonces se borra el
        archivo de la foto anterior.
        """
        motivo = validar_foto(datos)
        if motivo is not None:
            raise FotoInvalida(motivo)
        almacen = self._almacen()
        nombre = almacen.guardar(datos, tipo_de_imagen(datos))
        try:
            with self._transaction() as actual:
                anterior = actual.usuarios.guardar_foto(
                    usuario_id, nombre, tipo_de_imagen(datos)
                )
                actual.commit()
        except BaseException:
            almacen.borrar(nombre)
            raise
        if anterior is not None and anterior != nombre:
            almacen.borrar(anterior)

    def quitar_foto(self, usuario_id: UUID) -> bool:
        """Vuelve al avatar por defecto; `False` si la cuenta no tenía foto.

        Primero se borra la referencia y después el archivo: si el borrado del
        archivo fallara, queda un archivo suelto, nunca una fila que no lleva a nada.
        """
        with self._transaction() as actual:
            archivo = actual.usuarios.quitar_foto(usuario_id)
            actual.commit()
        if archivo is None:
            return False
        self._almacen().borrar(archivo)
        return True

    def archivo_de_foto(self, username: str) -> tuple[Path, str] | None:
        """Dónde está el archivo de la foto de esa cuenta y su tipo, para servirla.

        `None` si la cuenta no tiene foto o si su archivo ya no está en el almacén.
        No escribe.
        """
        with self._transaction() as actual:
            foto = actual.usuarios.foto_de(username)
        if foto is None:
            return None
        ruta = self._almacen().ruta(foto.archivo)
        return (ruta, foto.tipo) if ruta is not None else None

    def fotos_por_nombre(self) -> Mapping[str, datetime]:
        """Qué cuentas tienen foto y desde cuándo, para elegir foto o inicial.

        Sólo se devuelven las fotos cuyo archivo sigue en la carpeta. La base
        guarda la referencia y los bytes viven aparte, así que restaurar la base
        sin su carpeta dejaría filas apuntando a archivos que no están: sin este
        filtro la interfaz pintaría una imagen rota en vez de la inicial. No escribe.
        """
        with self._transaction() as actual:
            fotos = actual.usuarios.fotos_por_nombre()
        almacen = self._almacen()
        return {
            username: foto.actualizado_en
            for username, foto in fotos.items()
            if almacen.ruta(foto.archivo) is not None
        }

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
    "CambioDeContrasenaInvalido",
    "ContactoInvalido",
    "FotoInvalida",
    "CredencialesInvalidas",
    "Cuentas",
    "NoAprobado",
    "UsuarioDuplicado",
    "UsuarioInexistente",
    "UsuarioNoPendiente",
]
