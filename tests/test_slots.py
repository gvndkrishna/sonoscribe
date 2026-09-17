from sonoscribe.slots import (
    clean_pattern,
    conflict_key,
    fill,
    match_pattern,
    pattern_score,
    validate_pattern,
)


def test_clean_pattern_keeps_slots() -> None:
    phrase, errors = clean_pattern("Hello {1}")
    assert phrase == "hello {1}"
    assert errors == []
    phrase, errors = clean_pattern("note {*}")
    assert phrase == "note {*}"
    assert errors == []


def test_clean_pattern_rejects_malformed_slot() -> None:
    phrase, errors = clean_pattern("open {1")
    assert errors
    assert "{1" not in phrase


def test_phrase_cannot_start_with_slot() -> None:
    errors = validate_pattern("{1} save", set())
    assert any("cannot start" in err for err in errors)


def test_star_must_be_last() -> None:
    errors = validate_pattern("say {*} now", set())
    assert any("{*}" in err for err in errors)


def test_match_numbered_and_star() -> None:
    bound = match_pattern("open {1}", ["open", "safari"])
    assert bound == {"1": "safari"}
    bound = match_pattern("note {*}", ["note", "hello", "there"])
    assert bound == {"*": "hello there"}
    assert match_pattern("open {1}", ["save", "safari"]) is None


def test_match_named_slot() -> None:
    bound = match_pattern("insert {hello}", ["insert", "hello"], {"hello": "Greetings guys"})
    assert bound == {"hello": "Greetings guys"}
    assert match_pattern("insert {hello}", ["insert", "there"], {"hello": "Greetings guys"}) is None


def test_fill_star_expands_named_vars_but_numbered_stays_raw() -> None:
    names = {"hello": "Greetings guys"}
    assert fill("{*}", {"*": "hello there"}, names) == "Greetings guys there"
    assert fill("{1}", {"1": "hello"}, names) == "hello"
    assert fill("{hello}", {}, names) == "Greetings guys"
    assert fill("Dear {1},", {"1": "Ada"}, names) == "Dear Ada,"


def test_conflict_key_collapses_numbered_slots() -> None:
    assert conflict_key("open {1}") == conflict_key("open {2}")
    assert conflict_key("open {1}") != conflict_key("open {*}")
    assert pattern_score("insert {hello}") > pattern_score("insert {*}")
