"""Immutable exact historical input; every restored session is fresh."""

import gzip
import json
from functools import lru_cache
from pathlib import Path

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


@lru_cache(maxsize=1)
def historical_checkpoint_bytes() -> bytes:
    root = Path(__file__).resolve().parents[2]
    return gzip.decompress(
        (root / "data/source_audits/a32_recovery/oct14-post-exception.json.gz").read_bytes()
    )


@lru_cache(maxsize=1)
def recovered_checkpoint_bytes() -> bytes:
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        PROFILE_ID,
        reconstruct_local_checkpoint,
    )

    result = reconstruct_local_checkpoint(historical_checkpoint_bytes(), profile_id=PROFILE_ID)
    return json.dumps(result, sort_keys=True, separators=(",", ":")).encode()


def recovered_payload() -> JsonValue:
    return validate_json_value(json.loads(recovered_checkpoint_bytes()))
