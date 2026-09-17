import sys

from sonoscribe.runtime import in_app_bundle, package_dir, resource_path


def test_in_app_bundle_detects_macos_layout(tmp_path, monkeypatch) -> None:
    macos = tmp_path / "Sonoscribe.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    exe = macos / "sonoscribe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    assert in_app_bundle()


def test_in_app_bundle_false_for_plain_binary(tmp_path, monkeypatch) -> None:
    exe = tmp_path / "sonoscribe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    assert not in_app_bundle()


def test_in_app_bundle_false_for_missing_contents(tmp_path, monkeypatch) -> None:
    fake_app = tmp_path / "Sonoscribe.app" / "MacOS"
    fake_app.mkdir(parents=True)
    exe = fake_app / "sonoscribe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    assert not in_app_bundle()


def test_resource_path_is_inside_package() -> None:
    assert package_dir().name == "sonoscribe"
    assert resource_path("StatusItem.png").is_file()
    assert resource_path("StatusItem@2x.png").is_file()
