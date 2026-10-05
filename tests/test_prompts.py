import hashlib

import pytest

from slackchat.core.prompts import (
    VOICE_PLACEHOLDER,
    load_prompt,
    parse_frontmatter,
)


def test_parse_frontmatter_splits_metadata_from_body():
    meta, body = parse_frontmatter("---\nversion: 3\n---\nhello\nworld\n")
    assert meta == {"version": "3"}
    assert body == "hello\nworld"


def test_parse_frontmatter_tolerates_a_file_without_it():
    meta, body = parse_frontmatter("just a body\n")
    assert meta == {}
    assert body == "just a body"


@pytest.mark.parametrize("mode", ["correction", "translation"])
def test_placeholder_is_resolved(mode):
    prompt = load_prompt(mode)
    assert VOICE_PLACEHOLDER not in prompt.text
    assert "No em-dash" in prompt.text  # the voice body really got inlined
    assert prompt.mode == mode


def test_version_comes_from_the_template_file():
    assert load_prompt("correction").version == "2"


def test_hash_is_twelve_hex_chars_of_sha256_of_the_resolved_text():
    prompt = load_prompt("correction")
    assert len(prompt.hash) == 12
    assert prompt.hash == hashlib.sha256(prompt.text.encode("utf-8")).hexdigest()[:12]


def test_hash_differs_between_modes():
    assert load_prompt("correction").hash != load_prompt("translation").hash


def test_hash_is_stable_across_calls():
    assert load_prompt("correction").hash == load_prompt("correction").hash


def test_editing_the_voice_body_changes_the_hash(tmp_path):
    # This is the whole point of storing a hash next to a hand-bumped version.
    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe terse.\n", encoding="utf-8")
    (tmp_path / "correction.md").write_text(
        "---\nversion: 1\n---\nFix errors.\n\n{{VOICE}}\n", encoding="utf-8"
    )
    first = load_prompt("correction", prompts_dir=tmp_path)

    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe very terse.\n", encoding="utf-8")
    second = load_prompt("correction", prompts_dir=tmp_path)

    assert first.version == second.version == "1"
    assert first.hash != second.hash


def test_missing_placeholder_is_an_error(tmp_path):
    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe terse.\n", encoding="utf-8")
    (tmp_path / "correction.md").write_text("---\nversion: 1\n---\nFix errors.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="\\{\\{VOICE\\}\\}"):
        load_prompt("correction", prompts_dir=tmp_path)


def test_correction_prompt_forbids_introducing_banned_punctuation():
    text = load_prompt("correction").text
    assert "Never introduce an em dash or a semicolon" in text


def test_translation_prompt_forbids_adding_information():
    assert "Add nothing that is not there." in load_prompt("translation").text
