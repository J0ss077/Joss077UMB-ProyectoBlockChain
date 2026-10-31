// Editor de recorte de la foto de perfil. Al elegir una imagen (o al tocar
// «Editar» sobre la que ya está) se abre un diálogo con la imagen entera y, encima,
// un cuadro de recorte con la cuadrícula de tercios: se arrastra para moverlo y se
// tira de sus esquinas o se usan los botones de zoom para cambiar el tamaño; con el
// teclado, las flechas lo mueven y + y − acercan o alejan. Se puede girar de a 90°
// sin perder el encuadre —el cuadro gira con la imagen— y volver al encuadre
// inicial. El recorte es siempre cuadrado, como el avatar, y al lado se ve cómo va
// a quedar. «Guardar foto» dibuja ese cuadro en 512×512 y lo sube en
// lugar del archivo original. Sin JavaScript el formulario sube el archivo tal
// cual con su propio botón, y el servidor decide si sirve.
(() => {
    // Los textos a la vista pasan por `window.TEXTOS`, que pone `base.html`: vacío en
    // español y con las traducciones cuando la página va en inglés.
    const tr = (texto) => (window.TEXTOS && window.TEXTOS[texto]) || texto;
    const formulario = document.querySelector("[data-foto-formulario]");
    const dialogo = document.querySelector("[data-foto-editor]");
    if (!formulario || !dialogo || typeof dialogo.showModal !== "function") return;

    const entrada = formulario.querySelector('input[type="file"]');
    const estado = document.querySelector("[data-foto-estado]");
    const escenario = dialogo.querySelector("[data-foto-escenario]");
    const lienzo = dialogo.querySelector("[data-foto-lienzo]");
    const recorte = dialogo.querySelector("[data-foto-recorte]");
    const previa = dialogo.querySelector("[data-foto-previa]");
    const SALIDA = 512;
    // Lado máximo de la imagen con la que se trabaja: una foto de 4000 px del
    // teléfono no aporta nada a un avatar de 512 y haría lento cada redibujo.
    const LADO_DE_TRABAJO = 2048;
    // Lado mínimo del cuadro en pantalla, para que siempre se pueda agarrar.
    const MINIMO_EN_PANTALLA = 48;
    const PASO = 8;
    // Cuánto achica (acerca) o agranda (aleja) el cuadro cada toque de zoom.
    const FACTOR_DE_ZOOM = 0.8;
    // Aire entre la imagen y el borde del escenario, para que las esquinas del
    // cuadro se vean y se puedan agarrar aunque el recorte toque el borde.
    const AIRE = 14;

    // Con JavaScript el botón de subir sin editar sobra, y «Editar» ya funciona.
    for (const sinJs of formulario.querySelectorAll("[data-solo-sin-js]")) sinJs.hidden = true;
    const editar = document.querySelector("[data-foto-editar]");
    if (editar) editar.hidden = false;

    let original = null; // la imagen tal como llegó
    let giro = 0; // cuartos de vuelta en sentido horario
    let fuente = null; // la imagen ya girada, en un lienzo de trabajo
    // El cuadro vive en coordenadas de `fuente`: no cambia si cambia la pantalla.
    const cuadro = { x: 0, y: 0, lado: 0 };
    // Cómo se ve `fuente` dentro del escenario: escala y desplazamiento.
    let escala = 1;
    let margenX = 0;
    let margenY = 0;

    const prepararFuente = () => {
        const reduccion = Math.min(
            1,
            LADO_DE_TRABAJO / Math.max(original.naturalWidth, original.naturalHeight),
        );
        const ancho = Math.round(original.naturalWidth * reduccion);
        const alto = Math.round(original.naturalHeight * reduccion);
        const acostada = giro % 2 === 1;
        fuente = document.createElement("canvas");
        fuente.width = acostada ? alto : ancho;
        fuente.height = acostada ? ancho : alto;
        const ctx = fuente.getContext("2d");
        ctx.translate(fuente.width / 2, fuente.height / 2);
        ctx.rotate((giro * Math.PI) / 2);
        ctx.drawImage(original, -ancho / 2, -alto / 2, ancho, alto);
    };

    const minimo = () => Math.min(MINIMO_EN_PANTALLA / escala, fuente.width, fuente.height);

    const acotar = () => {
        cuadro.lado = Math.max(minimo(), Math.min(cuadro.lado, fuente.width, fuente.height));
        cuadro.x = Math.max(0, Math.min(cuadro.x, fuente.width - cuadro.lado));
        cuadro.y = Math.max(0, Math.min(cuadro.y, fuente.height - cuadro.lado));
    };

    // El encuadre inicial: el cuadrado más grande que cabe, centrado.
    const encuadreInicial = () => {
        cuadro.lado = Math.min(fuente.width, fuente.height);
        cuadro.x = (fuente.width - cuadro.lado) / 2;
        cuadro.y = (fuente.height - cuadro.lado) / 2;
    };

    // Cambia el lado del cuadro sin mover su centro, dentro de lo que permite la imagen.
    const redimensionar = (lado) => {
        const centroX = cuadro.x + cuadro.lado / 2;
        const centroY = cuadro.y + cuadro.lado / 2;
        cuadro.lado = lado;
        acotar();
        cuadro.x = centroX - cuadro.lado / 2;
        cuadro.y = centroY - cuadro.lado / 2;
        acotar();
    };

    const botonesDeZoom = [...dialogo.querySelectorAll("[data-foto-zoom]")];
    // Acercar no sigue más allá del cuadro mínimo, ni alejar más allá de la imagen.
    const reflejarZoom = () => {
        for (const boton of botonesDeZoom) {
            const acerca = boton.dataset.fotoZoom === "1";
            boton.disabled = acerca
                ? cuadro.lado <= minimo() + 0.5
                : cuadro.lado >= Math.min(fuente.width, fuente.height) - 0.5;
        }
    };

    const pintar = () => {
        const lado = escenario.clientWidth;
        const densidad = window.devicePixelRatio || 1;
        const util = lado - 2 * AIRE;
        escala = Math.min(util / fuente.width, util / fuente.height);
        margenX = (lado - fuente.width * escala) / 2;
        margenY = (lado - fuente.height * escala) / 2;
        lienzo.width = Math.round(lado * densidad);
        lienzo.height = Math.round(lado * densidad);
        const ctx = lienzo.getContext("2d");
        ctx.setTransform(densidad, 0, 0, densidad, 0, 0);
        ctx.clearRect(0, 0, lado, lado);
        ctx.drawImage(fuente, margenX, margenY, fuente.width * escala, fuente.height * escala);

        recorte.style.left = `${margenX + cuadro.x * escala}px`;
        recorte.style.top = `${margenY + cuadro.y * escala}px`;
        recorte.style.width = `${cuadro.lado * escala}px`;
        recorte.style.height = `${cuadro.lado * escala}px`;

        const vista = previa.getContext("2d");
        vista.fillStyle = "#ffffff";
        vista.fillRect(0, 0, previa.width, previa.height);
        vista.drawImage(fuente, cuadro.x, cuadro.y, cuadro.lado, cuadro.lado, 0, 0, previa.width, previa.height);
        reflejarZoom();
    };

    const empezar = () => {
        prepararFuente();
        encuadreInicial();
        pintar();
    };

    const abrir = (direccion) => {
        const nueva = new Image();
        nueva.onload = () => {
            original = nueva;
            giro = 0;
            dialogo.showModal();
            // El escenario recién tiene tamaño cuando el diálogo está abierto.
            empezar();
            recorte.focus();
        };
        nueva.onerror = () => {
            estado.textContent = tr("No se pudo abrir esa imagen. Prueba con otra.");
            entrada.value = "";
        };
        nueva.src = direccion;
    };

    entrada.addEventListener("change", () => {
        const [archivo] = entrada.files;
        if (archivo) abrir(URL.createObjectURL(archivo));
    });
    editar?.addEventListener("click", () => abrir(editar.dataset.fotoEditar));

    // ── Arrastrar el cuadro o una de sus esquinas ────────────────────────────
    // Una esquina cambia el tamaño dejando fija la esquina opuesta; el cuadro
    // sigue siendo cuadrado y no sale de la imagen.
    let gesto = null;
    const enLaImagen = (evento) => {
        const caja = escenario.getBoundingClientRect();
        const proporcion = escenario.clientWidth / caja.width;
        return {
            x: ((evento.clientX - caja.left) * proporcion - margenX) / escala,
            y: ((evento.clientY - caja.top) * proporcion - margenY) / escala,
        };
    };

    recorte.addEventListener("pointerdown", (evento) => {
        evento.preventDefault();
        const punto = enLaImagen(evento);
        const esquina = evento.target.dataset.esquina || null;
        const derecha = cuadro.x + cuadro.lado;
        const abajo = cuadro.y + cuadro.lado;
        gesto = {
            esquina,
            inicio: punto,
            desde: { ...cuadro },
            // La esquina que queda quieta mientras se tira de la opuesta.
            fija: {
                x: esquina && esquina.endsWith("o") ? derecha : cuadro.x,
                y: esquina && esquina.startsWith("n") ? abajo : cuadro.y,
            },
        };
        // Con la captura, el gesto sigue aunque el puntero salga del cuadro; si el
        // navegador la rechaza, el arrastre funciona igual dentro de él.
        try {
            recorte.setPointerCapture(evento.pointerId);
        } catch {}
        recorte.classList.add("activo");
    });

    recorte.addEventListener("pointermove", (evento) => {
        if (!gesto) return;
        const punto = enLaImagen(evento);
        if (!gesto.esquina) {
            cuadro.x = gesto.desde.x + (punto.x - gesto.inicio.x);
            cuadro.y = gesto.desde.y + (punto.y - gesto.inicio.y);
            acotar();
        } else {
            const { fija, esquina } = gesto;
            const haciaIzquierda = esquina.endsWith("o");
            const haciaArriba = esquina.startsWith("n");
            // Lo que cabe entre la esquina fija y el borde de la imagen.
            const espacioX = haciaIzquierda ? fija.x : fuente.width - fija.x;
            const espacioY = haciaArriba ? fija.y : fuente.height - fija.y;
            const pedido = Math.max(Math.abs(punto.x - fija.x), Math.abs(punto.y - fija.y));
            cuadro.lado = Math.max(minimo(), Math.min(pedido, espacioX, espacioY));
            cuadro.x = haciaIzquierda ? fija.x - cuadro.lado : fija.x;
            cuadro.y = haciaArriba ? fija.y - cuadro.lado : fija.y;
        }
        pintar();
    });

    const soltar = () => {
        gesto = null;
        recorte.classList.remove("activo");
    };
    recorte.addEventListener("pointerup", soltar);
    recorte.addEventListener("pointercancel", soltar);

    // ── Teclado: flechas mueven; + y − (o Mayús + flechas) cambian el tamaño ─
    recorte.addEventListener("keydown", (evento) => {
        const zoomDeTecla = { "+": 1, "=": 1, "-": -1, "_": -1 }[evento.key];
        if (zoomDeTecla) {
            evento.preventDefault();
            acercar(zoomDeTecla);
            return;
        }
        const direcciones = {
            ArrowLeft: [-1, 0],
            ArrowRight: [1, 0],
            ArrowUp: [0, -1],
            ArrowDown: [0, 1],
        };
        const direccion = direcciones[evento.key];
        if (!direccion) return;
        evento.preventDefault();
        const paso = PASO / escala;
        if (evento.shiftKey) {
            // Derecha y arriba agrandan, izquierda y abajo achican, desde el centro.
            redimensionar(cuadro.lado + (direccion[0] || -direccion[1]) * paso * 2);
        } else {
            cuadro.x += direccion[0] * paso;
            cuadro.y += direccion[1] * paso;
        }
        acotar();
        pintar();
    });

    // ── Zoom ─────────────────────────────────────────────────────────────────
    // `sentido` 1 acerca (cuadro más chico) y −1 aleja (cuadro más grande).
    const acercar = (sentido) => {
        redimensionar(sentido > 0 ? cuadro.lado * FACTOR_DE_ZOOM : cuadro.lado / FACTOR_DE_ZOOM);
        pintar();
    };
    for (const boton of botonesDeZoom) {
        boton.addEventListener("click", () => acercar(Number(boton.dataset.fotoZoom)));
    }

    // ── Girar y restablecer ──────────────────────────────────────────────────
    // El cuadro gira con la imagen: sigue encuadrando la misma parte de la foto.
    // En sentido horario, el punto (x, y) de una imagen de alto H pasa a
    // (H − y, x); en antihorario, el de una de ancho W pasa a (y, W − x). Para el
    // cuadro se gira su esquina opuesta a la que queda arriba a la izquierda.
    const girarCuadro = (sentido) => {
        const { x, y, lado } = cuadro;
        if (sentido > 0) {
            cuadro.x = fuente.height - (y + lado);
            cuadro.y = x;
        } else {
            cuadro.x = y;
            cuadro.y = fuente.width - (x + lado);
        }
    };
    for (const boton of dialogo.querySelectorAll("[data-foto-girar]")) {
        boton.addEventListener("click", () => {
            const sentido = Number(boton.dataset.fotoGirar);
            girarCuadro(sentido);
            giro = (giro + sentido + 4) % 4;
            prepararFuente();
            acotar();
            pintar();
        });
    }
    dialogo.querySelector("[data-foto-restablecer]").addEventListener("click", () => {
        giro = 0;
        empezar();
    });

    window.addEventListener("resize", () => {
        if (dialogo.open && fuente) pintar();
    });

    const cerrar = () => {
        dialogo.close();
        entrada.value = "";
    };
    dialogo.querySelector("[data-foto-cancelar]").addEventListener("click", cerrar);
    dialogo.addEventListener("cancel", () => {
        entrada.value = "";
    });

    dialogo.querySelector("[data-foto-guardar]").addEventListener("click", () => {
        const salida = document.createElement("canvas");
        salida.width = SALIDA;
        salida.height = SALIDA;
        const ctx = salida.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, SALIDA, SALIDA);
        ctx.drawImage(fuente, cuadro.x, cuadro.y, cuadro.lado, cuadro.lado, 0, 0, SALIDA, SALIDA);
        salida.toBlob(
            (resultado) => {
                if (!resultado) return;
                // El recorte reemplaza al archivo elegido y el formulario se envía
                // como siempre: el servidor no distingue un camino del otro.
                const transferencia = new DataTransfer();
                transferencia.items.add(new File([resultado], "foto.jpg", { type: "image/jpeg" }));
                entrada.files = transferencia.files;
                dialogo.close();
                estado.textContent = tr("Guardando…");
                formulario.submit();
            },
            "image/jpeg",
            0.9,
        );
    });
})();
