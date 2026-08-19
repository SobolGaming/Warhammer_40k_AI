from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
)
from warhammer40k_core.engine.primary_scoring_turn_scope import (
    primary_scoring_rule_applies_at_record,
)


def required_primary_scoring_boundary_kinds(
    *,
    policies: MissionScoringPolicies,
    record: ObjectiveControlRecord,
    turn_order: tuple[str, ...],
) -> tuple[PrimaryScoringBoundaryKind, ...]:
    """Derive the evidence rows required for one stored objective-control record."""
    if type(policies) is not MissionScoringPolicies:
        raise GameLifecycleError("Primary scoring boundary inventory requires policies.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring boundary inventory requires an ObjectiveControlRecord."
        )
    ordered_players = _identifier_tuple("turn_order", turn_order)
    if record.active_player_id not in ordered_players:
        raise GameLifecycleError(
            "Primary scoring boundary active player is missing from turn_order."
        )
    required: list[PrimaryScoringBoundaryKind] = []
    if any(
        _policy_has_rule_at_record(policy=policy, record=record, end_of_battle=False)
        for policy in policies.player_policies
    ):
        required.append(PrimaryScoringBoundaryKind.ORDINARY)
    if _is_final_end_of_battle_record(
        policies=policies,
        record=record,
        final_player_id=ordered_players[-1],
    ) and any(
        _policy_has_rule_at_record(policy=policy, record=record, end_of_battle=True)
        for policy in policies.player_policies
    ):
        required.append(PrimaryScoringBoundaryKind.END_OF_BATTLE)
    return tuple(required)


def _policy_has_rule_at_record(
    *,
    policy: object,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> bool:
    from warhammer40k_core.engine.scoring import MissionScoringPolicy

    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("Primary scoring boundary inventory requires a player policy.")
    return any(
        primary_scoring_rule_applies_at_record(
            timing=rule.timing,
            condition=rule.condition,
            record=record,
            scoring_player_id=policy.player_id,
            primary_scoring_phase=policy.primary_scoring_phase,
            primary_scoring_timing=policy.primary_scoring_timing,
            game_length_battle_rounds=policy.game_length_battle_rounds,
            end_of_battle=end_of_battle,
        )
        for rule in policy.primary_scoring_rules
    )


def _is_final_end_of_battle_record(
    *,
    policies: MissionScoringPolicies,
    record: ObjectiveControlRecord,
    final_player_id: str,
) -> bool:
    return (
        record.battle_round == policies.game_length_battle_rounds
        and record.active_player_id == final_player_id
        and record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )


def _identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple with at least two values.")
    raw_values = cast(tuple[object, ...], values)
    if len(raw_values) < 2:
        raise GameLifecycleError(f"{field_name} must be a tuple with at least two values.")
    identifiers = tuple(_identifier(field_name, value) for value in raw_values)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = ("required_primary_scoring_boundary_kinds",)
