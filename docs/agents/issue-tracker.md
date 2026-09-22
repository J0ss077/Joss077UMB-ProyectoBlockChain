# Issue tracker: markdown local

Los issues y las specs de este repositorio viven como archivos markdown en `.scratch/`. `.scratch/` se versiona en git: es la fuente de verdad del trabajo planificado, no un directorio temporal.

## Convenciones

- Un feature por directorio: `.scratch/<feature-slug>/`.
- La spec es `.scratch/<feature-slug>/spec.md`.
- Los issues de implementación son un archivo por ticket en `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numerados desde `01`. Un archivo combinado con todos los tickets no es válido.
- El estado de triage se registra en una línea `Status:` cerca del inicio del archivo; ver `triage-labels.md` para los strings de rol.
- Los comentarios y el historial se anexan al final del archivo bajo el encabezado `## Comments`.

## Cuando un skill dice "publish to the issue tracker"

Crear un archivo nuevo bajo `.scratch/<feature-slug>/`, creando el directorio si hace falta.

## Cuando un skill dice "fetch the relevant ticket"

Leer el archivo en la ruta referenciada. Normalmente el usuario pasa la ruta o el número directamente.

## Operaciones de wayfinding

Las usa `/wayfinder`. El mapa es un archivo con un hijo por ticket.

- **Mapa**: `.scratch/<effort>/map.md`, con el cuerpo de notas, decisiones tomadas y niebla pendiente.
- **Ticket hijo**: `.scratch/<effort>/issues/NN-<slug>.md`, numerado desde `01`, con la pregunta en el cuerpo. Una línea `Type:` registra el tipo (`research`, `prototype`, `grilling` o `task`); una línea `Status:` registra `claimed` o `resolved`.
- **Bloqueo**: una línea `Blocked by: NN, NN` cerca del inicio. Un ticket está desbloqueado cuando todos los archivos que lista están en `resolved`.
- **Frontera**: recorrer `.scratch/<effort>/issues/` buscando archivos abiertos, desbloqueados y sin reclamar; gana el número más bajo.
- **Reclamar**: escribir `Status: claimed` y guardar antes de empezar el trabajo.
- **Resolver**: anexar la respuesta bajo el encabezado `## Answer`, escribir `Status: resolved`, y anexar un puntero de contexto a las decisiones tomadas en `map.md`.

## Idioma

La prosa va en español. Los tokens que los skills leen literalmente (`Status:`, `Type:`, `Blocked by:`, `## Answer`, `## Comments`, `claimed`, `resolved`) se mantienen en inglés tal como aparecen aquí.
