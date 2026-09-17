from unittest.mock import patch

from huggingface_hub.errors import LocalEntryNotFoundError

from sonoscribe.transcriber import (
    MODELS,
    TranscribeError,
    Transcriber,
    clean_model,
    friendly_load_error,
    local_model_error,
    resolve_model_path,
    worker_command,
)


def test_worker_command_uses_module() -> None:
    cmd = worker_command("base")
    assert "-m" in cmd
    assert "sonoscribe" in cmd
    assert "--worker" in cmd
    assert "base" in cmd


def test_worker_command_uses_local_path() -> None:
    cmd = worker_command("custom-1", "/tmp/whisper")
    assert "--model-path" in cmd
    assert "/tmp/whisper" in cmd
    assert "--model" not in cmd


def test_models_cover_cli_choices() -> None:
    assert set(MODELS) == {"large-v3-turbo", "small", "base"}


def test_resolve_model_path_uses_cache_when_present() -> None:
    with patch(
        "huggingface_hub.snapshot_download",
        return_value="/cache/whisper",
    ) as download:
        assert resolve_model_path("mlx-community/whisper-base") == "/cache/whisper"
        download.assert_called_once_with(
            repo_id="mlx-community/whisper-base",
            local_files_only=True,
        )


def test_resolve_model_path_downloads_when_cache_missing() -> None:
    def fake_download(repo_id, local_files_only=False):
        if local_files_only:
            raise LocalEntryNotFoundError("missing")
        return "/downloaded/whisper"

    with patch("huggingface_hub.snapshot_download", side_effect=fake_download) as download:
        assert resolve_model_path("mlx-community/whisper-base") == "/downloaded/whisper"
        assert download.call_count == 2
        assert download.call_args_list[0].kwargs["local_files_only"] is True
        assert download.call_args_list[1].kwargs.get("local_files_only", False) is False


def test_clean_model_falls_back() -> None:
    assert clean_model("small") == "small"
    assert clean_model("nope") == "large-v3-turbo"


def test_set_model_rejects_unknown() -> None:
    transcriber = Transcriber("base")
    try:
        transcriber.set_model("tiny")
    except TranscribeError as exc:
        assert "tiny" in str(exc)
    else:
        raise AssertionError("expected TranscribeError")
    assert transcriber.model_key == "base"


def test_set_model_reloads_and_restores(monkeypatch) -> None:
    transcriber = Transcriber("base")
    loads: list[str] = []

    def fake_load() -> None:
        loads.append(transcriber.model_key)
        if transcriber.model_key == "small":
            raise TranscribeError("boom")

    monkeypatch.setattr(transcriber, "_load_locked", fake_load)
    transcriber.set_model("large-v3-turbo")
    assert transcriber.model_key == "large-v3-turbo"
    assert loads == ["large-v3-turbo"]
    try:
        transcriber.set_model("small")
    except TranscribeError:
        pass
    else:
        raise AssertionError("expected TranscribeError")
    assert transcriber.model_key == "large-v3-turbo"
    assert loads == ["large-v3-turbo", "small", "large-v3-turbo"]


def test_friendly_load_error_hides_hub_401() -> None:
    message = friendly_load_error("RepositoryNotFoundError: 401 Invalid username or password.")
    assert "401" not in message
    assert "local" in message.lower()


def test_local_model_error_requires_config_and_weights(tmp_path) -> None:
    folder = tmp_path / "whisper"
    folder.mkdir()
    assert local_model_error(str(folder))
    (folder / "config.json").write_text("{}", encoding="utf-8")
    assert local_model_error(str(folder))
    (folder / "weights.npz").write_bytes(b"x")
    assert local_model_error(str(folder)) is None

