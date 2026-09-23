"""Brique 13 (Chantier 2) — tous les seuils dans un seul fichier versionné : eval/thresholds.yml.

Conception Ch2 §3 et §9 : en changer un = un commit ; le fichier est sous eval/ pour que le
filtre de chemin déclenche le gate dès la PR. Manque connu depuis le 22/09 (le fichier était
promis, les seuils codés en dur). Échec fermé : fichier absent ou incomplet → erreur, jamais
un seuil par défaut deviné.
"""
from __future__ import annotations

import pytest
import yaml

from ops.seuils import ErreurSeuils, charger_seuils


def test_le_fichier_du_depot_porte_les_seuils_du_gate_actuel():
    """Aucun changement de comportement : les valeurs sont celles codées en dur jusqu'ici."""
    s = charger_seuils()
    assert s["gate"] == {"rappel_min": 0.75, "latence_p95_max_ms": 8000, "cout_moyen_max_eur": 0.15}
    assert s["fenetre"]["requetes_min"] == 30
    assert s["promotion"]["paliers"] == [10, 50, 100]


def test_fichier_absent_leve_une_erreur(tmp_path):
    with pytest.raises(ErreurSeuils, match="introuvable"):
        charger_seuils(tmp_path / "absent.yml")


def test_section_manquante_nommee_dans_l_erreur(tmp_path):
    complet = charger_seuils()
    del complet["promotion"]
    chemin = tmp_path / "seuils.yml"
    chemin.write_text(yaml.safe_dump(complet), encoding="utf-8")
    with pytest.raises(ErreurSeuils, match="promotion"):
        charger_seuils(chemin)


def test_un_fichier_de_demo_remplace_le_fichier_par_configuration(tmp_path, monkeypatch):
    """Conception §4.2 : en démo, requetes_min est abaissé « par configuration, jamais par le code »."""
    demo = charger_seuils()
    demo["fenetre"]["requetes_min"] = 3
    chemin = tmp_path / "demo.yml"
    chemin.write_text(yaml.safe_dump(demo), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(chemin))
    assert charger_seuils()["fenetre"]["requetes_min"] == 3


def test_le_gate_lit_son_seuil_dans_le_fichier(tmp_path, monkeypatch, historique):
    """Le fichier gouverne vraiment : un seuil impossible dans le fichier fait échouer le gate."""
    from eval.run_eval import evaluer

    seuils = charger_seuils()
    seuils["gate"]["rappel_min"] = 1.01
    chemin = tmp_path / "seuils.yml"
    chemin.write_text(yaml.safe_dump(seuils), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(chemin))

    rapport = evaluer("v2", sous_ensemble=["c01"], historique=historique)
    assert not rapport.passe
    assert any("seuil 1.01" in m for m in rapport.motifs)
