# .scratch

Tracker de issues local del proyecto. La convención completa, incluidos los tokens que los skills leen literalmente, está en `../docs/agents/issue-tracker.md`.

## Estructura

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

Este directorio se versiona: los tickets son parte del registro del proyecto, no archivos temporales. Todavía no hay ningún feature abierto.
