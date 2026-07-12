"""V5.1 (P21 P2 P4) — imdf Skill composition helper (R2 audit N5).

Provides a minimal ``chain()`` helper + ``PipelineStep`` dataclass so that
multiple imdf skills can be composed sequentially::

    a -> b -> c

where each step's ``SkillOutput.result`` is fed (after an optional
``extract`` transform) into the next step's ``SkillInput.params`` via
an optional ``inject`` transform.  This is the unblocker for the
``clean_pii_remove -> synth_translate_en`` (and similar) chains
documented as the headline R2 P0 finding N5.

Design notes
------------
* Minimal surface — no third-party deps.  Stdlib only.
* ``PipelineStep`` is a ``@dataclass`` (frozen=False) so users can build
  a step in one expression and chain them with ``chain([step_a, step_b])``.
* Default ``extract`` reads ``SkillOutput.result`` if present, else
  returns the whole output — making the default behaviour
  "what-the-previous-skill-returned flows straight to the next skill".
* Default ``inject`` wraps the extracted value in
  ``SkillInput(params={"input": value})`` — matching the convention used
  by the existing imdf skill ``*Input`` models that read
  ``input.params["input"]`` (e.g. ``PiiRemoveInput`` takes ``text`` but
  the chain is a generic helper — callers customise via ``inject``).
* ``chain`` is async, mirrors the existing imdf skill signature
  ``async def skill(input: SkillInput) -> SkillOutput``, and returns
  the list of every step's output (so callers can inspect intermediates
  or surface the last ``SkillOutput``).
* On error: the exception propagates.  Earlier successful results are
  visible to the caller via the exception's ``__cause__`` / by capturing
  the list before the raise — see test ``test_error_middle_step_keeps_earlier_results``.

Examples
--------
Direct (no extract/inject overrides)::

    chain([
        PipelineStep("upper", upper_skill),
        PipelineStep("shout", shout_skill),
    ], initial=SkillInput(params={"input": "hi"}))

Custom extract/inject — pass the previous result's nested dict straight
into the next skill's typed params::

    PipelineStep(
        name="translate",
        func=translate_en,
        extract=lambda out: out.result["translation"],
        inject=lambda x, _: SkillInput(params={"text": x}),
    )

Caveat
------
This module does **not** fix the upstream Pydantic v2 model_rebuild
blocker (N1, fixed in P2 P1) or the ``imdf.creative`` import blocker
in ``backend.imdf/skills/__init__.py`` (a separate P0 / N6 from R2).
The helper is usable today via direct import::

    from backend.imdf.skills.compose import chain, PipelineStep

and via the package-level re-export (which works once the upstream
``imdf.creative`` import blocker is resolved).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List

from backend.skills import SkillInput, SkillOutput


@dataclass
class PipelineStep:
    """One step in a skill composition chain.

    Attributes:
        name: Human-readable label (used in logs / error messages).
        func: The async ``async (SkillInput) -> SkillOutput`` callable
            to run for this step.  Must be awaitable.
        extract: ``(SkillOutput) -> Any`` — pull the value the next step
            should receive.  Default reads ``SkillOutput.result`` (the
            field is always present on the dataclass, even if ``None``).
        inject: ``(Any, SkillInput) -> SkillInput`` — build the next
            step's input.  Default wraps the extracted value as
            ``SkillInput(params={"input": value})``.
    """
    name: str
    func: Callable[..., "object"]  # ``async (SkillInput) -> SkillOutput``
    extract: Callable[[SkillOutput], Any] = field(
        default_factory=lambda: _default_extract
    )
    inject: Callable[[Any, SkillInput], SkillInput] = field(
        default_factory=lambda: _default_inject
    )


def _default_extract(out: SkillOutput) -> Any:
    """Default extractor — return ``out.result`` if present, else the output itself."""
    if hasattr(out, "result"):
        return out.result
    return out


def _default_inject(value: Any, _previous: SkillInput) -> SkillInput:
    """Default injector — wrap ``value`` in ``SkillInput(params={"input": value})``."""
    return SkillInput(params={"input": value})


async def chain(
    skills: List[PipelineStep],
    initial: SkillInput,
) -> List[SkillOutput]:
    """Run ``skills`` sequentially.  Output of step N becomes input of step N+1.

    Args:
        skills: Ordered list of ``PipelineStep``.  Must be non-empty.
        initial: The ``SkillInput`` to feed into the first step.

    Returns:
        List of every step's ``SkillOutput`` in the same order as
        ``skills``.  ``results[-1]`` is the chain's final result.

    Raises:
        TypeError: If any step's ``func`` is not awaitable, or if
            ``skills`` is not a list of ``PipelineStep``.
        Any exception raised by a step's ``func`` propagates to the
        caller.  The chain does **not** silently swallow errors.  The
        caller can still recover partial results by re-running the
        chain (each step is pure relative to its input) or by wrapping
        individual steps in their own try/except inside a custom
        ``PipelineStep.func``.

    Notes:
        The default extract/inject pair treats ``SkillOutput.result`` as
        the value to forward and wraps it as ``{"input": value}`` for
        the next step.  For most typed imdf skills that read
        ``input.params["text"]`` or ``input.params["url"]``, supply
        custom ``extract``/``inject`` lambdas.
    """
    if not isinstance(skills, list) or not skills:
        raise TypeError(
            "chain() requires a non-empty list of PipelineStep (got "
            f"{type(skills).__name__} of length "
            f"{len(skills) if isinstance(skills, list) else '?'})"
        )

    results: List[SkillOutput] = []
    current: SkillInput = initial

    for step in skills:
        if not isinstance(step, PipelineStep):
            raise TypeError(
                f"chain() expects PipelineStep, got {type(step).__name__}: {step!r}"
            )

        out = await step.func(current)
        results.append(out)

        extracted = step.extract(out)
        current = step.inject(extracted, current)

    return results


__all__ = ["PipelineStep", "chain"]
