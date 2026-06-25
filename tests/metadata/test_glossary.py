"""P4-4-W1: glossary tests (terms + relations + linking) (≥3 cases)."""
from __future__ import annotations

import pytest

from services.dataset_service.metadata import glossary as glossary_mod
from services.dataset_service.metadata.glossary import (
    add_relation, create_term, link_term_to_columns, list_glossaries,
    list_relations, list_terms, seed_default_glossary, upsert_glossary,
    validate_relation_type,
)


def test_glossary_crud_and_seed(init_db):
    """Seed a glossary and verify it appears + has expected terms."""
    out = seed_default_glossary()
    assert out["name"] == glossary_mod._DEFAULT_GLOSSARY_NAME
    assert out["seeded_terms"] >= 5

    glossaries = list_glossaries()
    assert any(g["name"] == glossary_mod._DEFAULT_GLOSSARY_NAME for g in glossaries)

    # Find the seeded glossary id
    g_id = next(g["id"] for g in glossaries
                if g["name"] == glossary_mod._DEFAULT_GLOSSARY_NAME)
    terms = list_terms(g_id)
    names = {t["name"] for t in terms}
    assert {"user_id", "uid", "email", "phone"}.issubset(names)


def test_term_create_validation(init_db):
    """Glossary not-found + duplicate-name raise ValueError."""
    g = upsert_glossary("Test", description="")
    with pytest.raises(ValueError):
        create_term("not-a-real-glossary", "x")
    create_term(g.id, "alpha", definition="first")
    with pytest.raises(ValueError):
        create_term(g.id, "alpha")  # duplicate


def test_add_relation_and_validation(init_db):
    """5 relation types valid; self-loop + unknown type rejected."""
    g = upsert_glossary("R", description="")
    t1 = create_term(g.id, "t1")
    t2 = create_term(g.id, "t2")

    # All 5 valid types work
    for rt in ("synonym", "antonym", "parent", "derives_from", "maps_to"):
        r = add_relation(t1.id, t2.id, rt, bidirectional=(rt == "synonym"))
        assert r.relation_type == rt

    # Unknown type rejected
    with pytest.raises(ValueError):
        add_relation(t1.id, t2.id, "random_link")

    # Self-relation rejected
    with pytest.raises(ValueError):
        add_relation(t1.id, t1.id, "synonym")

    # From/To term missing
    with pytest.raises(ValueError):
        add_relation("bogus", t2.id, "synonym")

    # Validate helper
    with pytest.raises(ValueError):
        validate_relation_type("")


def test_synonym_links_to_columns(seeded_metadata, init_db):
    """seeded glossary has user_id ⇄ uid synonym; the seeded metadata has
    a column named ``user_id`` in the orders table — link_term_to_columns
    should return at least that match."""
    out = seed_default_glossary()
    g_id = out["glossary_id"]
    user_id_term = next(t for t in list_terms(g_id) if t["name"] == "user_id")
    uid_term = next(t for t in list_terms(g_id) if t["name"] == "uid")

    cols = link_term_to_columns(user_id_term["id"])
    names = {c.column_name for c in cols}
    assert "user_id" in names
    # Every result carries the source database/schema/table context
    for c in cols:
        assert c.database_name == "primary"
        assert c.schema_name in {"public", "analytics"}
        assert c.table_name in {"users", "orders", "daily_revenue"}

    # The synonym term (uid) should also match (via synonym traversal)
    cols_uid = link_term_to_columns(uid_term["id"])
    syn_names = {c.column_name for c in cols_uid}
    assert "user_id" in syn_names


def test_list_relations(init_db):
    """list_relations returns relations involving a given term (either side)."""
    g = upsert_glossary("X")
    a = create_term(g.id, "a")
    b = create_term(g.id, "b")
    c = create_term(g.id, "c")
    add_relation(a.id, b.id, "synonym")
    add_relation(b.id, c.id, "parent")

    rels = list_relations(b.id)
    assert len(rels) == 2
    # Filter by type
    only_syn = list_relations(b.id, relation_type="synonym")
    assert len(only_syn) == 1
    assert only_syn[0]["relation_type"] == "synonym"
