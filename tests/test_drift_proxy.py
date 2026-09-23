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


# --- 23/09 (c12 > 8 s) : le relais ouvrait un AsyncClient NEUF par requête relayée -----------------------
# Mesuré : 23 appels de section en parallèle (c12) → via le proxy max 6,66 s / médiane 4,44 s ; direct Azure
# max 3,19 s / médiane 1,71 s. Une poignée de main TLS et une résolution DNS par appel, depuis le conteneur.


def test_le_relais_reutilise_un_seul_client_amont(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from fastapi.testclient import TestClient

    from ops import drift_proxy

    monkeypatch.setenv("AZURE_AI_ENDPOINT", "http://amont.test/openai/v1")
    monkeypatch.setenv("AZURE_AI_API_VERSION", "")
    drift_proxy._http = None                                   # état propre pour ce test
    fabriques: list[int] = []
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}))
    ClientOriginal = httpx.AsyncClient

    def _fabrique(*a, **k):
        fabriques.append(1)
        return ClientOriginal(transport=transport, timeout=k.get("timeout"))

    monkeypatch.setattr(httpx, "AsyncClient", _fabrique)
    client = TestClient(drift_proxy.app)
    for _ in range(3):
        r = client.post("/chat/completions", json={"x": 1}, headers={"x-mardik-provider": "azure"})
        assert r.status_code == 200
    assert len(fabriques) == 1                                 # un client, trois requêtes
    drift_proxy._http = None
