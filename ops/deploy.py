"""Déploiement : publication, canary, promotion, rollback, surveillance. [STUB]

Contrat attendu (le registre — ``ops/registry`` — enregistre ; ce module décide) :

    publier(version, *, bundle="v2", commit="local", registry=None, seuil=0.75,
            rapport=None) -> manifest
        Étiquette une version : joue le gate d'évaluation (``eval.run_eval.evaluer``)
        sur le bundle en chantier — sauf si un ``rapport`` est fourni — et
        REFUSE (``ErreurDeploiement``) si le gate échoue. Sinon dépose le bundle
        dans le registre avec commit + note d'éval, et journalise ``publication``.

    deployer_canary(version, pourcentage=None, registry=None) -> index
        Route ``pourcentage`` % du trafic vers ``version`` (défaut : CANARY_PERCENT
        de ``.env``, sinon 10). Journalise ``canary``.

    promouvoir(version, registry=None) -> index
        La version devient active pour 100 % du trafic ; l'ancienne active est
        conservée dans ``index["precedente"]`` ; le canary est retiré. Journalise
        ``promotion``.

    rollback(registry=None, motif="manuel") -> index
        Retour arrière en une opération : si un canary est en cours, il est
        retiré ; sinon l'active redevient ``precedente``. Journalise ``rollback``
        avec le motif et les versions avant/après.

    surveiller(registry=None, metriques=None, *, fenetre_s=120, score_min=0.7,
               taux_erreur_max=0.10, latence_p95_max_ms=8000, minimum=10) -> dict
        Lit les mesures récentes (``MetricsStore``) de la version sous
        surveillance (le canary s'il y en a un, sinon l'active). Dérive si
        score moyen < ``score_min``, ou taux d'erreur > ``taux_erreur_max``, ou
        P95 > ``latence_p95_max_ms`` — sur au moins ``minimum`` mesures.
        Renvoie {"version", "mesures", "derive", "motif", "rollback"}.

        ⚠️ ÉCART ASSUMÉ avec ce docstring d'origine : PAS de rollback automatique.
        Le formateur a tranché en classe (21/09) : « le rollback c'est une décision qui va
        être arbitrée » ; « pour beaucoup plus de simplicité, [ça] devrait être laissé
        manuel ». ``surveiller()`` détecte et journalise une ``alerte`` ; ``rollback``
        dans le dict renvoyé vaut TOUJOURS ``False``. Le retour arrière reste un appel
        explicite à ``rollback()`` — le geste humain, un clic. Voir la trace complète
        dans ``CONTINUITE.md`` §D quater du dossier du brief, et le test réécrit en
        conséquence dans ``tests/acceptance/test_observabilite.py``.

Ligne de commande : ``python -m ops.deploy publier v2.0.0 | canary v2.0.0 --pourcentage 10
| promouvoir v2.0.0 | rollback | surveiller [--boucle]``.
"""
from __future__ import annotations

import json
from pathlib import Path

import argparse
import os
import subprocess
import sys
import time
from typing import Any

from app.llm_client import Bundle
from app.telemetry import MetricsStore
from eval.run_eval import Rapport, evaluer
from ops.registry import Registry


class ErreurDeploiement(RuntimeError):
    pass


def _commit_courant() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "local"


def publier(
    version: str,
    *,
    bundle: str = "v2",
    commit: str | None = None,
    registry: Registry | None = None,
    seuil: float | None = None,   # None → eval/thresholds.yml (brique 13)
    rapport: Any | None = None,
) -> dict[str, Any]:
    reg = registry or Registry()
    if rapport is None:
        rapport = evaluer(bundle, seuil=seuil, registry=reg)
    if not rapport.passe:
        raise ErreurDeploiement(
            f"gate en échec pour {bundle} — publication de {version} refusée : "
            + " ; ".join(rapport.motifs)
        )

    bundle_charge = Bundle.charger(bundle)
    commit_final = commit or _commit_courant()
    # Le manifeste dit le modèle que le GATE a mesuré (rapport.modele) : publié depuis un rapport réel sur un
    # runner en MOCK, il dirait sinon modele-ci (constaté sur v2.3.1, 23/09).
    details = {"modele": rapport.modele} if getattr(rapport, "modele", None) else None
    manifest = reg.etiqueter(version, bundle_charge, commit=commit_final, note_eval=rapport.note,
                             signature=getattr(rapport, "signature", None), details=details)
    reg.journaliser("publication", version=version, commit=commit_final, note_eval=rapport.note)
    return manifest


def deployer_canary(
    version: str, pourcentage: int | None = None, registry: Registry | None = None
) -> dict[str, Any]:
    reg = registry or Registry()
    pct = pourcentage if pourcentage is not None else int(os.environ.get("CANARY_PERCENT", "10"))
    reg.definir_canary(version, pct)
    reg.journaliser("canary", version=version, pourcentage=pct)
    return reg.index()


def promouvoir(version: str, registry: Registry | None = None) -> dict[str, Any]:
    reg = registry or Registry()
    reg.manifest(version)  # doit exister dans le registre
    idx = reg.index()
    precedente = idx.get("active")
    reg.ecrire_index({"active": version, "canary": None, "canary_percent": 0, "precedente": precedente})
    reg.journaliser("promotion", version=version, precedente=precedente)
    return reg.index()


