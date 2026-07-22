from __future__ import annotations

import hashlib
import json
from typing import cast

from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionScoringRuleDefinition,
    PrimaryMissionDefinition,
    SecondaryMissionAvailability,
)
from warhammer40k_core.core.ruleset_descriptor import reserve_destruction_timing_kind_from_token
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveDestructionTimingPolicy
from warhammer40k_core.engine.scoring import (
    MissionActionScoringRule,
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    SecondaryMissionScoringRule,
    VictoryPointCapBucket,
    VictoryPointSourceKind,
    objective_control_timing_from_token,
)
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)

_SUPPORTED_CONTROL_OBJECTIVE_PRIMARY_CONDITIONS = frozenset(
    (
        "each_controlled_objective",
        "each_controlled_objective_from_battle_round_two",
    )
)
_SUPPORTED_STRUCTURED_PRIMARY_CONDITIONS = (
    _SUPPORTED_CONTROL_OBJECTIVE_PRIMARY_CONDITIONS
    | frozenset(
        (
            "control_one_or_more_central_objectives",
            "control_one_or_more_central_objectives_end_of_battle",
            "control_one_or_more_new_non_home_objectives",
            "control_one_or_more_non_home_objectives_from_battle_round_two",
            "each_non_home_objective_controlled_battle_rounds_two_to_four",
            "each_non_home_objective_controlled_from_battle_round_two",
            "each_non_home_objective_controlled_round_five",
            "each_terrain_area_trapped_this_turn",
            "each_trapped_objective_terrain_area_this_turn",
            "one_or_more_enemy_units_destroyed_after_starting_turn_in_trapped_terrain",
            "one_or_more_enemy_units_destroyed_this_turn",
        )
    )
)


def mission_scoring_policy_from_setup(mission_setup: MissionSetup) -> MissionScoringPolicy:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Mission scoring policy requires MissionSetup.")
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    primary = None
    for mission in mission_pack.primary_missions:
        if mission.primary_mission_id == mission_setup.primary_mission_id:
            primary = mission
            break
    if primary is None:
        raise GameLifecycleError("Primary mission is missing from mission pack.")
    primary_rules = _primary_scoring_rules_from_primary(primary)
    legacy_primary_rule = _legacy_control_objective_primary_rule(primary)
    scoring = mission_pack.scoring
    caps = mission_pack.scoring_caps
    return MissionScoringPolicy(
        mission_pack_id=mission_setup.mission_pack_id,
        primary_mission_id=mission_setup.primary_mission_id,
        game_length_battle_rounds=scoring.game_length_battle_rounds,
        primary_scoring_phase=scoring.primary_scoring_phase,
        primary_scoring_timing=objective_control_timing_from_token(scoring.primary_scoring_timing),
        primary_scoring_rule_id=(
            None if legacy_primary_rule is None else legacy_primary_rule.rule_id
        ),
        primary_scoring_rule_condition=(
            None if legacy_primary_rule is None else legacy_primary_rule.condition
        ),
        primary_scoring_rule_source_id=(
            None if legacy_primary_rule is None else legacy_primary_rule.source_id
        ),
        primary_vp_per_controlled_objective=primary.vp_per_controlled_objective,
        primary_max_vp_per_turn=primary.max_vp_per_turn,
        primary_scoring_rules=primary_rules,
        secondary_vp_per_score=scoring.secondary_vp_per_score,
        secondary_scoring_rules=_secondary_scoring_rules_from_mission_pack(mission_pack),
        mission_action_scoring_rules=_mission_action_scoring_rules_from_mission_pack(mission_pack),
        mission_action_vp=scoring.mission_action_vp,
        reserve_destruction_timing=scoring.reserve_destruction_timing,
        reserve_destruction_battle_round=scoring.reserve_destruction_battle_round,
        reserve_destruction_excludes_during_battle_strategic_reserves=(
            scoring.reserve_destruction_excludes_during_battle_strategic_reserves
        ),
        reserve_destruction_only_declare_battle_formations=(
            scoring.reserve_destruction_only_declare_battle_formations
        ),
        primary_vp_cap=scoring.primary_vp_cap,
        secondary_vp_cap=scoring.secondary_vp_cap,
        battle_ready_vp=caps.battle_ready_vp,
        total_vp_cap=scoring.total_vp_cap,
        end_of_round_scoring_windows=scoring.end_of_round_scoring_windows,
        end_of_game_scoring_windows=scoring.end_of_game_scoring_windows,
        source_id=f"{mission_setup.source_id}:scoring:{mission_setup.primary_mission_id}",
    )


