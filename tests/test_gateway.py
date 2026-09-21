"""Tests unitaires de la gateway — brique 9 du Chantier 1.

choisir_version est testée de façon exhaustive par le test d'acceptance
(tirages 0..99, canary_percent=30 → exactement 30 tirages canary) ; ce fichier couvre
ce que ce test ne couvre pas : aucun canary déployé, et la frontière exacte du pourcentage.
"""
from __future__ import annotations

from app.gateway import choisir_version


def test_choisir_version_sans_canary_renvoie_toujours_lactive():
    for tirage in (0.0, 10.0, 50.0, 99.9):
        assert choisir_version("v1.0.0", None, 50, tirage) == "v1.0.0"


def test_choisir_version_tirage_egal_au_pourcentage_nest_pas_le_canary():
    # tirage < canary_percent (strict) : un tirage égal au pourcentage ne bascule pas
    assert choisir_version("v1.0.0", "v2.0.0", 30, 30.0) == "v1.0.0"
    assert choisir_version("v1.0.0", "v2.0.0", 30, 29.999) == "v2.0.0"
