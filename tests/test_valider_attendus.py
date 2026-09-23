"""C13 — étape de test des données : eval/attendus.jsonl est validé avant que le gate le lise.

Référentiel C13 (pilier 5, brique 13 du `mlops-verifier`) : « étape de test des données intégrée et sans
erreur ». Le brief permet d'y verser des cas de production (brique 17, Chantier 2) — un cas mal formé, un
type de clause inconnu, ou un contrat manquant ne doivent jamais atteindre le gate en silence : ils doivent
être trouvés AVANT, avec une ligne précise et le numéro de ligne fautive.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from eval.valider_attendus import ErreurDonnees, valider_fichier

RACINE = Path(__file__).resolve().parent.parent


def _ecrire(tmp_path, *lignes):
    chemin = tmp_path / "attendus.jsonl"
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


def test_le_fichier_reel_du_depot_est_valide():
    """Aucun changement de comportement : les 12 contrats de référence passent déjà."""
    rapport = valider_fichier(RACINE / "eval" / "attendus.jsonl", RACINE / "eval" / "contrats")
    assert rapport["lignes"] == 12 and rapport["erreurs"] == []


def test_json_invalide_est_signale_avec_son_numero_de_ligne(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c01", "clauses_attendues": ["durée"]}', "{pas du json}")
    with pytest.raises(ErreurDonnees, match=r"ligne 2"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_champ_manquant_est_signale(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c01"}')
    with pytest.raises(ErreurDonnees, match=r"clauses_attendues"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_type_de_clause_hors_vocabulaire_est_signale(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c01", "clauses_attendues": ["clause magique"]}')
    with pytest.raises(ErreurDonnees, match=r"clause magique"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_contrat_id_en_double_est_signale(tmp_path):
    chemin = _ecrire(
        tmp_path,
        '{"contrat_id": "c01", "clauses_attendues": ["durée"]}',
        '{"contrat_id": "c01", "clauses_attendues": ["résiliation"]}',
    )
    with pytest.raises(ErreurDonnees, match=r"doublon.*c01|c01.*doublon"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_fichier_de_contrat_absent_est_signale(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c99-absent", "clauses_attendues": ["durée"]}')
    with pytest.raises(ErreurDonnees, match=r"c99-absent"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_seuil_note_hors_bornes_est_signale(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c01", "clauses_attendues": ["durée"], "seuil_note": 1.5}')
    with pytest.raises(ErreurDonnees, match=r"seuil_note"):
        valider_fichier(chemin, RACINE / "eval" / "contrats")


def test_fichier_absent_est_une_erreur_de_donnees_pas_un_crash(tmp_path):
    with pytest.raises(ErreurDonnees, match=r"introuvable"):
        valider_fichier(tmp_path / "absent.jsonl", RACINE / "eval" / "contrats")


def test_ligne_vide_est_ignoree_sans_erreur(tmp_path):
    chemin = _ecrire(tmp_path, '{"contrat_id": "c01", "clauses_attendues": ["durée"]}', "", "  ")
    rapport = valider_fichier(chemin, RACINE / "eval" / "contrats")
    assert rapport["lignes"] == 1 and rapport["erreurs"] == []
