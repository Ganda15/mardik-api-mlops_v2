"""Tests unitaires du gate d'évaluation — brique 7 du Chantier 1.

Ciblent la mécanique (rapport, seuils, historique) sur un seul contrat contrôlé ; la
comparaison v1 vs v2 sur les 12 contrats est le test d'acceptance fourni
(tests/acceptance/test_chaine.py::test_gate_evaluation_note_par_version).
"""
from __future__ import annotations

import json

from eval.run_eval import evaluer


def test_evaluer_calcule_le_rappel_et_ecrit_lhistorique(tmp_path):
    historique = tmp_path / "history.jsonl"
    rapport = evaluer("v2", sous_ensemble=["c01"], historique=historique)

    assert "c01" in rapport.par_contrat
    c = rapport.par_contrat["c01"]
    assert {"note", "seuil_note", "passe", "trouvees", "manquantes", "latence_ms", "cout_eur"} <= set(c)
    assert 0.0 <= c["note"] <= 1.0

    lignes = historique.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    entree = json.loads(lignes[0])
    assert entree["version"] == "v2.0.0"  # le rapport porte la version du bundle, pas "v2" brut


def test_evaluer_echoue_si_seuil_hors_de_portee():
    rapport = evaluer("v2", sous_ensemble=["c01"], seuil=1.5, historique=None)
    assert rapport.passe is False
    assert rapport.motifs != []
    assert any("seuil" in m for m in rapport.motifs)


# --- A1 (spec §5) : la précision à côté du rappel — constaté absent le 22/09 en lisant
# l'enregistrement du gate réel (rappel 1,000 partout : un modèle qui annoncerait les 14
# types aurait la même note). Rapportée, pas bloquante.


def test_noter_rappel_precision_et_en_trop():
    from eval.run_eval import noter

    rappel, precision, en_trop = noter({"a", "b", "d", "e"}, {"a", "b", "c"})

    assert rappel == 2 / 3
    assert precision == 2 / 4
    assert en_trop == ["d", "e"]


def test_noter_sans_annonce_ni_attente():
    from eval.run_eval import noter

    assert noter(set(), {"a"}) == (0.0, 1.0, [])  # rien d'annoncé : rien de faux, mais rien de trouvé
    assert noter({"a"}, set()) == (1.0, 0.0, ["a"])  # rien d'attendu : tout ce qui est annoncé est en trop


def test_evaluer_rapporte_la_precision_sans_bloquer(tmp_path):
    historique = tmp_path / "history.jsonl"
    rapport = evaluer("v2", sous_ensemble=["c01"], historique=historique)

    c = rapport.par_contrat["c01"]
    assert {"precision", "en_trop"} <= set(c)
    assert 0.0 <= c["precision"] <= 1.0
    assert set(c["en_trop"]).isdisjoint(c["trouvees"])
    assert 0.0 <= rapport.precision <= 1.0
    assert not any("précision" in m for m in rapport.motifs), "rapportée, jamais bloquante (spec §5 A1)"

    entree = json.loads(historique.read_text(encoding="utf-8").strip())
    assert "precision" in entree and "precision" in entree["par_contrat"]["c01"]
