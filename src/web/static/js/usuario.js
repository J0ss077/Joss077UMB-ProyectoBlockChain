// Los nombres de usuario se normalizan al escribir para que la interfaz refleje
// la regla del servidor tanto al registrarse como al ingresar.
(() => {
    const normalizar = (campo) => {
        campo.value = campo.value.toLowerCase();
    };

    for (const campo of document.querySelectorAll('input[name="usuario"]')) {
        normalizar(campo);
        campo.addEventListener("input", () => normalizar(campo));
    }
})();
