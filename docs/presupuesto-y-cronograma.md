# Presupuesto del proyecto

El presupuesto se estimó sobre el alcance del prototipo y su proyección a futuro. Casi
todas las herramientas que se usan son de código abierto o de uso gratuito, así que no
hay licenciamiento que pagar: el presupuesto general suma **solo lo que el equipo
desembolsa** —servicios, materiales de impresión y un margen de imprevistos— y deja
aparte el trabajo de las personas, que es propio y no se factura.

La tarifa de referencia para valorar ese trabajo es **$10.000 por hora**. Es una tarifa
de desarrollo junior en el mercado local, sin prestaciones ni cargas parafiscales, porque
el trabajo es académico y no hay relación laboral. La misma tarifa se usa en la
planeación y en la valoración del tiempo del equipo, para que las dos cifras sean
comparables.

## Presupuesto general

| Etapa | Costo (COP) | Descripción |
| --- | --- | --- |
| Planeación | $250.000 | Horas de trabajo del equipo (25 h × $10.000) |
| Diseño | $0 | Herramientas de código abierto: draw.io, PlantUML y LibreOffice |
| Desarrollo / ejecución | $120.000 | Internet y energía eléctrica del equipo, proporcional al proyecto |
| Pruebas / validación | $0 | pytest y PostgreSQL, software libre |
| Implementación | $0 | Despliegue local con Docker Compose |
| Cierre | $39.091 | Impresión de la documentación, copias y anillado |
| Subtotal | $409.091 | |
| Imprevistos (10 %) | $40.909 | |
| Total | **$450.000** | |

*Nota. Valores en pesos colombianos (COP). El detalle por actividad está más abajo.*

## Recursos humanos y tiempo de desarrollo

El equipo son tres integrantes que trabajaron en paralelo durante las diez semanas del
proyecto. Ese tiempo **no se cobra**, pero se declara porque es el recurso principal del
proyecto y la guía pide estimarlo. La dedicación es una estimación de trabajo efectivo
—reuniones, desarrollo, pruebas y documentación— y no incluye el tiempo de espera entre
entregas.

| Integrante | Rol en el proyecto | Dedicación estimada | Horas | Valor a $10.000/h |
| --- | --- | --- | --- | --- |
| José Camilo Pérez Daza | Dominio, persistencia, pruebas y despliegue | 12 h/semana × 11 semanas | 132 | $1.320.000 |
| Sebastián Fernando Revelo Meneses | Interfaz, sistema de diseño y asistente | 12 h/semana × 11 semanas | 132 | $1.320.000 |
| Tomas Alejandro Santiago Reyes | Requerimientos, documentación y evidencias | 12 h/semana × 11 semanas | 132 | $1.320.000 |
| **Total** | | | **396** | **$3.960.000** |

*Nota. Ese valor es el costo de referencia del trabajo propio: no se desembolsa y por eso
no entra en el total del presupuesto general. Las 25 horas de planeación que sí aparecen
en la tabla anterior son parte de estas 396 y se cobraron como costo de oportunidad del
equipo.*

## Presupuesto detallado

| Etapa | Actividad / recurso | Tipo | Cant. | Valor unitario (COP) | Total (COP) |
| --- | --- | --- | --- | --- | --- |
| Planeación | Reunión de definición de alcance y requisitos (3 integrantes × 2 h) | Personal | 6 | $10.000 | $60.000 |
| Planeación | Elaboración de cronograma, ficha técnica y presupuesto | Personal | 4 | $10.000 | $40.000 |
| Planeación | Investigación de requisitos y tecnologías blockchain (3 integrantes × 3 h) | Personal | 9 | $10.000 | $90.000 |
| Planeación | Reuniones de seguimiento del plan (3 integrantes × 2 h) | Personal | 6 | $10.000 | $60.000 |
| Planeación | Gestión de tareas en GitHub Projects | Software | 1 | $0 | $0 |
| Diseño | Diagramas de arquitectura y modelo de datos (draw.io / PlantUML) | Software | 1 | $0 | $0 |
| Diseño | Documentación técnica (LibreOffice) | Software | 1 | $0 | $0 |
| Desarrollo / ejecución | Backend en Python (Flask, hashlib, psycopg) | Software | 1 | $0 | $0 |
| Desarrollo / ejecución | Base de datos PostgreSQL en contenedor Docker | Software | 1 | $0 | $0 |
| Desarrollo / ejecución | Control de versiones Git + repositorio GitHub | Software | 1 | $0 | $0 |
| Desarrollo / ejecución | Computadores personales del equipo | Equipos | 3 | $0 | $0 |
| Desarrollo / ejecución | Conexión a internet (proporcional al proyecto) | Servicios | 1 | $30.000 | $30.000 |
| Desarrollo / ejecución | Energía eléctrica de los equipos (proporcional, por integrante) | Servicios | 3 | $30.000 | $90.000 |
| Desarrollo / ejecución | Uso de la API del asistente de IA (DeepSeek) | Servicios | 1 | $0 | $0 |
| Pruebas / validación | Pruebas unitarias e integración (pytest) | Software | 1 | $0 | $0 |
| Pruebas / validación | Pruebas de API y transacciones (curl / Bruno) | Software | 1 | $0 | $0 |
| Implementación | Despliegue local con Docker Compose | Software | 1 | $0 | $0 |
| Cierre | Impresión de documentación final (3 juegos, uno por integrante) | Materiales | 3 | $10.000 | $30.000 |
| Cierre | Copias y anillado de entregables y presentación | Materiales | 1 | $9.091 | $9.091 |
| **Subtotal** | | | | | **$409.091** |
| **Imprevistos (10 %)** | | | | | **$40.909** |
| **Total** | | | | | **$450.000** |

