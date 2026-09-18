from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
)
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    SetupStep,
)
from warhammer40k_core.engine.prebattle_alternation import (
    SELECT_PREBATTLE_ACTION_DECISION_TYPE as SELECT_PREBATTLE_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.prebattle_alternation import (
    SUBMIT_SCOUT_MOVE_DECISION_TYPE as SUBMIT_SCOUT_MOVE_DECISION_TYPE,
)
from warhammer40k_core.engine.prebattle_alternation import (
    SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE as SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.scout_abilities import (
    CORE_SCOUTS_SOURCE_RULE_ID,
)
from warhammer40k_core.engine.scout_abilities import (
    ScoutAbilityInstance as ScoutAbilityInstance,
)
from warhammer40k_core.engine.scout_abilities import (
    scout_ability_instances_for_rules_unit as scout_ability_instances_for_rules_unit,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.prebattle import PreBattleProposalRequest


def scout_distance_options_for_model_ids(
    *,
    model_instance_ids: tuple[str, ...],
    ability_instances: tuple[ScoutAbilityInstance, ...],
) -> tuple[float, ...]:
    from warhammer40k_core.engine.prebattle import (
        _validate_identifier_tuple,
        _validate_scout_ability_instances,
    )

    model_ids = _validate_identifier_tuple("model_instance_ids", model_instance_ids)
    if not model_ids:
        raise GameLifecycleError("Scouts distance selection requires model IDs.")
    by_model: dict[str, list[ScoutAbilityInstance]] = {model_id: [] for model_id in model_ids}
    for instance in _validate_scout_ability_instances(ability_instances):
        if instance.model_instance_id not in by_model:
            raise GameLifecycleError("ScoutAbilityInstance model is outside the selected unit.")
        by_model[instance.model_instance_id].append(instance)
    missing_model_ids = tuple(model_id for model_id, instances in by_model.items() if not instances)
    if missing_model_ids:
        raise GameLifecycleError("Every model must have a Scouts ability instance.")
    values = tuple(
        {instance.distance_inches for instance in instances} for instances in by_model.values()
    )
    shared = values[0].intersection(*values[1:])
    nonshared = values[0].union(*values[1:]) - shared
    return tuple(sorted(shared | ({min(nonshared)} if nonshared else set())))


def scout_distance_inches_for_model_ids(
    *,
    model_instance_ids: tuple[str, ...],
    ability_instances: tuple[ScoutAbilityInstance, ...],
    selected_distance_inches: float | None = None,
) -> float:
    choices = scout_distance_options_for_model_ids(
        model_instance_ids=model_instance_ids,
        ability_instances=ability_instances,
    )
    if selected_distance_inches is not None:
        if (
            type(selected_distance_inches) not in {int, float}
            or selected_distance_inches not in choices
        ):
            raise GameLifecycleError("Selected Scouts instance distance is unavailable.")
        return float(selected_distance_inches)
    if len(choices) != 1:
        raise GameLifecycleError("Duplicated Scouts values require controlling-player selection.")
    return choices[0]


def scout_selection_distance_options(payload: dict[str, JsonValue]) -> tuple[float, ...]:
    from warhammer40k_core.engine.scout_abilities import ScoutAbilityInstancePayload

    raw_models = payload["model_instance_ids"]
    raw_instances = payload["scout_ability_instances"]
    if not isinstance(raw_models, list) or not isinstance(raw_instances, list):
        raise GameLifecycleError("Scouts selection requires model and source inventories.")
    return scout_distance_options_for_model_ids(
        model_instance_ids=tuple(cast(list[str], raw_models)),
        ability_instances=tuple(
            ScoutAbilityInstance.from_payload(cast(ScoutAbilityInstancePayload, value))
            for value in raw_instances
        ),
    )


def _expand_scout_option(option: DecisionOption) -> tuple[DecisionOption, ...]:
    payload = option.payload
    if not isinstance(payload, dict) or payload.get("action_kind") not in {
        PreBattleActionKind.SCOUT_MOVE.value,
        PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE.value,
    }:
        return (option,)
    choices = scout_selection_distance_options(payload)
    return tuple(
        replace(
            option,
            option_id=option.option_id
            if len(choices) == 1
            else f"{option.option_id}:distance:{distance:g}",
            label=f"{option.label} ({distance:g} inches)",
            payload={**payload, "scout_distance_inches": distance},
        )
        for distance in choices
    )


def prebattle_action_selection_request(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> DecisionRequest:
    from warhammer40k_core.engine.prebattle import (
        SCOUT_MOVE_PROPOSAL_KIND,
        SCOUT_RESERVE_SETUP_PROPOSAL_KIND,
        _require_mission_setup,
        _validate_identifier,
        dedicated_transport_scout_move_candidates_for_player,
        prebattle_timing_state_for_state,
        scout_move_candidates_for_player,
        scout_reserve_setup_candidates_for_player,
    )

    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Pre-battle action selection requires RulesetDescriptor.")
    requested_player_id = _validate_identifier("player_id", player_id)
    timing_state = prebattle_timing_state_for_state(state, army_catalog=army_catalog)
    if requested_player_id != timing_state.next_player_id:
        raise GameLifecycleError(
            "Pre-battle action selection actor drifted from the alternation cursor."
        )
    mission_setup = _require_mission_setup(state)
    options: list[DecisionOption] = []
    for candidate in scout_reserve_setup_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"scout_reserve_setup:{candidate.unit_instance_id}",
                label=f"Scout Reserve Setup {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.SCOUT_RESERVE_SETUP,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_RESERVE_SETUP_PROPOSAL_KIND,
                ),
            )
        )
    for candidate in scout_move_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"scout_move:{candidate.unit_instance_id}",
                label=f"Scout Move {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.SCOUT_MOVE,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
                ),
            )
        )
    for candidate in dedicated_transport_scout_move_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"dedicated_transport_scout_move:{candidate.unit_instance_id}",
                label=f"Dedicated Transport Scout Move {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
                ),
            )
        )
    options.append(
        DecisionOption(
            option_id="complete_prebattle_actions",
            label="Complete Pre-battle Actions",
            payload={
                "submission_kind": SELECT_PREBATTLE_ACTION_DECISION_TYPE,
                "game_id": state.game_id,
                "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                "player_id": requested_player_id,
                "action_kind": PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value,
                "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
            },
        )
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        actor_id=requested_player_id,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": requested_player_id,
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
        options=tuple(expanded for option in options for expanded in _expand_scout_option(option)),
    )


