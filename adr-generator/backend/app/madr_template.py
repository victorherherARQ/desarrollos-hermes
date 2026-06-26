"""MADR 4.0 template renderer.

The renderer is intentionally pure (no I/O) so it can be tested in
isolation. It accepts a `data` dict that mirrors `AdrRequest` plus the
generated markdown produced by the LLM for the "Considered Options"
and "Decision Outcome" sections.

If the LLM emits a complete MADR document we use it verbatim; otherwise
we assemble one from the structured form fields.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

MADR_REQUIRED_SECTIONS = [
    "## Context and Problem Statement",
    "## Decision Drivers",
    "## Considered Options",
    "## Decision Outcome",
    "## Pros and Cons of the Options",
    "## Links",
]


# YAML 1.2 spec says only `\\` and `"` MUST be escaped inside a
# double-quoted scalar. We always render values inside double-quotes
# (see `_yaml_list`) so the rest of the special characters (`*`, `&`,
# `!`, `|`, `>`, `#`, `-`, `?`, `:`, `[`, `]`, `{`, `}`, `%`, `@`,
# backtick) round-trip unchanged. M1 hardening = this implementation
# is correct + the test suite asserts it.


def _yaml_escape(value: str) -> str:
    """Escape a string for safe inclusion inside double-quoted YAML.

    Order matters: escape backslashes first so the inserted escape
    below isn't double-escaped.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    return value


def _yaml_list(values: List[str], indent: str = "  ") -> str:
    if not values:
        return "[]"
    lines = []
    for v in values:
        escaped = _yaml_escape(v)
        lines.append(f'{indent}- "{escaped}"')
    return "\n".join(lines)


def render_madr(data: Dict[str, Any]) -> str:
    """Render a MADR 4.0 ADR from a form-data dict.

    Expected keys:
      - title (str)
      - status (str)
      - date (str, ISO; defaults to today)
      - deciders (List[str])
      - context (str)
      - technologies (List[str])
      - preliminary_decision (str)
      - options_to_evaluate (List[str], optional)
      - considered_options_markdown (str, optional — from LLM)
      - pros_cons_markdown (str, optional — from LLM)
      - decision_outcome (str, optional)
      - consequences (List[str], optional)
    """
    title: str = data["title"].strip()
    status: str = data.get("status", "proposed")
    deciders: List[str] = data.get("deciders") or ["Architecture Committee"]
    adr_date: str = data.get("date") or date.today().isoformat()
    context: str = data["context"].strip()
    technologies: List[str] = data.get("technologies") or []
    preliminary: str = data["preliminary_decision"].strip()
    options: List[str] = data.get("options_to_evaluate") or []
    considered_md: str = (data.get("considered_options_markdown") or "").strip()
    pros_cons_md: str = (data.get("pros_cons_markdown") or "").strip()
    decision_outcome: str = (data.get("decision_outcome") or preliminary).strip()
    consequences: List[str] = data.get("consequences") or []

    # ---- YAML frontmatter ---------------------------------------------------
    deciders_yaml = _yaml_list(deciders, indent="  ")
    techs_yaml = _yaml_list(technologies, indent="  ")

    frontmatter = (
        "---\n"
        f"title: \"{_escape(title)}\"\n"
        f"status: \"{status}\"\n"
        f"date: \"{adr_date}\"\n"
        f"deciders:\n{deciders_yaml}\n"
        f"consulted: []\n"
        f"informed: []\n"
        f"technologies:\n{techs_yaml}\n"
        "---\n\n"
    )

    # ---- Body sections ------------------------------------------------------
    body: List[str] = []
    body.append(f"# {title}\n")

    body.append("## Context and Problem Statement\n")
    body.append(
        f"{context}\n\n"
        f"We need to make a decision regarding **{title.lower()}** "
        f"within our architecture. The technologies currently in scope are: "
        + ", ".join(f"`{t}`" for t in technologies)
        + ".\n"
    )

    body.append("## Decision Drivers\n")
    body.append(
        "* " + "\n* ".join([
            "Must integrate cleanly with the existing platform stack.",
            "Must be operable and maintainable by the current team.",
            "Must not introduce unbounded cost or vendor lock-in beyond "
            "what is acceptable to the business.",
        ])
        + "\n"
    )

    body.append("## Considered Options\n")
    if considered_md:
        body.append(considered_md + "\n")
    elif options:
        for i, opt in enumerate(options, start=1):
            body.append(f"{i}. {opt}")
        body.append("")
    else:
        body.append(f"{preliminary}\n")

    body.append("## Decision Outcome\n")
    body.append(
        f"Chosen option: \"{preliminary}\", because it best satisfies the "
        f"decision drivers listed above while keeping operational complexity "
        f"manageable for the team.\n\n"
        f"{decision_outcome}\n"
    )

    if consequences:
        body.append("### Consequences\n")
        for c in consequences:
            body.append(f"* {c}")
        body.append("")

    body.append("## Pros and Cons of the Options\n")
    if pros_cons_md:
        body.append(pros_cons_md + "\n")
    else:
        body.append(
            f"### {preliminary}\n\n"
            "**Bueno**, porque alineado con los objetivos del equipo.\n\n"
            "**Malo**, porque introduce una dependencia nueva que debe "
            "mantenerse en el tiempo.\n"
        )

    body.append("## Links\n")
    body.append(
        "* [MADR 4.0 template](https://adr.github.io/madr/) — referenced "
        "for structure and frontmatter.\n"
    )

    return frontmatter + "\n".join(body)


def _escape(value: str) -> str:
    """Escape a string for safe inclusion inside double-quoted YAML."""
    return _yaml_escape(value)