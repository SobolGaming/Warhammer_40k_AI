from __future__ import annotations

import hashlib
import json
from typing import Final

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

ARTIFACT_SCHEMA: Final = "core-v2-phase17n-event-companion-primary-scoring-v1"
SOURCE_PACKAGE_ID: Final = "gw-11e-warhammer-event-companion-v1-1-2026-07"
PRIMARY_MISSION_ID: Final = "primary-meatgrinder"
EXPECTED_PACKAGE_HASH: Final = "21b3fabcb585ee33b2295a888963d666a42f85d3f09200e973dd7de8253bd39c"
EXPECTED_ARTIFACT_SHA256: Final = "5e892581956e2b3c81bac893caef6b04f71cf19c1c3e2590ea33256b1a786342"
_ARTIFACT_PACKAGE: Final = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"
_ARTIFACT_PATH: Final = "event_companion_2026_06_artifacts/primary-meatgrinder-scoring.json"
_EXPECTED_RULE_IDS: Final = (
    "meatgrinder-enemy-destroyed-turn-end",
    "meatgrinder-objective-control",
    "meatgrinder-more-destroyed-turn-end",
    "meatgrinder-opponent-home-turn-end",
)
_SUPPORTED_TIMINGS: Final = frozenset(
    {
        "turn_end",
        "command_phase_or_round_five_turn_end",
        "turn_end_from_battle_round_two",
    }
)
_SUPPORTED_CONDITIONS: Final = frozenset(
    {
        "one_or_more_enemy_units_destroyed_this_turn",
        "control_one_or_more_non_home_objectives_from_battle_round_two",
        "more_enemy_units_destroyed_than_friendly_previous_turn",
        "control_opponent_home_objective",
    }
)


class EventCompanionPrimaryScoringArtifactError(ValueError):
    """Raised when the committed Event Companion scoring artifact is invalid."""


class AuthoritativeScoringSourceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    source_kind: str
    source_title: str
    source_scope: str
    review_status: str
    review_pull_request: int
    review_commit: str


class SecondaryScoringCorroborationArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    provider: str
    authority_status: str
    transcription_url: str
    card_image_url: str
    retrieved_date: str
    card_image_sha256: str


class LayoutSourceBoundaryArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    source_pdf_filename: str
    source_pdf_sha256: str
    source_pages: tuple[int, ...]
    authority_scope: str
    contains_meatgrinder_scoring_clauses: bool


class PrimaryScoringRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    battle_round_window_text: str
    trigger_text: str
    canonical_text: str
    timing: str
    source_kind: str
    victory_points: int
    cap: None
    condition: str


class EventCompanionPrimaryScoringArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    primary_mission_id: str
    mission_name: str
    scoring_kind: str
    max_vp_per_turn: None
    vp_per_controlled_objective: None
    authoritative_source: AuthoritativeScoringSourceArtifact
    secondary_corroboration: SecondaryScoringCorroborationArtifact
    layout_source_boundary: LayoutSourceBoundaryArtifact
    scoring_rules: tuple[PrimaryScoringRuleArtifact, ...]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring artifact schema is unsupported."
            )
        if self.source_package_id != SOURCE_PACKAGE_ID:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring source package drifted."
            )
        if (
            self.primary_mission_id,
            self.mission_name,
            self.scoring_kind,
        ) != (PRIMARY_MISSION_ID, "Meatgrinder", "meatgrinder"):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring mission identity drifted."
            )
        _validate_authoritative_source(self.authoritative_source)
        _validate_secondary_corroboration(self.secondary_corroboration)
        _validate_layout_source_boundary(self.layout_source_boundary)
        _validate_scoring_rules(self.scoring_rules)
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != primary_scoring_package_hash(self):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring package hash is stale."
            )
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring package hash drifted from its reviewed pin."
            )


def event_companion_primary_scoring_artifact_from_json_bytes(
    raw: bytes,
) -> EventCompanionPrimaryScoringArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=EventCompanionPrimaryScoringArtifact)
    except msgspec.DecodeError as exc:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def primary_scoring_package_hash(artifact: EventCompanionPrimaryScoringArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_artifact() -> EventCompanionPrimaryScoringArtifact:
    try:
        raw = package_artifact_bytes(_ARTIFACT_PACKAGE, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact could not be loaded."
        ) from exc
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact bytes drifted from their reviewed pin."
        )
    return event_companion_primary_scoring_artifact_from_json_bytes(raw)


