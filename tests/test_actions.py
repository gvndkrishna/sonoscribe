from sonoscribe.actions import (
    BACKSPACE,
    DELETE_WORD,
    ENTER,
    SCRATCH,
    last_sentence_chars,
    match_action,
    trim_last_word,
)
from sonoscribe.lexicon import correct_product_name


def test_enter_alone_is_command() -> None:
    assert match_action("enter") == ENTER
    assert match_action("Enter.") == ENTER
    assert match_action("  ENTER  ") == ENTER


def test_fluent_enter_is_not_a_command() -> None:
    assert match_action("you may enter") is None
    assert match_action("google.com enter") is None


def test_scratch_that() -> None:
    assert match_action("scratch that") == SCRATCH
    assert match_action("undo that") == SCRATCH


def test_delete_last_word() -> None:
    assert match_action("delete last word") == DELETE_WORD
    assert match_action("hello delete last word") is None


def test_backspace() -> None:
    assert match_action("backspace") == BACKSPACE
    assert match_action("hello backspace") is None


def test_please_return_the_item_is_not_a_command() -> None:
    assert match_action("please return the item") is None


def test_empty_is_not_a_command() -> None:
    assert match_action("") is None
    assert match_action("   ") is None


def test_last_sentence_chars() -> None:
    assert last_sentence_chars("Hi. There.") == len("There.") + 1
    assert last_sentence_chars("Hello") == len("Hello")


def test_trim_last_word() -> None:
    assert trim_last_word("hello world") == "hello"
    assert trim_last_word("hello") == ""


def test_product_name_aliases() -> None:
    assert correct_product_name("sono scribe") == "Sonoscribe"
    assert correct_product_name("use sunoscribe please") == "use Sonoscribe please"
    assert correct_product_name("SONOSCRIBE") == "Sonoscribe"
    assert correct_product_name("scribe enter") == "scribe enter"
