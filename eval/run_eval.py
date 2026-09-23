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
        precision            moyenne sur les contrats de la précision (clauses annoncées
                             qui étaient attendues / clauses annoncées) — rapportée à côté
                             du rappel, jamais bloquante (spec §5 A1) : un modèle qui
                             annoncerait les 14 types aurait un rappel parfait, c'est ici
                             qu'on le voit.
        par_contrat          {contrat_id: {"note", "precision", "seuil_note", "passe",
                              "trouvees", "manquantes", "en_trop", "latence_ms", "cout_eur"}}
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
import os
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api_v1 import analyser_v1
from app.api_v2 import analyser_v2
from app.llm_client import Bundle, LLMClient
from app.telemetry import NoopSpanExporter, Telemetry, build_telemetry
from ops.registry import MOTIF_VERSION, Registry
from ops.seuils import charger_seuils

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
    precision: float = 0.0
    # Brique 20 : la signature de la version saine (médiane du score global, part < 0,5, nombre d'analyses),
    # calculée SEULEMENT avec le vrai modèle — None en MOCK. Portée par le manifeste (ops/deploy.publier).
    signature: dict[str, Any] | None = None

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


def noter(trouvees: set[str], attendues: set[str]) -> tuple[float, float, list[str]]:
    """(rappel, précision, en_trop) d'une passe : ce qui est trouvé face à ce qui est attendu.

    Rien d'annoncé → précision 1,0 (aucune erreur) mais rappel 0 ; rien d'attendu → rappel 1,0
    et tout ce qui est annoncé est en trop.
    """
    justes = trouvees & attendues
    rappel = len(justes) / len(attendues) if attendues else 1.0
    precision = len(justes) / len(trouvees) if trouvees else 1.0
    return rappel, precision, sorted(trouvees - attendues)


def _p95(valeurs: list[float]) -> float:
    if not valeurs:
        return 0.0
    tri = sorted(valeurs)
    return tri[min(len(tri) - 1, int(round(0.95 * len(tri) + 0.5)) - 1)]


def _analyser_une_fois(
    bundle: Bundle, client: LLMClient, telemetry: Telemetry, texte: str
) -> tuple[set[str], float, float, float | None]:
    """Une passe d'analyse : renvoie (types de clauses trouvés, latence_ms, cout_eur, score global ou None).

    v2 expose latence_ms et cout_eur directement dans sa réponse. v1 ne les expose pas
    (ReponseAnalyseV1 n'a que clauses/modele/version/tronque) — on les relit dans la
    dernière Mesure que analyser_v1 vient d'écrire dans la télémétrie : app/api_v1.py
    est intouchable, relire sa propre télémétrie est la seule façon légitime de
    récupérer ce chiffre sans dupliquer sa logique ailleurs.
    """
    if bundle.strategie == "map_reduce_clauses":
        reponse = analyser_v2(texte, client, telemetry)
        return {c.type for c in reponse.clauses}, reponse.latence_ms, reponse.cout_eur, reponse.confiance_globale

    debut = time.perf_counter()
    reponse = analyser_v1(texte, client, telemetry)
    latence_ms = (time.perf_counter() - debut) * 1000
    mesures = telemetry.metriques.lire()
    cout_eur = mesures[-1].cout_eur if mesures else 0.0
    return set(reponse.clauses), latence_ms, cout_eur, None   # la v1 n'a pas de score