*Nota. Los recursos con valor $0 son software de código abierto, planes gratuitos o
equipos propios del equipo. La API del asistente funciona con la cuenta gratuita del
equipo y, sin clave, el ayudante responde con su guía local: no es un costo obligatorio
para ejecutar el prototipo. Elaboración propia, Elaboración propia.*

# Cronograma

El cronograma cubre las diez semanas del proyecto, desde el 10 de septiembre de 2026
—cuando se presentó la propuesta de la idea con la ficha técnica profesional— hasta el
19 de noviembre, fecha prevista de entrega y sustentación. Las actividades están
agrupadas en seis etapas: planeación, diseño, desarrollo, pruebas, implementación y
cierre.

**Estado al 4 de noviembre de 2026.** Las actividades 1 a 23 están cerradas, incluida la
red neuronal (modelado, implementación e integración) y las tres de la Fase 4 que pedía
el repositorio. Quedan pendientes el merge de las ramas a `main` (24), los ajustes
finales del documento (26) y la entrega con la sustentación (27). El corte coincide con
lo desarrollado hasta hoy; las fechas de la columna «Fin» son las planificadas y varias
actividades terminaron antes.

## Cronograma general

| ID | Etapa | Actividad | Responsable | Inicio | Fin | Días | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Planeación | Propuesta de la idea y ficha técnica profesional | Equipo | 10/09/2026 | 10/09/2026 | 1 | Completada |
| 2 | Planeación | Problemática, contexto, objetivos, justificación y alcance | Equipo | 11/09/2026 | 24/09/2026 | 14 | Completada |
| 3 | Diseño | Requerimientos funcionales y no funcionales y matriz de trazabilidad | Equipo | 21/09/2026 | 02/10/2026 | 12 | Completada |
| 4 | Diseño | Marco conceptual y contextual | Equipo | 25/09/2026 | 05/10/2026 | 11 | Completada |
| 5 | Diseño | Arquitectura en capas y diagramas UML | Equipo | 01/10/2026 | 09/10/2026 | 9 | Completada |
| 6 | Diseño | Especificación de diseño y plan de implementación en 11 tareas | José Pérez | 10/10/2026 | 10/10/2026 | 1 | Completada |
| 7 | Desarrollo / ejecución | Prototipo base: dominio, persistencia PostgreSQL y aplicación Flask con las cinco rutas | José Pérez | 10/10/2026 | 10/10/2026 | 1 | Completada |
| 8 | Pruebas / validación | Suite de pruebas (pytest) y sabotaje guiado que demuestra la detección de alteraciones | José Pérez | 10/10/2026 | 16/10/2026 | 7 | Completada |
| 9 | Diseño | Marco integrador: asistente IA con API de DeepSeek | Equipo | 14/10/2026 | 17/10/2026 | 4 | Completada |
| 10 | Desarrollo / ejecución | Usuarios y roles: diseño, credenciales scrypt, sesión y aprobación | José Pérez | 16/10/2026 | 17/10/2026 | 2 | Completada |
| 11 | Desarrollo / ejecución | Rediseño de la interfaz con tema claro y oscuro y sistema de diseño | Sebastián Revelo | 17/10/2026 | 18/10/2026 | 2 | Completada |
| 12 | Diseño | Entrega documentación V1 (Arquitectura de Software) | Equipo | 18/10/2026 | 18/10/2026 | 1 | Completada |
| 13 | Desarrollo / ejecución | Perfil, contactos, foto, idioma y textos simples para el usuario común | Sebastián Revelo | 19/10/2026 | 19/10/2026 | 1 | Completada |
| 14 | Planeación | Estado del arte del documento | Tomás Santiago | 22/10/2026 | 22/10/2026 | 1 | Completada |
| 15 | Desarrollo / ejecución | Asistente IA que explica el sistema en palabras simples | Sebastián Revelo | 22/10/2026 | 22/10/2026 | 1 | Completada |
| 16 | Desarrollo / ejecución | Pestaña de ayudante que reemplaza al asistente flotante | Tomás Santiago | 29/10/2026 | 29/10/2026 | 1 | Completada |
| 17 | Planeación | Presupuesto y cronograma del proyecto | Sebastián Revelo | 29/10/2026 | 30/10/2026 | 2 | Completada |
| 18 | Diseño | Modelado de la red neuronal simple en el documento: propósito, entradas y salida, capas y funcionamiento | Equipo | 30/10/2026 | 04/11/2026 | 6 | Completada |
| 19 | Desarrollo / ejecución | Implementación de la red neuronal en el código con datos de prueba | Equipo | 02/11/2026 | 04/11/2026 | 3 | Completada |
| 20 | Pruebas / validación | Integración de la red neuronal con la interfaz y pruebas | Equipo | 04/11/2026 | 04/11/2026 | 1 | Completada |
| 21 | Desarrollo / ejecución | Fase 4: diseño uniforme de la interfaz y mensajes claros de éxito y error | Sebastián Revelo | 02/11/2026 | 04/11/2026 | 3 | Completada |
| 22 | Desarrollo / ejecución | Fase 4: menú principal y navegación entre módulos | Sebastián Revelo | 04/11/2026 | 04/11/2026 | 1 | Completada |
| 23 | Desarrollo / ejecución | Fase 4: conexión a la base de datos, validación previa y manejo de errores | José Pérez | 04/11/2026 | 04/11/2026 | 1 | Completada |
| 24 | Implementación | Fase 4: integración de la rama de la Fase 4 a main y publicación del repositorio | Equipo | 05/11/2026 | 07/11/2026 | 3 | Pendiente |
| 25 | Cierre | Fase 4: evidencias (capturas, consulta y registro en BD, cambios y dificultades) y entrega | Tomás Santiago | 04/11/2026 | 04/11/2026 | 1 | Completada |
| 26 | Cierre | Ajustes del documento final (estado del arte, red neuronal, presupuesto, cronograma y conclusiones) | Equipo | 12/11/2026 | 17/11/2026 | 6 | Pendiente |
| 27 | Cierre | Entrega final y sustentación del proyecto | Equipo | 19/11/2026 | 19/11/2026 | 1 | Pendiente |

