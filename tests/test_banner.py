from slackchat.cli.banner import (
    GLYPH_HEIGHT,
    GLYPH_WIDTH,
    GLYPHS,
    HINT,
    WORDMARK,
    banner,
    render_word,
)


def test_every_wordmark_letter_has_a_glyph():
    assert set(WORDMARK) <= set(GLYPHS)


def test_every_glyph_is_rectangular():
    for letter, rows in GLYPHS.items():
        assert len(rows) == GLYPH_HEIGHT, letter
        assert {len(r) for r in rows} == {GLYPH_WIDTH}, letter


def test_render_word_of_a_single_letter_is_that_glyph():
    assert render_word("T") == "\n".join(GLYPHS["T"])


def test_render_word_joins_letters_with_one_space_column():
    rendered = render_word("TT").splitlines()
    assert len(rendered) == GLYPH_HEIGHT
    assert rendered[0] == GLYPHS["T"][0] + " " + GLYPHS["T"][0]


def test_wordmark_lines_are_all_the_same_width():
    lines = render_word(WORDMARK).splitlines()
    assert len(lines) == GLYPH_HEIGHT
    expected = len(WORDMARK) * GLYPH_WIDTH + (len(WORDMARK) - 1)
    assert {len(line) for line in lines} == {expected}


def test_render_word_is_case_insensitive():
    assert render_word("slackchat") == render_word("SLACKCHAT")


def test_banner_includes_the_hint():
    assert HINT in banner(color=False)
    assert "Ctrl+D" in HINT


def test_banner_without_colour_has_no_escape_codes():
    assert "\x1b" not in banner(color=False)


def test_banner_with_colour_dims_the_hint():
    assert "\x1b[2m" in banner(color=True)


def test_banner_adds_no_dependency():
    import slackchat.cli.banner as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "import " in source  # sanity: the file parses as a module
    for forbidden in ("pyfiglet", "art", "rich"):
        assert forbidden not in source
