"""Bounded historical Order 97 inputs, never new live semantic evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAPPING = "data/source_audits/v963_shock/historical-inputs.json"
MAPPING_SHA256 = "51689e786d64ca281d7513bdd4e6b968aed65eeefd73a6dad1bb591d05de29b7"

ORDER102_MAPPING = "data/source_audits/order102/historical-inputs.json"
ORDER102_MAPPING_SHA256 = "c8e782fcab38c6944174b981cf8ebc9d37e2d4e8f073b3ed722ba759f8d54362"


ORDER103_MAPPING = "data/source_audits/order103/historical-inputs.json"
ORDER103_MAPPING_SHA256 = "af890dd01ff20bfafd61db06b3e6f5a546a97fc55dd06985be79b3c8a794b6df"


ISSUE535_MAPPING = "data/source_audits/issue535/historical-inputs.json"
ISSUE535_MAPPING_SHA256 = "5c0f44902158da51de3279bc7d44c9e2a13a2f4c2d3ce1c67d02925e3e851c95"


ISSUE534_MAPPING = "data/source_audits/issue534/historical-inputs.json"
ISSUE534_MAPPING_SHA256 = "49d81bcbb38b6b29ad24a4ab24742854b987fca858070e82dcd7cc0f5e87a45f"


ORDER104_MAPPING = "data/source_audits/order104/historical-inputs.json"
ORDER104_MAPPING_SHA256 = "229bf8b5f6803dc7857ed44fc3cf997cf944ab5c8d900234dd7b8dd0d4df6263"


ORDER107_MAPPING = "data/source_audits/order107/historical-inputs.json"
ORDER107_MAPPING_SHA256 = "abff3f6516cd2489ed63009bf2253d8a06a7487b1501343cb650e626c423baec"

ORDER108_MAPPING = "data/source_audits/order108/historical-inputs.json"
ORDER108_MAPPING_SHA256 = "36849bc5a2a436eee161e961f16e8445612bccfef82f46a99be4548c5f528606"


ORDER110_MAPPING = "data/source_audits/order110/historical-inputs.json"
ORDER110_MAPPING_SHA256 = "98057295d7c92a1f19b76befb40679f214731417315a205cb4985d990cc7e77f"


ORDER112_MAPPING = "data/source_audits/order112/historical-inputs.json"
ORDER112_MAPPING_SHA256 = "f409d4e5acf6d391ee4bb38df985ba6992806a7032b66dafeb5ae325777e6259"


ORDER113_MAPPING = "data/source_audits/order113/historical-inputs.json"
ORDER113_MAPPING_SHA256 = "c594f1e301bc4203505ab9785b21d549aa4867745e3477a4aa11f35509e54129"


ORDER114_MAPPING = "data/source_audits/order114/historical-inputs.json"
ORDER114_MAPPING_SHA256 = "6cbb3f6da99d02b753c6912daebd51f4b634485b9cc0e6b38bb4e52174a291ef"


def historical_evidence_path(reference: str, *, root: Path) -> Path | None:
    """Resolve only the reviewed mapping; missing or corrupt history never falls back."""
    for mapping_name, expected_sha256 in (
        (MAPPING, MAPPING_SHA256),
        (ORDER102_MAPPING, ORDER102_MAPPING_SHA256),
        (ORDER103_MAPPING, ORDER103_MAPPING_SHA256),
        (ISSUE535_MAPPING, ISSUE535_MAPPING_SHA256),
        (ISSUE534_MAPPING, ISSUE534_MAPPING_SHA256),
        (ORDER104_MAPPING, ORDER104_MAPPING_SHA256),
        (ORDER107_MAPPING, ORDER107_MAPPING_SHA256),
        (ORDER108_MAPPING, ORDER108_MAPPING_SHA256),
        (ORDER110_MAPPING, ORDER110_MAPPING_SHA256),
        (ORDER112_MAPPING, ORDER112_MAPPING_SHA256),
        (ORDER113_MAPPING, ORDER113_MAPPING_SHA256),
        (ORDER114_MAPPING, ORDER114_MAPPING_SHA256),
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
