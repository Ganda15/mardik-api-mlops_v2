"""Brique F1 — les champs additifs de /v2 que le frontend affiche (spec §2).

La spec promettait trois ajouts « sans casser la forme » : le libellé du niveau de
certitude, un ``request_id`` de corrélation, et l'en-tête de version sur la réponse.
Constaté le 23/09 : seul l'en-tête existait, et seulement sur la gateway. Ces tests
figent les trois, plus une garde : la réponse de /v1 ne gagne aucun champ.

Libellé (conception Ch1, H6) : ``haute`` >= 0,8 · ``moyenne`` [0,5 ; 0,8[ · ``basse`` < 0,5,
bornes lues dans le bundle (configuration versionnée), défaut = H6 pour les bundles
publiés avant l'ajout du champ.
"""
from __future__ import annotations

import re

import pytest

from app.llm_client import Bundle
from app.pipeline.confiance import libeller

MOTIF_REQUEST_ID = re.compile(r"^req_[0-9a-f]{12}$")


# --- le libellé : une fonction pure, bornes de H6 --------------------------------------


@pytest.mark.parametrize(
    ("score", "attendu"),
    [(1.0, "haute"), (0.8, "haute"), (0.79, "moyenne"), (0.5, "moyenne"), (0.49, "basse"), (0.0, "basse")],
)
def test_libeller_respecte_les_bornes_de_h6(score, attendu):
    assert libeller(score) == attendu


def test_libeller_lit_des_bornes_fournies():
    assert libeller(0.7, {"haute": 0.7, "moyenne": 0.4}) == "haute"
    assert libeller(0.39, {"haute": 0.7, "moyenne": 0.4}) == "basse"


def test_bundle_v2_declare_les_bornes_du_libelle():
    assert Bundle.charger("v2").parametres["seuils_libelle"] == {"haute": 0.8, "moyenne": 0.5}


# --- la réponse 200 de /v2 ------------------------------------------------------------


def test_v2_renvoie_un_libelle_coherent_avec_le_score_global(client, contrat):
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["libelle"] in {"haute", "moyenne", "basse"}
    assert corps["libelle"] == libeller(corps["confiance_globale"])


def test_v2_renvoie_un_request_id_unique_par_requete(client, contrat):
    a = client.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    b = client.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    assert MOTIF_REQUEST_ID.match(a) and MOTIF_REQUEST_ID.match(b)
    assert a != b


def test_v2_signe_sa_reponse_avec_l_en_tete_de_version(client, contrat):
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.headers["X-Mardik-Version"] == r.json()["version"]


def test_request_id_est_dans_la_trace(client, contrat, span_exporter):
    """Le request_id relie la réponse vue par le juriste à la trace Jaeger (diagnostic C21)."""
    rid = client.post("/v2/analyse", json={"texte": contrat("c01")}).json()["request_id"]
    racines = [s for s in span_exporter.get_finished_spans() if s.name == "analyse.requete"]
    assert racines and racines[-1].attributes["mardik.request_id"] == rid


# --- la réponse 503 : explicite, et corrélable ----------------------------------------


def test_v2_en_panne_renvoie_503_avec_request_id_et_version(client, contrat, monkeypatch):
    monkeypatch.setenv("MOCK", "off")
    monkeypatch.setenv("LLM_PROXY_URL", "http://127.0.0.1:9")  # port fermé : vraie panne réseau
    monkeypatch.setenv("LLM_TIMEOUT_S", "2")
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 503, r.text
    corps = r.json()
    assert "LLM" in corps["detail"]
    assert MOTIF_REQUEST_ID.match(corps["request_id"])
    assert r.headers["X-Mardik-Version"] == Bundle.charger("v2").version


# --- la gateway sert les mêmes champs quand elle route vers v2, et rien de plus pour v1 ---


def test_gateway_vers_v2_porte_libelle_et_request_id(client, contrat, registry):
    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="test", note_eval=1.0)
    registry.definir_canary("v2.0.0", 100)
    r = client.post("/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 200, r.text
    assert r.headers["X-Mardik-Version"] == "v2.0.0"
    assert r.json()["libelle"] in {"haute", "moyenne", "basse"}
    assert MOTIF_REQUEST_ID.match(r.json()["request_id"])


def test_reponse_v1_ne_gagne_aucun_champ(client, contrat):
    """Exigence 2 du CTO : le contrat /v1 ne bouge pas, même de façon additive."""
    r = client.post("/v1/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"clauses", "modele", "version", "tronque"}


def test_gateway_en_panne_renvoie_503_avec_request_id(client, contrat, registry, monkeypatch):
    """Le frontend passe par la gateway : une panne y reste explicite ET corrélable."""
    monkeypatch.setenv("MOCK", "off")
    monkeypatch.setenv("LLM_PROXY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_TIMEOUT_S", "2")
    r = client.post("/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 503, r.text
    assert "LLM" in r.json()["detail"]
    assert MOTIF_REQUEST_ID.match(r.json()["request_id"])
    assert r.headers["X-Mardik-Version"] == "v1.0.0"
