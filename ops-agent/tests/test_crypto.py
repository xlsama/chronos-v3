import pytest

from src.services.crypto import CryptoService


@pytest.fixture
def crypto():
    return CryptoService(key="dGVzdGtleS1mb3ItY3J5cHRvLTMyYnl0ZXMh")


@pytest.fixture
def crypto_wrong_key():
    return CryptoService(key="d3Jvbmdrreee1LWZvci1jcnlwdG8tMzJieXQ=")


def test_encrypt_decrypt_roundtrip(crypto: CryptoService):
    plaintext = "my-secret-password"
    encrypted = crypto.encrypt(plaintext)
    assert encrypted != plaintext
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertext(crypto: CryptoService):
    plaintext = "my-secret-password"
    enc1 = crypto.encrypt(plaintext)
    enc2 = crypto.encrypt(plaintext)
    assert enc1 != enc2  # different IV each time


def test_decrypt_with_wrong_key_fails(crypto: CryptoService, crypto_wrong_key: CryptoService):
    encrypted = crypto.encrypt("secret")
    with pytest.raises(Exception):
        crypto_wrong_key.decrypt(encrypted)


def test_encrypt_empty_string(crypto: CryptoService):
    encrypted = crypto.encrypt("")
    assert crypto.decrypt(encrypted) == ""
