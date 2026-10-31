"""Almacén de las fotos de perfil: archivos en una carpeta, fuera de la base.

La base guarda sólo el nombre del archivo, su tipo y cuándo cambió; los bytes
viven acá, como un artefacto aparte. El nombre lo genera el almacén (un
identificador al azar con la extensión del tipo), así que nada de lo que manda
quien sube la foto llega a formar una ruta: ni el nombre de su archivo ni su
usuario.

La escritura es atómica: se escribe un temporal en la misma carpeta y se lo
renombra, para que nadie lea nunca una foto a medio escribir.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

EXTENSIONES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# La forma de todo nombre que genera el almacén, y la misma que exige el CHECK de
# `fotos_de_perfil.archivo`. Un nombre que no la cumple no se abre ni se borra.
PATRON_DE_ARCHIVO = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")


class CarpetaDeFotos:
    """Guarda, ubica y borra las fotos de perfil dentro de una carpeta."""

    def __init__(self, carpeta: Path) -> None:
        self._carpeta = Path(carpeta)

    def guardar(self, datos: bytes, tipo: str) -> str:
        """Escribe la imagen con un nombre nuevo y lo devuelve."""
        self._carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"{uuid4().hex}.{EXTENSIONES[tipo]}"
        descriptor, temporal = tempfile.mkstemp(dir=self._carpeta, prefix=".subiendo-")
        try:
            with os.fdopen(descriptor, "wb") as archivo:
                archivo.write(datos)
            os.replace(temporal, self._carpeta / nombre)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise
        return nombre

    def ruta(self, nombre: str) -> Path | None:
        """Dónde está ese archivo, o `None` si el nombre no es uno del almacén o ya no está."""
        if not PATRON_DE_ARCHIVO.fullmatch(nombre):
            return None
        ruta = self._carpeta / nombre
        return ruta if ruta.is_file() else None

    def borrar(self, nombre: str) -> None:
        """Borra el archivo si existe; un nombre ajeno al almacén no se toca."""
        if PATRON_DE_ARCHIVO.fullmatch(nombre):
            (self._carpeta / nombre).unlink(missing_ok=True)
