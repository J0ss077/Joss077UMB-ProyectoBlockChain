# Perfil, contactos, fotos, idioma y ayudante — diseño

**Proyecto**: _Diseño de la arquitectura de un sistema transaccional basado en blockchain._
**Alcance de este documento**: las cinco funciones que llegaron en la rama del equipo y que
entran al alcance evaluado. **La analítica que pidió el tutor no entra**: se está diseñando
todavía y el ayudante es hoy un módulo de explicación, no un tablero de estadísticas.

---

## 1. Por qué

El sistema de usuarios dejó a la persona con una cuenta, un saldo y un historial, pero sin
nada de lo que un producto tiene alrededor: no podía cambiar su contraseña, no podía elegir
a quién le envía sin teclear un nombre de usuario, no tenía foto, no tenía inglés y no tenía
dónde preguntar qué significa lo que está viendo. Las cinco funciones de este documento
cierran esa brecha.

El tutor pidió además que el ayudante sirviera para **analítica**. Ese pedido es posterior y
más grande: la decisión de esta entrega es que el chat deja de ser una ventana flotante y
pasa a ser un **módulo propio**, que es el lugar donde la analítica va a vivir. Lo que hay
hoy en ese módulo es explicación, no estadística, y así se declara.

## 2. Lo que ya existe, y no se toca

- Las cinco rutas del eje y las rutas de cuenta que agregó el sistema de usuarios.
- Las tres capas y sus guardas: la presentación no habla SQL ni decide reglas (REQ-29), el
  dominio no importa el driver (REQ-16), y las cuentas son un contexto aparte del ledger.
- Las llaves privadas cifradas con la `MASTER_KEY` del entorno y el saldo de bienvenida.
- Los 39 requerimientos del documento maestro, con su prueba.

Ninguna de estas funciones cambia el ledger ni la forma en que se firma o se agrupa.

## 3. Decisiones que tomó la persona a cargo

1. **La foto es un artefacto, no una columna.** Los bytes viven en una carpeta del equipo
   (`FOTOS_DIR`) y la base guarda el nombre, el tipo y la fecha. El respaldo, por lo tanto,
   son dos piezas: la base y la carpeta.
2. **Los contactos son una agenda de un solo sentido**: agregar a alguien no lo obliga a
   agregarte.
3. **El cambio de contraseña se pide y un administrador lo aprueba.** Se conserva como
   mecanismo de seguridad, aunque el sistema no tenga hoy correo ni recuperación.
4. **El idioma es una preferencia del navegador**, no de la cuenta, porque tiene que valer
   también en el ingreso y en el registro.
5. **El ayudante vive en su propia pestaña** y es de sólo lectura.
6. **La IA es opcional**: sin clave, el ayudante contesta con su guía local y funciona sin
   red.

## 4. Requerimientos

### REQ-40 — Perfil de la cuenta

Cada cuenta con sesión ve en `/perfil` su nombre de usuario, su rol, su estado y su foto, y
puede poner o quitar la foto. **Criterio**: la foto se acepta sólo si sus primeros bytes son
de JPEG, PNG o WebP (nunca SVG, que puede llevar código), pesa como máximo 2 MB y se guarda
con un nombre que genera la aplicación. Se sirve con el tipo que la base declara, con
`nosniff` y con una política de contenido que impide ejecutar nada. Si el archivo no está en
la carpeta, la interfaz pinta la inicial y no una imagen rota.

### REQ-41 — Cambio de contraseña con aprobación

El usuario común pide el cambio desde su perfil; la solicitud queda **pendiente** y un
administrador la aprueba o la rechaza con un motivo. Mientras tanto, la contraseña vigente
sigue siendo la anterior. **Criterio**: se exige la contraseña actual, la nueva cumple el
mismo mínimo que el registro (`LARGO_MINIMO_DE_CONTRASENA`), no puede ser igual a la actual,
sólo hay una solicitud pendiente por cuenta, la nueva se guarda hasheada con `scrypt` y sal,
y la pantalla muestra el estado de la última solicitud. El administrador, que no tiene a
quién pedírselo, aplica la suya de inmediato.

### REQ-42 — Contactos

Cada usuario común tiene una agenda. **Criterio**: se agrega por nombre de usuario, sólo si
esa cuenta es un usuario común **aprobado** (o sea, tiene wallet), no puede ser la propia y
no se repite; quitar es idempotente (doble clic no es un error); la agenda nunca muestra
datos de otra cuenta más allá del nombre y del historial que el propio usuario ya puede ver.
La agenda no obliga a la otra persona a aceptar nada.

### REQ-43 — Idioma

La interfaz se ve en español o en inglés, a elección, por defecto en español. **Criterio**:
sin cookie se ve español; la elección sobrevive al cierre del navegador; el `lang` del
documento cambia; toda frase marcada en las plantillas tiene su entrada en el catálogo
inglés y una prueba lo exige; los mensajes que llegan armados desde el dominio o el servicio
se traducen por patrón y un texto libre (como el motivo de un rechazo) queda tal cual.

### REQ-44 — Ayudante con guía local

El ayudante explica qué está pasando sin conexión. **Criterio**: sin `ASISTENTE_API_KEY`
responde siempre con su guía; `/asistente/ahora` devuelve el estado de la cuenta en palabras
simples y las sugerencias de la página; un botón sugerido contesta el tema exacto sin gastar
una llamada; sin sesión no explica ni consulta nada (401 en las rutas de datos y redirección
al ingreso en la página); y no escribe ni mueve nada.

### REQ-45 — Ayudante con IA, opcional

Con `ASISTENTE_API_KEY` configurada, una pregunta **escrita a mano** se responde con el
servicio externo, con el contexto de la cuenta de la sesión. **Criterio**: la clave se lee
sólo del entorno, nunca se registra ni llega al navegador; el contexto se limita a la cuenta
de quien pregunta (para el administrador, sólo conteos); si el servicio falla, se contesta
con la guía local y la persona no ve un error técnico; y la página dice, antes de preguntar,
que la pregunta y el resumen de la cuenta salen hacia un servicio externo.

## 5. Límites que se declaran

- **Cambiar la contraseña no cierra las sesiones abiertas.** La cookie sólo lleva el
  identificador de la cuenta y no tiene versión; cerrar sesión en otro navegador exige
  esperar a que caduque la cookie (no es permanente y muere al cerrar el navegador).
- **La foto no es obligatoria y no hay recorte en el servidor**: el navegador ofrece el
  recorte y el servidor valida tipo y tamaño.
- **El ayudante no hace analítica todavía.** El módulo es el lugar donde va a vivir; hoy
  explica.
- **Con IA configurada, la pregunta y el resumen de la cuenta salen del equipo.** Sin clave,
  nada sale. La decisión es del operador que pone la clave, y la persona la ve en la página.
- **Un volumen anterior a estas funciones no tiene las tres tablas nuevas** y el proyecto no
  tiene migraciones: el arranque lo detecta y dice qué hacer (`down -v` y volver a sembrar).

## 6. Trazabilidad

| Requerimiento | Dónde se prueba                                                          |
| ------------- | ------------------------------------------------------------------------ |
| REQ-40        | `tests/integration/test_foto.py`, `test_perfil.py`                       |
| REQ-41        | `tests/integration/test_perfil.py`                                       |
| REQ-42        | `tests/integration/test_contactos.py`                                    |
| REQ-43        | `tests/integration/test_idioma.py`                                       |
| REQ-44        | `tests/integration/test_asistente.py`                                    |
| REQ-45        | `tests/integration/test_asistente.py`, `tests/unit/test_asistente_ia.py` |
