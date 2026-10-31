// Emisor y receptor se escriben a mano: el nombre del dueño de la wallet, su
// identificador completo o sus primeros caracteres. Las wallets conocidas salen de
// las sugerencias del formulario (`datalist`), que ya traen el identificador como
// valor y el nombre, la clave corta y el saldo como texto. Debajo de cada campo se
// dice a qué wallet corresponde lo escrito y, al enviar, el campo se reemplaza por el
// identificador, que es lo único que recibe la ruta. Si lo escrito no corresponde a
// una sola wallet, el campo queda inválido y el formulario no se envía.
(() => {
    // Los textos a la vista pasan por `window.TEXTOS`, que pone `base.html`: vacío en
    // español y con las traducciones cuando la página va en inglés.
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const ruta = document.querySelector("[data-ruta-envio]");
    if (!ruta) return;
    const formulario = ruta.closest("form");

    const wallets = [...ruta.querySelectorAll("datalist option")].map((opcion) => {
        const [nombre, clave, saldo] = opcion.textContent.split(" · ");
        return {
            id: opcion.value,
            // Las wallets sin dueño sólo se pueden elegir por su identificador. La
            // opción dice «Sin dueño» en el idioma de la página, igual que `tr`.
            nombre: nombre === tr("Sin dueño") ? null : nombre,
            clave,
            // El saldo llega como «saldo 12» o «balance 12»: se descarta la palabra.
            saldo: saldo.replace(/^\S+ /, ""),
        };
    });

    const resolver = (texto) => {
        const buscado = texto.trim().toLowerCase();
        if (!buscado) return { wallet: null, motivo: "" };
        const exacta = wallets.find(
            (wallet) => wallet.id === buscado || wallet.nombre?.toLowerCase() === buscado,
        );
        if (exacta) return { wallet: exacta };
        if (buscado.length >= 4) {
            const porPrefijo = wallets.filter((wallet) => wallet.id.startsWith(buscado));
            if (porPrefijo.length === 1) return { wallet: porPrefijo[0] };
            if (porPrefijo.length > 1) {
                return {
                    wallet: null,
                    motivo: tr("{n} wallets empiezan así; escribe más caracteres.").replace("{n}", porPrefijo.length),
                };
            }
        }
        return { wallet: null, motivo: tr("Ninguna wallet tiene ese nombre o ese ID.") };
    };

    const campos = [...ruta.querySelectorAll("input[list]")];

    const revisar = (campo) => {
        const salida = document.getElementById(campo.getAttribute("aria-describedby"));
        const { wallet, motivo } = resolver(campo.value);
        const antes = salida.textContent;
        salida.replaceChildren();
        if (wallet) {
            const nombre = document.createElement("b");
            nombre.textContent = wallet.nombre ?? tr("Sin dueño");
            salida.append(nombre, ` · ${wallet.id.slice(0, 8)}… · ${tr("saldo")} ${wallet.saldo}`);
            salida.dataset.estado = "encontrada";
            campo.setCustomValidity("");
        } else {
            salida.textContent = motivo;
            salida.dataset.estado = motivo ? "ninguna" : "";
            campo.setCustomValidity(motivo);
        }
        // La línea se anima sólo cuando cambia; el campo marca si quedó resuelto y la
        // flecha avanza cuando las dos wallets lo están.
        if (salida.textContent !== antes) {
            salida.classList.remove("recien");
            void salida.offsetWidth;
            salida.classList.add("recien");
        }
        campo.classList.toggle("resuelto", Boolean(wallet));
        ruta.classList.toggle("lista", campos.every((otro) => otro.classList.contains("resuelto")));
        return wallet;
    };

    for (const campo of campos) {
        // Después de proponer, el campo vuelve con el identificador que se envió: se
        // muestra el nombre del dueño, que es lo que la persona escribió.
        const previa = wallets.find((wallet) => wallet.id === campo.value.trim());
        if (previa?.nombre) campo.value = previa.nombre;
        campo.addEventListener("input", () => revisar(campo));
        revisar(campo);
    }

    formulario.addEventListener("submit", (evento) => {
        const resueltas = campos.map(revisar);
        if (resueltas.some((wallet) => !wallet)) {
            evento.preventDefault();
            campos.forEach((campo, i) => {
                if (resueltas[i]) return;
                campo.classList.remove("sacudir");
                void campo.offsetWidth;
                campo.classList.add("sacudir");
            });
            formulario.reportValidity();
            return;
        }
        campos.forEach((campo, i) => {
            campo.value = resueltas[i].id;
        });
    });
})();
