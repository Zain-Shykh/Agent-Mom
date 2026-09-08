"""CryptoService: AES-GCM encrypt/decrypt for message payloads (3.2.4.1-3.2.4.6).

A single symmetric key is generated once at process start (main.py) and
shared out-of-band across all agent windows in the demo — this stands in
for the SRS's conceptual "key-distribution agent" (architecture.md §4.5),
flagged in Part 1 as an AI-introduced, unsupported design choice.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96-bit nonce, the size AES-GCM is designed for.


class CryptoService:
    def __init__(self, key: bytes):
        self._aesgcm = AESGCM(key)

    @staticmethod
    def generate_key() -> bytes:
        return AESGCM.generate_key(bit_length=256)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt `plaintext`, returning base64(nonce || ciphertext)."""
        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a base64(nonce || ciphertext) string produced by encrypt().

        Raises cryptography.exceptions.InvalidTag if the key is wrong or the
        data was tampered with — AES-GCM's authentication tag makes silent
        garbage-output decryption impossible by construction.
        """
        raw = base64.b64decode(ciphertext_b64)
        nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
