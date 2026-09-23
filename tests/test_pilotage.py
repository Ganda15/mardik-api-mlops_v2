"""Brique 16 (Chantier 2) — l'API de pilotage, la page avec le bouton, et le rollback par GitHub Actions.

Spec Ch2 §2 (contrat figé avant le code) :
    GET  /pilotage/etat          → 200 : actif, canary, signaux par version, alertes en cours
    GET  /pilotage/journal       → 200 : les dernières lignes, les plus récentes d'abord
    POST /pilotage/rollback      → 201 + la ligne créée · 422 sans acteur · 409 rien à annuler
                                   · 401 mauvais jeton · 403 aucun jeton d'administration configuré
Le retour arrière est une décision HUMAINE (CTO) : le clic porte un nom, jamais anonyme, et la ligne de
journal relie le rollback à l'alerte qui l'a motivé. Décision du 23/09 : aussi par la chaîne
(``.github/workflows/rollback.yml``, déclenchement manuel).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import pilotage
from app.llm_client import Bundle
from app.main import create_app
from app.telemetry import Mesure
from ops.deploy import deployer_canary
from ops.deploy import main as deploy_main

RACINE = Path(__file__).resolve().parent.parent
JETON = "jeton-admin-de-test"


@pytest.fixture
def api(registry, metriques):
    app = create_app()
    app.dependency_overrides[pilotage.get_registry] = lambda: registry
    app.dependency_overrides[pilotage.get_metriques] = lambda: metriques
    return TestClient(app)


@pytest.fixture
def canary_en_alerte(registry):
    registry.etiqueter("v2.0.0", Bundle.charger("v2"), commit="test", note_eval=1.0)
    deployer_canary("v2.0.0", 10, registry=registry)
    time.sleep(0.02)  # horloge Windows à 15,6 ms : l'alerte vient après le canary (cf. test_watcher)
    registry.journaliser("alerte", version="v2.0.0", signal="score_median", valeur=0.52, seuil=0.843,
                         fenetre={"requetes": 40}, action="aucune — décision humaine", acteur="watcher")
    return registry


def _post(api, corps, jeton=JETON):
    return api.post("/pilotage/rollback", json=corps, headers={"X-Admin-Token": jeton} if jeton else {})


# --- lecture -----------------------------------------------------------------------------


def test_etat_donne_actif_canary_signaux_et_alertes(api, canary_en_alerte, metriques):
    for _ in range(3):
        metriques.enregistrer(Mesure(ts=time.time(), version="v2.0.0", route="/analyse",
                                     latence_ms=1000, score=0.52, cout_eur=0.03))
    r = api.get("/pilotage/etat")
    assert r.status_code == 200
    e = r.json()
    assert e["active"] == "v1.0.0" and e["canary"] == "v2.0.0" and e["canary_percent"] == 10
    assert e["versions"]["v2.0.0"]["score_median"] == 0.52
    assert [a["signal"] for a in e["alertes"]] == ["score_median"]


def test_journal_du_plus_recent_au_plus_ancien(api, canary_en_alerte):
    lignes = api.get("/pilotage/journal", params={"limite": 2}).json()
    assert len(lignes) == 2
    assert lignes[0]["evenement"] == "alerte" and lignes[1]["evenement"] == "canary"


# --- le rollback : humain, nommé, tracé ---------------------------------------------------


def test_sans_jeton_configure_le_rollback_est_desactive(api, canary_en_alerte):
    assert _post(api, {"acteur": "M. Dupont"}).status_code == 403


def test_mauvais_jeton_refuse(api, canary_en_alerte, monkeypatch):
    monkeypatch.setenv("MARDIK_ADMIN_TOKEN", JETON)
    assert _post(api, {"acteur": "M. Dupont"}, jeton="faux").status_code == 401
    assert _post(api, {"acteur": "M. Dupont"}, jeton=None).status_code == 401


def test_un_clic_anonyme_est_refuse(api, canary_en_alerte, monkeypatch):
    monkeypatch.setenv("MARDIK_ADMIN_TOKEN", JETON)
    assert _post(api, {"acteur": "  "}).status_code == 422
    assert _post(api, {}).status_code == 422


def test_rien_a_annuler_409(api, registry, monkeypatch):
    monkeypatch.setenv("MARDIK_ADMIN_TOKEN", JETON)
    r = _post(api, {"acteur": "M. Dupont"})
    assert r.status_code == 409 and "précédente" in r.json()["detail"]


def test_rollback_relie_a_l_alerte_avec_son_acteur(api, canary_en_alerte, monkeypatch):
    monkeypatch.setenv("MARDIK_ADMIN_TOKEN", JETON)
    r = _post(api, {"acteur": "M. Dupont", "commentaire": "médiane effondrée"})
    assert r.status_code == 201, r.text
    ligne = r.json()
    assert ligne["evenement"] == "rollback" and ligne["acteur"] == "M. Dupont"
    assert ligne["commentaire"] == "médiane effondrée"
    assert ligne["alerte"]["signal"] == "score_median" and ligne["alerte"]["valeur"] == 0.52
    assert canary_en_alerte.canary() == (None, 0) and canary_en_alerte.active() == "v1.0.0"
    assert api.get("/pilotage/etat").json()["alertes"] == []     # l'alerte est traitée


# --- la page ------------------------------------------------------------------------------


def test_la_page_de_pilotage(api):
    r = api.get("/pilotage")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    page = r.text
    assert "Rollback" in page and 'id="acteur"' in page and "X-Admin-Token" in page
    for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert interdit not in page
    assert re.search(r'(src|href)\s*=\s*"https?://', page) is None


# --- par la chaîne : la ligne de commande et le workflow ----------------------------------


def test_la_ligne_de_commande_trace_l_acteur(canary_en_alerte, monkeypatch):
    monkeypatch.setenv("REGISTRY_PATH", str(canary_en_alerte.root))
    assert deploy_main(["rollback", "--acteur", "Era (GitHub Actions)", "--motif", "alerte médiane"]) == 0
    ligne = canary_en_alerte.journal()[-1]
    assert ligne["evenement"] == "rollback" and ligne["acteur"] == "Era (GitHub Actions)"


def test_le_workflow_de_rollback_est_manuel_et_nomme_son_acteur():
    wf = yaml.safe_load((RACINE / ".github" / "workflows" / "rollback.yml").read_text(encoding="utf-8"))
    declencheurs = wf.get("on") or wf.get(True)                 # YAML lit « on » comme True
    assert set(declencheurs) == {"workflow_dispatch"}           # jamais automatique
    assert declencheurs["workflow_dispatch"]["inputs"]["acteur"]["required"] is True
    texte = (RACINE / ".github" / "workflows" / "rollback.yml").read_text(encoding="utf-8")
    assert "ops.deploy rollback" in texte and "--acteur" in texte
    assert "git push" not in texte                              # il ne touche pas à main
