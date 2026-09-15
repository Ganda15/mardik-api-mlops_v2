"""Le gate d'évaluation. [STUB]

Contrat attendu :

    evaluer(version, *, n_essais=None, seuil=0.75, latence_max_ms=8000,
            cout_max_eur=0.15, contrats=..., attendus=..., registry=None) -> Rapport

    Rapport (dataclass, sérialisable en JSON) :
        version, date, essais,
        note                 moyenne sur les contrats du rappel des clauses attendues
                             (clauses attendues trouvées / clauses attendues), elle-même
                             moyennée sur ``n_essais`` passes — deux passes du vrai
                             modèle ne donnent pas la même note : c'est voulu.
        par_contrat          {contrat_id: {"note", "seuil_note", "passe", "trouvees",
                              "manquantes", "latence_ms", "cout_eur"}}
        latence_p95_ms       P95 des latences par analyse    (contrainte client : < 8 s)
        cout_moyen_eur       coût moyen par analyse          (contrainte client : < 0,15 €)
        passe                note >= seuil ET aucun contrat sous son ``seuil_note``
                             ET latence_p95_ms < latence_max_ms ET cout_moyen_eur < cout_max_eur
        motifs               liste des raisons d'échec (vide si passe)

* ``version`` désigne soit un bundle en chantier (``v1``, ``v2`` → ``models/``),
  soit une version livrée (``v2.0.3`` → registre) ;
* chaque contrat de ``eval/contrats/`` est analysé avec le moteur que
  dicte la stratégie du bundle (``analyser_v1`` / ``analyser_v2``) ;
* ``n_essais`` vaut par défaut ``parametres.essais_eval`` du bundle (1 sinon) ;
* chaque exécution ajoute une ligne à ``eval/history.jsonl`` (le rapport) ;
* en ligne de commande : ``python -m eval.run_eval --version v2 --seuil 0.75``
  → affiche le rapport, code de sortie 0 si le gate passe, 1 sinon.
  ``--essais N`` force le nombre de passes, ``--contrats c01,c07`` restreint.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.llm_client import Bundle
from app.telemetry import Telemetry
from ops.registry import MOTIF_VERSION, Registry

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONTRATS = RACINE / "eval" / "contrats"
CHEMIN_ATTENDUS = RACINE / "eval" / "attendus.jsonl"
CHEMIN_HISTORIQUE = RACINE / "eval" / "history.jsonl"


@dataclass
class Rapport:
    version: str
    date: str
    essais: int
    note: float
    par_contrat: dict[str, dict[str, Any]]
    latence_p95_ms: float
    cout_moyen_eur: float
    passe: bool
    motifs: list[str] = field(default_factory=list)
    seuil: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def charger_attendus(chemin: Path = CHEMIN_ATTENDUS) -> dict[str, dict[str, Any]]:
    attendus: dict[str, dict[str, Any]] = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.strip():
            item = json.loads(ligne)
            attendus[item["contrat_id"]] = item
    return attendus


def charger_bundle(version: str, registry: Registry | None = None) -> Bundle:
    if MOTIF_VERSION.match(version):
        return (registry or Registry()).bundle(version)
    return Bundle.charger(version)


def _p95(valeurs: list[float]) -> float:
    if not valeurs:
        return 0.0
    tri = sorted(valeurs)
    return tri[min(len(tri) - 1, int(round(0.95 * len(tri) + 0.5)) - 1)]


def evaluer(
    version: str,
    *,
    n_essais: int | None = None,
    seuil: float = 0.75,
    latence_max_ms: float = 8000.0,
    cout_max_eur: float = 0.15,
    contrats: Path = DOSSIER_CONTRATS,
    attendus: Path = CHEMIN_ATTENDUS,
    registry: Registry | None = None,
    telemetry: Telemetry | None = None,
    sous_ensemble: list[str] | None = None,
    historique: Path | None = CHEMIN_HISTORIQUE,
) -> Rapport:
    raise NotImplementedError("eval.run_eval.evaluer — le gate d'évaluation")


def afficher(rapport: Rapport) -> None:
    print(f"== Gate d'évaluation — {rapport.version} ({rapport.essais} essai(s)) ==")
    for cid, c in rapport.par_contrat.items():
        etat = "OK " if c["passe"] else "KO "
        manque = f"  manquantes: {', '.join(c['manquantes'])}" if c["manquantes"] else ""
        print(f"  {etat} {cid}  note={c['note']:.2f}  (seuil {c['seuil_note']}){manque}")
    print(
        f"note globale = {rapport.note:.3f} | P95 = {rapport.latence_p95_ms:.0f} ms"
        f" | coût moyen = {rapport.cout_moyen_eur:.4f} €"
    )
    print("GATE : " + ("PASSE" if rapport.passe else "ÉCHEC — " + " ; ".join(rapport.motifs)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate d'évaluation Mardik")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--seuil", type=float, default=0.75)
    parser.add_argument("--essais", type=int, default=None)
    parser.add_argument("--latence-max-ms", type=float, default=8000)
    parser.add_argument("--cout-max-eur", type=float, default=0.15)
    parser.add_argument("--contrats", default=None, help="liste c01,c02,… (défaut : tous)")
    args = parser.parse_args(argv)
    sous_ensemble = re.split(r"[,\s]+", args.contrats.strip()) if args.contrats else None
    rapport = evaluer(
        args.version,
        n_essais=args.essais,
        seuil=args.seuil,
        latence_max_ms=args.latence_max_ms,
        cout_max_eur=args.cout_max_eur,
        sous_ensemble=sous_ensemble,
    )
    afficher(rapport)
    return 0 if rapport.passe else 1


if __name__ == "__main__":
    sys.exit(main())
