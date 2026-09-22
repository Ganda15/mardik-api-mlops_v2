"""Brique 12 bis — le corps envoyé à Azure doit utiliser ``max_completion_tokens``.

Constat du 21/09 (vraie ressource Azure, déploiement ``gpt-5.4``) : un appel avec
``max_tokens`` renvoie 400 « Unsupported parameter: 'max_tokens' is not supported with
this model. Use 'max_completion_tokens' instead. » — un appel avec ``max_completion_tokens``
renvoie 200. ``app/llm_client.py`` envoyait encore l'ancien nom. Comme le fichier est
[FOURNI] et sans test de son propre appel HTTP, ce test capture le corps réellement
envoyé (``httpx.MockTransport``, aucun réseau) pour figer le bon nom de paramètre.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.llm_client import Bundle, LLMClient


def _bundle() -> Bundle:
    return Bundle(
        version="v2.0.0",
        modele="gpt-5.4",
        prompt="système",
        parametres={"temperature": 0.2, "seed": 42, "max_tokens": 500},
        schema_sortie=None,
        strategie="map_reduce_clauses",
    )


def test_appel_azure_utilise_max_completion_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    corps_envoye: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        corps_envoye.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )

    transport = httpx.MockTransport(handler)
    ClientOriginal = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: ClientOriginal(transport=transport, timeout=k.get("timeout"))
    )

    client = LLMClient(_bundle(), provider="azure", proxy_url="http://proxy.test", mock="off")
    reponse = client.completer("bonjour")

    assert reponse.texte == "ok"
    assert "max_completion_tokens" in corps_envoye
    assert "max_tokens" not in corps_envoye
    assert corps_envoye["max_completion_tokens"] == 500
