// Animaciones que necesitan JavaScript: barra de carga, botones ocupados (que además
// evitan el doble envío), cifras que cuentan, títulos palabra por palabra, foco de luz
// e inclinación de las tarjetas, imán y onda de los botones, confeti, el escaneo de la
// cadena antes del dictamen, el bloque recién cerrado y la fila recién propuesta.
// Nada de esto cambia el contenido que llega del servidor: los textos se restauran al
// terminar y, con movimiento reducido, sólo queda lo que evita el doble envío.
(() => {
    const raiz = document.documentElement;
    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ── Barra de carga y botones ocupados (también con movimiento reducido) ──
    const barra = document.createElement("div");
    barra.className = "barra-carga";
    barra.setAttribute("aria-hidden", "true");
    document.body.append(barra);
    const cargar = () => {
        barra.classList.remove("activa");
        void barra.offsetWidth;
        barra.classList.add("activa");
    };

    document.addEventListener("click", (evento) => {
        const enlace = evento.target.closest("a[href]");
        if (
            !enlace ||
            evento.defaultPrevented ||
            evento.button !== 0 ||
            evento.metaKey ||
            evento.ctrlKey ||
            evento.shiftKey ||
            evento.altKey ||
            enlace.target ||
            enlace.hasAttribute("download") ||
            enlace.origin !== location.origin ||
            (enlace.pathname === location.pathname && enlace.hash)
        ) {
            return;
        }
        cargar();
    });

    const HEX = "0123456789abcdef";
    const barajar = (largo) => Array.from({ length: largo }, () => HEX[(Math.random() * 16) | 0]).join("");

    // Va en el documento, así corre después de los guiones de cada formulario: si uno
    // de ellos canceló el envío (por ejemplo, una wallet que no se encontró), no se
    // marca nada.
    document.addEventListener("submit", (evento) => {
        if (evento.defaultPrevented) return;
        const formulario = evento.target;
        if (formulario.dataset.enviando) {
            evento.preventDefault();
            return;
        }
        formulario.dataset.enviando = "si";
        formulario.setAttribute("aria-busy", "true");
        const boton = evento.submitter || formulario.querySelector("[type=submit]");
        cargar();
        if (!boton) return;
        boton.classList.add("ocupado");
        boton.setAttribute("aria-disabled", "true");
        // Cerrar un bloque es "minar": el botón baraja hexadecimales mientras espera.
        if (!quieto && formulario.method === "post" && new URL(formulario.action).pathname === "/bloques") {
            boton.setAttribute("aria-label", boton.textContent.trim());
            boton.classList.add("minando");
            setInterval(() => {
                boton.textContent = barajar(14);
            }, 70);
        }
    });

    // Al volver con el botón Atrás la página sale de la caché tal como quedó.
    window.addEventListener("pageshow", (evento) => {
        if (!evento.persisted) return;
        barra.classList.remove("activa");
        for (const formulario of document.querySelectorAll("form[data-enviando]")) {
            delete formulario.dataset.enviando;
            formulario.removeAttribute("aria-busy");
        }
        for (const boton of document.querySelectorAll(".ocupado")) {
            boton.classList.remove("ocupado");
            boton.removeAttribute("aria-disabled");
        }
    });

    if (quieto) return;

    const color = (nombre) => getComputedStyle(raiz).getPropertyValue(nombre).trim();

    // ── Confeti de bloquecitos ──────────────────────────────────────────────
    const confeti = (x, y, cantidad = 40, fuerza = 1) => {
        const colores = [color("--color-lima"), color("--color-acento"), color("--color-cadena-2"), color("--color-exito")];
        for (let i = 0; i < cantidad; i++) {
            const pieza = document.createElement("span");
            pieza.className = "confeti";
            const lado = 6 + Math.random() * 8;
            pieza.style.width = `${lado}px`;
            pieza.style.height = `${lado * (0.6 + Math.random() * 0.8)}px`;
            pieza.style.background = colores[i % colores.length];
            document.body.append(pieza);
            const angulo = Math.random() * Math.PI * 2;
            const velocidad = (120 + Math.random() * 220) * fuerza;
            const dx = Math.cos(angulo) * velocidad;
            const dy = Math.sin(angulo) * velocidad - 140 * fuerza;
            const giro = (Math.random() - 0.5) * 1080;
            pieza
                .animate(
                    [
                        { transform: `translate(${x}px, ${y}px) rotate(0deg) scale(1)`, opacity: 1 },
                        { transform: `translate(${x + dx * 0.6}px, ${y + dy * 0.6}px) rotate(${giro * 0.6}deg) scale(1)`, opacity: 1, offset: 0.45 },
                        { transform: `translate(${x + dx}px, ${y + dy + 260}px) rotate(${giro}deg) scale(0.6)`, opacity: 0 },
                    ],
                    { duration: 1100 + Math.random() * 700, easing: "cubic-bezier(0.2, 0.7, 0.4, 1)" },
                )
                .finished.then(() => pieza.remove());
        }
    };
    const centro = (elemento) => {
        const caja = elemento.getBoundingClientRect();
        return [caja.left + caja.width / 2, caja.top + caja.height / 2];
    };

    // ── Títulos palabra por palabra ─────────────────────────────────────────
    for (const titulo of document.querySelectorAll(".titulo-pagina, .veredicto-titulo, .acceso-arte h2, .titulo-bloque")) {
        if ([...titulo.childNodes].some((nodo) => nodo.nodeType !== Node.TEXT_NODE)) continue;
        const partes = titulo.textContent.trim().split(/(\s+)/);
        // Las palabras van en un solo contenedor: algunos títulos son flex y separarían
        // cada palabra como un elemento aparte.
        // Los lectores de pantalla leen el texto entero de una copia oculta: algunos
        // leerían cada palabra animada como un elemento aparte. No se usa
        // `aria-label` porque no vale en un párrafo como el título del dictamen.
        const entero = document.createElement("span");
        entero.className = "solo-lectores";
        entero.textContent = titulo.textContent.trim();
        const frase = document.createElement("span");
        frase.setAttribute("aria-hidden", "true");
        titulo.replaceChildren(entero, frase);
        let i = 0;
        for (const parte of partes) {
            if (/^\s+$/.test(parte)) {
                frase.append(" ");
                continue;
            }
            const palabra = document.createElement("span");
            palabra.className = "palabra";
            const interior = document.createElement("span");
            interior.style.setProperty("--i", i++);
            interior.textContent = parte;
            palabra.append(interior);
            frase.append(palabra);
        }
    }

    // ── Cifras que cuentan desde cero ───────────────────────────────────────
    const contar = (elemento) => {
        const final = elemento.textContent.trim();
        const coincide = /^(-?)(\d+)(?:\.(\d+))?$/.exec(final);
        if (!coincide) return;
        const objetivo = Number(final);
        const decimales = coincide[3] ? coincide[3].length : 0;
        if (!objetivo) return;
        const duracion = 1400;
        const inicio = performance.now();
        const paso = (ahora) => {
            const t = Math.min(1, (ahora - inicio) / duracion);
            const suave = 1 - Math.pow(2, -10 * t);
            elemento.textContent = (objetivo * suave).toFixed(decimales);
            if (t < 1) {
                requestAnimationFrame(paso);
            } else {
                elemento.textContent = final;
                elemento.classList.add("contada");
            }
        };
        requestAnimationFrame(paso);
    };
    const contables = document.querySelectorAll(
        ".metrica-numero, .saldo-cifra .cantidad, .resumen-dato b, .contador, .pool-cadena b, .fila-wallet .saldo .cantidad",
    );
    const alVerse = new IntersectionObserver((entradas) => {
        for (const entrada of entradas) {
            if (!entrada.isIntersecting) continue;
            alVerse.unobserve(entrada.target);
            const hoja = entrada.target.querySelector(".cantidad") || entrada.target;
            contar(hoja);
        }
    });
    contables.forEach((elemento) => alVerse.observe(elemento));

    // ── Foco de luz e inclinación ───────────────────────────────────────────
    const CON_LUZ = ".mosaico, .metrica, .fila-wallet, .eslabon-cadena, .acceso-arte, .tarjeta-resultado, .error-arte";
    document.querySelectorAll(CON_LUZ).forEach((elemento) => elemento.classList.add("con-luz"));
    const INCLINABLES = ".metrica, .saldo-principal, .tarjeta-resultado, .acceso-arte, .error-arte, .veredicto";
    document.querySelectorAll(INCLINABLES).forEach((elemento) => elemento.classList.add("inclinable"));
    const IMANES = ".boton-primario, .boton-lima, .boton-tinta, .boton-grande";

    let ultimo = null;
    let cuadro = 0;
    document.addEventListener("pointermove", (evento) => {
        ultimo = evento;
        if (cuadro) return;
        cuadro = requestAnimationFrame(() => {
            cuadro = 0;
            const { clientX: x, clientY: y, target } = ultimo;
            if (!(target instanceof Element)) return;
            const luz = target.closest(".con-luz");
            if (luz) {
                const caja = luz.getBoundingClientRect();
                luz.style.setProperty("--mx", `${x - caja.left}px`);
                luz.style.setProperty("--my", `${y - caja.top}px`);
            }
            const inclinable = target.closest(".inclinable");
            if (inclinable) {
                const caja = inclinable.getBoundingClientRect();
                // Las tarjetas grandes se inclinan menos que las métricas.
                const maximo = caja.width > 420 ? 3 : 9;
                const px = (x - caja.left) / caja.width - 0.5;
                const py = (y - caja.top) / caja.height - 0.5;
                inclinable.classList.add("siguiendo");
                inclinable.style.setProperty("--rx", `${(-py * maximo).toFixed(2)}deg`);
                inclinable.style.setProperty("--ry", `${(px * maximo).toFixed(2)}deg`);
            }
            const iman = target.closest(IMANES);
            if (iman && !iman.classList.contains("ocupado")) {
                const caja = iman.getBoundingClientRect();
                const dx = x - (caja.left + caja.width / 2);
                const dy = y - (caja.top + caja.height / 2);
                iman.style.translate = `${(dx * 0.12).toFixed(1)}px ${(dy * 0.25).toFixed(1)}px`;
            }
        });
    });
    document.addEventListener("pointerout", (evento) => {
        if (!(evento.target instanceof Element)) return;
        const destino = evento.relatedTarget instanceof Element ? evento.relatedTarget : null;
        const inclinable = evento.target.closest(".inclinable");
        if (inclinable && !inclinable.contains(destino)) {
            inclinable.classList.remove("siguiendo");
            inclinable.style.setProperty("--rx", "0deg");
            inclinable.style.setProperty("--ry", "0deg");
        }
        const iman = evento.target.closest(IMANES);
        if (iman && !iman.contains(destino)) iman.style.translate = "";
        const luz = evento.target.closest(".con-luz");
        if (luz && !luz.contains(destino)) {
            luz.style.removeProperty("--mx");
            luz.style.removeProperty("--my");
        }
    });

    // ── Onda al presionar un botón y salto al copiar ────────────────────────
    document.addEventListener("pointerdown", (evento) => {
        const boton = evento.target instanceof Element && evento.target.closest(".boton");
        if (!boton) return;
        const caja = boton.getBoundingClientRect();
        const onda = document.createElement("span");
        onda.className = "onda";
        onda.setAttribute("aria-hidden", "true");
        onda.style.left = `${evento.clientX - caja.left}px`;
        onda.style.top = `${evento.clientY - caja.top}px`;
        boton.append(onda);
        onda.addEventListener("animationend", () => onda.remove());
    });
    document.addEventListener("click", (evento) => {
        const boton = evento.target instanceof Element && evento.target.closest(".copiar");
        if (!boton) return;
        boton.classList.remove("copiado");
        void boton.offsetWidth;
        boton.classList.add("copiado");
        const [x, y] = centro(boton);
        confeti(x, y, 12, 0.45);
    });
    document.addEventListener("animationend", (evento) => {
        if (evento.animationName === "copiado") evento.target.classList.remove("copiado");
    });

    // ── Celebraciones de los resultados ─────────────────────────────────────
    const celebrar = (elemento, retraso, cantidad, fuerza) => {
        if (!elemento) return;
        setTimeout(() => {
            const [x, y] = centro(elemento);
            confeti(x, y, cantidad, fuerza);
        }, retraso);
    };
    // El bloque recién cerrado cae, se sella y explota en bloquecitos.
    celebrar(document.querySelector(".cadena-resultado .es-ultimo"), 1500, 70, 1.2);
    // Registro recibido.
    celebrar(document.querySelector(".tarjeta-resultado .sello"), 500, 50, 1);
    // Una transacción que entró al pool, o una cuenta aprobada.
    const aceptada = document.querySelector(".exito.resultado:not(:has(.cadena-resultado))");
    celebrar(aceptada, 450, 36, 0.8);
    celebrar(document.querySelector(".avisos .exito"), 300, 30, 0.7);

    // La transacción recién propuesta se enciende en la tabla de abajo.
    for (const titulo of document.querySelectorAll(".resultado .ficha dt")) {
        if (titulo.textContent.trim() !== "Transacción") continue;
        const valor = titulo.nextElementSibling?.querySelector("[data-copiar]")?.dataset.copiar;
        if (!valor) continue;
        for (const fila of document.querySelectorAll("tbody tr")) {
            const primera = fila.querySelector("td [data-copiar]");
            if (primera?.dataset.copiar === valor) fila.classList.add("fila-nueva");
        }
    }

    // ── Escaneo de la cadena antes de mostrar el dictamen ───────────────────
    // Es decorativo (aria-hidden): el dictamen ya está en la página y sólo se oculta
    // mientras dura. En una cadena alterada se recorren los bloques hasta el índice
    // roto, que es el único dato que trae el dictamen; en una válida, una fila genérica.
    const veredicto = document.querySelector(".veredicto");
    if (veredicto) {
        const invalido = veredicto.classList.contains("veredicto-invalido");
        const indiceRoto = invalido ? Number(veredicto.querySelector("code")?.textContent) : NaN;
        const roto = Number.isInteger(indiceRoto) ? indiceRoto : -1;
        // Con el índice roto se muestran hasta nueve bloques antes y dos después.
        const desde = invalido && roto >= 0 ? Math.max(0, roto - 9) : 0;
        const total = invalido && roto >= 0 ? roto + 3 : 8;

        const escaneo = document.createElement("div");
        escaneo.className = "escaneo";
        escaneo.setAttribute("aria-hidden", "true");
        const titulo = document.createElement("p");
        titulo.className = "escaneo-titulo";
        titulo.textContent = "Recalculando los hashes de la cadena…";
        const nodos = document.createElement("div");
        nodos.className = "escaneo-nodos";
        const lista = [];
        for (let i = desde; i < total; i++) {
            const nodo = document.createElement("span");
            nodo.className = "escaneo-nodo";
            nodo.textContent = invalido ? `#${i}` : "";
            nodos.append(nodo);
            lista.push({ nodo, indice: i });
            if (i < total - 1) {
                const union = document.createElement("span");
                union.className = "escaneo-union";
                nodos.append(union);
            }
        }
        const hash = document.createElement("p");
        hash.className = "escaneo-hash";
        escaneo.append(titulo, nodos, hash);
        veredicto.before(escaneo);
        veredicto.classList.add("esperando-escaneo");

        const hexes = setInterval(() => {
            hash.textContent = `sha256 → ${barajar(64)}`;
        }, 50);
        let paso = 0;
        const avanzar = () => {
            const actual = lista[paso];
            if (actual) {
                if (invalido && actual.indice === roto) {
                    actual.nodo.classList.add("roto");
                    titulo.textContent = `El bloque #${roto} no coincide`;
                    lista.slice(paso + 1).forEach(({ nodo }) => nodo.classList.add("contaminado"));
                    paso = lista.length;
                    setTimeout(terminar, 1100);
                    return;
                }
                actual.nodo.classList.add("revisado");
                if (!invalido) actual.nodo.textContent = "✓";
                paso++;
                setTimeout(avanzar, 150);
                return;
            }
            setTimeout(terminar, 250);
        };
        const terminar = () => {
            clearInterval(hexes);
            escaneo.classList.add("terminando");
            setTimeout(() => {
                escaneo.remove();
                veredicto.classList.remove("esperando-escaneo");
                if (!invalido) celebrar(veredicto.querySelector(".veredicto-icono"), 900, 60, 1.1);
            }, 380);
        };
        setTimeout(avanzar, 350);
    }
})();
