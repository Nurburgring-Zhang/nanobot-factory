"""Shared fixtures for builtin skill tests.

Imports the skills package and provides helpers for constructing
SkillContext instances with mock LLM where needed.
"""
import sys
from pathlib import Path
import pytest

# Ensure backend/ is on sys.path so `import skills` works
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture
def skill_ctx():
    """Build a SkillContext with arbitrary inputs; let each test set its own."""
    from skills.context import SkillContext
    return SkillContext.create(user_id="tester", project_id="test_proj")


@pytest.fixture
def make_ctx():
    """Factory: SkillContext.create with custom inputs."""
    from skills.context import SkillContext

    def _make(inputs=None, **kwargs):
        return SkillContext.create(
            user_id=kwargs.get("user_id", "tester"),
            project_id=kwargs.get("project_id", "test_proj"),
            inputs=inputs or {},
        )

    return _make