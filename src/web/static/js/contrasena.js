// Medidor de fuerza para las contraseñas nuevas y aviso de coincidencia para la
// repetición. Es una ayuda y no una regla: lo único que el servidor exige es el
// largo mínimo (REQ-30), que llega por `data-largo-minimo` desde la misma
// constante que valida el registro. Sin JavaScript queda la ayuda de texto.
// Todo campo de contraseña lleva además el botón para verla u ocultarla; lo arma
// este guion y no la plantilla para que sin JavaScript no quede un botón muerto.
(() => {
    // Los textos a la vista pasan por `window.TEXTOS`, que pone `base.html`: vacío en
    // español y con las traducciones cuando la página va en inglés.
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const COMUN =
        /^(?:password|passw0rd|contrasena|contraseña|qwerty|letmein|welcome|admin|iloveyou|monkey|dragon|abc123|111111|123123|123456)/i;
    const REPETIDO = /(.)\1{3,}/;
    const ESCALERA =
        /(?:0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|defg|qwer|wert|erty|asdf)/i;
    const SIMBOLO = /[!-/:-@[-`{-~]/;
    const ETIQUETAS = ["Vacía", "Débil", "Regular", "Buena", "Fuerte"].map(tr);
    const ESPERA_DEL_ANUNCIO = 700;
    const SVG = "http://www.w3.org/2000/svg";

    const crear = (etiqueta, clase, texto) => {
        const nodo = document.createElement(etiqueta);
        if (clase) nodo.className = clase;
        if (texto !== undefined) nodo.textContent = texto;
        return nodo;
    };

    const marca = () => {
        const caja = crear("span", "fuerza-casilla");
        caja.setAttribute("aria-hidden", "true");
        const svg = document.createElementNS(SVG, "svg");
        svg.setAttribute("viewBox", "0 0 12 12");
        svg.setAttribute("fill", "none");
        const trazo = document.createElementNS(SVG, "path");
        trazo.setAttribute("d", "M2 6.2 4.7 8.9 10 3.3");
        trazo.setAttribute("stroke", "currentColor");
        trazo.setAttribute("stroke-width", "1.9");
        trazo.setAttribute("stroke-linecap", "round");
        trazo.setAttribute("stroke-linejoin", "round");
        svg.append(trazo);
        caja.append(svg);
        return caja;
    };

    const ojo = (abierto) => {
        const svg = document.createElementNS(SVG, "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("width", "20");
        svg.setAttribute("height", "20");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "2");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("aria-hidden", "true");
        const trazos = abierto
            ? ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"]
            : [
                  "M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-2.5 3.4",
                  "M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6",
                  "M9.9 9.9a3 3 0 0 0 4.2 4.2",
                  "M3 3l18 18",
              ];
        for (const d of trazos) {
            const trazo = document.createElementNS(SVG, "path");
            trazo.setAttribute("d", d);
            svg.append(trazo);
        }
        return svg;
    };

    // El botón dice lo que va a hacer y `aria-pressed` dice si la contraseña está
    // a la vista. Al enviar el formulario vuelve a ocultarse, para que el
    // navegador no la recuerde como texto.
    const montarOjo = (campo) => {
        const envoltura = crear("div", "campo-clave");
        campo.before(envoltura);
        envoltura.append(campo);
        const boton = crear("button", "ver-clave");
        boton.type = "button";
        boton.setAttribute("aria-controls", campo.id);
        envoltura.append(boton);

        const mostrar = (visible) => {
            campo.type = visible ? "text" : "password";
            boton.setAttribute("aria-pressed", String(visible));
            boton.setAttribute("aria-label", tr(visible ? "Ocultar contraseña" : "Mostrar contraseña"));
            boton.title = boton.getAttribute("aria-label");
            boton.replaceChildren(ojo(!visible));
        };

        boton.addEventListener("click", () => mostrar(campo.type === "password"));
        campo.form?.addEventListener("submit", () => mostrar(false));
        mostrar(false);
    };

    const tonoPara = (puntaje, maximo) => {
        if (puntaje === 0) return "ninguno";
        const proporcion = puntaje / maximo;
        if (proporcion <= 0.34) return "peligro";
        if (proporcion <= 0.67) return "precaucion";
        return "exito";
    };

    const montarMedidor = (contenedor, campo) => {
        const largo = Number(contenedor.dataset.largoMinimo) || 8;
        const reglas = [
            { texto: tr("{n} caracteres o más").replace("{n}", largo), prueba: (v) => v.length >= largo },
            { texto: tr("Mayúsculas y minúsculas"), prueba: (v) => /[a-z]/.test(v) && /[A-Z]/.test(v) },
            { texto: tr("Un número"), prueba: (v) => /\d/.test(v) },
            { texto: tr("Un símbolo"), prueba: (v) => SIMBOLO.test(v) },
        ];
        const maximo = reglas.length;

        const medidor = crear("div", "fuerza-medidor");
        medidor.setAttribute("role", "meter");
        medidor.setAttribute("aria-label", tr("Fuerza de la contraseña"));
        medidor.setAttribute("aria-valuemin", "0");
        medidor.setAttribute("aria-valuemax", String(maximo));
        const segmentos = reglas.map((_, i) => {
            const segmento = crear("span", "fuerza-segmento");
            const relleno = crear("span", "fuerza-relleno");
            relleno.style.setProperty("--i", String(i));
            segmento.append(relleno);
            medidor.append(segmento);
            return segmento;
        });

        const fila = crear("div", "fuerza-fila");
        const etiquetas = crear("span", "fuerza-etiquetas");
        etiquetas.setAttribute("aria-hidden", "true");
        const textos = ETIQUETAS.map((texto) => {
            const nodo = crear("span", "fuerza-etiqueta", texto);
            etiquetas.append(nodo);
            return nodo;
        });
        const comun = crear("span", "fuerza-comun", tr("Patrón muy común"));
        comun.setAttribute("aria-hidden", "true");
        fila.append(etiquetas, comun);

        const lista = crear("ul", "fuerza-reglas");
        lista.id = `${campo.id}-reglas`;
        const items = reglas.map((regla) => {
            const item = crear("li", "fuerza-regla");
            const estado = crear("span", "solo-lectores");
            item.append(marca(), crear("span", "", regla.texto), estado);
            lista.append(item);
            return { item, estado };
        });

        const anuncio = crear("p", "solo-lectores");
        anuncio.setAttribute("aria-live", "polite");

        contenedor.replaceChildren(medidor, fila, lista, anuncio);
        contenedor.hidden = false;
        // La lista de reglas reemplaza a la ayuda de texto, que sólo decía el largo.
        const ayuda = document.getElementById(contenedor.dataset.reemplaza || "");
        if (ayuda) ayuda.hidden = true;
        campo.setAttribute("aria-describedby", lista.id);

        let espera;
        const actualizar = () => {
            const valor = campo.value;
            const cumplidas = reglas.map((regla) => regla.prueba(valor));
            const pasadas = cumplidas.filter(Boolean).length;
            const adivinable =
                valor.length > 0 && (COMUN.test(valor) || REPETIDO.test(valor) || ESCALERA.test(valor));
            let puntaje = valor.length === 0 ? 0 : adivinable ? 1 : Math.max(1, pasadas);
            // Sin el largo mínimo el servidor la rechaza: no puede verse mejor que débil.
            if (valor.length > 0 && !cumplidas[0]) puntaje = 1;
            const etiqueta = ETIQUETAS[Math.min(puntaje, ETIQUETAS.length - 1)];

            contenedor.dataset.tono = tonoPara(puntaje, maximo);
            medidor.setAttribute("aria-valuenow", String(puntaje));
            medidor.setAttribute("aria-valuetext", etiqueta);
            segmentos.forEach((segmento, i) => segmento.classList.toggle("lleno", i < puntaje));
            textos.forEach((nodo, i) => nodo.classList.toggle("visible", i === Math.min(puntaje, ETIQUETAS.length - 1)));
            comun.classList.toggle("visible", adivinable);
            items.forEach(({ item, estado }, i) => {
                item.classList.toggle("cumplida", cumplidas[i]);
                estado.textContent = tr(cumplidas[i] ? "cumplida" : "pendiente");
            });

            // El anuncio espera a que la persona deje de escribir: leer cada tecla
            // taparía lo que el lector de pantalla está diciendo.
            clearTimeout(espera);
            if (valor.length === 0) {
                anuncio.textContent = "";
                return;
            }
            const faltan = reglas.filter((_, i) => !cumplidas[i]).map((regla) => regla.texto.toLowerCase());
            const texto = [
                tr("Fuerza de la contraseña: {etiqueta}.").replace("{etiqueta}", etiqueta.toLowerCase()),
                adivinable ? tr("Es un patrón muy común.") : "",
                faltan.length === 0
                    ? tr("Cumple todas las recomendaciones.")
                    : tr("Falta: {lista}.").replace("{lista}", faltan.join(", ")),
            ]
                .filter(Boolean)
                .join(" ");
            espera = setTimeout(() => {
                anuncio.textContent = texto;
            }, ESPERA_DEL_ANUNCIO);
        };

        campo.addEventListener("input", actualizar);
        actualizar();
    };

    const montarCoincidencia = (contenedor, campo, original) => {
        const fila = crear("p", "fuerza-regla coincidencia");
        const texto = crear("span");
        fila.append(marca(), texto);
        fila.setAttribute("aria-live", "polite");
        contenedor.replaceChildren(fila);

        const actualizar = () => {
            const vacia = campo.value.length === 0;
            const iguales = !vacia && campo.value === original.value;
            contenedor.hidden = vacia;
            fila.classList.toggle("cumplida", iguales);
            texto.textContent = tr(iguales ? "Las contraseñas coinciden" : "Todavía no coinciden");
        };

        campo.addEventListener("input", actualizar);
        original.addEventListener("input", actualizar);
        actualizar();
    };

    for (const campo of document.querySelectorAll('input[type="password"]')) {
        montarOjo(campo);
    }
    for (const contenedor of document.querySelectorAll("[data-fuerza-de]")) {
        const campo = document.getElementById(contenedor.dataset.fuerzaDe);
        if (campo) montarMedidor(contenedor, campo);
    }
    for (const contenedor of document.querySelectorAll("[data-coincide-con]")) {
        const campo = document.getElementById(contenedor.dataset.campo);
        const original = document.getElementById(contenedor.dataset.coincideCon);
        if (campo && original) montarCoincidencia(contenedor, campo, original);
    }
})();
