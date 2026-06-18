from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.rules_units import rules_unit_owner_player_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:death_guard:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:death_guard:army_rule:nurgles_gift"
SOURCE_RULE_ID = "phase17f:phase17e:death-guard:army-rule"
DEATH_GUARD_FACTION_ID = "death-guard"
DEATH_GUARD_FACTION_KEYWORD = "DEATH GUARD"
NURGLES_GIFT_STATE_KIND = "death_guard_nurgles_gift_plague_selection"
CONTAGION_RANGE_CAP_AFTER_MODIFIERS_INCHES = 12.0


class NurglesGiftPlague(StrEnum):
    SKULLSQUIRM_BLIGHT = "skullsquirm_blight"
    RATTLEJOINT_AGUE = "rattlejoint_ague"
    SCABROUS_SOULROT = "scabrous_soulrot"


_PLAGUE_LABELS = {
    NurglesGiftPlague.SKULLSQUIRM_BLIGHT: "Skullsquirm Blight",
    NurglesGiftPlague.RATTLEJOINT_AGUE: "Rattlejoint Ague",
    NurglesGiftPlague.SCABROUS_SOULROT: "Scabrous Soulrot",
}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_formation_hook_bindings=(
            BattleFormationHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=plague_selection_request,
                result_handler=apply_plague_selection_result,
            ),
        ),
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id=f"{HOOK_ID}:toughness",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_toughness_modifier,
            ),
            UnitCharacteristicModifierBinding(
                modifier_id=f"{HOOK_ID}:leadership",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_leadership_modifier,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=f"{HOOK_ID}:melee-hit-roll",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_hit_roll_modifier_handler,
            ),
        ),
        save_option_modifier_bindings=(
            SaveOptionModifierBinding(
                modifier_id=f"{HOOK_ID}:armour-save-option",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_save_option_modifier,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id=f"{HOOK_ID}:movement-budget",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_movement_budget_modifier,
            ),
        ),
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id=f"{HOOK_ID}:objective-control",
                source_id=SOURCE_RULE_ID,
                handler=nurgles_gift_objective_control_modifier,
            ),
        ),
    )


def plague_selection_request(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleFormationRequestContext:
        raise GameLifecycleError("Death Guard plague selection requires request context.")
    for army in _death_guard_armies(context.state):
        if selected_plague_for_player(context.state, player_id=army.player_id) is not None:
            continue
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload={
                "game_id": context.state.game_id,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "faction_id": DEATH_GUARD_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "state_kind": NURGLES_GIFT_STATE_KIND,
            },
            options=_plague_selection_options(player_id=army.player_id),
        )
    return None


def apply_plague_selection_result(context: BattleFormationResultContext) -> bool:
    if type(context) is not BattleFormationResultContext:
        raise GameLifecycleError("Death Guard plague selection requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Death Guard plague selection requires an actor.")
    player_id = result.actor_id
    if not _player_has_death_guard_army(state=context.state, player_id=player_id):
        raise GameLifecycleError("Death Guard plague selection actor does not own Death Guard.")
    if selected_plague_for_player(context.state, player_id=player_id) is not None:
        raise GameLifecycleError("Death Guard plague selection is already recorded.")
    payload = _payload_object(result.payload)
    plague = _plague_from_token(_payload_string(payload, key="plague_id"))
    state_record = FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:plague-selection",
        player_id=player_id,
        faction_id=DEATH_GUARD_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=NURGLES_GIFT_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=result.result_id,
        payload=validate_json_value(
            {
                "plague_id": plague.value,
                "plague_label": _PLAGUE_LABELS[plague],
                "selected_option_id": result.selected_option_id,
                "hook_id": HOOK_ID,
                "contagion_range_cap_after_modifiers_inches": (
                    CONTAGION_RANGE_CAP_AFTER_MODIFIERS_INCHES
                ),
                "rules_update_source": (
                    "warhammer_40000_11th:death_guard:faction_pack:rules_updates:nurgles_gift"
                ),
            }
        ),
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        "death_guard_nurgles_gift_plague_selected",
        {
            "game_id": context.state.game_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "plague_id": plague.value,
            "faction_rule_state": validate_json_value(state_record.to_payload()),
        },
    )
    return True


