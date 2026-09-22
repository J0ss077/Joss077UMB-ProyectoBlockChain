# ADR-0003: Estructura del repositorio y documentación

- **Estado**: aceptado
- **Fecha**: 2026-09-21

## Contexto

El repositorio llegó con el contenido crudo: dos README que se pisaban, un `__.gitignore` que git nunca leyó (git solo reconoce el nombre exacto `.gitignore`), la documentación de la Fase 2 viviendo en un archivo llamado `__README.md`, y ninguna carpeta donde registrar decisiones ni glosario.

## Decisión

La documentación se separa por función, con una sola fuente de verdad por tema:

- `README.md` en la raíz: qué es el proyecto, stack, quickstart e índice. Es una puerta de entrada, no el detalle.
- `docs/`: el detalle, en `arquitectura.md`, `base-de-datos.md`, `puesta-en-marcha.md` y `referencias.md`.
- `docs/adr/`: las decisiones difíciles de revertir, numeradas.
- `docs/agents/`: la configuración interna del repositorio: tracker de issues, etiquetas y documentación de dominio.
- `CONTEXT.md` en la raíz: el glosario del dominio.
- `.scratch/`: el tracker de issues local, versionado. Un directorio por feature, con una spec y un archivo por ticket.
- `database/`: la fuente de verdad del esquema.
- `Makefile`: las operaciones del entorno, hoy solo de base de datos.

El layout es single-context: un solo `CONTEXT.md` y un solo `docs/adr/`, sin `CONTEXT-MAP.md`.

## Consecuencias

- Un tema se documenta en un solo archivo. El README no repite lo que ya está en `docs/`.
- Los documentos de entrega de cada fase no se versionan acá: se manejan por fuera del repositorio. Lo que tengan de permanente se incorpora a `docs/`.
- La configuración interna del repositorio vive apartada del resto de la documentación, así que cambiar el tracker o el layout no obliga a reescribir los documentos del proyecto.
- Los archivos del tracker usan un conjunto fijo de palabras clave en inglés (`Status:`, `Type:`, `Blocked by:`) para que su lectura sea mecánica y no dependa de cómo redacte cada autor.
- Todavía no existe paquete de Python, ni `pyproject.toml`, ni carpeta de tests. Se añadirán cuando la fase de backend los necesite, para no fijar interfaces antes de tener el diseño.

## Alternativas consideradas

- **Mantener un solo README largo**: descartado. Quien busca el esquema de la base no debería atravesar la visión del proyecto para encontrarlo.
- **Tracker en GitHub Issues**: descartado por preferencia del equipo. El tracker local mantiene los tickets dentro del repositorio y del alcance de la entrega.
