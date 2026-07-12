"""Unit tests for :mod:`backend.imdf.agency.loader`.

These tests exercise the public surface that the V5 routing layer
(v5.1 intent-classification) actually depends on.  Coverage:

  1. ``load_all()`` returns 232 roles                          (test_load_all)
  2. ``load_by_department("Data Acquisition")`` returns 15   (test_load_by_department)
  3. ``load_by_id`` happy + sad paths                         (test_load_by_id_*)
  4. ``search("crawler")`` finds the right experts            (test_search)
  5. ``get_capability_matrix`` is complete (232 id-bearing)   (test_capability_matrix)

Plus a few invariants that the loader must preserve:
  * every role has a unique id
  * every id slug ends in ``_expert_NNN``
  * every department referenced appears in :data:`DEPARTMENT_ORDER`
    (with the exception of the ``"_spare_"`` sentinel).
  * capability-matrix values are sorted lists of role ids.
"""
from __future__ import annotations

from typing import Dict, List

import pytest

from backend.imdf.agency import (
    AGENCY_DIR,
    DEFAULT_DEPARTMENTS_FILE,
    DEPARTMENT_ORDER,
    DEPARTMENT_SEAT_QUOTAS,
    EXPECTED_TOTAL_ROLES,
    AgentRole,
    AgencyLoader,
    Bilingual,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def loader() -> AgencyLoader:
    """A module-level loader: heavy to construct, cheap to reuse."""
    return AgencyLoader()


@pytest.fixture(scope="module")
def all_roles(loader: AgencyLoader) -> List[AgentRole]:
    return loader.load_all()


# ---------------------------------------------------------------------------
# 1. load_all() returns 232 roles
# ---------------------------------------------------------------------------

def test_load_all_returns_expected_total(loader: AgencyLoader) -> None:
    """The roster must contain exactly 232 experts (V5 Chapter 28)."""
    roles = loader.load_all()
    assert len(roles) == EXPECTED_TOTAL_ROLES == 232
    assert EXPECTED_TOTAL_ROLES == sum(DEPARTMENT_SEAT_QUOTAS.values())


def test_load_all_ids_are_unique(all_roles: List[AgentRole]) -> None:
    """Two roles must never share an id slug."""
    ids = [r.id for r in all_roles]
    assert len(ids) == len(set(ids)), f"Duplicate ids detected: {sorted(x for x in set(ids) if ids.count(x) > 1)}"


def test_load_all_ids_follow_slug_pattern(all_roles: List[AgentRole]) -> None:
    """Every id must end in ``_expert_<3-digit-number>``."""
    import re

    pattern = re.compile(r"^[a-z0-9_]+_expert_\d{3}$")
    bad = [r.id for r in all_roles if not pattern.match(r.id)]
    assert not bad, f"Bad id slugs: {bad[:10]}"


def test_load_all_departments_are_canonical(loader: AgencyLoader) -> None:
    """Every role's department is either one of the 16 or ``_spare_``."""
    allowed = set(DEPARTMENT_ORDER) | {"_spare_"}
    for r in loader.load_all():
        assert r.department in allowed, f"Unknown department: {r.department!r}"


# ---------------------------------------------------------------------------
# 2. load_by_department returns the expected size
# ---------------------------------------------------------------------------

def test_load_by_department_data_acquisition_has_15(loader: AgencyLoader) -> None:
    """Data Acquisition should have exactly 15 experts."""
    roles = loader.load_by_department("Data Acquisition")
    assert len(roles) == 15
    assert all(r.department == "Data Acquisition" for r in roles)


def test_load_by_department_is_case_insensitive(loader: AgencyLoader) -> None:
    """Department lookup is case-insensitive on the canonical name."""
    canonical = loader.load_by_department("Data Acquisition")
    lower = loader.load_by_department("data acquisition")
    assert {r.id for r in canonical} == {r.id for r in lower}


def test_load_by_department_empty_returns_empty(loader: AgencyLoader) -> None:
    """An empty / unknown department returns ``[]`` rather than raising."""
    assert loader.load_by_department("") == []
    assert loader.load_by_department("Nonexistent") == []


# ---------------------------------------------------------------------------
# 3. load_by_id
# ---------------------------------------------------------------------------

def test_load_by_id_returns_role_for_valid_slug(loader: AgencyLoader) -> None:
    """A known id slug should resolve to an :class:`AgentRole`."""
    role = loader.load_by_id("data_acquisition_expert_001")
    assert role is not None
    assert role.id == "data_acquisition_expert_001"
    assert role.department == "Data Acquisition"
    # Bilingual sanity
    assert isinstance(role.name, Bilingual)
    assert role.name.en  # non-empty
    assert role.name.zh  # non-empty


def test_load_by_id_returns_none_for_unknown(loader: AgencyLoader) -> None:
    """Unknown id → ``None`` (not an exception, not an empty AgentRole)."""
    assert loader.load_by_id("nonexistent_expert_999") is None
    assert loader.load_by_id("") is None
    assert loader.load_by_id("   ") is None


def test_load_by_id_roundtrips_all_roles(all_roles: List[AgentRole], loader: AgencyLoader) -> None:
    """For every role, ``load_by_id(r.id)`` returns the same instance.

    This catches drift between load_all() ordering and id-keyed lookups.
    """
    for r in all_roles:
        fetched = loader.load_by_id(r.id)
        assert fetched is not None, f"missing role for id={r.id}"
        assert fetched.id == r.id
        assert fetched.department == r.department


# ---------------------------------------------------------------------------
# 4. search
# ---------------------------------------------------------------------------

def test_search_crawler_returns_relevant_hits(loader: AgencyLoader) -> None:
    """``search('crawler')`` must surface the crawler-relevant experts."""
    hits = loader.search("crawler")
    assert hits, "search('crawler') returned no hits"
    # Senior Crawler Specialist is in Data Acquisition, and the Web Scraping
    # Engineer is the obvious other hit.
    ids = {r.id for r in hits}
    assert "data_acquisition_expert_001" in ids  # Senior Crawler Specialist


def test_search_is_case_insensitive(loader: AgencyLoader) -> None:
    lower = loader.search("crawler")
    upper = loader.search("CRAWLER")
    mixed = loader.search("CrAwLeR")
    assert {r.id for r in lower} == {r.id for r in upper} == {r.id for r in mixed}


def test_search_empty_query_returns_all(loader: AgencyLoader) -> None:
    """An empty query returns the whole roster (caller asked for everything)."""
    assert len(loader.search("")) == EXPECTED_TOTAL_ROLES
    assert len(loader.search("   ")) == EXPECTED_TOTAL_ROLES


def test_search_zero_hits_for_unknown(loader: AgencyLoader) -> None:
    """A search for nonsense should return an empty list (not raise)."""
    assert loader.search("xyzzy123-no-such-thing") == []


def test_search_results_ordered_by_department_then_id(loader: AgencyLoader) -> None:
    """Results are sorted by (department index, id) for stable UI rendering."""
    hits = loader.search("engineer")
    if len(hits) < 2:
        pytest.skip("need at least 2 hits to verify ordering")
    order = {name: i for i, name in enumerate(DEPARTMENT_ORDER)}
    order["_spare_"] = len(DEPARTMENT_ORDER)
    keys = [(order.get(h.department, 99), h.id) for h in hits]
    assert keys == sorted(keys), "search() returned results out of order"


# ---------------------------------------------------------------------------
# 5. capability_matrix
# ---------------------------------------------------------------------------

def test_capability_matrix_covers_all_232_roles(loader: AgencyLoader) -> None:
    """Capability matrix union must contain every role id in the roster."""
    matrix: Dict[str, List[str]] = loader.get_capability_matrix()
    all_ids = {r.id for r in loader.load_all()}
    matrix_ids = {rid for ids in matrix.values() for rid in ids}
    assert matrix_ids == all_ids, (
        f"Matrix missing ids: {sorted(all_ids - matrix_ids)[:5]} | "
        f"Matrix extras: {sorted(matrix_ids - all_ids)[:5]}"
    )


def test_capability_matrix_values_are_sorted_lists(loader: AgencyLoader) -> None:
    """For deterministic JSON / UI output, every list must be alphabetised."""
    matrix = loader.get_capability_matrix()
    for skill, ids in matrix.items():
        assert ids == sorted(ids), f"unsorted ids for skill={skill!r}"


def test_capability_matrix_at_least_one_skill_per_role(all_roles: List[AgentRole], loader: AgencyLoader) -> None:
    """Sanity-check: each role contributes at least one skill to the matrix."""
    matrix = loader.get_capability_matrix()
    for r in all_roles:
        # Will be True unless somehow a role has zero skills, which the
        # dataclass forbids in __post_init__.
        assert any(r.id in ids for ids in matrix.values()), f"role {r.id} not in matrix"


# ---------------------------------------------------------------------------
# Invariants on AgentRole / Bilingual
# ---------------------------------------------------------------------------

def test_agent_role_is_frozen(all_roles: List[AgentRole]) -> None:
    """Roles are frozen — mutation should raise ``dataclasses.FrozenInstanceError``."""
    import dataclasses
    role = all_roles[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        role.id = "tampered"  # type: ignore[misc]


def test_bilingual_rejects_empty_strings() -> None:
    """Bilingual must reject blank strings."""
    with pytest.raises(ValueError):
        Bilingual(zh="", en="en")
    with pytest.raises(ValueError):
        Bilingual(zh="zh", en="   ")


def test_bilingual_from_value_dict_and_string() -> None:
    """Bilingual.from_value accepts dicts and plain strings."""
    b1 = Bilingual.from_value({"zh": "中文", "en": "English"})
    assert b1.zh == "中文" and b1.en == "English"
    b2 = Bilingual.from_value("plain text")
    assert b2.zh == "plain text" and b2.en == "plain text"


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

def test_agency_dir_path_exists() -> None:
    """AGENCY_DIR must point to the bundled ``imdf/agency`` directory."""
    assert AGENCY_DIR.exists()
    assert AGENCY_DIR.is_dir()
    assert (AGENCY_DIR / DEFAULT_DEPARTMENTS_FILE).exists(), (
        f"departments.json missing from {AGENCY_DIR}"
    )


def test_department_order_has_16_entries() -> None:
    """The roster is keyed on exactly 16 canonical departments."""
    assert len(DEPARTMENT_ORDER) == 16