def _prebattle_selection_payload(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    mission_setup: MissionSetup,
    view: RulesUnitView,
    setup_step: SetupStep,
    action_kind: PreBattleActionKind,
    source_rule_id: str,
    proposal_kind: str,
) -> JsonValue:
    from warhammer40k_core.engine.prebattle import (
        SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        _dedicated_transport_cargo_scout_instances,
        _deployment_zones_for_player,
    )

    if action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
        cargo_instances = _dedicated_transport_cargo_scout_instances(
            state=state,
            army_catalog=army_catalog,
            transport_view=view,
        )
        scout_instances = _dedicated_transport_move_scout_instances_for_transport(
            transport_view=view,
            cargo_instances=cargo_instances,
        )
    else:
        scout_instances = scout_ability_instances_for_rules_unit(
            state=state,
            view=view,
            army_catalog=army_catalog,
        )
    choices = (
        ()
        if not scout_instances
        else scout_distance_options_for_model_ids(
            model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
            ability_instances=scout_instances,
        )
    )
    scout_distance_inches = choices[0] if len(choices) == 1 else None
    payload = {
        "submission_kind": SELECT_REDEPLOY_UNIT_DECISION_TYPE
        if setup_step is SetupStep.REDEPLOY_UNITS
        else SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        "game_id": state.game_id,
        "player_id": view.owner_player_id,
        "setup_step": setup_step.value,
        "unit_instance_id": view.unit_instance_id,
        "is_attached_rules_unit": view.is_attached_rules_unit,
        "component_unit_instance_ids": list(view.component_unit_instance_ids),
        "model_instance_ids": [model.model_instance_id for model in view.alive_models()],
        "deployment_zone_ids": [
            zone.deployment_zone_id
            for zone in _deployment_zones_for_player(mission_setup, view.owner_player_id)
        ],
        "mission_pack_id": mission_setup.mission_pack_id,
        "deployment_map_id": mission_setup.deployment_map_id,
        "terrain_layout_id": mission_setup.terrain_layout_id,
        "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        "action_kind": action_kind.value,
        "source_rule_id": source_rule_id,
        "proposal_kind": proposal_kind,
        "scout_distance_inches": scout_distance_inches,
        "scout_ability_instances": [instance.to_payload() for instance in scout_instances],
    }
    return validate_json_value(payload)


