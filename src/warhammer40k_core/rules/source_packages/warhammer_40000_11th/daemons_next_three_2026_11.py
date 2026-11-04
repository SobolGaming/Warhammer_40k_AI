"""Three bounded keyword corrections; complete observations are not gameplay certification."""

from __future__ import annotations

import hashlib
from functools import cache
from importlib.resources import files

from warhammer40k_core.rules.faction_source_governance import (
    FactionSourceAudit,
    FactionSourceError,
    validate_faction_source_audit_bytes,
)
from warhammer40k_core.rules.faction_source_package import faction_source_package_from_audit
from warhammer40k_core.rules.source_evidence import RuleSourcePackage

AUDIT_ARTIFACT_NAME = "daemons_next_three_2026_11.audit.json"
AUDIT_SHA256 = "ef49da41af68b0e862ca9b88cc4f08259ec124638ac69cf64283ea186012a6bd"
SOURCE_PACKAGE_NAME = "reviewed-daemons-next-three-observations-2026-11"
SOURCE_VERSION = "reviewed-2026-11-04"
KEYWORD_SOURCE_IDS = (
    ("000001112", "faction-app:chaos-daemons:datasheet:flesh-hounds"),
    ("000001120", "faction-app:chaos-daemons:datasheet:lord-of-change"),
    ("000001132", "faction-app:chaos-daemons:datasheet:plaguebearers"),
)
KEYWORD_PREIMAGES = (
    (
        "000001112",
        "000001112:Shadow Legion:global:false:4377",
        "0abff95a749c6ae143536a46dd4a0fab89bd0e75506a1a8141e867e5c415028e",
    ),
    (
        "000001120",
        "000001120:Shadow Legion:global:false:4434",
        "3bf016b1b3be15ae386e5de8d96ce4710014f6471a1bc35f06f298d87c8e13bd",
    ),
    (
        "000001132",
        "000001132:Shadow Legion:global:false:4496",
        "59e2762b8907207917b668a01db8d78f5d5e69a5a4d7d5a4a437e69706bc1413",
    ),
)


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Daemons next-three audit bytes drifted from reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)
