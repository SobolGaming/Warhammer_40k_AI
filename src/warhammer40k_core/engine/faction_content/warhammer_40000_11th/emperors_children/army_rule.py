from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookBinding,
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.turn_start_engagement import (
    turn_start_enemy_unit_ids_for_friendly_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:emperors_children:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers"
ADVANCE_ELIGIBILITY_HOOK_ID = f"{HOOK_ID}:advance-eligibility"
FALL_BACK_ELIGIBILITY_HOOK_ID = f"{HOOK_ID}:fall-back-eligibility"
SHOOTING_TARGET_RESTRICTION_HOOK_ID = f"{HOOK_ID}:shooting-target-restriction"
CHARGE_TARGET_RESTRICTION_HOOK_ID = f"{HOOK_ID}:charge-target-restriction"
SOURCE_RULE_ID = "phase17f:phase17e:emperors-children:army-rule"
EMPERORS_CHILDREN_FACTION_ID = "emperors-children"
EMPERORS_CHILDREN_FACTION_KEYWORD = "EMPEROR'S CHILDREN"
THRILL_SEEKERS_RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:emperors_children:faction_pack:rules_updates:none"
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        advance_eligibility_hook_bindings=(
            AdvanceEligibilityHookBinding(
                hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=thrill_seekers_advance_eligibility,
            ),
        ),
        fall_back_hook_bindings=(
            FallBackEligibilityHookBinding(
                hook_id=FALL_BACK_ELIGIBILITY_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=thrill_seekers_fall_back_eligibility,
            ),
        ),
        shooting_target_restriction_hook_bindings=(
            ShootingTargetRestrictionHookBinding(
                hook_id=SHOOTING_TARGET_RESTRICTION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=thrill_seekers_shooting_target_restriction,
            ),
        ),
        charge_target_restriction_hook_bindings=(
            ChargeTargetRestrictionHookBinding(
                hook_id=CHARGE_TARGET_RESTRICTION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=thrill_seekers_charge_target_restriction,
            ),
        ),
    )


