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
**Constaté le 23/09 : seul l'en-tête existait, et seulement sur la gateway. Écrits le 23/09 (brique F1)** :
`libelle` (`haute` / `moyenne` / `basse`, bornes H6 lues dans `parametres.seuils_libelle` du bundle), `request_id`
(`req_` + 12 hexa, dans la réponse 200 et la 503, dans les journaux et sur le span `analyse.requete`), en-tête
`X-Mardik-Version` sur `/v2` (succès et 503). Un `422` ne porte pas de `request_id` : il est produit avant tout journal et
toute trace, il n'y a rien à corréler. `/v1` ne gagne aucun champ (test de garde).

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
  ✅ Écrit le 22/09 (`tests/test_run_eval.py`, 3 tests) — mesuré sur le vrai modèle : 0,950.
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
| En-tête de version | `X-Mardik-Release`, sur toutes les réponses, `/v1` comprise | `X-Mardik-Version`, sur `/v2` et la gateway ; `/v1` inchangée | nom imposé par le test d'acceptance fourni (`test_observabilite.py`) ; `/v1` : exigence 2 du CTO, aucun ajout même additif |

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
7. `eval/run_eval.py` — le gate : rappel, p95, coût, `history.jsonl`, code de sortie. ✅ La **précision** (A1, §5) n'y était
   pas — constaté le 22/09 en lisant l'enregistrement du gate réel, alors que cette ligne disait « rappel + précision » ;
   **écrite le 22/09** (`noter()`, `precision` + `en_trop` par contrat, rapportée, jamais bloquante). ✅
8. `ops/deploy.py` — `publier` (refuse si le gate est rouge), `deployer_canary`, `promouvoir`, `rollback`, `surveiller`
   (alerte seule, **jamais** de rollback automatique — décision du formateur, 21/09, `CONTINUITE.md` §D quater). ✅
9. `app/gateway.py` — `choisir_version` (fonction pure), `GET /gateway/etat`, `POST /analyse` (routage canary v1/v2). ✅
10. `ops/dashboard.py` — `resume` (agrégats par version), `rendre_texte`, `rendre_html`.
11. `.github/workflows/llmops.yml` — gates, build, publication, canary ; filtre de chemin pour le gate payant. ✅
    **Exécutée pour de vrai le 22/09** (PR #1 puis fusion sur `main`, run 35715784616, 7/7 jobs verts) après correction de
    4 défauts trouvés à la relecture (registre éphémère sur le runner, version calculée depuis des dossiers absents, job canary
    sans le registre publié, image jamais poussée, `GITHUB_TOKEN` en lecture seule). Traces : image
    `ghcr.io/ganda15/mardik-api-mlops_v2:v2.0.0` (publique), tag git `v2.0.0` annoté, artefacts `registry-v2.0.0` et
    `registry-v2.0.0-canary` (`index.json` : active v1.0.0, canary v2.0.0 à 10 %). Réserve : le manifeste publié porte
    `modele: modele-ci` et `note_eval: 1.0` (environnement CI, `MOCK=on`), pas le vrai modèle ni la vraie note.
12. `app/api_v2.py` — sections analysées en parallèle (`parallelisme` du bundle, pool borné, ordre conservé, spans imbriqués). ✅
    Ajoutée le 21/09 après la mesure réelle ci-dessous ; **juste chez un fournisseur qui sert plusieurs requêtes à la fois, sans
    effet (et même nuisible : 503) sur un Ollama local à `OLLAMA_NUM_PARALLEL=1`**.

**Les 12 briques sont faites.** `chantier1/dev` : 19 commits, 50 tests, 10/10 tests d'acceptance du brief verts,
`ruff check` propre. Reste hors de cette liste : `docs/exploitation.md` (runbook, 7 sections, vide) et le frontend
(livrable N12, jamais décidé). *(État du 21/09. Le runbook a été écrit le 22/09 ; le frontend, ci-dessous.)*

**Ajoutées le 23/09, décision d'Era — le frontend avant le Chantier 2** (numérotées F pour ne pas décaler les briques 13–16
du Chantier 2) :

- **F1.** `app/api_v2.py`, `app/gateway.py`, `app/pipeline/confiance.py` — les champs additifs de §2 que le frontend affiche :
  `libelle`, `request_id`, `X-Mardik-Version`. ✅ 16 tests (`tests/test_api_v2_champs_frontend.py`).
- **F2.** `app/static/index.html`, servie sur `GET /` par `app/main.py` — la page unique de H15 : coller ou charger un contrat,
  choisir la route (production = gateway, ou v2 directe), afficher le niveau de certitude **avec sa règle de décision**, le
  score, les clauses et leur extrait (surligné sous 0,7), la version qui a répondu, le `request_id`, la durée et le coût ;
  rend aussi une réponse v1 (liste de clauses, alerte de troncature) et les erreurs 422 / 503 en français. Aucune ressource
  externe, aucun HTML construit depuis les données. ✅ 5 tests (`tests/test_frontend.py`) + vérification dans un navigateur
  (fichier chargé, réponse v2, réponse v1, 422, largeur mobile, mode sombre, console sans erreur) — un défaut trouvé ainsi
  (le mot « null » affiché sous une réponse v1) et corrigé. **Limite** : le JavaScript de la page n'a pas de test automatisé,
  seulement cette vérification manuelle outillée.
