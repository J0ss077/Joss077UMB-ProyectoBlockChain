// El ayudante flotante. Al abrirlo pide a `/asistente/ahora` la explicación de la
// página y de la cuenta en palabras simples, y ofrece preguntas sugeridas. Lo que
// la persona escribe va a `/asistente/preguntar`, que contesta con Claude o con la
// guía local. La conversación se guarda en `sessionStorage` (por pestaña) para que
// no se pierda al cambiar de página; si el almacenamiento falla, sigue funcionando
// sin recordarla. Las respuestas se pintan siempre como texto, nunca como HTML.
(() => {
    const raiz = document.querySelector("[data-asistente]");
    if (!raiz) return;
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const $ = (selector) => raiz.querySelector(selector);

    const lanzador = $("[data-asistente-lanzador]");
    const panel = $("[data-asistente-panel]");
    const cuerpo = $("[data-asistente-cuerpo]");
    const ahora = $("[data-asistente-ahora]");
    const pagina = $("[data-asistente-pagina]");
    const puntos = $("[data-asistente-puntos]");
    const mensajes = $("[data-asistente-mensajes]");
    const chips = $("[data-asistente-chips]");
    const formulario = $("[data-asistente-formulario]");
    const campo = $("[data-asistente-pregunta]");
    const punto = $("[data-asistente-punto]");
    const teaser = $("[data-asistente-teaser]");

    const CLAVE = "asistente:" + (raiz.dataset.usuario || "visitante");
    const leer = () => {
        try {
            return JSON.parse(sessionStorage.getItem(CLAVE)) || {};
        } catch {
            return {};
        }
    };
    const guardar = () => {
        try {
            sessionStorage.setItem(CLAVE, JSON.stringify({ abierto: !panel.hidden, historial }));
        } catch {}
    };

    let historial = Array.isArray(leer().historial) ? leer().historial : [];
    let ocupado = false;

    // El aviso visible en la página (la burbuja del último envío, por ejemplo): el
    // ayudante lo ofrece explicar y se lo pasa al servidor como contexto.
    // Se lee al cargar porque los avisos de éxito se van solos a los pocos segundos.
    const textoDe = (burbuja) => (burbuja ? burbuja.innerText.replace(/\s+/g, " ").trim().slice(0, 300) : "");
    const avisoInicial = textoDe(document.querySelector("[data-burbuja]"));
    const avisoVisible = () => textoDe(document.querySelector("[data-burbuja]:not(.cerrando)")) || avisoInicial;

    // ── Pintado ────────────────────────────────────────────────────────────
    // Un texto con párrafos, listas con guiones y **negritas**, armado con nodos.
    const pintarTexto = (contenedor, texto) => {
        const conNegritas = (destino, linea) => {
            linea.split(/(\*\*[^*]+\*\*)/).forEach((parte) => {
                if (/^\*\*[^*]+\*\*$/.test(parte)) {
                    const b = document.createElement("b");
                    b.textContent = parte.slice(2, -2);
                    destino.append(b);
                } else if (parte) {
                    destino.append(parte);
                }
            });
        };
        let lista = null;
        texto.split("\n").forEach((cruda) => {
            const linea = cruda.trim();
            if (!linea) {
                lista = null;
                return;
            }
            const item = linea.match(/^(?:[-•*]|\d+[.)])\s+(.*)$/);
            if (item) {
                if (!lista) {
                    lista = document.createElement("ul");
                    contenedor.append(lista);
                }
                const li = document.createElement("li");
                conNegritas(li, item[1]);
                lista.append(li);
                return;
            }
            lista = null;
            const p = document.createElement("p");
            conNegritas(p, linea.replace(/^#+\s*/, ""));
            contenedor.append(p);
        });
    };

    const agregarMensaje = (rol, texto, { fuente, animar = true } = {}) => {
        const li = document.createElement("li");
        li.className = "asistente-mensaje asistente-mensaje-" + rol;
        if (!animar) li.classList.add("sin-animar");
        const quien = document.createElement("span");
        quien.className = "solo-lectores";
        quien.textContent = (rol === "persona" ? tr("Tú") : tr("Ayudante")) + ": ";
        li.append(quien);
        const globo = document.createElement("div");
        globo.className = "asistente-globo";
        if (rol === "persona") globo.textContent = texto;
        else pintarTexto(globo, texto);
        li.append(globo);
        if (fuente) {
            const sello = document.createElement("span");
            sello.className = "asistente-fuente";
            sello.textContent = fuente === "ia" ? tr("Respuesta con IA") : tr("Guía rápida");
            li.append(sello);
        }
        mensajes.append(li);
        // Una respuesta larga se muestra desde su comienzo, no desde el final.
        if (rol === "ayudante" && animar) cuerpo.scrollTop = li.offsetTop - 12;
        else bajar();
        return li;
    };

    const bajar = () => {
        cuerpo.scrollTop = cuerpo.scrollHeight;
    };

    const pintarChips = (sugerencias) => {
        chips.replaceChildren();
        (sugerencias || []).forEach(({ clave, texto }) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "asistente-chip";
            chip.textContent = texto;
            chip.addEventListener("click", () => preguntar(texto, clave));
            chips.append(chip);
        });
    };

    const escribiendo = () => {
        const li = document.createElement("li");
        li.className = "asistente-mensaje asistente-mensaje-ayudante asistente-escribiendo";
        li.innerHTML = '<div class="asistente-globo"><i></i><i></i><i></i></div>';
        const leyenda = document.createElement("span");
        leyenda.className = "solo-lectores";
        leyenda.textContent = tr("Pensando…");
        li.prepend(leyenda);
        mensajes.append(li);
        bajar();
        return li;
    };

    // ── Datos ──────────────────────────────────────────────────────────────
    let cargado = false;
    const cargarAhora = async () => {
        ahora.classList.add("cargando");
        try {
            const url = raiz.dataset.ahora + "?pagina=" + encodeURIComponent(location.pathname);
            const respuesta = await fetch(url, { headers: { Accept: "application/json" } });
            if (!respuesta.ok) throw new Error(String(respuesta.status));
            const datos = await respuesta.json();
            pagina.textContent = datos.pagina || "";
            puntos.replaceChildren(
                ...datos.puntos.map((texto) => {
                    const li = document.createElement("li");
                    li.textContent = texto;
                    return li;
                }),
            );
            ahora.hidden = !datos.pagina && !datos.puntos.length;
            if (!historial.length) pintarChips(datos.sugerencias);
            cargado = true;
        } catch {
            ahora.hidden = true;
        } finally {
            ahora.classList.remove("cargando");
        }
    };

    const preguntar = async (texto, tema) => {
        texto = (texto || "").trim();
        if (!texto || ocupado) return;
        ocupado = true;
        formulario.classList.add("ocupado");
        chips.replaceChildren();
        agregarMensaje("persona", texto);
        const anteriores = historial.slice(-10);
        historial.push({ rol: "persona", texto });
        guardar();
        const espera = escribiendo();
        try {
            const respuesta = await fetch(raiz.dataset.preguntar, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({
                    pregunta: texto,
                    tema: tema || "",
                    pagina: location.pathname,
                    aviso: avisoVisible(),
                    historial: anteriores,
                }),
            });
            if (!respuesta.ok) throw new Error(String(respuesta.status));
            const datos = await respuesta.json();
            espera.remove();
            agregarMensaje("ayudante", datos.respuesta, { fuente: datos.fuente });
            historial.push({ rol: "ayudante", texto: datos.respuesta, fuente: datos.fuente });
            guardar();
            pintarChips(datos.sugerencias);
        } catch {
            espera.remove();
            agregarMensaje("ayudante", tr("No pude conectarme. Revisa tu conexión e inténtalo otra vez."));
        } finally {
            ocupado = false;
            formulario.classList.remove("ocupado");
        }
    };

    // ── Abrir y cerrar ─────────────────────────────────────────────────────
    const abrir = ({ enfocar = true } = {}) => {
        panel.hidden = false;
        raiz.classList.add("abierto");
        lanzador.setAttribute("aria-expanded", "true");
        punto.hidden = true;
        teaser.hidden = true;
        if (!cargado) cargarAhora();
        bajar();
        if (enfocar) campo.focus();
        guardar();
    };
    const cerrar = () => {
        panel.hidden = true;
        raiz.classList.remove("abierto");
        lanzador.setAttribute("aria-expanded", "false");
        guardar();
    };

    lanzador.addEventListener("click", () => {
        if (panel.hidden) abrir();
        else {
            cerrar();
            lanzador.focus();
        }
    });
    $("[data-asistente-cerrar]").addEventListener("click", () => {
        cerrar();
        lanzador.focus();
    });
    $("[data-asistente-reiniciar]").addEventListener("click", () => {
        historial = [];
        mensajes.replaceChildren();
        guardar();
        cargado = false;
        cargarAhora();
        campo.focus();
    });
    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape" && !panel.hidden && raiz.contains(document.activeElement)) {
            evento.stopPropagation();
            cerrar();
            lanzador.focus();
        }
    });

    formulario.addEventListener("submit", (evento) => {
        evento.preventDefault();
        const texto = campo.value;
        campo.value = "";
        ajustarAltura();
        preguntar(texto);
    });
    // Enter envía; Mayúsculas+Enter hace salto de línea.
    campo.addEventListener("keydown", (evento) => {
        if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
            evento.preventDefault();
            formulario.requestSubmit();
        }
    });
    const ajustarAltura = () => {
        campo.style.height = "auto";
        campo.style.height = Math.min(campo.scrollHeight, 120) + "px";
    };
    campo.addEventListener("input", ajustarAltura);

    // ── Al cargar la página ────────────────────────────────────────────────
    historial.forEach(({ rol, texto, fuente }) => {
        if ((rol === "persona" || rol === "ayudante") && typeof texto === "string") {
            agregarMensaje(rol, texto, { fuente, animar: false });
        }
    });

    // Si la página trae un aviso (un envío hecho o rechazado), el botón lo marca
    // y, un momento después, ofrece explicarlo.
    if (avisoInicial) {
        punto.hidden = false;
        setTimeout(() => {
            if (panel.hidden) teaser.hidden = false;
        }, 1200);
    }
    $("[data-asistente-explicar]").addEventListener("click", () => {
        const aviso = avisoVisible();
        abrir({ enfocar: false });
        preguntar(tr("Explícame este aviso") + (aviso ? ": «" + aviso + "»" : ""));
    });
    $("[data-asistente-teaser-cerrar]").addEventListener("click", () => {
        teaser.hidden = true;
    });

    if (leer().abierto) abrir({ enfocar: false });
})();
