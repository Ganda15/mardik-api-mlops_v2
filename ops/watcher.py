"""Le watcher : il alerte, il promeut, il ne recule jamais seul. Brique 15 (Chantier 2).

    tick(registry=None, metriques=None, maintenant=None) -> dict      # un tour
    python -m ops.watcher [--boucle] [--intervalle 60]

Conception Ch2 §4.1, §4.2, §6.1 ; tous les seuils viennent de ``eval/thresholds.yml`` (brique 13).

**Alerte** — pour chaque version qui sert du trafic (l'active, le canary), sur sa fenêtre (brique 14),
si l'état est ``ok`` : taux d'erreur, P95, part des scores < 0,5 et médiane comparés à
``rollback_alerte`` et à la ``signature`` de la version saine. Un signal franchi → une ligne ``alerte``
(signal, valeur, seuil, fenêtre, acteur ``watcher``), une seule fois tant que rien n'a changé.
**Le retour arrière reste humain** (arbitrage du CTO) : ce module n'appelle jamais ``rollback``.

**Promotion** — si un canary sert du trafic : sa fenêtre d'observation, ce sont les mesures arrivées
**depuis la dernière décision** à son palier. Elle s'achève quand il y en a ``promotion.requetes_min``
et que le palier dure depuis ``jours_min``. Alors **tous** les critères doivent tenir, aucun ne compense
un autre : palier suivant (10 → 50 → 100, et à 100 le canary devient l'active) ; sinon
``refus_promotion`` avec les critères en échec ; ``refus_consecutifs_alerte`` refus de suite → alerte
pour décision humaine. Références des critères relatifs : la version stable sur sa fenêtre si elle a
assez de mesures (et des scores) ; sinon la signature — la v1 ne produit pas de score.
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

from app.telemetry import MetricsStore
from ops.registry import Registry
from ops.seuils import charger_seuils
from ops.signaux import calculer_signaux, signaux_par_version

EVENEMENTS_REMISE_A_ZERO = {"publication", "canary", "promotion", "rollback"}
EVENEMENTS_DECISION = {"canary", "promotion", "refus_promotion"}


def _derniere(journal: list[dict[str, Any]], version: str, evenements: set[str]) -> float:
    ts = [e["ts"] for e in journal if e.get("version") == version and e.get("evenement") in evenements]
    return max(ts) if ts else 0.0


def _deja_signale(journal: list[dict[str, Any]], version: str, signal: str) -> bool:
    depuis = _derniere(journal, version, EVENEMENTS_REMISE_A_ZERO)
    return any(
        e.get("evenement") == "alerte" and e.get("version") == version and e.get("signal") == signal
        and e["ts"] > depuis
        for e in journal
    )


def _signaux_franchis(sig: dict[str, Any], seuils: dict[str, Any]) -> list[tuple[str, float, float]]:
    """(signal, valeur, seuil) pour chaque signal de dérive franchi."""
    ra, ref = seuils["rollback_alerte"], seuils["signature"]
    franchis = []
    if sig["taux_erreur"] > ra["taux_erreur_max"]:
        franchis.append(("taux_erreur", sig["taux_erreur"], ra["taux_erreur_max"]))
    if sig["latence_p95_ms"] > ra["p95_ms_max"]:
        franchis.append(("latence_p95_ms", sig["latence_p95_ms"], ra["p95_ms_max"]))
    if sig["part_score_bas"] is not None:
        seuil = round(ref["part_score_bas"] + ra["part_score_bas_delta_max"], 4)
        if sig["part_score_bas"] > seuil:
            franchis.append(("part_score_bas", sig["part_score_bas"], seuil))
    if sig["score_median"] is not None:
        seuil = round(ref["score_median"] + ra["mediane_delta_min"], 4)
        if sig["score_median"] < seuil:
            franchis.append(("score_median", sig["score_median"], seuil))
    return franchis


def _criteres_promotion(
    canary: dict[str, Any], stable: dict[str, Any] | None, seuils: dict[str, Any]
) -> list[tuple[str, float, float]]:
    """(critère, valeur, seuil) pour chaque critère de promotion en échec — vide si tout tient."""
    pr, sig_ref = seuils["promotion"], seuils["signature"]
    stable_ok = stable is not None and stable["etat"] == "ok"
    ref_erreur = stable["taux_erreur"] if stable_ok else seuils["rollback_alerte"]["taux_erreur_max"]
    ref_score = stable if stable_ok and stable["score_median"] is not None else {
        "part_score_bas": sig_ref["part_score_bas"], "score_median": sig_ref["score_median"]}

    echecs = []
    if canary["latence_p95_ms"] > pr["p95_ms_max"]:
        echecs.append(("latence_p95_ms", canary["latence_p95_ms"], pr["p95_ms_max"]))
    seuil_err = round(ref_erreur + pr["taux_erreur_delta_max"], 4)
    if canary["taux_erreur"] > seuil_err:
        echecs.append(("taux_erreur", canary["taux_erreur"], seuil_err))
    if canary["part_score_bas"] is not None:
        seuil = round(ref_score["part_score_bas"] + pr["part_score_bas_delta_max"], 4)
        if canary["part_score_bas"] > seuil:
            echecs.append(("part_score_bas", canary["part_score_bas"], seuil))
    if canary["score_median"] is not None:
        seuil = round(ref_score["score_median"] + pr["mediane_delta_min"], 4)
        if canary["score_median"] < seuil:
            echecs.append(("score_median", canary["score_median"], seuil))
    if canary["cout_moyen_eur"] > pr["cout_moyen_eur_max"]:
        echecs.append(("cout_moyen_eur", canary["cout_moyen_eur"], pr["cout_moyen_eur_max"]))
    return echecs


def tick(
    registry: Registry | None = None,
    metriques: MetricsStore | None = None,
    maintenant: float | None = None,
) -> dict[str, Any]:
    reg = registry or Registry()
    met = metriques or MetricsStore()
    maintenant = maintenant if maintenant is not None else time.time()
    seuils = charger_seuils()
    mesures = met.lire()
    active = reg.active()
    canary, pct = reg.canary()
    par_version = signaux_par_version(mesures, seuils, maintenant)
    resultat: dict[str, Any] = {"alertes": [], "decision": None}

    # 1. Alertes de dérive, sur chaque version qui sert du trafic. Jamais de retour arrière ici.
    for version in [v for v in (active, canary) if v]:
        sig = par_version.get(version)
        if not sig or sig["etat"] != "ok":
            continue
        for signal, valeur, seuil in _signaux_franchis(sig, seuils):
            if _deja_signale(reg.journal(), version, signal):
                continue
            reg.journaliser("alerte", version=version, signal=signal, valeur=valeur, seuil=seuil,
                            fenetre={"requetes": sig["requetes"]}, action="aucune — décision humaine",
                            acteur="watcher")
            resultat["alertes"].append(signal)

    # 2. Promotion du canary, quand sa fenêtre d'observation s'achève.
    if canary:
        pr = seuils["promotion"]
        journal = reg.journal()
        depuis = _derniere(journal, canary, EVENEMENTS_DECISION)
        debut_palier = _derniere(journal, canary, {"canary", "promotion"})
        fenetre = [m for m in mesures if m.version == canary and m.ts > depuis]
        if len(fenetre) < int(pr["requetes_min"]) or maintenant - debut_palier < float(pr["jours_min"]) * 86400:
            resultat["decision"] = "attente"
            return resultat

        sig_canary = calculer_signaux(fenetre, int(pr["requetes_min"]))
        echecs = _criteres_promotion(sig_canary, par_version.get(active), seuils)
        valeurs = {k: sig_canary[k] for k in ("requetes", "latence_p95_ms", "taux_erreur",
                                               "part_score_bas", "score_median", "cout_moyen_eur")}
        if not echecs:
            suivant = next((p for p in pr["paliers"] if p > pct), 100)
            if suivant >= 100:
                reg.ecrire_index({"active": canary, "canary": None, "canary_percent": 0, "precedente": active})
                action = f"{canary} devient l'active (100 %), {active} devient la précédente"
            else:
                reg.definir_canary(canary, suivant)
                action = f"canary {canary} : {pct} % → {suivant} %"
            reg.journaliser("promotion", version=canary, palier=suivant, valeurs=valeurs, action=action,
                            acteur="watcher")
            resultat["decision"] = f"promotion {suivant}"
        else:
            signal, valeur, seuil = echecs[0]
            reg.journaliser("refus_promotion", version=canary, palier=pct, signal=signal, valeur=valeur,
                            seuil=seuil, criteres_en_echec=[e[0] for e in echecs], valeurs=valeurs,
                            action="aucune", acteur="watcher")
            resultat["decision"] = "refus"
            journal = reg.journal()
            refus = [e for e in journal if e.get("version") == canary and e.get("evenement") == "refus_promotion"
                     and e["ts"] > _derniere(journal, canary, {"canary", "promotion"})]
            if len(refus) >= int(pr["refus_consecutifs_alerte"]) and not _deja_signale(journal, canary, "refus_consecutifs"):
                reg.journaliser("alerte", version=canary, signal="refus_consecutifs", valeur=len(refus),
                                seuil=pr["refus_consecutifs_alerte"], action="aucune — attendre ou reculer : décision humaine",
                                acteur="watcher")
                resultat["alertes"].append("refus_consecutifs")
    return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watcher Mardik : alerte et promotion, jamais de retour arrière")
    parser.add_argument("--boucle", action="store_true", help="tourner sans fin")
    parser.add_argument("--intervalle", type=float, default=60.0, help="secondes entre deux tours")
    args = parser.parse_args(argv)
    while True:
        print(json.dumps(tick(), ensure_ascii=False), flush=True)
        if not args.boucle:
            return 0
        time.sleep(args.intervalle)


if __name__ == "__main__":
    raise SystemExit(main())
