"""Brique 18a (Chantier 2) — ajuster un seuil à partir des distributions observées, et le tracer.

Brief, 5e puce du Chantier 2 : « ajuster les seuils des gates à partir des distributions observées, chaque ajustement
tracé au journal de pilotage ». Conception Ch2 §9 — une procédure, pas une habitude :
1. mesurer les distributions réelles sur la période ;
2. proposer de nouvelles valeurs dans eval/thresholds.yml ;
3. une pull request (elle relance le gate : filtre de chemin) — la fusion est la trace (auteur, diff, date) ;
4. une ligne ``ajustement_seuil`` au journal : la clé, l'ancienne et la nouvelle valeur, le sens, la valeur observée,
   le commit, l'auteur, le motif. Un motif est obligatoire : on n'ajuste pas « au doigt mouillé ».
"""
from __future__ import annotations

import time

import pytest
import yaml

from app.telemetry import Mesure
from ops.ajuster_seuils import ErreurAjustement, comparer, journaliser_ajustements, main, mesurer
from ops.seuils import charger_seuils

JOUR = 86400.0


def test_comparer_trouve_les_seuils_modifies_et_leur_sens():
    avant = charger_seuils()
    apres = charger_seuils()
    apres["gate"]["latence_p95_max_ms"] = 7500           # un max qui baisse : plus strict
    apres["gate"]["rappel_min"] = 0.70                    # un min qui baisse : plus souple
    apres["capture"]["score_global_max"] = 0.6            # capture élargie : ni l'un ni l'autre
    changements = {c["cle"]: c for c in comparer(avant, apres)}
    assert set(changements) == {"gate.latence_p95_max_ms", "gate.rappel_min", "capture.score_global_max"}
    assert changements["gate.latence_p95_max_ms"] == {"cle": "gate.latence_p95_max_ms", "ancien": 8000,
                                                      "nouveau": 7500, "sens": "durcissement"}
    assert changements["gate.rappel_min"]["sens"] == "assouplissement"
    assert changements["capture.score_global_max"]["sens"] == "assouplissement"


def test_rien_de_modifie_rien_a_tracer():
    assert comparer(charger_seuils(), charger_seuils()) == []


def test_chaque_ajustement_est_trace_avec_commit_auteur_motif_et_valeur_observee(registry):
    changements = [{"cle": "gate.latence_p95_max_ms", "ancien": 8000, "nouveau": 7500, "sens": "durcissement"}]
    journaliser_ajustements(changements, commit="a41c9e2", acteur="E. Gandakumar",
                            motif="P95 observé 6,4 à 7,0 s sur 3 jours", observe={"gate.latence_p95_max_ms": 7046},
                            registry=registry)
    ligne = registry.journal()[-1]
    assert ligne["evenement"] == "ajustement_seuil" and ligne["signal"] == "gate.latence_p95_max_ms"
    assert ligne["seuil"] == {"ancien": 8000, "nouveau": 7500} and ligne["sens"] == "durcissement"
    assert ligne["valeur"] == 7046 and ligne["commit"] == "a41c9e2" and ligne["acteur"] == "E. Gandakumar"
    assert ligne["commentaire"] == "P95 observé 6,4 à 7,0 s sur 3 jours"


def test_un_ajustement_sans_motif_est_refuse(registry):
    with pytest.raises(ErreurAjustement, match="motif"):
        journaliser_ajustements([{"cle": "gate.rappel_min", "ancien": 0.75, "nouveau": 0.7, "sens": "assouplissement"}],
                                commit="x", acteur="y", motif="  ", registry=registry)
    assert all(e["evenement"] != "ajustement_seuil" for e in registry.journal())


def test_mesurer_donne_la_distribution_de_la_periode_par_version():
    maintenant = time.time()
    ms = [Mesure(ts=maintenant - 2 * JOUR, version="v2.0.0", route="/analyse", latence_ms=5000, score=0.9, cout_eur=0.05),
          Mesure(ts=maintenant, version="v2.0.0", route="/analyse", latence_ms=7000, score=0.4, cout_eur=0.03),
          Mesure(ts=maintenant - 10 * JOUR, version="v2.0.0", route="/analyse", latence_ms=99999, score=0.1, cout_eur=9)]
    par = mesurer(ms, depuis_jours=3, maintenant=maintenant)
    v2 = par["v2.0.0"]
    assert v2["requetes"] == 2                            # la mesure d'il y a 10 jours est hors période
    assert v2["latence_p95_ms"] == 7000 and v2["part_score_bas"] == 0.5 and v2["score_median"] == 0.65


def test_la_ligne_de_commande_compare_au_commit_precedent_et_trace(registry, tmp_path, monkeypatch):
    avant = charger_seuils()
    apres = charger_seuils()
    apres["rollback_alerte"]["taux_erreur_max"] = 0.08
    fichier = tmp_path / "thresholds.yml"
    fichier.write_text(yaml.safe_dump(apres, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(fichier))
    monkeypatch.setenv("REGISTRY_PATH", str(registry.root))

    import ops.ajuster_seuils as mod
    reponses = {("show", "HEAD~1:eval/thresholds.yml"): yaml.safe_dump(avant, allow_unicode=True),
                ("rev-parse", "--short", "HEAD"): "b7d01f3", ("log", "-1", "--format=%an"): "Era"}
    monkeypatch.setattr(mod, "_git", lambda *args: reponses[args])

    assert main(["journaliser", "--motif", "erreurs observées < 2 % sur 5 jours"]) == 0
    ligne = registry.journal()[-1]
    assert ligne["signal"] == "rollback_alerte.taux_erreur_max" and ligne["commit"] == "b7d01f3"
    assert ligne["acteur"] == "Era" and ligne["seuil"] == {"ancien": 0.1, "nouveau": 0.08}


def test_la_ligne_de_commande_ne_plante_pas_dans_une_console_windows(registry, tmp_path, monkeypatch):
    """23/09, premier usage réel : la ligne de journal était écrite, puis print('→') plantait — la console de
    PowerShell 5.1 est en cp1252, sans flèche. Reproduit ici avec une sortie cp1252."""
    import io
    import sys

    import ops.ajuster_seuils as mod
    avant, apres = charger_seuils(), charger_seuils()
    apres["gate"]["latence_p95_max_ms"] = 7500
    fichier = tmp_path / "thresholds.yml"
    fichier.write_text(yaml.safe_dump(apres, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("MARDIK_SEUILS", str(fichier))
    monkeypatch.setenv("REGISTRY_PATH", str(registry.root))
    reponses = {("show", "HEAD~1:eval/thresholds.yml"): yaml.safe_dump(avant, allow_unicode=True),
                ("rev-parse", "--short", "HEAD"): "c0ffee1", ("log", "-1", "--format=%an"): "Era"}
    monkeypatch.setattr(mod, "_git", lambda *args: reponses[args])
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    assert main(["journaliser", "--motif", "test console"]) == 0
    console.flush()
    assert b"gate.latence_p95_max_ms" in console.buffer.getvalue()
