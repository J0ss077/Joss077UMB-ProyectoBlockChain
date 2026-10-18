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
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID

from flask import (
    Flask,
    abort,
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
from src.accounts.model import ADMINISTRADOR, UsuarioDuplicado
from src.accounts.service import CredencialesInvalidas, Cuentas, NoAprobado
from src.domain.blockchain import Blockchain, ensure_genesis
from src.web.admin import crear_blueprint_de_la_cola
from src.web.auth import (
    CLAVE_DEL_USUARIO,
    abrir_sesion,
    cerrar_sesion,
    requiere_administrador,
    sesion_vigente,
    usuario_de_la_sesion,
)
from src.web.forms import a_monto, a_uuid
from src.web.panel import datos_del_panel
from src.web.user import crear_blueprint_del_usuario

# Nombre de la variable que firma la cookie. Es una constante y no un literal
# porque el respaldo y su mensaje de error tienen que nombrar la misma variable.
VARIABLE_DEL_SECRETO_DE_SESION = "SESSION_SECRET"

# La clave de ejemplo que trae `.env.example`. El respaldo de la aplicación la
# rechaza igual que el lector de la configuración: armar la aplicación con el valor
# público dejaría que cualquiera firme una cookie de sesión. La prueba de REQ-37
# exige que sea la misma que la del lector, para que las dos no se separen.
SECRETO_DE_SESION_DE_LA_PLANTILLA = "0" * 64

FabricaDeCadenas = Callable[[], AbstractContextManager[Blockchain]]
FabricaDeCuentas = Callable[[], AbstractContextManager[Cuentas]]


def create_app(
    chain_factory: FabricaDeCadenas,
    cuentas_factory: FabricaDeCuentas,
    *,
    secret_key: str | bytes | None = None,
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
    """
    app = Flask(__name__)
    app.secret_key = _secreto_de_sesion() if secret_key is None else secret_key
    # La cookie no es permanente —`session.permanent` nace en False y no se toca—,
    # no se lee desde JavaScript y no acompaña peticiones de otro sitio. `SECURE`
    # queda en False porque el prototipo se sirve por HTTP local.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

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

    # Las rutas del usuario común se registran con las mismas fábricas: el
    # blueprint no arma el ledger ni las cuentas por su cuenta (REQ-29).
    app.register_blueprint(crear_blueprint_del_usuario(abrir_cadena, abrir_cuentas))
    # La cola de pendientes del administrador sigue la misma regla: recibe las
    # fábricas de cuentas y de cadena y no abre conexiones por su cuenta; la cadena
    # es la que alimenta el panel de wallets con saldos que comparten sus páginas
    # (REQ-29, REQ-31).
    app.register_blueprint(crear_blueprint_de_la_cola(abrir_cuentas, abrir_cadena))

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

    @app.route("/wallets", methods=["GET", "POST"])
    @requiere_administrador
    def wallets():
        """CU-01: registra una wallet y muestra su clave pública (REQ-24).

        La rama `GET` abre la cadena solo para el panel lateral, que es la lista de
        wallets: con ella el CU-05 queda alcanzable desde cualquier página sin teclear
        una llave de 66 caracteres, dentro de una ruta que ya existe. El `POST` la pasa
        además con la wallet recién registrada a la vista.
        """
        if request.method == "GET":
            with abrir_cadena() as chain:
                return render_template(
                    "wallet.html", wallet=None, **datos_del_panel(chain)
                )
        with abrir_cadena() as chain:
            wallet = chain.register_wallet()
            return render_template(
                "wallet.html", wallet=wallet, **datos_del_panel(chain)
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
        """CU-04: recalcula la cadena y muestra el dictamen (REQ-27)."""
        with abrir_cadena() as chain:
            return render_template(
                "verificar.html",
                dictamen=chain.verify_chain(),
                **datos_del_panel(chain),
            )

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
            detalle = "No se encontró lo que buscaba."
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
