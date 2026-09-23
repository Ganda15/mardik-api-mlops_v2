"""Brique 18b (Chantier 2) — le détecteur de dérive mesuré dans les deux sens (critère A3 de la spec).

Question de réflexion du brief : « comment distinguez-vous une vraie dérive du bruit ? ». Conception Ch2 §3 : avant de
confier une alerte au détecteur, deux chiffres — le taux de détection sur du trafic dégradé, le taux de fausses alertes
sur du trafic sain. Méthode : le bootstrap — on tire au hasard, avec remise, de nombreuses fenêtres de la taille du
watcher (30 requêtes) dans chaque groupe de mesures réelles, et on applique à chaque fenêtre la règle EXACTE du watcher
(``ops.watcher._signaux_franchis``). Graine fixe : le même calcul donne le même chiffre.
"""
from __future__ import annotations

import time

import pytest

from app.telemetry import Mesure
from ops.detecteur import ErreurDetecteur, mesurer_detecteur
from ops.seuils import charger_seuils


def _ms(scores, latence=5000.0):
    return [Mesure(ts=time.time(), version="v2.0.0", route="/analyse", latence_ms=latence, score=s, cout_eur=0.03)
            for s in scores]


def test_trafic_sain_zero_fausse_alerte_trafic_derive_toujours_detecte():
    r = mesurer_detecteur(_ms([0.99, 0.98, 0.995, 0.97]), _ms([0.52, 0.53, 0.51, 0.52]), charger_seuils(),
                          taille=30, tirages=200)
    assert r["taux_fausses_alertes"] == 0.0 and r["taux_detection"] == 1.0
    assert r["n_saines"] == 4 and r["n_derivees"] == 4 and r["taille"] == 30 and r["tirages"] == 200


def test_chaque_signal_a_son_propre_taux_la_mediane_voit_ce_que_la_part_rate():
    """Des scores à ~0,52 (ce que produit derive-score) : juste au-dessus de 0,5, la part < 0,5 ne bouge pas ;
    la médiane s'effondre. C'est pour cela que les deux statistiques sont surveillées."""
    r = mesurer_detecteur(_ms([0.99] * 5), _ms([0.52] * 5), charger_seuils(), taille=30, tirages=100)
    assert r["detection_par_signal"]["score_median"] == 1.0
    assert r["detection_par_signal"].get("part_score_bas", 0.0) == 0.0


def test_meme_graine_meme_resultat():
    saines, derivees = _ms([0.99, 0.2, 0.98, 0.97, 0.99]), _ms([0.52, 0.9, 0.51, 0.3])
    a = mesurer_detecteur(saines, derivees, charger_seuils(), tirages=300, graine=7)
    b = mesurer_detecteur(saines, derivees, charger_seuils(), tirages=300, graine=7)
    assert a == b


def test_trop_peu_de_mesures_reelles_refuse():
    with pytest.raises(ErreurDetecteur, match="au moins"):
        mesurer_detecteur(_ms([0.99, 0.98]), _ms([0.52] * 10), charger_seuils())


def test_la_derive_du_score_est_separee_des_contraintes_client():
    """Mesuré le 23/09 sur les analyses réelles : 3 sur 8 dépassent 8 s. Toute fenêtre saine franchit alors le P95 —
    ce n'est pas une fausse alerte de DÉRIVE, c'est la contrainte client dépassée. Le rapport sépare les deux."""
    lent = _ms([0.99] * 5, latence=10_000)
    r = mesurer_detecteur(lent, _ms([0.52] * 5), charger_seuils(), taille=30, tirages=100)
    assert r["taux_fausses_alertes"] == 1.0                      # tous signaux confondus
    assert r["taux_fausses_alertes_derive_score"] == 0.0         # le détecteur de dérive, lui, ne crie pas
    assert r["taux_detection_derive_score"] == 1.0
