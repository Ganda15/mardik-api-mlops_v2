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
import html
import json
import sys
from typing import Any

from app.telemetry import Mesure, MetricsStore
from ops.registry import Registry
from ops.seuils import charger_seuils
from ops.signaux import calculer_signaux


def _percentile(valeurs: list[float], p: float) -> float:
    if not valeurs:
        return 0.0
    tri = sorted(valeurs)
    indice = min(len(tri) - 1, int(round(p * len(tri) + 0.5)) - 1)
    return tri[indice]


def resume(
    metriques: MetricsStore | None = None,
    *,
    fenetre_s: float = 300,
    registry: Registry | None = None,
) -> dict[str, Any]:
    met = metriques or MetricsStore()
    mesures = met.lire(depuis_s=fenetre_s)
    total = len(mesures)

    par_version_brut: dict[str, list[Mesure]] = {}
    for m in mesures:
        par_version_brut.setdefault(m.version, []).append(m)

    requetes_min = int(charger_seuils()["fenetre"]["requetes_min"])  # brique 14 : « données insuffisantes »
    par_version: dict[str, dict[str, Any]] = {}
    for version, ms in par_version_brut.items():
        requetes = len(ms)
        trafic_pct = round(requetes / total * 100, 1) if total else 0.0
        taux_erreur = sum(1 for m in ms if m.erreur) / requetes if requetes else 0.0

        # erreurs exclues des latences et des scores (docstring) : une requête en échec
        # n'a pas de temps de réponse significatif, ni de score
        ms_valides = [m for m in ms if not m.erreur]
        latences = [m.latence_ms for m in ms_valides]
        scores = [m.score for m in ms_valides if m.score is not None]

        par_version[version] = {
            "requetes": requetes,
            "trafic_pct": trafic_pct,
            "latence_p50_ms": _percentile(latences, 0.50),
            "latence_p95_ms": _percentile(latences, 0.95),
            "taux_erreur": round(taux_erreur, 4),
            "score_moyen": round(sum(scores) / len(scores), 3) if scores else None,
            "cout_total_eur": round(sum(m.cout_eur for m in ms), 6),
        }
        # Brique 14 (Ch2) : la distribution du score, pas seulement sa moyenne (gardée pour le test fourni).
        sig = calculer_signaux(ms, requetes_min)
        for cle in ("etat", "cout_moyen_eur", "part_score_bas", "score_median", "score_deciles"):
            par_version[version][cle] = sig[cle]

    reg = registry or Registry()
    journal = reg.journal()[-5:]

    return {"fenetre_s": fenetre_s, "total": total, "par_version": par_version, "journal": journal}


def rendre_texte(r: dict[str, Any]) -> str:
    lignes = [f"Tableau de bord — fenêtre {r['fenetre_s']:.0f} s — {r['total']} requêtes"]
    if not r["par_version"]:
        lignes.append("  (aucun trafic dans la fenêtre)")
    for version, v in r["par_version"].items():
        if v.get("part_score_bas") is None:
            score = "score —"
        else:
            score = f"score < 0,5 : {v['part_score_bas']:.0%}  médiane {v['score_median']:.2f}"
        etat = "  [données insuffisantes]" if v.get("etat") == "donnees_insuffisantes" else ""
        lignes.append(
            f"  {version:10} {v['requetes']:4} req  ({v['trafic_pct']:5.1f} %)  "
            f"p50={v['latence_p50_ms']:.0f} ms  p95={v['latence_p95_ms']:.0f} ms  "
            f"erreurs={v['taux_erreur']:.1%}  coût moyen={v.get('cout_moyen_eur', 0):.3f} €  {score}{etat}"
        )
    if r["journal"]:
        lignes.append("Derniers événements :")
        for e in r["journal"]:
            lignes.append(f"  {e.get('date', '?')}  {e.get('evenement', '?')}")
    return "\n".join(lignes)


def rendre_html(r: dict[str, Any]) -> str:
    # Les valeurs numériques (requetes, trafic_pct, latences, taux_erreur, score) sont
    # produites par des f-strings avec spécificateur de format (":.1f", ":.0f", ":.1%") :
    # leur sortie est garantie numérique, pas besoin d'échapper. "version" et les champs du
    # journal sont des chaînes d'origine externe au calcul (config du bundle, événements) :
    # échappées explicitement, même si rien d'injectable n'y transite aujourd'hui.
    def _ligne(version: str, v: dict[str, Any]) -> str:
        bas = "—" if v.get("part_score_bas") is None else f"{v['part_score_bas']:.0%}"
        med = "—" if v.get("score_median") is None else f"{v['score_median']:.2f}"
        etat = "données insuffisantes" if v.get("etat") == "donnees_insuffisantes" else "ok"
        return (
            f"<tr><td>{html.escape(version)}</td><td>{v['requetes']}</td>"
            f"<td>{v['trafic_pct']:.1f}&nbsp;%</td>"
            f"<td>{v['latence_p50_ms']:.0f}&nbsp;ms</td><td>{v['latence_p95_ms']:.0f}&nbsp;ms</td>"
            f"<td>{v['taux_erreur']:.1%}</td><td>{v.get('cout_moyen_eur', 0):.3f}&nbsp;€</td>"
            f"<td>{bas}</td><td>{med}</td><td>{etat}</td></tr>"
        )

    lignes_versions = "".join(_ligne(version, v) for version, v in r["par_version"].items())
    lignes_journal = "".join(
        f"<li>{html.escape(str(e.get('date', '?')))} — {html.escape(str(e.get('evenement', '?')))}</li>"
        for e in r["journal"]
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>Mardik — tableau de bord</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>Mardik — tableau de bord</h1>
  <p>Fenêtre : {r['fenetre_s']:.0f} s — {r['total']} requêtes</p>
  <table>
    <tr><th>Version</th><th>Requêtes</th><th>Trafic</th><th>P50</th><th>P95</th><th>Erreurs</th><th>Coût moyen</th><th>Scores &lt; 0,5</th><th>Médiane du score</th><th>État</th></tr>
    {lignes_versions}
  </table>
  <h2>Derniers événements</h2>
  <ul>{lignes_journal}</ul>
</body>
</html>"""


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
