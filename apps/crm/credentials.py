"""Authenticated encryption for external-account secrets.

Only ciphertext is persisted.  The encryption key belongs in deployment secrets,
never in the database, source tree, API response or logs.
"""

import base64
import binascii
import os

from Crypto.Cipher import AES
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


PREFIX = 'aesgcm:v1:'


def _encryption_key():
    encoded = str(getattr(settings, 'EXTERNAL_ACCOUNT_ENCRYPTION_KEY', '') or '').strip()
    if not encoded:
        raise ImproperlyConfigured('EXTERNAL_ACCOUNT_ENCRYPTION_KEY is not configured.')
    try:
        key = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ImproperlyConfigured('EXTERNAL_ACCOUNT_ENCRYPTION_KEY is invalid.') from exc
    if len(key) != 32:
        raise ImproperlyConfigured('EXTERNAL_ACCOUNT_ENCRYPTION_KEY must contain 32 bytes.')
    return key


def encrypt_external_secret(value):
    if value in (None, ''):
        return ''
    nonce = os.urandom(12)
    cipher = AES.new(_encryption_key(), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(str(value).encode('utf-8'))
    payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode('ascii').rstrip('=')
    return PREFIX + payload


def decrypt_external_secret(value):
    if not value:
        return ''
    if not str(value).startswith(PREFIX):
        raise ValueError('Unknown external-account secret format.')
    encoded = str(value)[len(PREFIX):]
    try:
        payload = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
        nonce, tag, ciphertext = payload[:12], payload[12:28], payload[28:]
        if len(nonce) != 12 or len(tag) != 16:
            raise ValueError('Invalid encrypted external-account secret.')
        cipher = AES.new(_encryption_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8')
    except (ValueError, KeyError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError('Unable to decrypt external-account secret.') from exc
