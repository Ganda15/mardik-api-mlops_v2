"""Model wrapper exposing a single predict() over the Azure-hosted model."""
from __future__ import annotations

from typing import Any


class ModelWrapper:
    """Wraps the underlying model behind a stable predict() signature."""

    version = "kimi-k2.6"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def predict(self, text: str) -> dict[str, Any]:
        raise NotImplementedError


def get_model() -> ModelWrapper:
    """FastAPI dependency returning the model used to serve predictions."""
    return ModelWrapper()
