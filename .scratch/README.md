# .scratch

Área de trabajo de los agentes. Contiene dos cosas: el tracker de issues y el historial de acciones.

## Tracker de issues

La convención completa, incluidos los tokens que los skills leen literalmente, está en `../docs/agents/issue-tracker.md`.

```
.scratch/
└── <feature-slug>/
    ├── spec.md
    └── issues/
        ├── 01-<slug>.md
        └── 02-<slug>.md
```

- Un directorio por feature, en kebab-case.
- `spec.md` describe el feature.
- Un archivo por ticket dentro de `issues/`, numerado desde `01`. Nunca un archivo combinado con todos los tickets.
- Cada ticket lleva una línea `Status:` cerca del inicio y el historial al final, bajo `## Comments`.

## Historial de acciones

La convención está en `../docs/agents/journal.md`.

```
.scratch/journal/
└── AAAA-MM-DD-HHMM-<slug>.md
```

Un archivo por sesión de trabajo. Se anexa mientras la sesión sigue viva y se crea uno nuevo si pasaron más de dos horas desde la última entrada, si el usuario cierra la sesión o si otro agente toma el relevo.

## Versionado

Este directorio se versiona: tanto los tickets como el historial son parte del registro del proyecto, no archivos temporales. Tampoco deben aparecer en la documentación del proyecto ni en el material de entrega.
