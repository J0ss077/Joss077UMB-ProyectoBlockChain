# Proceso de construcción y alcance

Cómo se llegó al prototipo que está en este repositorio, qué se entregó en cada etapa, y
qué queda explícitamente afuera. Es el complemento de
[arquitectura-y-decisiones.md](arquitectura-y-decisiones.md): acá está el recorrido, allá
están las decisiones.

## 1. Las etapas

| Etapa | Qué se entregó | Cómo se supo que estaba |
| --- | --- | --- |
| 1. Núcleo del dominio | `Wallet`, `Transaction`, `Block`, `Blockchain` y los estados; firma, validación y hash | Pruebas unitarias por requerimiento, sin base de datos (`REQ-17`) |
| 2. Persistencia | Esquema en `db/init.sql`, adaptadores PostgreSQL detrás de protocolos y unidad de trabajo atómica | Pruebas de integración contra PostgreSQL, incluida la atomicidad de la agrupación (`REQ-18`) |
| 3. Las cinco rutas | `POST /wallets`, `POST /transacciones`, `POST /bloques`, `GET /verificar` y `GET /historial/<wallet>` | Pruebas de rutas y guarda de que la presentación no toca el motor (`REQ-29`) |
| 4. Arranque y demostración | `python -m src.bootstrap`: génesis idempotente, datos del caso del eje y cuentas | El arranque se corre dos veces y no duplica nada |
| 5. Usuarios y roles | Registro moderado, aprobación, ingreso, sesión, perfil, contactos, foto y solicitudes de contraseña | Diez requerimientos nuevos, cada uno con su prueba |
| 6. Interfaz | Sistema de diseño «Bloques», tema claro y oscuro, navegación por rol, mensajes de éxito y de error | Capturas de todas las pantallas y pruebas de navegación |
| 7. Ayudante | Asistente que explica el sistema en palabras simples, con API externa y guía local de respaldo | Pruebas de que sólo consulta y de que nunca escribe |
| 8. Fase 4 | Estadísticas con filtros y gráficas, proyección del próximo mes con red neuronal, manejo del error de conexión y evidencias | 21 capturas, pruebas de navegación, de conexión y de la proyección |

El orden no fue casual: cada etapa se apoyó en la anterior y ninguna avanzó sin sus
pruebas. La etapa 5 es la única que agregó una tabla al modelo del eje (`users`), y lo hizo
sin tocar las tres originales.

## 2. Cómo se verifica

- **Las pruebas se llaman por requerimiento** (`test_req_NN_*`) y llevan el criterio de
  aceptación en el docstring: para explicar una regla alcanza con mostrar la prueba que la
  demuestra. Hoy son **350**.
- **Las guardas automáticas** sostienen la arquitectura: una falla si la presentación nombra
  el motor o la capa de datos, y otra si el dominio importa `psycopg`.
- **La herramienta de sabotaje** (`python -m src.sabotaje`) muestra en una sola corrida qué
  detecta la cadena y qué no, incluidos los límites declarados.
- **La prueba de coherencia** falla si el recorrido de casos de uso deja de nombrar un caso o
  un requerimiento.
- **El recorrido de demostración** (`docs/recorrido-de-casos-de-uso.md`) es el camino real de
  cada caso de uso: ruta, método del dominio, tabla y consulta.

## 3. Lo que no entra

Está declarado para que no se lea como olvido:

- Cambio de contraseña sin aprobación, baja o suspensión de usuarios, y bitácora de lo que
  hace el administrador.
- Correo electrónico, recuperación de contraseña, verificación por correo y doble factor.
- Que la persona custodie su llave privada, o varias wallets por usuario.
- Protección CSRF y límite de intentos de ingreso.
- Migraciones de esquema.
- Nodos pares, consenso, minado o cualquier forma de red.

## 4. Riesgos conocidos

| Riesgo | Qué se hizo |
| --- | --- |
| El clúster del equipo es PostgreSQL 18 y el destino es 16 | El esquema se validó contra 16 en contenedor: `uuid-ossp`, `CHAR(64)`, los CHECK con expresiones regulares y `NUMERIC(18,8)` se comportan igual |
| La explicación se separa del código | Los docstrings viven junto al código, las pruebas se llaman por requerimiento y la prueba de coherencia falla si el recorrido pierde un caso |
| La cadena crece con cada aprobación (un bloque por saldo de bienvenida) | Se midió la verificación: 1,4 ms con 4 bloques y 84 ms con 1.000 |
| La proyección se apoya en una serie sintética | Se declara en la tarjeta de la página y en `docs/red-neuronal.md`; con historial real se reentrena |

## 5. Por dónde empezar a leer

1. `README.md`: qué es, cómo se instala y cómo se corre.
2. `docs/arquitectura-y-decisiones.md`: las capas y por qué cada decisión.
3. `db/init.sql`: el esquema completo, con sus CHECK e índices.
4. `docs/recorrido-de-casos-de-uso.md`: el camino de cada caso de uso.
5. `src/domain/`: las reglas, que es donde está lo interesante del proyecto.
6. `tests/`: la explicación ejecutable, requerimiento por requerimiento.
7. `docs/red-neuronal.md` y `docs/presupuesto-y-cronograma.md`: la red de la proyección y
   los números del proyecto.
