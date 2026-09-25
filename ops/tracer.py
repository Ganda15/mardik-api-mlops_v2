"""Traçabilité — l'historique complet d'une analyse à partir de son ``request_id``.

    python -m ops.tracer <request_id>          # affichage lisible
    python -m ops.tracer <request_id> --json   # pour un outil

Réunit ce que la chaîne a écrit, fichier par fichier, sans rien recalculer :
  1. la ligne de métriques      (ops/metrics.jsonl)  — version, latence, coût, score, erreur ;
  2. la trace                   (ops/traces.jsonl)   — chaque étape chronométrée, chaque appel au modèle ;
  3. les journaux               (ops/logs.jsonl)     — analyse terminée ou en échec ;
  4. le manifeste de la version (ops/registry/<v>/)  — commit, modèle, empreinte, note du gate réel ;
  5. les seuils de la version   (models/<bundle>/config.yaml) — libellés de certitude, calibration ;
  6. les décisions de pilotage  (ops/registry/journal.jsonl) — sur cette version, dans les 2 jours qui suivent.

Un fichier absent ou une ligne introuvable est rendu vide, jamais inventé.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml

RACINE = Path(__file__).resolve().parent.parent
FENETRE_DECISIONS_S = 2 * 24 * 3600  # même fenêtre que le watcher


def _lignes(chemin: Path) -> list[dict[str, Any]]:
    if not chemin.exists():
        return []
    sortie = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.strip():
            try:
                sortie.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue
    return sortie


def _lire_au_commit(commit: str, chemin: str) -> str | None:
    """Le fichier tel qu'il était au commit de la version (``git show``) ; None si git ou le commit manquent."""
    try:
        r = subprocess.run(["git", "show", f"{commit}:{chemin}"], cwd=RACINE, capture_output=True,
                           text=True, encoding="utf-8", timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _seuils(
    version: str | None,
    commit: str | None,
    lire: Callable[[str, str], str | None] = _lire_au_commit,
) -> dict[str, Any]:
    """Seuils et calibration du bundle qui a répondu (v1.x → models/v1, sinon models/v2), lus dans la config
    DU COMMIT de la version — celle du jour peut avoir changé depuis. À défaut, la config du jour, en le disant."""
    if not version:
        return {}
    chemin = f"models/{'v1' if version.startswith('v1') else 'v2'}/config.yaml"
    texte = lire(commit, chemin) if commit else None
    source = f"commit {commit}"
    if texte is None:
        actuelle = RACINE / chemin
        if not actuelle.exists():
            return {}
        texte = actuelle.read_text(encoding="utf-8")
        source = "config actuelle (commit de la version illisible : pas forcément celle qui a répondu)"
    parametres = (yaml.safe_load(texte) or {}).get("parametres") or {}
    seuils = {k: parametres[k] for k in ("seuils_libelle", "calibration") if k in parametres}
    return {**seuils, "source": source}


def historique(
    request_id: str,
    *,
    metrics: Path | str | None = None,
    traces: Path | str | None = None,
    logs: Path | str | None = None,
    registre: Path | str | None = None,
) -> dict[str, Any]:
    metrics = Path(metrics or os.environ.get("METRICS_PATH", RACINE / "ops" / "metrics.jsonl"))
    traces = Path(traces or os.environ.get("TRACES_PATH", RACINE / "ops" / "traces.jsonl"))
    logs = Path(logs or os.environ.get("LOGS_PATH", RACINE / "ops" / "logs.jsonl"))
    registre = Path(registre or os.environ.get("REGISTRY_PATH", RACINE / "ops" / "registry"))

    ligne = next((m for m in _lignes(metrics) if m.get("request_id") == request_id), None)
    spans = _lignes(traces)
    ids_trace = {s["trace_id"] for s in spans if s.get("attributs", {}).get("mardik.request_id") == request_id}
    trace = sorted((s for s in spans if s.get("trace_id") in ids_trace), key=lambda s: s.get("debut", 0))
    journaux = [e for e in _lignes(logs) if e.get("request_id") == request_id]

    version = ligne.get("version") if ligne else None
    manifeste_chemin = registre / version / "manifest.json" if version else None
    manifeste = (json.loads(manifeste_chemin.read_text(encoding="utf-8"))
                 if manifeste_chemin and manifeste_chemin.exists() else None)
    decisions = []
    if ligne:
        decisions = [d for d in _lignes(registre / "journal.jsonl")
                     if d.get("version") == version and 0 <= d.get("ts", 0) - ligne["ts"] <= FENETRE_DECISIONS_S]

    return {
        "request_id": request_id,
        "metriques": ligne,
        "trace": trace,
        "journaux": journaux,
        "manifeste": manifeste,
        "seuils": _seuils(version, (manifeste or {}).get("commit")),
        "decisions": decisions,
    }


def _en_arbre(spans: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """Les spans dans l'ordre de l'arbre (parent puis ses enfants, par heure de début), avec leur profondeur."""
    ids = {s.get("span_id") for s in spans}
    enfants: dict[Any, list[dict[str, Any]]] = {}
    for s in spans:
        parent = s.get("parent_id") if s.get("parent_id") in ids else None
        enfants.setdefault(parent, []).append(s)
    ordre: list[tuple[dict[str, Any], int]] = []

    def parcourir(parent: Any, profondeur: int) -> None:
        for s in sorted(enfants.get(parent, []), key=lambda x: x.get("debut", 0)):
            ordre.append((s, profondeur))
            parcourir(s.get("span_id"), profondeur + 1)

    parcourir(None, 0)
    return ordre


def _afficher(h: dict[str, Any]) -> str:
    m = h["metriques"]
    if m is None and not h["trace"] and not h["journaux"]:
        return f"request_id {h['request_id']} : introuvable dans les métriques, les traces et les journaux."
    out = [f"=== Historique de la requête {h['request_id']} ==="]
    if m:
        out.append(f"[1] Métriques : version {m['version']} · route {m['route']} · latence {m['latence_ms']:.0f} ms · "
                   f"coût {m.get('cout_eur', 0):.4f} € · score {m.get('score')} · erreur {m.get('erreur')} · "
                   f"appels LLM {m.get('appels_llm')}")
    else:
        out.append("[1] Métriques : aucune ligne (fichier écrit avant le 24/09 ?)")
    appele = next((s["attributs"]["llm.modele"] for s in h["trace"] if "llm.modele" in s.get("attributs", {})), None)
    out.append(f"[2] Trace : {len(h['trace'])} étape(s) · modèle appelé {appele or 'non tracé (avant le 24/09)'}")
    for s, profondeur in _en_arbre(h["trace"]):
        a = s.get("attributs", {})
        detail = f" section {a['mardik.section']} · LLM {a.get('llm.latence_ms', 0):.0f} ms · {a.get('llm.tokens')} jetons" \
            if "mardik.section" in a else ""
        nom = "  " * profondeur + s["nom"]
        out.append(f"      {nom:<30} {s['duree_ms']:>9.1f} ms  {s['statut']}{detail}")
    out.append("[3] Journaux : " + (", ".join(e.get("event", "?") for e in h["journaux"]) or "aucun"))
    man = h["manifeste"]
    out.append("[4] Manifeste : " + (f"modèle visé {man.get('modele')} · commit {man.get('commit')} · empreinte "
                                     f"{man.get('empreinte')} · note du gate {man.get('note_eval')}" if man else "absent"))
    libelle = h["seuils"].get("seuils_libelle")
    libelle_txt = (json.dumps(libelle, ensure_ascii=False) if libelle
                   else "absents de la config → bornes par défaut du code (SEUILS_LIBELLE_DEFAUT)")
    out.append(f"[5] Seuils : {libelle_txt} · calibration "
               f"{(h['seuils'].get('calibration') or {}).get('methode', 'aucune')} · source {h['seuils'].get('source', '-')}")
    out.append(f"[6] Décisions de pilotage sur cette version (2 jours suivants) : {len(h['decisions'])}")
    for d in h["decisions"]:
        out.append(f"      {d.get('date')} {d.get('evenement')} · signal {d.get('signal', '-')} · acteur {d.get('acteur')}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Historique complet d'une analyse Mardik")
    parser.add_argument("request_id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    h = historique(args.request_id)
    print(json.dumps(h, ensure_ascii=False, indent=2) if args.json else _afficher(h))
    return 0 if h["metriques"] or h["trace"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
