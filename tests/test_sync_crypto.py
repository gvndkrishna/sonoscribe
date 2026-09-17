import pytest

from sonoscribe.sync.crypto import (
    CryptoError,
    decrypt,
    encrypt,
    fingerprint,
    generate_keypair,
    public_pem_from_private,
)


def test_hybrid_roundtrip() -> None:
    private_pem, public_pem = generate_keypair()
    box = encrypt(public_pem, b'{"ok": true}')
    assert decrypt(private_pem, box) == b'{"ok": true}'
    assert fingerprint(private_pem) == fingerprint(public_pem)
    assert public_pem_from_private(private_pem).startswith("-----BEGIN PUBLIC KEY-----")


def test_wrong_key_cannot_decrypt() -> None:
    _private_a, public_a = generate_keypair()
    private_b, _public_b = generate_keypair()
    box = encrypt(public_a, b"secret")
    with pytest.raises(CryptoError):
        decrypt(private_b, box)


def test_bad_pem_rejected() -> None:
    with pytest.raises(CryptoError):
        public_pem_from_private("not-a-key")
