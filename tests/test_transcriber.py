from unittest.mock import patch

from huggingface_hub.errors import LocalEntryNotFoundError

from sonoscribe.transcriber import MODELS, resolve_model_path, worker_command


def test_worker_command_uses_module() -> None:
    cmd = worker_command("base")
    assert "-m" in cmd
    assert "sonoscribe" in cmd
    assert "--worker" in cmd
    assert "base" in cmd


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

