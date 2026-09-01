from sonoscribe.commands import apply_commands
from sonoscribe.cleaner import clean, process


def test_strips_fillers_and_capitalizes() -> None:
    raw = "Um, I think, uh, we should, you know, ship this."
    assert clean(raw) == "I think, we should, ship this."


def test_keeps_like_as_content() -> None:
    assert clean("I like this") == "I like this"


def test_strips_artifacts_and_thanks() -> None:
    raw = "[BLANK_AUDIO] Hello there. Thanks for watching."
    assert clean(raw) == "Hello there."


def test_thank_you_only_is_empty() -> None:
    assert clean("Thank you.") == ""


def test_process_respects_toggle() -> None:
    raw = "Um hello"
    assert "Um" not in process(raw, remove_fillers=True)
    assert process(raw, remove_fillers=False) == "Um hello"


def test_domain_is_not_title_cased() -> None:
    assert clean("Google.com") == "google.com"
    assert clean("www.Google.com") == "www.google.com"


def test_domain_in_a_sentence_is_lowercased() -> None:
    assert clean("go to Google.com please") == "Go to google.com please"


def test_google_dot_com_command() -> None:
    assert apply_commands("google dot com") == "google.com"
    assert clean("google dot com") == "google.com"
    assert clean("www dot google dot com") == "www.google.com"


def test_spoken_punctuation() -> None:
    assert clean("hello comma world period") == "Hello, world."


def test_slash_in_url_path() -> None:
    assert clean("google.com slash maps") == "google.com/maps"


def test_new_line_command() -> None:
    assert apply_commands("hello new line world") == "hello\nworld"


def test_period_of_time_is_not_punctuation() -> None:
    assert "period of time" in apply_commands("a period of time").lower()
