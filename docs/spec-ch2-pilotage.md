# Spec courte — Chantier 2 : l'observabilité qui pilote

> **Statut : VALIDÉE par Era le 23/09/2026.** Réponses d'Era aux questions du §8 : échéance du 24/09 confirmée ; rollback
> **par les deux chemins** (bouton de la page de pilotage ET déclenchement GitHub Actions).
> Source qui fait foi : `Mardik-Conception-Chantier2.md` (dossier du brief, validé). Cette spec ne redécide rien : elle
> **condense** la conception en exigences, contraintes et critères d'acceptation, et dit ce que le dépôt fait déjà.
> Échéance annoncée en réunion le 23/09 : **Chantier 2 fini le jeudi 24/09**.
> Format repris de `docs/spec-v2-perimetre.md`. Remarque du formateur à un camarade le 23/09, appliquée ici : **les critères
> d'acceptation (§5) sont séparés des contraintes (§3)**, et chacun pointe vers le test qui le prouve.

## 1. Exigences fonctionnelles (les 5 puces « Chantier 2 » du brief)

| # | Exigence (vue utilisateur) | Pour qui | Ce que le dépôt fait déjà (mesuré le 23/09) | Ce qui manque |
|---|---|---|---|---|
| **E6** | Voir en un écran : latence, coût, erreurs, **distribution** du score, part de trafic v1/v2, par version | chef de projet | tableau de bord (brique 10) : P50/P95, taux d'erreur, coût, part de trafic… et un **score moyen** | la **distribution** du score (part < 0,5, médiane, déciles) — la moyenne cache exactement le défaut à voir ; l'état « données insuffisantes » |
| **E7** | Quand le score dérive, être **alerté**, puis revenir en arrière **en un clic**, et que l'événement soit tracé avec le signal qui l'a déclenché | chef de projet (non-développeur) | `surveiller()` détecte et journalise une `alerte` ; `rollback` existe en ligne de commande | le **bouton** ; le lien alerte → rollback dans le journal (signal, valeur, seuil, acteur) ; les seuils lus dans un fichier |
| **E8** | Le canary **monte seul** (10 → 50 → 100 %) quand ses métriques tiennent, et **ne monte pas** sinon | l'équipe, sans veille manuelle | `promouvoir` existe, **manuelle** | la décision automatique, non compensable, avec `refus_promotion` tracé |
| **E9** | Un cas réel à faible confiance devient un cas du jeu d'évaluation, **rejoué** à la fusion suivante | juristes, développeur | le gate rejoue `eval/attendus.jsonl` à chaque PR qui le touche (filtre de chemin, brique 11) | la **capture** (score < 0,5), le **masquage**, l'ajout au jeu en version N+1 |
| **E10** | Tout ajustement (seuil, promotion, rollback) figure au **journal** avec le signal qui l'a déclenché | CTO, audit | `ops/registry/journal.jsonl` (append-only) : publication, canary, alerte, rollback | un format de ligne uniforme (`signal`, `valeur`, `seuil`, `fenetre`, `acteur`) ; la ligne `ajustement_seuil` ; un seul fichier de seuils |

## 2. Contrat de l'API de pilotage (interface figée avant le code)

| Route | Rôle | Réponses |
|---|---|---|
| `GET /pilotage/etat` | par version : les cinq signaux, l'état (`ok` / `alerte` / `donnees_insuffisantes`), la fenêtre | 200 |
| `GET /pilotage/journal?limite=` | les dernières lignes du journal, les plus récentes d'abord | 200 |
| `POST /pilotage/rollback` `{acteur, commentaire}` | retour arrière, tracé avec l'acteur et l'alerte en cours | **201** + la ligne créée · **422** sans `acteur` (jamais anonyme) · **409** rien à annuler · **401** sans jeton d'administration |

Jeton d'administration **distinct** de la clé du lien public (`MARDIK_ADMIN_TOKEN` ≠ `MARDIK_API_KEY`) : cette API agit sur la
production, elle n'analyse pas de contrats. **Pas de route d'écriture des seuils** : un seuil change par un commit, jamais par un
champ de saisie (conception §6.4 et §9).

## 3. Contraintes (ce qui doit rester vrai)

| Contrainte | D'où elle vient |
|---|---|
| **Le retour arrière n'est jamais automatique** : le watcher alerte, un humain décide et clique | CTO, 16/09 (« antinomique » avec le canary) ; formateur, 21/09 ; spec Ch1 §3 |
| Avancer est automatique **seulement si tous les critères tiennent** — aucun ne compense un autre | conception §4.2 |
| **30 mesures minimum** dans la fenêtre, sinon « données insuffisantes » et **aucune décision** | conception §2, §3 |
| **Échec fermé** : métriques absentes ou illisibles → aucune promotion | conception §3 |
| Tous les seuils dans **un seul fichier versionné** ; en changer un = un commit | conception §3, §9 ; manque connu depuis le 22/09 (`eval/thresholds.yml` promis, absent) |
| Le journal est **append-only** et ne contient **jamais de texte de contrat** | conception §5 |
| Aucun texte de contrat capturé sans **masquage** préalable des parties et montants | conception §4.3 (masquage partiel, dit tel quel) |
| Le contrat `/v1`, le contrat `/v2` et `llmops.yml` ne changent pas | conception §1 |

