# Expression de besoin — Mardik

## Demande

Mardik exploite un modèle de classification du sentiment des avis clients.
Aujourd'hui ce modèle est appelé manuellement par l'équipe data. La direction
veut le **livrer en nouvelle version**, exposé par une **API** réutilisable par
les autres équipes, avec une **chaîne de livraison automatique**.

## Attentes fonctionnelles

- Une API HTTP qui prend en entrée un texte d'avis et renvoie une prédiction
  (étiquette + score) accompagnée de l'identité et de la version du modèle.
- Des entrées invalides doivent être refusées proprement, avec un message
  d'erreur explicite — l'API ne doit jamais « planter ».
- Chaque fusion sur la branche principale doit produire **automatiquement** une
  version étiquetée du modèle, testée avant d'être livrée.
- En cas de livraison défaillante, l'équipe doit pouvoir **revenir à la version
  précédente** rapidement.

## Contraintes

- Modèle servi : Kimi-K2.6 (Azure AI Inference).
- Le service tourne en conteneur ; les artefacts de modèle sont stockés dans un
  registre dédié.
- Plusieurs versions coexistent ; l'API sert la version active.

## Hors périmètre

- Réentraînement du modèle.
- Interface graphique (l'API suffit pour cette version).
