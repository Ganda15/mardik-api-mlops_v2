"""L'API de pilotage et sa page. Brique 16 (Chantier 2) — contrat figé dans docs/spec-ch2-pilotage.md §2.

    GET  /pilotage             la page : bannière d'alerte, signaux par version, journal, bouton
    GET  /pilotage/etat        actif, canary, signaux par version (brique 14), alertes en cours
    GET  /pilotage/journal     les dernières lignes du journal, les plus récentes d'abord
    POST /pilotage/rollback    {acteur, commentaire} → 201 + la ligne de journal créée

Le retour arrière est une décision humaine (CTO, 16/09) : le clic porte un nom — ``422`` sinon,
jamais anonyme — et la ligne de journal cite l'alerte en cours. Cette API agit sur la production :
jeton d'administration ``MARDIK_ADMIN_TOKEN`` (en-tête ``X-Admin-Token``), distinct de la clé du
lien public. Aucun jeton configuré → ``403`` : sans jeton, le rollback par l'API est désactivé
(échec fermé), la ligne de commande et le workflow ``rollback.yml`` restent disponibles.
Pas de route d'écriture des seuils : un seuil change par un commit (conception Ch2 §6.4, §9).
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.telemetry import MetricsStore
from ops.deploy import ErreurDeploiement, rollback
from ops.registry import Registry
from ops.seuils import charger_seuils
from ops.signaux import signaux_par_version

router = APIRouter(tags=["pilotage"])
PAGE_PILOTAGE = Path(__file__).resolve().parent / "static" / "pilotage.html"
REMISE_A_ZERO = {"publication", "canary", "promotion", "rollback"}


def get_registry() -> Registry:
    return Registry()


def get_metriques() -> MetricsStore:
    return MetricsStore()


class DemandeRollback(BaseModel):
    acteur: str | None = None
    commentaire: str | None = None


def alertes_en_cours(reg: Registry) -> list[dict[str, Any]]:
    """Les alertes des versions qui servent du trafic, postérieures au dernier changement de version."""
    journal = reg.journal()
    canary, _ = reg.canary()
    en_cours: dict[tuple[str, str], dict[str, Any]] = {}
    for version in [v for v in (reg.active(), canary) if v]:
        depuis = max((e["ts"] for e in journal if e.get("version") == version
                      and e.get("evenement") in REMISE_A_ZERO), default=0.0)
        for e in journal:
            if e.get("evenement") == "alerte" and e.get("version") == version and e["ts"] > depuis:
                en_cours[(version, e.get("signal", "?"))] = e
    return sorted(en_cours.values(), key=lambda e: e["ts"])


@router.get("/pilotage", response_class=HTMLResponse, include_in_schema=False)
def page() -> HTMLResponse:
    return HTMLResponse(PAGE_PILOTAGE.read_text(encoding="utf-8"))


@router.get("/pilotage/etat")
def etat(reg: Registry = Depends(get_registry), met: MetricsStore = Depends(get_metriques)) -> dict[str, Any]:
    canary, pct = reg.canary()
    return {
        "active": reg.active(),
        "canary": canary,
        "canary_percent": pct,
        "versions": signaux_par_version(met.lire(), charger_seuils()),
        "alertes": alertes_en_cours(reg),
    }


@router.get("/pilotage/journal")
def journal(limite: int = Query(20, ge=1, le=500), reg: Registry = Depends(get_registry)) -> list[dict[str, Any]]:
    return list(reversed(reg.journal()))[:limite]


@router.post("/pilotage/rollback", status_code=201)
def demander_rollback(
    demande: DemandeRollback,
    x_admin_token: str | None = Header(default=None),
    reg: Registry = Depends(get_registry),
) -> dict[str, Any]:
    attendu = os.environ.get("MARDIK_ADMIN_TOKEN", "").strip()
    if not attendu:
        raise HTTPException(403, "rollback par l'API désactivé : aucun jeton d'administration configuré "
                                 "(MARDIK_ADMIN_TOKEN) — utiliser la ligne de commande ou le workflow rollback.yml")
    if not hmac.compare_digest((x_admin_token or "").encode(), attendu.encode()):
        raise HTTPException(401, "jeton d'administration absent ou invalide : en-tête X-Admin-Token attendu")
    acteur = (demande.acteur or "").strip()
    if not acteur:
        raise HTTPException(422, "acteur obligatoire : un retour arrière porte le nom de qui le décide")

    alertes = alertes_en_cours(reg)
    alerte = None
    if alertes:
        a = alertes[-1]
        alerte = {k: a.get(k) for k in ("date", "version", "signal", "valeur", "seuil")}
    try:
        rollback(reg, motif="bouton de pilotage", acteur=acteur,
                 commentaire=(demande.commentaire or "").strip() or None, alerte=alerte)
    except ErreurDeploiement as exc:
        raise HTTPException(409, str(exc)) from exc
    return reg.journal()[-1]