def thrill_seekers_advance_eligibility(
    context: AdvanceEligibilityContext,
) -> AdvanceEligibilityGrant | None:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Thrill Seekers Advance eligibility requires context.")
    if not _unit_has_thrill_seekers(
        context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return AdvanceEligibilityGrant(
        hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=_thrill_seekers_replay_payload(context.battle_round),
    )


def thrill_seekers_fall_back_eligibility(
    context: FallBackEligibilityContext,
) -> FallBackEligibilityGrant | None:
    if type(context) is not FallBackEligibilityContext:
        raise GameLifecycleError("Thrill Seekers Fall Back eligibility requires context.")
    if not _unit_has_thrill_seekers(
        context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return FallBackEligibilityGrant(
        hook_id=FALL_BACK_ELIGIBILITY_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=_thrill_seekers_replay_payload(context.battle_round),
    )


def thrill_seekers_shooting_target_restriction(
    context: ShootingTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Thrill Seekers shooting restriction requires context.")
    if not _thrill_seekers_restrictions_active(
        context.state,
        player_id=context.player_id,
        unit_instance_id=context.attacking_unit_instance_id,
    ):
        return None
    return _thrill_seekers_target_restriction(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        acting_unit_instance_id=context.attacking_unit_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        hook_id=SHOOTING_TARGET_RESTRICTION_HOOK_ID,
    )


def thrill_seekers_charge_target_restriction(
    context: ChargeTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ChargeTargetRestrictionContext:
        raise GameLifecycleError("Thrill Seekers charge restriction requires context.")
    if not _thrill_seekers_restrictions_active(
        context.state,
        player_id=context.player_id,
        unit_instance_id=context.charging_unit_instance_id,
    ):
        return None
    return _thrill_seekers_target_restriction(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        acting_unit_instance_id=context.charging_unit_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        hook_id=CHARGE_TARGET_RESTRICTION_HOOK_ID,
    )


def _thrill_seekers_target_restriction(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    acting_unit_instance_id: str,
    target_unit_instance_id: str,
    hook_id: str,
) -> TargetRestriction | None:
    turn_start_targets = turn_start_enemy_unit_ids_for_friendly_unit(
        state,
        player_id=player_id,
        battle_round=battle_round,
        friendly_unit_instance_id=acting_unit_instance_id,
    )
    if target_unit_instance_id in turn_start_targets:
        return TargetRestriction(
            hook_id=hook_id,
            source_id=SOURCE_RULE_ID,
            violation_code="thrill_seekers_turn_start_engagement",
            message=(
                "Thrill Seekers cannot target a unit this unit was within Engagement Range "
                "of at the start of the turn."
            ),
            replay_payload=_target_restriction_payload(
                battle_round=battle_round,
                acting_unit_instance_id=acting_unit_instance_id,
                target_unit_instance_id=target_unit_instance_id,
            ),
        )
    if _target_was_selected_by_another_unit_this_phase(
        state=state,
        acting_unit_instance_id=acting_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return TargetRestriction(
            hook_id=hook_id,
            source_id=SOURCE_RULE_ID,
            violation_code="thrill_seekers_target_already_selected",
            message=(
                "Thrill Seekers cannot target a unit that was the target of another unit's "
                "charge or attack this phase."
            ),
            replay_payload=_target_restriction_payload(
                battle_round=battle_round,
                acting_unit_instance_id=acting_unit_instance_id,
                target_unit_instance_id=target_unit_instance_id,
            ),
        )
    return None


def _target_was_selected_by_another_unit_this_phase(
    *,
    state: GameState,
    acting_unit_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    if state.current_battle_phase is BattlePhase.SHOOTING:
        shooting_state = state.shooting_phase_state
        if shooting_state is None:
            return False
        return any(
            pool.target_unit_instance_id == target_unit_instance_id
            and _unit_instance_id_for_model(
                state=state,
                model_instance_id=pool.attacker_model_instance_id,
            )
            != acting_unit_instance_id
            for pool in shooting_state.attack_pools
        )
    if state.current_battle_phase is BattlePhase.CHARGE:
        charge_state = state.charge_phase_state
        if charge_state is None:
            return False
        return any(
            unit_id != acting_unit_instance_id and target_unit_instance_id in target_ids
            for unit_id, target_ids in (
                charge_state.declared_target_unit_instance_ids_by_unit.items()
            )
        )
    return False


def _thrill_seekers_restrictions_active(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if not _unit_has_thrill_seekers(state, player_id=player_id, unit_instance_id=unit_instance_id):
        return False
    return (
        state.advanced_unit_state_for_unit(
            player_id=player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
        )
        is not None
        or state.fell_back_unit_state_for_unit(
            player_id=player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
        )
        is not None
    )


def _unit_has_thrill_seekers(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    army = _emperors_children_army_for_player(state, player_id=player_id)
    if army is None:
        return False
    unit = _unit_by_id(army, unit_instance_id=unit_instance_id)
    if unit is None:
        return False
    return _unit_has_emperors_children_keyword(unit)


def _emperors_children_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    _validate_game_state(state)
    for army in state.army_definitions:
        if army.player_id == player_id and army.detachment_selection.faction_id == (
            EMPERORS_CHILDREN_FACTION_ID
        ):
            return army
    return None


def _unit_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance | None:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Thrill Seekers unit lookup requires an ArmyDefinition.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    return None


def _unit_instance_id_for_model(*, state: GameState, model_instance_id: str) -> str:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == model_id for model in unit.own_models):
                return unit.unit_instance_id
    raise GameLifecycleError("Thrill Seekers attacker model was not found.")


def _unit_has_emperors_children_keyword(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Thrill Seekers unit keyword lookup requires a UnitInstance.")
    return _canonical_keyword(EMPERORS_CHILDREN_FACTION_KEYWORD) in {
        _canonical_keyword(keyword) for keyword in unit.faction_keywords
    }


def _thrill_seekers_replay_payload(battle_round: int) -> JsonValue:
    return validate_json_value(
        {
            "ability": "Thrill Seekers",
            "battle_round": _validate_positive_int("battle_round", battle_round),
            "rules_update_source": THRILL_SEEKERS_RULE_UPDATE_SOURCE,
        }
    )


def _target_restriction_payload(
    *,
    battle_round: int,
    acting_unit_instance_id: str,
    target_unit_instance_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "ability": "Thrill Seekers",
            "battle_round": _validate_positive_int("battle_round", battle_round),
            "acting_unit_instance_id": _validate_identifier(
                "acting_unit_instance_id",
                acting_unit_instance_id,
            ),
            "target_unit_instance_id": _validate_identifier(
                "target_unit_instance_id",
                target_unit_instance_id,
            ),
            "rules_update_source": THRILL_SEEKERS_RULE_UPDATE_SOURCE,
        }
    )


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("\u2019", "").replace("'", "").upper()


def _validate_game_state(state: GameState) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Thrill Seekers requires a GameState.")


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Thrill Seekers {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"Thrill Seekers {field_name} must be greater than zero.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Thrill Seekers {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Thrill Seekers {field_name} must not be empty.")
    return stripped