*Nota. Las actividades 19 a 25 se cerraron al 4 de noviembre, antes de su fecha
planificada, porque el trabajo se adelantó para llegar a la entrega de la Fase 4 con la
red neuronal ya integrada. Elaboración propia.*

## Vista semanal

| Actividad | S1 10/09 | S2 17/09 | S3 24/09 | S4 01/10 | S5 08/10 | S6 15/10 | S7 22/10 | S8 29/10 | S9 05/11 | S10 12/11 | S11 19/11 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Propuesta de la idea y ficha técnica | ● | | | | | | | | | | |
| 2. Problemática, contexto y objetivos | ● | ● | ● | | | | | | | | |
| 3. Requerimientos y matriz de trazabilidad | | ● | ● | ● | | | | | | | |
| 4. Marco conceptual y contextual | | | ● | ● | | | | | | | |
| 5. Arquitectura en capas y diagramas UML | | | | ● | ● | | | | | | |
| 6. Especificación de diseño y plan | | | | | ● | | | | | | |
| 7. Prototipo base del dominio | | | | | ● | | | | | | |
| 8. Suite de pruebas y sabotaje | | | | | ● | ● | | | | | |
| 9. Marco integrador del asistente IA | | | | | ● | ● | | | | | |
| 10. Usuarios y roles | | | | | | ● | | | | | |
| 11. Rediseño de la interfaz | | | | | | ● | | | | | |
| 12. Entrega documentación V1 | | | | | | ● | | | | | |
| 13. Perfil, contactos, foto e idioma | | | | | | | ● | | | | |
| 14. Estado del arte del documento | | | | | | | ● | | | | |
| 15. Asistente IA en palabras simples | | | | | | | ● | | | | |
| 16. Pestaña de ayudante | | | | | | | | ● | | | |
| 17. Presupuesto y cronograma | | | | | | | | ● | | | |
| 18. Red neuronal en el documento | | | | | | | | ● | | | |
| 19. Red neuronal en el código | | | | | | | | ● | ● | | |
| 20. Integración de la red y pruebas | | | | | | | | | ● | ● | |
| 21. Fase 4: diseño uniforme y mensajes | | | | | | | | ● | ● | | |
| 22. Fase 4: menú y navegación | | | | | | | | ● | ● | | |
| 23. Fase 4: conexión, validación y errores | | | | | | | | ● | ● | | |
| 24. Fase 4: merge a main y publicación | | | | | | | | | ● | | |
| 25. Fase 4: evidencias y entrega | | | | | | | | | ● | ● | |
| 26. Ajustes del documento final | | | | | | | | | | ● | |
| 27. Entrega final y sustentación | | | | | | | | | | | ● |

*Nota. Cada punto indica una semana de trabajo; cada semana empieza el jueves, desde el
10 de septiembre (S1) hasta el 19 de noviembre de 2026 (S11): diez semanas de trabajo,
con una fecha de inicio de semana por columna. Elaboración propia.*
