"""Unit tests for the MADR 4.0 renderer."""

from __future__ import annotations

from app.madr_template import MADR_REQUIRED_SECTIONS, render_madr


def _sample_form() -> dict:
    return {
        "title": "Use PostgreSQL as primary database",
        "status": "accepted",
        "date": "2026-04-12",
        "deciders": ["Architecture Committee"],
        "context": (
            "We need a transactional relational database that supports "
            "semi-structured JSON and full-text search, without introducing "
            "a new on-prem provider."
        ),
        "technologies": ["PostgreSQL", "Python"],
        "preliminary_decision": "Managed PostgreSQL (RDS / Cloud SQL)",
        "options_to_evaluate": [
            "Managed PostgreSQL (RDS / Cloud SQL)",
            "MySQL 8",
            "CockroachDB",
        ],
    }


def test_render_madr_starts_with_frontmatter():
    md = render_madr(_sample_form())
    assert md.startswith("---"), "ADR must start with YAML frontmatter delimiter"
    # Second `---` closes the frontmatter
    end = md.find("\n---", 3)
    assert end != -1, "Frontmatter must be closed by a second `---` line"


def test_render_madr_contains_required_sections():
    md = render_madr(_sample_form())
    missing = [s for s in MADR_REQUIRED_SECTIONS if s not in md]
    assert not missing, f"Missing required sections: {missing}"


def test_render_madr_frontmatter_fields():
    md = render_madr(_sample_form())
    assert 'title: "Use PostgreSQL as primary database"' in md
    assert 'status: "accepted"' in md
    assert 'date: "2026-04-12"' in md
    assert "- \"Architecture Committee\"" in md
    assert "- \"PostgreSQL\"" in md


def test_render_madr_with_no_options_falls_back_to_preliminary():
    data = _sample_form()
    data["options_to_evaluate"] = []
    md = render_madr(data)
    # The Considered Options section should still exist and mention the decision
    assert "## Considered Options" in md
    assert data["preliminary_decision"] in md


def test_render_madr_uses_default_deciders_when_missing():
    data = _sample_form()
    data.pop("deciders")
    md = render_madr(data)
    assert "Architecture Committee" in md


def test_render_madr_includes_pros_cons_structure():
    md = render_madr(_sample_form())
    # Even with the default fallback renderer, the Pros and Cons section
    # must contain the Bueno/Malo markers.
    assert "## Pros and Cons of the Options" in md
    assert "**Bueno**" in md
    assert "**Malo**" in md


def test_render_madr_handles_special_characters_in_title():
    data = _sample_form()
    data["title"] = 'Use "PostgreSQL" for our OLTP workloads'
    md = render_madr(data)
    assert md.startswith("---")
    # The title's embedded double quotes must be escaped in YAML
    assert 'title: "Use \\"PostgreSQL\\" for our OLTP workloads"' in md


def test_render_madr_uses_today_when_date_missing():
    data = _sample_form()
    data.pop("date")
    md = render_madr(data)
    # Should default to today's ISO date (YYYY-MM-DD, length 10).
    import re
    m = re.search(r'date: "(\d{4}-\d{2}-\d{2})"', md)
    assert m is not None
    assert len(m.group(1)) == 10


def test_render_madr_yaml_escapes_dangerous_characters():
    """Strings with YAML-significant characters must round-trip via yaml.safe_load.

    M1 hardening: we escape `* & ! | > # % @ ` [ ] { } : ?` plus
    leading `-`/`?` so a malformed/hostile frontmatter can't break the
    parser downstream.
    """
    import yaml

    data = _sample_form()
    data["title"] = 'Use "PostgreSQL" with @flags & [more]'
    data["technologies"] = [
        "-leading-dash",
        "with:colon",
        "with?question",
        "with*asterisk",
        "with&ampersand",
        "with!exclaim",
        "with|pipe",
        "with>gt",
        "with#hash",
        "with%percent",
        "with@at",
        "with`tick",
        "with[bracket]",
        "with{brace}",
    ]
    md = render_madr(data)

    front = md.split("---", 2)[1]
    parsed = yaml.safe_load(front)
    # Title round-trips intact.
    assert parsed["title"] == data["title"]
    # Every tech entry round-trips intact (no structural damage).
    assert parsed["technologies"] == data["technologies"]