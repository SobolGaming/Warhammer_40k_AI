from __future__ import annotations

from dataclasses import replace
from typing import Literal

from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    unit_selection,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
)

RulesUnitPresence = Literal["deployed", "reserves", "embarked"]


def attached_when_drawn_state(
    *,
    setup: MissionSetup,
    card_player_id: str,
    bodyguard_model_count: int,
    secondary_mission_id: str,
    leader_starting_wounds: int = 5,
    presence: RulesUnitPresence = "deployed",
    record_card: bool = True,
) -> GameState:
    enemy_player_id = "player-b" if card_player_id == "player-a" else "player-a"
    base = phase11c_config()
    force_disposition_ids = tuple(
        setup.primary_mission_assignment_for_player(player_id).force_disposition_id
        for player_id in base.player_ids
    )
    catalog = replace(
        base.army_catalog,
        datasheets=tuple(
            _when_drawn_datasheet(
                datasheet,
                leader_starting_wounds=leader_starting_wounds,
            )
            for datasheet in base.army_catalog.datasheets
        ),
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=tuple(
                    dict.fromkeys((*detachment.force_disposition_ids, *force_disposition_ids))
                ),
            )
            for detachment in base.army_catalog.detachments
        ),
    )
    requests: list[ArmyMusterRequest] = []
    for player_id, army_id in (("player-a", "army-alpha"), ("player-b", "army-beta")):
        enemy = player_id == enemy_player_id
        selections = (
            (
                unit_selection(
                    unit_selection_id="bodyguard-unit",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_id="core-intercessor-like",
                    model_count=bodyguard_model_count,
                ),
                unit_selection(
                    unit_selection_id="leader-unit",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
                *(
                    (
                        unit_selection(
                            unit_selection_id="transport-unit",
                            datasheet_id="core-transport",
                            model_profile_id="core-transport",
                            model_count=1,
                        ),
                    )
                    if presence == "embarked"
                    else ()
                ),
            )
            if enemy
            else (default_unit_selection("card-owner-unit"),)
        )
        request = army_muster_request(
            catalog=catalog,
            player_id=player_id,
            army_id=army_id,
            unit_selections=selections,
            attachment_declarations=(
                (
                    AttachmentDeclaration(
                        source_unit_selection_id="leader-unit",
                        bodyguard_unit_selection_id="bodyguard-unit",
                    ),
                )
                if enemy
                else ()
            ),
        )
        requests.append(
            replace(
                request,
                force_disposition_id=(
                    setup.primary_mission_assignment_for_player(player_id).force_disposition_id
                ),
            )
        )
    config = replace(
        base,
        game_id=(
            f"phase17n-when-drawn-{secondary_mission_id}-{card_player_id}-"
            f"{bodyguard_model_count}-{presence}"
        ),
        army_catalog=catalog,
        army_muster_requests=tuple(requests),
        mission_setup=setup,
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{config.game_id}-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(player_id=player_id, mode=SecondaryMissionMode.TACTICAL)
        )
    complete_setup_through_gate(state=state, decisions=DecisionController(), config=config)
    state.stage = GameLifecycleStage.BATTLE
    state.battle_round = 2
    state.active_player_id = card_player_id
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    for card in tuple(state.secondary_mission_card_states):
        state.forget_secondary_mission_card_state(card)
    _set_attached_rules_unit_presence(state, enemy_player_id=enemy_player_id, presence=presence)
    if record_card:
        record_unresolved_when_drawn_card(
            state,
            player_id=card_player_id,
            secondary_mission_id=secondary_mission_id,
        )
    return state


def record_unresolved_when_drawn_card(
    state: GameState,
    *,
    player_id: str,
    secondary_mission_id: str,
) -> None:
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-when-drawn-{player_id}-{secondary_mission_id}",
        )
    )


def _when_drawn_datasheet(
    datasheet: DatasheetDefinition,
    *,
    leader_starting_wounds: int,
) -> DatasheetDefinition:
    if datasheet.datasheet_id == "core-intercessor-like-infantry":
        return replace(
            datasheet,
            composition=tuple(replace(part, max_models=20) for part in datasheet.composition),
        )
    if datasheet.datasheet_id != "core-character-leader":
        return datasheet
    return replace(
        datasheet,
        model_profiles=tuple(
            replace(
                profile,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.WOUNDS, leader_starting_wounds)
                    if value.characteristic is Characteristic.WOUNDS
                    else value
                    for value in profile.characteristics
                ),
            )
            for profile in datasheet.model_profiles
        ),
    )


def _set_attached_rules_unit_presence(
    state: GameState,
    *,
    enemy_player_id: str,
    presence: RulesUnitPresence,
) -> None:
    enemy_army = next(army for army in state.army_definitions if army.player_id == enemy_player_id)
    formation = enemy_army.attached_units[0]
    if presence == "deployed":
        return
    if state.battlefield_state is None:
        raise AssertionError("When Drawn fixture requires battlefield state.")
    battlefield_state = state.battlefield_state
    for component_id in formation.component_unit_instance_ids:
        battlefield_state = battlefield_state.without_unit_placement(component_id)
    state.replace_battlefield_state(battlefield_state)
    if presence == "reserves":
        state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id=enemy_player_id,
                unit_instance_id=formation.attached_unit_instance_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
                    state.ruleset_descriptor_for_runtime_policy().mission_policy
                ),
            )
        )
        return
    transport = enemy_army.unit_by_id(f"{enemy_army.army_id}:transport-unit")
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id=enemy_player_id,
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=20,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=formation.component_unit_instance_ids,
        )
    )
