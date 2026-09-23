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


# Constaté le 22/09 pendant la preuve de rollback : CANARY_PERCENT=10 dans .env forçait le
# routage à 10 % (3 requêtes sur 30) pendant que /gateway/etat annonçait les 50 % du registre.
# L'état affiché doit être le pourcentage EFFECTIF, et dire d'où il vient.


def _canary_50(registry):
    from app.llm_client import Bundle

    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="test", note_eval=1.0)
    registry.definir_canary("v2.0.0", 50)


def test_etat_rapporte_le_pourcentage_du_registre_sans_variable(client, registry):
    _canary_50(registry)
    etat = client.get("/gateway/etat").json()
    assert etat["canary"] == "v2.0.0"
    assert etat["canary_percent"] == 50
    assert etat["source"] == "registre"


def test_etat_rapporte_le_pourcentage_effectif_force_par_env(client, registry, monkeypatch):
    _canary_50(registry)
    monkeypatch.setenv("CANARY_PERCENT", "10")
    etat = client.get("/gateway/etat").json()
    assert etat["canary_percent"] == 10, "c'est ce que /analyse applique vraiment"
    assert etat["source"] == "env:CANARY_PERCENT"
    assert etat["canary_percent_registre"] == 50


def test_variable_vide_vaut_absente(client, registry, monkeypatch):
    # `CANARY_PERCENT=` (vide) dans .env ne doit ni planter (int('')) ni forcer 0
    _canary_50(registry)
    monkeypatch.setenv("CANARY_PERCENT", "")
    etat = client.get("/gateway/etat").json()
    assert etat["canary_percent"] == 50
    assert etat["source"] == "registre"
