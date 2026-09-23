"""Les cinq signaux de pilotage, par version. Brique 14 (Chantier 2).

Conception Ch2 §2 et §3 — une seule source, les ``Mesure`` de ``ops/metrics.jsonl`` :

* latence P95 (erreurs exclues) — la contrainte client est un P95, pas une moyenne ;
* coût moyen par analyse ;
* taux d'erreur ;
* **distribution** du score : part des scores < 0,5, médiane, déciles — jamais la seule moyenne,
  qui cacherait un modèle sûr de lui sur les contrats courts et faux sur les longs ;
* part de trafic par version.

Fenêtre : les ``requetes`` dernières mesures ou les ``jours`` derniers jours, **la plus grande des
deux**. Sous ``requetes_min`` : état ``donnees_insuffisantes`` — un P95 sur quatre requêtes ment.
"""
from __future__ import annotations

import statistics
import time
from typing import Any

from app.telemetry import Mesure

SCORE_BAS = 0.5  # la bande « basse » du libellé (H6) : ce que le juriste ressent, combien de fois il relit


def _p95(valeurs: list[float]) -> float:
    if not valeurs:
        return 0.0
    tri = sorted(valeurs)
    return tri[min(len(tri) - 1, int(round(0.95 * len(tri) + 0.5)) - 1)]


def fenetre_de(mesures: list[Mesure], cfg: dict[str, Any], maintenant: float | None = None) -> list[Mesure]:
    """Les N dernières mesures ou celles des J derniers jours, la plus grande des deux."""
    maintenant = maintenant if maintenant is not None else time.time()
    tri = sorted(mesures, key=lambda m: m.ts)
    recentes = [m for m in tri if m.ts >= maintenant - float(cfg["jours"]) * 86400]
    dernieres = tri[-int(cfg["requetes"]):]
    return recentes if len(recentes) >= len(dernieres) else dernieres


def calculer_signaux(mesures: list[Mesure], requetes_min: int) -> dict[str, Any]:
    n = len(mesures)
    valides = [m for m in mesures if not m.erreur]
    scores = sorted(m.score for m in valides if m.score is not None)
    return {
        "requetes": n,
        "etat": "ok" if n >= requetes_min else "donnees_insuffisantes",
        "latence_p95_ms": _p95([m.latence_ms for m in valides]),
        "cout_moyen_eur": round(sum(m.cout_eur for m in mesures) / n, 6) if n else 0.0,
        "taux_erreur": round(sum(1 for m in mesures if m.erreur) / n, 4) if n else 0.0,
        "part_score_bas": round(sum(1 for s in scores if s < SCORE_BAS) / len(scores), 4) if scores else None,
        "score_median": round(statistics.median(scores), 4) if scores else None,
        "score_deciles": [round(q, 4) for q in statistics.quantiles(scores, n=10)] if len(scores) >= 2 else [],
    }


def signaux_par_version(
    mesures: list[Mesure], seuils: dict[str, Any], maintenant: float | None = None
) -> dict[str, dict[str, Any]]:
    """Par version : les signaux sur sa fenêtre, et sa part du trafic dans l'ensemble des fenêtres."""
    fenetre = seuils["fenetre"]
    par_version: dict[str, list[Mesure]] = {}
    for m in mesures:
        par_version.setdefault(m.version, []).append(m)
    fenetres = {v: fenetre_de(ms, fenetre, maintenant) for v, ms in par_version.items()}
    total = sum(len(f) for f in fenetres.values())
    resultat = {}
    for version, ms in fenetres.items():
        sig = calculer_signaux(ms, int(fenetre["requetes_min"]))
        sig["trafic_pct"] = round(len(ms) / total * 100, 1) if total else 0.0
        resultat[version] = sig
    return resultat
