"""Bounded historical Order 97 inputs, never new live semantic evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAPPING = "data/source_audits/v963_shock/historical-inputs.json"
MAPPING_SHA256 = "51689e786d64ca281d7513bdd4e6b968aed65eeefd73a6dad1bb591d05de29b7"

ORDER102_MAPPING = "data/source_audits/order102/historical-inputs.json"
ORDER102_MAPPING_SHA256 = "c8e782fcab38c6944174b981cf8ebc9d37e2d4e8f073b3ed722ba759f8d54362"


def historical_evidence_path(reference: str, *, root: Path) -> Path | None:
    """Resolve only the reviewed mapping; missing or corrupt history never falls back."""
    for mapping_name, expected_sha256 in (
        (MAPPING, MAPPING_SHA256),
        (ORDER102_MAPPING, ORDER102_MAPPING_SHA256),
    ):
        raw = (root / mapping_name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("Order 97 historical-input mapping drifted.")
        mapping = json.loads(raw)
        for item in mapping["files"]:
            if item["path"] != reference:
                continue
            path = root / str(item["historical_path"])
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Order 97 historical evidence escaped the repository.")
            retained = path.read_bytes()
            if (
                len(retained) != item["bytes"]
                or hashlib.sha256(retained).hexdigest() != item["sha256"]
            ):
                raise ValueError("Order 97 immutable historical input drifted.")
            return path
    return None
