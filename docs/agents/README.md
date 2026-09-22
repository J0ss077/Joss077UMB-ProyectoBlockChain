# Configuración para agentes

Estos cuatro archivos son la configuración que leen los skills de ingeniería al trabajar en este repositorio. No son documentación del proyecto: son el contrato con las herramientas.

| Archivo                              | Qué define                                                   |
| ------------------------------------ | ------------------------------------------------------------ |
| [issue-tracker.md](issue-tracker.md) | Dónde viven los issues, con qué estructura y con qué tokens. |
| [triage-labels.md](triage-labels.md) | El string real de cada uno de los cinco roles de triage.     |
| [domain.md](domain.md)               | Dónde están `CONTEXT.md` y los ADR, y cómo consumirlos.      |
| [journal.md](journal.md)             | Dónde y cómo se registra lo que cada agente hace.            |

El resumen de una línea de cada uno vive en el bloque `## Agent skills` de `AGENTS.md`, que es el punto de entrada. Si se cambia el tracker o el layout de documentación, se editan estos archivos y ese bloque; no hace falta reconfigurar desde cero.

Los tokens que los skills parsean literalmente (`Status:`, `Type:`, `Blocked by:`, `## Answer`, `## Comments`, `claimed`, `resolved`) se mantienen en inglés aunque la prosa esté en español. Traducirlos rompe la lectura automática.
