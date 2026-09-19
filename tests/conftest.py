import pytest

from sonoscribe.catalog import clear_library_cache
from sonoscribe.settings import clear_settings_cache
from sonoscribe.sync.keychain import reset_keychain_store, use_memory_keychain
from sonoscribe.scout import clear_scout_cache, set_brief_insert, set_brief_notice, set_runner
from sonoscribe.scout.tools import take_capture, take_queued_page


@pytest.fixture(autouse=True)
def isolate_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("SONOSCRIBE_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SONOSCRIBE_STATS", str(tmp_path / "stats.json"))
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "routines.json"))
    monkeypatch.setenv("SONOSCRIBE_SCOUT", str(tmp_path / "scout.json"))
    monkeypatch.setenv("SONOSCRIBE_KEYCHAIN", "memory")
    clear_settings_cache()
    clear_library_cache()
    clear_scout_cache()
    set_runner(None)
    set_brief_notice(None)
    set_brief_insert(None)
    take_queued_page()
    take_capture()
    reset_keychain_store()
    use_memory_keychain()
    yield
    clear_settings_cache()
    clear_library_cache()
    clear_scout_cache()
    set_runner(None)
    set_brief_notice(None)
    set_brief_insert(None)
    take_queued_page()
    take_capture()
    reset_keychain_store()
