"""Authenticate the finite test-fixture migration before historical proof reads.

Live references still execute current modules. This boundary reconstructs only
reviewed pre-migration test evidence; it never accepts a runtime save or replay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict, cast

EVIDENCE = "data/source_audits/private_rng_fixture_preimages_v1.json"
EVIDENCE_SHA256 = "624295c16ad595651c60534cb69872203d60d3549589037e417e45745d8cb456"
BASE = "2b640ffca912f72d74e3b08cec0c0c4b12ce776a"


class FixtureEdit(TypedDict):
    added: str
    removed: str
    offset: int


class FixtureRecord(TypedDict):
    before_sha256: str
    after_sha256: str
    edits: list[FixtureEdit]


def private_rng_fixture_records() -> dict[str, FixtureRecord]:
    raw = (Path(__file__).resolve().parents[2] / EVIDENCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != EVIDENCE_SHA256:
        raise ValueError("Private RNG fixture evidence bytes drifted.")
    value = cast(dict[str, Any], json.loads(raw))
    if (
        type(value) is not dict
        or set(value) != {"schema", "base", "records"}
        or value["schema"] != "private-rng-fixture-preimages-v1"
        or value["base"] != BASE
        or type(value["records"]) is not dict
    ):
        raise ValueError("Private RNG fixture evidence identity drifted.")
    records = cast(dict[str, FixtureRecord], value["records"])
    for relative, record in records.items():
        if (
            not relative.startswith("tests/")
            or ".." in Path(relative).parts
            or set(record) != {"before_sha256", "after_sha256", "edits"}
            or any(
                type(digest) is not str
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                for digest in (record["before_sha256"], record["after_sha256"])
            )
            or not record["edits"]
        ):
            raise ValueError("Private RNG fixture record drifted.")
        offsets: list[int] = []
        for edit in record["edits"]:
            if (
                set(edit) != {"added", "removed", "offset"}
                or type(edit["added"]) is not str
                or type(edit["removed"]) is not str
                or type(edit["offset"]) is not int
                or edit["offset"] < 0
            ):
                raise ValueError("Private RNG fixture edit shape drifted.")
            offsets.append(edit["offset"])
        if offsets != sorted(set(offsets)):
            raise ValueError("Private RNG fixture edit order drifted.")
    return records


def private_rng_fixture_predecessor(relative: str, current: bytes) -> bytes:
    """Reconstruct exactly pinned test evidence, preserving every unrelated byte."""
    records = private_rng_fixture_records()
    if relative not in records:
        return current
    record = records[relative]
    digest = hashlib.sha256(current).hexdigest()
    if digest == record["before_sha256"]:
        return current
    if digest != record["after_sha256"]:
        raise ValueError("Private RNG fixture successor bytes drifted: " + relative)
    predecessor = current
    for edit in reversed(record["edits"]):
        added = edit["added"].encode()
        offset = edit["offset"]
        if predecessor[offset : offset + len(added)] != added:
            raise ValueError("Private RNG fixture edit bytes drifted: " + relative)
        predecessor = (
            predecessor[:offset] + edit["removed"].encode() + predecessor[offset + len(added) :]
        )
    if hashlib.sha256(predecessor).hexdigest() != record["before_sha256"]:
        raise ValueError("Private RNG fixture predecessor bytes drifted: " + relative)
    return predecessor
