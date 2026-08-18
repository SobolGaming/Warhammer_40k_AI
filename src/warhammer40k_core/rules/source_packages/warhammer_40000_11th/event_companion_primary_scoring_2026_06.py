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

ARTIFACT_SCHEMA: Final = "core-v2-phase17n-event-companion-primary-scoring-v6"
SOURCE_PACKAGE_ID: Final = "gw-11e-warhammer-event-companion-v1-1-2026-07"
EXPECTED_PACKAGE_HASH: Final = "eeee655d6f7c42902d0cebf4426c3758b9d88b82d120b5d88335bba49d71f3e5"
EXPECTED_ARTIFACT_SHA256: Final = "1a5651f8328aadaae148df60d0e388445def27384909398f6c8825c14289eb0f"
_ARTIFACT_PACKAGE: Final = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"
_ARTIFACT_PATH: Final = "event_companion_2026_06_artifacts/primary-scoring.json"
_EXPECTED_TURN_SCOPES: Final = frozenset({"own_player_turn", "any_player_turn"})
_EXPECTED_ANY_PLAYER_TURN_CONDITIONS: Final = frozenset(
    {
        "one_or_more_condemned_enemy_units_left_battlefield_this_turn",
    }
)
_PENDING_SCORING_KIND: Final = "event_companion_primary_source_known_engine_pending"
_EXPECTED_TIMINGS: Final = frozenset(
    {
        "battle_round_four_onwards_turn_end",
        "battle_rounds_two_and_three_command_phase",
        "command_phase",
        "command_phase_or_round_five_turn_end",
        "end_of_battle",
        "first_and_second_battle_round_turn_end",
        "first_battle_round_turn_end",
        "turn_end",
        "turn_end_from_battle_round_two",
    }
)
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
    "primary-battlefield-dominance": "battlefield_dominance",
    "primary-consecrate": "consecrate",
    "primary-death-trap": "death_trap",
    "primary-delaying-action": "delaying_action",
    "primary-destroyers-wrath": "destroyers_wrath",
    "primary-determined-acquisition": "determined_acquisition",
    "primary-immovable-object": "immovable_object",
    "primary-inescapable-dominion": "inescapable_dominion",
    "primary-meatgrinder": "meatgrinder",
    "primary-outmaneuver": "outmaneuver",
    "primary-punishment": "punishment",
    "primary-purge-and-secure": "purge_and_secure",
    "primary-reconnaissance-sweep": "reconnaissance_sweep",
    "primary-sabotage": "sabotage",
    "primary-search-and-scour": "search_and_scour",
    "primary-secure-asset": "secure_asset",
    "primary-smoke-and-mirrors": "smoke_and_mirrors",
    "primary-triangulation": "triangulation",
    "primary-unstoppable-force": "unstoppable_force",
    "primary-vanguard-operation": "vanguard_operation",
}
_EXPECTED_RESOLUTION_GROUPS: Final = {
    "battlefield-dominance-command-primary": (
        "cumulative",
        (
            "battlefield-dominance-each-objective",
            "battlefield-dominance-home-controlled-non-home-bonus",
        ),
    ),
    "determined-acquisition-command-primary": (
        "cumulative",
        (
            "determined-acquisition-each-objective",
            "determined-acquisition-opponent-territory-bonus",
        ),
    ),
    "sabotage-turn-end-primary": (
        "cumulative",
        (
            "sabotage-each-unit-turn-end",
            "sabotage-opponent-territory-bonus-turn-end",
        ),
    ),
    "vital-link-turn-end-primary": (
        "cumulative",
        (
            "vital-link-central-objective-turn-end",
            "vital-link-operation-marker-central-bonus-turn-end",
        ),
    ),
    "vital-link-command-primary": (
        "cumulative",
        (
            "vital-link-objective-control",
            "vital-link-central-objective-bonus",
        ),
    ),
    "purge-and-secure-destruction-primary": (
        "exclusive_highest",
        (
            "purge-and-secure-destroyed-by-objective-unit-turn-end",
            "purge-and-secure-started-objective-destroyed-turn-end",
        ),
    ),
    "reconnaissance-sweep-quarters-primary": (
        "exclusive_highest",
        (
            "reconnaissance-sweep-three-quarters-turn-end",
            "reconnaissance-sweep-four-quarters-turn-end",
        ),
    ),
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
_EXPECTED_PRIMARY_ACTION_IDS: Final = (
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
_EXPECTED_PRIMARY_ACTION_CLAUSES: Final = {
    "commit-sabotage": (
        "primary-sabotage",
        "Sabotage",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_range_of_non_home_objective",
        "objective_marker_excluding_home",
        "unlimited_different_objective_per_unit_this_phase",
        "unit_commits_sabotage_if_action_unit_controls_target_at_turn_end",
    ),
    "decoy-objective": (
        "primary-smoke-and-mirrors",
        "Decoy",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit",
        "objective_marker_excluding_home_not_decoy",
        "unlimited_different_objective_per_unit_this_phase",
        "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
    ),
    "extract-intelligence": (
        "primary-gather-intel",
        "Extract Intelligence",
        "shooting",
        "shooting_phase_action_start_from_battle_round_two",
        "turn_end",
        "active_player_unit",
        "objective_marker_excluding_home_without_friendly_operation_marker",
        "unlimited_different_objective_per_unit_this_phase",
        "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
    ),
    "maintain-control": (
        "primary-vital-link",
        "Maintain Control",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_range_of_central_objective",
        "central_objective_marker",
        "once_per_turn",
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
    ),
    "secure-asset": (
        "primary-secure-asset",
        "Secure Asset",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_range_of_non_home_objective",
        "objective_marker_excluding_home",
        "once_per_turn",
        "unit_secures_asset_if_action_unit_controls_target_at_turn_end",
    ),
    "sensor-sweep-extract-relic": (
        "primary-extract-relic",
        "Sensor Sweep",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_range_of_central_objective",
        (
            "central_objective_and_opponent_operation_marker_requires_more_than_one_"
            "opponent_marker_remaining"
        ),
        "once_per_turn",
        (
            "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_"
            "objective_at_turn_end"
        ),
    ),
    "sensor-sweep-locate-and-deny": (
        "primary-locate-and-deny",
        "Sensor Sweep",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_range_of_central_objective",
        (
            "central_objective_and_friendly_operation_marker_requires_more_than_one_"
            "friendly_marker_remaining"
        ),
        "once_per_turn",
        (
            "remove_one_friendly_operation_marker_if_action_unit_controls_selected_central_"
            "objective_at_turn_end"
        ),
    ),
    "surveil-enemy-unit": (
        "primary-surveil-the-foe",
        "Surveil the Foe",
        "shooting",
        "shooting_phase_action_start",
        "immediate",
        "active_player_unit",
        "visible_enemy_unit_within_18_not_surveilled_this_turn",
        "unlimited",
        "enemy_unit_becomes_surveilled_until_turn_end",
    ),
    "triangulate-objective": (
        "primary-triangulation",
        "Triangulate",
        "shooting",
        "shooting_phase_action_start_from_battle_round_two",
        "turn_end",
        "active_player_unit",
        "objective_marker_excluding_home",
        "once_per_turn",
        "objective_becomes_triangulated_if_action_unit_controls_target_at_turn_end",
    ),
    "vanguard-operation": (
        "primary-vanguard-operation",
        "Vanguard Operation",
        "shooting",
        "shooting_phase_action_start",
        "turn_end",
        "active_player_unit_within_terrain_area_in_enemy_territory",
        "terrain_area_in_enemy_territory",
        "once_per_turn",
        "unit_performs_vanguard_operation_if_no_enemy_units_in_terrain_area_at_turn_end",
    ),
}
_EXPECTED_PRIMARY_STATE_RULE_IDS: Final = (
    "consecrate-destroyer-becomes-consecration-unit",
    "surveil-remove-operation-markers-after-move",
)
_EXPECTED_PRIMARY_STATE_RULE_CLAUSES: Final = {
    "consecrate-destroyer-becomes-consecration-unit": (
        "primary-consecrate",
        "friendly_rules_unit_destroys_one_or_more_units",
        "destroying_friendly_rules_unit",
        "unit_becomes_consecration_unit",
        "until_consumed",
    ),
    "surveil-remove-operation-markers-after-move": (
        "primary-surveil-the-foe",
        "friendly_rules_unit_move_end",
        ("moving_friendly_rules_unit_within_range_of_objective_with_opponent_operation_markers"),
        "remove_all_opponent_operation_markers_from_each_in_range_objective",
        "immediate",
    ),
}
_EXPECTED_PRIMARY_CHOICE_RULE_IDS: Final = (
    "consecrate-objective-at-turn-end",
    "locate-and-deny-operation-marker-setup",
    "punishment-condemn-enemy-units",
)
_EXPECTED_PRIMARY_CHOICE_RULE_CLAUSES: Final = {
    "consecrate-objective-at-turn-end": (
        "primary-consecrate",
        "own_turn_end",
        "each_friendly_consecration_unit",
        "objective_within_subject_range_excluding_home_not_consecrated",
        "optional_up_to_one_per_subject",
        0,
        1,
        None,
        "place_friendly_operation_marker_consecrate_objective_and_consume_unit_status",
        "persistent",
    ),
    "locate-and-deny-operation-marker-setup": (
        "primary-locate-and-deny",
        "battle_start",
        None,
        "terrain_area_outside_own_deployment_zone",
        "exactly_five_or_all_available_when_fewer",
        0,
        5,
        None,
        "place_one_friendly_operation_marker_in_each_selected_terrain_area",
        "persistent",
    ),
    "punishment-condemn-enemy-units": (
        "primary-punishment",
        "own_turn_start",
        None,
        ("enemy_battlefield_unit_within_objective_range_or_destroyed_friendly_unit_previous_turn"),
        "one_to_three_or_exactly_one_fallback_when_no_primary_targets",
        1,
        3,
        "enemy_battlefield_unit",
        "selected_enemy_units_become_condemned",
        "until_start_of_own_next_turn",
    ),
}


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


class EventCompanionScoringLimitSourceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    source_pdf_filename: str
    source_pdf_sha256: str
    source_pages: tuple[int, ...]
    authority_scope: str
    primary_max_vp_per_battle_round: int
    end_of_battle_primary_vp_exempt: bool


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
    turn_scope: str
    source_kind: str
    victory_points: int
    cap: None
    condition: str
    resolution_mode: str
    resolution_group_id: str | None


class PrimaryMissionScoringArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    primary_mission_id: str
    mission_name: str
    engine_support_status: str
    scoring_kind: str
    max_vp_per_turn: int
    vp_per_controlled_objective: None
    scoring_rules: tuple[PrimaryScoringRuleArtifact, ...]


class PrimaryMissionActionArtifact(
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


class PrimaryMissionStateRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    state_rule_id: str
    primary_mission_id: str
    trigger_timing: str
    subject_policy: str
    effect_descriptor: str
    effect_duration: str
    engine_exposure_status: str
    source_id: str


class PrimaryMissionChoiceRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    choice_rule_id: str
    primary_mission_id: str
    trigger_timing: str
    subject_policy: str | None
    target_policy: str
    selection_policy: str
    minimum_selections: int
    maximum_selections: int
    fallback_target_policy: str | None
    effect_descriptor: str
    effect_duration: str
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
    scoring_limit_source: EventCompanionScoringLimitSourceArtifact
    primary_missions: tuple[PrimaryMissionScoringArtifact, ...]
    primary_mission_actions: tuple[PrimaryMissionActionArtifact, ...]
    primary_mission_state_rules: tuple[PrimaryMissionStateRuleArtifact, ...]
    primary_mission_choice_rules: tuple[PrimaryMissionChoiceRuleArtifact, ...]
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
        _validate_scoring_limit_source(self.scoring_limit_source)
        _validate_primary_missions(
            self.primary_missions,
            primary_max_vp_per_battle_round=(
                self.scoring_limit_source.primary_max_vp_per_battle_round
            ),
        )
        primary_mission_ids = frozenset(
            mission.primary_mission_id for mission in self.primary_missions
        )
        _validate_primary_mission_actions(
            self.primary_mission_actions,
            primary_mission_ids=primary_mission_ids,
        )
        _validate_primary_mission_state_rules(
            self.primary_mission_state_rules,
            primary_mission_ids=primary_mission_ids,
        )
        _validate_primary_mission_choice_rules(
            self.primary_mission_choice_rules,
            primary_mission_ids=primary_mission_ids,
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
            "All 25 Primary mission scoring records, 10 executable Primary Mission Action "
            "descriptors, 2 Primary mission state rules, and 3 Primary mission choice rules"
        ),
        "not_committed_transcription_review_only",
        "all_primary_scoring_action_state_and_choice_descriptors",
        "meatgrinder_scoring_clauses_only",
        "reviewed_with_project_owner_supplied_step4_clauses",
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring authoritative provenance drifted."
        )
    expected_reviews = (
        (107, "c0fe665249a4a39e5bf5ca19c38bb18b4a9dc56a"),
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


def _validate_scoring_limit_source(source: EventCompanionScoringLimitSourceArtifact) -> None:
    if (
        source.source_pdf_filename,
        source.source_pdf_sha256,
        source.source_pages,
        source.authority_scope,
        source.primary_max_vp_per_battle_round,
        source.end_of_battle_primary_vp_exempt,
    ) != (
        "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf",
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20",
        (2, 4),
        "primary_battle_round_vp_cap_and_end_of_battle_exemption",
        15,
        True,
    ):
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion Primary scoring-limit provenance drifted."
        )


def _validate_primary_missions(
    missions: tuple[PrimaryMissionScoringArtifact, ...],
    *,
    primary_max_vp_per_battle_round: int,
) -> None:
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
    grouped_rules: dict[str, list[tuple[str, PrimaryScoringRuleArtifact]]] = {}
    total_rule_count = 0
    for mission in missions:
        identifiers("primary_mission_id", mission.primary_mission_id)
        _validate_canonical_text("mission_name", mission.mission_name)
        if mission.max_vp_per_turn != primary_max_vp_per_battle_round:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary missions must use the source-backed 15VP "
                "per-battle-round cap."
            )
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
            if rule.resolution_group_id is not None:
                grouped_rules.setdefault(rule.resolution_group_id, []).append(
                    (mission.primary_mission_id, rule)
                )
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
    _validate_resolution_groups(grouped_rules)


def _validate_primary_scoring_rule(
    rule: PrimaryScoringRuleArtifact,
    *,
    identifiers: IdentifierValidator,
) -> None:
    identifiers("rule_id", rule.rule_id)
    identifiers("timing", rule.timing)
    if rule.timing not in _EXPECTED_TIMINGS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring timing grammar is unsupported."
        )
    identifiers("turn_scope", rule.turn_scope)
    if rule.turn_scope not in _EXPECTED_TURN_SCOPES:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring turn_scope is unsupported."
        )
    identifiers("condition", rule.condition)
    expected_turn_scope = (
        "any_player_turn"
        if rule.condition in _EXPECTED_ANY_PLAYER_TURN_CONDITIONS
        else "own_player_turn"
    )
    if rule.turn_scope != expected_turn_scope:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring turn_scope drifted from its condition."
        )
    if rule.source_kind != "primary":
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring rule source_kind must be primary."
        )
    if type(rule.victory_points) is not int or rule.victory_points <= 0:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring victory_points must be a positive integer."
        )
    if rule.resolution_mode == "independent":
        if rule.resolution_group_id is not None:
            raise EventCompanionPrimaryScoringArtifactError(
                "Independent Event Companion scoring rules cannot declare a resolution group."
            )
        return
    if rule.resolution_mode not in {"cumulative", "exclusive_highest"}:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring resolution mode is unsupported."
        )
    identifiers("resolution_group_id", rule.resolution_group_id)


