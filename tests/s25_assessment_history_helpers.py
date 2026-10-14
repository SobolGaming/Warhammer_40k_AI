"""Read immutable S25 final assessment inputs without rebinding them to later work."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "assessment.json": "9171c671986f75232bb308208765f729d04853abee79fe22342d1836256012ff",
    "operation-map.json": "c7534626e361870139ab0598fdd09b5c3e6cbf062dad98fd08b1534f73b55ae9",
}


def s25_final_assessment_bytes(name: str) -> bytes:
    if name not in PINS:
        raise ValueError("Unknown historical S25 assessment input.")
    raw = (ROOT / "docs/performance/policy-v3/s25-final-history" / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError("Historical S25 assessment input hash mismatch.")
    return raw
