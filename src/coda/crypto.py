"""Symmetric encryption for stored Arcaea credentials.

Covers both our own bot accounts and player-linked accounts under one key
(``FERNET_KEY``). There is deliberately no rotation path at this scale.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from coda.config import config

_fernet = Fernet(config.fernet_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a stored secret.

    Raises ``cryptography.fernet.InvalidToken`` if the key changed since the
    row was written.
    """
    return _fernet.decrypt(token.encode()).decode()
