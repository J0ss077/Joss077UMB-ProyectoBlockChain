# Convenciones del proyecto

Instrucciones para cualquiera que trabaje en este repositorio, sea una persona o un agente.

## Reparto del trabajo

- **Funcionalidad y lógica**: dominio, persistencia, rutas, servicios, pruebas y documentos técnicos.
- **Diseño de interfaces**: lo lleva un integrante del equipo. Un cambio de funcionalidad no debe alterar decisiones visuales —paleta, tipografías, disposición— sin coordinarlo. El sistema de diseño está en `docs/sistema-de-diseno.md`.

## Registro de la escritura

- Documentos, comentarios y docstrings: **impersonal** («se registra», «la wallet queda»).
- Interfaz, mensajes de error y dictámenes: **tuteo** («Tienes», «Abre», «Tu wallet»). El proyecto es colombiano: nada de voseo ni de usted.
- Sin emojis en prosa ni en comentarios; el `✓` de la interfaz es un glifo funcional.
- Mensajes de commit en español y con tildes.

## Cómo se verifica

```bash
.venv/bin/ruff check .                              # limpio
.venv/bin/pytest tests -q                           # la suite completa
env -u DATABASE_URL .venv/bin/pytest tests/unit -q   # las que no necesitan base
```

La suite con base necesita `DATABASE_URL`, `SESSION_SECRET` y `ADMIN_PASSWORD` en el entorno. La base de desarrollo vive en el puerto 55432; las pruebas de integración no deben usarla: con `TEST_DATABASE_URL` apuntan a otra base y no la tocan. Las pruebas vacían las tablas en cada caso, así que una base desechable es lo correcto.

**No sobrescribir `.env`**: lleva la `MASTER_KEY` con la que están cifradas las llaves de las wallets sembradas, y sin ella esas wallets quedan ilegibles.

Las fotos de perfil son archivos en `FOTOS_DIR` (por defecto `datos/fotos/`, que git ignora) y la base sólo guarda la referencia: el respaldo son la base **y** la carpeta.

## Documentos

- `docs/superpowers/specs/`: los diseños, uno por función.
- `docs/superpowers/plans/`: los planes de implementación. La convención del proceso exige que vivan bajo `docs/superpowers/`.
- `README.md`: cómo se levanta, se apaga y se limpia el proyecto.

Si además existe la carpeta local `.superpowers/` —no se versiona—, ahí están el registro de ejecución con las decisiones y el porqué de cada una, y los reportes de cada tarea: es lo primero que conviene leer al retomar.
