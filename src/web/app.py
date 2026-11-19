"""Aplicación Flask: las rutas del eje y las de la sesión (REQ-24 a REQ-38).

La presentación resuelve una cosa sola: toma la petición, llama a la fachada del
ledger o al servicio de cuentas y pinta la plantilla con lo que devolvieron.
Ninguna ruta decide reglas de negocio ni ejecuta consultas (REQ-29), así que este
módulo no conoce el motor ni los repositorios: recibe una fábrica de cadenas y una
fábrica de cuentas, y habla con `Blockchain`, con `Wallet` y con `Cuentas`.

La sesión guarda sólo el identificador de la cuenta y se recarga de la base en
cada petición (REQ-37). Las puertas de `auth.py` deciden quién puede llamar: las
rutas del eje quedan del lado del administrador, el usuario común tiene su
tablero, que vive en `user.py` (REQ-34, REQ-35, REQ-39), y la cola de pendientes
del administrador está en `admin.py` (REQ-31). El motivo del rechazo se muestra
porque el CU-02 lo pide: quien propone una transacción tiene que saber por qué no
entró al pool.

Uso: `python -m src.web`.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import NotFound

from src.accounts.credentials import (
    AYUDA_DE_USUARIO,
    LARGO_MAXIMO_DE_USUARIO,
    LARGO_MINIMO_DE_CONTRASENA,
    PATRON_DE_USUARIO,
)
from src.accounts.fotos import MOTIVO_DE_FOTO_GRANDE
from src.accounts.model import ADMINISTRADOR, UsuarioDuplicado
from src.accounts.service import (
    CredencialesInvalidas,
    Cuentas,
    DuenoInvalido,
    NoAprobado,
)
from src.domain.blockchain import Blockchain, ensure_genesis
from src.errores import MENSAJE_SIN_CONEXION, NoHayConexion
from src.web.admin import crear_blueprint_de_la_cola
from src.web.asistente import crear_blueprint_del_asistente
from src.web.auth import (
    CLAVE_DEL_USUARIO,
    abrir_sesion,
    cerrar_sesion,
    requiere_administrador,
    sesion_vigente,
    usuario_de_la_sesion,
)
from src.web.estadisticas import crear_blueprint_de_estadisticas
from src.web.forms import a_monto, a_uuid, ruta_interna
from src.web.ia import crear_conector
from src.web.idioma import (
    COOKIE_DEL_IDIOMA,
    DURACION_DE_LA_COOKIE,
    IDIOMAS,
    idioma_actual,
    t,
    textos_de_js,
)
from src.web.panel import datos_del_panel
from src.web.perfil import crear_blueprint_del_perfil
from src.web.user import crear_blueprint_del_usuario

if TYPE_CHECKING:
    # Solo para las anotaciones: la presentación no arma el sello ni conoce su
    # adaptador (REQ-29); recibe el contrato estructural de abajo, ya construido por
    # el arranque o por las pruebas.
    from src.domain.auditoria import LecturaDelSello, Sello
    from src.domain.reparacion import Reparacion


class SelloDeVigilancia(Protocol):
    """Lo que la presentación necesita del sello de vigilancia que recibe.

    Es el contrato estructural del ancla externa contra el recorte de la cola: la
    lectura del panel y la escritura de la acción `fijar-sello` usan solo estos dos
    métodos. El adaptador real vive en la capa de persistencia y lo cablea el
    arranque; este módulo no lo importa (REQ-29).
    """

    def leer(self) -> LecturaDelSello:
        """Devuelve el sello guardado o el motivo por el que no se puede usar."""
        ...

    def fijar(self, *, altura: int, hash: str) -> Sello:
        """Escribe el sello en la cabeza indicada y devuelve lo fijado."""
        ...

# Nombre de la variable que firma la cookie. Es una constante y no un literal
# porque el respaldo y su mensaje de error tienen que nombrar la misma variable.
VARIABLE_DEL_SECRETO_DE_SESION = "SESSION_SECRET"

# La clave de ejemplo que trae `.env.example`. El respaldo de la aplicación la
# rechaza igual que el lector de la configuración: armar la aplicación con el valor
# público dejaría que cualquiera firme una cookie de sesión. La prueba de REQ-37
# exige que sea la misma que la del lector, para que las dos no se separen.
SECRETO_DE_SESION_DE_LA_PLANTILLA = "0" * 64

TAMANO_MAXIMO_DE_LA_PETICION = 3 * 1024 * 1024

# Acciones que acepta `POST /verificar/reparar`. Son claves estables y no frases:
# el despacho las compara y la plantilla las traduce. La de reagrupar usa
# `Blockchain.group_pending`; las otras cuatro, los métodos de reparación del
# dominio, y `fijar-sello` el adaptador inyectado.
ACCION_DE_REPARAR_TODO = "reparar-todo"
ACCION_DE_ENCADENAR = "encadenar"
ACCION_DE_AISLAR = "aislar"
ACCION_DE_RECHAZAR_PENDIENTES = "rechazar-pendientes"
ACCION_DE_REAGRUPAR = "reagrupar"
ACCION_DE_FIJAR_SELLO = "fijar-sello"
ACCIONES_DE_REPARACION = frozenset(
    (
        ACCION_DE_REPARAR_TODO,
        ACCION_DE_ENCADENAR,
        ACCION_DE_AISLAR,
        ACCION_DE_RECHAZAR_PENDIENTES,
        ACCION_DE_REAGRUPAR,
        ACCION_DE_FIJAR_SELLO,
    )
)

# Los avisos de la ruta de reparaciones. Van como constantes para que la bandeja
# los traduzca con la misma frase que se registró en `traducciones.EN`. Ninguno
# incluye cifras ni el detalle técnico del dominio: eso queda en el panel, que se
# vuelve a pintar después de la redirección.
MENSAJE_REPARACION_SIN_CONFIRMAR = (
    "No se reparó nada: falta marcar la casilla de confirmación."
)
MENSAJE_REPARACION_DESCONOCIDA = "No se reparó nada: esa acción no existe."
MENSAJE_SIN_SELLO_CONFIGURADO = (
    "No hay un sello de vigilancia configurado: no se escribió nada."
)
MENSAJE_SIN_BLOQUES_PARA_SELLAR = (
    "No hay ningún bloque que sellar: no se escribió nada."
)
MENSAJE_SELLO_NO_ESCRITO = "No se pudo escribir el sello: no cambió nada."
MENSAJE_SELLO_FIJADO = "El sello quedó fijado en la cabeza de la cadena."
MENSAJE_REPARAR_TODO = (
    "Se reparó todo lo que se pudo. Revisa el sello de vigilancia."
)
MENSAJE_ENCADENADO = "La cadena quedó reencadenada. Revisa el sello de vigilancia."
MENSAJE_ENCADENADO_NADA = "No había nada que reencadenar."
MENSAJE_AISLADO = (
    "Se aislaron las transacciones confirmadas inválidas. Revisa el sello de vigilancia."
)
MENSAJE_AISLADO_NADA = "No había transacciones confirmadas inválidas."
MENSAJE_PENDIENTES_RECHAZADAS = "Se rechazaron las transacciones inválidas del pool."
MENSAJE_PENDIENTES_NADA = "El pool no tenía transacciones inválidas."
MENSAJE_REAGRUPADO = "El pool quedó agrupado en un bloque nuevo."
MENSAJE_REAGRUPADO_NADA = "El pool estaba vacío: no se creó ningún bloque."


def _aviso_de_reparacion(
    reparacion: Reparacion, *, aplicado: str, nada: str
) -> tuple[str, str]:
    """El aviso y su categoría según lo que la reparación realmente hizo.

    Con cambios escritos se anuncia la acción que se aplicó; una reparación
    aplicada que no escribió nada se informa como que no había nada que hacer. Si
    no se aplicó, se muestra el detalle del dominio, que es el único que explica el
    motivo (la cadena ya estaba encadenada, el primer bloque no es el génesis, no
    había filas inválidas) sin afirmar que se reparó algo.
    """
    if reparacion.aplicada and reparacion.cambios > 0:
        return aplicado, "exito"
    if reparacion.aplicada:
        return nada, "aviso"
    return reparacion.detalle, "aviso"

# El dueño que se elige al registrar llegó mal escrito o no puede serlo. El texto
# es el mismo que da `DuenoInvalido` para una cuenta que no sirve: el formulario no
# tiene por qué contar en qué estado está la cuenta elegida.
MENSAJE_DUENO_INVALIDO = "Esa cuenta no puede ser dueña de una wallet."

FabricaDeCadenas = Callable[[], AbstractContextManager[Blockchain]]
FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]


def create_app(
    chain_factory: FabricaDeCadenas,
    cuentas_factory: FabricaDeCuentas,
    *,
    secret_key: str | bytes | None = None,
    asistente: Mapping[str, str | None] | None = None,
    sello: SelloDeVigilancia | None = None,
) -> Flask:
    """Arma la aplicación con las fábricas que abren el ledger y las cuentas.

    Las dos fábricas llegan por parámetro en vez de armarse aquí porque este módulo
    no puede importar la capa que las construye (REQ-29): la presentación no sabe
    de dónde salen la cadena ni el servicio de cuentas, solo que puede pedirlos.
    Ese es también el punto por el que las pruebas inyectan su propia base, y por
    el que `src/web/__main__.py` cablea las reales cuando se levanta la aplicación.

    `secret_key` se inyecta por la misma razón: el arranque pasa la clave que lee
    de la configuración. Si no llega, se toma del entorno, que es lo que deja a la
    fábrica usable sola en una prueba.

    `asistente` trae las variables del servicio de IA del ayudante, leídas de
    `.env` por el arranque. Sin ellas el ayudante contesta con su guía local.

    `sello` es el ancla externa contra el recorte de la cola que lee la auditoría
    de `/verificar` y que fija la acción `fijar-sello`. Llega inyectado para que
    este módulo no arme adaptadores de persistencia (REQ-29); sin él, la
    verificación declara el sello ausente y la acción avisa que no hay dónde
    escribirlo. Queda en `app.extensions["sello"]`.
    """
    app = Flask(__name__)
    app.secret_key = _secreto_de_sesion() if secret_key is None else secret_key
    # La cookie no es permanente —`session.permanent` nace en False y no se toca—,
    # no se lee desde JavaScript y no acompaña peticiones de otro sitio. `SECURE`
    # queda en False porque el prototipo se sirve por HTTP local.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # El único formulario con archivo es la foto de perfil, que admite 2 MB;
        # el margen cubre el resto del cuerpo. Más que eso se corta antes de leerlo.
        MAX_CONTENT_LENGTH=TAMANO_MAXIMO_DE_LA_PETICION,
    )
    # El sello vive junto al ayudante en las extensiones de la aplicación: es el
    # adaptador que inyecta el arranque y el que consultan la lectura y la escritura.
    app.extensions["sello"] = sello

    @contextmanager
    def abrir_cadena() -> Iterator[Blockchain]:
        """Abre el ledger y deja el génesis asegurado antes de usarlo."""
        with chain_factory() as chain:
            # El génesis se asegura en cada petición porque es idempotente: así la
            # aplicación no depende de que alguien haya corrido el arranque antes.
            ensure_genesis(chain)
            yield chain

    @contextmanager
    def abrir_cuentas() -> Iterator[Cuentas]:
        """Abre el servicio de cuentas que entrega la fábrica inyectada."""
        with cuentas_factory() as cuentas:
            yield cuentas

    def leer_sello() -> tuple[Sello | None, str | None]:
        """Lee el sello inyectado sin escribir nada (REQ-22).

        Sin adaptador configurado la lectura es `ausente`, que es lo que la
        auditoría necesita para declarar la nota y el límite del recorte. El
        adaptador nunca levanta: un archivo ilegible llega como `ilegible`.
        """
        if sello is None:
            return None, "ausente"
        lectura = sello.leer()
        return lectura.sello, lectura.problema

    def reparar_cadena(accion: str) -> tuple[str, str]:
        """Aplica una reparación de la cadena y devuelve el aviso y su categoría.

        Cada acción usa el método de la fachada que le corresponde. El aviso refleja
        el resultado real: si la reparación no se aplicó se muestra su detalle, que
        es el que explica por qué; si escribió cambios se anuncia la acción y se
        recuerda revisar el sello. El panel que sigue a la redirección vuelve a
        pintar el estado completo.
        """
        with abrir_cadena() as chain:
            if accion == ACCION_DE_REPARAR_TODO:
                reparaciones = chain.repair_all()
                if any(reparacion.aplicada for reparacion in reparaciones):
                    return MENSAJE_REPARAR_TODO, "exito"
                # Nada se aplicó: el detalle de la última reparación (el
                # reencadenado) es el que explica el estado en que quedó la cadena.
                return reparaciones[-1].detalle, "aviso"
            if accion == ACCION_DE_ENCADENAR:
                return _aviso_de_reparacion(
                    chain.repair_chain(),
                    aplicado=MENSAJE_ENCADENADO,
                    nada=MENSAJE_ENCADENADO_NADA,
                )
            if accion == ACCION_DE_AISLAR:
                return _aviso_de_reparacion(
                    chain.isolate_invalid_transactions(),
                    aplicado=MENSAJE_AISLADO,
                    nada=MENSAJE_AISLADO_NADA,
                )
            if accion == ACCION_DE_RECHAZAR_PENDIENTES:
                return _aviso_de_reparacion(
                    chain.reject_invalid_pending(),
                    aplicado=MENSAJE_PENDIENTES_RECHAZADAS,
                    nada=MENSAJE_PENDIENTES_NADA,
                )
            # De las acciones válidas solo queda reagrupar: cierra el pool en un
            # bloque nuevo, que es la agrupación de siempre y no una reparación.
            if chain.group_pending() is None:
                return MENSAJE_REAGRUPADO_NADA, "aviso"
            return MENSAJE_REAGRUPADO, "exito"

    def fijar_sello() -> None:
        """Fija el sello en la cabeza actual y avisa lo que pasó en la bandeja.

        La cadena se lee primero y el archivo se escribe después: si la escritura
        falla, ninguna tabla cambió y el sello anterior queda intacto. Sin sello
        configurado no hay archivo que escribir y la acción se declara no aplicada.
        """
        if sello is None:
            flash(MENSAJE_SIN_SELLO_CONFIGURADO, "aviso")
            return
        with abrir_cadena() as chain:
            cabeza = chain.blocks.last()
        if cabeza is None:
            flash(MENSAJE_SIN_BLOQUES_PARA_SELLAR, "aviso")
            return
        try:
            sello.fijar(altura=cabeza.block_index, hash=cabeza.hash)
        except (OSError, RuntimeError, ValueError):
            # El adaptador valida los datos y escribe el archivo; un fallo de la
            # ruta no puede tumbar la página ni dejar un sello a medio escribir.
            flash(MENSAJE_SELLO_NO_ESCRITO, "aviso")
            return
        flash(MENSAJE_SELLO_FIJADO, "exito")

    # Las rutas del usuario común se registran con las mismas fábricas: el
    # blueprint no arma el ledger ni las cuentas por su cuenta (REQ-29).
    app.register_blueprint(crear_blueprint_del_usuario(abrir_cadena, abrir_cuentas))
    # La cola de pendientes del administrador sigue la misma regla: recibe las
    # fábricas de cuentas y de cadena y no abre conexiones por su cuenta; la cadena
    # es la que alimenta el panel de wallets con saldos que comparten sus páginas
    # (REQ-29, REQ-31).
    app.register_blueprint(crear_blueprint_de_la_cola(abrir_cuentas, abrir_cadena))
    # Las estadísticas también: el común ve las suyas y el administrador elige de
    # quién; las dos leen con las mismas fábricas y no abren conexiones propias.
    app.register_blueprint(crear_blueprint_de_estadisticas(abrir_cadena, abrir_cuentas))
    # El perfil es de las dos clases de cuenta: datos, idioma y contraseña.
    app.register_blueprint(crear_blueprint_del_perfil(abrir_cuentas))
    # El ayudante, con su pestaña en la barra, lee la cadena y las cuentas para explicar,
    # en palabras simples, lo que tiene la cuenta de la sesión; tampoco abre conexiones propias.
    # El conector queda a la vista del arranque, que avisa en la terminal a qué IA quedó
    # conectado el ayudante.
    app.extensions["asistente"] = conector = crear_conector(asistente)
    app.register_blueprint(crear_blueprint_del_asistente(abrir_cadena, abrir_cuentas, conector))

    # `t` traduce en todas las plantillas, también en las macros importadas sin
    # contexto; por eso va como global del entorno y no en un procesador.
    app.jinja_env.globals["t"] = t

    @app.context_processor
    def idioma_de_la_pagina() -> dict[str, object]:
        """El idioma vigente, los disponibles y los textos que necesitan los guiones."""
        return {
            "idioma": idioma_actual(),
            "idiomas": IDIOMAS,
            "textos_de_js": textos_de_js(),
        }

    @app.post("/idioma")
    def elegir_idioma() -> Response:
        """Guarda el idioma elegido en una cookie y vuelve a la página de origen.

        Sólo se vuelve a una ruta propia: un `volver` que no empiece con una sola
        barra —o que empiece por dos, o por barra y barra invertida, que el navegador
        lee como dos— se descarta, para que el formulario no sirva de redirección
        abierta.
        """
        elegido = request.form.get("idioma", "")
        volver = ruta_interna(request.form.get("volver"), "/")
        respuesta = redirect(volver)
        if elegido in IDIOMAS:
            respuesta.set_cookie(
                COOKIE_DEL_IDIOMA,
                elegido,
                max_age=DURACION_DE_LA_COOKIE,
                httponly=True,
                samesite="Lax",
            )
        return respuesta

    @app.context_processor
    def valores_de_los_formularios() -> dict[str, object]:
        """Publica en las plantillas las reglas que ya viven en `credentials`.

        Es un procesador de contexto porque no toca la base: sólo comparte el
        patrón, los largos y la ayuda de los formularios de entrada, para que las
        plantillas no repitan el conjunto de caracteres permitido (REQ-30).
        """
        return {
            "patron_usuario": PATRON_DE_USUARIO,
            "largo_maximo_de_usuario": LARGO_MAXIMO_DE_USUARIO,
            "largo_minimo_de_contrasena": LARGO_MINIMO_DE_CONTRASENA,
            "ayuda_de_usuario": AYUDA_DE_USUARIO,
            "rol_administrador": ADMINISTRADOR,
        }

    @app.context_processor
    def nombres_de_las_wallets() -> dict[str, object]:
        """Publica `nombre_de_wallet(id)`: el usuario dueño de una wallet, o `None`.

        La lectura es perezosa y se hace una vez por petición: sólo la paga la
        página que muestra nombres, y una página de error no abre las cuentas. Las
        wallets que registra el administrador no tienen dueño y devuelven `None`.
        """

        def nombre_de_wallet(wallet_id: UUID) -> str | None:
            if "nombres_por_wallet" not in g:
                with abrir_cuentas() as cuentas:
                    g.nombres_por_wallet = cuentas.nombres_por_wallet()
            return g.nombres_por_wallet.get(wallet_id)

        return {"nombre_de_wallet": nombre_de_wallet}

    def url_de_foto(username: str) -> str | None:
        """La dirección de la foto de esa cuenta, o `None` para pintar su inicial.

        Como `nombre_de_wallet`, lee una vez por petición y sólo si la página
        muestra avatares. Va como global del entorno porque la usa la macro
        `avatar`, que se importa sin contexto. La fecha de la foto versiona la
        dirección: al cambiarla, la caché del navegador no muestra la vieja.
        """
        if "fotos_por_nombre" not in g:
            # El avatar es lo único que una página puede necesitar de la base
            # después de pintar el cuerpo. Si el motor se cayó, la página tiene
            # que salir igual —con la inicial— y no convertir el 503 en un 500.
            try:
                with abrir_cuentas() as cuentas:
                    g.fotos_por_nombre = cuentas.fotos_por_nombre()
            except NoHayConexion:
                g.fotos_por_nombre = {}
        actualizada = g.fotos_por_nombre.get(username)
        if actualizada is None:
            return None
        return url_for("perfil.foto", username=username, v=int(actualizada.timestamp()))

    app.jinja_env.globals["url_de_foto"] = url_de_foto

    @app.errorhandler(413)
    def demasiado_grande(_error):
        """Un cuerpo más grande que el tope: en la foto se avisa en el perfil."""
        if request.path == url_for("perfil.poner_foto") and g.get("user"):
            flash(MOTIVO_DE_FOTO_GRANDE, "motivo")
            return redirect(url_for("perfil.ver"))
        return render_template("error.html", detalle="La solicitud es demasiado grande."), 413

    @app.before_request
    def recargar_usuario() -> None:
        """Recarga la cuenta de la cookie en cada petición (REQ-37).

        Sin identificador no se abre ninguna conexión: una página de error o el
        propio ingreso no pagan una consulta por no tener sesión. Con
        identificador, la fila se relee de la base y se descarta la sesión si ya no
        existe o si dejó de estar aprobada, que es lo que hace que un cambio de
        estado o de rol se note sin reiniciar.
        """
        g.user = None
        if not session.get(CLAVE_DEL_USUARIO):
            return
        with abrir_cuentas() as cuentas:
            usuario = usuario_de_la_sesion(cuentas)
        if not sesion_vigente(usuario):
            cerrar_sesion()
            return
        g.user = usuario

    @app.route("/registrarme", methods=["GET", "POST"])
    def registrarme():
        """REQ-30: registra una cuenta pendiente y muestra qué usuario ingresar.

        El registro no abre sesión: la cuenta nace pendiente y la aprobación es
        del administrador. Las dos contraseñas se comparan antes de llamar al
        servicio porque ese dato no es una regla del dominio sino del formulario;
        el resto de las validaciones las decide el servicio y su motivo se muestra
        tal cual para que la persona sepa cómo corregir.
        """
        if request.method == "GET":
            return _formulario_de_registro()
        nombre = request.form.get("usuario", "")
        contrasena = request.form.get("contrasena", "")
        if contrasena != request.form.get("repetir", ""):
            return _formulario_de_registro("Las contraseñas no coinciden.", nombre)
        with abrir_cuentas() as cuentas:
            try:
                creado = cuentas.registrar(nombre, contrasena)
            except UsuarioDuplicado:
                return _formulario_de_registro(
                    "Ese nombre de usuario ya está registrado.", nombre
                )
            except ValueError as error:
                return _formulario_de_registro(str(error), nombre)
        return render_template("registro.html", creado=creado)

    @app.route("/ingresar", methods=["GET", "POST"])
    def ingresar():
        """REQ-32: abre la sesión sólo a una cuenta aprobada que acierte la clave.

        Los fallos se pintan en la misma página con el texto que elige el
        servicio: el de credenciales es único para el usuario existente y el
        inexistente, y el del pendiente o el rechazado dice su estado. El rol
        decide a qué pantalla se va después, y la sesión no se abre hasta después
        de autenticar.
        """
        if request.method == "GET":
            return render_template("ingreso.html", error=None, usuario="")
        nombre = request.form.get("usuario", "")
        contrasena = request.form.get("contrasena", "")
        with abrir_cuentas() as cuentas:
            try:
                usuario = cuentas.autenticar(nombre, contrasena)
            except (CredencialesInvalidas, NoAprobado) as error:
                return render_template("ingreso.html", error=str(error), usuario=nombre)
        abrir_sesion(usuario)
        if usuario.role == ADMINISTRADOR:
            return redirect(url_for("portada"))
        return redirect(url_for("usuario.mi_tablero"))

    @app.post("/salir")
    def salir():
        """REQ-37: cierra la sesión y devuelve al ingreso."""
        cerrar_sesion()
        return redirect(url_for("ingresar"))

    @app.get("/")
    def portada():
        """Portada: los conteos del ledger y el panel lateral, sólo del administrador.

        Sin sesión manda al ingreso; un usuario común va a su tablero, que es su
        pantalla de trabajo. No lleva decorador porque tiene que poder contestar a
        quien todavía no ingresó.
        """
        if g.user is None:
            return redirect(url_for("ingresar"))
        if g.user.role != ADMINISTRADOR:
            return redirect(url_for("usuario.mi_tablero"))
        with abrir_cadena() as chain:
            estado = chain.ledger_state()
            bloques = chain.blocks.list()
            # Todo son lecturas de la fachada: la cadena para dibujar sus eslabones,
            # el pool, el dictamen y las últimas transacciones. El repositorio lista
            # de la más vieja a la más nueva, así que las últimas son la cola de la
            # lista completa.
            # El panel sale de una sola fuente, la misma para todas las páginas del
            # administrador: la lista de wallets y el saldo disponible que calcula la
            # fachada con la cuenta del envío (REQ-05, REQ-29). Es la celda de la
            # matriz de permisos (§8) que le da al administrador las wallets con sus
            # saldos, y el usuario común no la recibe (REQ-35).
            return render_template(
                "index.html",
                estado=estado,
                bloques=bloques,
                # Sólo se cuentan los cinco eslabones que dibuja la portada.
                transacciones_por_bloque={
                    bloque.id: len(chain.transactions.of_block(bloque.id))
                    for bloque in bloques[-5:]
                },
                en_el_pool=len(chain.transactions.pending()),
                dictamen=chain.verify_chain(),
                ultimas=list(reversed(chain.transactions.list(limit=estado["transactions"])[-5:])),
                **datos_del_panel(chain),
            )

    def _formulario_de_wallet(error: str | None = None, dueno: str = ""):
        """Pinta el registro de wallet con las cuentas que pueden ser dueñas.

        `dueno` es el identificador que se había elegido: se devuelve a la plantilla
        para que el selector conserve la opción después de un error. `usuarios` es la
        lista del selector; sin aprobadas queda sólo la opción de dejarla sin dueño.
        """
        with abrir_cuentas() as cuentas, abrir_cadena() as chain:
            return render_template(
                "wallet.html",
                wallet=None,
                error=error,
                dueno=dueno,
                usuarios=list(cuentas.usuarios_aprobados()),
                **datos_del_panel(chain),
            )

    @app.route("/wallets", methods=["GET", "POST"])
    @requiere_administrador
    def wallets():
        """CU-01 y REQ-46: registra una wallet y le pone dueño, o la deja sin dueño.

        La rama `GET` abre la cadena sólo para el panel lateral, que es la lista de
        wallets: con ella el CU-05 queda alcanzable desde cualquier página sin teclear
        una llave de 66 caracteres, dentro de una ruta que ya existe; y abre las cuentas
        para el selector de dueño, que lista las cuentas comunes aprobadas. El `POST`
        lee `dueno` —identificador de cuenta o vacío— y lo valida en el servicio: una
        cuenta que no puede ser dueña deja la wallet sin crear y repinta el formulario
        con el mismo motivo que da `DuenoInvalido`.
        """
        if request.method == "GET":
            return _formulario_de_wallet()
        texto = request.form.get("dueno", "").strip()
        dueno_id = a_uuid(texto)
        if texto and dueno_id is None:
            return _formulario_de_wallet(MENSAJE_DUENO_INVALIDO, texto)
        with abrir_cuentas() as cuentas:
            try:
                wallet = cuentas.registrar_wallet(dueno_id)
            except DuenoInvalido as error:
                # El servicio decide el motivo y el formulario lo muestra tal cual,
                # como el del registro de cuentas.
                return _formulario_de_wallet(str(error) or MENSAJE_DUENO_INVALIDO, texto)
        with abrir_cadena() as chain:
            return render_template(
                "wallet.html",
                wallet=wallet,
                error=None,
                dueno="",
                usuarios=[],
                **datos_del_panel(chain),
            )

    @app.route("/transacciones", methods=["GET", "POST"])
    @requiere_administrador
    def transacciones():
        """CU-02: propone una transacción e informa si entró al pool o por qué no (REQ-25).

        El motivo se muestra aunque no haya fila guardada: el rechazo sin escritura
        también es un resultado del caso de uso, y quien propuso necesita saberlo. El
        selector de wallets y el panel lateral son la misma lista de la fachada, así que
        se consulta una vez por página.
        """
        if request.method == "GET":
            with abrir_cadena() as chain:
                return render_template(
                    "transaccion.html",
                    resultado=None,
                    error_formulario=None,
                    **datos_del_panel(chain),
                )
        with abrir_cadena() as chain:
            sender_id = a_uuid(request.form.get("sender_id"))
            receiver_id = a_uuid(request.form.get("receiver_id"))
            if sender_id is None or receiver_id is None:
                # Un identificador ausente o mal escrito no llega a la fachada: se
                # informa en la misma página, que es el resultado del caso de uso.
                return render_template(
                    "transaccion.html",
                    resultado=None,
                    error_formulario="El emisor y el receptor deben ser wallets registradas.",
                    **datos_del_panel(chain),
                )
            resultado = chain.create_transaction(
                sender_id=sender_id,
                receiver_id=receiver_id,
                amount=a_monto(request.form.get("amount")),
            )
            return render_template(
                "transaccion.html",
                resultado=resultado,
                error_formulario=None,
                **datos_del_panel(chain),
            )

    @app.route("/bloques", methods=["GET", "POST"])
    @requiere_administrador
    def bloques():
        """CU-03: agrupa el pool en un bloque nuevo y muestra el eslabón creado (REQ-26).

        La rama `GET` abre la cadena solo para el panel lateral; el `POST` además lee el
        pool y lo agrupa.
        """
        if request.method == "GET":
            with abrir_cadena() as chain:
                return render_template(
                    "bloque.html",
                    bloque=None,
                    habia_pool=False,
                    **datos_del_panel(chain),
                )
        with abrir_cadena() as chain:
            habia_pool = bool(chain.transactions.pending())
            bloque = chain.group_pending()
            return render_template(
                "bloque.html",
                bloque=bloque,
                habia_pool=habia_pool,
                **datos_del_panel(chain),
            )

    @app.get("/verificar")
    @requiere_administrador
    def verificar():
        """CU-04: recalcula la cadena, la audita y muestra el panel completo (REQ-27).

        Sigue entregando el dictamen de siempre y suma la auditoría de solo lectura
        con el sello ya leído. No escribe: ni tablas ni el archivo del sello
        (REQ-22); las reparaciones son el POST aparte y explícito.
        """
        sello_leido, problema = leer_sello()
        with abrir_cadena() as chain:
            return render_template(
                "verificar.html",
                dictamen=chain.verify_chain(),
                auditoria=chain.audit_chain(
                    sello=sello_leido, problema_del_sello=problema
                ),
                **datos_del_panel(chain),
            )

    @app.post("/verificar/reparar")
    @requiere_administrador
    def reparar():
        """Aplica una reparación explícita y vuelve a `/verificar` (spec §4).

        La confirmación y la acción se validan antes de tocar la cadena: sin
        `confirmar=si` o con una acción inventada no se escribe nada y la bandeja
        avisa. Todas las ramas responden 303 a la verificación, que es el patrón
        POST-redirect-GET con el que el panel vuelve a pintar el estado real.
        """
        accion = request.form.get("accion", "")
        if request.form.get("confirmar") != "si":
            flash(MENSAJE_REPARACION_SIN_CONFIRMAR, "aviso")
            return redirect(url_for("verificar"), code=303)
        if accion not in ACCIONES_DE_REPARACION:
            flash(MENSAJE_REPARACION_DESCONOCIDA, "aviso")
            return redirect(url_for("verificar"), code=303)
        if accion == ACCION_DE_FIJAR_SELLO:
            fijar_sello()
            return redirect(url_for("verificar"), code=303)
        aviso, categoria = reparar_cadena(accion)
        flash(aviso, categoria)
        return redirect(url_for("verificar"), code=303)

    @app.get("/historial/<wallet>")
    @requiere_administrador
    def historial(wallet: str):
        """CU-05: el historial de una wallet, con el estado de cada transacción (REQ-28).

        El identificador se valida antes de consultar nada y la wallet se busca en la
        fachada: si no existe, la respuesta es la página de error con 404 y no un
        error del motor en pantalla (RF-5). El panel lateral se pasa al final, cuando ya
        se sabe que la wallet existe.
        """
        try:
            wallet_id = UUID(wallet)
        except ValueError:
            abort(404, description="El identificador no es un UUID válido.")
        with abrir_cadena() as chain:
            if chain.wallets.get(wallet_id) is None:
                abort(404, description="No hay ninguna wallet registrada con ese identificador.")
            return render_template(
                "historial.html",
                wallet_id=wallet_id,
                transacciones=chain.wallet_history(wallet_id),
                **datos_del_panel(chain),
            )

    @app.errorhandler(404)
    def no_encontrado(error):
        """Página de error clara y en español para lo que no existe (RF-5).

        Las rutas de este módulo pasan su descripción en español. Cuando la ruta no
        existe, la descripción la pone Werkzeug en inglés, así que se reemplaza por
        una propia en vez de mostrarla dentro de una página en español. No se pasa el
        panel lateral: esta página no abre el ledger.
        """
        detalle = error.description
        if not detalle or detalle == NotFound.description:
            detalle = "No se encontró lo que buscabas."
        return render_template("error.html", detalle=detalle), 404

    @app.errorhandler(403)
    def sin_permiso(_error):
        """Página de error para la puerta que niega por rol (REQ-38).

        Igual que la del 404, no abre el ledger: la negación se pinta sólo con la
        explicación, para que una ruta prohibida no dependa de la base al mostrar
        el error.
        """
        return (
            render_template(
                "error.html",
                titulo="Sin permiso",
                encabezado="No tienes permiso para esta operación",
                detalle="Tu cuenta no tiene el rol que esta página exige.",
            ),
            403,
        )

    @app.errorhandler(NoHayConexion)
    def sin_base(_error):
        """La base no respondió: página propia con 503, no el 500 genérico del motor.

        Es el único fallo de infraestructura que la aplicación traduce (lo levanta
        el módulo de conexión de la capa de datos), y se pinta como las otras
        páginas de error:
        sin abrir el ledger ni las cuentas —volver a la base sería fallar otra vez—
        y con el botón de reintentar apuntando a esta misma dirección.

        El 503 y no el 500: el servidor está bien y lo que falta es un servicio del
        que depende, que es justo lo que significa «servicio no disponible». Un
        reintento tiene sentido, y por eso el botón está.

        Sólo se ofrece reintentar cuando la petición fue un GET: repetir un POST
        desde un enlace del navegador no es lo mismo que recargar la página, y el
        formulario ya se puede volver a enviar desde su pantalla.
        """
        return (
            render_template(
                "error.html",
                codigo=503,
                encabezado="La base de datos no respondió",
                detalle=MENSAJE_SIN_CONEXION,
                reintentar=request.full_path.rstrip("?")
                if request.method == "GET"
                else None,
            ),
            503,
        )

    return app


def _secreto_de_sesion() -> str:
    """Respaldo del secreto cuando la aplicación no lo recibe cableado (REQ-37).

    El arranque de verdad inyecta la clave de la configuración, que además sabe
    leer `.env`; este respaldo deja la fábrica usable sola —por ejemplo en una
    prueba— cuando la variable está en el entorno. Si falta, falla nombrando la
    variable en vez de firmar la cookie con una clave inventada.
    """
    valor = os.environ.get(VARIABLE_DEL_SECRETO_DE_SESION)
    if not valor:
        raise RuntimeError(
            f"Falta {VARIABLE_DEL_SECRETO_DE_SESION} en el entorno: la aplicación "
            "no puede firmar la cookie de sesión sin esa clave."
        )
    if valor == SECRETO_DE_SESION_DE_LA_PLANTILLA:
        raise RuntimeError(
            f"{VARIABLE_DEL_SECRETO_DE_SESION} sigue siendo el valor de la plantilla "
            "`.env.example`: reemplázala por una clave propia."
        )
    return valor


def _formulario_de_registro(error: str | None = None, usuario: str = ""):
    """Pinta el formulario de registro, con el motivo y el nombre si hubo error."""
    return render_template("registro.html", creado=None, error=error, usuario=usuario)
