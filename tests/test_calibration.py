"""Calibration statistique du score de confiance (Platt) — la probabilité mesurée qu'une clause renvoyée soit juste.

Le score brut (`confiance`) reste inchangé : la dérive, les seuils et la signature du watcher sont mesurés sur lui.
La calibration ajoute `confiance_calibree` par clause et `confiance_globale_calibree` : une probabilité apprise sur le
jeu de référence (eval/calibration_donnees.jsonl), versionnée dans le bundle (parametres.calibration).
"""
import math

import pytest

from app.pipeline.calibration import calibrer
from eval.calibration import ajuster_platt, ece, evaluer_loco


def test_calibrer_sans_parametres_rend_none():
    assert calibrer(0.9, None) is None
    assert calibrer(0.9, {}) is None


def test_calibrer_est_une_probabilite_bornee():
    p = {"methode": "platt", "a": 2.0, "b": 0.5}
    for s in (0.0, 0.01, 0.5, 0.99, 1.0):
        v = calibrer(s, p)
        assert 0.0 <= v <= 1.0


def test_calibrer_est_monotone():
    p = {"methode": "platt", "a": 1.5, "b": -0.2}
    valeurs = [calibrer(s, p) for s in (0.1, 0.3, 0.5, 0.7, 0.9, 0.99)]
    assert valeurs == sorted(valeurs)


def test_calibrer_identite_quand_a1_b0():
    p = {"methode": "platt", "a": 1.0, "b": 0.0}
    assert calibrer(0.8, p) == pytest.approx(0.8, abs=1e-3)


def test_ajuster_platt_retrouve_une_surconfiance():
    # Le modèle dit 0.9 mais n'a raison que 60 % du temps : la calibration doit ramener vers 0.6.
    xs = [0.9] * 100
    ys = [1] * 60 + [0] * 40
    p = ajuster_platt(xs, ys)
    assert calibrer(0.9, p) == pytest.approx(0.6, abs=0.05)


def test_ajuster_platt_ne_diverge_pas_si_tout_est_juste():
    xs = [0.95, 0.99, 0.97, 0.93]
    ys = [1, 1, 1, 1]
    p = ajuster_platt(xs, ys)
    assert all(math.isfinite(v) for v in (p["a"], p["b"]))
    assert calibrer(0.97, p) > 0.8


def test_ece_nulle_pour_des_probabilites_parfaites():
    assert ece([1.0, 1.0, 0.0, 0.0], [1, 1, 0, 0]) == pytest.approx(0.0)


def test_ece_mesure_la_surconfiance():
    assert ece([0.9] * 10, [1] * 5 + [0] * 5) == pytest.approx(0.4, abs=1e-6)


def test_evaluer_loco_exclut_le_contrat_evalue():
    points = [{"contrat": c, "score": 0.9, "correct": 1 if i % 4 else 0}
              for c in ("c1", "c2", "c3") for i in range(8)]
    r = evaluer_loco(points)
    assert r["n"] == 24 and r["contrats"] == 3
    assert 0.0 <= r["ece_apres"] <= 1.0 and 0.0 <= r["ece_avant"] <= 1.0


def test_v2_renvoie_les_champs_calibres(client, contrat):
    r = client.post("/v2/analyse", json={"texte": contrat("c01")})
    assert r.status_code == 200
    corps = r.json()
    assert "confiance_globale_calibree" in corps
    for c in corps["clauses"]:
        assert "confiance_calibree" in c
        if c["confiance_calibree"] is not None:
            assert 0.0 <= c["confiance_calibree"] <= 1.0


def test_la_v1_ne_gagne_toujours_aucun_champ(client, contrat):
    r = client.post("/v1/analyse", json={"texte": contrat("c01")})
    assert set(r.json()) == {"clauses", "modele", "version", "tronque"}


def test_calibrer_respecte_le_plafond_statistique():
    # 186 justes sur 186 ne prouvent pas « jamais faux » : règle de trois, erreur < 3/n -> plafond 1 - 3/n.
    p = {"methode": "platt", "a": 3.0, "b": 0.0, "plafond": 0.984}
    assert calibrer(0.999, p) == 0.984
    assert calibrer(0.2, p) < 0.984


def test_le_bundle_v2_porte_une_calibration_plafonnee():
    from app.llm_client import Bundle
    c = Bundle.charger("v2").parametres["calibration"]
    assert c["methode"] == "platt" and 0 < c["plafond"] < 1
    assert c["plafond"] == round(1 - 3 / (c["points"] - c["faux"]), 3)