def _validate_resolution_groups(
    grouped_rules: dict[str, list[tuple[str, PrimaryScoringRuleArtifact]]],
) -> None:
    actual: dict[str, tuple[str, tuple[str, ...]]] = {}
    for group_id, entries in grouped_rules.items():
        if len(entries) < 2:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring resolution groups require at least two rules."
            )
        mission_ids = {mission_id for mission_id, _rule in entries}
        timings = {rule.timing for _mission_id, rule in entries}
        source_kinds = {rule.source_kind for _mission_id, rule in entries}
        modes = {rule.resolution_mode for _mission_id, rule in entries}
        if any(len(values) != 1 for values in (mission_ids, timings, source_kinds, modes)):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion primary-scoring resolution groups must share mission, timing, "
                "source kind, and mode."
            )
        actual[group_id] = (
            entries[0][1].resolution_mode,
            tuple(rule.rule_id for _mission_id, rule in entries),
        )
    if actual != _EXPECTED_RESOLUTION_GROUPS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion primary-scoring resolution grammar drifted."
        )


def _validate_primary_mission_actions(
    actions: tuple[PrimaryMissionActionArtifact, ...],
    *,
    primary_mission_ids: frozenset[str],
) -> None:
    if tuple(action.mission_action_id for action in actions) != _EXPECTED_PRIMARY_ACTION_IDS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion Primary Action inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion Primary Action",
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
                "Event Companion Primary Action references an unknown mission."
            )
        if action.engine_exposure_status != "engine_implemented":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary Actions must be engine-implemented."
            )
        if action.source_id != (f"{SOURCE_PACKAGE_ID}:primary-action:{action.mission_action_id}"):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary Action source ID drifted."
            )
        actual_clause = (
            action.primary_mission_id,
            action.name,
            action.start_phase,
            action.start_timing,
            action.completion_timing,
            action.eligible_unit_policy,
            action.target_policy,
            action.use_limit,
            action.effect_descriptor,
        )
        if actual_clause != _EXPECTED_PRIMARY_ACTION_CLAUSES[action.mission_action_id]:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary Action clauses drifted."
            )


