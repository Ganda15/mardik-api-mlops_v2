# Rappel : ce que la remédiation a laissé en place

Au brief de remédiation (« Mardik, production aveugle »), l'application a été
instrumentée. Ces briques sont **fournies fonctionnelles** : on construit
dessus, on ne les refait pas.

```
                 requête HTTP
                      │
   ┌──────────────────▼──────────────────┐
   │  app/api_v1.py   (contrat historique)│   span  analyse.requete
   │      │  tronque si > contexte_max    │     └─ span  llm.appel
   │      ▼                               │
   │  app/llm_client.py ──► proxy ──► LLM │   log   analyse.terminee / analyse.echec
   │                     (ops/drift_proxy)│   mesure Mesure(...) → ops/metrics.jsonl
   └──────────────────────────────────────┘
```

## Les trois signaux (`app/telemetry.py`)

| Signal | Où | Comment le lire |
|---|---|---|
| **Traces** (OpenTelemetry) | spans `analyse.requete` → `llm.appel`, attributs `mardik.version`, `mardik.tronque`, `llm.latence_ms`, `llm.tokens` | en local : exportées sur la console en JSON (`OTEL_TRACES=console`) ; dans les tests : `InMemorySpanExporter` (fixture `span_exporter`) |
| **Logs structurés** (structlog, JSON) | événements `analyse.terminee`, `analyse.echec` avec `version`, `latence_ms`, `clauses`, `tronque` | `docker compose logs app` ; dans les tests : `structlog.testing.capture_logs()` |
| **Métriques** (`MetricsStore`) | une ligne JSON par requête dans `ops/metrics.jsonl` : `ts, version, route, latence_ms, erreur, score, cout_eur, appels_llm, tokens, tronque` | `MetricsStore().lire(depuis_s=300)` — c'est la source du tableau de bord et de la surveillance |

Exemple d'une ligne de `ops/metrics.jsonl` :

```json
{"ts": 1757900000.12, "version": "v1.0.0", "route": "/v1/analyse", "latence_ms": 2410.5,
 "erreur": false, "score": null, "cout_eur": 0.0031, "appels_llm": 1, "tokens": 1560, "tronque": true}
```

## Ce que ça implique pour la v2

- La v2 et la gateway doivent produire **les mêmes signaux** : un span
  `analyse.requete`, un span `llm.appel` par appel au modèle, une `Mesure`
  par requête — avec, en plus, le **score de confiance** (`score`) que la v1
  ne produit pas (`null`).
- Le tableau de bord (`ops/dashboard.py`) et la surveillance
  (`ops/deploy.py::surveiller`) **ne lisent que** `ops/metrics.jsonl` et le
  registre. Si une version n'y écrit pas, elle est invisible — et donc
  impilotable.
- Les tests d'intégration (`tests/integration/`) vérifient que ces signaux
  sont là sur `/v1`. Ils sont verts et doivent le rester.

## Comment lire une dérive

Le proxy (`ops/drift_proxy.py`) dégrade le trafic **entre** l'app et le
modèle. Vu depuis les métriques :

| `DRIFT=` | ce qu'on observe dans `metrics.jsonl` |
|---|---|
| `latence` | `latence_ms` ×4 sur la version qui reçoit le trafic |
| `erreurs` | `erreur: true` sur ~10 % des lignes |
| `score` | `score` qui s'effondre vers 0,5 (uniquement sur les versions qui produisent un score) |

La question du brief : *qui regarde ces lignes, à quelle fréquence, et que
déclenche-t-il ?*
