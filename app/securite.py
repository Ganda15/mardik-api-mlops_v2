"""Protection d'une instance exposée publiquement. Brique F3.

Décision d'Era du 23/09 : le lien public du frontend (livrable N12) passe par un tunnel
depuis son PC (option C). Une page publique qui appelle Azure, c'est un budget que n'importe
qui peut dépenser. Deux gardes, actives SEULEMENT si leur variable d'environnement est posée
sur l'instance exposée — jamais dans ``.env`` :

* ``MARDIK_API_KEY`` — chaque POST exige l'en-tête ``X-API-Key`` (conception Ch1 §2.3). Les
  trois routes POST (``/v1/analyse``, ``/v2/analyse``, ``/analyse``) appellent toutes le modèle ;
  les GET (la page, ``/health``, la doc, ``/gateway/etat``) restent ouverts, pour que la page se
  charge et qu'on puisse y saisir la clé.
* ``MARDIK_BUDGET_JOUR_EUR`` — au-delà de ce coût sur 24 h glissantes, lu dans les ``Mesure``
  du journal de métriques, tout POST est refusé en ``429``.

Ordre : la clé d'abord (``401``), le budget ensuite (``429``) — sans clé, on n'apprend rien sur
le budget. Les deux refus sont décidés avant tout appel au modèle : ils ne coûtent rien.

Le contrat de ``/v1`` ne change pas : le client v1 vise une instance sans ces variables.
"""
from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.telemetry import MetricsStore

FENETRE_BUDGET_S = 24 * 3600


def _euros(montant: float) -> str:
    """3 décimales, virgule française : à 2 décimales, 0,006 et 0,005 s'affichaient tous deux « 0.01 »."""
    return f"{montant:.3f}".replace(".", ",") + " €"


def cout_recent_eur(fenetre_s: float = FENETRE_BUDGET_S) -> float:
    return sum(m.cout_eur for m in MetricsStore().lire(depuis_s=fenetre_s))


async def garde_instance_publique(
    request: Request, suite: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method != "POST":
        return await suite(request)

    cle = os.environ.get("MARDIK_API_KEY", "").strip()
    if cle:
        fournie = request.headers.get("X-API-Key", "")
        # compare_digest : même durée que la clé soit juste ou fausse, rien à deviner au chronomètre.
        if not hmac.compare_digest(fournie.encode(), cle.encode()):
            return JSONResponse(
                status_code=401,
                content={"detail": "clé d'accès absente ou invalide : en-tête X-API-Key attendu"},
            )

    plafond = os.environ.get("MARDIK_BUDGET_JOUR_EUR", "").strip()
    if plafond:
        depense = cout_recent_eur()
        if depense >= float(plafond):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"budget de 24 h atteint : {_euros(depense)} dépensés "
                    f"pour {_euros(float(plafond))} autorisés"
                },
            )

    return await suite(request)