def _proposal_request_from_selection(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selection_request: DecisionRequest,
    result: DecisionResult,
    setup_step: SetupStep,
    decision_type: str,
    placement_kind: BattlefieldPlacementKind | None,
) -> PreBattleProposalRequest:
    from warhammer40k_core.engine.prebattle import (
        PreBattleProposalRequest,
        _action_kind_from_token,
        _dedicated_transport_cargo_scout_instances,
        _deployment_zones_for_player,
        _payload_string,
        _require_mission_setup,
    )

    if result.actor_id is None:
        raise GameLifecycleError("Pre-battle selection requires actor_id.")
    if not isinstance(result.payload, dict):
        raise GameLifecycleError("Pre-battle selection payload must be an object.")
    unit_instance_id = _payload_string(result.payload, "unit_instance_id")
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    if view.owner_player_id != result.actor_id:
        raise GameLifecycleError("Pre-battle selection owner drift.")
    mission_setup = _require_mission_setup(state)
    action_kind = _action_kind_from_token(_payload_string(result.payload, "action_kind"))
    source_rule_id = _payload_string(result.payload, "source_rule_id")
    proposal_kind = _payload_string(result.payload, "proposal_kind")
    scout_distance_inches = None
    if action_kind in {
        PreBattleActionKind.SCOUT_MOVE,
        PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
    }:
        instances = scout_ability_instances_for_rules_unit(
            state=state,
            view=view,
            army_catalog=army_catalog,
        )
        if action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
            instances = _dedicated_transport_cargo_scout_instances(
                state=state,
                army_catalog=army_catalog,
                transport_view=view,
            )
        selected_distance = result.payload["scout_distance_inches"]
        if type(selected_distance) not in {int, float}:
            raise GameLifecycleError("Scout Move requires its selected finite distance.")
        scout_distance_inches = scout_distance_inches_for_model_ids(
            selected_distance_inches=cast(float, selected_distance),
            model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
            ability_instances=(
                scout_ability_instances_for_rules_unit(
                    state=state,
                    view=view,
                    army_catalog=army_catalog,
                )
                if action_kind is PreBattleActionKind.SCOUT_MOVE
                else _dedicated_transport_move_scout_instances_for_transport(
                    transport_view=view,
                    cargo_instances=instances,
                )
            ),
        )
    return PreBattleProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=decision_type,
        actor_id=result.actor_id,
        game_id=state.game_id,
        setup_step=setup_step,
        player_id=result.actor_id,
        unit_instance_id=view.unit_instance_id,
        component_unit_instance_ids=view.component_unit_instance_ids,
        model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
        proposal_kind=proposal_kind,
        action_kind=action_kind,
        source_rule_id=source_rule_id,
        deployment_zones=_deployment_zones_for_player(mission_setup, result.actor_id),
        mission_setup=mission_setup,
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        source_decision_request_id=selection_request.request_id,
        source_decision_result_id=result.result_id,
        placement_kind=placement_kind,
        scout_distance_inches=scout_distance_inches,
        context={
            "is_attached_rules_unit": view.is_attached_rules_unit,
            "source_rule_id": source_rule_id,
            "action_kind": action_kind.value,
        },
    )


__all__ = (
    "_dedicated_transport_move_scout_instances_for_transport",
    "_prebattle_selection_payload",
    "_proposal_request_from_selection",
)


def _dedicated_transport_move_scout_instances_for_transport(
    *,
    transport_view: RulesUnitView,
    cargo_instances: tuple[ScoutAbilityInstance, ...],
) -> tuple[ScoutAbilityInstance, ...]:
    distances = scout_distance_options_for_model_ids(
        model_instance_ids=tuple(
            sorted({instance.model_instance_id for instance in cargo_instances})
        ),
        ability_instances=cargo_instances,
    )
    return tuple(
        ScoutAbilityInstance(
            model_instance_id=model.model_instance_id,
            distance_inches=distance,
            source_id=f"{CORE_SCOUTS_SOURCE_RULE_ID}:cargo-distance:{distance:g}",
        )
        for model in transport_view.alive_models()
        for distance in distances
    )
