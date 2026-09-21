# Spec v2 — périmètre figé (Chantier 1)

> Courte spec demandée par le brief (« Développement — Chantier 1 », puce 1). Elle fige ce que la v2 fait, ce qu'elle ne fait pas,
> et ce qui prouve qu'elle le fait. Elle découle du dossier de conception Chantier 1 validé par le formateur, corrigé le 21/09 par ce
> que le dépôt impose. Source du besoin : `docs/besoin_client.md`. Baseline du brief : `Mardik-BRIEF-original.md` (dossier du brief).

## 1. Exigences fonctionnelles (ce que la v2 fait)

- **E1 — Contrats entiers, sans troncature.** Le contrat est découpé en sections (`pipeline.decouper`, par intitulé d'article,
  `taille_max` par section), chaque section est analysée par un appel LLM (`pipeline.extraire`), les clauses sont fusionnées et
  dédoublonnées (`pipeline.consolider`). La concaténation des sections couvre tout le texte : rien n'est perdu — c'est le défaut de la v1.
- **E2 — Score de confiance par clause et global.** `pipeline.scorer` calcule un score composite : la confiance déclarée par le modèle
  **et** au moins une vérification faite sans lui (l'extrait cité figure-t-il dans le contrat ? la clause a-t-elle été vue dans
  plusieurs sections ?). Un modèle sûr de lui sur une citation inventée obtient un score bas. `confiance_globale` résume les scores par
  clause ; c'est ce que le juriste lit pour savoir quand relire.
- **E3 — Erreurs explicites, jamais un 500 brut.** `422` corps invalide ou texte trop court ; `503` fournisseur LLM indisponible, avec
  un `detail` lisible. Une requête invalide ne coûte aucun appel au modèle.
- **E4 — `/v1` intact.** `app/api_v1.py` n'est pas modifié. Le client historique `scripts/client_v1.py` passe avant, pendant et après.
- **E5 — Mêmes signaux que la v1, plus le score.** Chaque requête `/v2` écrit une `Mesure` (`version`, `latence_ms`, `score`, `cout_eur`,
  `appels_llm`, `erreur`) et des spans `analyse.requete` → `llm.appel` (un par section). Une version qui n'écrit pas là est invisible.

## 2. Contrat `/v2` (imposé par le dépôt et ses tests)

`POST /v2/analyse` `{"texte": "...", "contrat_id": "c07"}` →
`{"clauses": [{"type", "extrait", "confiance", "sections"}], "confiance_globale", "modele", "version", "sections", "appels_llm",
"latence_ms", "cout_eur"}`. Champs additifs prévus par la conception (non testés par le dépôt, ajoutés sans casser la forme) :
`request_id`, libellé du niveau de certitude, en-tête de version sur la réponse.

## 3. Contraintes (ce qui doit rester vrai)

| Contrainte | Valeur | D'où elle vient | Où elle est vérifiée |
|---|---|---|---|
| Latence | p95 < 8 s, contrats longs compris | `docs/besoin_client.md` | gate d'évaluation (`latence_max_ms`), critère bloquant |
| Coût | < 0,15 € par analyse en moyenne | `docs/besoin_client.md` | gate d'évaluation (`cout_max_eur`), critère bloquant |
| Note | ≥ `seuil_note` par contrat (0,75 ; 0,8 pour c07, c10, c12) | `eval/attendus.jsonl` | gate d'évaluation ; rappel imposé, **précision rapportée en plus** |
| Non-déterminisme | température et `seed` figés dans le bundle ; `essais_eval` passes moyennées | README du dépôt, séance du 16/09 | `models/v2/config.yaml`, `eval/run_eval.py` |
| Livraison | aucune livraison manuelle ; une fusion sur `main` = une version étiquetée ; un gate rouge bloque | note du CTO | `llmops.yml`, `ops/deploy.publier` refuse si le gate échoue |
| Branches | branche courte par changement, jamais de push direct sur `main`, PR relue | conception Ch1 §3.0, validée 18/09 | protection de branche GitHub |
| Rollback | **manuel, entièrement** — une décision arbitrée par une personne ; jamais automatique, ni pour le canary ni pour l'actif | formateur, 21/09 : « pour beaucoup plus de simplicité, [ça] devrait être laissé manuel » | `surveiller()` alerte et journalise, n'appelle jamais `rollback()` |
| Secrets | jamais dans l'image, le registre, les journaux | conception Ch1 §3.7 | `.env` non versionné, secrets GitHub Actions |