def selected_plague_for_player(
    state: GameState,
    *,
    player_id: str,
) -> NurglesGiftPlague | None:
    _validate_game_state(state)
    states = state.faction_rule_states_for_player(
        player_id=player_id,
        state_kind=NURGLES_GIFT_STATE_KIND,
    )
    if len(states) > 1:
        raise GameLifecycleError("Death Guard plague lookup found multiple selections.")
    if not states:
        return None
    payload = _payload_object(states[0].payload)
    return _plague_from_token(_payload_string(payload, key="plague_id"))


def contagion_range_inches(
    *,
    battle_round: int,
    modifier_inches: float = 0.0,
) -> float:
    if type(battle_round) is not int:
        raise GameLifecycleError("Contagion Range battle_round must be an int.")
    if battle_round <= 0:
        raise GameLifecycleError("Contagion Range requires a positive battle round.")
    if type(modifier_inches) not in {int, float}:
        raise GameLifecycleError("Contagion Range modifier_inches must be numeric.")
    base = _contagion_range_base_inches(battle_round)
    return min(
        base + float(modifier_inches),
        CONTAGION_RANGE_CAP_AFTER_MODIFIERS_INCHES,
    )


def nurgles_gift_modified_toughness(
    *,
    state: GameState,
    target_unit_instance_id: str,
    base_toughness: int,
) -> int:
    if type(base_toughness) is not int:
        raise GameLifecycleError("Nurgle's Gift toughness requires an int.")
    if base_toughness <= 0:
        raise GameLifecycleError("Nurgle's Gift toughness requires a positive value.")
    if afflicting_death_guard_player_ids(state, target_unit_instance_id=target_unit_instance_id):
        return max(1, base_toughness - 1)
    return base_toughness


def nurgles_gift_toughness_modifier(context: UnitCharacteristicModifierContext) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Nurgle's Gift toughness modifier requires context.")
    if context.characteristic is not Characteristic.TOUGHNESS:
        return context.current_value
    return nurgles_gift_modified_toughness(
        state=context.state,
        target_unit_instance_id=context.unit_instance_id,
        base_toughness=context.current_value,
    )


def nurgles_gift_hit_roll_modifier(
    *,
    state: GameState,
    attacker_model_instance_id: str,
    source_phase: BattlePhase,
) -> int:
    if type(source_phase) is not BattlePhase:
        raise GameLifecycleError("Nurgle's Gift hit modifier requires a BattlePhase.")
    if source_phase is not BattlePhase.FIGHT:
        return 0
    unit, _owner = _unit_for_model(state=state, model_instance_id=attacker_model_instance_id)
    for player_id in afflicting_death_guard_player_ids(
        state,
        target_unit_instance_id=unit.unit_instance_id,
    ):
        if selected_plague_for_player(state, player_id=player_id) is (
            NurglesGiftPlague.SKULLSQUIRM_BLIGHT
        ):
            return -1
    return 0