def _validate_primary_mission_state_rules(
    rules: tuple[PrimaryMissionStateRuleArtifact, ...],
    *,
    primary_mission_ids: frozenset[str],
) -> None:
    if tuple(rule.state_rule_id for rule in rules) != _EXPECTED_PRIMARY_STATE_RULE_IDS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion Primary state-rule inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion Primary state rule",
    )
    for rule in rules:
        for field_name, value in (
            ("state_rule_id", rule.state_rule_id),
            ("primary_mission_id", rule.primary_mission_id),
            ("trigger_timing", rule.trigger_timing),
            ("subject_policy", rule.subject_policy),
            ("effect_descriptor", rule.effect_descriptor),
            ("effect_duration", rule.effect_duration),
        ):
            identifiers(field_name, value)
        if rule.primary_mission_id not in primary_mission_ids:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary state rule references an unknown mission."
            )
        if rule.engine_exposure_status != "engine_implemented":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary state rules must be engine-implemented."
            )
        if rule.source_id != f"{SOURCE_PACKAGE_ID}:primary-state-rule:{rule.state_rule_id}":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary state-rule source ID drifted."
            )
        actual_clause = (
            rule.primary_mission_id,
            rule.trigger_timing,
            rule.subject_policy,
            rule.effect_descriptor,
            rule.effect_duration,
        )
        if actual_clause != _EXPECTED_PRIMARY_STATE_RULE_CLAUSES[rule.state_rule_id]:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary state-rule clauses drifted."
            )


