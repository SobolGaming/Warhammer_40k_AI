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

ARTIFACT_SCHEMA: Final = "core-v2-phase17n-event-companion-primary-scoring-v2"
SOURCE_PACKAGE_ID: Final = "gw-11e-warhammer-event-companion-v1-1-2026-07"
EXPECTED_PACKAGE_HASH: Final = "e96c461ec66f7b4d71bbd6f2b9b12899b0fc1a8bd3dae8fe60597d6dcc793e0f"
EXPECTED_ARTIFACT_SHA256: Final = "0751341279c5c823a7e847b1f2db98a69cd6d29c39c4cd1682cc9fce0e8c1486"
_ARTIFACT_PACKAGE: Final = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"
_ARTIFACT_PATH: Final = "event_companion_2026_06_artifacts/primary-scoring.json"
_PENDING_SCORING_KIND: Final = "event_companion_primary_source_known_engine_pending"
_EXPECTED_PRIMARY_MISSION_IDS: Final = (
    "primary-battlefield-dominance",
    "primary-consecrate",
    "primary-death-trap",
    "primary-delaying-action",
    "primary-destroyers-wrath",
    "primary-determined-acquisition",
    "primary-extract-relic",
    "primary-gather-intel",
    "primary-immovable-object",
    "primary-inescapable-dominion",
    "primary-locate-and-deny",
    "primary-meatgrinder",
    "primary-outmaneuver",
    "primary-punishment",
    "primary-purge-and-secure",
    "primary-reconnaissance-sweep",
    "primary-sabotage",
    "primary-search-and-scour",
    "primary-secure-asset",
    "primary-smoke-and-mirrors",
    "primary-surveil-the-foe",
    "primary-triangulation",
    "primary-unstoppable-force",
    "primary-vanguard-operation",
    "primary-vital-link",
)
_EXPECTED_ENGINE_IMPLEMENTED_SCORING_KINDS: Final = {
    "primary-death-trap": "death_trap",
    "primary-immovable-object": "immovable_object",
    "primary-meatgrinder": "meatgrinder",
    "primary-unstoppable-force": "unstoppable_force",
}
_EXPECTED_RULE_COUNTS: Final = {
    "primary-battlefield-dominance": 3,
    "primary-consecrate": 5,
    "primary-death-trap": 4,
    "primary-delaying-action": 3,
    "primary-destroyers-wrath": 4,
    "primary-determined-acquisition": 3,
    "primary-extract-relic": 5,
    "primary-gather-intel": 5,
    "primary-immovable-object": 3,
    "primary-inescapable-dominion": 4,
    "primary-locate-and-deny": 4,
    "primary-meatgrinder": 4,
    "primary-outmaneuver": 4,
    "primary-punishment": 4,
    "primary-purge-and-secure": 4,
    "primary-reconnaissance-sweep": 4,
    "primary-sabotage": 3,
    "primary-search-and-scour": 4,
    "primary-secure-asset": 4,
    "primary-smoke-and-mirrors": 4,
    "primary-surveil-the-foe": 4,
    "primary-triangulation": 5,
    "primary-unstoppable-force": 4,
    "primary-vanguard-operation": 4,
    "primary-vital-link": 5,
}
_EXPECTED_SOURCE_ONLY_ACTION_IDS: Final = (
    "commit-sabotage",
    "decoy-objective",
    "extract-intelligence",
    "maintain-control",
    "secure-asset",
    "sensor-sweep-extract-relic",
    "sensor-sweep-locate-and-deny",
    "surveil-enemy-unit",
    "triangulate-objective",
    "vanguard-operation",
)


class EventCompanionPrimaryScoringArtifactError(ValueError):
    """Raised when the committed Event Companion Primary artifact is invalid."""


class SourceReviewRecordArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    pull_request: int
    commit: str


class AuthoritativeScoringSourceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    source_kind: str
    source_title: str
    source_scope: str
    official_source_binary_status: str
    structured_transcription_scope: str
    verbatim_text_scope: str
    review_status: str
    review_records: tuple[SourceReviewRecordArtifact, ...]


class SecondaryScoringCorroborationArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    primary_mission_id: str
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
    contains_primary_mission_card_scoring_clauses: bool


class PrimaryScoringRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    battle_round_window_text: str | None
    trigger_text: str | None
    canonical_text: str | None
    timing: str
    source_kind: str
    victory_points: int
    cap: None
    condition: str


class PrimaryMissionScoringArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    primary_mission_id: str
    mission_name: str
    engine_support_status: str
    scoring_kind: str
    max_vp_per_turn: None
    vp_per_controlled_objective: None
    scoring_rules: tuple[PrimaryScoringRuleArtifact, ...]


class PrimaryMissionActionSourceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    mission_action_id: str
    primary_mission_id: str
    name: str
    start_phase: str
    start_timing: str
    completion_timing: str
    eligible_unit_policy: str
    target_policy: str
    use_limit: str
    effect_descriptor: str
    engine_exposure_status: str
    source_id: str


class EventCompanionPrimaryScoringArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    authoritative_source: AuthoritativeScoringSourceArtifact
    secondary_corroborations: tuple[SecondaryScoringCorroborationArtifact, ...]
    layout_source_boundary: LayoutSourceBoundaryArtifact
    primary_missions: tuple[PrimaryMissionScoringArtifact, ...]
    source_only_primary_actions: tuple[PrimaryMissionActionSourceArtifact, ...]
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
        _validate_authoritative_source(self.authoritative_source)
        _validate_secondary_corroborations(self.secondary_corroborations)
        _validate_layout_source_boundary(self.layout_source_boundary)
        _validate_primary_missions(self.primary_missions)
        _validate_source_only_primary_actions(
            self.source_only_primary_actions,
            primary_mission_ids=frozenset(
                mission.primary_mission_id for mission in self.primary_missions
            ),
        )
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
        source.official_source_binary_status,
        source.structured_transcription_scope,
        source.verbatim_text_scope,
        source.review_status,
    ) != (
        "project_owner_supplied_official_source_transcription",
        "Warhammer 40,000 Chapter Approved 2026-27 Primary Mission cards",
        (
            "All 25 Primary mission scoring records and 10 source-only Primary Mission "
            "Action descriptors"
        ),
        "not_committed_transcription_review_only",
        "all_primary_scoring_and_source_only_action_descriptors",
        "meatgrinder_scoring_clauses_only",
        "reviewed_and_merged",
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring authoritative provenance drifted."
        )
    expected_reviews = (
        (134, "35b9ddaf5a49ad947177712a883fd0c76e3db224"),
        (136, "34e05f19886c8c483fb0fa7c3e1ba86626bb89f1"),
        (379, "15af220739679f5aa84dd16981ae3e7dbaa93520"),
    )
    if tuple((row.pull_request, row.commit) for row in source.review_records) != (expected_reviews):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring review provenance drifted."
        )
    for review in source.review_records:
        if type(review.pull_request) is not int or review.pull_request <= 0:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring review PR must be a positive integer."
            )
        _validate_git_commit("review commit", review.commit)


def _validate_secondary_corroborations(
    sources: tuple[SecondaryScoringCorroborationArtifact, ...],
) -> None:
    if len(sources) != 1:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring secondary corroboration inventory drifted."
        )
    source = sources[0]
    if (
        source.primary_mission_id,
        source.provider,
        source.authority_status,
        source.transcription_url,
        source.card_image_url,
        source.retrieved_date,
        source.card_image_sha256,
    ) != (
        "primary-meatgrinder",
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
        source.contains_primary_mission_card_scoring_clauses,
    ) != (
        "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf",
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20",
        tuple(range(9, 54)),
        "battlefield_and_layout_facts_only",
        False,
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion layout-versus-scoring provenance boundary drifted."
        )


def _validate_primary_missions(missions: tuple[PrimaryMissionScoringArtifact, ...]) -> None:
    mission_ids = tuple(mission.primary_mission_id for mission in missions)
    if mission_ids != _EXPECTED_PRIMARY_MISSION_IDS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring mission inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion primary-scoring",
    )
    seen_rule_ids: set[str] = set()
    canonical_text_missions: set[str] = set()
    total_rule_count = 0
    for mission in missions:
        identifiers("primary_mission_id", mission.primary_mission_id)
        _validate_canonical_text("mission_name", mission.mission_name)
        expected_scoring_kind = _EXPECTED_ENGINE_IMPLEMENTED_SCORING_KINDS.get(
            mission.primary_mission_id
        )
        if expected_scoring_kind is None:
            expected_status = "source_known_engine_pending"
            expected_scoring_kind = _PENDING_SCORING_KIND
        else:
            expected_status = "engine_implemented"
        if (
            mission.engine_support_status,
            mission.scoring_kind,
        ) != (expected_status, expected_scoring_kind):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring engine support truth drifted."
            )
        expected_rule_count = _EXPECTED_RULE_COUNTS[mission.primary_mission_id]
        if len(mission.scoring_rules) != expected_rule_count:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring per-mission rule inventory drifted."
            )
        total_rule_count += len(mission.scoring_rules)
        for rule in mission.scoring_rules:
            _validate_primary_scoring_rule(rule, identifiers=identifiers)
            if rule.rule_id in seen_rule_ids:
                raise EventCompanionPrimaryScoringArtifactError(
                    "Event Companion primary-scoring rule IDs must be globally unique."
                )
            seen_rule_ids.add(rule.rule_id)
            text_fields = (
                rule.battle_round_window_text,
                rule.trigger_text,
                rule.canonical_text,
            )
            if any(value is not None for value in text_fields):
                if not all(value is not None for value in text_fields):
                    raise EventCompanionPrimaryScoringArtifactError(
                        "Event Companion primary-scoring canonical text fields are atomic."
                    )
                canonical_text_missions.add(mission.primary_mission_id)
                for field_name, value in zip(
                    ("battle_round_window_text", "trigger_text", "canonical_text"),
                    text_fields,
                    strict=True,
                ):
                    _validate_canonical_text(field_name, value)
    if total_rule_count != 100:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring rule inventory must contain 100 rows."
        )
    if canonical_text_missions != {"primary-meatgrinder"}:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring verbatim-text scope drifted."
        )


