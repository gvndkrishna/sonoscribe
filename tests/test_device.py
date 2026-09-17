from sonoscribe.device import ensure_device, is_alias_of, this_device


def test_ensure_device_uses_hardware_serial_as_id(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.device.hardware_serial", lambda: "C02SERIAL01")
    settings = {"device": {"id": "dev-abcdef123456", "serial": "old", "name": "Studio"}}
    assert ensure_device(settings) is True
    assert settings["device"]["id"] == "C02SERIAL01"
    assert settings["device"]["serial"] == "C02SERIAL01"
    assert settings["device"]["name"] == "Studio"
    assert settings["device"]["previous_ids"] == ["dev-abcdef123456"]


def test_ensure_device_keeps_generated_id_without_hardware(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.device.hardware_serial", lambda: "")
    settings = {"device": {"id": "dev-abcdef123456", "serial": "", "name": "Desk"}}
    ensure_device(settings)
    assert settings["device"]["id"] == "dev-abcdef123456"
    assert settings["device"]["serial"] == "dev-abcdef123456"
    assert settings["device"]["name"] == "Desk"


def test_this_device_exposes_serial(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.device.hardware_serial", lambda: "C02SERIAL01")
    device = this_device({"device": {"name": "Studio Mac"}})
    assert device["id"] == "C02SERIAL01"
    assert device["serial"] == "C02SERIAL01"
    assert device["name"] == "Studio Mac"


def test_generated_id_with_same_name_is_alias(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.device.hardware_serial", lambda: "C02SERIAL01")
    this = this_device({"device": {"name": "H7T46T609N"}})
    ghost = {"id": "dev-99b7193939a6", "serial": "dev-99b7193939a6", "name": "H7T46T609N"}
    assert is_alias_of(ghost, this) is True
    other = {"id": "dev-aaaaaaaaaaaa", "serial": "dev-aaaaaaaaaaaa", "name": "Other Mac"}
    assert is_alias_of(other, this) is False
