"""Datos de demostración de la parte social: contactos y una solicitud de contraseña.

La semilla del ledger deja wallets, cuentas y movimientos, pero las pantallas que no
miran la cadena quedan vacías: la agenda de cada usuario y la cola de cambios de
contraseña del administrador. Un producto de demostración con esas dos pantallas en
blanco no muestra el flujo completo.

Este módulo las llena con el mismo camino que la interfaz: los contactos se agregan con
`Cuentas.agregar_contacto`, que valida que la otra cuenta sea un usuario común aprobado,
y la solicitud se crea con `Cuentas.cambiar_contrasena`, que guarda el hash nuevo y la
deja esperando al administrador.

**Es idempotente**: si un contacto ya está o ya hay una solicitud pendiente, el servicio
levanta el motivo y este módulo lo ignora. Correrlo dos veces no duplica nada.

Uso:

    <venv> -m src.demo_social
"""
from __future__ import annotations

from src.accounts.almacen import CarpetaDeFotos
from src.accounts.service import (
    MENSAJE_CONTACTO_REPETIDO,
    MENSAJE_SOLICITUD_YA_PENDIENTE,
    CambioDeContrasenaInvalido,
    ContactoInvalido,
    Cuentas,
)
from src.persistence.factory import carpeta_de_fotos, transaction

# La agenda de cada cuenta de demostración. El fondo no agenda a nadie: es la
# contraparte de los aportes, no una persona con la que se mantenga una agenda.
CONTACTOS: dict[str, tuple[str, ...]] = {
    "asociado1": ("asociado2", "asociado3", "fondo"),
    "asociado2": ("asociado1", "fondo"),
    "asociado3": ("asociado1", "asociado2"),
}

# La cuenta que pide el cambio y la contraseña nueva que queda esperando aprobación.
# La actual es la de demostración que siembra el arranque.
CUENTA_QUE_PIDE = "asociado2"
CONTRASENA_ACTUAL = "demostracion"
CONTRASENA_NUEVA = "clave-nueva-2026"


def sembrar(cuentas: Cuentas) -> tuple[int, int]:
    """Agrega los contactos que falten y deja una solicitud pendiente.

    Devuelve cuántos contactos y cuántas solicitudes se crearon en esta corrida.
    """
    agregados = 0
    for nombre, agenda in CONTACTOS.items():
        usuario = cuentas.por_username(nombre)
        if usuario is None:
            continue
        for contacto in agenda:
            try:
                cuentas.agregar_contacto(usuario.id, contacto)
                agregados += 1
            except ContactoInvalido as error:
                # «Ya está en tus contactos» es el único caso que significa que este
                # paso ya se hizo. Cualquier otro (la cuenta no existe, no es común,
                # es la propia) es un fallo de la semilla y no se puede esconder.
                if str(error) != MENSAJE_CONTACTO_REPETIDO:
                    raise
                continue

    solicitudes = 0
    usuario = cuentas.por_username(CUENTA_QUE_PIDE)
    if usuario is not None:
        try:
            cuentas.cambiar_contrasena(
                usuario.id, CONTRASENA_ACTUAL, CONTRASENA_NUEVA
            )
            solicitudes = 1
        except CambioDeContrasenaInvalido as error:
            # Sólo «ya hay una pendiente» es idempotencia; si la contraseña actual
            # cambió, el mensaje de la cola sería falso y hay que verlo.
            if str(error) != MENSAJE_SOLICITUD_YA_PENDIENTE:
                raise
    return agregados, solicitudes


def main() -> None:
    """Arma el servicio de cuentas real y siembra la parte social de la demostración."""
    cuentas = Cuentas(transaction, fotos=CarpetaDeFotos(carpeta_de_fotos()))
    agregados, solicitudes = sembrar(cuentas)
    total = sum(len(agenda) for agenda in CONTACTOS.values())
    print(
        f"contactos: {agregados} agregados ahora (la agenda de la demo tiene {total})"
    )
    estado = (
        "1 creada ahora (esperando al administrador)"
        if solicitudes
        else "ya había una pendiente"
    )
    print(f"solicitudes de contraseña: {estado}")


if __name__ == "__main__":
    main()
