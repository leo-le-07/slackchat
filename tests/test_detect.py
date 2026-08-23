import pytest

from slackchat.core.detect import detect

VIETNAMESE = [
    "Tôi đã hoàn thành task hôm qua.",
    "Cà phê ở đây ngon.",
    "Em gửi anh bản cập nhật.",
    "Mai họp lúc 3 giờ nhé",
    "Kiều Anh sẽ review lại",
    "Số liệu này chưa khớp",
    "Cà phê sáng nay hơi đắng",
    "À, tôi hiểu rồi",
    # Vietnamese sentence that also contains an English loanword
    "Tôi đi café với Linh.",
]

ENGLISH = [
    "The deployment failed because the config was missing.",
    "I has finish the task yesterday.",
    # Unaccented Vietnamese-looking English is still treated as English:
    # the user commits to always typing Vietnamese with diacritics.
    "Anh oi, minh can them mot seat nua.",
    "Vui long kiem tra lai",
    # Accented English loanwords must not trip detection
    "Let's meet at the café after standup.",
    "Please attach your résumé and a short cliché-free intro.",
    "That is a naïve assumption about the façade.",
    "We had déjà vu over the crème brûlée invoice.",
    "Order à la carte, not the set menu.",
    "The rôle of the protégé is unclear.",
]


@pytest.mark.parametrize("text", VIETNAMESE)
def test_vietnamese_routes_to_translation(text):
    assert detect(text) == "translation"


@pytest.mark.parametrize("text", ENGLISH)
def test_english_routes_to_correction(text):
    assert detect(text) == "correction"


def test_decomposed_diacritics_are_normalised():
    # "Tôi" written as T + o + combining circumflex + i
    assert detect("Tôi đã xong") == "translation"


def test_empty_and_whitespace_default_to_correction():
    assert detect("") == "correction"
    assert detect("   \n ") == "correction"


def test_exclusive_letter_alone_is_decisive():
    # A single 'đ' is proof enough, no allowlist consultation
    assert detect("đ") == "translation"