**Taille de section.** Le stub propose `taille_max = 6000` caractères. Avec trois contrats de 30, 35 et 40 pages, cela fait plusieurs
appels séquentiels par analyse : la valeur sera **mesurée** contre les 8 s et 0,15 € sur c07, c10, c12 avant d'être figée. Ce chiffre
n'est pas une hypothèse à défendre, c'est un résultat du gate.

## 4. Hors périmètre de la v2 (dit, pas oublié)

Traduction en anglais et chatbot (demandes « pendant qu'on y est », hors note du CTO, incompatibles avec 8 s / 0,15 €) · dépôt de
fichiers PDF (les juristes collent le texte) · modification fonctionnelle de `/v1` · environnement de staging (le canary sur trafic réel
en tient lieu à 20 requêtes par jour) · signature cosign (si le temps le permet, jamais annoncée avant) · calibration isotonique du score
(itération 2, sur le score composite) · tout le Chantier 2 (tableau de bord, boucles, journal de pilotage).

## 5. Critères d'acceptation (ce qui prouve E1 à E5)

Les cinq tests fournis dans `tests/acceptance/test_chaine.py`, rouges au départ, verts à la fin du Chantier 1 :

| # | Test | Exigence prouvée |
|---|---|---|
| 1 | `test_contrat_v2_long_analyse_sans_troncature` | E1, E2 — c12 (40 p.) : `sections > 1`, résiliation et droit applicable trouvés, pas de doublon |
| 2 | `test_erreurs_explicites_jamais_de_500` | E3 — 422 corps invalide, 422 texte court, 503 fournisseur en panne avec « LLM » dans `detail` |
| 3 | `test_client_v1_fonctionne` | E4 — le client historique passe |
| 4 | `test_etiquetage_version_apres_gate` | livraison — un gate vert étiquette `v2.0.0` dans le registre avec commit, empreinte, note ; un gate rouge refuse |
| 5 | `test_gate_evaluation_note_par_version` | note par contrat pour v1 et v2, `history.jsonl`, v2 > v1 sur c07, c10, c12 |

Deux critères ajoutés par la conception, sans test fourni — à écrire :
- **A1** : le rapport du gate contient la **précision** à côté du rappel (un modèle qui annonce les 14 types ne doit pas passer inaperçu).
- **A2** : le gate de release tourne sur le **vrai modèle** au moins une fois avant tout étiquetage ; en CI (`MOCK=on`) sans fixtures
  enregistrées, le vert prouve la plomberie, pas le modèle — dit tel quel dans le runbook.

## 6. Ce qui a changé depuis le dossier de conception validé (traçabilité)

| Sujet | Dossier Ch1 (16–18/09) | Cette spec (21/09) | Pourquoi |
|---|---|---|---|
| Documents longs | un appel long-contexte, `413` au-dessus d'un plafond | map-reduce par sections | imposé par le dépôt : stub `map_reduce_clauses`, test 1 `sections > 1` |
| Route et champs `/v2` | `/v2/analyses`, 14 types avec `presente`, score calibré | `/v2/analyse`, champs du dépôt ; les nôtres deviennent additifs | imposé par les tests fournis |
| Note du gate | F1 | rappel (imposé) + précision rapportée | `eval/run_eval.py` |
| Rollback | manuel | manuel, **sans** découpage canary / actif | formateur, 21/09 |
| Architecture | trois conteneurs derrière un routeur | un processus, gateway en interne lisant le registre à chaque requête | `app/gateway.py`, `docker-compose.yml` |

Le registre des décisions complet, avec les citations, est dans `CONTINUITE.md` du dossier du brief (§D quater).

## 7. Ordre des briques (chacune : test rouge → code → vert → diff montré)

> ⚠️ Corrigé le 21/09, deux fois : la liste d'origine (9 briques) oubliait `app/gateway.py`
> (2 tests d'acceptance en dépendent) — insérée comme brique 9. Puis, en clôturant la brique 9,
> constaté qu'`ops/dashboard.py` n'était non plus listé nulle part, alors qu'un test d'acceptance
> (`test_dashboard_par_version`) en dépend directement. Insérée comme brique 10 ; la chaîne CI
> passe à la brique 11. Les deux oublis ont la même cause : la liste d'origine a été faite en
> lisant les 5 puces du brief, pas l'arborescence réelle du dépôt (section « Les chantiers » du
> README) — elle ne nommait que les fichiers alors « gros », pas les 2 petits stubs restants.

1. `models/v2/config.yaml` — le bundle v2 : stratégie, prompt par section, schéma JSON de sortie, température, `seed`, `essais_eval`. ✅
2. `app/pipeline/decoupage.py` — `decouper` : rien ne se perd, aucune phrase coupée. ✅
3. `app/pipeline/extraction.py` — `extraire` : un appel par section, JSON contraint, clause fautive ignorée et signalée. ✅
4. `app/pipeline/consolidation.py` — `consolider` : un type = une clause, extrait le plus long, sections fusionnées. ✅
5. `app/pipeline/confiance.py` — `scorer` : composite (déclaré × extrait vérifié × multi-sections), global. ✅
6. `app/api_v2.py` — `analyser_v2` + la route, télémétrie, 503 explicite. ✅
7. `eval/run_eval.py` — le gate : rappel + précision, p95, coût, `history.jsonl`, code de sortie. ✅
8. `ops/deploy.py` — `publier` (refuse si le gate est rouge), `deployer_canary`, `promouvoir`, `rollback`, `surveiller`
   (alerte seule, **jamais** de rollback automatique — décision du formateur, 21/09, `CONTINUITE.md` §D quater). ✅
9. `app/gateway.py` — `choisir_version` (fonction pure), `GET /gateway/etat`, `POST /analyse` (routage canary v1/v2). ✅
10. `ops/dashboard.py` — `resume` (agrégats par version), `rendre_texte`, `rendre_html`.
11. `.github/workflows/llmops.yml` — gates, build, publication, canary ; filtre de chemin pour le gate payant. ✅

**Les 11 briques sont faites.** `chantier1/dev` : 15 commits, 48 tests, 10/10 tests d'acceptance du brief verts,
`ruff check` propre. Reste hors de cette liste : `docs/exploitation.md` (runbook, 7 sections, vide), le frontend
(livrable N12, jamais décidé), et la mesure réelle (`MOCK=off`) de `contexte_max_caracteres` contre le budget
8 s / 0,15 € — ouverte depuis la brique 1, jamais fermée, parce que tout ce dossier a tourné en `MOCK=on`.

## 📖 Glossaire

- **Map-reduce par clauses** : découper le contrat en sections, un appel LLM par section (map), puis fusionner les clauses (reduce).
- **Bundle** : `models/vX/config.yaml` — modèle, prompt, paramètres, schéma de sortie, stratégie ; c'est *la* version du modèle ici.
- **Gate** : contrôle bloquant de la chaîne ; rouge = rien n'est étiqueté, rien ne part.
- **Rappel / précision** : part des clauses attendues trouvées / part des clauses annoncées qui sont attendues.
- **Registre** : `ops/registry/`, un dossier par version livrée, `index.json` pour qui sert le trafic, `journal.jsonl`.
- **Fixture MOCK** : réponse LLM enregistrée, rejouée en CI sans réseau.
- **Rollback** : retour à la version précédente en une opération ; ici toujours déclenché par une personne.
