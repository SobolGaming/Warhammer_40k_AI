"""Typed eager loader for versioned faction Stratagem activation data."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, fields

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

SOURCE_PACKAGE_ID = "gw-11e-phase17s-faction-stratagem-activation-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Faction Stratagem Activation Support"
SOURCE_VERSION = "2026-27"
SOURCE_DATE = "2026-06-21"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17s-stratagem-activation-v1"
RULE_IR_NORMALIZED_TEXT = "stratagem_activation_target_binding"
RULE_IR_PARSER_VERSION = "phase17s-stratagem-activation-template-v2"
RULE_IR_SCHEMA_VERSION = "phase17c-rule-ir-v1"
RULE_IR_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"


@dataclass(frozen=True, slots=True)
class SourceStratagemActivationProfile:
    profile_id: str
    source_row_id: str
    source_id: str
    faction_id: str
    detachment_id: str
    stratagem_id: str
    name: str
    command_point_cost: int
    category: str
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    trigger_kind: str
    phase_tokens: tuple[str, ...]
    target_kind: str
    target_policy_id: str
    required_keywords: tuple[str, ...] = ()
    required_keywords_any: tuple[str, ...] = ()
    required_faction_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    excluded_faction_keywords: tuple[str, ...] = ()
    rule_ir_hash: str = ""

    def rule_ir_payload(self) -> dict[str, object]:
        return deepcopy(_STATIC_RULE_IR_PAYLOADS_BY_PROFILE_ID[self.profile_id])

    def effect_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "rule_ir": self.rule_ir_payload(),
            "activation_profile_id": self.profile_id,
            "activation_template_id": RULE_IR_TEMPLATE_ID,
        }
        effect_selection_kind = _EFFECT_SELECTION_KIND_BY_PROFILE_ID.get(self.profile_id)
        if effect_selection_kind is not None:
            payload["effect_selection_kind"] = effect_selection_kind
        return payload

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "source_row_id": self.source_row_id,
            "source_id": self.source_id,
            "faction_id": self.faction_id,
            "detachment_id": self.detachment_id,
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "command_point_cost": self.command_point_cost,
            "category": self.category,
            "trigger_kind": self.trigger_kind,
            "phase_tokens": list(self.phase_tokens),
            "target_kind": self.target_kind,
            "target_policy_id": self.target_policy_id,
            "required_keywords": list(self.required_keywords),
            "required_keywords_any": list(self.required_keywords_any),
            "required_faction_keywords": list(self.required_faction_keywords),
            "excluded_keywords": list(self.excluded_keywords),
            "excluded_faction_keywords": list(self.excluded_faction_keywords),
            "rule_ir_hash": self.rule_ir_hash,
        }


def stratagem_activation_profiles() -> tuple[SourceStratagemActivationProfile, ...]:
    return _PROFILES


def source_package_identity_payload() -> dict[str, str]:
    return {
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "source_commit_or_import_hash": _import_hash(),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def _import_hash() -> str:
    payload = [profile.to_payload() for profile in _PROFILES]
    return _sha256_payload(payload)


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validate_profiles(
    profiles: tuple[SourceStratagemActivationProfile, ...],
) -> tuple[SourceStratagemActivationProfile, ...]:
    seen: set[str] = set()
    for profile in profiles:
        if type(profile) is not SourceStratagemActivationProfile:
            raise ValueError("Stratagem activation profiles must be typed profiles.")
        if profile.source_row_id in seen:
            raise ValueError("Stratagem activation profiles must be unique by source row.")
        seen.add(profile.source_row_id)
        if not profile.phase_tokens:
            raise ValueError("Stratagem activation profile phases must not be empty.")
    return profiles


class ActivationArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_snapshot_sha256: str
    profiles: tuple[SourceStratagemActivationProfile, ...]
    rule_ir_by_profile_id: dict[str, RuleIRPayload]
    effect_selection_kind_by_profile_id: dict[str, str]


EXPECTED_ARTIFACT_SHA256 = "c50e9b188744bff24359d8a0559556f1c47a59a48f32aae662822322ab58f67f"


def validate_artifact_bytes(raw: bytes) -> ActivationArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ValueError("Stratagem activation artifact bytes drifted.")
    try:
        artifact = msgspec.json.decode(raw, type=ActivationArtifact)
    except msgspec.DecodeError as exc:
        raise ValueError("Stratagem activation artifact schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-stratagem-activation-artifact-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
    ):
        raise ValueError("Stratagem activation artifact identity drifted.")
    # Data rows carry every required field, including meaningful empty values.
    payload = msgspec.json.decode(raw)
    expected_fields = {field.name for field in fields(SourceStratagemActivationProfile)}
    if any(set(row) != expected_fields for row in payload["profiles"]):
        raise ValueError("Stratagem activation profile fields drifted.")
    profiles_by_id = {profile.profile_id: profile for profile in artifact.profiles}
    profile_ids = set(profiles_by_id)
    if len(profile_ids) != len(artifact.profiles):
        raise ValueError("Stratagem activation profile IDs must be unique.")
    if (
        set(artifact.rule_ir_by_profile_id) != profile_ids
        or not set(artifact.effect_selection_kind_by_profile_id) <= profile_ids
    ):
        raise ValueError("Stratagem activation artifact contains foreign profiles.")
    for profile_id, rule_payload in artifact.rule_ir_by_profile_id.items():
        rule = RuleIR.from_payload(rule_payload)
        profile = profiles_by_id[profile_id]
        if (
            rule.rule_id != profile.profile_id
            or rule.source_id != profile.source_id
            or rule.ir_hash() != profile.rule_ir_hash
        ):
            raise ValueError("Stratagem activation RuleIR source identity drifted.")
    return artifact


_ARTIFACT = validate_artifact_bytes(
    package_artifact_bytes(
        "warhammer40k_core.rules.source_packages.warhammer_40000_11th",
        "faction_stratagem_activation_2026_27.json",
    )
)
_STATIC_RULE_IR_PAYLOADS_BY_PROFILE_ID: dict[str, dict[str, object]] = {
    key: dict(value) for key, value in _ARTIFACT.rule_ir_by_profile_id.items()
}
_EFFECT_SELECTION_KIND_BY_PROFILE_ID = _ARTIFACT.effect_selection_kind_by_profile_id
_PROFILES = _validate_profiles(_ARTIFACT.profiles)
