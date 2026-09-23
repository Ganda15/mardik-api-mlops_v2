"""Test des données — C13 (pilier 5 du référentiel MLOps). Valide eval/attendus.jsonl AVANT le gate.

    python -m eval.valider_attendus [eval/attendus.jsonl] [eval/contrats]

Manque connu du 22/09, comblé le 23/09. Le gate d'évaluation (brique 7) et l'enrichissement du jeu
d'éval (brique 17) écrivent tous les deux dans ce fichier — la brique 17 y verse des cas réels
étiquetés par un juriste, pas relus par un développeur. Une ligne mal formée doit être trouvée ICI,
avec son numéro de ligne exact, jamais laissée au gate qui planterait plus loin sans dire pourquoi.

Chaque ligne doit avoir : ``contrat_id`` (unique dans le fichier), ``clauses_attendues`` (liste de
types connus, vocabulaire fermé de ``app.llm_client.TYPES_CLAUSES``), et si présent, ``seuil_note``
dans [0, 1]. Le fichier `<contrat_id>.txt` doit exister dans le dossier des contrats.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.llm_client import TYPES_CLAUSES

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_ATTENDUS_DEFAUT = RACINE / "eval" / "attendus.jsonl"
DOSSIER_CONTRATS_DEFAUT = RACINE / "eval" / "contrats"


class ErreurDonnees(ValueError):
    """Le jeu d'évaluation est mal formé : ne jamais le laisser atteindre le gate tel quel."""


def _valider_ligne(numero: int, brut: str, dossier_contrats: Path, vus: set[str]) -> dict[str, Any]:
    try:
        item = json.loads(brut)
    except json.JSONDecodeError as exc:
        raise ErreurDonnees(f"ligne {numero} : JSON invalide ({exc})") from exc
    if not isinstance(item, dict):
        raise ErreurDonnees(f"ligne {numero} : doit être un objet JSON, reçu {type(item).__name__}")

    for champ in ("contrat_id", "clauses_attendues"):
        if champ not in item:
            raise ErreurDonnees(f"ligne {numero} : champ manquant : {champ}")

    cid = item["contrat_id"]
    if not isinstance(cid, str) or not cid:
        raise ErreurDonnees(f"ligne {numero} : contrat_id doit être une chaîne non vide")
    if cid in vus:
        raise ErreurDonnees(f"ligne {numero} : doublon de contrat_id : {cid}")
    vus.add(cid)

    clauses = item["clauses_attendues"]
    if not isinstance(clauses, list):
        raise ErreurDonnees(f"ligne {numero} ({cid}) : clauses_attendues doit être une liste")
    inconnues = [c for c in clauses if c not in TYPES_CLAUSES]
    if inconnues:
        raise ErreurDonnees(
            f"ligne {numero} ({cid}) : type(s) de clause hors vocabulaire : {', '.join(inconnues)}"
        )

    seuil = item.get("seuil_note")
    if seuil is not None and not (isinstance(seuil, (int, float)) and 0.0 <= seuil <= 1.0):
        raise ErreurDonnees(f"ligne {numero} ({cid}) : seuil_note hors bornes [0, 1] : {seuil!r}")

    if not (dossier_contrats / f"{cid}.txt").is_file():
        raise ErreurDonnees(f"ligne {numero} : contrat_id {cid} sans fichier eval/contrats/{cid}.txt")

    return item


def valider_fichier(
    chemin: Path = CHEMIN_ATTENDUS_DEFAUT, dossier_contrats: Path = DOSSIER_CONTRATS_DEFAUT
) -> dict[str, Any]:
    if not chemin.is_file():
        raise ErreurDonnees(f"fichier introuvable : {chemin}")
    vus: set[str] = set()
    n = 0
    for numero, brut in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        if not brut.strip():
            continue
        _valider_ligne(numero, brut, dossier_contrats, vus)
        n += 1
    return {"fichier": str(chemin), "lignes": n, "contrats": sorted(vus), "erreurs": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("attendus", nargs="?", default=str(CHEMIN_ATTENDUS_DEFAUT))
    parser.add_argument("contrats", nargs="?", default=str(DOSSIER_CONTRATS_DEFAUT))
    args = parser.parse_args(argv)
    try:
        rapport = valider_fichier(Path(args.attendus), Path(args.contrats))
    except ErreurDonnees as exc:
        print(f"REFUSÉ — jeu d'évaluation invalide : {exc}", file=sys.stderr)
        return 1
    print(f"OK — {rapport['lignes']} contrats valides dans {rapport['fichier']} : {', '.join(rapport['contrats'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
