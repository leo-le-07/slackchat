import re
from pathlib import Path

import slackchat.eval.review as review_module
from slackchat.core.prompts import parse_frontmatter
from slackchat.eval.review import DIMENSIONS, rubric_version

RUBRIC = Path(review_module.__file__).parent / "rubric.md"


def _rubric_text():
    meta, body = parse_frontmatter(RUBRIC.read_text(encoding="utf-8"))
    return meta, body


def test_rubric_is_versioned():
    meta, _ = _rubric_text()
    assert meta["version"] == "1"
    assert rubric_version() == "1"


def test_the_seven_dimensions_from_the_spec_are_present():
    assert DIMENSIONS["translation"] == ("Adequacy", "Naturalness", "Voice compliance", "Concision")
    assert DIMENSIONS["correction"] == ("Minimality", "Correctness", "Voice preservation")


def test_every_dimension_has_a_heading_in_the_rubric():
    _, body = _rubric_text()
    for dimensions in DIMENSIONS.values():
        for name in dimensions:
            assert f"### {name}" in body, name


def test_every_dimension_anchors_all_three_levels():
    _, body = _rubric_text()
    sections = re.split(r"^### ", body, flags=re.MULTILINE)[1:]
    assert len(sections) == 7
    for section in sections:
        for level in ("**0**", "**1**", "**2**"):
            assert level in section, section.splitlines()[0]


def test_every_level_carries_a_concrete_example():
    _, body = _rubric_text()
    sections = re.split(r"^### ", body, flags=re.MULTILINE)[1:]
    for section in sections:
        assert section.count("*Output:*") >= 3, section.splitlines()[0]


def test_the_tie_break_rule_is_stated():
    _, body = _rubric_text()
    assert "take the lower one" in body


def test_the_scale_is_zero_one_two_not_one_to_five():
    _, body = _rubric_text()
    assert "Scale: 0, 1, 2" in body
