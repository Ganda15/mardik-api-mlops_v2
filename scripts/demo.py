"""Démo Chantier 2 en une commande — sans make (absent sur ce poste : PowerShell 5.1, Git Bash).

    uv run python -m scripts.demo up       # app + proxy + dashboard + watcher : seuils de démo, watcher 10 s
    uv run python -m scripts.demo public   # la même chose + instance verrouillée + tunnel ; affiche le lien
    uv run python -m scripts.demo down     # arrête tout, lien compris

Toujours les DEUX fichiers compose. Trouvé le 23/09 : `docker compose --profile public up -d` seul
recrée app, watcher et public SANS l'overlay — seuils réels (30 requêtes, 1 jour), watcher à 60 s.
Équivalent Makefile (runner, Linux) : make demo / demo-public / demo-down.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIERS = ["-f", "docker-compose.yml", "-f", "docker-compose.demo.yml"]
_LIEN = re.compile(r"https://[a-z-]+\.trycloudflare\.com")


def commande(action: str) -> list[str]:
    base = ["docker", "compose", *FICHIERS]
    if action == "up":
        return [*base, "up", "-d", "--build"]
    if action == "public":
        return [*base, "--profile", "public", "up", "-d", "--build"]
    if action == "down":
        return [*base, "--profile", "public", "down"]
    raise ValueError(f"action inconnue : {action} (up | public | down)")


def lien_tunnel() -> str | None:
    """Le lien est dans les journaux du conteneur tunnel, quelques secondes après son démarrage.
    Seulement les journaux POSTÉRIEURS à ce démarrage : un conteneur redémarré garde les anciens, et
    l'adresse de la veille (morte) serait renvoyée — arrivé le 23/09."""
    depuis = subprocess.run(["docker", "inspect", "--format", "{{.State.StartedAt}}", "mardik-api-mlops_v2-tunnel-1"],
                            cwd=RACINE, capture_output=True, text=True, check=False).stdout.strip()
    for _ in range(10):
        cmd = ["docker", "compose", "--profile", "public", "logs"]
        if depuis:
            cmd += ["--since", depuis]
        sortie = subprocess.run([*cmd, "tunnel"], cwd=RACINE, capture_output=True, text=True, check=False).stdout
        liens = _LIEN.findall(sortie)
        if liens:
            return liens[-1]
        time.sleep(2)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["up", "public", "down"])
    args = parser.parse_args(argv)
    code = subprocess.run(commande(args.action), cwd=RACINE, check=False).returncode
    if code != 0:
        return code
    if args.action == "up":
        print("pilotage : http://localhost:8000/pilotage — seuils : eval/thresholds.demo.yml — watcher toutes les 10 s")
    elif args.action == "public":
        lien = lien_tunnel()
        print(f"lien public : {lien}" if lien else "lien public : pas encore dans les journaux — docker compose logs tunnel")
        print("code d'accès : notepad public.env — jamais dans un message")
    return 0


if __name__ == "__main__":
    sys.exit(main())
