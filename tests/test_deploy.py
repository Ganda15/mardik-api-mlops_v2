"""Tests unitaires du déploiement — brique 8 du Chantier 1.

Couvre ce que les tests d'acceptance ne testent pas explicitement : le pourcentage canary
par défaut lu depuis l'environnement, et le refus explicite d'un rollback sans version
précédente connue.
"""
from __future__ import annotations

import pytest

from ops.deploy import ErreurDeploiement, deployer_canary, rollback
from ops.registry import Registry


def test_deployer_canary_utilise_le_defaut_canary_percent_de_lenv(registry, monkeypatch):
    from app.llm_client import Bundle

    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="abc", note_eval=0.9)
    monkeypatch.setenv("CANARY_PERCENT", "15")
    index = deployer_canary("v2.0.0", registry=registry)
    assert index["canary_percent"] == 15


def test_rollback_sans_version_precedente_leve_une_erreur(tmp_path):
    reg = Registry(tmp_path / "registry")  # registre neuf, aucune version, aucune "precedente"
    with pytest.raises(ErreurDeploiement):
        rollback(registry=reg)
