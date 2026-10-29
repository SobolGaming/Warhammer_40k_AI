"""Fail-closed predecessor views for the authorized Section13 descriptor repair."""

import hashlib
from pathlib import Path

DESCRIPTOR = "src/warhammer40k_core/core/ruleset_descriptor.py"
GOLDEN_TEST = "tests/unit/test_ruleset_descriptor.py"
ARCHIVE = "data/source_audits/section13-repairs"
BEFORE_DESCRIPTOR = "40eb947f9582890a4c4daf117a776d02e29fa299d74a2aebb89783e9ca863b4c"
AFTER_DESCRIPTOR = "d4d30951aa60f5c7ef10941f609ee76abb3400945cba928a69f5321a14cbb7b8"
BEFORE_TEST = "98ea3e421d654ca84d6bc21f360f2383d60c740c108c63e0b250c67a663d951d"
AFTER_TEST = "4a8d071b4a0fa245b456373ac64b466b78eadd68a5b1ac01b8357224f245db9c"
OLD_HASH = b"358ded485e5c9aab3619b2ac06048820dbc60ad96443737f0a4d1a2e21a31536"
NEW_HASH = b"6f1b37df63b218433f568b2ddddabd4b6a4a34e939655266ad6f918d2d46f144"


def pre_section13_descriptor_bytes(root: Path) -> bytes:
    current = (root / DESCRIPTOR).read_bytes()
    before = (root / ARCHIVE / "ruleset-descriptor-before.py.txt").read_bytes()
    if (
        hashlib.sha256(current).hexdigest() != AFTER_DESCRIPTOR
        or hashlib.sha256(before).hexdigest() != BEFORE_DESCRIPTOR
    ):
        raise ValueError("Section13 exact descriptor/predecessor bytes drifted.")
    return before


def preserved_section13_golden_bytes(root: Path, path: str, current: bytes) -> bytes:
    if path != GOLDEN_TEST:
        return current
    before = (root / ARCHIVE / "descriptor-test-before.py.txt").read_bytes()
    if (
        hashlib.sha256(before).hexdigest() != BEFORE_TEST
        or hashlib.sha256(current).hexdigest() != AFTER_TEST
        or before.count(OLD_HASH) != 1
        or before.replace(OLD_HASH, NEW_HASH, 1) != current
    ):
        raise ValueError("Section13 exact one-literal descriptor golden maintenance drifted.")
    return before
