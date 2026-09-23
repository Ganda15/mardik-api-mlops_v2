"""Le détecteur de dérive, mesuré dans les deux sens. Brique 18b (Chantier 2), critère A3 de la spec.

    mesurer_detecteur(saines, derivees, seuils) -> {taux_detection, taux_fausses_alertes, …}
    python -m ops.detecteur --saines "2026-09-21T00:00/2026-09-24T00:00" --derive "2026-09-22T10:30/2026-09-22T11:00"

Question de réflexion du brief : « comment distinguez-vous une vraie dérive du bruit ? ». Réponse mesurée, pas affirmée :
**bootstrap** — on tire ``tirages`` fenêtres de ``taille`` requêtes (la taille minimale du watcher, 30), avec remise, dans
un groupe de mesures réelles saines puis dans un groupe dérivé ; on applique à chaque fenêtre la règle EXACTE du watcher
(``_signaux_franchis``). Part des fenêtres dérivées qui alertent = taux de détection ; part des fenêtres saines qui
alertent = taux de fausses alertes. Graine fixe : reproductible.

Limite, dite telle quelle : le bootstrap ré-échantillonne les mesures qu'on a ; avec une vingtaine de mesures réelles par
groupe, il dit comment le détecteur se comporte SUR CES MESURES, pas sur toute la production future.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from typing import Any

from app.telemetry import Mesure, MetricsStore
from ops.seuils import charger_seuils
from ops.signaux import calculer_signaux
from ops.watcher import _signaux_franchis

MINIMUM_PAR_GROUPE = 4
SIGNAUX_SCORE = {"part_score_bas", "score_median"}   # la dérive du modèle ; P95 et erreurs sont des contraintes client


class ErreurDetecteur(ValueError):
    """Pas assez de mesures réelles pour mesurer le détecteur."""


def _taux(mesures: list[Mesure], seuils: dict[str, Any], taille: int, tirages: int, hasard: random.Random):
    alertes, alertes_score, par_signal = 0, 0, {}
    for _ in range(tirages):
        fenetre = hasard.choices(mesures, k=taille)
        franchis = [f[0] for f in _signaux_franchis(calculer_signaux(fenetre, taille), seuils)]
        alertes += bool(franchis)
        alertes_score += bool(SIGNAUX_SCORE & set(franchis))
        for signal in franchis:
            par_signal[signal] = par_signal.get(signal, 0) + 1
    return (round(alertes / tirages, 4), round(alertes_score / tirages, 4),
            {s: round(n / tirages, 4) for s, n in sorted(par_signal.items())})


def mesurer_detecteur(
    saines: list[Mesure],
    derivees: list[Mesure],
    seuils: dict[str, Any],
    *,
    taille: int = 30,
    tirages: int = 1000,
    graine: int = 42,
) -> dict[str, Any]:
    for nom, groupe in (("saines", saines), ("dérivées", derivees)):
        if len(groupe) < MINIMUM_PAR_GROUPE:
            raise ErreurDetecteur(f"mesures {nom} : {len(groupe)}, il en faut au moins {MINIMUM_PAR_GROUPE}")
    hasard = random.Random(graine)
    fausses, fausses_score, fausses_par_signal = _taux(saines, seuils, taille, tirages, hasard)
    detection, detection_score, detection_par_signal = _taux(derivees, seuils, taille, tirages, hasard)
    return {
        # le détecteur de dérive du score : ce qu'on lui confie
        "taux_detection_derive_score": detection_score,
        "taux_fausses_alertes_derive_score": fausses_score,
        # tous signaux confondus : inclut les contraintes client (P95, erreurs) franchies par le trafic « sain »
        "taux_detection": detection,
        "taux_fausses_alertes": fausses,
        "detection_par_signal": detection_par_signal,
        "fausses_alertes_par_signal": fausses_par_signal,
        "n_saines": len(saines),
        "n_derivees": len(derivees),
        "taille": taille,
        "tirages": tirages,
        "graine": graine,
    }


def _intervalle(texte: str) -> tuple[float, float]:
    debut, fin = texte.split("/")
    conv = lambda t: datetime.fromisoformat(t if "+" in t or t.endswith("Z") else t + "+00:00").timestamp()  # noqa: E731
    return conv(debut), conv(fin)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mesurer le détecteur de dérive dans les deux sens (Ch2, brique 18b)")
    p.add_argument("--version", default="v2.0.0")
    p.add_argument("--saines", required=True, help="intervalle UTC ISO début/fin des mesures saines")
    p.add_argument("--derive", required=True, help="intervalle UTC ISO début/fin des mesures sous dérive")
    p.add_argument("--cout-min", type=float, default=0.005, help="écarte les analyses simulées (MOCK coûte ~0,002 €)")
    p.add_argument("--taille", type=int, default=30)
    p.add_argument("--tirages", type=int, default=1000)
    args = p.parse_args(argv)

    d0, d1 = _intervalle(args.derive)
    s0, s1 = _intervalle(args.saines)
    reelles = [m for m in MetricsStore().lire() if m.version == args.version and not m.erreur
               and m.score is not None and m.cout_eur >= args.cout_min]
    derivees = [m for m in reelles if d0 <= m.ts <= d1]
    saines = [m for m in reelles if s0 <= m.ts <= s1 and not d0 <= m.ts <= d1]
    print(json.dumps(mesurer_detecteur(saines, derivees, charger_seuils(), taille=args.taille, tirages=args.tirages),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
