"""Brique 15 (Chantier 2) — le watcher : il alerte, il promeut, il ne recule JAMAIS seul.

Conception Ch2 §4.1, §4.2, §6.1 ; spec Ch2 §3 :
* un signal de dérive franchi → une ligne ``alerte`` (signal, valeur, seuil, fenêtre, acteur watcher) ;
  le retour arrière reste une décision humaine (CTO) : l'index du registre ne bouge pas ;
* canary : quand la fenêtre d'observation s'achève (assez de mesures depuis la dernière décision, assez
  de temps au palier), **tous** les critères tiennent → palier suivant 10 → 50 → 100 ; sinon
  ``refus_promotion`` avec le critère en échec ; deux refus de suite → alerte pour décision humaine ;
* sous le minimum de mesures : aucune décision.
"""
from __future__ import annotations

import time

import pytest
import yaml

from app.llm_client import Bundle
from app.telemetry import Mesure
from ops.deploy import deployer_canary
from ops.seuils import charger_seuils
from ops.watcher import tick


@pytest.fixture
def seuils_demo(tmp_path, monkeypatch):
    """Démo : 5 mesures suffisent et aucun délai au palier — par configuration, jamais par le code."""
    s = charger_seuils()
    s["fenetre"]["requetes_min"] = 5
    s["promotion"]["requetes_min"] = 5
    s["promotion"]["jours_min"] = 0
    chemin = tmp_path / "seuils-demo.yml"
    chemin.write_text(yaml.safe_dump(s, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(chemin))
    return s


@pytest.fixture
def canary_v2(registry):
    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="test", note_eval=1.0)
    deployer_canary("v2.0.0", 10, registry=registry)
    return registry


def le_temps_passe():
    """Après une décision, le trafic arrive plus tard. Sous Windows l'horloge avance par pas de 15,6 ms
    (mesuré le 23/09) : sans cette pause, une mesure prise juste après une décision porte le MÊME
    horodatage qu'elle et sort de la fenêtre « depuis la décision » — test instable, pas le code."""
    time.sleep(0.02)


def trafic(metriques, version, n, *, score=0.99, erreur=False, latence=1500.0, cout=0.03):
    le_temps_passe()
    for _ in range(n):
        metriques.enregistrer(
            Mesure(ts=time.time(), version=version, route="/analyse", latence_ms=latence,
                   erreur=erreur, score=None if version == "v1.0.0" else score, cout_eur=cout)
        )


def lignes(registry, evenement):
    return [e for e in registry.journal() if e["evenement"] == evenement]


def test_derive_du_score_alerte_avec_signal_valeur_seuil_et_ne_recule_pas(seuils_demo, canary_v2, metriques):
    trafic(metriques, "v2.0.0", 6, score=0.52)  # ce que produit derive-score, mesuré le 22/09
    tick(registry=canary_v2, metriques=metriques)
    alertes = [a for a in lignes(canary_v2, "alerte") if a.get("signal") == "score_median"]
    assert len(alertes) == 1
    a = alertes[0]
    assert a["version"] == "v2.0.0" and a["acteur"] == "watcher"
    assert a["valeur"] == 0.52 and a["seuil"] == pytest.approx(0.843)
    assert a["fenetre"]["requetes"] == 6
    assert canary_v2.canary() == ("v2.0.0", 10)          # jamais de retour arrière automatique
    assert lignes(canary_v2, "rollback") == []


def test_la_meme_alerte_n_est_pas_repetee_a_chaque_tour(seuils_demo, canary_v2, metriques):
    trafic(metriques, "v2.0.0", 6, score=0.52)
    tick(registry=canary_v2, metriques=metriques)
    tick(registry=canary_v2, metriques=metriques)
    assert len([a for a in lignes(canary_v2, "alerte") if a.get("signal") == "score_median"]) == 1


def test_canary_conforme_monte_de_palier_puis_devient_active(seuils_demo, canary_v2, metriques):
    trafic(metriques, "v1.0.0", 6)
    trafic(metriques, "v2.0.0", 6)
    tick(registry=canary_v2, metriques=metriques)
    assert canary_v2.canary() == ("v2.0.0", 50)
    p = lignes(canary_v2, "promotion")[-1]
    assert p["palier"] == 50 and p["acteur"] == "watcher" and "valeurs" in p

    trafic(metriques, "v2.0.0", 6)                          # une nouvelle fenêtre, après la décision
    tick(registry=canary_v2, metriques=metriques)
    assert canary_v2.active() == "v2.0.0" and canary_v2.canary() == (None, 0)
    assert canary_v2.index()["precedente"] == "v1.0.0"


def test_canary_non_conforme_n_est_pas_promu(seuils_demo, canary_v2, metriques):
    trafic(metriques, "v1.0.0", 6)
    trafic(metriques, "v2.0.0", 4)
    trafic(metriques, "v2.0.0", 2, erreur=True)            # 33 % d'erreurs
    tick(registry=canary_v2, metriques=metriques)
    assert canary_v2.canary() == ("v2.0.0", 10)
    refus = lignes(canary_v2, "refus_promotion")[-1]
    assert "taux_erreur" in refus["criteres_en_echec"] and refus["signal"] == "taux_erreur"


def test_deux_refus_de_suite_alertent_pour_decision_humaine(seuils_demo, canary_v2, metriques):
    for _ in range(2):
        trafic(metriques, "v2.0.0", 6, latence=9000)       # P95 au-dessus de 8 s
        tick(registry=canary_v2, metriques=metriques)
    assert len(lignes(canary_v2, "refus_promotion")) == 2
    assert any(a.get("signal") == "refus_consecutifs" for a in lignes(canary_v2, "alerte"))


def test_pas_assez_de_mesures_aucune_decision(seuils_demo, canary_v2, metriques):
    trafic(metriques, "v2.0.0", 3)
    tick(registry=canary_v2, metriques=metriques)
    assert canary_v2.canary() == ("v2.0.0", 10)
    assert lignes(canary_v2, "promotion") == [] and lignes(canary_v2, "refus_promotion") == []


def test_le_temps_minimum_au_palier_est_respecte(seuils_demo, canary_v2, metriques, tmp_path, monkeypatch):
    s = seuils_demo
    s["promotion"]["jours_min"] = 1
    chemin = tmp_path / "seuils-1-jour.yml"
    chemin.write_text(yaml.safe_dump(s, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(chemin))
    trafic(metriques, "v2.0.0", 6)
    tick(registry=canary_v2, metriques=metriques)
    assert canary_v2.canary() == ("v2.0.0", 10)             # un jour pas écoulé : on attend


def test_sans_canary_une_version_saine_ne_produit_rien(seuils_demo, registry, metriques):
    trafic(metriques, "v1.0.0", 10)
    avant = len(registry.journal())
    tick(registry=registry, metriques=metriques)
    assert len(registry.journal()) == avant
