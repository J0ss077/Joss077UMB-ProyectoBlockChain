# Puesta en marcha

Cómo levantar el entorno local y verificar que quedó bien. El modelo de datos está en `base-de-datos.md`; la estructura del código en `arquitectura.md`.

## Requisitos

- Docker y Docker Compose. En esta máquina el binario `docker` es un alias a `podman`.
- `make`, para los atajos del `Makefile`. Todos los comandos tienen su equivalente directo de Docker Compose, así que `make` es opcional.
- Cliente `psql` solo si se quiere conectar desde el anfitrión. El contenedor ya trae uno.

No hace falta Python para nada de lo que existe hoy: todavía no hay código de aplicación.

## Configuración

```bash
cp .env.example .env
```

`.env` no se versiona. Si se cambia el usuario, la contraseña, el nombre de la base o el puerto, hay que hacerlo en ese archivo. Cualquier variable nueva se refleja también en `.env.example`, que sí es la plantilla de referencia del repositorio.

## Levantar la base

```bash
make up
# Equivalente: docker compose up -d
```

Postgres inicializa el volumen la primera vez y ejecuta en orden los scripts montados desde `database/init/`:

1. `01_schema.sql`, que crea la extensión `uuid-ossp` y las tablas.
2. `02_seed.sql`, que inserta los datos de prueba.

## Verificar

```bash
make tables   # lista las tablas
make schema   # describe wallets, blocks y transactions
make counts   # cuenta las filas de las tres tablas
make psql     # abre una sesión interactiva
```

Los mismos comandos, sin `make`:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"

docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT
     (SELECT count(*) FROM wallets) AS wallets,
     (SELECT count(*) FROM blocks) AS blocks,
     (SELECT count(*) FROM transactions) AS transactions;"
```

Con el seed aplicado, el conteo debe dar tres wallets, dos bloques y tres transacciones.

Desde el anfitrión, si hay `psql` instalado y las variables del `.env` están cargadas en la sesión:

```bash
set -a && . ./.env && set +a
psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
```

## Detener y reiniciar

```bash
make down    # detiene el contenedor conservando los datos
make logs    # sigue los logs del contenedor
make reset   # destruye el volumen y vuelve a aplicar esquema y seed
```

`make reset` es la única forma de que los scripts de `database/init/` se vuelvan a ejecutar, porque el contenedor solo los corre al crear el volumen. Equivale a `docker compose down -v` seguido de `docker compose up -d`.

## Problemas conocidos

- **La base no tiene las tablas**: el volumen ya existía de un intento anterior y los scripts de init no se volvieron a ejecutar. `make reset` lo resuelve.
- **El puerto está ocupado**: cambiar `POSTGRES_PORT` en `.env`. El contenedor siempre escucha en 5432 internamente; esa variable solo mueve el puerto publicado en el anfitrión.
- **`docker compose` falla al arrancar el motor de contenedores**: como `docker` es un alias a `podman` sin demonio, un fallo de configuración de podman aparece como un fallo de Docker. `podman info` muestra la causa real.

## Alcance de esta etapa

No hay backend, ni CRUD, ni conexión desde una aplicación: solo el contenedor y el SQL. Las siguientes fases añaden el código Python descrito en `arquitectura.md`.
