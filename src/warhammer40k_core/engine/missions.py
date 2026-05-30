from __future__ import annotations

import hashlib
import json
from typing import cast

from warhammer40k_core.core.missions import (
    MissionScoringRuleDefinition,
    PrimaryMissionDefinition,
    SecondaryMissionAvailability,
)
from warhammer40k_core.core.ruleset_descriptor import reserve_destruction_timing_kind_from_token
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveDestructionTimingPolicy
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    SecondaryMissionScoringRule,
    VictoryPointSourceKind,
    objective_control_timing_from_token,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack

_CONTROL_OBJECTIVES_PRIMARY_SCORING_KIND = "control_objectives"
_SUPPORTED_CONTROL_OBJECTIVE_PRIMARY_CONDITIONS = frozenset(
    (
        "each_controlled_objective",
        "each_controlled_objective_from_battle_round_two",
    )
)


def mission_scoring_policy_from_setup(mission_setup: MissionSetup) -> MissionScoringPolicy:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Mission scoring policy requires MissionSetup.")
    mission_pack = chapter_approved_2025_26_mission_pack()
    if mission_setup.mission_pack_id != mission_pack.mission_pack_id:
        raise GameLifecycleError("Unsupported mission pack for scoring policy.")
    primary = None
    for mission in mission_pack.primary_missions:
        if mission.primary_mission_id == mission_setup.primary_mission_id:
            primary = mission
            break
    if primary is None:
        raise GameLifecycleError("Primary mission is missing from mission pack.")
    if primary.max_vp_per_turn is None:
        raise GameLifecycleError("Supported primary scoring policy requires a per-turn VP cap.")
    if primary.scoring_kind != _CONTROL_OBJECTIVES_PRIMARY_SCORING_KIND:
        raise GameLifecycleError(
            f"Unsupported primary mission scoring policy: {mission_setup.primary_mission_id}."
        )
    primary_rule = _supported_control_objective_primary_rule(primary)
    primary_vp = _required_scoring_int(
        "Supported primary scoring rule requires VP data.",
        primary_rule.victory_points,
    )
    primary_cap = _required_scoring_int(
        "Supported primary scoring rule requires cap data.",
        primary_rule.cap,
    )
    scoring = mission_pack.scoring
    caps = mission_pack.scoring_caps
    return MissionScoringPolicy(
        mission_pack_id=mission_setup.mission_pack_id,
        primary_mission_id=mission_setup.primary_mission_id,
        game_length_battle_rounds=scoring.game_length_battle_rounds,
        primary_scoring_phase=scoring.primary_scoring_phase,
        primary_scoring_timing=objective_control_timing_from_token(scoring.primary_scoring_timing),
        primary_scoring_rule_id=primary_rule.rule_id,
        primary_scoring_rule_condition=primary_rule.condition,
        primary_scoring_rule_source_id=primary_rule.source_id,
        primary_vp_per_controlled_objective=primary_vp,
        primary_max_vp_per_turn=primary_cap,
        secondary_vp_per_score=scoring.secondary_vp_per_score,
        secondary_scoring_rules=_secondary_scoring_rules_from_mission_pack(mission_pack),
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
        source_id=f"{mission_setup.source_id}:scoring:{mission_setup.primary_mission_id}",
    )


def _supported_control_objective_primary_rule(
    primary: PrimaryMissionDefinition,
) -> MissionScoringRuleDefinition:
    rules = tuple(
        rule
        for rule in primary.scoring_rules
        if rule.source_kind == "primary" and rule.timing == "command_phase"
    )
    if len(rules) != 1:
        raise GameLifecycleError("Supported primary scoring policy requires one command rule.")
    rule = rules[0]
    if rule.victory_points is None or rule.cap is None:
        raise GameLifecycleError("Supported primary scoring rule requires VP and cap data.")
    if primary.vp_per_controlled_objective != rule.victory_points:
        raise GameLifecycleError("Primary mission VP data does not match its scoring rule.")
    if primary.max_vp_per_turn != rule.cap:
        raise GameLifecycleError("Primary mission cap data does not match its scoring rule.")
    if rule.condition not in _SUPPORTED_CONTROL_OBJECTIVE_PRIMARY_CONDITIONS:
        raise GameLifecycleError("Unsupported primary scoring rule condition.")
    return rule


def _required_scoring_int(message: str, value: int | None) -> int:
    if value is None:
        raise GameLifecycleError(message)
    return value


def _secondary_scoring_rules_from_mission_pack(
    mission_pack: object,
) -> tuple[SecondaryMissionScoringRule, ...]:
    from warhammer40k_core.core.missions import MissionPackDefinition

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
                    victory_points=rule.victory_points,
                    condition=rule.condition,
                    rule_id=rule.rule_id,
                    source_id=rule.source_id,
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
    mission_pack = chapter_approved_2025_26_mission_pack()
    if mission_setup.mission_pack_id != mission_pack.mission_pack_id:
        raise GameLifecycleError("Unsupported mission pack for tactical secondary draw.")
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


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


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
