"""Brique 19 (latence) — un seul client HTTP réutilisé, un délai par appel de section, une reprise.

Constat du 23/09 : ``app/llm_client.py`` ouvrait un ``httpx.Client`` NEUF à chaque appel de section (une
poignée de main TLS par section, 19 à 31 par contrat) avec 60 s de délai et aucune reprise — un seul appel
lent ou pendu traînait toute l'analyse (map-reduce : on attend la section la plus lente). Ici, aucun réseau :
``httpx.MockTransport``.
"""
from __future__ import annotations

import httpx
import pytest

from app.llm_client import Bundle, ErreurLLM, LLMClient


def _bundle(**params) -> Bundle:
    return Bundle(version="v2.0.0", modele="gpt-5.4", prompt="système",
                  parametres={"temperature": 0.2, "seed": 42, "max_tokens": 500, **params},
                  schema_sortie=None, strategie="map_reduce_clauses")


def _ok() -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 1}})


_CLIENT_ORIGINAL = httpx.Client   # capturé une fois : deux _client() dans un même test ne s'emboîtent pas


def _client(monkeypatch, handler, compteur: list | None = None, **params) -> LLMClient:
    transport = httpx.MockTransport(handler)
    ClientOriginal = _CLIENT_ORIGINAL

    def _fabrique(*a, **k):
        if compteur is not None:
            compteur.append(k.get("timeout"))
        return ClientOriginal(transport=transport, timeout=k.get("timeout"))

    monkeypatch.setattr(httpx, "Client", _fabrique)
    return LLMClient(_bundle(**params), provider="azure", proxy_url="http://proxy.test", mock="off")


def test_un_seul_client_http_pour_tous_les_appels(monkeypatch):
    fabriques: list = []
    client = _client(monkeypatch, lambda r: _ok(), compteur=fabriques, timeout_s=20)
    for prompt in ("a", "b", "c"):
        client.completer(prompt)
    assert len(fabriques) == 1                    # une connexion réutilisée, pas trois poignées de main
    assert fabriques[0] == 20                     # le délai vient du bundle


def test_un_delai_depasse_est_repris_une_fois(monkeypatch):
    tentatives: list[int] = []

    def handler(request):
        tentatives.append(1)
        if len(tentatives) == 1:
            raise httpx.ReadTimeout("trop lent", request=request)
        return _ok()

    client = _client(monkeypatch, handler, reprises=1)
    assert client.completer("x").texte == "ok"
    assert len(tentatives) == 2


def test_une_erreur_5xx_est_reprise_une_4xx_jamais(monkeypatch):
    appels: list[int] = []

    def serveur_puis_ok(request):
        appels.append(500 if not appels else 200)
        return httpx.Response(appels[-1], json={"error": "x"}) if appels[-1] == 500 else _ok()

    assert _client(monkeypatch, serveur_puis_ok, reprises=1).completer("x").texte == "ok"
    assert appels == [500, 200]

    quatre_cents: list[int] = []

    def refus(request):
        quatre_cents.append(1)
        return httpx.Response(400, json={"error": "paramètre"})

    with pytest.raises(ErreurLLM, match="HTTP 400"):
        _client(monkeypatch, refus, reprises=3).completer("x")
    assert len(quatre_cents) == 1                 # une 400 ne se répare pas en réessayant


def test_apres_la_derniere_reprise_l_erreur_reste_explicite(monkeypatch):
    def toujours_lent(request):
        raise httpx.ReadTimeout("trop lent", request=request)

    with pytest.raises(ErreurLLM, match="injoignable"):
        _client(monkeypatch, toujours_lent, reprises=1).completer("x")


def test_le_bundle_v2_borne_le_delai_et_prevoit_une_reprise():
    p = Bundle.charger("v2").parametres
    assert 0 < float(p["timeout_s"]) <= 30, "60 s sans reprise = une analyse qui pend une minute"
    assert int(p["reprises"]) >= 1
