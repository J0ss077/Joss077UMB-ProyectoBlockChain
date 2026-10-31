// Notificaciones en burbuja, centradas arriba. Entran con una animación de
// apertura tipo macOS (la burbuja nace chica y aplastada y se despliega con un
// rebote) y salen encogiéndose hacia arriba. Se cierran con su botón o con
// Escape, que cierra la más reciente. Las de éxito (`data-se-va-solo`) se van solas
// después de unos segundos, salvo mientras el puntero o el foco están sobre ellas;
// los avisos y los errores esperan a que se cierren.
(() => {
    const ESPERA = 6000;
    const bandeja = document.querySelector("[data-burbujas]");
    if (!bandeja) return;

    const cerrar = (burbuja) => {
        if (burbuja.classList.contains("cerrando")) return;
        clearTimeout(burbuja._reloj);
        burbuja.classList.add("cerrando");
        // Sin animación (movimiento reducido) `animationend` no llega: se quita igual.
        const quitar = () => burbuja.remove();
        burbuja.addEventListener("animationend", quitar, { once: true });
        setTimeout(quitar, 500);
    };

    const burbujas = [...bandeja.querySelectorAll("[data-burbuja]")];
    burbujas.forEach((burbuja, indice) => {
        // Si llegan varias, se despliegan una detrás de otra.
        burbuja.style.setProperty("--orden", String(indice));
        const programar = () => {
            if (burbuja.hasAttribute("data-se-va-solo")) {
                burbuja._reloj = setTimeout(() => cerrar(burbuja), ESPERA + indice * 400);
            }
        };
        const pausar = () => clearTimeout(burbuja._reloj);
        burbuja.querySelector("[data-burbuja-cerrar]")?.addEventListener("click", () => cerrar(burbuja));
        burbuja.addEventListener("mouseenter", pausar);
        burbuja.addEventListener("mouseleave", programar);
        burbuja.addEventListener("focusin", pausar);
        burbuja.addEventListener("focusout", programar);
        programar();
    });

    document.addEventListener("keydown", (evento) => {
        if (evento.key !== "Escape") return;
        // Un diálogo abierto (el editor de la foto) se queda con su propio Escape.
        if (document.querySelector("dialog[open]")) return;
        const abiertas = bandeja.querySelectorAll("[data-burbuja]:not(.cerrando)");
        if (abiertas.length) cerrar(abiertas[abiertas.length - 1]);
    });
})();
