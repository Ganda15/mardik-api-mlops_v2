"""Fixtures for the acceptance suite: a test client with a stubbed model."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from mardik_api.app import create_app
from mardik_api.model import get_model


class StubModel:
    """A deterministic stand-in for the real model, used in acceptance tests."""

    version = "stub-1"

    def predict(self, text: str) -> dict[str, Any]:
        return {"label": "positive", "score": 0.97}


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_model] = lambda: StubModel()
    return TestClient(app)