def mission_pack_for_id(mission_pack_id: str) -> MissionPackDefinition:
    requested_pack_id = _validate_identifier("mission_pack_id", mission_pack_id)
    for mission_pack in _supported_mission_packs():
        if mission_pack.mission_pack_id == requested_pack_id:
            return mission_pack
    raise GameLifecycleError("Unsupported mission pack.")


def _supported_mission_packs() -> tuple[MissionPackDefinition, ...]:
    return (
        chapter_approved_2026_27_mission_pack(),
        warhammer_event_companion_2026_07_mission_pack(),
    )


def _legacy_control_objective_primary_rule(
    primary: PrimaryMissionDefinition,
) -> MissionScoringRuleDefinition | None:
    rules = tuple(
        rule
        for rule in primary.scoring_rules
        if rule.source_kind == "primary"
        and rule.timing == "command_phase"
        and rule.condition in _SUPPORTED_CONTROL_OBJECTIVE_PRIMARY_CONDITIONS
    )
    if not rules:
        return None
    if len(rules) != 1:
        raise GameLifecycleError("Legacy primary scoring snapshot requires one command rule.")
    return rules[0]


def _primary_scoring_rules_from_primary(
    primary: PrimaryMissionDefinition,
) -> tuple[PrimaryMissionScoringRule, ...]:
    if type(primary) is not PrimaryMissionDefinition:
        raise GameLifecycleError("Primary scoring rules require PrimaryMissionDefinition.")
    if primary.scoring_kind == "event_companion_primary_source_known_engine_pending":
        raise GameLifecycleError(
            "Primary mission scoring source is known but engine implementation is pending."
        )
    rules: list[PrimaryMissionScoringRule] = []
    for rule in primary.scoring_rules:
        if rule.source_kind != VictoryPointSourceKind.PRIMARY.value:
            continue
        if rule.victory_points is None:
            raise GameLifecycleError("Primary scoring rule requires VP data.")
        if rule.condition not in _SUPPORTED_STRUCTURED_PRIMARY_CONDITIONS:
            raise GameLifecycleError("Unsupported primary scoring rule condition.")
        rules.append(
            PrimaryMissionScoringRule(
                rule_id=rule.rule_id,
                timing=rule.timing,
                source_kind=VictoryPointSourceKind.PRIMARY,
                victory_points=rule.victory_points,
                cap=rule.cap,
                condition=rule.condition,
                source_id=rule.source_id,
            )
        )
    if not rules:
        raise GameLifecycleError(
            f"Unsupported primary mission scoring policy: {primary.primary_mission_id}."
        )
    return tuple(rules)


