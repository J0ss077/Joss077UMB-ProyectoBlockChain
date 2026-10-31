"""El conector del ayudante con un servicio de IA: cualquiera, con sólo la clave.

La configuración vive en `.env` y la lee el arranque (`src/web/__main__.py`), que
se la pasa a `create_app`. Lo único obligatorio es `ASISTENTE_API_KEY`: el
proveedor se reconoce por el comienzo de la clave (`sk-ant-` es Anthropic, `gsk_`
es Groq, `AIza` es Google Gemini…) y cada proveedor trae su dirección y un modelo
por defecto. Tres variables opcionales cubren el resto:

- `ASISTENTE_PROVEEDOR`: para las claves que no se distinguen por su comienzo
  (DeepSeek y Mistral, por ejemplo) o para un servidor local como Ollama.
- `ASISTENTE_MODELO`: otro modelo del mismo proveedor.
- `ASISTENTE_URL`: cualquier servicio compatible con la API de OpenAI
  (`…/v1/chat/completions`), aunque no esté en la tabla.

Hay dos formas de hablar con un servicio: la de Anthropic, con su SDK oficial, y
la «compatible con OpenAI» (`POST {url}/chat/completions`), que hoy hablan casi
todos —OpenAI, Gemini, Groq, DeepSeek, Mistral, OpenRouter, xAI, Together, Ollama—
y que se llama con la biblioteca estándar para no sumar dependencias.

Si algo falla —sin red, clave inválida, modelo inexistente—, `responder` devuelve
`None`, deja el motivo en el registro del servidor y el ayudante contesta con su
guía local. La persona nunca ve un error técnico.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

registro = logging.getLogger(__name__)

# Nombres de las variables de `.env`. Los lee el arranque; acá sólo se nombran
# para los mensajes del registro.
VARIABLE_DE_LA_CLAVE = "ASISTENTE_API_KEY"
VARIABLE_DEL_PROVEEDOR = "ASISTENTE_PROVEEDOR"
VARIABLE_DEL_MODELO = "ASISTENTE_MODELO"
VARIABLE_DE_LA_URL = "ASISTENTE_URL"
VARIABLES = (
    VARIABLE_DE_LA_CLAVE,
    VARIABLE_DEL_PROVEEDOR,
    VARIABLE_DEL_MODELO,
    VARIABLE_DE_LA_URL,
)

ESPERA_MAXIMA = 40  # segundos


@dataclass(frozen=True, slots=True)
class Proveedor:
    """Cómo hablar con un servicio: la forma de la API, su dirección y un modelo."""

    nombre: str
    forma: str  # "anthropic" u "openai"
    url: str
    modelo: str


PROVEEDORES: dict[str, Proveedor] = {
    proveedor.nombre: proveedor
    for proveedor in (
        Proveedor("anthropic", "anthropic", "https://api.anthropic.com", "claude-opus-5-5"),
        Proveedor("openai", "openai", "https://api.openai.com/v1", "gpt-4.1-mini"),
        Proveedor(
            "gemini",
            "openai",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-2.5-flash",
        ),
        Proveedor(
            "groq", "openai", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"
        ),
        Proveedor("deepseek", "openai", "https://api.deepseek.com/v1", "deepseek-chat"),
        Proveedor("mistral", "openai", "https://api.mistral.ai/v1", "mistral-small-latest"),
        Proveedor("openrouter", "openai", "https://openrouter.ai/api/v1", "openrouter/auto"),
        Proveedor("xai", "openai", "https://api.x.ai/v1", "grok-3-mini"),
        Proveedor(
            "together",
            "openai",
            "https://api.together.xyz/v1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ),
        # Local y sin clave: `ollama serve` en la misma máquina.
        Proveedor("ollama", "openai", "http://localhost:11434/v1", "llama3.2"),
    )
}

# El comienzo de la clave dice de quién es. El orden importa: `sk-ant-` y `sk-or-`
# empiezan igual que las de OpenAI, así que van antes que `sk-`. Una clave `sk-`
# también puede ser de DeepSeek: en ese caso hay que decirlo en ASISTENTE_PROVEEDOR.
PREFIJOS: tuple[tuple[str, str], ...] = (
    ("sk-ant-", "anthropic"),
    ("sk-or-", "openrouter"),
    ("gsk_", "groq"),
    ("AIza", "gemini"),
    ("xai-", "xai"),
    ("sk-", "openai"),
)

# Los modelos de Claude que aceptan el respaldo del servidor ante un rechazo y el
# parámetro de esfuerzo; a otros no se les mandan, porque responderían 400.
CLAUDE_CON_RESPALDO = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")
CLAUDE_CON_ESFUERZO = ("claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5")


def detectar_proveedor(clave: str) -> str | None:
    for prefijo, nombre in PREFIJOS:
        if clave.startswith(prefijo):
            return nombre
    return None


class ConectorDeIA:
    """Le pregunta al servicio configurado y devuelve el texto, o `None` si falla."""

    def __init__(self, proveedor: Proveedor, clave: str | None, modelo: str, url: str) -> None:
        self.proveedor = proveedor
        self.clave = clave
        self.modelo = modelo
        self.url = url.rstrip("/")

    def __repr__(self) -> str:  # nunca la clave
        return f"ConectorDeIA({self.proveedor.nombre}, {self.modelo})"

    def responder(self, instrucciones: str, mensajes: Sequence[Mapping[str, str]]) -> str | None:
        """`mensajes` alterna `user` y `assistant` y termina en `user`."""
        if self.proveedor.forma == "anthropic":
            return self._anthropic(instrucciones, mensajes)
        return self._compatible_con_openai(instrucciones, mensajes)

    def _anthropic(self, instrucciones: str, mensajes: Sequence[Mapping[str, str]]) -> str | None:
        try:
            import anthropic
        except ImportError:
            registro.warning("Falta el paquete anthropic: pip install -r requirements.txt")
            return None
        cliente = anthropic.Anthropic(
            api_key=self.clave,
            base_url=None if self.url == PROVEEDORES["anthropic"].url else self.url,
            timeout=float(ESPERA_MAXIMA),
            max_retries=1,
        )
        opciones: dict[str, object] = {}
        if self.modelo.startswith(CLAUDE_CON_ESFUERZO):
            opciones["output_config"] = {"effort": "low"}
        if self.modelo in CLAUDE_CON_RESPALDO:
            opciones["betas"] = ["server-side-fallback-2026-07-01"]
            opciones["fallbacks"] = "default"
        try:
            respuesta = cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=16000,
                system=[{
                    "type": "text",
                    "text": instrucciones,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[dict(m) for m in mensajes],
                **opciones,
            )
        except anthropic.RateLimitError:
            registro.warning("Anthropic limitó las peticiones del ayudante")
            return None
        except anthropic.APIStatusError as error:
            registro.warning("Anthropic respondió %s: %s", error.status_code, error.message)
            return None
        except anthropic.APIConnectionError:
            registro.warning("Sin conexión con Anthropic")
            return None
        if respuesta.stop_reason == "refusal":
            return None
        return "".join(b.text for b in respuesta.content if b.type == "text").strip() or None

    def _compatible_con_openai(
        self, instrucciones: str, mensajes: Sequence[Mapping[str, str]]
    ) -> str | None:
        # Sin `temperature` ni tope de tokens: hay modelos que rechazan uno u otro,
        # y las instrucciones ya piden respuestas cortas.
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": instrucciones}, *map(dict, mensajes)],
        }
        cabeceras = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.clave:
            cabeceras["Authorization"] = f"Bearer {self.clave}"
        peticion = urllib.request.Request(
            f"{self.url}/chat/completions",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers=cabeceras,
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=ESPERA_MAXIMA) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detalle = error.read(500).decode("utf-8", "replace")
            registro.warning(
                "%s respondió %s al ayudante: %s", self.proveedor.nombre, error.code, detalle
            )
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            registro.warning("Sin conexión con %s: %s", self.proveedor.nombre, error)
            return None
        except ValueError:
            registro.warning("%s devolvió algo que no es JSON", self.proveedor.nombre)
            return None
        try:
            contenido = datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            registro.warning("%s devolvió una respuesta sin texto", self.proveedor.nombre)
            return None
        # Algunos modelos devuelven el contenido como lista de partes.
        if isinstance(contenido, list):
            contenido = "".join(
                parte.get("text", "") for parte in contenido if isinstance(parte, dict)
            )
        return contenido.strip() if isinstance(contenido, str) and contenido.strip() else None


def crear_conector(configuracion: Mapping[str, str | None] | None) -> ConectorDeIA | None:
    """El conector que pide la configuración, o `None` para usar sólo la guía local."""
    if not configuracion:
        return None
    clave = (configuracion.get(VARIABLE_DE_LA_CLAVE) or "").strip() or None
    nombre = (configuracion.get(VARIABLE_DEL_PROVEEDOR) or "").strip().lower()
    url = (configuracion.get(VARIABLE_DE_LA_URL) or "").strip()
    modelo = (configuracion.get(VARIABLE_DEL_MODELO) or "").strip()

    if not nombre and clave:
        nombre = detectar_proveedor(clave) or ""
    if not nombre and url:
        # Una dirección propia sin proveedor: se la trata como compatible con OpenAI.
        nombre = "personalizado"
    if not nombre:
        if clave:
            registro.warning(
                "No se reconoce de qué servicio es %s; indícalo en %s (%s). El ayudante "
                "usa su guía local.",
                VARIABLE_DE_LA_CLAVE,
                VARIABLE_DEL_PROVEEDOR,
                ", ".join(PROVEEDORES),
            )
        return None

    proveedor = PROVEEDORES.get(nombre)
    if proveedor is None:
        if not url:
            registro.warning(
                "%s=%s no está en la lista (%s); para otro servicio define %s. El "
                "ayudante usa su guía local.",
                VARIABLE_DEL_PROVEEDOR,
                nombre,
                ", ".join(PROVEEDORES),
                VARIABLE_DE_LA_URL,
            )
            return None
        proveedor = Proveedor(nombre, "openai", url, "")
    if not modelo:
        modelo = proveedor.modelo
    if not modelo:
        registro.warning("Falta %s para %s", VARIABLE_DEL_MODELO, url)
        return None
    if not clave and nombre != "ollama" and not url:
        return None
    conector = ConectorDeIA(proveedor, clave, modelo, url or proveedor.url)
    return conector
