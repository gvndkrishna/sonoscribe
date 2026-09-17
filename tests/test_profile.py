from sonoscribe.profile import clean_username, username_error, usernames_match


def test_username_is_chosen_not_os() -> None:
    assert clean_username("  studio.mac  ") == "studio.mac"
    assert username_error("") == "Username required."
    assert username_error("a") is not None
    assert username_error("ok_user") is None
    assert username_error("has space") is not None


def test_usernames_match_casefold() -> None:
    assert usernames_match("Studio", "studio")
    assert not usernames_match("studio", "other")
    assert not usernames_match("", "studio")
