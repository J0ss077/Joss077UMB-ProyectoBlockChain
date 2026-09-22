# Etiquetas de triage

Los skills hablan en términos de cinco roles canónicos de triage. Este archivo mapea cada rol al string que se usa realmente en el tracker de este repositorio.

| Rol               | String en este repositorio | Significado                                                  |
| ----------------- | -------------------------- | ------------------------------------------------------------ |
| `needs-triage`    | `needs-triage`             | Falta que alguien evalúe el issue                            |
| `needs-info`      | `needs-info`               | Se espera información adicional de quien reportó             |
| `ready-for-agent` | `ready-for-agent`          | Completamente especificado, listo para un agente desatendido |
| `ready-for-human` | `ready-for-human`          | Requiere implementación humana                               |
| `wontfix`         | `wontfix`                  | No se va a atender                                           |

Cuando un skill mencione un rol, hay que usar el string correspondiente de esta tabla.

En el tracker local el rol se escribe en la línea `Status:` del archivo del ticket, no como etiqueta de una plataforma externa. Ver `issue-tracker.md`.