def _validate_authoritative_source(source: AuthoritativeScoringSourceArtifact) -> None:
    if (
        source.source_kind,
        source.source_title,
        source.source_scope,
        source.review_status,
        source.review_pull_request,
        source.review_commit,
    ) != (
        "project_owner_supplied_official_source_transcription",
        "Warhammer 40,000 Chapter Approved 2026-27 Meatgrinder Primary Mission card",
        "Meatgrinder primary mission scoring clauses",
        "reviewed_and_merged",
        134,
        "35b9ddaf5",
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring authoritative provenance drifted."
        )


def _validate_secondary_corroboration(
    source: SecondaryScoringCorroborationArtifact,
) -> None:
    if (
        source.provider,
        source.authority_status,
        source.transcription_url,
        source.card_image_url,
        source.retrieved_date,
        source.card_image_sha256,
    ) != (
        "GDMissions",
        "secondary_corroboration_not_official_gw_source",
        "https://gdmissions.app/11th/primary-missions/purge-the-foe/meatgrinder",
        "https://gdmissions.app/assets/11th/primary-missions/purge-the-foe/meatgrinder.png",
        "2026-08-09",
        "d4bcc1dfde2d72fb2fc31b095964d1ea7721dcd082967b0063bcfd77c9965c24",
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring secondary corroboration drifted."
        )


def _validate_layout_source_boundary(source: LayoutSourceBoundaryArtifact) -> None:
    if (
        source.source_pdf_filename,
        source.source_pdf_sha256,
        source.source_pages,
        source.authority_scope,
        source.contains_meatgrinder_scoring_clauses,
    ) != (
        "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf",
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20",
        (24, 25, 26),
        "battlefield_and_layout_facts_only",
        False,
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion layout-versus-scoring provenance boundary drifted."
        )


def _validate_scoring_rules(rules: tuple[PrimaryScoringRuleArtifact, ...]) -> None:
    if type(rules) is not tuple:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring rules must be a tuple."
        )
    if tuple(rule.rule_id for rule in rules) != _EXPECTED_RULE_IDS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring rule inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion primary-scoring",
    )
    seen_conditions: set[str] = set()
    for rule in rules:
        identifiers("rule_id", rule.rule_id)
        identifiers("timing", rule.timing)
        identifiers("condition", rule.condition)
        if rule.source_kind != "primary":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring rule source_kind must be primary."
            )
        if rule.timing not in _SUPPORTED_TIMINGS:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring rule timing is unsupported."
            )
        if rule.condition not in _SUPPORTED_CONDITIONS:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring rule condition is unsupported."
            )
        if rule.condition in seen_conditions:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring rules must not duplicate conditions."
            )
        seen_conditions.add(rule.condition)
        if type(rule.victory_points) is not int or rule.victory_points <= 0:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring victory_points must be a positive integer."
            )
        for field_name, value in (
            ("battle_round_window_text", rule.battle_round_window_text),
            ("trigger_text", rule.trigger_text),
            ("canonical_text", rule.canonical_text),
        ):
            if type(value) is not str or value.strip() != value or not value:
                raise EventCompanionPrimaryScoringArtifactError(
                    f"Event Companion primary-scoring {field_name} must be canonical text."
                )


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            f"Event Companion primary-scoring {field_name} must be lowercase SHA-256."
        )
    return value


_ARTIFACT: Final = _load_artifact()
MEATGRINDER_SCORING_PACKAGE_HASH: Final = _ARTIFACT.package_hash
MEATGRINDER_SCORING_ARTIFACT_SHA256: Final = EXPECTED_ARTIFACT_SHA256


def meatgrinder_primary_scoring_artifact() -> EventCompanionPrimaryScoringArtifact:
    return _ARTIFACT


def validate_meatgrinder_primary_scoring_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact bytes drifted from their reviewed pin."
        )
    event_companion_primary_scoring_artifact_from_json_bytes(raw)


__all__ = (
    "MEATGRINDER_SCORING_ARTIFACT_SHA256",
    "MEATGRINDER_SCORING_PACKAGE_HASH",
    "EventCompanionPrimaryScoringArtifact",
    "EventCompanionPrimaryScoringArtifactError",
    "PrimaryScoringRuleArtifact",
    "event_companion_primary_scoring_artifact_from_json_bytes",
    "meatgrinder_primary_scoring_artifact",
    "validate_meatgrinder_primary_scoring_artifact_bytes",
)
