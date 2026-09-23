"""23/09 — le gate écrivait ses mesures dans eval/.metrics_eval.jsonl même en MOCK, depuis les tests :
486 lignes et 7,23 € de faux coûts trouvés à côté des vraies mesures. EVAL_METRICS_PATH isole
(conftest → tmp) ; sans la variable, le fichier réel reste le défaut.
"""
from __future__ import annotations

from eval.run_eval import evaluer


def test_le_gate_ecrit_ses_mesures_la_ou_l_environnement_le_dit(tmp_path, monkeypatch, historique):
    cible = tmp_path / "mesures_du_gate.jsonl"
    monkeypatch.setenv("EVAL_METRICS_PATH", str(cible))
    evaluer("v2", sous_ensemble=["c01"], historique=historique)
    assert cible.exists()
    assert len(cible.read_text(encoding="utf-8").splitlines()) >= 1
