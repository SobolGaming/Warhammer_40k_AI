"""Bounded V963 supersession of five Order 97 inputs, never new live evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAPPING = "data/source_audits/v963_shock/historical-inputs.json"
MAPPING_SHA256 = "51689e786d64ca281d7513bdd4e6b968aed65eeefd73a6dad1bb591d05de29b7"


def historical_evidence_path(reference: str, *, root: Path) -> Path | None:
    """Resolve only the reviewed mapping; missing or corrupt history never falls back."""
    raw = (root / MAPPING).read_bytes()
    if hashlib.sha256(raw).hexdigest() != MAPPING_SHA256:
        raise ValueError("Order 97 V963 historical-input mapping drifted.")
    mapping = json.loads(raw)
    for item in mapping["files"]:
        if item["path"] != reference:
            continue
        path = root / str(item["historical_path"])
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Order 97 historical evidence escaped the repository.")
        retained = path.read_bytes()
        if len(retained) != item["bytes"] or hashlib.sha256(retained).hexdigest() != item["sha256"]:
            raise ValueError("Order 97 immutable historical input drifted.")
        return path
    return None
