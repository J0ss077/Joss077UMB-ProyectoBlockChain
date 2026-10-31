# Sistema de diseño «Bloques»

Guía de la interfaz del ledger transaccional. La dirección de arte es «Bloques»: un bento geométrico en cobalto con un único acento lima, radios generosos y datos en monoespaciada.

## Dónde vive

| Archivo                                    | Contenido                                                                               |
| ------------------------------------------ | --------------------------------------------------------------------------------------- |
| `src/web/static/css/tokens.css`            | Punto de entrada: sólo `@import` de los archivos de tokens                              |
| `src/web/static/css/tokens/fuentes.css`    | `@font-face` de las fuentes alojadas                                                    |
| `src/web/static/css/tokens/colores.css`    | Paleta base, alias semánticos y tema oscuro                                             |
| `src/web/static/css/tokens/tipografia.css` | Familias, escala, pesos, interlineado y tracking                                        |
| `src/web/static/css/tokens/espacio.css`    | Espaciado y medidas de layout                                                           |
| `src/web/static/css/tokens/forma.css`      | Radios, sombras y anillo de foco                                                        |
| `src/web/static/css/tokens/movimiento.css` | Duraciones, curvas y fundido del cambio de tema                                         |
| `src/web/static/css/app.css`               | Componentes y pantallas                                                                 |
| `src/web/static/css/animaciones.css`       | Animaciones vistosas, todas dentro de `prefers-reduced-motion: no-preference`           |
| `src/web/static/js/tema.js`                | Botón de tema claro/oscuro (revelado circular con View Transitions)                     |
| `src/web/static/js/codigos.js`             | Ventana con el código completo, códigos completos donde caben y montos sin ceros de más |
| `src/web/static/js/animaciones.js`         | Barra de carga, botones ocupados, cifras que cuentan, escaneo de la cadena, confeti     |
| `src/web/static/js/transaccion.js`         | Emisor y receptor escritos por nombre o ID                                              |
| `src/web/static/fonts/`                    | Bricolage Grotesque y Geist Mono (woff2 variables) con su licencia OFL                  |

Los componentes usan siempre los **alias semánticos** (`--color-superficie`, `--color-texto-suave`…), nunca la paleta base, para que el tema oscuro funcione sin tocar cada regla.

## Tema claro y oscuro

- Sin elección guardada manda `prefers-color-scheme`.
- El botón de la barra alterna el tema y lo guarda en `localStorage` (clave `tema`, valores `claro` u `oscuro`). Si el almacenamiento falla, el tema cambia igual pero no se recuerda.
- Un guion corto en el `<head>` de `base.html` aplica `data-tema` en `<html>` **antes** de cargar el CSS, así que no hay parpadeo al cargar.
- Donde el navegador tiene View Transitions, el tema nuevo se revela en un círculo que crece desde el botón; si no, los colores se funden durante 200 ms (clase `cambiando-tema`). Con movimiento reducido el cambio es instantáneo.

## Contenido y tono

- **Idioma:** español neutro. La interfaz tutea siempre, también en los dictámenes, en los mensajes de error, en los mensajes que arma el servicio y en los textos que fijan las pruebas («Entra con la cuenta que aprobó un administrador», «Haz tu primer envío», «No se puede verificar tu historial»). Los documentos y los comentarios van en impersonal.
- **Mensajes del dominio:** el motivo de un rechazo se muestra sin traducir ni adornar, en minúsculas como lo devuelve el dominio («el saldo disponible no alcanza»).
- **Estados en pantalla:** «En el pool», «Confirmada», «Rechazada». El valor técnico (`pending`, `confirmed`, `rejected`) queda en el HTML que leen las pruebas.
- **Cifras:** los montos llevan siempre ocho decimales (`300.00000000`) en Geist Mono.
- **Sin emoji.** Los iconos son trazos SVG en línea.
- **Mayúsculas:** sólo al inicio de frase; los antetítulos van en versalitas de Geist Mono con tracking (`--tracking-etiqueta`).

## Fundamentos visuales

