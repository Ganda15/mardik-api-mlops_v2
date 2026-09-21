from app.llm_client import Bundle, LLMClient
from app.pipeline.decoupage import Section
from app.pipeline.extraction import extraire


def test_extraire_trouve_une_clause_connue_dans_une_section():
    bundle = Bundle.charger("v2")
    client = LLMClient(bundle)
    section = Section(
        indice=0,
        titre="Résiliation",
        texte="Article 16 — Résiliation\n\nChaque partie peut résilier le contrat moyennant un préavis de trois mois.",
    )

    clauses, reponse = extraire(section, client)

    types_trouves = [c.type for c in clauses]
    assert "résiliation" in types_trouves

    clause = next(c for c in clauses if c.type == "résiliation")
    assert 0.0 <= clause.confiance_llm <= 1.0
    assert clause.sections == [section.indice]