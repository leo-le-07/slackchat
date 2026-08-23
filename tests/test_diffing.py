from slackchat.core.diffing import diff_words, tokenize, word_count


def test_tokenize_splits_on_whitespace_only():
    assert tokenize("Hi a @ka, is that okay?") == ["Hi", "a", "@ka,", "is", "that", "okay?"]
    assert tokenize("  spaced \n out  ") == ["spaced", "out"]
    assert tokenize("") == []


def test_identical_text_is_all_equal_and_zero_ratio():
    changes, ratio = diff_words("The deployment failed.", "The deployment failed.")
    assert ratio == 0.0
    assert [c.kind for c in changes] == ["equal"]
    assert changes[0].before == "The deployment failed."


def test_two_word_fix_in_a_six_word_sentence():
    changes, ratio = diff_words(
        "I has finish the task yesterday.", "I finished the task yesterday."
    )
    assert [c.kind for c in changes] == ["equal", "replace", "equal"]
    assert changes[1].before == "has finish"
    assert changes[1].after == "finished"
    # replace of 2 tokens by 1 counts as max(2, 1) = 2 changed, over 6 input tokens
    assert ratio == 0.3333


def test_pure_insertion_counts_inserted_tokens():
    changes, ratio = diff_words("Deploy done", "Deploy is done")
    assert [c.kind for c in changes] == ["equal", "insert", "equal"]
    assert changes[1].before == ""
    assert changes[1].after == "is"
    assert ratio == 0.5  # 1 inserted / 2 input tokens


def test_pure_deletion_counts_deleted_tokens():
    changes, ratio = diff_words("Deploy is really done", "Deploy is done")
    assert [c.kind for c in changes] == ["equal", "delete", "equal"]
    assert changes[1].before == "really"
    assert changes[1].after == ""
    assert ratio == 0.25


def test_ratio_can_exceed_one_when_output_balloons():
    _, ratio = diff_words("hello", "Greetings and salutations to you my friend")
    assert ratio == 7.0


def test_empty_original_with_output_is_ratio_one():
    _, ratio = diff_words("", "something appeared")
    assert ratio == 1.0


def test_both_empty_is_ratio_zero():
    changes, ratio = diff_words("", "")
    assert changes == []
    assert ratio == 0.0


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0
