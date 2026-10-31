// El botón de tema alterna entre claro y oscuro y recuerda la elección. La
// preferencia guardada se aplica antes de pintar con el guion corto del <head> de
// base.html; este archivo sólo atiende el botón. Sin elección guardada manda el
// sistema (`prefers-color-scheme`), y el botón refleja ese tema mientras tanto.
(() => {
    // Los textos a la vista pasan por `window.TEXTOS`, que pone `base.html`: vacío en
    // español y con las traducciones cuando la página va en inglés.
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const CLAVE = "tema";
    const raiz = document.documentElement;
    const sistemaOscuro = window.matchMedia("(prefers-color-scheme: dark)");

    const temaActual = () =>
        raiz.dataset.tema || (sistemaOscuro.matches ? "oscuro" : "claro");

    const reflejar = () => {
        const oscuro = temaActual() === "oscuro";
        for (const boton of document.querySelectorAll("[data-alternar-tema]")) {
            boton.setAttribute("aria-pressed", String(oscuro));
            boton.setAttribute(
                "aria-label",
                tr(oscuro ? "Cambiar a tema claro" : "Cambiar a tema oscuro")
            );
        }
    };

    const aplicar = (tema, fundir = true) => {
        if (fundir) raiz.classList.add("cambiando-tema");
        raiz.dataset.tema = tema;
        // El almacenamiento puede faltar (ventana privada, sitio bloqueado): el tema
        // cambia igual, sólo que no se recuerda.
        try {
            localStorage.setItem(CLAVE, tema);
        } catch {}
        reflejar();
        setTimeout(() => raiz.classList.remove("cambiando-tema"), 250);
    };

    // Donde el navegador tiene View Transitions, el tema nuevo se revela en un círculo
    // que crece desde el botón (animaciones.css); si no, o con movimiento reducido, los
    // colores se funden.
    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)");
    document.addEventListener("click", (evento) => {
        const boton = evento.target.closest("[data-alternar-tema]");
        if (!boton) return;
        const siguiente = temaActual() === "oscuro" ? "claro" : "oscuro";
        if (!document.startViewTransition || quieto.matches) {
            aplicar(siguiente);
            return;
        }
        const caja = boton.getBoundingClientRect();
        const x = caja.left + caja.width / 2;
        const y = caja.top + caja.height / 2;
        const radio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
        raiz.style.setProperty("--revelar-x", `${x}px`);
        raiz.style.setProperty("--revelar-y", `${y}px`);
        raiz.style.setProperty("--revelar-r", `${radio}px`);
        raiz.classList.add("revelando-tema");
        boton.classList.remove("girando");
        void boton.offsetWidth;
        boton.classList.add("girando");
        document
            .startViewTransition(() => aplicar(siguiente, false))
            .finished.finally(() => raiz.classList.remove("revelando-tema"));
    });
    sistemaOscuro.addEventListener("change", reflejar);
    reflejar();
})();
