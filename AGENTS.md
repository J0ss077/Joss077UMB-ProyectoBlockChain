# AGENTS.md

Prototipo de sistema transaccional basado en blockchain, de nodo único, en Python y PostgreSQL. El glosario del dominio está en `CONTEXT.md`; las decisiones cerradas, en `docs/adr/`.

## Estado del proyecto y regla de confirmación

Este repositorio está en construcción activa y su contenido cambia de forma drástica y frecuente. La estructura de carpetas, el modelo de dominio, las decisiones de diseño y el alcance pueden reescribirse sin aviso previo, así que nada de lo que hay acá debe tratarse como definitivo.

Por eso, todo cambio se confirma con los desarrolladores antes de aplicarse. La confirmación cubre crear, borrar y reescribir archivos; tocar `database/`, la configuración del entorno o las convenciones de trabajo; y cualquier decisión que afecte al alcance, al modelo de dominio o a la arquitectura.

Cuando una instrucción sea ambigua, cuando falte información o cuando el trabajo implique una decisión que el repositorio no haya cerrado, la conducta esperada es preguntar y esperar respuesta. Si la decisión parece obvia, conviene confirmarla igual: preguntar cuesta menos que rehacer el trabajo.

Para dejar constancia de una propuesta, se escribe un ADR en `docs/adr/` con estado `propuesto` y se pide la revisión.

Antes de actuar, conviene comprobar que la documentación sigue siendo cierta. Puede haber quedado desactualizada respecto del estado real del proyecto, y en ese caso la discrepancia se reporta en lugar de resolverse por interpretación.

## Agent skills

### Issue tracker

Los issues viven como markdown local en `.scratch/<feature>/`. Ver `docs/agents/issue-tracker.md`.

### Triage labels

Vocabulario por defecto de cinco roles; el string de cada rol es su propio nombre. Ver `docs/agents/triage-labels.md`.

### Domain docs

Layout single-context: `CONTEXT.md` en la raíz y ADRs en `docs/adr/`. Ver `docs/agents/domain.md`.

### Action journal

Cada sesión de trabajo deja su propio registro en `.scratch/journal/`. Ver `docs/agents/journal.md`.

## Mapa de documentos

| Documento                  | Cuándo leerlo                                                           |
| -------------------------- | ----------------------------------------------------------------------- |
| `.scratch/`                | Al empezar una sesión: los tickets abiertos son el trabajo pendiente.   |
| `CONTEXT.md`               | Antes de nombrar un concepto del dominio en un issue, un test o un ADR. |
| `docs/arquitectura.md`     | Al tocar capas, modelo de datos o el encadenamiento por hash.           |
| `docs/base-de-datos.md`    | Al trabajar con esquema, seed, índices o constraints.                   |
| `docs/puesta-en-marcha.md` | Al levantar el entorno o depurar el contenedor.                         |
| `docs/adr/`                | Antes de contradecir una decisión previa.                               |
| `docs/referencias.md`      | Al citar una fuente o al buscar los diagramas UML del proyecto.         |

## Convenciones del repositorio

- Al empezar una sesión de trabajo se revisan los tickets abiertos en `.scratch/`, y el trabajo sale de ahí en lugar de la memoria. Lo que quede pendiente al terminar se registra como ticket, no solo en el historial.
- Todo el trabajo ocurre dentro de este directorio: ninguna ruta de escritura sale de aquí.
- La documentación se escribe en español, con cada párrafo en una sola línea continua y sin emojis. El código, los nombres de archivo y los tokens que otros skills leen literalmente van en inglés.
- `database/` es la fuente de verdad del esquema y su estructura está congelada: no se agregan ni se modifican tablas, columnas, constraints ni índices. `01_schema.sql` y `02_seed.sql` ya están aplicados, y cualquier cambio en ese directorio requiere confirmación explícita de los desarrolladores.
- El backend vive en `src/`, y la persistencia queda aislada detrás de los protocolos de `src/persistence/ports.py`. Cómo levantarlo y cómo operarlo a mano está en `docs/puesta-en-marcha.md`.
- Antes de terminar una sesión de trabajo, el registro de `.scratch/journal/` queda escrito con lo que se hizo.
- `.env` no se versiona. Toda variable nueva se refleja también en `.env.example`.
- Los scripts de `database/init/` solo se ejecutan cuando se crea el volumen. `docs/puesta-en-marcha.md` describe el reinicio limpio y cómo verificar el resultado.
