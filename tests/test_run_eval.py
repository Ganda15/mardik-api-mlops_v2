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
