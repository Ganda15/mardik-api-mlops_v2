"""Tests unitaires du bundle v2 — brique 1 du Chantier 1 (aucune dépendance au pipeline).

La suite fournie (tests/acceptance/) n'exerce le bundle qu'à travers le pipeline entier via
evaluer() : sans ce test, la configuration pourrait rester à moitié écrite sans qu'aucun rouge
ne le dise avant la brique 6 ou 7. Voir docs/spec-v2-perimetre.md §7, brique 1.
"""
from __future__ import annotations

from app.llm_client import TYPES_CLAUSES, Bundle


def test_bundle_v2_strategie_map_reduce():
    bundle = Bundle.charger("v2")
    assert bundle.strategie == "map_reduce_clauses"


def test_bundle_v2_prompt_ecrit_pas_un_todo():
    bundle = Bundle.charger("v2")
    assert bundle.prompt.strip(), "le prompt v2 est vide"
    assert "TODO" not in bundle.prompt.upper()
    # le prompt s'applique à UNE section (titre + texte), pas au contrat entier (spec §7)
    assert "section" in bundle.prompt.lower()


def test_bundle_v2_parametres_fixes_pour_un_gate_stable():
    bundle = Bundle.charger("v2")
    p = bundle.parametres
    assert 0.0 <= p["temperature"] <= 1.0
    assert p["temperature"] < 0.5, "un gate stable veut de la variance basse, pas un mode créatif"
    assert p.get("seed") is not None, "seed figé — deux exécutions doivent au moins tenter d'être comparables"
    assert p.get("essais_eval", 1) >= 3, "moyenner plusieurs passes : deux appels réels ne donnent pas la même note (README)"
    assert p.get("contexte_max_caracteres", 0) > 0


def test_bundle_v2_schema_sortie_couvre_le_vocabulaire_partage():
    bundle = Bundle.charger("v2")
    schema = bundle.schema_sortie
    assert schema is not None, "schema_sortie TODO — sans lui, extraction.py ne peut pas contraindre le JSON"
    types_du_schema = set(
        schema["properties"]["clauses"]["items"]["properties"]["type"]["enum"]
    )
    assert types_du_schema == set(TYPES_CLAUSES), (
        "le schéma doit couvrir exactement les 14 types de llm_client.TYPES_CLAUSES — "
        "sinon une clause valide serait rejetée, ou une inventée acceptée"
    )
    champs_clause = set(schema["properties"]["clauses"]["items"]["properties"])
    assert {"type", "extrait", "confiance"} <= champs_clause
