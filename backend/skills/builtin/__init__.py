"""P4-8-W1: Built-in skills — 10 official skills inspired by open-source.

Each skill is a single class decorated with ``@skill(...)``.  When this
package is imported, every skill auto-registers into :data:`SKILL_REGISTRY`.

Skill roster
------------
1.  ``guizang_ppt``            (content)     — idea → PPT outline + slides
2.  ``guizang_social_card``    (content)     — text → social card deck
3.  ``awesome_gpt_image``      (image)       — AI image prompt library
4.  ``humanizer_zh``           (content)     — AI-voice → human-voice (zh)
5.  ``deep_research``          (research)    — cited deep research
6.  ``anything_to_notebooklm`` (research)    — source → multi-format summary
7.  ``wewrite``                (content)     — public-account writing one-stop
8.  ``youtube_clipper``        (video)       — long-video → short clips
9.  ``oh_story_claudecode``    (content)     — web-novel topic mining
10. ``marketingskills``        (marketing)   — marketing toolkit
"""

from . import (  # noqa: F401  -- register by side-effect
    guizang_ppt,
    guizang_social_card,
    awesome_gpt_image,
    humanizer_zh,
    deep_research,
    anything_to_notebooklm,
    wewrite,
    youtube_clipper,
    oh_story_claudecode,
    marketingskills,
)


def all_skill_names() -> list[str]:
    return [
        "guizang_ppt",
        "guizang_social_card",
        "awesome_gpt_image",
        "humanizer_zh",
        "deep_research",
        "anything_to_notebooklm",
        "wewrite",
        "youtube_clipper",
        "oh_story_claudecode",
        "marketingskills",
    ]


__all__ = ["all_skill_names"]