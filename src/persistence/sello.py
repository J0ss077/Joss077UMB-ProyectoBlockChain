"""Sello de vigilancia: ancla externa contra el recorte de la cola (spec §2).

El sello guarda en un archivo JSON la altura y el hash de la cabeza de la cadena,
firmados con HMAC-SHA256 sobre la forma canónica del JSON. La firma permite notar
un cambio a mano del archivo y, como el ancla vive fuera de la base, un recorte de
la cola deja de ser indistinguible de una cadena que nunca tuvo esos bloques. El
sello no se actualiza solo: lo fija la persona después de sembrar, de reparar o de
comprobar el estado, y la escritura es atómica para que un corte a mitad no deje
un archivo truncado.

La lectura nunca levanta: un archivo ausente se informa como `"ausente"` y uno
ilegible como `"ilegible"`, que es lo que la auditoría necesita para mostrarlo en
el panel en vez de tumbar la página.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.domain.auditoria import LecturaDelSello, Sello

# Los dos motivos por los que la lectura no entrega un sello utilizable. Son los
# mismos valores que espera `EstadoDelSello.problema` en la auditoría.
AUSENTE = "ausente"
ILEGIBLE = "ilegible"


def _json_canonico(datos: dict[str, Any]) -> bytes:
    """Los bytes que se firman y se verifican: claves ordenadas y sin espacios.

    Ordenar las claves y quitar los espacios hace que la firma no dependa del
    formato con el que se escribió el archivo; solo de su contenido.
    """
    return json.dumps(
        datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _firma(clave: bytes, datos: dict[str, Any]) -> str:
    """HMAC-SHA256 en hexadecimal sobre la forma canónica de los datos."""
    return hmac.new(clave, _json_canonico(datos), hashlib.sha256).hexdigest()


def _sello_desde_datos(datos: dict[str, Any]) -> Sello:
    """Convierte los datos firmados en el `Sello` del dominio.

    La firma se comprueba antes de llamar acá, así que esto solo descarta datos
    con la forma equivocada: una altura no entera, un hash que no es texto o una
    marca de tiempo que no es un instante UTC. Cualquier caso levanta `ValueError`
    y quien lee lo traduce a `"ilegible"`.
    """
    altura = datos.get("altura")
    hash_del_bloque = datos.get("hash")
    fijado_en = datos.get("fijado_en")
    if not isinstance(altura, int) or isinstance(altura, bool) or altura < 0:
        raise ValueError("la altura del sello no es un entero no negativo")
    if not isinstance(hash_del_bloque, str) or not hash_del_bloque:
        raise ValueError("el hash del sello no es texto")
    if not isinstance(fijado_en, str):
        raise ValueError("la marca de tiempo del sello no es texto")
    instante = datetime.fromisoformat(fijado_en)
    if instante.utcoffset() != timedelta(0):
        raise ValueError("la marca de tiempo del sello no está en UTC")
    return Sello(altura=altura, hash=hash_del_bloque, fijado_en=instante)


class SelloDeVigilancia:
    """Lee y fija el sello de vigilancia en un archivo firmado con HMAC-SHA256.

    `ruta` es el archivo JSON del sello y `clave` la clave maestra con la que se
    firma. El adaptador no abre conexiones ni conoce la base: solo lee y escribe
    el ancla que la auditoría compara con la cadena.
    """

    def __init__(self, ruta: Path, clave: bytes) -> None:
        self._ruta = ruta
        self._clave = clave

    @property
    def ruta(self) -> Path:
        """El archivo donde se lee y donde se escribe el sello.

        Se expone para que la composición y las pruebas puedan afirmar cuál es el
        archivo en uso sin tocar el estado privado del adaptador.
        """
        return self._ruta

    def leer(self) -> LecturaDelSello:
        """Devuelve el sello guardado o el motivo por el que no se puede usar.

        No levanta ante ningún contenido: un archivo ausente da
        `problema="ausente"` y un JSON roto, con la forma equivocada o con una
        firma que no cuadra dan `problema="ilegible"`. Quien audita decide qué
        severidad tiene cada caso.
        """
        try:
            contenido = self._ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            return LecturaDelSello(sello=None, problema=AUSENTE)
        except OSError:
            return LecturaDelSello(sello=None, problema=ILEGIBLE)
        try:
            return LecturaDelSello(sello=self._leer_del_texto(contenido), problema=None)
        except Exception:  # el contrato es no caer con archivos rotos
            return LecturaDelSello(sello=None, problema=ILEGIBLE)

    def fijar(self, *, altura: int, hash: str) -> Sello:
        """Fija el sello en el archivo y devuelve lo fijado.

        La marca de tiempo es el instante actual en UTC. La escritura va primero a
        un archivo temporal en la misma carpeta y se reemplaza con `os.replace`,
        que es atómico en el mismo sistema de archivos: un corte a mitad deja el
        sello anterior intacto en vez de un JSON truncado. Crea la carpeta si no
        existe.
        """
        if not isinstance(altura, int) or isinstance(altura, bool) or altura < 0:
            raise ValueError("la altura del sello tiene que ser un entero no negativo")
        if not isinstance(hash, str) or not hash:
            raise ValueError("el hash del sello tiene que ser texto no vacío")
        sello = Sello(altura=altura, hash=hash, fijado_en=datetime.now(UTC))
        datos = {
            "altura": sello.altura,
            "hash": sello.hash,
            "fijado_en": sello.fijado_en.isoformat(),
        }
        documento = {"datos": datos, "firma": _firma(self._clave, datos)}
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(
            dir=self._ruta.parent, prefix=f"{self._ruta.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
                json.dump(
                    documento,
                    archivo,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self._ruta)
        finally:
            # Después de un `replace` exitoso el temporal ya no existe y esto no
            # hace nada; si la escritura falló, lo borra antes de dejar subir el
            # error para no acumular archivos a medio escribir.
            with suppress(OSError):
                os.unlink(temporal)
        return sello

    def _leer_del_texto(self, contenido: str) -> Sello:
        """Valida la estructura y la firma del archivo y devuelve el sello.

        Levanta `ValueError` —o lo que levante `json`— cuando el archivo no es el
        JSON esperado o la firma no cuadra; quien lee lo traduce a `"ilegible"`.
        """
        documento = json.loads(contenido)
        if not isinstance(documento, dict):
            raise ValueError("el sello no es un objeto JSON")
        datos = documento.get("datos")
        firma = documento.get("firma")
        if not isinstance(datos, dict) or not isinstance(firma, str):
            raise ValueError("el sello no tiene datos y firma")
        if not hmac.compare_digest(firma, _firma(self._clave, datos)):
            raise ValueError("la firma del sello no cuadra")
        return _sello_desde_datos(datos)