def _validate_primary_mission_choice_rules(
    rules: tuple[PrimaryMissionChoiceRuleArtifact, ...],
    *,
    primary_mission_ids: frozenset[str],
) -> None:
    if tuple(rule.choice_rule_id for rule in rules) != _EXPECTED_PRIMARY_CHOICE_RULE_IDS:
        raise EventCompanionPrimaryScoringArtifactError(
            "Event Companion Primary choice-rule inventory or order drifted."
        )
    identifiers = IdentifierValidator(
        error_factory=EventCompanionPrimaryScoringArtifactError,
        message_prefix="Event Companion Primary choice rule",
    )
    for rule in rules:
        for field_name, value in (
            ("choice_rule_id", rule.choice_rule_id),
            ("primary_mission_id", rule.primary_mission_id),
            ("trigger_timing", rule.trigger_timing),
            ("target_policy", rule.target_policy),
            ("selection_policy", rule.selection_policy),
            ("effect_descriptor", rule.effect_descriptor),
            ("effect_duration", rule.effect_duration),
        ):
            identifiers(field_name, value)
        if rule.subject_policy is not None:
            identifiers("subject_policy", rule.subject_policy)
        if rule.fallback_target_policy is not None:
            identifiers("fallback_target_policy", rule.fallback_target_policy)
        if (
            type(rule.minimum_selections) is not int
            or type(rule.maximum_selections) is not int
            or rule.minimum_selections < 0
            or rule.maximum_selections < rule.minimum_selections
        ):
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary choice-rule selection bounds are invalid."
            )
        if rule.primary_mission_id not in primary_mission_ids:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary choice rule references an unknown mission."
            )
        if rule.engine_exposure_status != "engine_implemented":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary choice rules must be engine-implemented."
            )
        if rule.source_id != f"{SOURCE_PACKAGE_ID}:primary-choice-rule:{rule.choice_rule_id}":
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary choice-rule source ID drifted."
            )
        actual_clause = (
            rule.primary_mission_id,
            rule.trigger_timing,
            rule.subject_policy,
            rule.target_policy,
            rule.selection_policy,
            rule.minimum_selections,
            rule.maximum_selections,
            rule.fallback_target_policy,
            rule.effect_descriptor,
            rule.effect_duration,
        )
        if actual_clause != _EXPECTED_PRIMARY_CHOICE_RULE_CLAUSES[rule.choice_rule_id]:
            raise EventCompanionPrimaryScoringArtifactError(
                "Event Companion Primary choice-rule clauses drifted."
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
    "EventCompanionScoringLimitSourceArtifact",
    "PrimaryMissionActionArtifact",
    "PrimaryMissionChoiceRuleArtifact",
    "PrimaryMissionScoringArtifact",
    "PrimaryMissionStateRuleArtifact",
    "PrimaryScoringRuleArtifact",
    "engine_implemented_primary_mission_ids",
    "event_companion_primary_scoring_artifact",
    "event_companion_primary_scoring_artifact_from_json_bytes",
    "validate_event_companion_primary_scoring_artifact_bytes",
)