- **F3.** `app/securite.py`, branché dans `app/main.py` — **décision d'Era du 23/09 : le lien public passe par un tunnel depuis
  son PC (option C)**. Une page publique qui appelle Azure = un budget que n'importe qui peut dépenser, donc deux gardes, actives
  seulement sur l'instance lancée avec leur variable (jamais dans `.env`) : `MARDIK_API_KEY` → chaque POST exige `X-API-Key`
  (conception Ch1 §2.3), `401` sinon ; `MARDIK_BUDGET_JOUR_EUR` → `429` au-delà du coût des 24 dernières heures (lu dans les
  `Mesure`). Les GET restent ouverts (la page doit se charger). Refus décidés avant tout appel au modèle : ils ne coûtent rien.
  La page porte un champ « Code d'accès » (gardé dans l'onglet, `sessionStorage`) et traduit `401` / `429`. ✅ 13 tests
  (`tests/test_securite_instance_publique.py`, +1 dans `tests/test_frontend.py`) ; `conftest.py` retire les deux variables
  (l'app charge `.env`) ; vérifié dans un navigateur, un défaut trouvé ainsi et corrigé (montants arrondis à 2 décimales :
  0,006 € et 0,005 € s'affichaient tous deux « 0.01 »). **Limite** : un tunnel n'est pas un hébergement — le lien meurt quand
  le PC s'éteint, et son adresse change à chaque lancement.

**La question de §3 (« taille de section »), mesurée deux fois le 21/09 — sur deux fournisseurs différents :**

*D'abord sur `llama3.2:3b` (Ollama local, CPU 4 threads, pas de GPU), contrat c01 (2 p., 10 537 car.)* : en série, 18 sections,
404,7 s ; en parallèle par 4, 503 après 127 s (Ollama sert une requête à la fois, `OLLAMA_NUM_PARALLEL:1`, les appels en attente
dépassent `LLM_TIMEOUT_S=60`). **Mais Ollama local n'est que l'option gratuite du dépôt** (`.env.example:3`) — l'architecture
réelle du brief est « API LLM externe... hébergée sur Azure » (`Mardik-BRIEF-original.md:151-152`). Ce résultat ne répond donc
pas à la question sur la vraie cible.

*Ensuite sur Azure (déploiement `gpt-5.4`, la vraie architecture du brief), `parallelisme` porté à la taille du contrat* — sur
les 3 contrats que ce §3 nomme explicitement :

| Contrat | Sections | Durée | Coût |
|---|---|---|---|
| c01 (le plus court, hors cible §3) | 18 | 4,1 – 7,1 s | 0,020 € |
| **c07** | 26 | **5,9 s** | **0,049 €** |
| **c10** | 27 | **4,8 s** | **0,053 €** |
| **c12** | 31 | **5,1 s** | **0,062 €** |

**Sur la vraie architecture du brief, les 3 contrats de référence tiennent les deux budgets, confortablement.** Jaeger confirme
un vrai parallélisme côté fournisseur (4+ appels simultanés, Azure ne fait pas la queue comme Ollama). Deux bugs réels trouvés
et corrigés en testant contre le vrai modèle (`max_tokens` → `max_completion_tokens` pour `gpt-5.4` ; le paramètre
`api-version` cassait la surface Azure unifiée `.../openai/v1`) — détail et commits dans `ETAT.md` du dossier du brief.
**Tranché le 22/09 : `parallelisme: 32`** (une vague pour c12, 31 sections ; trafic client ~20 req/jour, §4 — pas de risque de
quota à ce volume). **Puis le gate lui-même a tourné sur le vrai modèle** (`MOCK=off`, 1 essai, ~0,40 €) :

| Gate v2.0.0, Azure `gpt-5.4`, 22/09 | Mesuré | Seuil |
|---|---|---|
| Note globale (rappel) | **1,000** — 12/12 contrats ≥ leur `seuil_note` | ≥ 0,75 (0,8 pour c07, c10, c12) |
| Latence P95 | **6 353 ms** | < 8 000 ms |
| Coût moyen par analyse | **0,030 €** | < 0,15 € |
| Verdict | **PASSE**, code de sortie 0 | |

Deuxième run le même jour, une fois A1 écrit : **rappel 1,000, précision 0,950, P95 7 046 ms, coût 0,030 €, PASSE** — la
précision montre ce que le rappel seul cachait (`garantie` annoncée sans être attendue sur c01, c04, c11 ; `résiliation` sur
c03 : faux positifs du modèle ou attendus manquants, à trancher contrat par contrat).
Réserves : un seul essai (le bundle en prévoit 3) ; P95 sur 12 mesures, **6 353 puis 7 046 ms** — la marge sous 8 000 est
étroite ; les appels manuels par HTTP donnent 4,7 – 9,8 s selon le run.

## 📖 Glossaire

- **Map-reduce par clauses** : découper le contrat en sections, un appel LLM par section (map), puis fusionner les clauses (reduce).
- **Bundle** : `models/vX/config.yaml` — modèle, prompt, paramètres, schéma de sortie, stratégie ; c'est *la* version du modèle ici.
- **Gate** : contrôle bloquant de la chaîne ; rouge = rien n'est étiqueté, rien ne part.
- **Rappel / précision** : part des clauses attendues trouvées / part des clauses annoncées qui sont attendues.
- **Registre** : `ops/registry/`, un dossier par version livrée, `index.json` pour qui sert le trafic, `journal.jsonl`.
- **Fixture MOCK** : réponse LLM enregistrée, rejouée en CI sans réseau.
- **Rollback** : retour à la version précédente en une opération ; ici toujours déclenché par une personne.
