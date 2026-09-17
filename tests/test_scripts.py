import pytest

from sonoscribe.scripts import ScriptError, looks_like_bundle_id, run_script, runtime_for_path


def test_looks_like_bundle_id() -> None:
    assert looks_like_bundle_id("com.apple.Safari")
    assert looks_like_bundle_id("org.mozilla.firefox")
    assert not looks_like_bundle_id("Safari")
    assert not looks_like_bundle_id("Notes")


def test_runtime_for_path() -> None:
    assert runtime_for_path("/tmp/hello.applescript") == "applescript"
    assert runtime_for_path("/tmp/hello.sh") == "bash"


def test_rejects_elevated_bash() -> None:
    with pytest.raises(ScriptError):
        run_script("bash", body="sudo rm -rf /")


def test_rejects_admin_applescript() -> None:
    with pytest.raises(ScriptError):
        run_script(
            "applescript",
            body='do shell script "echo hi" with administrator privileges',
        )
