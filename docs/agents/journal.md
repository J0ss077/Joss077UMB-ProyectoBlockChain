# Historial de acciones

Registro de lo que cada agente hace en el repositorio. No es documentación del proyecto: es la trazabilidad de los cambios.

## Dónde

Los registros viven en `.scratch/journal/`, un archivo por sesión de trabajo, versionado en git.

El nombre es `AAAA-MM-DD-HHMM-<slug>.md`: la fecha y la hora de inicio, más un slug corto en kebab-case que describa la sesión. Por ejemplo, `2026-09-21-2030-backend-crud.md`.

## Cuándo se abre un archivo nuevo

Al empezar a trabajar se mira el archivo más reciente de `.scratch/journal/` y se decide entre anexar o crear uno nuevo.

Se **anexa** si su última entrada es de hace menos de dos horas y la sesión sigue siendo la misma.

Se **crea un archivo nuevo** en cualquier otro caso, y siempre que ocurra alguna de estas tres cosas:

- El usuario pide cerrar la sesión.
- Otro agente toma el relevo.
- Pasaron más de dos horas desde la última entrada.

Las entradas ya escritas no se editan. Si algo hay que corregir, se anota una entrada nueva que lo diga.

## Qué se registra

Solo acciones con efecto sobre el repositorio o sobre el entorno:

- Archivos creados, modificados o borrados.
- Comandos que cambian algo: instalaciones, operaciones sobre la base, commits.
- Las decisiones que se tomaron y por qué, con enlace al ADR cuando corresponda.

Las lecturas, las búsquedas y la exploración no se registran.

## Formato de cada entrada

```markdown
### AAAA-MM-DD HH:MM. Título corto

- **Tarea**: qué se pidió.
- **Acciones**: archivos y comandos, uno por línea.
- **Decisiones**: qué se decidió y por qué. Enlace al ADR si aplica.
- **Verificación**: qué se comprobó de verdad y qué quedó sin comprobar.
- **Pendiente**: qué queda abierto.
```

Los campos que no apliquen se omiten. Un campo vacío no aporta nada.

## Promoción de pendientes

El historial dice qué pasó; el tracker dice qué falta. Un pendiente que solo vive en una entrada del historial se pierde, porque nadie lee el historial completo para buscarlo.

Por eso, antes de cerrar una entrada, todo lo que quede pendiente y sea accionable se registra además como ticket en `.scratch/`, con su `Status:`. El campo `Pendiente` de la entrada puede referenciar el ticket en lugar de describirlo.

## Idioma

La prosa va en español. Los nombres de archivo, de comando y de tabla se escriben tal cual, sin traducir.
