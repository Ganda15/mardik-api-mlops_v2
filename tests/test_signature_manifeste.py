"""Brique 20 (23/09) — la signature de la version saine est CALCULÉE par le gate, PORTÉE par le manifeste,
LUE par le watcher. Avant : mesurée à la main sur 8 analyses et recopiée dans eval/thresholds.yml (provisoire,
dit tel quel depuis le 23/09 matin). Règle : jamais une signature depuis un modèle simulé (MOCK) — le manifeste
de la CI n'en porte pas, et le watcher retombe alors sur eval/thresholds.yml.
"""
from __future__ import annotations

import json
import time

import pytest

from app.telemetry import Mesure
from eval import run_eval
from eval.run_eval import Rapport, evaluer
from ops.deploy import main as deploy_main
from ops.deploy import publier
from ops.watcher import tick


def test_en_mock_le_gate_ne_produit_aucune_signature(historique):
    rapport = evaluer("v2", sous_ensemble=["c01"], historique=historique)
    assert rapport.signature is None


def test_avec_le_vrai_modele_le_gate_calcule_mediane_et_part_basse(monkeypatch, historique):
    monkeypatch.setenv("MOCK", "off")                      # aucun réseau : l'analyse est remplacée ci-dessous
    scores = iter([0.99, 0.4, 0.95, 0.9])

    def _fausse_analyse(bundle, client, telemetry, texte):
        return {"durée"}, 100.0, 0.01, next(scores)

    monkeypatch.setattr(run_eval, "_analyser_une_fois", _fausse_analyse)
    rapport = evaluer("v2", sous_ensemble=["c01", "c02", "c03", "c04"], n_essais=1, historique=historique)
    assert rapport.signature == {"score_median": 0.925, "part_score_bas": 0.25, "analyses": 4}
    ligne = json.loads(historique.read_text(encoding="utf-8").splitlines()[-1])
    assert ligne["signature"]["analyses"] == 4           # l'historique la garde


def _rapport(signature):
    return Rapport(version="v2.0.0", date="2026-09-23T00:00:00+00:00", essais=1, note=1.0, par_contrat={},
                   latence_p95_ms=1000.0, cout_moyen_eur=0.01, passe=True, signature=signature)


def test_publier_porte_la_signature_dans_le_manifeste(registry):
    publier("v2.0.0", rapport=_rapport({"score_median": 0.97, "part_score_bas": 0.0, "analyses": 12}), registry=registry)
    assert registry.manifest("v2.0.0")["signature"]["score_median"] == 0.97
    publier("v2.0.1", rapport=_rapport(None), registry=registry)
    assert registry.manifest("v2.0.1")["signature"] is None     # CI (MOCK) : présent, mais vide — dit


def _trafic(metriques, version, score, n=35):
    for _ in range(n):
        metriques.enregistrer(Mesure(ts=time.time(), version=version, route="/v2/analyse",
                                     latence_ms=1000, score=score, cout_eur=0.02))


def test_le_watcher_lit_la_signature_du_manifeste_de_la_version_active(registry, metriques):
    publier("v2.0.0", rapport=_rapport({"score_median": 0.90, "part_score_bas": 0.0, "analyses": 12}), registry=registry)
    registry.definir_actif("v2.0.0")
    _trafic(metriques, "v2.0.0", score=0.78)              # 0,78 > 0,90 − 0,15 : sain pour CETTE version
    assert tick(registry, metriques)["alertes"] == []


def test_sans_signature_au_manifeste_le_watcher_retombe_sur_le_fichier_de_seuils(registry, metriques):
    publier("v2.0.0", rapport=_rapport(None), registry=registry)
    registry.definir_actif("v2.0.0")
    _trafic(metriques, "v2.0.0", score=0.78)              # 0,78 < 0,993 − 0,15 (eval/thresholds.yml) : alerte
    assert tick(registry, metriques)["alertes"] == ["score_median"]


def test_la_ligne_de_commande_publie_depuis_un_rapport_sauvegarde(tmp_path, registry, monkeypatch):
    """Le gate réel tourne à part (gate-reel.yml, brique 21) : la publication réutilise son rapport, sans
    ré-évaluer — donc sans payer une deuxième fois."""
    monkeypatch.setenv("REGISTRY_PATH", str(registry.root))
    monkeypatch.setattr("ops.deploy.evaluer", lambda *a, **k: pytest.fail("le gate ne doit pas retourner"))
    chemin = tmp_path / "rapport.json"
    chemin.write_text(json.dumps(_rapport({"score_median": 0.96, "part_score_bas": 0.0, "analyses": 12}).to_dict()),
                      encoding="utf-8")
    assert deploy_main(["publier", "v2.3.0", "--rapport", str(chemin)]) == 0
    assert registry.manifest("v2.3.0")["signature"]["analyses"] == 12
