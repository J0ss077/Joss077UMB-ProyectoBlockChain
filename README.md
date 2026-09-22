# Sistema Transaccional Basado en Blockchain

Diseño y prototipo de un sistema transaccional que valida e integra transacciones sin depender de una autoridad central, aplicado al registro de aportes y retiros de una organización del sector solidario.

## Resumen

Los sistemas transaccionales tradicionales confían la validación de cada operación a una entidad central, lo que crea un punto único de fallo. Este proyecto propone una arquitectura alternativa basada en blockchain: wallets con par de llaves, transacciones firmadas, validación automática y bloques enlazados por hash, todo corriendo en un solo nodo local.

El caso de aplicación son los fondos de empleados y asociaciones mutuales, donde el registro de los aportes de los asociados suele recaer en una sola figura y no existe un mecanismo independiente para comprobar el historial. El sistema no reemplaza a esa figura: hace que su palabra deje de ser la única garantía, porque vuelve detectable cualquier alteración.

No es una red blockchain de producción. Es un prototipo que aísla los mecanismos de integridad —hash encadenado, validación automática, evidencia de manipulación— antes de escalar a un sistema distribuido.

## Estado

| Entregable                | Estado                                |
| ------------------------- | ------------------------------------- |
| Diseño de la arquitectura | documentado en `docs/arquitectura.md` |
| Persistencia PostgreSQL   | esquema, seed y contenedor listos     |
| Backend Python            | no iniciado                           |

Hoy el repositorio contiene la base de datos, su documentación y las decisiones de arquitectura. Todavía no hay código de aplicación, y por lo tanto tampoco hay tests ni dependencias que instalar.

## Inicio rápido

```bash
cp .env.example .env
make up        # equivalente a: docker compose up -d
make counts    # verifica que esquema y seed se aplicaron
```

Los requisitos, el resto de los comandos y los problemas conocidos están en [docs/puesta-en-marcha.md](docs/puesta-en-marcha.md).

## Documentación

El índice completo está en [docs/README.md](docs/README.md). Los documentos principales:

- [Arquitectura](docs/arquitectura.md): tipo de arquitectura, componentes, comunicación y límites.
- [Base de datos](docs/base-de-datos.md): tablas, constraints, índices y datos de prueba.
- [Decisiones](docs/adr/README.md): los ADR del proyecto.
- [Referencias](docs/referencias.md): fuentes y artefactos que viven fuera del repositorio.

El vocabulario del dominio está en [CONTEXT.md](CONTEXT.md) y las convenciones de trabajo del repositorio en [AGENTS.md](AGENTS.md).

## Stack

| Componente        | Elección                           |
| ----------------- | ---------------------------------- |
| Persistencia      | PostgreSQL 16 sobre Docker Compose |
| Lenguaje previsto | Python 3.11 o superior             |
| Encadenamiento    | SHA-256 de `hashlib`               |
| Firma             | ECDSA                              |
| Pruebas           | `pytest`                           |

## Estructura del repositorio

```
├── database/init/      # esquema y seed: la fuente de verdad de la base
├── docs/               # arquitectura, base de datos y ADR
├── .scratch/           # tracker de issues local
├── docker-compose.yml
├── Makefile
├── CONTEXT.md          # glosario del dominio
└── AGENTS.md           # convenciones de trabajo del repositorio
```

## Alcance

Lo que el prototipo implementa:

- Encadenamiento criptográfico por hash, que localiza el punto exacto de una alteración.
- Evidencia de manipulación: el sistema no impide alterar un registro, pero garantiza que la alteración sea detectable.
- Autenticación de origen mediante firma digital con ECDSA.
- Validación automática por reglas de firma, saldo y formato, antes de que la transacción entre al pool.

Lo que queda fuera, y que conviene tener presente porque son las limitaciones reales del prototipo:

- Consenso distribuido, red P2P y descentralización.
- Resistencia a la manipulación: quien controla el nodo puede recalcular la cadena completa.
- Inmutabilidad garantizada. El proyecto va hacia inmutabilidad verificable.
- Wallet no custodial: el nodo guarda el material cifrado de todas las llaves privadas.
- Validación legal y valor real de los montos.

El detalle está en [docs/arquitectura.md](docs/arquitectura.md), y las razones del recorte en el [ADR-0001](docs/adr/0001-nodo-unico-sin-consenso-distribuido.md).

## Autores

- José Camilo Pérez Daza
- Sebastián Fernando Revelo Meneses
- Tomás Alejandro Santiago Reyes

## Licencia

GNU General Public License v3.0. Ver [LICENSE](LICENSE).
