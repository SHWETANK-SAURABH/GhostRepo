"""HTTP client for the Ollama runtime. Ollama serves models; it is not itself a model."""

from dataclasses import dataclass
from typing import Any

import httpx

from app.schemas.common import OllamaModel, OllamaModelsResponse, OllamaStatus

_STATUS_TIMEOUT = 3.0
_MAX_REPLY_TOKENS = 2048
_GRAMMAR_UNSUPPORTED = {
    "$defs",
    "title",
    "description",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
}


class OllamaError(Exception):
    """Inference failed. The message is safe to show to a user."""


@dataclass
class OllamaClient:
    endpoint: str
    model: str
    timeout_seconds: float = 300
    context_tokens: int = 8192
    transport: httpx.BaseTransport | None = None

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self.endpoint.rstrip("/"),
            timeout=timeout,
            transport=self.transport,
            follow_redirects=False,
            trust_env=False,
        )

    def list_models(self) -> list[OllamaModel]:
        with self._client(_STATUS_TIMEOUT) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            entries = response.json().get("models", [])
        return [_parse_model(entry) for entry in entries if entry.get("name")]

    def version(self) -> str | None:
        with self._client(_STATUS_TIMEOUT) as client:
            response = client.get("/api/version")
            response.raise_for_status()
            return response.json().get("version")

    def status(self, enabled: bool = True) -> OllamaStatus:
        try:
            version = self.version()
            names = [model.name for model in self.list_models()]
        except (httpx.HTTPError, ValueError, AttributeError):
            return OllamaStatus(
                enabled=enabled,
                reachable=False,
                model=self.model,
                model_available=False,
                message="Ollama is not reachable at the configured endpoint.",
            )
        available = model_matches(self.model, names)
        message = (
            f"Ollama is running and {self.model} is installed."
            if available
            else f"Ollama is running, but {self.model} is not installed. "
            f"Run: ollama pull {self.model}"
        )
        return OllamaStatus(
            enabled=enabled,
            reachable=True,
            version=version,
            model=self.model,
            model_available=available,
            message=message,
        )

    def models_response(self) -> OllamaModelsResponse:
        try:
            models = self.list_models()
        except (httpx.HTTPError, ValueError, AttributeError):
            return OllamaModelsResponse(
                reachable=False,
                models=[],
                message="Ollama is not reachable at the configured endpoint.",
            )
        return OllamaModelsResponse(
            reachable=True, models=models, message=f"{len(models)} model(s) installed."
        )

    def chat_json(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        """Return the raw reply text. Falls back to JSON mode if a schema is refused."""
        fmt: dict[str, Any] | str = schema if schema is not None else "json"
        try:
            return self._chat(system, user, fmt)
        except _FormatRefused as exc:
            if fmt == "json":
                raise OllamaError(str(exc)) from exc
            try:
                return self._chat(system, user, "json")
            except _FormatRefused as retry_exc:
                raise OllamaError(str(retry_exc)) from retry_exc

    def _chat(self, system: str, user: str, fmt: dict[str, Any] | str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": fmt,
            "options": {
                "temperature": 0.1,
                "num_ctx": self.context_tokens,
                "num_predict": _MAX_REPLY_TOKENS,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            with self._client(self.timeout_seconds) as client:
                response = client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"The model did not answer within {int(self.timeout_seconds)} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaError("Could not connect to Ollama at the configured endpoint.") from exc

        if response.status_code == 404:
            raise OllamaError(f"Model {self.model} is not installed in Ollama.")
        if response.status_code == 400:
            raise _FormatRefused("Ollama rejected the structured output request.")
        if response.status_code >= 400:
            raise OllamaError(f"Ollama returned HTTP {response.status_code}.")

        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaError("Ollama returned a response in an unexpected format.") from exc
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("The model returned an empty response.")
        return content


class _FormatRefused(Exception):
    pass


def grammar_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Simplify a JSON schema for Ollama, which compiles it into a sampling grammar.

    References and length limits can make that fail with "failed to parse grammar". This keeps
    structure, types and enums. Pydantic still enforces the full limits on the reply.
    """
    definitions = schema.get("$defs", {})

    def simplify(node: Any) -> Any:
        if isinstance(node, list):
            return [simplify(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return simplify(definitions[node["$ref"].rsplit("/", 1)[-1]])
        return {
            key: {name: simplify(value) for name, value in child.items()}
            if key == "properties"
            else simplify(child)
            for key, child in node.items()
            if key not in _GRAMMAR_UNSUPPORTED
        }

    return simplify(schema)


def model_matches(wanted: str, installed: list[str]) -> bool:
    """Ollama treats a name without a tag as name:latest."""
    candidates = {wanted} if ":" in wanted else {wanted, f"{wanted}:latest"}
    return any(name in candidates for name in installed)


def _parse_model(entry: dict[str, Any]) -> OllamaModel:
    details = entry.get("details") or {}
    return OllamaModel(
        name=entry["name"],
        size_bytes=entry.get("size"),
        family=details.get("family"),
        parameter_size=details.get("parameter_size"),
        quantization=details.get("quantization_level"),
    )
