"""Calibration du score de confiance : collecte étiquetée, ajustement de Platt, évaluation honnête.

    python -m eval.calibration collecter --essais 2          # VRAI modèle (coût réel, ~0,40 € par passe)
    python -m eval.calibration ablation                       # VRAI modèle : variantes sans un article (~1,3 €)
    python -m eval.calibration ajuster                        # ajuste Platt et affiche le bloc YAML à mettre dans le bundle

Données : pour chaque contrat étiqueté (eval/attendus.jsonl + eval/attendus_production.jsonl), chaque clause RENVOYÉE
par la v2 devient un point  (score brut, juste ?)  — juste = son type figure dans les clauses attendues. Les points
sont écrits dans eval/calibration_donnees.jsonl (versionné : la calibration est reproductible).

Évaluation : « leave-one-contract-out » — pour chaque contrat, la courbe est apprise SANS lui puis appliquée à lui.
On rapporte l'ECE (erreur de calibration attendue) et le score de Brier avant/après, et le nombre de points :
avec peu de clauses fausses, l'intervalle d'incertitude reste large — c'est dit, pas caché.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from app.pipeline.calibration import EPS, calibrer

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "eval" / "calibration_donnees.jsonl"


def _logit(s: float) -> float:
    s = min(max(s, EPS), 1 - EPS)
    return math.log(s / (1 - s))


def ajuster_platt(scores: list[float], justes: list[int], l2: float = 0.01, iterations: int = 100) -> dict:
    """Régression logistique à une variable (logit du score) par Newton, légère pénalité L2 pour ne pas diverger
    quand toutes les réponses sont justes. Part de a=1, b=0 (l'identité)."""
    a, b = 1.0, 0.0
    xs = [_logit(s) for s in scores]
    for _ in range(iterations):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, justes):
            p = 1.0 / (1.0 + math.exp(-max(min(a * x + b, 50.0), -50.0)))
            ga += (p - y) * x
            gb += (p - y)
            w = p * (1 - p)
            haa += w * x * x
            hab += w * x
            hbb += w
        ga += l2 * (a - 1.0)
        gb += l2 * b
        haa += l2
        hbb += l2
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) < 1e-8 and abs(db) < 1e-8:
            break
    return {"methode": "platt", "a": round(a, 6), "b": round(b, 6)}