def rollback(
    registry: Registry | None = None,
    motif: str = "manuel",
    *,
    acteur: str | None = None,
    commentaire: str | None = None,
    alerte: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retour arrière — toujours une décision humaine (CTO). Brique 16 (Ch2) : la ligne de journal
    porte aussi qui a décidé (``acteur``), pourquoi (``commentaire``), l'alerte qui l'a motivé, et la
    version quittée (``version``) — le lien signal → décision que demande le test 10 du brief."""
    reg = registry or Registry()
    idx = reg.index()
    avant = dict(idx)

    canary, _pct = reg.canary()
    quittee = canary or idx.get("active")
    if canary:
        nouvel_index = {**idx, "canary": None, "canary_percent": 0}
    else:
        precedente = idx.get("precedente")
        if precedente is None:
            raise ErreurDeploiement("rollback impossible : aucune version précédente connue")
        nouvel_index = {**idx, "active": precedente, "canary": None, "canary_percent": 0}

    reg.ecrire_index(nouvel_index)
    apres = reg.index()
    details: dict[str, Any] = {"version": quittee, "motif": motif, "avant": avant, "apres": apres}
    if acteur:
        details["acteur"] = acteur
    if commentaire:
        details["commentaire"] = commentaire
    if alerte:
        details["alerte"] = alerte
    reg.journaliser("rollback", **details)
    return apres


def surveiller(
    registry: Registry | None = None,
    metriques: MetricsStore | None = None,
    *,
    fenetre_s: float = 120,
    score_min: float = 0.7,
    taux_erreur_max: float = 0.10,
    latence_p95_max_ms: float = 8000,
    minimum: int = 10,
) -> dict[str, Any]:
    reg = registry or Registry()
    met = metriques or MetricsStore()

    canary, _pct = reg.canary()
    version_surveillee = canary or reg.active()
    mesures = [m for m in met.lire(depuis_s=fenetre_s) if m.version == version_surveillee]

    if len(mesures) < minimum:
        return {
            "version": version_surveillee,
            "mesures": len(mesures),
            "derive": False,
            "motif": None,
            "rollback": False,
        }

    scores = [m.score for m in mesures if m.score is not None]
    score_moyen = sum(scores) / len(scores) if scores else None
    taux_erreur = sum(1 for m in mesures if m.erreur) / len(mesures)
    latences = sorted(m.latence_ms for m in mesures)
    p95 = latences[min(len(latences) - 1, int(round(0.95 * len(latences) + 0.5)) - 1)]

    motif: str | None = None
    if score_moyen is not None and score_moyen < score_min:
        motif = f"score moyen {score_moyen:.3f} < {score_min}"
    elif taux_erreur > taux_erreur_max:
        motif = f"taux d'erreur {taux_erreur:.3f} > {taux_erreur_max}"
    elif p95 > latence_p95_max_ms:
        motif = f"latence p95 {p95:.0f} ms > {latence_p95_max_ms:.0f} ms"

    derive = motif is not None
    if derive:
        # Alerte seulement — jamais de rollback automatique (décision du formateur, 21/09).
        reg.journaliser("alerte", version=version_surveillee, motif=motif, mesures=len(mesures))

    return {
        "version": version_surveillee,
        "mesures": len(mesures),
        "derive": derive,
        "motif": motif,
        "rollback": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Déploiement Mardik")
    sub = parser.add_subparsers(dest="commande", required=True)
    p = sub.add_parser("publier")
    p.add_argument("version")
    p.add_argument("--bundle", default="v2")
    p.add_argument("--seuil", type=float, default=None)
    p.add_argument("--rapport", default=None,
                   help="publier depuis un rapport de gate sauvegardé (JSON, une ligne de eval/history.jsonl) — sans ré-évaluer")
    c = sub.add_parser("canary")
    c.add_argument("version")
    c.add_argument("--pourcentage", type=int, default=None)
    pr = sub.add_parser("promouvoir")
    pr.add_argument("version")
    r = sub.add_parser("rollback")
    r.add_argument("--motif", default="manuel")
    r.add_argument("--acteur", default=None, help="qui décide (brique 16) — obligatoire depuis la chaîne")
    s = sub.add_parser("surveiller")
    s.add_argument("--boucle", action="store_true")
    s.add_argument("--intervalle", type=float, default=5.0)
    s.add_argument("--fenetre", type=float, default=120)
    args = parser.parse_args(argv)

    try:
        if args.commande == "publier":
            rapport = None
            if args.rapport:
                rapport = Rapport(**json.loads(Path(args.rapport).read_text(encoding="utf-8")))
            print(publier(args.version, bundle=args.bundle, seuil=args.seuil, rapport=rapport))
        elif args.commande == "canary":
            print(deployer_canary(args.version, args.pourcentage))
        elif args.commande == "promouvoir":
            print(promouvoir(args.version))
        elif args.commande == "rollback":
            print(rollback(motif=args.motif, acteur=args.acteur))
        elif args.commande == "surveiller":
            while True:
                res = surveiller(fenetre_s=args.fenetre)
                print(res)
                if not args.boucle or res["rollback"]:
                    break
                time.sleep(args.intervalle)
    except ErreurDeploiement as exc:
        print(f"REFUSÉ : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
