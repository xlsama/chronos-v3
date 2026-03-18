import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoService:
    def __init__(self, key: str):
        raw = base64.b64decode(key)
        # AESGCM requires 16, 24, or 32 byte keys
        self._key = raw[:32].ljust(32, b"\0")
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def decrypt(self, token: str) -> str:
        raw = base64.b64decode(token)
        nonce, ciphertext = raw[:12], raw[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode()