def ece(probas: list[float], justes: list[int], bins: int = 10) -> float:
    """Erreur de calibration attendue : écart moyen, pondéré par l'effectif, entre confiance annoncée et justesse observée."""
    n = len(probas)
    if n == 0:
        return 0.0
    total = 0.0
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        idx = [i for i, p in enumerate(probas) if (lo <= p < hi) or (k == bins - 1 and p == 1.0)]
        if idx:
            conf = sum(probas[i] for i in idx) / len(idx)
            acc = sum(justes[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(conf - acc)
    return round(total, 6)


def brier(probas: list[float], justes: list[int]) -> float:
    return round(sum((p - y) ** 2 for p, y in zip(probas, justes)) / len(probas), 6) if probas else 0.0


def evaluer_loco(points: list[dict]) -> dict:
    """Pour chaque contrat : apprendre sur les autres, prédire sur lui. Rien n'est évalué sur ses propres données."""
    contrats = sorted({p["contrat"] for p in points})
    avant, apres, ys = [], [], []
    for c in contrats:
        train = [p for p in points if p["contrat"] != c]
        test = [p for p in points if p["contrat"] == c]
        par = ajuster_platt([p["score"] for p in train], [p["correct"] for p in train]) if train else {"methode": "platt", "a": 1.0, "b": 0.0}
        for p in test:
            avant.append(p["score"])
            apres.append(calibrer(p["score"], par))
            ys.append(p["correct"])
    return {"n": len(ys), "contrats": len(contrats), "faux": ys.count(0),
            "justesse_observee": round(sum(ys) / len(ys), 4) if ys else None,
            "ece_avant": ece(avant, ys), "ece_apres": ece(apres, ys),
            "brier_avant": brier(avant, ys), "brier_apres": brier(apres, ys)}


ABLATION = RACINE / "eval" / "calibration_ablation.jsonl"

# Ablation : titres d'article DISTINCTIFS -> type de clause. Durée, prix et droit applicable sont exclus : ils sont
# cités dans d'autres articles, l'étiquette « absente » ne serait pas fiable. Ordre = priorité (types les plus rares
# d'abord, pour couvrir le plus de variété sous le plafond par contrat).
TITRE_VERS_TYPE = {
    "Exclusivité": "exclusivité", "Non-concurrence": "non-concurrence", "Reconduction": "reconduction tacite",
    "Données personnelles": "données personnelles", "Force majeure": "force majeure",
    "Propriété intellectuelle": "propriété intellectuelle", "Garantie": "garantie", "Pénalités": "pénalité de retard",
    "Responsabilité": "limitation de responsabilité", "Confidentialité": "confidentialité", "Résiliation": "résiliation",
}


def retirer_article(texte: str, titre: str) -> str | None:
    """Retire l'article « Article N — <titre> » (titre et corps, jusqu'à l'article suivant). None s'il est absent."""
    lignes = texte.splitlines(keepends=True)
    debut = next((i for i, lg in enumerate(lignes)
                  if lg.startswith("Article ") and lg.rstrip().endswith("— " + titre)), None)
    if debut is None:
        return None
    fin = next((j for j in range(debut + 1, len(lignes)) if lignes[j].startswith("Article ")), len(lignes))
    return "".join(lignes[:debut] + lignes[fin:])


def variantes_ablation(contrat: str, texte: str, attendues: set[str], max_par_contrat: int = 3) -> list[dict]:
    """Une variante par article distinctif retiré, dont le type était attendu : étiquette = attendues - {type}."""
    out = []
    for titre, type_ in TITRE_VERS_TYPE.items():
        if len(out) >= max_par_contrat:
            break
        if type_ not in attendues:
            continue
        variante = retirer_article(texte, titre)
        if variante is not None:
            out.append({"contrat": contrat, "retire": type_, "texte": variante, "attendues": attendues - {type_}})
    return out


def _attendus() -> dict[str, tuple[set[str], Path]]:
    out = {}
    for fichier in (RACINE / "eval" / "attendus.jsonl", RACINE / "eval" / "attendus_production.jsonl"):
        if fichier.exists():
            for ligne in fichier.read_text(encoding="utf-8").splitlines():
                if ligne.strip():
                    d = json.loads(ligne)
                    out[d["contrat_id"]] = (set(d["clauses_attendues"]), RACINE / "eval" / "contrats" / f"{d['contrat_id']}.txt")
    return out


def collecter(essais: int, sortie: Path = DONNEES) -> int:
    """Passe le jeu étiqueté dans la v2 sur le VRAI modèle (MOCK doit être off) et écrit un point par clause renvoyée."""
    if os.environ.get("MOCK", "off").lower() == "on":
        raise SystemExit("MOCK=on : la calibration doit être apprise sur le vrai modèle, jamais sur des réponses rejouées")
    from app.api_v2 import analyser_v2
    from app.llm_client import Bundle, LLMClient
    from app.telemetry import NoopSpanExporter, build_telemetry
    # Mesures de la collecte hors de ops/metrics.jsonl : ce n'est pas du trafic de production.
    tele = build_telemetry(span_exporter=NoopSpanExporter(), level="WARNING",
                           metrics_path=os.environ.get("EVAL_METRICS_PATH", str(RACINE / "eval" / ".metrics_eval.jsonl")))
    client = LLMClient(Bundle.charger("v2"))
    lignes = []
    for essai in range(1, essais + 1):
        for cid, (attendues, chemin) in _attendus().items():
            rep = analyser_v2(chemin.read_text(encoding="utf-8"), client, tele)
            for c in rep.clauses:
                lignes.append({"contrat": cid, "essai": essai, "type": c.type, "score": round(c.confiance, 4),
                               "correct": int(c.type in attendues), "modele": rep.modele})
            print(f"essai {essai} {cid}: {len(rep.clauses)} clauses, {rep.cout_eur:.4f} €")
    sortie.write_text("".join(json.dumps(pt, ensure_ascii=False) + "\n" for pt in lignes), encoding="utf-8")
    return len(lignes)


def collecter_ablation(max_par_contrat: int = 3, sortie: Path = ABLATION) -> int:
    """Passe chaque variante (un article distinctif retiré) dans la v2 sur le VRAI modèle ; un point par clause
    renvoyée, étiqueté contre attendues - {type retiré}. `contrat` = contrat SOURCE : l'évaluation leave-one-contract-out
    garde ainsi une variante avec son original, jamais d'un côté et de l'autre."""
    if os.environ.get("MOCK", "off").lower() == "on":
        raise SystemExit("MOCK=on : la calibration doit être apprise sur le vrai modèle, jamais sur des réponses rejouées")
    from app.api_v2 import analyser_v2
    from app.llm_client import Bundle, LLMClient
    from app.telemetry import NoopSpanExporter, build_telemetry
    tele = build_telemetry(span_exporter=NoopSpanExporter(), level="WARNING",
                           metrics_path=os.environ.get("EVAL_METRICS_PATH", str(RACINE / "eval" / ".metrics_eval.jsonl")))
    client = LLMClient(Bundle.charger("v2"))
    lignes, cout = [], 0.0
    for cid, (attendues, chemin) in _attendus().items():
        for v in variantes_ablation(cid, chemin.read_text(encoding="utf-8"), attendues, max_par_contrat):
            rep = analyser_v2(v["texte"], client, tele)
            cout += rep.cout_eur
            for c in rep.clauses:
                lignes.append({"contrat": cid, "variante": f"sans {v['retire']}", "type": c.type,
                               "score": round(c.confiance, 4), "correct": int(c.type in v["attendues"]),
                               "modele": rep.modele})
            signale = any(c.type == v["retire"] for c in rep.clauses)
            print(f"{cid} sans {v['retire']}: {len(rep.clauses)} clauses, retiré encore signalé: {signale}, {rep.cout_eur:.4f} €")
    sortie.write_text("".join(json.dumps(pt, ensure_ascii=False) + "\n" for pt in lignes), encoding="utf-8")
    print(f"coût total : {cout:.3f} €")
    return len(lignes)


def charger_points() -> list[dict]:
    points = []
    for fichier in (DONNEES, ABLATION):
        if fichier.exists():
            points += [json.loads(ligne) for ligne in fichier.read_text(encoding="utf-8").splitlines() if ligne.strip()]
    return points


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.calibration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collecter")
    c.add_argument("--essais", type=int, default=1)
    a = sub.add_parser("ablation")
    a.add_argument("--max-par-contrat", type=int, default=3)
    sub.add_parser("ajuster")
    args = ap.parse_args(argv)
    if args.cmd == "collecter":
        print("points écrits :", collecter(args.essais))
        return 0
    if args.cmd == "ablation":
        print("points écrits :", collecter_ablation(args.max_par_contrat))
        return 0
    points = charger_points()
    par = ajuster_platt([p["score"] for p in points], [p["correct"] for p in points])
    justes = sum(p["correct"] for p in points)
    par["plafond"] = round(1 - 3 / justes, 3) if justes else 1.0   # règle de trois
    rapport = evaluer_loco(points)
    print(json.dumps({"parametres": par, "evaluation_loco": rapport}, ensure_ascii=False, indent=1))
    print("\n# bloc à placer sous parametres: dans models/v2/config.yaml")
    print(f"  calibration:\n    methode: platt\n    a: {par['a']}\n    b: {par['b']}\n"
          f"    points: {rapport['n']}\n    faux: {rapport['faux']}\n    plafond: {par['plafond']}\n"
          f"    ece_loco_avant: {rapport['ece_avant']}\n"
          f"    ece_loco_apres: {rapport['ece_apres']}\n    source: eval/calibration_donnees.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
