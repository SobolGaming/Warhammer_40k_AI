"""Four bounded keyword corrections; complete observations are not gameplay certification."""

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

AUDIT_ARTIFACT_NAME = "daemons_final_four_2026_11.audit.json"
AUDIT_SHA256 = "3cd1615fe1ced5db286c9fd5dc25c9db1b5d8aec24394b44329cc01228257c12"
SOURCE_PACKAGE_NAME = "reviewed-daemons-final-four-observations-2026-11"
SOURCE_VERSION = "reviewed-2026-11-04"
KEYWORD_SOURCE_IDS = (
    ("000002582", "faction-app:chaos-daemons:datasheet:bloodthirster"),
    ("000001149", "faction-app:chaos-daemons:datasheet:daemon-prince-of-chaos"),
    ("000002758", "faction-app:chaos-daemons:datasheet:daemon-prince-of-chaos-with-wings"),
    ("000001151", "faction-app:chaos-daemons:datasheet:soul-grinder"),
)
KEYWORD_PREIMAGES = (
    (
        "000002582",
        "000002582:Shadow Legion:global:false:6851",
        "38b8ca2d92e754f779791bb09be3ea29ad26a67b7c42da843f4ca3d49b8d3ffe",
    ),
    (
        "000001149",
        "000001149:Shadow Legion:global:false:4621",
        "a250f449548f85237f069867bd81ae851a5b829a4bb5b228abb213ae5947750c",
    ),
    (
        "000002758",
        "000002758:Shadow Legion:global:false:7698",
        "498ea479adc49e64d876472b99b6ce71f9294fab25df9ded34af9becf7ecd64c",
    ),
    (
        "000001151",
        "000001151:Shadow Legion:global:false:4638",
        "24b9239b6c9dc1451d99d702aab515c1b2c31af14449a6edce8f99620ab1ecc8",
    ),
)


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Daemons final-four audit bytes drifted from reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)
