"""Per-department coverage tests for :mod:`backend.imdf.agency.loader`.

The V5 Chapter 28 spec partitions 232 experts across 16 canonical
departments.  This file asserts the spec's seat quota is honoured for
**every** department — catching off-by-one errors in
``build_roster.py`` early.

We also assert a few structural invariants per department:

  * role ids start with ``<dept_slug>_expert_``
  * ``Bilingual`` fields are non-empty
  * every role has at least one skill
  * titles are non-empty strings
"""
from __future__ import annotations

from typing import List

import pytest

from backend.imdf.agency import (
    DEPARTMENT_ORDER,
    DEPARTMENT_SEAT_QUOTAS,
    EXPECTED_TOTAL_ROLES,
    AgentRole,
    AgencyLoader,
    Bilingual,
)


@pytest.fixture(scope="module")
def loader() -> AgencyLoader:
    return AgencyLoader()


# ---------------------------------------------------------------------------
# Static shape: 16 departments + 1 spare = 17 buckets, totals match
# ---------------------------------------------------------------------------

def test_department_order_has_16_entries() -> None:
    assert len(DEPARTMENT_ORDER) == 16


def test_department_seat_quotas_sum_to_232() -> None:
    """Sum of ``DEPARTMENT_SEAT_QUOTAS`` must equal ``EXPECTED_TOTAL_ROLES``."""
    assert sum(DEPARTMENT_SEAT_QUOTAS.values()) == EXPECTED_TOTAL_ROLES == 232


# ---------------------------------------------------------------------------
# One test per department — the spec's seat quota is enforced for every one
# ---------------------------------------------------------------------------

EXPECTED_DEPARTMENT_QUOTAS: dict[str, int] = {
    # 16 canonical departments
    "Data Acquisition":       15,
    "Annotation":             15,
    "Quality Assurance":      15,
    "Workflow":               14,
    "Project Management":     12,
    "Domain Expert":          20,
    "Creative Writing":       15,
    "Visual Arts":            15,
    "Audio & Music":          12,
    "Video & Film":           15,
    "AI/ML Research":         15,
    "Security & Compliance":  10,
    "DevOps & Infrastructure": 10,
    "Customer Service":       12,
    "Sales & Marketing":      12,
    "Executive & Strategy":   10,
    # Spare pool — 15 cross-functional bench experts
    "_spare_":                15,
}


@pytest.mark.parametrize("department,quota", sorted(EXPECTED_DEPARTMENT_QUOTAS.items()))
def test_department_has_expected_seat_count(
    loader: AgencyLoader, department: str, quota: int
) -> None:
    """Each department must contain exactly ``quota`` experts."""
    roles = loader.load_by_department(department)
    assert len(roles) == quota, (
        f"{department}: expected {quota} experts, found {len(roles)}"
    )


def test_department_quota_dict_matches_module_constant() -> None:
    """The expected-quota table here must mirror :data:`DEPARTMENT_SEAT_QUOTAS`."""
    for dept, quota in EXPECTED_DEPARTMENT_QUOTAS.items():
        assert DEPARTMENT_SEAT_QUOTAS.get(dept) == quota, (
            f"{dept}: this test says {quota}, module says {DEPARTMENT_SEAT_QUOTAS.get(dept)}"
        )


# ---------------------------------------------------------------------------
# Structural invariants applied department-by-department
# ---------------------------------------------------------------------------

DEPARTMENT_TO_ID_SLUG: dict[str, str] = {
    "Data Acquisition":        "data_acquisition",
    "Annotation":              "annotation",
    "Quality Assurance":       "quality_assurance",
    "Workflow":                "workflow",
    "Project Management":      "project_management",
    "Domain Expert":           "domain_expert",
    "Creative Writing":        "creative_writing",
    "Visual Arts":             "visual_arts",
    "Audio & Music":           "audio_music",
    "Video & Film":            "video_film",
    "AI/ML Research":          "ai_ml_research",
    "Security & Compliance":   "security_compliance",
    "DevOps & Infrastructure": "devops_infrastructure",
    "Customer Service":        "customer_service",
    "Sales & Marketing":       "sales_marketing",
    "Executive & Strategy":    "executive_strategy",
    # _spare_ uses _spare_ as its slug
    "_spare_":                 "_spare_",
}


@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_ids_use_correct_slug(loader: AgencyLoader, department: str) -> None:
    """Every id in department D must start with ``<dept_slug>_expert_``."""
    expected_prefix = f"{DEPARTMENT_TO_ID_SLUG[department]}_expert_"
    for r in loader.load_by_department(department):
        assert r.id.startswith(expected_prefix), (
            f"{department}: role id {r.id!r} does not start with {expected_prefix!r}"
        )


@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_roles_have_bilingual_fields(loader: AgencyLoader, department: str) -> None:
    """Every role has non-empty zh/en for name, description, system_prompt."""
    for r in loader.load_by_department(department):
        assert isinstance(r.name, Bilingual) and r.name.zh and r.name.en
        assert isinstance(r.description, Bilingual) and r.description.zh and r.description.en
        assert isinstance(r.system_prompt, Bilingual) and r.system_prompt.zh and r.system_prompt.en


@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_roles_have_skills(loader: AgencyLoader, department: str) -> None:
    """Every role must declare at least one skill (dataclass-enforced)."""
    for r in loader.load_by_department(department):
        assert r.skills, f"{department}/{r.id}: empty skills list"


@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_roles_have_title(loader: AgencyLoader, department: str) -> None:
    """Every role must have a non-empty title."""
    for r in loader.load_by_department(department):
        assert isinstance(r.title, str) and r.title.strip(), (
            f"{department}/{r.id}: empty title"
        )


@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_ids_are_unique_within_department(loader: AgencyLoader, department: str) -> None:
    """Two roles in the same department must never share an id slug."""
    ids = [r.id for r in loader.load_by_department(department)]
    assert len(ids) == len(set(ids)), f"{department}: duplicate ids found"


# ---------------------------------------------------------------------------
# Spare-pool semantics
# ---------------------------------------------------------------------------

def test_spare_pool_distinct_from_canonical_departments(loader: AgencyLoader) -> None:
    """The 15 spare experts must not overlap with any canonical department."""
    spare_ids = {r.id for r in loader.load_by_department("_spare_")}
    assert len(spare_ids) == 15
    canonical_ids = {r.id for d in DEPARTMENT_ORDER for r in loader.load_by_department(d)}
    assert spare_ids.isdisjoint(canonical_ids), (
        f"spare/canonical overlap: {sorted(spare_ids & canonical_ids)[:5]}"
    )
    assert len(canonical_ids) == sum(
        EXPECTED_DEPARTMENT_QUOTAS[d] for d in DEPARTMENT_ORDER
    )


# ---------------------------------------------------------------------------
# Capability matrix sanity per department
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("department", sorted(EXPECTED_DEPARTMENT_QUOTAS.keys()))
def test_each_department_contributes_to_capability_matrix(
    loader: AgencyLoader, department: str
) -> None:
    """For each department, every role's skills must appear in the matrix."""
    matrix = loader.get_capability_matrix()
    for r in loader.load_by_department(department):
        for skill in r.skills:
            assert r.id in matrix.get(skill, []), (
                f"{department}/{r.id}: skill {skill!r} not in capability matrix"
            )
