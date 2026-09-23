"""Crée (ou remplace) ``public.env`` : le code d'accès du lien public et le plafond de coût.

    uv run python -m scripts.nouveau_code_public            # plafond 2 € sur 24 h
    uv run python -m scripts.nouveau_code_public --budget 5
    uv run python -m scripts.nouveau_code_public --admin      # admin.env : le jeton du rollback (brique 16)

Le fichier est lu par le service ``public`` de docker-compose, et ignoré par git. Le code
n'est jamais affiché en entier (4 caractères) : on le lit avec « notepad public.env », on le recopie dans la page, et
nulle part ailleurs (ni message, ni fichier partagé). Relancer le script = nouveau code ;
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
    # Jamais le secret en entier à l'écran (23/09 : trois secrets copiés depuis le terminal dans un message).
    # On montre 4 caractères pour reconnaître la valeur ; on la lit en entier dans le fichier, avec le Bloc-notes.
    if args.admin:
        jeton = ecrire_jeton_admin(CHEMIN_ADMIN)
        print(f"Nouveau jeton d'administration écrit : {jeton[:4]}… (l'ancien ne marche plus)")
        print(f"Pour le lire en entier : notepad {CHEMIN_ADMIN.name}   (à saisir dans la page /pilotage)")
        print("Puis : docker compose up -d --force-recreate app")
        return
    code = ecrire_fichier_code(CHEMIN_DEFAUT, budget_eur=args.budget)
    print(f"Nouveau code d'accès écrit : {code[:4]}… (plafond {args.budget} € sur 24 h)")
    print(f"Pour le lire en entier : notepad {CHEMIN_DEFAUT.name}   (à donner avec le lien, par un autre canal)")
    print("Puis : docker compose --profile public up -d --force-recreate public")


if __name__ == "__main__":
    main()
