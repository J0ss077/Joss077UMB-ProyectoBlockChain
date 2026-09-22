# Referencias

Fuentes en las que se apoyan las afirmaciones de diseño de esta documentación, y ubicación de los artefactos del proyecto que viven fuera del repositorio.

## Bibliografía

Yaga, D., Mell, P., Roby, N. y Scarfone, K. (2018). Blockchain technology overview (NISTIR 8202). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.IR.8202

Es la fuente de la definición de blockchain como libro mayor digital resistente a la manipulación, y de la distinción entre capas criptográfica, de reglas y de red que usa `arquitectura.md` para delimitar el alcance.

Haber, S. y Stornetta, W. S. (1991). How to time-stamp a digital document. Journal of Cryptology, 3(2), 99–111. https://doi.org/10.1007/BF00196791

Es la fuente del sellado por marcas temporales y del encadenamiento por hash: si cada bloque incluye el hash del anterior, retro o posdatar un documento deja de ser viable, porque cualquier cambio rompe la cadena.

Kessem, L. (2025, 19 de noviembre). 2025 Cost of a Data Breach Report: Navigating the AI rush without sidelining security. IBM. https://www.ibm.com/think/x-force/2025-cost-of-a-data-breach-navigating-ai

Es la fuente de la magnitud del costo de una violación de datos y del peso desproporcionado de los actores internos maliciosos. Respalda la problemática, no una decisión técnica.

Sebastian.Cardenas. (s. f.). Los delitos informáticos aumentaron 36 % en Colombia en lo que va de 2026. El Nuevo Siglo. https://www.elnuevosiglo.com.co/nacion/los-delitos-informaticos-aumentaron-36-en-colombia-en-lo-que-va-de-2026

Es la fuente del crecimiento de los delitos informáticos en Colombia y del predominio del hurto por medios informáticos y el acceso abusivo a sistemas. Respalda la problemática.

## Artefactos fuera del repositorio

Anexo A. Carpeta `UML_Microproyecto_Transaccionales` con los diagramas del sistema en archivos `.puml`.

https://drive.google.com/drive/folders/1THiDby7u70zowmUAEgfTH9w-VnwX9MBN

Contiene los diagramas de casos de uso, de clases y del modelo relacional que `arquitectura.md` describe en prosa. Son la versión gráfica de las tablas de ese documento; si cambian, hay que actualizar la prosa.

## Documentos de entrega

Los documentos de entrega de cada fase no se versionan en este repositorio: se manejan por fuera. Lo que de ellos sea permanente se incorpora a `docs/`, que es la fuente de verdad del proyecto.
