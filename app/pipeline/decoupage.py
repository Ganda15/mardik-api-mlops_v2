"""Découpage d'un contrat par clauses (étape *map* du map-reduce). Brique 2 du Chantier 1.

    decouper(texte: str, taille_max: int = 6000) -> list[Section]

Découpe sur les intitulés « Article N <séparateur> Titre » (« Article 3 — Résiliation »,
« ARTICLE 3 : Résiliation »), insensible à la casse et au séparateur (em-dash, tiret, deux-
points ou point). Le format « N. Titre » sans le mot « article », mentionné dans le contrat
d'origine de ce module, N'EST PAS géré ici : aucun des 12 contrats de référence
(eval/contrats/) ne l'utilise, et le reconnaître sans confondre une liste numérotée dans le
corps du texte demanderait un signal de plus (ligne isolée, casse du titre…). À reprendre si
un futur contrat en a besoin — voir tests/test_decoupage.py pour ce qui est réellement testé.

Garantie testée : concaténer les ``texte`` de toutes les sections redonne le texte d'origine,
caractère pour caractère — rien n'est perdu. C'est précisément ce que la v1 ne garantit pas
au-delà de son plafond (elle tronque en silence).

Une section plus longue que ``taille_max`` est re-découpée en morceaux qui se terminent
toujours après une phrase ou un paragraphe complet, jamais au milieu d'une phrase.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_MOTIF_ARTICLE = re.compile(r"^article\s+\d+\s*[—–:.\-]\s*(.+)$", re.IGNORECASE)


@dataclass
class Section:
    indice: int
    titre: str
    texte: str


def decouper(texte: str, taille_max: int = 6000) -> list[Section]:
    lignes = texte.splitlines(keepends=True)
    frontieres = _reperer_articles(lignes)

    blocs: list[tuple[str, str]] = []
    debut_preambule = frontieres[0][0] if frontieres else len(lignes)
    if debut_preambule > 0:
        blocs.append(("préambule", "".join(lignes[:debut_preambule])))
    for i, (debut, titre) in enumerate(frontieres):
        fin = frontieres[i + 1][0] if i + 1 < len(frontieres) else len(lignes)
        blocs.append((titre, "".join(lignes[debut:fin])))

    sections: list[Section] = []
    for titre, bloc in blocs:
        for morceau in _sous_decouper(bloc, taille_max):
            sections.append(Section(indice=len(sections), titre=titre, texte=morceau))
    return sections


def _reperer_articles(lignes: list[str]) -> list[tuple[int, str]]:
    """Renvoie ``[(indice de ligne, titre)]`` pour chaque ligne d'en-tête d'article."""
    frontieres: list[tuple[int, str]] = []
    for i, ligne in enumerate(lignes):
        m = _MOTIF_ARTICLE.match(ligne.strip())
        if m:
            frontieres.append((i, m.group(1).strip()))
    return frontieres


def _sous_decouper(bloc: str, taille_max: int) -> list[str]:
    """Redécoupe ``bloc`` en morceaux <= ``taille_max``, coupés après une phrase ou un
    paragraphe entier — jamais au milieu d'une phrase. Concaténer les morceaux redonne
    exactement ``bloc``."""
    if len(bloc) <= taille_max:
        return [bloc]
    morceaux: list[str] = []
    reste = bloc
    while len(reste) > taille_max:
        limite = _frontiere_de_phrase(reste, taille_max)
        morceaux.append(reste[:limite])
        reste = reste[limite:]
    if reste:
        morceaux.append(reste)
    return morceaux


def _frontiere_de_phrase(texte: str, taille_max: int) -> int:
    """La coupure la plus proche de ``taille_max``, juste après une phrase ou un
    paragraphe complet ; à défaut (aucune ponctuation trouvée), une coupure brute en
    dernier recours — documenté, jamais silencieux."""
    fenetre = texte[:taille_max]
    for motif in (r"\n\n", r"(?<=[.!?])\s"):
        candidats = list(re.finditer(motif, fenetre))
        if candidats:
            return candidats[-1].end()
    return taille_max