def _validate_primary_scoring_rule(
    rule: PrimaryScoringRuleArtifact,
    *,
    identifiers: IdentifierValidator,
) -> None:
    identifiers("rule_id", rule.rule_id)
    identifiers("timing", rule.timing)
    identifiers("condition", rule.condition)
    if rule.source_kind != "primary":
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring rule source_kind must be primary."
        )
    if type(rule.victory_points) is not int or rule.victory_points <= 0:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring victory_points must be a positive integer."
        )


def _validate_source_only_primary_actions(
    actions: tuple[PrimaryMissionActionSourceArtifact, ...],
    *,
    primary_mission_ids: frozenset[str],
) -> None:
    if tuple(action.mission_action_id for action in actions) != (_EXPECTED_SOURCE_ONLY_ACTION_IDS):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion source-only Primary Action inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion source-only Primary Action",
    )
    for action in actions:
        for field_name, value in (
            ("mission_action_id", action.mission_action_id),
            ("primary_mission_id", action.primary_mission_id),
            ("start_phase", action.start_phase),
            ("start_timing", action.start_timing),
            ("completion_timing", action.completion_timing),
            ("eligible_unit_policy", action.eligible_unit_policy),
            ("target_policy", action.target_policy),
            ("use_limit", action.use_limit),
            ("effect_descriptor", action.effect_descriptor),
        ):
            identifiers(field_name, value)
        _validate_canonical_text("action name", action.name)
        if action.primary_mission_id not in primary_mission_ids:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion source-only Primary Action references an unknown mission."
            )
        if action.engine_exposure_status != "source_known_engine_pending":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion source-only Primary Actions must remain engine-pending."
            )
        if action.source_id != (f"{SOURCE_PACKAGE_ID}:primary-action:{action.mission_action_id}"):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion source-only Primary Action source ID drifted."
            )


def _validate_canonical_text(field_name: str, value: object) -> str:
    if type(value) is not str or value.strip() != value or not value:
        raise EventCompanionPrimaryScoringArtifactError(
            f"Event Companion primary-scoring {field_name} must be canonical text."
        )
    return value


def _validate_git_commit(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            f"Event Companion primary-scoring {field_name} must be a full Git commit hash."
        )
    return value


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
PRIMARY_SCORING_PACKAGE_HASH: Final = _ARTIFACT.package_hash
PRIMARY_SCORING_ARTIFACT_SHA256: Final = EXPECTED_ARTIFACT_SHA256


def event_companion_primary_scoring_artifact() -> EventCompanionPrimaryScoringArtifact:
    return _ARTIFACT


def engine_implemented_primary_mission_ids() -> frozenset[str]:
    return frozenset(
        mission.primary_mission_id
        for mission in _ARTIFACT.primary_missions
        if mission.engine_support_status == "engine_implemented"
    )


def validate_event_companion_primary_scoring_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring artifact bytes drifted from their reviewed pin."
        )
    event_companion_primary_scoring_artifact_from_json_bytes(raw)


__all__ = (
    "PRIMARY_SCORING_ARTIFACT_SHA256",
    "PRIMARY_SCORING_PACKAGE_HASH",
    "EventCompanionPrimaryScoringArtifact",
    "EventCompanionPrimaryScoringArtifactError",
    "PrimaryMissionActionSourceArtifact",
    "PrimaryMissionScoringArtifact",
    "PrimaryScoringRuleArtifact",
    "engine_implemented_primary_mission_ids",
    "event_companion_primary_scoring_artifact",
    "event_companion_primary_scoring_artifact_from_json_bytes",
    "validate_event_companion_primary_scoring_artifact_bytes",
)
