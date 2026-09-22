"""Client de démonstration de la v2 — le pendant de ``client_v1.py`` pour ``POST /v2/analyse``.

    python scripts/client_v2.py [--url http://localhost:8000] [--contrat eval/contrats/c07.txt] [--json]

Lit le contrat en UTF-8, l'envoie, affiche la réponse lisiblement (ou le JSON brut avec
``--json``). Code de sortie 0 si la réponse est un 200 conforme, 1 sinon (le détail de
l'erreur est affiché tel que l'API le renvoie : 422, 503…).

Pourquoi un script Python et pas une commande PowerShell : Windows PowerShell 5.1 ne lit,
n'envoie ni ne décode l'UTF-8 par défaut — trois contournements nécessaires pour un seul
appel (mesuré le 22/09). Python fait les trois correctement sans rien demander.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONTRAT_DEFAUT = RACINE / "eval" / "contrats" / "c07.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Client de démonstration Mardik (v2)")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--contrat", default=str(CONTRAT_DEFAUT))
    parser.add_argument("--json", action="store_true", help="afficher la réponse JSON brute")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)

    import httpx

    sys.stdout.reconfigure(errors="replace")
    chemin = Path(args.contrat)
    texte = chemin.read_text(encoding="utf-8")
    corps = {"texte": texte, "contrat_id": chemin.stem}

    try:
        r = httpx.post(f"{args.url.rstrip('/')}/v2/analyse", json=corps, timeout=args.timeout)
    except httpx.HTTPError as exc:
        print(f"ECHEC : {args.url} injoignable — {exc}")
        return 1

    try:
        data = r.json()
    except ValueError:
        print(f"HTTP {r.status_code} — réponse non JSON : {r.text[:300]}")
        return 1

    if r.status_code != 200:
        print(f"HTTP {r.status_code} — {json.dumps(data, ensure_ascii=False)}")
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"contrat   : {chemin.name} ({len(texte)} caractères)")
    print(f"version   : {data['version']} / {data['modele']}")
    print(f"sections  : {data['sections']}  (appels LLM : {data['appels_llm']})")
    print(f"latence   : {data['latence_ms'] / 1000:.1f} s")
    print(f"coût      : {data['cout_eur']:.4f} €")
    print(f"confiance : {data['confiance_globale']:.3f}")
    print(f"clauses   : {len(data['clauses'])}")
    for c in data["clauses"]:
        extrait = c["extrait"].replace("\n", " ")
        if len(extrait) > 90:
            extrait = extrait[:87] + "..."
        print(f"  - {c['type']:<30} {c['confiance']:.2f}  sections {c['sections']}  « {extrait} »")
    return 0


if __name__ == "__main__":
    sys.exit(main())
