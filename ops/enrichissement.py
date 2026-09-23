"""Enrichissement du jeu d'évaluation par les cas réels à faible confiance. Brique 17 (Chantier 2).

    capturer(texte, request_id=, version=, score=, clauses=)  → bool   (appelé par les routes /v2 et gateway)
    ajouter_cas(request_id, clauses)                           → contrat_id
    python -m ops.enrichissement lister
    python -m ops.enrichissement ajouter req_xxx --clauses "durée,résiliation"

Conception Ch2 §4.3 :
1. **Capture** — une analyse dont le score global est < ``capture.score_global_max`` (eval/thresholds.yml)
   est copiée dans ``ops/candidats.jsonl`` (ignoré par git : ce sont des données de production).
2. **Masquage avant stockage** — courriels, montants, parties (« Mardik SAS » → PARTIE_A). **Partiel par
   construction** : une regex ne voit pas un nom sans forme juridique, une adresse, un numéro de SIREN.
   L'anonymisation reste une question ouverte avec le client ; le dossier le dit au lieu de la supposer réglée.
3. **Étiquetage** — un juriste dit quelles clauses étaient attendues (``lister`` puis ``ajouter``).
4. **Ajout** — texte masqué dans ``eval/contrats/prod-<request_id>.txt``, ligne dans ``eval/attendus.jsonl``
   avec son origine ; c'est un commit, porté par une pull request.
5. **Rejeu** — la PR modifie ``eval/attendus.jsonl`` : le filtre de chemin de llmops.yml relance le gate.
La capture est tracée dans ``candidats.jsonl`` (heure, requête, score, seuil) ; le journal de pilotage trace
l'``enrichissement``, qui est une décision — jamais un texte de contrat.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.llm_client import TYPES_CLAUSES
from ops.registry import Registry
from ops.seuils import charger_seuils

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_CANDIDATS_DEFAUT = RACINE / "ops" / "candidats.jsonl"
CHEMIN_ATTENDUS = RACINE / "eval" / "attendus.jsonl"
DOSSIER_CONTRATS = RACINE / "eval" / "contrats"

_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MONTANT = re.compile(r"\d{1,3}(?:[   .]\d{3})*(?:,\d+)?\s?(?:€|euros?\b|EUR\b)", re.IGNORECASE)
_PARTIE = re.compile(r"\b((?:[A-ZÀ-Ý][\w'’-]*\s+){1,4})(SASU|SAS|SARL|SA|EURL|SCI|SNC)\b")


class ErreurEnrichissement(ValueError):
    """Le cas ne peut pas entrer dans le jeu d'évaluation."""


def chemin_candidats() -> Path:
    return Path(os.environ.get("CANDIDATS_PATH") or CHEMIN_CANDIDATS_DEFAUT)


def masquer(texte: str) -> str:
    """Courriels → COURRIEL, montants → MONTANT, sociétés → PARTIE_A, PARTIE_B… (le même nom garde la
    même étiquette, y compris cité seul plus loin). Partiel par construction — voir la docstring du module."""
    texte = _COURRIEL.sub("COURRIEL", texte)
    texte = _MONTANT.sub("MONTANT", texte)
    etiquettes: dict[str, str] = {}

    def _remplacer(m: re.Match[str]) -> str:
        nom = m.group(1).strip()
        if nom not in etiquettes:
            etiquettes[nom] = f"PARTIE_{chr(ord('A') + len(etiquettes))}"
        return etiquettes[nom]

    texte = _PARTIE.sub(_remplacer, texte)
    for nom, etiquette in etiquettes.items():
        texte = re.sub(rf"\b{re.escape(nom)}\b", etiquette, texte)
    return texte