## 4. Hors périmètre (dit, pas oublié)

- Un collecteur autre que Jaeger (Langfuse nommé et écarté, conception §7).
- Un courriel d'alerte (optionnel dans la conception).
- La recalibration du score (le score n'est pas calibré ; le dire, pas le prétendre).
- Un conteneur par version et Caddy en frontal : la gateway en processus reste l'architecture (spec Ch1 §6).

## 5. Critères d'acceptation (ce qui prouve que c'est fait)

Les cinq tests « L'observabilité qui pilote » du brief, chacun rattaché à sa preuve :

| # | Test du brief (résumé) | Preuve prévue | État le 23/09 |
|---|---|---|---|
| **6** | dérive simulée (`traffic_sim.py`) → seuil franchi → retour arrière via la chaîne, tracé | `derive-score` → ligne `alerte` avec signal / valeur / seuil → clic sur le bouton → ligne `rollback` avec acteur et alerte d'origine → `X-Mardik-Version` revient à la version précédente | alerte + rollback CLI **prouvés le 22/09** (runbook §7) ; bouton et lien alerte → rollback **à faire** |
| **7** | canary conforme → promu ; non conforme → pas de promotion | trafic sain → ligne `promotion` et poids 10 → 50 ; `DRIFT=erreurs` → ligne `refus_promotion`, poids inchangé | **à faire** |
| **8** | cas à faible confiance capturé → dans le jeu d'éval → rejoué à la fusion suivante | requête à score < 0,5 → `ops/candidats.jsonl` (masqué) → ajout étiqueté à `eval/attendus.jsonl` → la PR déclenche le gate | **à faire** |
| **9** | tableau de bord : latence, coût, erreurs, distribution du score, part v1/v2 | page ouverte, les cinq visibles par version | **partiel** : distribution absente (moyenne seule) |
| **10** | journal : tout ajustement avec son signal | chaque ligne `alerte` / `promotion` / `refus_promotion` / `rollback` / `ajustement_seuil` porte `signal`, `valeur`, `seuil` | **partiel** : format non uniforme, `ajustement_seuil` absent |

Critères ajoutés par la conception :
- **A3** — le détecteur est **mesuré dans les deux sens** avant la démo : trafic dégradé → taux de détection ; trafic sain →
  taux de fausses alertes. Les deux chiffres notés (conception §3).
  ✅ **Mesuré le 23/09** (brique 18b, données réelles de la version actuelle) : détection de la dérive du score **100 %**,
  fausses alertes de dérive **0 %**. Révèle aussi que le P95 < 8 s n'est pas tenu sur des requêtes réelles (runbook §9).
- **A4** — sous 30 mesures, l'état affiché est « données insuffisantes » et **aucune** promotion ne part.

Les cinq tests fournis de `tests/acceptance/test_observabilite.py` sont **verts depuis le Chantier 1** et restent verts.

## 6. Divergences conception ↔ dépôt (traçabilité)

| Sujet | Conception Ch2 | Cette spec | Pourquoi |
|---|---|---|---|
| Rollback « s'exécute » quand le seuil est franchi (texte du brief) | alerte → clic humain | **alerte → clic humain** | arbitrage du CTO, test fourni réécrit le 21/09 ; le brief est lu à la lumière de l'annexe B |
| Poids du canary | `weights.json`, `set_weight` | l'index du registre (`canary_percent`), `deployer_canary` | le dépôt a déjà ce mécanisme, lu à chaque requête par la gateway |
| Journal | `ops/journal.jsonl` | `ops/registry/journal.jsonl`, **un seul** journal | le dépôt l'écrit déjà ; deux journaux = deux vérités |
| `llmops.yml` « ne change pas » | intact | **deux lignes retirées** (`--seuil 0.75` codé en dur, gate et publication) | sans cela le fichier de seuils serait ignoré par la chaîne — « documenté mais absent » ; aucune étape ajoutée ni retirée (brique 13) |
| Référence de la dérive | la signature calculée par le gate, portée par le manifeste | **mesurée** sur 17 analyses réelles saines (médiane 0,993, part < 0,5 : 5,9 %), écrite dans `eval/thresholds.yml` §`signature`, validée par Era le 23/09 — **provisoire** | le manifeste ne porte pas encore de signature ; constat utile : la dérive simulée met les scores à ~0,52, juste au-dessus de 0,5 — la part < 0,5 bouge peu (+6,6 pts), la **médiane** s'effondre (−0,47) : les deux statistiques sont surveillées parce que chacune voit ce que l'autre rate |
| Journal et capture | une ligne `capture` au journal par cas capturé | la capture est tracée dans `ops/candidats.jsonl` (heure, requête, score, seuil) ; le journal garde les **décisions** (alerte, promotion, refus, rollback, **enrichissement**, seuil) | journaliser chaque capture cassait le test fourni `test_promotion_canary_puis_totale` (« chaque étape est journalisée » : les deux dernières lignes doivent être canary puis promotion) et noyait les décisions ; une capture est une observation, l'ajout au jeu d'évaluation est la décision, et il est journalisé |
| Seuils | `thresholds.yml` | **`eval/thresholds.yml`** | sous `eval/`, un changement de seuil déclenche le gate dès la PR (filtre de chemin) — exactement la procédure §9 |
| Watcher | conteneur à part, boucle 60 s / 10 min | un module appelable une fois (`tick`) ou en boucle ; service `watcher` dans `docker-compose.yml` | testable sans horloge ; même service en démo |
| Bouton | sur le tableau de bord | page `/pilotage` servie par l'API | le tableau de bord fourni ne sert que du HTML en lecture ; la conception Ch2 H23 prévoit ce repli |
| Rollback « via la chaîne » | le bouton appelle `redeploy` | **les deux** : le bouton agit sur la production (registre lu par la gateway) ; un workflow `rollback.yml` (`workflow_dispatch`, champs `acteur` et `motif`) agit sur le registre publié par la chaîne (artefact `registry-<version>`) et le re-publie en `-rollback` | décision d'Era du 23/09 ; `llmops.yml` reste intact, c'est un fichier à part. Limite dite : le runner ne voit pas la production locale, il agit sur l'état publié |
| Cas de production dans le jeu d'éval | une ligne de plus dans `eval/attendus.jsonl`, rejouée par le gate | **un fichier à part, `eval/attendus_production.jsonl`**, rejoué par sa propre étape `eval.rejouer_production` (job `gate-evaluation`, bloquante), le filtre de chemin le surveille aussi | constaté le 23/09 sur le **premier cas réel** (`prod-req_0f26491a2c08`) : le test fourni `test_gate_evaluation_note_par_version` fige « les 12 contrats annotés » (`set(par_contrat) == {c01…c12}`) — un 13ᵉ contrat dans ce fichier le casse pour toujours, pas seulement à la fusion suivante. Le test n'a pas été touché ; c'est le dépôt qui s'y plie. Le rejeu reste bloquant : un cas de production en échec arrête la livraison |
| Latence (risque n°1 trouvé par le détecteur, brique 18b) | hors Chantier 2 | **brique 19** : un seul client HTTP (plus une poignée de main TLS par section), délai 20 s + 1 reprise par appel (bundle), **sections voisines regroupées** (4 000 caractères, `regroupement_caracteres`) — c01 passe de 18 appels à 3 | on attend le plus lent des appels : moins d'appels = queue plus courte. **Mesuré au gate réel le 23/09** : P95 **5 940 ms** (7 046 le 22/09), coût **0,019 €/analyse** (0,030), rappel 1,000 et précision 0,953 inchangés. Diverge de la brique 2 « un appel par section » : le découpage est intact, le regroupement est un paramètre du bundle (0 = comportement d'origine) |
| Latence, suite (c12 > 8 s sur requête isolée) | — | **proxy de dérive corrigé** : un seul client amont réutilisé (`ops/drift_proxy.py`, fichier fourni, une correction) | sondé le 23/09 : 1,2–1,5 s en direct vs 3,9–7,4 s via le proxy pour le même appel ; 23 appels parallèles max 6,66 s vs 3,19 s. Après : c12 2,75–4,20 s sur 8 requêtes réelles, c07 3,8 s. La limite « c12 > 8 s » est levée sur cet échantillon |
| Coût par analyse | `cout_par_1k_tokens` unique (hérité v1) | **brique 23** : `cout_par_1k_entree` / `cout_par_1k_sortie` au catalogue, partage des jetons dans chaque `Mesure` | la sortie coûte 6× l'entrée sur gpt-5.4 ; l'ancien tarif sous-estimait ×1,7. Gate réel : **0,033 €/analyse**, c12 0,088 — cible 0,15 tenue. Tarif Azure à confirmer sur le portail (action d'Era) |
| Référence de la dérive (suite) | signature calculée par le gate, portée par le manifeste | **brique 20** : `Rapport.signature` (vrai modèle seulement — jamais en MOCK), `manifest.signature`, le watcher lit celle de la version active et retombe sur `eval/thresholds.yml` sinon ; `ops.deploy publier --rapport` publie depuis un rapport sauvegardé | ferme la divergence « provisoire » ci-dessus : v2.3.0 publiée localement avec la signature du gate réel (0,9915 / 0,0 / 12). En CI le manifeste reste sans signature tant que le gate réel ne tourne pas dans la chaîne (brique 21) |
| Gate réel et livraison (réserve A2, `modele-ci`) | idée de David : tag `eval-ok/<sha>` | **brique 21** : `gate-reel.yml` (manuel, Azure, secrets d'Era, rapport en artefact, tag `eval-ok/<sha>`) ; `llmops.yml` refuse de publier sans ce tag **si** la variable de dépôt `MARDIK_EXIGER_EVAL_OK=1`, et publie alors depuis le vrai rapport | la variable évite de bloquer `main` avant que les secrets existent — poser les secrets et la variable est l'action d'Era ; le workflow n'a pas encore tourné (dit tel quel) |
| Mesures du gate | un fichier `eval/.metrics_eval.jsonl` | `EVAL_METRICS_PATH` (tmp dans les tests) | trouvé le 23/09 : les suites de tests en MOCK y avaient écrit 486 lignes et 7,23 € de faux coûts à côté des vraies mesures |

## 7. Ordre des briques (chacune : test rouge → code → vert → suite complète → commit)

| Brique | Quoi | Ferme |
|---|---|---|
| **13** ✅ | `eval/thresholds.yml` + `ops/seuils.py` (échec fermé, `MARDIK_SEUILS` pour la démo) ; le gate, la publication et la chaîne lisent le fichier, valeurs inchangées. `surveiller()` est remplacé par le watcher en brique 15 | contrainte « un seul fichier » ; manque du 22/09 |
| **14** ✅ | les cinq signaux par version sur une fenêtre, « données insuffisantes » ; le tableau de bord montre part < 0,5, médiane, déciles | E6, test 9, A4 |
| **15** ✅ | le watcher, un tour : alerte tracée (signal, valeur, seuil, fenêtre) ; promotion automatique 10 → 50 → 100 si **tous** les critères tiennent, sinon `refus_promotion` ; **jamais** de rollback | E7 (détection), E8, test 7 |
| **16** ✅ | l'API de pilotage (§2) + la page `/pilotage` : bannière d'alerte, signaux, journal, bouton de rollback avec nom obligatoire ; **et** `.github/workflows/rollback.yml` (`workflow_dispatch`) sur le registre publié | E7 (décision), test 6, test 10 |
| **17** ✅ | capture des cas < 0,5 avec masquage ; script d'ajout étiqueté au jeu d'évaluation (version N+1) | E9, test 8 |
| **18** ✅ | procédure d'ajustement des seuils (ligne `ajustement_seuil` avec le commit) ; mesure du détecteur dans les deux sens ; transcript réel du test 6 de bout en bout | E10, A3 |
| **19** ✅ | latence : client partagé, délai + reprise, regroupement des sections — mesuré au gate réel | `tests/test_llm_client_reprises.py`, `test_decoupage.py` |
| **20** ✅ | signature calculée par le gate, portée par le manifeste, lue par le watcher ; `publier --rapport` | `tests/test_signature_manifeste.py` |
| **21** ✅ (forme) | gate réel manuel `gate-reel.yml`, tag `eval-ok/<sha>`, publication qui l'exige sur variable — **non exécuté** (secrets d'Era) | `tests/test_gate_reel.py` |
| **22** ✅ | collection Bruno de la démo, une requête par étape avec son explication | `tests/test_bruno.py` |
| **23** ✅ | coût réel : tarifs entrée/sortie du modèle, partage des jetons dans chaque mesure — gate réel 0,033 €/analyse | `tests/test_cout_entree_sortie.py` |

**Risque dit tel quel** : six briques pour une échéance au lendemain. Si le temps manque, l'ordre ci-dessus livre d'abord ce que
les tests du brief exigent (13 → 16) ; 17 et 18 viennent ensuite. Aucune brique n'est déclarée faite sans son test.

## 8. À clarifier

- **[TRANCHÉ par Era, 23/09 : les deux chemins, §6]** « le rollback s'exécute **via la chaîne** » : le bouton qui modifie le registre lu par la gateway
  suffit-il, ou attend-il un déclenchement GitHub Actions (`workflow_dispatch`) ? Le registre de production est local, pas sur le
  runner ; la conception a retenu le premier.
- **[TRANCHÉ par Era, 23/09 : oui]** l'échéance du 24/09 s'applique-t-elle à ce projet (elle a été dite pendant la présentation d'un camarade) ?
- **[À CLARIFIER — client]** l'anonymisation des contrats capturés : le masquage par motifs est partiel ; la question reste ouverte
  avec le client (conception §4.3).
