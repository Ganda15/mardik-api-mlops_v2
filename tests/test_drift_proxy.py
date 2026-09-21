"""``ops/drift_proxy.py::_amont`` — brique 12 ter.

Constat du 21/09, vraie ressource Azure (``.../openai/v1``) : un appel avec
``?api-version=...`` en trop renvoie 400 « API version not supported ». Le proxy
l'ajoutait sans condition pour ``azure``, écrit contre l'ancienne API « Azure AI
Inference » (``.../models``) qui l'exige — les deux surfaces coexistent selon la
ressource, donc le paramètre ne doit être ajouté que s'il est configuré.
"""
from __future__ import annotations

import pytest

from ops.drift_proxy import _amont


def test_amont_azure_ajoute_api_version_si_definie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://exemple.services.ai.azure.com/models")
    monkeypatch.setenv("AZURE_AI_API_VERSION", "2024-05-01-preview")

    url, _ = _amont("azure", "chat/completions")

    assert url == "https://exemple.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"


def test_amont_azure_omet_api_version_si_vide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://exemple.services.ai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_AI_API_VERSION", "")

    url, _ = _amont("azure", "chat/completions")

    assert url == "https://exemple.services.ai.azure.com/openai/v1/chat/completions"
