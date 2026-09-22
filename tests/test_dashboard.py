"""Tests unitaires du tableau de bord — brique 10 du Chantier 1.

Le calcul par version (trafic, p50/p95, taux d'erreur, score moyen) est déjà couvert en
profondeur par le test d'acceptance fourni (test_dashboard_par_version). Ce fichier couvre
ce qu'il ne couvre pas : aucun trafic dans la fenêtre.
"""
from __future__ import annotations

from ops.dashboard import rendre_texte, resume


def test_resume_sans_trafic_ne_plante_pas(metriques, registry):
    r = resume(metriques, fenetre_s=60, registry=registry)
    assert r["total"] == 0
    assert r["par_version"] == {}
    assert rendre_texte(r)  # ne plante pas, produit du texte même à vide
