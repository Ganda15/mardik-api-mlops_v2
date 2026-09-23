"""Brique 21 (23/09) — le gate RÉEL, à la main, prouvé par un tag ; la publication peut l'exiger.

Ce test ne joue pas le workflow (poser les secrets Azure est une action manuelle, hors dépôt). Il fige sa forme : manuel
seulement, MOCK off, une passe par défaut, le rapport en artefact, le tag ``eval-ok/<sha>`` ; et côté
llmops.yml, une publication qui REFUSE sans ce tag quand la variable est posée — et ne change rien sinon.
"""
from __future__ import annotations

from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
GATE_REEL = RACINE / ".github" / "workflows" / "gate-reel.yml"
LLMOPS = RACINE / ".github" / "workflows" / "llmops.yml"


def test_le_gate_reel_est_manuel_hors_mock_et_une_passe_par_defaut():
    wf = yaml.safe_load(GATE_REEL.read_text(encoding="utf-8"))
    declencheurs = wf.get("on") or wf.get(True)
    assert set(declencheurs) == {"workflow_dispatch"}
    assert declencheurs["workflow_dispatch"]["inputs"]["essais"]["default"] == "1"
    assert wf["env"]["MOCK"] == "off" and wf["env"]["LLM_PROVIDER"] == "azure"


def test_le_gate_reel_ne_contient_aucun_secret_en_clair_et_pose_le_tag():
    texte = GATE_REEL.read_text(encoding="utf-8")
    assert "secrets.AZURE_AI_API_KEY" in texte and "secrets.AZURE_AI_ENDPOINT" in texte
    assert "openai.azure.com" not in texte                     # jamais l'adresse réelle dans le dépôt
    assert "eval.run_eval --version v2 --essais" in texte
    assert 'git tag -a "eval-ok/$GITHUB_SHA"' in texte and 'git push origin "refs/tags/eval-ok/' in texte
    assert "gate-reel-${{ github.sha }}" in texte             # le rapport, retrouvable par commit
    assert "r['passe']" in texte                               # le rapport décide du tag, pas le code de sortie


def test_la_publication_exige_le_tag_seulement_si_la_variable_est_posee():
    wf = yaml.safe_load(LLMOPS.read_text(encoding="utf-8"))
    etapes = wf["jobs"]["publication"]["steps"]
    garde = next(s for s in etapes if s.get("id") == "eval-ok")
    assert "MARDIK_EXIGER_EVAL_OK" in garde["if"]              # absente : rien ne change, main ne se bloque pas
    assert "eval-ok/$SHA" in garde["run"] and "exit 1" in garde["run"]
    assert "HEAD^2" in garde["run"]                            # la tête de la PR compte aussi (fusion = autre sha)
    etiqueter = next(s for s in etapes if "ops.deploy publier" in s.get("run", ""))
    assert "steps.eval-ok.outputs.rapport" in etiqueter["run"]  # le manifeste vient du vrai rapport
