"""Hybrid RSA-OAEP + AES-256-GCM box for the sync payload."""

from __future__ import annotations

import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_WRAP_SIZE = 256


class CryptoError(ValueError):
    pass


def generate_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def public_pem_from_private(private_pem: str) -> str:
    key = _load_private(private_pem)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def fingerprint(pem: str) -> str:
    if "PRIVATE KEY" in pem:
        pem = public_pem_from_private(pem)
    digest = hashlib.sha256(_load_public(pem).public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )).hexdigest()
    return " ".join(digest[index : index + 4] for index in range(0, 16, 4))


def encrypt(public_pem: str, plaintext: bytes) -> str:
    public = _load_public(public_pem)
    aes_key = os.urandom(32)
    nonce = os.urandom(12)
    wrapped = public.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    if len(wrapped) != _WRAP_SIZE:
        raise CryptoError("Unexpected wrapped key size")
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    packed = struct.pack(">H", len(wrapped)) + wrapped + nonce + ciphertext
    return base64.b64encode(packed).decode("ascii")


def decrypt(private_pem: str, blob: str) -> bytes:
    try:
        packed = base64.b64decode(blob.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as exc:
        raise CryptoError("Ciphertext is not valid") from exc
    if len(packed) < 2 + _WRAP_SIZE + 12 + 16:
        raise CryptoError("Ciphertext is too short")
    (wrap_len,) = struct.unpack(">H", packed[:2])
    start = 2
    end = start + wrap_len
    if wrap_len != _WRAP_SIZE or end + 12 > len(packed):
        raise CryptoError("Ciphertext is damaged")
    wrapped = packed[start:end]
    nonce = packed[end : end + 12]
    ciphertext = packed[end + 12 :]
    private = _load_private(private_pem)
    try:
        aes_key = private.decrypt(
            wrapped,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("Could not unlock this library with that key") from exc


def _load_private(pem: str):
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise CryptoError("That does not look like a Sonoscribe private key") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CryptoError("That does not look like a Sonoscribe private key")
    return key


def _load_public(pem: str):
    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except ValueError as exc:
        raise CryptoError("Public key is not valid") from exc
    if not isinstance(key, rsa.RSAPublicKey):
        raise CryptoError("Public key is not valid")
    return key
