"""Clauses sans preuve et garde de taille — issus du red-team Era du 23/09.

Deux comportements attendus, détectés sur l'instance de test (run Era e04cea659151) :

* un texte qui n'est pas un contrat faisait répondre les quatorze types de clauses avec
  des extraits vides — le score les ramenait à 0 mais la réponse les listait quand même ;
* aucun plafond de taille : un document surdimensionné déclenchait des centaines d'appels
  payants avant que le fournisseur ne bride.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.pipeline.confiance import Clause, clauses_prouvees


# ------------------------------------------------------------------ clauses_prouvees


def test_une_clause_avec_extrait_verifie_est_conservee():
    texte = "Le présent contrat est conclu pour une durée de douze mois."
    clause = Clause(type="durée", extrait="durée de douze mois", confiance_llm=0.9, sections=[0])
    assert clauses_prouvees([clause], texte) == [clause]


def test_une_clause_avec_extrait_invente_est_ecartee():
    texte = "Le présent contrat est conclu pour une durée de douze mois."
    clause = Clause(type="durée", extrait="cette phrase n'existe pas dans le contrat", confiance_llm=0.99, sections=[0])
    assert clauses_prouvees([clause], texte) == []


def test_les_quatorze_types_avec_extraits_vides_sont_tous_ecartes():
    """Le cas mesuré : une question sans rapport fait répondre 14 types, extraits vides."""
    texte = "Le vaccin contre la grippe donne la grippe, c'est bien connu, non ?"
    clauses = [
        Clause(type=t, extrait="", confiance_llm=1.0, sections=[0])
        for t in ("résiliation", "pénalité de retard", "confidentialité", "durée", "prix et paiement")
    ]
    assert clauses_prouvees(clauses, texte) == []


# ------------------------------------------------------------------ la réponse de /v2


def test_v2_ne_renvoie_que_les_clauses_prouvees(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Le LLM (moqué) annonce trois clauses ; une seule cite un extrait qui existe."""
    from app import api_v2
    from app.pipeline.extraction import ReponseLLM  # noqa: F401 — cohérence des imports

    vrai_extrait = "Le paiement intervient à trente jours fin de mois"
    texte = (
        "Article 1 — Le paiement intervient à trente jours fin de mois. "
        "Article 2 — Les parties gardent les informations confidentielles."
    )

    def extraire_factice(section, client_llm):  # noqa: ANN001 — même signature que pipeline.extraire
        return (
            [
                Clause(type="prix et paiement", extrait=vrai_extrait, confiance_llm=0.9, sections=[section.indice]),
                Clause(type="résiliation", extrait="extrait inventé par le modèle", confiance_llm=0.95, sections=[section.indice]),
                Clause(type="durée", extrait="", confiance_llm=1.0, sections=[section.indice]),
            ],
            type("R", (), {"latence_ms": 1.0, "tokens": 1, "tokens_entree": 1, "tokens_sortie": 0, "cout_eur": 0.0})(),
        )

    monkeypatch.setattr(api_v2, "extraire", extraire_factice)
    r = client.post("/v2/analyse", json={"texte": texte})
    assert r.status_code == 200, r.text
    clauses = r.json()["clauses"]
    assert [c["type"] for c in clauses] == ["prix et paiement"]
    assert clauses[0]["extrait"] == vrai_extrait


def test_v2_refuse_un_document_surdimensionne_avant_tout_appel(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """413 avant le moindre appel au modèle : la taille ne doit coûter ni temps ni argent."""
    from app import api_v2

    def echec_si_appele(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("le pipeline ne doit pas être exécuté")

    monkeypatch.setattr(api_v2, "analyser_v2", echec_si_appele)
    r = client.post("/v2/analyse", json={"texte": "x" * (api_v2.TAILLE_MAX_TEXTE + 1)})
    assert r.status_code == 413
    assert "volumineux" in r.json()["detail"]