- **Color:** fondo niebla (`--color-fondo`) con mosaicos blancos encima; en oscuro, tinta casi negra con mosaicos azul noche. El cobalto (`--color-acento`) marca la acción principal y los datos destacados; el **lima** (`--color-lima`) se reserva para el bloque más reciente de la cadena, la cadena válida y el chip «Tú». Éxito, pendiente y peligro tienen texto y fondo propios.
- **Tipografía:** títulos en Bricolage 800 con tracking −0.035em; cuerpo en 400–600; cifras grandes (saldo, métricas) en Geist Mono o Bricolage 800 con tracking −0.04em.
- **Layout:** rejilla de 12 columnas, 16 px de separación, contenido máximo de 1400 px. Las páginas se arman con mosaicos (`--radio-3xl`, 24 px de relleno).
- **Formas:** radios grandes y escalonados (6 → 28 px); las píldoras de estado son totalmente redondeadas. Sin bordes de color a un costado.
- **Sombras:** casi ninguna. Las superficies se separan por color. Sólo llevan sombra el bloque más reciente (`--sombra-lima`) y lo que flota (`--sombra-flotante`).
- **Fondos:** planos. La única decoración es la propia cadena de bloques (nodos unidos por un cable en degradado cobalto con puntos en los extremos).
- **Identidades:** nombre en negrita arriba y código debajo en Geist Mono 12 px gris. En tablas y paneles el código va en una línea recortado como `59d745dc…b0a1`, con el completo en el tooltip y botón de copiar al lado.
- **Interacción:** hover con cambio de fondo, foco visible con `--anillo-foco` (3 px del color de foco), objetivos táctiles de al menos 44 px.
- **Movimiento:** salidas suaves (`--curva-salida`), resorte sólo en confirmaciones; todas las duraciones caen a ~0 con `prefers-reduced-motion`.
- **Transparencia y desenfoque:** no se usan.

## Iconografía

Trazos SVG en línea de 1.6–2.2 px, con `currentColor` y `aria-hidden="true"`; el botón que los contiene lleva `aria-label`. No hay fuente de iconos ni sprite: los pocos iconos (tema, copiar, flechas de entrada/salida, check, aviso, candado) se escriben en la plantilla. No se usan emoji ni caracteres Unicode como iconos.

## Marca

El proyecto no tiene logo. La marca es el nombre «Ledger» junto a un cuadro cobalto de cuatro celdas con la última en lima, hecho con CSS (no es un logo dibujado).

## Accesibilidad

Todas las parejas de texto de los dos temas pasan WCAG AA (la más justa: éxito sobre su fondo, 4.70:1). Los bordes de controles (`--color-borde-fuerte`) pasan 3:1 contra sus superficies.

Además (Fase 5, revisado con axe-core en los dos temas y en 320, 375, 768, 1024 y 1440 px):

- Cada pantalla tiene un único `<main id="contenido">` y el primer elemento enfocable es «Saltar al contenido».
- Todo control enfocable muestra anillo de foco y mide al menos 24×24 px (WCAG 2.5.8).
- Ninguna página se desplaza a lo ancho; sólo las tablas y la cadena se desplazan dentro de su caja.
- Con `prefers-reduced-motion` no hay animaciones: sólo queda el bloqueo del doble envío. Los títulos animados palabra por palabra llevan una copia `.solo-lectores` con el texto entero y la versión animada va con `aria-hidden`; el escaneo de la cadena es decorativo y el dictamen ya está en la página.

## Contratos de las pruebas que la interfaz respeta

- Los códigos llegan del servidor en forma corta (`dato`: `>{corta}<` con el valor completo en `title` y `data-copiar`); `codigos.js` los amplía en el navegador sólo donde caben.
- En las páginas del administrador la clave pública nunca es texto visible (`test_req_24`).
- `base.html` conserva la regla `code, .mono, select, option, input { font-family: var(--mono) }` y el guion de copiar (`test_req_29`).
- El formulario de transacción conserva `<option value="…" title="…">` exacto, ahora como sugerencias del campo de texto.
