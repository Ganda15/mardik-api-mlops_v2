"""Tableau de bord : latence, erreurs, score de confiance, trafic par version. [STUB]

Contrat attendu :

    resume(metriques=None, *, fenetre_s=300) -> dict
        Agrège les mesures des ``fenetre_s`` dernières secondes de
        ``MetricsStore`` (``ops/metrics.jsonl`` par défaut) :
        {
          "fenetre_s": 300, "total": 128,
          "par_version": {
             "v1.0.0": {"requetes": 115, "trafic_pct": 89.8, "latence_p50_ms": …,
                        "latence_p95_ms": …, "taux_erreur": 0.02,
                        "score_moyen": null, "cout_total_eur": …},
             "v2.0.0": {… "score_moyen": 0.84 …}
          },
          "journal": [ …5 derniers événements de déploiement… ]
        }
        Les versions sans trafic dans la fenêtre n'apparaissent pas.
        ``score_moyen`` vaut ``None`` pour une version qui ne produit pas de
        score (v1). Les erreurs sont exclues des latences et des scores.

    python -m ops.dashboard              → affiche le résumé en texte
    python -m ops.dashboard --serve      → page HTML auto-rafraîchie sur :8501
                                           (service ``dashboard`` du docker-compose)
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.telemetry import MetricsStore
from ops.registry import Registry


def resume(
    metriques: MetricsStore | None = None,
    *,
    fenetre_s: float = 300,
    registry: Registry | None = None,
) -> dict[str, Any]:
    raise NotImplementedError("dashboard.resume — agrégats par version sur la fenêtre")


def rendre_texte(r: dict[str, Any]) -> str:
    raise NotImplementedError("dashboard.rendre_texte — rendu texte du résumé")


def rendre_html(r: dict[str, Any]) -> str:
    raise NotImplementedError("dashboard.rendre_html — page HTML auto-rafraîchie")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tableau de bord Mardik")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--fenetre", type=float, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.serve:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse

        app = FastAPI(title="Mardik dashboard")

        @app.get("/", response_class=HTMLResponse)
        def page() -> str:
            return rendre_html(resume(fenetre_s=args.fenetre))

        @app.get("/api")
        def api() -> dict[str, Any]:
            return resume(fenetre_s=args.fenetre)

        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
        return 0
    r = resume(fenetre_s=args.fenetre)
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else rendre_texte(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
