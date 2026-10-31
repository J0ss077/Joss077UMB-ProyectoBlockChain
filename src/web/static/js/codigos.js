// Ventana con el código completo al pasar el mouse sobre un dato corto (o al
// enfocar su botón de copiar). Los códigos se muestran recortados para no mover el
// layout; el valor completo ya viaja en `data-copiar`, que es lo que lee esta
// ventana. Va en posición fija sobre la página para que no la corte el
// desplazamiento horizontal de las tablas. Mientras se muestra, el `title` del dato
// se guarda aparte para que el navegador no pinte un segundo tooltip encima.
(() => {
    // Los textos a la vista pasan por `window.TEXTOS`, que pone `base.html`: vacío en
    // español y con las traducciones cuando la página va en inglés.
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const ventana = document.createElement("div");
    ventana.className = "ventana-codigo";
    ventana.setAttribute("role", "tooltip");
    ventana.hidden = true;
    const valor = document.createElement("span");
    valor.className = "ventana-codigo-valor";
    const pista = document.createElement("span");
    pista.className = "ventana-codigo-pista";
    ventana.append(valor, pista);

    let actual = null;

    // Los UUID se leen por sus guiones; las claves y los hashes, en grupos de 8.
    const agrupar = (texto) =>
        texto.includes("-") ? texto : (texto.match(/.{1,8}/g) || [texto]).join(" ");

    const ubicar = (origen) => {
        const caja = origen.getBoundingClientRect();
        const margen = 8;
        const ancho = ventana.offsetWidth;
        const alto = ventana.offsetHeight;
        let izquierda = caja.left + caja.width / 2 - ancho / 2;
        izquierda = Math.max(margen, Math.min(izquierda, window.innerWidth - ancho - margen));
        let arriba = caja.top - alto - margen;
        if (arriba < margen) arriba = caja.bottom + margen;
        ventana.style.left = `${izquierda}px`;
        ventana.style.top = `${arriba}px`;
    };

    const mostrar = (origen) => {
        if (actual === origen) return;
        ocultar();
        actual = origen;
        if (origen.title) {
            origen.dataset.tituloGuardado = origen.title;
            origen.removeAttribute("title");
        }
        valor.textContent = agrupar(origen.dataset.copiar);
        pista.textContent = origen.classList.contains("copiar")
            ? tr("Enter para copiar")
            : tr("Clic para copiar");
        if (!ventana.isConnected) document.body.append(ventana);
        ventana.hidden = false;
        ubicar(origen);
    };

    const ocultar = () => {
        if (!actual) return;
        if (actual.dataset.tituloGuardado) {
            actual.title = actual.dataset.tituloGuardado;
            delete actual.dataset.tituloGuardado;
        }
        actual = null;
        ventana.hidden = true;
    };

    const origenDe = (objetivo) =>
        objetivo instanceof Element ? objetivo.closest(".mono[data-copiar], .copiar[data-copiar]") : null;

    document.addEventListener("mouseover", (evento) => {
        const origen = origenDe(evento.target);
        if (origen) mostrar(origen);
        else if (actual && !origenDe(evento.relatedTarget)) ocultar();
    });
    document.addEventListener("mouseout", (evento) => {
        if (actual && !origenDe(evento.relatedTarget)) ocultar();
    });
    document.addEventListener("focusin", (evento) => {
        const origen = origenDe(evento.target);
        if (origen) mostrar(origen);
    });
    document.addEventListener("focusout", ocultar);
    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") ocultar();
    });
    window.addEventListener("scroll", ocultar, { passive: true, capture: true });

    // Los códigos llegan recortados (`59d745dc…b0a1`), que es lo que leen las pruebas
    // y lo que se ve sin JavaScript. Donde el valor completo cabe sin mover el layout
    // se muestra completo: en las tablas se prueba columna por columna y se conserva
    // sólo si la tabla sigue entrando en su caja; fuera de las tablas, si el código no
    // se sale de su tarjeta. Las claves públicas quedan siempre cortas: las pruebas
    // del administrador exigen que nunca se vean completas como texto.
    const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const HASH = /^[0-9a-f]{64}$/i;
    const ampliables = () =>
        [...document.querySelectorAll(".mono[data-copiar]")].filter((dato) => {
            // Los eslabones de la cadena son de ancho fijo: un hash de 64 nunca cabe.
            if (dato.closest(".cadena")) return false;
            const valor = dato.dataset.copiar;
            return UUID.test(valor) || HASH.test(valor);
        });
    const cortos = new Map();
    const contraer = (dato) => {
        if (cortos.has(dato)) dato.textContent = cortos.get(dato);
    };
    const ampliar = (dato) => {
        if (!cortos.has(dato)) cortos.set(dato, dato.textContent);
        dato.textContent = dato.dataset.copiar;
    };
    // Cabe si la tarjeta no se ensanchó, el código (con su botón) no pasa del borde
    // interior de la tarjeta y la página no ganó desplazamiento horizontal.
    const tarjetaDe = (dato) =>
        dato.closest(".eslabon-cadena, .fila-wallet, .ficha, .dato-wallet, .mi-wallet, .mi-wallet-tarjeta, .mosaico");
    const cabeEnSuTarjeta = (dato, anchoPrevio) => {
        const caja = tarjetaDe(dato);
        if (!caja) return true;
        const rect = caja.getBoundingClientRect();
        const borde = rect.right - parseFloat(getComputedStyle(caja).paddingRight);
        const codigo = dato.parentElement.closest(".codigo") || dato;
        const raiz = document.documentElement;
        return (
            rect.width <= anchoPrevio + 0.5 &&
            codigo.getBoundingClientRect().right <= borde + 0.5 &&
            raiz.scrollWidth <= raiz.clientWidth
        );
    };
    const ajustar = () => {
        const datos = ampliables();
        datos.forEach(contraer);
        // Las tablas, columna por columna, de izquierda a derecha.
        for (const envoltura of document.querySelectorAll(".tabla-desplazable")) {
            const columnas = new Map();
            for (const dato of datos) {
                const celda = dato.closest("td");
                if (!celda || !envoltura.contains(celda)) continue;
                if (!columnas.has(celda.cellIndex)) columnas.set(celda.cellIndex, []);
                columnas.get(celda.cellIndex).push(dato);
            }
            for (const indice of [...columnas.keys()].sort((a, b) => a - b)) {
                const enColumna = columnas.get(indice);
                enColumna.forEach(ampliar);
                if (envoltura.scrollWidth > envoltura.clientWidth + 1) enColumna.forEach(contraer);
            }
        }
        // Fuera de las tablas, cada código por su cuenta.
        for (const dato of datos) {
            if (dato.closest(".tabla-desplazable")) continue;
            const caja = tarjetaDe(dato);
            const anchoPrevio = caja ? caja.getBoundingClientRect().width : 0;
            ampliar(dato);
            if (!cabeEnSuTarjeta(dato, anchoPrevio)) contraer(dato);
        }
    };
    let pendiente = 0;
    const reajustar = () => {
        cancelAnimationFrame(pendiente);
        pendiente = requestAnimationFrame(ajustar);
    };
    ajustar();
    document.fonts?.ready.then(reajustar);
    window.addEventListener("resize", reajustar);

    // Los montos de las tablas de movimientos llegan con sus ocho decimales, porque
    // así los leen las pruebas en el HTML; al mostrarlos se quitan los ceros que
    // sobran (1000.00000000 → 1000, 12.50000000 → 12.5) y el valor exacto queda en
    // el `title`. Sin JavaScript se ve el monto completo.
    for (const monto of document.querySelectorAll(".tabla-movimientos td:nth-child(4) > code")) {
        const exacto = monto.textContent.trim();
        if (!/^-?\d+\.\d+$/.test(exacto)) continue;
        monto.textContent = exacto.replace(/\.?0+$/, "");
        monto.title = exacto;
    }
})();
