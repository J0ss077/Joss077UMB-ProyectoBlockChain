// Las estadísticas: filtros y gráficas que se resuelven en el navegador con los
// movimientos que el servidor dejó en `#datos-estadisticas`. Cambiar un filtro no
// recarga la página: las cifras cuentan hasta su nuevo valor, las barras crecen o
// se encogen en su lugar y la línea del saldo se transforma en la nueva. Con
// movimiento reducido todo cambia de golpe, sin perder nada de lo que se muestra.
(() => {
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;

    // El selector del administrador va a la página del elegido apenas se cambia.
    const elegir = document.querySelector("[data-elegir-usuario]");
    if (elegir) {
        elegir.querySelector("select").addEventListener("change", () => elegir.requestSubmit());
    }

    const fuente = document.getElementById("datos-estadisticas");
    if (!fuente) return;

    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const idioma = document.documentElement.lang || "es";
    const DIA = 86400000;
    const todos = JSON.parse(fuente.textContent).map((m) => ({
        ...m,
        fecha: new Date(m.fecha),
        monto: Number(m.monto),
    }));

    const ESTADOS = [
        ["confirmed", tr("Completada")],
        ["pending", tr("En espera")],
        ["rejected", tr("Rechazada")],
    ];
    const NOMBRE_DEL_ESTADO = Object.fromEntries(ESTADOS);

    // Los montos se muestran como en el resto de la página: hasta ocho decimales
    // y sin ceros de más a la derecha.
    const sinCeros = (texto) => (texto.includes(".") ? texto.replace(/0+$/, "").replace(/\.$/, "") : texto);
    const monto = (n) => (n < 0 ? "−" : "") + sinCeros(Math.abs(n).toFixed(8));
    const corto = (n) => (n < 0 ? "−" : "") + sinCeros(Math.abs(n).toFixed(2));
    const veces = (n) => (n === 1 ? tr("{n} vez") : tr("{n} veces")).replace("{n}", n);
    const persona = (nombre) => tr(nombre);
    const fechaLarga = new Intl.DateTimeFormat(idioma, { dateStyle: "medium", timeStyle: "short" });
    const fechaDia = new Intl.DateTimeFormat(idioma, { day: "numeric", month: "short" });
    const fechaMes = new Intl.DateTimeFormat(idioma, { month: "short", year: "2-digit" });
    const diaSemana = new Intl.DateTimeFormat(idioma, { weekday: "short" });

    const crear = (etiqueta, clase, texto) => {
        const elemento = document.createElement(etiqueta);
        if (clase) elemento.className = clase;
        if (texto !== undefined) elemento.textContent = texto;
        return elemento;
    };
    const SVG = "http://www.w3.org/2000/svg";
    const crearSvg = (etiqueta, atributos) => {
        const elemento = document.createElementNS(SVG, etiqueta);
        for (const [clave, valor] of Object.entries(atributos)) elemento.setAttribute(clave, valor);
        return elemento;
    };

    // ── El globo de las gráficas: al pasar el puntero o enfocar una marca ──────
    const globo = document.querySelector("[data-globo]");
    const lineasDelGlobo = new WeakMap();
    const mostrarGlobo = (marca, x, y) => {
        const lineas = lineasDelGlobo.get(marca);
        if (!lineas) return;
        globo.replaceChildren(
            ...lineas.map(([texto, clase], i) => crear(i === 0 ? "b" : "span", clase || "", texto)),
        );
        globo.hidden = false;
        const ancho = globo.offsetWidth;
        const izquierda = Math.min(window.innerWidth - ancho - 12, Math.max(12, x - ancho / 2));
        globo.style.left = `${izquierda}px`;
        globo.style.top = `${Math.max(12, y - globo.offsetHeight - 14)}px`;
    };
    const ocultarGlobo = () => {
        globo.hidden = true;
    };
    const conGlobo = (marca, lineas) => {
        lineasDelGlobo.set(marca, lineas);
        marca.setAttribute("aria-label", lineas.map(([texto]) => texto).join(", "));
    };
    document.addEventListener("pointerover", (evento) => {
        const marca = evento.target.closest("[data-marca]");
        if (marca) mostrarGlobo(marca, evento.clientX, evento.clientY);
    });
    document.addEventListener("pointermove", (evento) => {
        const marca = evento.target.closest("[data-marca]");
        if (marca) mostrarGlobo(marca, evento.clientX, evento.clientY);
        else if (!evento.target.closest("[data-grafica='saldo']")) ocultarGlobo();
    });
    document.addEventListener("focusin", (evento) => {
        const marca = evento.target.closest("[data-marca]");
        if (!marca) return;
        const caja = marca.getBoundingClientRect();
        mostrarGlobo(marca, caja.left + caja.width / 2, caja.top);
    });
    document.addEventListener("focusout", ocultarGlobo);
    window.addEventListener("scroll", ocultarGlobo, { passive: true });

    // ── Filtros ───────────────────────────────────────────────────────────────
    const filtros = document.querySelector("[data-filtros]");
    const limpiar = filtros.querySelector("[data-limpiar]");
    const POR_DEFECTO = { periodo: "todo", tipo: "todo", estado: "todo", persona: "todo" };
    const leerFiltros = () => {
        const valores = {};
        for (const nombre of Object.keys(POR_DEFECTO)) {
            const marcado = filtros.querySelector(`[name="${nombre}"]:checked`);
            valores[nombre] = marcado ? marcado.value : filtros.querySelector(`[name="${nombre}"]`).value;
        }
        return valores;
    };
    filtros.addEventListener("change", () => pintar());
    limpiar.addEventListener("click", () => {
        for (const [nombre, valor] of Object.entries(POR_DEFECTO)) {
            const radio = filtros.querySelector(`[name="${nombre}"][value="${valor}"]`);
            if (radio) radio.checked = true;
            else filtros.querySelector(`[name="${nombre}"]`).value = valor;
        }
        pintar();
    });

    // El tiempo que se mira: los últimos N días, o desde el primer movimiento.
    const rango = (periodo) => {
        const fin = new Date();
        if (periodo === "todo") {
            const primero = todos.length ? todos[0].fecha : fin;
            return [new Date(Math.min(primero, fin - DIA)), fin];
        }
        return [new Date(fin - Number(periodo) * DIA), fin];
    };

    // ── Cifras que cuentan del valor anterior al nuevo ──────────────────────
    const animarCifra = (elemento, valor, aTexto) => {
        const desde = elemento._valor ?? 0;
        elemento._valor = valor;
        cancelAnimationFrame(elemento._cuadro);
        if (quieto || desde === valor) {
            elemento.textContent = aTexto(valor);
            return;
        }
        const inicio = performance.now();
        const paso = (ahora) => {
            const t = Math.min(1, (ahora - inicio) / 700);
            const suave = 1 - Math.pow(1 - t, 3);
            elemento.textContent = aTexto(desde + (valor - desde) * suave);
            if (t < 1) elemento._cuadro = requestAnimationFrame(paso);
            else elemento.textContent = aTexto(valor);
        };
        elemento._cuadro = requestAnimationFrame(paso);
    };
    const cifra = (nombre) => document.querySelector(`[data-cifra="${nombre}"]`);
    const nota = (nombre) => document.querySelector(`[data-nota="${nombre}"]`);

    const pintarCifras = (filtrados) => {
        const completados = filtrados.filter((m) => m.estado === "confirmed");
        const entra = completados.filter((m) => m.tipo === "entra");
        const sale = completados.filter((m) => m.tipo === "sale");
        const recibido = entra.reduce((suma, m) => suma + m.monto, 0);
        const enviado = sale.reduce((suma, m) => suma + m.monto, 0);
        animarCifra(cifra("recibido"), recibido, monto);
        animarCifra(cifra("enviado"), enviado, monto);
        animarCifra(cifra("balance"), recibido - enviado, monto);
        animarCifra(cifra("movimientos"), filtrados.length, (n) => String(Math.round(n)));
        nota("recibido").textContent = veces(entra.length);
        nota("enviado").textContent = veces(sale.length);
        nota("movimientos").textContent = tr("{n} completados").replace("{n}", completados.length);
        const balance = cifra("balance").closest(".est-cifra");
        balance.classList.toggle("positivo", recibido - enviado > 0);
        balance.classList.toggle("negativo", recibido - enviado < 0);
    };

    // ── Lo que entró y salió, por día, semana o mes ─────────────────────────
    const inicioDe = (fecha, paso) => {
        const d = new Date(fecha.getFullYear(), fecha.getMonth(), paso === "mes" ? 1 : fecha.getDate());
        if (paso === "semana") d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
        return d;
    };
    const siguiente = (fecha, paso) => {
        const d = new Date(fecha);
        if (paso === "mes") d.setMonth(d.getMonth() + 1);
        else d.setDate(d.getDate() + (paso === "semana" ? 7 : 1));
        return d;
    };
    const tramos = (desde, hasta) => {
        const dias = (hasta - desde) / DIA;
        const paso = dias <= 31 ? "dia" : dias <= 120 ? "semana" : "mes";
        const lista = [];
        for (let d = inicioDe(desde, paso); d <= hasta; d = siguiente(d, paso)) {
            lista.push({ desde: d, hasta: siguiente(d, paso), entra: 0, sale: 0, n: 0 });
        }
        return { paso, lista };
    };
    const nombreDelTramo = (tramo, paso) => {
        if (paso === "mes") return fechaMes.format(tramo.desde);
        if (paso === "dia") return fechaDia.format(tramo.desde);
        const fin = new Date(tramo.hasta - DIA);
        return `${fechaDia.format(tramo.desde)} – ${fechaDia.format(fin)}`;
    };

    const flujo = document.querySelector("[data-grafica='flujo']");
    let clavesDelFlujo = "";
    const pintarFlujo = (filtrados, desde, hasta) => {
        const { paso, lista } = tramos(desde, hasta);
        for (const m of filtrados) {
            if (m.estado !== "confirmed") continue;
            const tramo = lista.find((t) => m.fecha >= t.desde && m.fecha < t.hasta);
            if (!tramo) continue;
            tramo[m.tipo] += m.monto;
            tramo.n += 1;
        }
        const mayor = Math.max(0, ...lista.map((t) => Math.max(t.entra, t.sale)));
        const claves = paso + lista.length + lista[0]?.desde.getTime();
        // Con los mismos tramos las barras cambian de alto en su lugar; con otros, la
        // gráfica se arma de nuevo y las barras crecen desde la base.
        if (claves !== clavesDelFlujo) {
            clavesDelFlujo = claves;
            const cada = Math.ceil(lista.length / 8);
            const plano = crear("div", "est-plano");
            plano.append(crear("div", "est-guias"));
            const columnas = crear("div", "est-columnas");
            lista.forEach((tramo, i) => {
                const columna = crear("div", "est-columna");
                columna.tabIndex = 0;
                columna.dataset.marca = "";
                const par = crear("div", "est-par");
                par.append(crear("i", "barra entra"), crear("i", "barra sale"));
                columna.append(par, crear("span", "est-eje", i % cada === 0 ? nombreDelTramo(tramo, paso) : ""));
                columnas.append(columna);
            });
            plano.append(columnas);
            flujo.replaceChildren(plano, crear("p", "est-sin", tr("No hay movimientos completados con estos filtros.")));
            flujo.classList.remove("listo");
            void flujo.offsetWidth;
        }
        const guias = flujo.querySelector(".est-guias");
        guias.replaceChildren(
            ...[1, 0.5, 0].map((parte) => crear("span", "", mayor ? corto(mayor * parte) : "0")),
        );
        flujo.querySelectorAll(".est-columna").forEach((columna, i) => {
            const tramo = lista[i];
            const [entra, sale] = columna.querySelectorAll(".barra");
            entra.style.setProperty("--alto", mayor ? `${(tramo.entra / mayor) * 100}%` : "0%");
            sale.style.setProperty("--alto", mayor ? `${(tramo.sale / mayor) * 100}%` : "0%");
            conGlobo(columna, [
                [nombreDelTramo(tramo, paso)],
                [`${tr("Recibido")}: +${monto(tramo.entra)}`, "entra"],
                [`${tr("Enviado")}: −${monto(tramo.sale)}`, "sale"],
            ]);
        });
        flujo.classList.toggle("sin-datos", mayor === 0);
        requestAnimationFrame(() => flujo.classList.add("listo"));
    };

    // ── Cómo fue cambiando el saldo ─────────────────────────────────────────
    // La línea sale de muestrear el saldo en puntos fijos del tiempo: así la
    // anterior y la nueva tienen los mismos puntos y una se transforma en la otra.
    const MUESTRAS = 120;
    const saldo = document.querySelector("[data-grafica='saldo']");
    const lienzo = crearSvg("svg", { viewBox: "0 0 100 100", preserveAspectRatio: "none", "aria-hidden": "true" });
    const area = crearSvg("path", { class: "area" });
    const cero = crearSvg("line", { class: "cero", x1: 0, x2: 100 });
    const trazo = crearSvg("path", { class: "trazo" });
    lienzo.append(area, cero, trazo);
    const cruz = crear("div", "est-cruz");
    const punto = crear("div", "est-punto");
    const topeAlto = crear("span", "est-tope arriba");
    const topeBajo = crear("span", "est-tope abajo");
    const ejeSaldo = crear("div", "est-eje-linea");
    saldo.append(lienzo, cruz, punto, topeAlto, topeBajo, ejeSaldo);
    saldo.setAttribute("role", "img");
    let muestrasPrevias = null;
    let muestrasActuales = [];
    let escala = { bajo: 0, alto: 1 };

    const dibujarLinea = (valores, bajo, alto) => {
        const y = (v) => 96 - ((v - bajo) / (alto - bajo || 1)) * 92;
        const puntos = valores.map((v, i) => `${(i / (valores.length - 1)) * 100},${y(v).toFixed(2)}`);
        trazo.setAttribute("d", `M${puntos.join("L")}`);
        area.setAttribute("d", `M0,${y(Math.max(bajo, 0))}L${puntos.join("L")}L100,${y(Math.max(bajo, 0))}Z`);
        cero.setAttribute("y1", y(0));
        cero.setAttribute("y2", y(0));
        cero.style.display = bajo < 0 ? "" : "none";
    };

    const pintarSaldo = (desde, hasta) => {
        const completados = todos.filter((m) => m.estado === "confirmed");
        const signo = (m) => (m.tipo === "entra" ? m.monto : -m.monto);
        let acumulado = completados.filter((m) => m.fecha < desde).reduce((s, m) => s + signo(m), 0);
        const dentro = completados.filter((m) => m.fecha >= desde && m.fecha <= hasta);
        const valores = [];
        let j = 0;
        for (let i = 0; i < MUESTRAS; i += 1) {
            const momento = desde.getTime() + ((hasta - desde) * i) / (MUESTRAS - 1);
            while (j < dentro.length && dentro[j].fecha.getTime() <= momento) {
                acumulado += signo(dentro[j]);
                j += 1;
            }
            valores.push(acumulado);
        }
        const alto = Math.max(...valores, 0) * 1.08 || 1;
        const bajo = Math.min(...valores, 0) * 1.08;
        escala = { bajo, alto };
        muestrasActuales = valores.map((valor, i) => ({
            valor,
            momento: new Date(desde.getTime() + ((hasta - desde) * i) / (MUESTRAS - 1)),
        }));
        topeAlto.textContent = corto(alto / 1.08);
        topeBajo.textContent = corto(bajo / 1.08);
        ejeSaldo.replaceChildren(crear("span", "", fechaDia.format(desde)), crear("span", "", fechaDia.format(hasta)));
        saldo.setAttribute(
            "aria-label",
            `${tr("Saldo")}: ${monto(valores[0])} → ${monto(valores[valores.length - 1])}`,
        );

        const previas = muestrasPrevias;
        muestrasPrevias = valores;
        cancelAnimationFrame(saldo._cuadro);
        if (quieto || !previas) {
            dibujarLinea(valores, bajo, alto);
            if (!quieto) saldo.classList.add("dibujando");
            return;
        }
        const escalaPrevia = saldo._escala || escala;
        saldo._escala = escala;
        const inicio = performance.now();
        const paso = (ahora) => {
            const t = Math.min(1, (ahora - inicio) / 650);
            const s = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
            const mezcla = (a, b) => a + (b - a) * s;
            dibujarLinea(
                valores.map((v, i) => mezcla(previas[i], v)),
                mezcla(escalaPrevia.bajo, bajo),
                mezcla(escalaPrevia.alto, alto),
            );
            if (t < 1) saldo._cuadro = requestAnimationFrame(paso);
        };
        saldo._cuadro = requestAnimationFrame(paso);
    };

    // La cruz sigue al puntero y el globo dice el saldo en ese momento.
    saldo.addEventListener("pointermove", (evento) => {
        const caja = saldo.getBoundingClientRect();
        const parte = Math.min(1, Math.max(0, (evento.clientX - caja.left) / caja.width));
        const i = Math.round(parte * (MUESTRAS - 1));
        const muestra = muestrasActuales[i];
        if (!muestra) return;
        const y = 96 - ((muestra.valor - escala.bajo) / (escala.alto - escala.bajo || 1)) * 92;
        const x = (i / (MUESTRAS - 1)) * 100;
        cruz.style.left = punto.style.left = `${x}%`;
        punto.style.top = `${y}%`;
        saldo.classList.add("apuntado");
        lineasDelGlobo.set(saldo, [[fechaLarga.format(muestra.momento)], [`${tr("Saldo")}: ${monto(muestra.valor)}`]]);
        mostrarGlobo(saldo, caja.left + (x / 100) * caja.width, caja.top + (y / 100) * caja.height);
    });
    saldo.addEventListener("pointerleave", () => {
        saldo.classList.remove("apuntado");
        ocultarGlobo();
    });

    // ── Cómo terminaron: completados, en espera y rechazados ────────────────
    const dona = document.querySelector("[data-grafica='estados']");
    const aro = crearSvg("svg", { viewBox: "0 0 42 42", class: "est-aro", "aria-hidden": "true" });
    aro.append(crearSvg("circle", { class: "fondo", cx: 21, cy: 21, r: 15.915 }));
    const segmentos = Object.fromEntries(
        ESTADOS.map(([clave]) => {
            const circulo = crearSvg("circle", { class: `segmento ${clave}`, cx: 21, cy: 21, r: 15.915 });
            aro.append(circulo);
            return [clave, circulo];
        }),
    );
    const centro = crear("div", "est-centro");
    const total = crear("b", "", "0");
    centro.append(total, crear("span", "", tr("movimientos")));
    const leyendaDona = crear("ul", "est-leyenda-dona");
    const filasDona = Object.fromEntries(
        ESTADOS.map(([clave, nombre]) => {
            const fila = crear("li", "");
            const valor = crear("b", "", "0");
            fila.append(crear("span", `pildora pildora-${clave}`, nombre), valor);
            leyendaDona.append(fila);
            return [clave, valor];
        }),
    );
    const caja = crear("div", "est-aro-caja");
    caja.append(aro, centro);
    dona.append(caja, leyendaDona);

    const pintarEstados = (filtradosSinEstado) => {
        const cuentas = { confirmed: 0, pending: 0, rejected: 0 };
        for (const m of filtradosSinEstado) cuentas[m.estado] += 1;
        const suma = filtradosSinEstado.length;
        let recorrido = 0;
        for (const [clave] of ESTADOS) {
            const parte = suma ? (cuentas[clave] / suma) * 100 : 0;
            // Un poco de aire entre segmentos, para que no se toquen.
            const visible = parte > 1.2 && parte < 100 ? parte - 1.2 : parte;
            segmentos[clave].style.strokeDasharray = `${visible} ${100 - visible}`;
            segmentos[clave].style.strokeDashoffset = `${25 - recorrido}`;
            recorrido += parte;
            const porcentaje = suma ? Math.round(parte) : 0;
            filasDona[clave].textContent = `${cuentas[clave]} · ${porcentaje}%`;
        }
        animarCifra(total, suma, (n) => String(Math.round(n)));
        dona.setAttribute(
            "aria-label",
            ESTADOS.map(([clave, nombre]) => `${nombre}: ${cuentas[clave]}`).join(", "),
        );
        dona.setAttribute("role", "img");
    };

    // ── Con quién se movió más dinero ───────────────────────────────────────
    const personas = document.querySelector("[data-grafica='personas']");
    const filasDePersonas = new Map();
    const sinPersonas = crear("li", "est-sin", tr("No hay movimientos completados con estos filtros."));
    const pintarPersonas = (filtrados) => {
        const sumas = new Map();
        for (const m of filtrados) {
            if (m.estado !== "confirmed") continue;
            const suma = sumas.get(m.persona) || { entra: 0, sale: 0, n: 0 };
            suma[m.tipo] += m.monto;
            suma.n += 1;
            sumas.set(m.persona, suma);
        }
        const orden = [...sumas.entries()]
            .sort((a, b) => b[1].entra + b[1].sale - (a[1].entra + a[1].sale))
            .slice(0, 6);
        const mayor = orden.length ? orden[0][1].entra + orden[0][1].sale : 0;
        const visibles = new Set(orden.map(([nombre]) => nombre));
        for (const [nombre, fila] of filasDePersonas) {
            if (!visibles.has(nombre)) {
                fila.remove();
                filasDePersonas.delete(nombre);
            }
        }
        for (const [nombre, suma] of orden) {
            let fila = filasDePersonas.get(nombre);
            if (!fila) {
                fila = crear("li", "est-persona");
                fila.tabIndex = 0;
                fila.dataset.marca = "";
                const cabeza = crear("div", "est-persona-cabeza");
                cabeza.append(crear("span", "est-persona-nombre", persona(nombre)), crear("b", "est-persona-total"));
                const pista = crear("div", "est-pista");
                pista.append(crear("i", "barra entra"), crear("i", "barra sale"));
                fila.append(cabeza, pista);
                filasDePersonas.set(nombre, fila);
            }
            personas.append(fila);
            fila.querySelector(".est-persona-total").textContent = monto(suma.entra + suma.sale);
            const [entra, sale] = fila.querySelectorAll(".barra");
            requestAnimationFrame(() => {
                entra.style.setProperty("--ancho", `${(suma.entra / mayor) * 100}%`);
                sale.style.setProperty("--ancho", `${(suma.sale / mayor) * 100}%`);
            });
            conGlobo(fila, [
                [persona(nombre)],
                [`${tr("Recibido")}: +${monto(suma.entra)}`, "entra"],
                [`${tr("Enviado")}: −${monto(suma.sale)}`, "sale"],
                [veces(suma.n)],
            ]);
        }
        if (orden.length) sinPersonas.remove();
        else personas.append(sinPersonas);
    };

    // ── Qué días hay más movimiento ─────────────────────────────────────────
    const semana = document.querySelector("[data-grafica='semana']");
    const dias = Array.from({ length: 7 }, (_, i) => {
        const columna = crear("div", "est-dia");
        columna.tabIndex = 0;
        columna.dataset.marca = "";
        const pista = crear("div", "est-dia-pista");
        pista.append(crear("i", "barra"));
        // El 1 de enero de 2024 fue lunes: de ahí salen los nombres de la semana.
        const nombre = diaSemana.format(new Date(2024, 0, 1 + i));
        columna.append(crear("b", "est-dia-n", "0"), pista, crear("span", "est-eje", nombre));
        semana.append(columna);
        return { columna, nombre };
    });
    const pintarSemana = (filtrados) => {
        const cuentas = Array(7).fill(0);
        for (const m of filtrados) cuentas[(m.fecha.getDay() + 6) % 7] += 1;
        const mayor = Math.max(...cuentas);
        dias.forEach(({ columna, nombre }, i) => {
            columna.querySelector(".barra").style.setProperty("--alto", mayor ? `${(cuentas[i] / mayor) * 100}%` : "0%");
            columna.querySelector(".est-dia-n").textContent = cuentas[i];
            columna.classList.toggle("pico", mayor > 0 && cuentas[i] === mayor);
            conGlobo(columna, [[nombre], [tr("{n} movimientos").replace("{n}", cuentas[i])]]);
        });
    };

    // ── La tabla, para leer lo mismo sin gráficas ───────────────────────────
    const tabla = document.querySelector("[data-tabla]");
    const cuentaTabla = document.querySelector("[data-cuenta-tabla]");
    const pintarTabla = (filtrados) => {
        const filas = [...filtrados].reverse().map((m) => {
            const fila = crear("tr", "");
            const signo = m.tipo === "entra" ? "+" : "−";
            const celdaMonto = crear("td", `numero ${m.tipo}`, `${signo}${monto(m.monto)}`);
            const celdaEstado = crear("td", "");
            celdaEstado.append(crear("span", `pildora pildora-${m.estado}`, NOMBRE_DEL_ESTADO[m.estado] || m.estado));
            fila.append(
                crear("td", "", fechaLarga.format(m.fecha)),
                crear("td", "", m.tipo === "entra" ? tr("Recibido") : tr("Enviado")),
                crear("td", "", persona(m.persona)),
                celdaEstado,
                celdaMonto,
            );
            return fila;
        });
        if (!filas.length) {
            const fila = crear("tr", "");
            const celda = crear("td", "est-sin", tr("No hay movimientos con estos filtros."));
            celda.colSpan = 5;
            fila.append(celda);
            filas.push(fila);
        }
        tabla.replaceChildren(...filas);
        cuentaTabla.textContent = filtrados.length;
    };

    // ── Todo junto ──────────────────────────────────────────────────────────
    const pintar = () => {
        const f = leerFiltros();
        const [desde, hasta] = rango(f.periodo);
        const enTiempo = todos.filter((m) => m.fecha >= desde && m.fecha <= hasta);
        const sinEstado = enTiempo.filter(
            (m) => (f.tipo === "todo" || m.tipo === f.tipo) && (f.persona === "todo" || m.persona === f.persona),
        );
        const filtrados = sinEstado.filter((m) => f.estado === "todo" || m.estado === f.estado);
        limpiar.hidden = Object.entries(POR_DEFECTO).every(([clave, valor]) => f[clave] === valor);
        pintarCifras(filtrados);
        pintarFlujo(filtrados, desde, hasta);
        pintarSaldo(desde, hasta);
        pintarEstados(sinEstado);
        pintarPersonas(filtrados);
        pintarSemana(filtrados);
        pintarTabla(filtrados);
    };

    document.documentElement.classList.add("con-estadisticas");
    pintar();
})();
