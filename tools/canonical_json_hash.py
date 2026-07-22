from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast


def canonical_json_sha256(path: Path) -> str:
    if not isinstance(path, Path):
        raise TypeError("Canonical JSON hash path must be a Path.")
    try:
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}.") from exc
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
