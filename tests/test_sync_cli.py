from sonoscribe.sync.cli import (
    Destination,
    SyncError,
    _gcs_cp_args,
    _is_rapid_gcs_bucket,
    classify_error,
    download,
    friendly_error,
    login_command,
    object_key,
    probe_providers,
    upload,
)


def test_object_key_joins_prefix() -> None:
    assert object_key("") == "sonoscribe-sync.json"
    assert object_key("/library/") == "library/sonoscribe-sync.json"


def test_probe_missing_clis(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.sync.cli.which", lambda _name: None)
    probed = probe_providers()
    assert probed["aws"]["available"] is False
    assert "AWS CLI" in probed["aws"]["message"]
    assert probed["gcs"]["available"] is False
    assert probed["azure"]["available"] is False


def test_friendly_errors() -> None:
    assert "signed in" in friendly_error("aws", "Unable to locate credentials")
    assert "permission" in friendly_error("gcs", "AccessDenied: 403")
    assert "wasn’t found" in friendly_error("azure", "BlobNotFound")


def test_classify_auth_errors() -> None:
    message, kind = classify_error("gcs", "Please run gcloud auth login")
    assert kind == "auth"
    assert "signed in" in message
    _, kind = classify_error("aws", "ExpiredToken")
    assert kind == "auth"
    _, kind = classify_error("azure", "Please run 'az login'")
    assert kind == "auth"
    assert login_command("gcs") == ["gcloud", "auth", "login"]


def test_gcloud_empty_object_is_missing(monkeypatch) -> None:
    details = (
        "ERROR: (gcloud.storage.cp) The following URLs matched no objects or files:\n"
        "gs://sonoscribe-sync-bucket/sonoscribe-sync.json"
    )
    assert "wasn’t found" in friendly_error("gcs", details)

    def fake_run(provider: str, args: list[str]) -> None:
        raise SyncError(friendly_error(provider, details), details)

    monkeypatch.setattr("sonoscribe.sync.cli.which", lambda name: "/usr/bin/gcloud" if name == "gcloud" else None)
    monkeypatch.setattr("sonoscribe.sync.cli._run", fake_run)
    assert download(Destination("gcs", "sonoscribe-sync-bucket")) is None


def test_rapid_bucket_error_is_specific() -> None:
    details = (
        "Copying file:///tmp/sonoscribe-sync.json to gs://sonoscribe-sync-bucket/sonoscribe-sync.json\n"
        "ERROR: HTTPError 400: This bucket requires appendable objects."
    )
    message = friendly_error("gcs", details)
    assert "Rapid" in message
    assert "Region" in message


def test_rapid_bucket_metadata() -> None:
    assert _is_rapid_gcs_bucket({"default_storage_class": "RAPID", "location_type": "zone"})
    assert _is_rapid_gcs_bucket({"storageClass": "STANDARD", "locationType": "zone"})
    assert not _is_rapid_gcs_bucket({"default_storage_class": "STANDARD", "location_type": "region"})


def test_upload_rejects_rapid_gcs_bucket(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.sync.cli.which", lambda name: "/opt/homebrew/bin/gcloud" if name == "gcloud" else None)
    monkeypatch.setattr(
        "sonoscribe.sync.cli._gcs_bucket_describe",
        lambda _dest: {"default_storage_class": "RAPID", "location_type": "zone"},
    )

    def fail_run(*_args, **_kwargs):
        raise AssertionError("upload should not copy into a Rapid bucket")

    monkeypatch.setattr("sonoscribe.sync.cli._run", fail_run)
    try:
        upload(Destination("gcs", "sonoscribe-sync-bucket", project="demox-internal"), b"{}")
    except SyncError as exc:
        assert "Rapid" in exc.message
    else:
        raise AssertionError("expected SyncError")


def test_gcs_args_include_optional_project(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.sync.cli.which", lambda name: "/opt/homebrew/bin/gcloud" if name == "gcloud" else None)
    dest = Destination("gcs", "sonoscribe-sync-bucket", project="demox-internal")
    args = _gcs_cp_args(dest, "/tmp/local.json", "gs://sonoscribe-sync-bucket/sonoscribe-sync.json")
    assert args[:4] == ["/opt/homebrew/bin/gcloud", "--project", "demox-internal", "storage"]
    bare = _gcs_cp_args(Destination("gcs", "bucket"), "a", "b")
    assert "--project" not in bare


def test_upload_without_cli_is_calm(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.sync.cli.which", lambda _name: None)
    try:
        upload(Destination("aws", "bucket"), b"{}")
    except SyncError as exc:
        assert "AWS CLI" in exc.message
    else:
        raise AssertionError("expected SyncError")