def _secondary_scoring_rules_from_mission_pack(
    mission_pack: MissionPackDefinition,
) -> tuple[SecondaryMissionScoringRule, ...]:
    if type(mission_pack) is not MissionPackDefinition:
        raise GameLifecycleError("Secondary scoring rules require MissionPackDefinition.")
    rules: list[SecondaryMissionScoringRule] = []
    for mission in mission_pack.secondary_missions:
        for rule in mission.scoring_rules:
            if rule.source_kind == VictoryPointSourceKind.FIXED_SECONDARY.value:
                source_kind = VictoryPointSourceKind.FIXED_SECONDARY
            elif rule.source_kind == VictoryPointSourceKind.TACTICAL_SECONDARY.value:
                source_kind = VictoryPointSourceKind.TACTICAL_SECONDARY
            else:
                continue
            if rule.victory_points is None:
                raise GameLifecycleError("Secondary scoring rule requires VP data.")
            rules.append(
                SecondaryMissionScoringRule(
                    secondary_mission_id=mission.secondary_mission_id,
                    source_kind=source_kind,
                    timing=rule.timing,
                    victory_points=rule.victory_points,
                    cap=rule.cap,
                    condition=rule.condition,
                    rule_id=rule.rule_id,
                    source_id=rule.source_id,
                )
            )
    return tuple(rules)


def _mission_action_scoring_rules_from_mission_pack(
    mission_pack: MissionPackDefinition,
) -> tuple[MissionActionScoringRule, ...]:
    if type(mission_pack) is not MissionPackDefinition:
        raise GameLifecycleError("Mission Action scoring rules require MissionPackDefinition.")
    rules: list[MissionActionScoringRule] = []
    for action in mission_pack.mission_actions:
        if action.mission_kind == "primary":
            cap_bucket = VictoryPointCapBucket.PRIMARY
        elif action.mission_kind == "secondary":
            cap_bucket = VictoryPointCapBucket.SECONDARY
        else:
            raise GameLifecycleError("Mission Action kind is unsupported for VP caps.")
        rules.append(
            MissionActionScoringRule(
                mission_action_id=action.mission_action_id,
                mission_id=action.mission_id,
                mission_kind=action.mission_kind,
                scoring_source_id=action.scoring_source_id,
                victory_points=action.victory_points,
                cap_bucket=cap_bucket,
                source_id=action.source_id,
            )
        )
    return tuple(rules)


def reserve_destruction_policy_from_scoring_policy(
    policy: MissionScoringPolicy,
) -> ReserveDestructionTimingPolicy:
    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("Reserve destruction scoring policy must be MissionScoringPolicy.")
    return ReserveDestructionTimingPolicy(
        timing_kind=reserve_destruction_timing_kind_from_token(policy.reserve_destruction_timing),
        battle_round=policy.reserve_destruction_battle_round,
        exclude_during_battle_strategic_reserves=(
            policy.reserve_destruction_excludes_during_battle_strategic_reserves
        ),
        only_declare_battle_formations=policy.reserve_destruction_only_declare_battle_formations,
        source_id=f"{policy.source_id}:reserve-destruction",
    )


def deterministic_tactical_secondary_draw(
    *,
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    draw_count: int,
    excluded_secondary_mission_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Tactical secondary draw requires MissionSetup.")
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_count = _validate_positive_int("draw_count", draw_count)
    excluded = _validate_identifier_tuple(
        "excluded_secondary_mission_ids",
        excluded_secondary_mission_ids,
    )
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    candidates = tuple(
        mission.secondary_mission_id
        for mission in mission_pack.secondary_missions
        if mission.availability
        in {SecondaryMissionAvailability.TACTICAL, SecondaryMissionAvailability.BOTH}
        and mission.secondary_mission_id not in excluded
    )
    if len(candidates) < requested_count:
        raise GameLifecycleError("Tactical secondary deck does not contain enough cards.")
    return tuple(
        sorted(
            candidates,
            key=lambda mission_id: _stable_draw_key(
                mission_pack_id=mission_setup.mission_pack_id,
                player_id=requested_player,
                battle_round=requested_round,
                mission_id=mission_id,
            ),
        )[:requested_count]
    )


def _stable_draw_key(
    *,
    mission_pack_id: str,
    player_id: str,
    battle_round: int,
    mission_id: str,
) -> str:
    encoded = json.dumps(
        {
            "mission_pack_id": mission_pack_id,
            "player_id": player_id,
            "battle_round": battle_round,
            "secondary_mission_id": mission_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
