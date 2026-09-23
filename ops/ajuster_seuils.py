"""Ajuster les seuils à partir des distributions observées, et tracer chaque ajustement. Brique 18a (Chantier 2).

    python -m ops.ajuster_seuils mesurer [--jours 7]                 # 1. les distributions réelles, par version
    # 2. modifier eval/thresholds.yml ; 3. pull request (elle relance le gate) puis fusion
    python -m ops.ajuster_seuils journaliser --motif "…" [--ref HEAD~1]   # 4. une ligne par seuil changé

Brief, 5e puce du Chantier 2 ; conception Ch2 §9. La fusion de la PR est la trace git (auteur, diff, date) ; la ligne
``ajustement_seuil`` du journal de pilotage la relie à ce qui a été observé : la clé, l'ancienne et la nouvelle valeur,
le sens (``durcissement`` / ``assouplissement``), la valeur observée, le commit, l'auteur, le motif — obligatoire.
Jamais : baisser un seuil pour faire passer une version. Un assouplissement se voit dans le journal, avec son motif.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from app.telemetry import Mesure, MetricsStore
from ops.registry import Registry
from ops.seuils import charger_seuils
from ops.signaux import calculer_signaux

RACINE = Path(__file__).resolve().parent.parent
IGNORES = {"version", "signature.source"}


class ErreurAjustement(ValueError):
    """L'ajustement ne peut pas être tracé."""


def _aplatir(d: dict[str, Any], prefixe: str = "") -> dict[str, Any]:
    plat: dict[str, Any] = {}
    for cle, valeur in d.items():
        nom = f"{prefixe}{cle}"
        if isinstance(valeur, dict):
            plat.update(_aplatir(valeur, nom + "."))
        elif nom not in IGNORES:
            plat[nom] = valeur
    return plat


def _sens(cle: str, ancien: Any, nouveau: Any) -> str:
    """Un ``…max…`` qui baisse ou un ``…min…`` qui monte : plus strict. L'inverse : plus souple."""
    feuille = cle.rsplit(".", 1)[-1]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (ancien, nouveau)):
        return "changement"
    if "max" in feuille:
        return "durcissement" if nouveau < ancien else "assouplissement"
    if "min" in feuille:
        return "durcissement" if nouveau > ancien else "assouplissement"
    return "changement"


def comparer(avant: dict[str, Any], apres: dict[str, Any]) -> list[dict[str, Any]]:
    a, b = _aplatir(avant), _aplatir(apres)
    return [
        {"cle": cle, "ancien": a.get(cle), "nouveau": b.get(cle), "sens": _sens(cle, a.get(cle), b.get(cle))}
        for cle in sorted(set(a) | set(b))
        if a.get(cle) != b.get(cle)
    ]


def mesurer(mesures: list[Mesure], depuis_jours: float = 7, maintenant: float | None = None) -> dict[str, dict[str, Any]]:
    """Les distributions de la période, par version — l'étape « mesurer » avant de proposer une valeur."""
    maintenant = maintenant if maintenant is not None else time.time()
    periode = [m for m in mesures if m.ts >= maintenant - depuis_jours * 86400]
    par_version: dict[str, list[Mesure]] = {}
    for m in periode:
        par_version.setdefault(m.version, []).append(m)
    minimum = int(charger_seuils()["fenetre"]["requetes_min"])
    return {v: calculer_signaux(ms, minimum) for v, ms in par_version.items()}


def valeurs_observees(signaux: dict[str, Any] | None, cles: list[str]) -> dict[str, Any]:
    """Relie chaque clé de seuil au signal observé qui la concerne (sur la version active)."""
    if not signaux:
        return {}
    correspondances = (("p95", "latence_p95_ms"), ("taux_erreur", "taux_erreur"), ("cout", "cout_moyen_eur"),
                       ("part_score_bas", "part_score_bas"), ("mediane", "score_median"))
    observe = {}
    for cle in cles:
        for motif, signal in correspondances:
            if motif in cle:
                observe[cle] = signaux.get(signal)
                break
    return observe


def journaliser_ajustements(
    changements: list[dict[str, Any]],
    *,
    commit: str,
    acteur: str,
    motif: str,
    observe: dict[str, Any] | None = None,
    registry: Registry | None = None,
) -> int:
    if not (motif or "").strip():
        raise ErreurAjustement("motif obligatoire : un seuil s'ajuste sur des distributions observées, qu'on cite")
    reg = registry or Registry()
    for c in changements:
        reg.journaliser("ajustement_seuil", signal=c["cle"], valeur=(observe or {}).get(c["cle"]),
                        seuil={"ancien": c["ancien"], "nouveau": c["nouveau"]}, sens=c["sens"],
                        action="eval/thresholds.yml modifié", acteur=acteur, commit=commit,
                        commentaire=motif.strip())
    return len(changements)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True, check=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ajuster les seuils (Ch2, brique 18a)")
    sub = parser.add_subparsers(dest="commande", required=True)
    m = sub.add_parser("mesurer", help="distributions observées par version sur la période")
    m.add_argument("--jours", type=float, default=7)
    j = sub.add_parser("journaliser", help="une ligne ajustement_seuil par seuil changé depuis --ref")
    j.add_argument("--motif", required=True)
    j.add_argument("--ref", default="HEAD~1", help="version précédente du fichier (défaut : le commit d'avant)")
    j.add_argument("--acteur", default=None)
    args = parser.parse_args(argv)
    # La console de PowerShell 5.1 est en cp1252 : un caractère absent (ex. une flèche) y faisait planter l'affichage
    # APRÈS l'écriture au journal (23/09). Un caractère non affichable est remplacé, jamais une erreur.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.commande == "mesurer":
        par = mesurer(MetricsStore().lire(), depuis_jours=args.jours)
        if not par:
            print("Aucune mesure sur la période.")
        for version, s in par.items():
            bas = "—" if s["part_score_bas"] is None else f"{s['part_score_bas']:.1%}"
            med = "—" if s["score_median"] is None else f"{s['score_median']:.3f}"
            print(f"{version:10} {s['requetes']:5} req  P95 {s['latence_p95_ms']:.0f} ms  erreurs {s['taux_erreur']:.1%}  "
                  f"coût moyen {s['cout_moyen_eur']:.3f} €  scores < 0,5 {bas}  médiane {med}  [{s['etat']}]")
        return 0

    avant = yaml.safe_load(_git("show", f"{args.ref}:eval/thresholds.yml"))
    changements = comparer(avant, charger_seuils())
    if not changements:
        print(f"Aucun seuil modifié depuis {args.ref}.")
        return 0
    reg = Registry()
    observe = valeurs_observees(mesurer(MetricsStore().lire()).get(reg.active() or ""), [c["cle"] for c in changements])
    n = journaliser_ajustements(changements, commit=_git("rev-parse", "--short", "HEAD"),
                                acteur=args.acteur or _git("log", "-1", "--format=%an"), motif=args.motif,
                                observe=observe, registry=reg)
    for c in changements:
        print(f"{c['cle']} : {c['ancien']} -> {c['nouveau']} ({c['sens']})")
    print(f"{n} ajustement(s) tracé(s) au journal de pilotage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
