"""Rejeu des cas de production — brique 17, test 8 du brief : « la chaîne le rejoue à la fusion suivante ».

    python -m eval.rejouer_production --version v2

Lit ``eval/attendus_production.jsonl`` — les cas capturés en production et étiquetés par un juriste
(``python -m ops.enrichissement ajouter``) — et les évalue SEULS, avec les mêmes seuils que le gate
(``eval/thresholds.yml``). Jamais mêlés aux 12 contrats de référence de ``eval/attendus.jsonl`` : le test
fourni ``test_gate_evaluation_note_par_version`` fige ces 12 contrats, et un 13ᵉ dans ce fichier le casse
pour toujours, pas seulement à la fusion suivante — constaté le 23/09 sur le premier cas réel.

Sortie 1 si un cas échoue : un cas de production qui met la version en défaut bloque la livraison, comme
n'importe quel gate. Sans fichier, ou fichier vide : rien à rejouer, sortie 0 — l'étape est dans
``llmops.yml`` avant même le premier cas.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.run_eval import CHEMIN_HISTORIQUE, DOSSIER_CONTRATS, Rapport, charger_attendus, evaluer
from ops.enrichissement import chemin_attendus_production


def rejouer(
    version: str = "v2",
    *,
    attendus: Path | None = None,
    contrats: Path = DOSSIER_CONTRATS,
    historique: Path | None = CHEMIN_HISTORIQUE,
) -> Rapport | None:
    source = attendus or chemin_attendus_production()
    if not source.is_file():
        return None
    ids = sorted(charger_attendus(source))
    if not ids:
        return None
    return evaluer(version, sous_ensemble=ids, attendus=source, contrats=contrats, historique=historique)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="v2")
    parser.add_argument("--contrats", default=str(DOSSIER_CONTRATS))
    parser.add_argument("--historique", default=str(CHEMIN_HISTORIQUE))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # console Windows cp1252 (leçon de ops/ajuster_seuils)

    rapport = rejouer(args.version, contrats=Path(args.contrats), historique=Path(args.historique))
    if rapport is None:
        print("Aucun cas de production a rejouer (eval/attendus_production.jsonl absent ou vide).")
        return 0
    for cid, c in rapport.par_contrat.items():
        print(f"  {cid}: note {c['note']:.3f} (seuil {c['seuil_note']}) -> {'ok' if c['passe'] else 'ECHEC'}")
    etat = "PASSE" if rapport.passe else "BLOQUE"
    print(f"Rejeu de {len(rapport.par_contrat)} cas de production, version {args.version} : {etat} (note {rapport.note:.3f})")
    for motif in rapport.motifs:
        print(f"  - {motif}")
    return 0 if rapport.passe else 1


if __name__ == "__main__":
    raise SystemExit(main())