def evaluer(
    version: str,
    *,
    n_essais: int | None = None,
    seuil: float | None = None,
    latence_max_ms: float | None = None,
    cout_max_eur: float | None = None,
    contrats: Path = DOSSIER_CONTRATS,
    attendus: Path = CHEMIN_ATTENDUS,
    registry: Registry | None = None,
    telemetry: Telemetry | None = None,
    sous_ensemble: list[str] | None = None,
    historique: Path | None = CHEMIN_HISTORIQUE,
) -> Rapport:
    # Brique 13 (Ch2) : un seuil non fourni vient de eval/thresholds.yml — jamais d'une valeur codée ici.
    gate = charger_seuils()["gate"]
    seuil = gate["rappel_min"] if seuil is None else seuil
    latence_max_ms = gate["latence_p95_max_ms"] if latence_max_ms is None else latence_max_ms
    cout_max_eur = gate["cout_moyen_max_eur"] if cout_max_eur is None else cout_max_eur

    bundle = charger_bundle(version, registry)
    client = LLMClient(bundle)
    tel = telemetry or build_telemetry(
        span_exporter=NoopSpanExporter(), metrics_path=Path(os.environ.get("EVAL_METRICS_PATH") or RACINE / "eval" / ".metrics_eval.jsonl")
    )
    essais = n_essais or int(bundle.parametres.get("essais_eval", 1))

    tous_attendus = charger_attendus(attendus)
    ids = sous_ensemble or sorted(tous_attendus)

    par_contrat: dict[str, dict[str, Any]] = {}
    toutes_latences: list[float] = []
    tous_couts: list[float] = []
    notes: list[float] = []
    precisions: list[float] = []
    scores: list[float] = []

    for contrat_id in ids:
        item = tous_attendus[contrat_id]
        attendues = set(item["clauses_attendues"])
        texte = (contrats / f"{contrat_id}.txt").read_text(encoding="utf-8")

        notes_essais: list[float] = []
        precisions_essais: list[float] = []
        dernieres_trouvees: set[str] = set()
        dernier_en_trop: list[str] = []
        for _ in range(essais):
            trouvees, latence_ms, cout_eur, score = _analyser_une_fois(bundle, client, tel, texte)
            if score is not None:
                scores.append(float(score))
            toutes_latences.append(latence_ms)
            tous_couts.append(cout_eur)
            rappel, precision, en_trop = noter(trouvees, attendues)
            notes_essais.append(rappel)
            precisions_essais.append(precision)
            dernieres_trouvees = trouvees & attendues
            dernier_en_trop = en_trop

        note_contrat = sum(notes_essais) / len(notes_essais)
        precision_contrat = sum(precisions_essais) / len(precisions_essais)
        seuil_note = float(item.get("seuil_note", seuil))
        par_contrat[contrat_id] = {
            "note": note_contrat,
            "precision": precision_contrat,
            "seuil_note": seuil_note,
            "passe": note_contrat >= seuil_note,
            "trouvees": sorted(dernieres_trouvees),
            "manquantes": sorted(attendues - dernieres_trouvees),
            "en_trop": dernier_en_trop,
            "latence_ms": toutes_latences[-1],
            "cout_eur": tous_couts[-1],
        }
        notes.append(note_contrat)
        precisions.append(precision_contrat)

    note_globale = sum(notes) / len(notes) if notes else 0.0
    precision_globale = sum(precisions) / len(precisions) if precisions else 0.0
    latence_p95 = _p95(toutes_latences)
    cout_moyen = sum(tous_couts) / len(tous_couts) if tous_couts else 0.0
    signature = None
    if scores and client.mock != "on":
        signature = {
            "score_median": round(statistics.median(scores), 4),
            "part_score_bas": round(sum(1 for x in scores if x < 0.5) / len(scores), 4),
            "analyses": len(scores),
        }

    motifs: list[str] = []
    if note_globale < seuil:
        motifs.append(f"note {note_globale:.3f} < seuil {seuil}")
    for cid, c in par_contrat.items():
        if not c["passe"]:
            motifs.append(f"{cid} : note {c['note']:.3f} < seuil_note {c['seuil_note']}")
    if latence_p95 > latence_max_ms:
        motifs.append(f"latence p95 {latence_p95:.0f} ms > {latence_max_ms:.0f} ms")
    if cout_moyen > cout_max_eur:
        motifs.append(f"coût moyen {cout_moyen:.4f} € > {cout_max_eur:.4f} €")

    rapport = Rapport(
        version=bundle.version,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        essais=essais,
        note=note_globale,
        par_contrat=par_contrat,
        latence_p95_ms=latence_p95,
        cout_moyen_eur=cout_moyen,
        passe=not motifs,
        motifs=motifs,
        seuil=seuil,
        precision=precision_globale,
        signature=signature,
    )

    if historique is not None:
        historique.parent.mkdir(parents=True, exist_ok=True)
        with historique.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rapport.to_dict(), ensure_ascii=False) + "\n")

    return rapport


def afficher(rapport: Rapport) -> None:
    print(f"== Gate d'évaluation — {rapport.version} ({rapport.essais} essai(s)) ==")
    for cid, c in rapport.par_contrat.items():
        etat = "OK " if c["passe"] else "KO "
        manque = f"  manquantes: {', '.join(c['manquantes'])}" if c["manquantes"] else ""
        en_trop = f"  en trop: {', '.join(c['en_trop'])}" if c.get("en_trop") else ""
        print(
            f"  {etat} {cid}  rappel={c['note']:.2f}  précision={c.get('precision', 0.0):.2f}"
            f"  (seuil {c['seuil_note']}){manque}{en_trop}"
        )
    print(
        f"rappel global = {rapport.note:.3f} | précision globale = {rapport.precision:.3f}"
        f" | P95 = {rapport.latence_p95_ms:.0f} ms | coût moyen = {rapport.cout_moyen_eur:.4f} €"
    )
    print("GATE : " + ("PASSE" if rapport.passe else "ÉCHEC — " + " ; ".join(rapport.motifs)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate d'évaluation Mardik")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--seuil", type=float, default=None, help="défaut : eval/thresholds.yml")
    parser.add_argument("--essais", type=int, default=None)
    parser.add_argument("--latence-max-ms", type=float, default=None)
    parser.add_argument("--cout-max-eur", type=float, default=None)
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
