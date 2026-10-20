// La vista previa de los campos de destinatario: mientras se teclea, pide al
// servidor los nombres que coinciden y los muestra debajo del campo. Se elige con
// el ratón o con las flechas y Enter; Escape la cierra. Sin JavaScript el campo
// sigue siendo un campo de texto y el formulario funciona igual.
(() => {
    const ESPERA_MS = 150;

    for (const campo of document.querySelectorAll("input[data-sugerencias]")) {
        const lista = document.createElement("ul");
        lista.className = "lista-sugerencias";
        lista.id = `${campo.id}-sugerencias`;
        lista.setAttribute("role", "listbox");
        lista.hidden = true;
        campo.after(lista);
        campo.parentElement.classList.add("campo-con-sugerencias");

        campo.setAttribute("role", "combobox");
        campo.setAttribute("aria-autocomplete", "list");
        campo.setAttribute("aria-controls", lista.id);
        campo.setAttribute("aria-expanded", "false");

        let espera = null;
        let pedido = null;

        const opciones = () => [...lista.querySelectorAll('[role="option"]')];
        const marcada = () => lista.querySelector('[aria-selected="true"]');

        const cerrar = () => {
            lista.hidden = true;
            campo.setAttribute("aria-expanded", "false");
            campo.removeAttribute("aria-activedescendant");
        };

        const marcar = (opcion) => {
            for (const otra of opciones()) otra.setAttribute("aria-selected", "false");
            if (!opcion) {
                campo.removeAttribute("aria-activedescendant");
                return;
            }
            opcion.setAttribute("aria-selected", "true");
            campo.setAttribute("aria-activedescendant", opcion.id);
            opcion.scrollIntoView({ block: "nearest" });
        };

        const elegir = (opcion) => {
            campo.value = opcion.dataset.nombre;
            cerrar();
            campo.focus();
        };

        const buscar = async () => {
            const texto = campo.value.trim();
            pedido?.abort();
            if (!texto) {
                cerrar();
                return;
            }
            pedido = new AbortController();
            const url = new URL(campo.dataset.sugerencias, location.origin);
            url.searchParams.set("q", texto);
            try {
                const respuesta = await fetch(url, { signal: pedido.signal });
                if (!respuesta.ok) return cerrar();
                lista.innerHTML = await respuesta.text();
            } catch (error) {
                if (error.name !== "AbortError") cerrar();
                return;
            }
            opciones().forEach((opcion, i) => {
                opcion.id = `${lista.id}-${i}`;
            });
            lista.hidden = false;
            campo.setAttribute("aria-expanded", "true");
        };

        campo.addEventListener("input", () => {
            clearTimeout(espera);
            espera = setTimeout(buscar, ESPERA_MS);
        });

        campo.addEventListener("keydown", (evento) => {
            if (lista.hidden) {
                if (evento.key === "ArrowDown" && campo.value.trim()) buscar();
                return;
            }
            const todas = opciones();
            const actual = todas.indexOf(marcada());
            if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
                evento.preventDefault();
                if (!todas.length) return;
                const paso = evento.key === "ArrowDown" ? 1 : -1;
                marcar(todas[(actual + paso + todas.length) % todas.length]);
            } else if (evento.key === "Enter" && actual >= 0) {
                // Enter con una opción marcada la elige; sin marca, envía el formulario.
                evento.preventDefault();
                elegir(todas[actual]);
            } else if (evento.key === "Escape") {
                evento.preventDefault();
                cerrar();
            }
        });

        campo.addEventListener("blur", cerrar);

        // `mousedown` y no `click`: el clic llega después del `blur`, que ya cerró la lista.
        lista.addEventListener("mousedown", (evento) => {
            const opcion = evento.target.closest('[role="option"]');
            if (!opcion) return;
            evento.preventDefault();
            elegir(opcion);
        });
        lista.addEventListener("mousemove", (evento) => {
            const opcion = evento.target.closest('[role="option"]');
            if (opcion && opcion !== marcada()) marcar(opcion);
        });
    }
})();