def nurgles_gift_hit_roll_modifier_handler(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Nurgle's Gift hit roll modifier requires context.")
    return nurgles_gift_hit_roll_modifier(
        state=context.state,
        attacker_model_instance_id=context.attacker_model_instance_id,
        source_phase=context.source_phase,
    )


def nurgles_gift_modified_save_options(
    *,
    state: GameState,
    target_unit_instance_id: str,
    save_options: tuple[SaveOption, ...],
) -> tuple[SaveOption, ...]:
    if type(save_options) is not tuple:
        raise GameLifecycleError("Nurgle's Gift save modifier requires save options tuple.")
    if not _unit_afflicted_by_plague(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
        plague=NurglesGiftPlague.RATTLEJOINT_AGUE,
    ):
        return save_options
    modified: list[SaveOption] = []
    for option in save_options:
        if type(option) is not SaveOption:
            raise GameLifecycleError("Nurgle's Gift save options must contain SaveOption.")
        if option.save_kind is not SaveKind.ARMOUR:
            modified.append(option)
            continue
        modified.append(
            replace(
                option,
                characteristic_target_number=option.characteristic_target_number + 1,
                target_number=option.target_number + 1,
                source_rule_ids=tuple(dict.fromkeys((*option.source_rule_ids, SOURCE_RULE_ID))),
            )
        )
    return tuple(modified)


def nurgles_gift_save_option_modifier(
    context: SaveOptionModifierContext,
) -> tuple[SaveOption, ...]:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Nurgle's Gift save option modifier requires context.")
    return nurgles_gift_modified_save_options(
        state=context.state,
        target_unit_instance_id=context.target_unit_instance_id,
        save_options=context.save_options,
    )


def nurgles_gift_modified_leadership_target(
    *,
    state: GameState,
    unit_instance_id: str,
    base_leadership: int,
) -> int:
    if type(base_leadership) is not int:
        raise GameLifecycleError("Nurgle's Gift Leadership requires an int.")
    if base_leadership <= 0:
        raise GameLifecycleError("Nurgle's Gift Leadership requires a positive value.")
    if _unit_afflicted_by_plague(
        state=state,
        target_unit_instance_id=unit_instance_id,
        plague=NurglesGiftPlague.SCABROUS_SOULROT,
    ):
        return base_leadership + 1
    return base_leadership


def nurgles_gift_leadership_modifier(context: UnitCharacteristicModifierContext) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Nurgle's Gift Leadership modifier requires context.")
    if context.characteristic is not Characteristic.LEADERSHIP:
        return context.current_value
    return nurgles_gift_modified_leadership_target(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        base_leadership=context.current_value,
    )


def nurgles_gift_modified_objective_control(
    *,
    state: GameState,
    unit_instance_id: str,
    base_objective_control: int,
) -> int:
    if type(base_objective_control) is not int:
        raise GameLifecycleError("Nurgle's Gift Objective Control requires an int.")
    if base_objective_control < 0:
        raise GameLifecycleError("Nurgle's Gift Objective Control cannot be negative.")
    if _unit_afflicted_by_plague(
        state=state,
        target_unit_instance_id=unit_instance_id,
        plague=NurglesGiftPlague.SCABROUS_SOULROT,
    ):
        return max(1, base_objective_control - 1)
    return base_objective_control


def nurgles_gift_objective_control_modifier(context: ObjectiveControlModifierContext) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Nurgle's Gift Objective Control modifier requires context.")
    return nurgles_gift_modified_objective_control(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        base_objective_control=context.current_objective_control,
    )


def nurgles_gift_modified_movement_inches(
    *,
    state: GameState,
    unit_instance_id: str,
    base_movement_inches: float,
) -> float:
    if type(base_movement_inches) not in {int, float}:
        raise GameLifecycleError("Nurgle's Gift Movement requires numeric inches.")
    movement = float(base_movement_inches)
    if movement < 0.0:
        raise GameLifecycleError("Nurgle's Gift Movement cannot be negative.")
    if _unit_afflicted_by_plague(
        state=state,
        target_unit_instance_id=unit_instance_id,
        plague=NurglesGiftPlague.SCABROUS_SOULROT,
    ):
        return max(0.0, movement - 1.0)
    return movement


def nurgles_gift_movement_budget_modifier(context: MovementBudgetModifierContext) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Nurgle's Gift Movement modifier requires context.")
    return nurgles_gift_modified_movement_inches(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        base_movement_inches=context.current_movement_inches,
    )


def afflicting_death_guard_player_ids(
    state: GameState,
    *,
    target_unit_instance_id: str,
) -> tuple[str, ...]:
    _validate_game_state(state)
    eligible_armies = tuple(
        army
        for army in _death_guard_armies(state)
        if selected_plague_for_player(state, player_id=army.player_id) is not None
    )
    if not eligible_armies:
        return ()
    target_owner = rules_unit_owner_player_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    afflicting: list[str] = []
    for army in eligible_armies:
        if army.player_id == target_owner:
            continue
        if _unit_within_contagion_range(
            state=state,
            death_guard_army=army,
            target_unit_instance_id=target_unit_instance_id,
        ):
            afflicting.append(army.player_id)
    return tuple(sorted(afflicting))


def _unit_afflicted_by_plague(
    *,
    state: GameState,
    target_unit_instance_id: str,
    plague: NurglesGiftPlague,
) -> bool:
    for player_id in afflicting_death_guard_player_ids(
        state,
        target_unit_instance_id=target_unit_instance_id,
    ):
        if selected_plague_for_player(state, player_id=player_id) is plague:
            return True
    return False


def _plague_selection_options(*, player_id: str) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for plague in NurglesGiftPlague:
        options.append(
            DecisionOption(
                option_id=f"death_guard:nurgles_gift:{plague.value}",
                label=_PLAGUE_LABELS[plague],
                payload={
                    "submission_kind": "death_guard_nurgles_gift_plague_selection",
                    "player_id": player_id,
                    "faction_id": DEATH_GUARD_FACTION_ID,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": HOOK_ID,
                    "state_kind": NURGLES_GIFT_STATE_KIND,
                    "plague_id": plague.value,
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                },
            )
        )
    return tuple(options)


def _contagion_range_base_inches(battle_round: int) -> float:
    if battle_round == 1:
        return 3.0
    if battle_round == 2:
        return 6.0
    return 9.0


def _unit_within_contagion_range(
    *,
    state: GameState,
    death_guard_army: ArmyDefinition,
    target_unit_instance_id: str,
) -> bool:
    target_models = _unit_geometry_models(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    if not target_models:
        return False
    range_inches = contagion_range_inches(battle_round=state.battle_round)
    for source_unit in death_guard_army.units:
        if not _unit_has_faction_keyword(source_unit, DEATH_GUARD_FACTION_KEYWORD):
            continue
        for source_model in _unit_geometry_models(
            state=state,
            unit_instance_id=source_unit.unit_instance_id,
        ):
            if any(
                shapely_backend.base_footprint_distance(
                    source_model.base,
                    source_model.pose,
                    target_model.base,
                    target_model.pose,
                )
                <= range_inches
                for target_model in target_models
            ):
                return True
    return False


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Nurgle's Gift requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    try:
        unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _unit_for_model(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[UnitInstance, str]:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                return unit, army.player_id
    raise GameLifecycleError("Nurgle's Gift model is unknown.")


def _death_guard_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == DEATH_GUARD_FACTION_ID
    )


def _player_has_death_guard_army(*, state: GameState, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    return any(army.player_id == requested_player_id for army in _death_guard_armies(state))


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _plague_from_token(token: object) -> NurglesGiftPlague:
    if type(token) is NurglesGiftPlague:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Nurgle's Gift plague token must be a string.")
    try:
        return NurglesGiftPlague(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Nurgle's Gift plague: {token}.") from exc


def _payload_object(payload: JsonValue) -> Mapping[str, JsonValue]:
    if not isinstance(payload, Mapping):
        raise GameLifecycleError("Nurgle's Gift payload must be an object.")
    return cast(Mapping[str, JsonValue], payload)


def _payload_string(payload: Mapping[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Nurgle's Gift payload missing string field {key}.")
    return value


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Nurgle's Gift {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Nurgle's Gift {field_name} must not be empty.")
    return stripped


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState as RuntimeGameState

    if type(state) is not RuntimeGameState:
        raise GameLifecycleError("Nurgle's Gift requires GameState.")
