"""Crée (ou remplace) ``public.env`` : le code d'accès du lien public et le plafond de coût.

    uv run python -m scripts.nouveau_code_public            # plafond 2 € sur 24 h
    uv run python -m scripts.nouveau_code_public --budget 5
    uv run python -m scripts.nouveau_code_public --admin      # admin.env : le jeton du rollback (brique 16)

Le fichier est lu par le service ``public`` de docker-compose, et ignoré par git. Le code
est affiché une seule fois : on le recopie dans le champ « Code d'accès » de la page, et
nulle part ailleurs (ni chat, ni fichier partagé). Relancer le script = nouveau code ;
redémarrer ensuite le service : ``docker compose --profile public up -d``.
"""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

CHEMIN_DEFAUT = Path(__file__).resolve().parent.parent / "public.env"
CHEMIN_ADMIN = Path(__file__).resolve().parent.parent / "admin.env"


def ecrire_fichier_code(chemin: Path = CHEMIN_DEFAUT, budget_eur: float = 2.0) -> str:
    code = secrets.token_urlsafe(12)
    chemin.write_text(
        f"MARDIK_API_KEY={code}\nMARDIK_BUDGET_JOUR_EUR={budget_eur}\n", encoding="utf-8"
    )
    return code


def ecrire_jeton_admin(chemin: Path = CHEMIN_ADMIN) -> str:
    """Le jeton d'administration de /pilotage/rollback : distinct de la clé du lien public, plus long."""
    jeton = secrets.token_urlsafe(24)
    chemin.write_text(f"MARDIK_ADMIN_TOKEN={jeton}\n", encoding="utf-8")
    return jeton


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget", type=float, default=2.0, help="plafond de coût sur 24 h, en euros")
    parser.add_argument("--admin", action="store_true", help="écrire admin.env (jeton du rollback) à la place")
    args = parser.parse_args()
    if args.admin:
        jeton = ecrire_jeton_admin()
        print(f"Jeton d'administration : {jeton}")
        print(f"Fichier : {CHEMIN_ADMIN}. À saisir dans la page /pilotage pour autoriser un retour arrière.")
        print("Ne collez ce jeton dans aucun chat ni fichier partagé.")
        return
    code = ecrire_fichier_code(budget_eur=args.budget)
    print(f"Code d'accès : {code}")
    print(f"Plafond : {args.budget} € sur 24 h. Fichier : {CHEMIN_DEFAUT}")
    print("Ne collez ce code dans aucun chat ni fichier partagé.")


if __name__ == "__main__":
    main()
