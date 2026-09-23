"""Brique 14 (Chantier 2) — les cinq signaux par version, et la distribution du score.

Conception Ch2 §2 : latence P95, coût moyen, taux d'erreur, distribution du score (part des scores
< 0,5 et médiane — jamais la seule moyenne, qui cacherait un modèle sûr de lui et faux sur les
contrats longs), part de trafic. Fenêtre : les 50 dernières requêtes ou les 2 derniers jours, la
plus grande des deux ; sous 30 requêtes, « données insuffisantes » et aucune décision.
"""
from __future__ import annotations

import time

from app.telemetry import Mesure
from ops.seuils import charger_seuils
from ops.signaux import calculer_signaux, fenetre_de, signaux_par_version

JOUR = 86400.0


def _m(score=0.9, erreur=False, latence=1000.0, cout=0.03, version="v2.0.0", age_s=0.0, maintenant=None):
    t = (maintenant or time.time()) - age_s
    return Mesure(ts=t, version=version, route="/analyse", latence_ms=latence, erreur=erreur, score=score, cout_eur=cout)


def test_part_des_scores_bas_et_mediane_pas_seulement_la_moyenne():
    ms = [_m(score=s) for s in (0.2, 0.4, 0.6, 0.8, 0.9)]
    sig = calculer_signaux(ms, requetes_min=1)
    assert sig["part_score_bas"] == 0.4        # 0,2 et 0,4 sont sous 0,5
    assert sig["score_median"] == 0.6
    assert len(sig["score_deciles"]) == 9


def test_les_erreurs_comptent_dans_le_taux_pas_dans_la_latence_ni_le_score():
    ms = [_m(latence=1000, score=0.9)] * 3 + [_m(latence=50, score=None, erreur=True)]
    sig = calculer_signaux(ms, requetes_min=1)
    assert sig["taux_erreur"] == 0.25
    assert sig["latence_p95_ms"] == 1000
    assert sig["score_median"] == 0.9


def test_sous_le_minimum_donnees_insuffisantes():
    assert calculer_signaux([_m()] * 29, requetes_min=30)["etat"] == "donnees_insuffisantes"
    assert calculer_signaux([_m()] * 30, requetes_min=30)["etat"] == "ok"


def test_une_version_sans_score_n_a_pas_de_distribution():
    sig = calculer_signaux([_m(score=None, version="v1.0.0")] * 5, requetes_min=1)
    assert sig["part_score_bas"] is None and sig["score_median"] is None and sig["score_deciles"] == []


def test_fenetre_la_plus_grande_des_deux():
    maintenant = time.time()
    cfg = {"requetes": 50, "jours": 2}
    recentes = [_m(maintenant=maintenant, age_s=60) for _ in range(60)]
    assert len(fenetre_de(recentes, cfg, maintenant)) == 60          # 60 en 2 jours > 50 dernières
    anciennes = [_m(maintenant=maintenant, age_s=5 * JOUR) for _ in range(45)]
    peu = [_m(maintenant=maintenant, age_s=60) for _ in range(10)]
    assert len(fenetre_de(anciennes + peu, cfg, maintenant)) == 50   # 10 en 2 jours < 50 dernières


def test_signaux_par_version_avec_part_de_trafic():
    maintenant = time.time()
    ms = [_m(version="v1.0.0", score=None, maintenant=maintenant)] * 30 + [_m(version="v2.0.0", maintenant=maintenant)] * 10
    par = signaux_par_version(ms, charger_seuils(), maintenant)
    assert par["v1.0.0"]["trafic_pct"] == 75.0 and par["v2.0.0"]["trafic_pct"] == 25.0
    assert par["v1.0.0"]["etat"] == "ok" and par["v2.0.0"]["etat"] == "donnees_insuffisantes"


def test_le_tableau_de_bord_montre_la_distribution(metriques, registry):
    from ops.dashboard import rendre_html, rendre_texte, resume

    for s in (0.3, 0.4, 0.9, 0.95):
        metriques.enregistrer(_m(score=s))
    r = resume(metriques, fenetre_s=60, registry=registry)
    v2 = r["par_version"]["v2.0.0"]
    assert v2["part_score_bas"] == 0.5 and v2["score_median"] == 0.65
    assert v2["etat"] == "donnees_insuffisantes"          # 4 mesures < 30
    assert "< 0,5" in rendre_texte(r) and "médiane" in rendre_texte(r)
    assert "données insuffisantes" in rendre_html(r)
