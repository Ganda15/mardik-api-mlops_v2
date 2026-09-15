"""Trafic réaliste sur la gateway + pilotage des modes de dérive — [FOURNI].

    python scripts/traffic_sim.py --mode normal        --duree 60 --rps 1
    python scripts/traffic_sim.py --mode derive-score  --duree 90 --rps 2
    python scripts/traffic_sim.py --mode derive-latence
    python scripts/traffic_sim.py --mode erreurs

* envoie des contrats tirés de ``eval/contrats/`` sur ``POST /analyse`` (la
  gateway, qui répartit entre active et canary) ;
* ``--mode`` positionne le proxy de dérive (``POST /_drift``) au démarrage,
  et le remet à ``off`` à la fin (sauf ``--laisser``) ;
* affiche une ligne par requête : version servie, statut, latence, score.

C'est l'outil de la démo finale : dérive lancée en live, rollback observé
sur le tableau de bord et dans le journal.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONTRATS = RACINE / "eval" / "contrats"
MODES = {
    "normal": "off",
    "derive-score": "score",
    "derive-latence": "latence",
    "erreurs": "erreurs",
}


def piloter_proxy(proxy_url: str, mode: str) -> None:
    try:
        r = httpx.post(f"{proxy_url.rstrip('/')}/_drift", json={"mode": mode}, timeout=5)
        print(f"proxy de dérive → {r.json()}")
    except httpx.HTTPError as exc:
        print(f"(proxy injoignable : {exc} — trafic envoyé sans pilotage de dérive)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulateur de trafic Mardik")
    parser.add_argument("--mode", choices=sorted(MODES), default="normal")
    parser.add_argument("--duree", type=float, default=60, help="secondes")
    parser.add_argument("--rps", type=float, default=1.0, help="requêtes par seconde")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--proxy", default="http://localhost:8080")
    parser.add_argument("--courts-seulement", action="store_true", help="évite les contrats longs")
    parser.add_argument("--laisser", action="store_true", help="ne pas remettre DRIFT=off à la fin")
    args = parser.parse_args(argv)

    contrats = sorted(DOSSIER_CONTRATS.glob("c*.txt"))
    if args.courts_seulement:
        contrats = [c for c in contrats if c.stat().st_size < 20_000]
    if not contrats:
        print("aucun contrat dans eval/contrats/", file=sys.stderr)
        return 1

    piloter_proxy(args.proxy, MODES[args.mode])
    fin = time.time() + args.duree
    intervalle = 1.0 / max(args.rps, 0.01)
    n = erreurs = 0
    try:
        with httpx.Client(timeout=180) as http:
            while time.time() < fin:
                contrat = random.choice(contrats)
                texte = contrat.read_text(encoding="utf-8")
                debut = time.perf_counter()
                try:
                    r = http.post(f"{args.url.rstrip('/')}/analyse", json={"texte": texte})
                    latence = (time.perf_counter() - debut) * 1000
                    version = r.headers.get("x-mardik-version", "?")
                    score = r.json().get("confiance_globale") if r.status_code == 200 else None
                    etat = "OK " if r.status_code == 200 else "ERR"
                    erreurs += r.status_code != 200
                    print(
                        f"{etat} {contrat.stem} → {version:8} {r.status_code} {latence:7.0f} ms"
                        f"  score={'-' if score is None else f'{score:.2f}'}"
                    )
                except httpx.HTTPError as exc:
                    erreurs += 1
                    print(f"ERR {contrat.stem} → injoignable : {exc}")
                n += 1
                time.sleep(max(0.0, intervalle - (time.perf_counter() - debut)))
    except KeyboardInterrupt:
        pass
    finally:
        if not args.laisser:
            piloter_proxy(args.proxy, "off")
    print(f"{n} requêtes, {erreurs} erreurs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