def capturer(
    texte: str,
    *,
    request_id: str,
    version: str,
    score: float | None,
    clauses: list[str],
    chemin: Path | None = None,
) -> bool:
    seuil = float(charger_seuils()["capture"]["score_global_max"])
    if score is None or score >= seuil:
        return False
    cible = chemin or chemin_candidats()
    cible.parent.mkdir(parents=True, exist_ok=True)
    cas = {
        "ts": time.time(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "request_id": request_id,
        "version": version,
        "score": score,
        "seuil": seuil,
        "clauses_trouvees": clauses,
        "texte_masque": masquer(texte),
    }
    with cible.open("a", encoding="utf-8") as f:
        f.write(json.dumps(cas, ensure_ascii=False) + "\n")
    # Pas de ligne au journal de pilotage : il garde les DÉCISIONS ; candidats.jsonl est la trace de la capture.
    # (23/09 : journaliser chaque capture cassait le test fourni test_promotion_canary_puis_totale.)
    return True


def _lire_jsonl(chemin: Path) -> list[dict[str, Any]]:
    if not chemin.exists():
        return []
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines() if x.strip()]


def ajouter_cas(
    request_id: str,
    clauses: list[str],
    *,
    candidats: Path | None = None,
    attendus: Path = CHEMIN_ATTENDUS,
    contrats: Path = DOSSIER_CONTRATS,
    registry: Registry | None = None,
    seuil_note: float = 0.75,
) -> str:
    inconnus = [c for c in clauses if c not in TYPES_CLAUSES]
    if inconnus:
        raise ErreurEnrichissement(f"type de clause inconnu : {', '.join(inconnus)} (vocabulaire : {', '.join(TYPES_CLAUSES)})")
    cas = next((c for c in _lire_jsonl(candidats or chemin_candidats()) if c["request_id"] == request_id), None)
    if cas is None:
        raise ErreurEnrichissement(f"candidat introuvable : {request_id}")
    contrat_id = f"prod-{request_id}"
    existants = _lire_jsonl(attendus)
    if any(e["contrat_id"] == contrat_id for e in existants):
        raise ErreurEnrichissement(f"{contrat_id} est déjà dans le jeu d'évaluation")

    contrats.mkdir(parents=True, exist_ok=True)
    (contrats / f"{contrat_id}.txt").write_text(cas["texte_masque"], encoding="utf-8")
    ligne = {
        "contrat_id": contrat_id,
        "clauses_attendues": clauses,
        "seuil_note": seuil_note,
        "origine": {"request_id": request_id, "version": cas["version"], "score": cas["score"]},
    }
    with attendus.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    (registry or Registry()).journaliser(
        "enrichissement", version=cas["version"], request_id=request_id, contrat_id=contrat_id,
        clauses_attendues=clauses, nb_cas=len(existants) + 1,
        action="ajouté à eval/attendus.jsonl — à committer par une pull request (le gate le rejoue)")
    return contrat_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrichissement du jeu d'évaluation (Ch2, brique 17)")
    sub = parser.add_subparsers(dest="commande", required=True)
    sub.add_parser("lister", help="les candidats capturés pas encore ajoutés")
    a = sub.add_parser("ajouter", help="ajouter un candidat étiqueté au jeu d'évaluation")
    a.add_argument("request_id")
    a.add_argument("--clauses", required=True, help='clauses attendues, séparées par des virgules : "durée,résiliation"')
    args = parser.parse_args(argv)

    if args.commande == "lister":
        deja = {e["contrat_id"] for e in _lire_jsonl(CHEMIN_ATTENDUS)}
        restants = [c for c in _lire_jsonl(chemin_candidats()) if f"prod-{c['request_id']}" not in deja]
        if not restants:
            print("Aucun candidat en attente d'étiquetage.")
        for c in restants:
            print(f"{c['request_id']}  score {c['score']:.2f}  {c['version']}  trouvées : {', '.join(c['clauses_trouvees']) or '—'}")
            print(f"    {c['texte_masque'][:160]}…")
        return 0
    try:
        cid = ajouter_cas(args.request_id, [c.strip() for c in args.clauses.split(",") if c.strip()])
    except ErreurEnrichissement as exc:
        print(f"REFUSÉ : {exc}", file=sys.stderr)
        return 1
    print(f"Ajouté : {cid}. À committer (eval/attendus.jsonl + eval/contrats/{cid}.txt) par une pull request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
