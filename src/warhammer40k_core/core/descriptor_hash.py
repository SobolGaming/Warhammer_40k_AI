from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import NoReturn


def canonical_payload_sha256(
    payload: Mapping[str, object], *, omit_empty_lists: tuple[str, ...] = ()
) -> str:
    payload_to_hash = dict(payload)
    for field_name in omit_empty_lists:
        if payload_to_hash.get(field_name) == []:
            del payload_to_hash[field_name]
    encoded = json.dumps(payload_to_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_sha256_hex(
    value: object,
    *,
    field_name: str,
    error_type: type[ValueError],
) -> str:
    if type(value) is not str:
        _raise(error_type, f"{field_name} must be a string.")
    stripped = value.strip()
    if len(stripped) != 64:
        _raise(error_type, f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in stripped):
        _raise(error_type, f"{field_name} must be a lowercase SHA-256 hex digest.")
    return stripped


def _raise(error_type: type[ValueError], message: str) -> NoReturn:
    raise error_type(message)
