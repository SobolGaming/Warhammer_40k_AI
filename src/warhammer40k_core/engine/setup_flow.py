from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import cast

from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusteringError, muster_army
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookRegistry,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.catalog_prebattle_redeploy import (
    apply_redeploy_to_strategic_reserves,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    apply_deployment_placement,
    create_empty_deployment_battlefield_state,
    deployment_completion_accounted_model_ids,
    deployment_placement_request_from_selection,
    deployment_setup_state_for_state,
    deployment_unit_selection_request,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    DedicatedTransportSetupConsequence,
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    secondary_mission_mode_from_token,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.prebattle import (
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SELECT_REDEPLOY_UNIT_DECISION_TYPE,
    SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    apply_prebattle_completion,
    apply_redeploy_completion,
    apply_redeploy_placement,
    apply_scout_move,
    apply_scout_reserve_setup,
    prebattle_action_selection_request,
    prebattle_next_player_id_for_timing_state,
    prebattle_proposal_request_from_selection,
    prebattle_sequencing_request_for_timing_state,
    prebattle_timing_state_for_state,
    redeploy_placement_request_from_selection,
    redeploy_timing_state_for_state,
    redeploy_unit_selection_request,
)
from warhammer40k_core.engine.prebattle_records import PreBattleActionKind
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
    apply_mandatory_aircraft_reserve_declarations,
    apply_reserve_declaration_decision,
    reserve_declaration_request_for_next_player,
    reserve_declaration_state_for_state,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    decision_controller_before_pending_sequencing_roll_off,
)
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.start_battle_hooks import (
    StartBattleHookRegistry,
    StartBattleRequestContext,
    StartBattleResultContext,
    invalid_pending_start_battle_request_status,
    is_start_battle_boundary,
)
from warhammer40k_core.engine.tracked_targets import SELECT_TRACKED_TARGET_DECISION_TYPE
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency

SECONDARY_MISSION_DECISION_TYPE = "select_secondary_missions"


@dataclass(frozen=True, slots=True)
class _AuthoritativeSetupRequest:
    request: DecisionRequest
    is_start_battle_request: bool


@dataclass(slots=True)
class SetupFlow:
    battle_formation_hooks: BattleFormationHookRegistry = field(
        default_factory=BattleFormationHookRegistry.empty
    )
    start_battle_hooks: StartBattleHookRegistry = field(
        default_factory=StartBattleHookRegistry.empty
    )

    def __post_init__(self) -> None:
        if type(self.battle_formation_hooks) is not BattleFormationHookRegistry:
            raise GameLifecycleError("SetupFlow battle_formation_hooks must be a registry.")
        if type(self.start_battle_hooks) is not StartBattleHookRegistry:
            raise GameLifecycleError("SetupFlow start_battle_hooks must be a registry.")

    def invalid_pending_request_status(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        pending_request: DecisionRequest,
        reaction_frame_count: int,
    ) -> LifecycleStatus | None:
        if state.stage is not GameLifecycleStage.SETUP:
            return None
        issued_request: DecisionRequest | None = None
        try:
            issued_request = _last_issued_setup_request(decisions)
            authoritative = self._authoritative_pending_request(
                state=state,
                decisions=decisions,
                config=config,
                pending_request=pending_request,
                reaction_frame_count=reaction_frame_count,
            )
        except GameLifecycleError as exc:
            return _invalid_authoritative_setup_request_status(
                state=state,
                detail=str(exc),
                source_request=issued_request,
            )
        if authoritative is None:
            return _invalid_authoritative_setup_request_status(
                state=state,
                detail="Setup pending request has no authoritative source at this boundary.",
                source_request=issued_request,
            )
        if authoritative.is_start_battle_request:
            invalid_reason, message = _start_battle_invalid_status_context(authoritative.request)
            return invalid_pending_start_battle_request_status(
                registry=self.start_battle_hooks,
                context=StartBattleRequestContext(
                    state=state,
                    decisions=decisions,
                    config=config,
                ),
                request=pending_request,
                invalid_reason=invalid_reason,
                message=message,
            )
        if pending_request != authoritative.request:
            return _invalid_authoritative_setup_request_status(
                state=state,
                detail="Setup pending request drifted.",
                source_request=issued_request,
            )
        return None

    def _authoritative_pending_request(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        pending_request: DecisionRequest,
        reaction_frame_count: int,
    ) -> _AuthoritativeSetupRequest | None:
        state_clone = GameState.from_payload(state.to_payload())
        decisions_clone = DecisionController.from_payload(decisions.to_payload())
        removed_request = decisions_clone.queue.pop_next()
        if removed_request != pending_request:
            raise GameLifecycleError("Setup pending request clone drifted.")
        if decisions_clone.queue.pending_requests:
            raise GameLifecycleError(
                "Setup request authority requires exactly one pending request."
            )
        if state_clone.decision_request_count < 1:
            raise GameLifecycleError("Setup request authority requires an issued request ID.")
        state_clone.decision_request_count -= 1
        nested_request = self._nested_pending_request_from_last_record(
            state=state_clone,
            decisions=decisions_clone,
            config=config,
        )
        if nested_request is not None:
            return _AuthoritativeSetupRequest(
                request=nested_request,
                is_start_battle_request=False,
            )
        sequencing_roll_off_rewind = decision_controller_before_pending_sequencing_roll_off(
            decisions=decisions_clone,
            request=pending_request,
        )
        if sequencing_roll_off_rewind is not None:
            decisions_clone = sequencing_roll_off_rewind.decisions
        regenerated_suffix_start = len(decisions_clone.event_log.records)
        hook_state = GameState.from_payload(state_clone.to_payload())
        hook_decisions = DecisionController.from_payload(decisions_clone.to_payload())
        status = self.advance(
            state=state_clone,
            decisions=decisions_clone,
            config=config,
            reaction_frame_count=reaction_frame_count,
        )
        authoritative_request = status.decision_request
        if authoritative_request is None:
            return None
        if authoritative_request.decision_type == SEQUENCING_DECISION_TYPE:
            if sequencing_roll_off_rewind is None:
                raise GameLifecycleError(
                    "Setup sequencing request has no authoritative roll-off event suffix."
                )
            regenerated_suffix = decisions_clone.event_log.records[regenerated_suffix_start:]
            if regenerated_suffix != sequencing_roll_off_rewind.removed_events:
                raise GameLifecycleError(
                    "Setup sequencing event suffix drifted from authoritative regeneration."
                )
        elif sequencing_roll_off_rewind is not None:
            raise GameLifecycleError(
                "Setup roll-off event suffix does not belong to the authoritative request."
            )
        is_start_battle_request = False
        if is_start_battle_boundary(hook_state):
            hook_request = self.start_battle_hooks.next_request_for(
                StartBattleRequestContext(
                    state=hook_state,
                    decisions=hook_decisions,
                    config=config,
                    authoritative_request_id=authoritative_request.request_id,
                )
            )
            is_start_battle_request = hook_request == authoritative_request
        return _AuthoritativeSetupRequest(
            request=authoritative_request,
            is_start_battle_request=is_start_battle_request,
        )

    def _nested_pending_request_from_last_record(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> DecisionRequest | None:
        if not decisions.records:
            return None
        record = decisions.records[-1]
        if (
            state.current_setup_step is SetupStep.DEPLOY_ARMIES
            and record.request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
        ):
            return deployment_placement_request_from_selection(
                state=state,
                ruleset_descriptor=config.ruleset_descriptor,
                selection_request=record.request,
                result=record.result,
            ).to_decision_request()
        if (
            state.current_setup_step is SetupStep.REDEPLOY_UNITS
            and record.request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
        ):
            action_kind = _prebattle_action_kind_from_payload(
                _decision_payload_object(record.result.payload)
            )
            if action_kind is PreBattleActionKind.REDEPLOY:
                return redeploy_placement_request_from_selection(
                    state=state,
                    ruleset_descriptor=config.ruleset_descriptor,
                    army_catalog=config.army_catalog,
                    selection_request=record.request,
                    result=record.result,
                ).to_decision_request()
        if (
            state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
            and record.request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
        ):
            action_kind = _prebattle_action_kind_from_payload(
                _decision_payload_object(record.result.payload)
            )
            if action_kind in {
                PreBattleActionKind.SCOUT_MOVE,
                PreBattleActionKind.SCOUT_RESERVE_SETUP,
                PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
            }:
                return prebattle_proposal_request_from_selection(
                    state=state,
                    ruleset_descriptor=config.ruleset_descriptor,
                    army_catalog=config.army_catalog,
                    selection_request=record.request,
                    result=record.result,
                ).to_decision_request()
        return None

    def advance(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        reaction_frame_count: int = 0,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("SetupFlow can advance only during setup.")
        current_step = state.current_setup_step
        if current_step is None:
            raise GameLifecycleError("SetupFlow requires a current setup step.")

        if current_step is SetupStep.SELECT_SECONDARY_MISSIONS:
            next_player_id = self._next_secondary_mission_player_id(state)
            if next_player_id is not None:
                request = self._secondary_mission_request(
                    state=state,
                    config=config,
                    player_id=next_player_id,
                )
                decisions.request_decision(request)
                return LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.SETUP,
                    decision_request=request,
                    payload={
                        "setup_step": current_step.value,
                        "player_id": next_player_id,
                    },
                )
        elif current_step is SetupStep.MUSTER_ARMIES:
            self._muster_armies(state=state, decisions=decisions, config=config)
        elif current_step is SetupStep.CREATE_BATTLEFIELD:
            self._create_battlefield(state=state, decisions=decisions)
        elif current_step is SetupStep.DECLARE_BATTLE_FORMATIONS:
            reserve_status = self._advance_declare_battle_formations(
                state=state,
                decisions=decisions,
                config=config,
            )
            if reserve_status is not None:
                return reserve_status
        elif current_step is SetupStep.DEPLOY_ARMIES:
            deployment_status = self._advance_deploy_armies(
                state=state,
                decisions=decisions,
                config=config,
            )
            if deployment_status is not None:
                return deployment_status
        elif current_step is SetupStep.REDEPLOY_UNITS:
            redeploy_status = self._advance_redeploy_units(
                state=state,
                decisions=decisions,
                config=config,
            )
            if redeploy_status is not None:
                return redeploy_status
        elif current_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS:
            prebattle_status = self._advance_resolve_prebattle_actions(
                state=state,
                decisions=decisions,
                config=config,
            )
            if prebattle_status is not None:
                return prebattle_status

        setup_completion_gate: SetupCompletionGate | None = None
        battle_start_payload: dict[str, JsonValue] | None = None
        final_setup_step = is_start_battle_boundary(state)
        if final_setup_step:
            start_battle_request = self.start_battle_hooks.next_request_for(
                StartBattleRequestContext(
                    state=state,
                    decisions=decisions,
                    config=config,
                )
            )
            if start_battle_request is not None:
                decisions.request_decision(start_battle_request)
                return LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.SETUP,
                    decision_request=start_battle_request,
                    payload={
                        "setup_step": current_step.value,
                        "start_battle_hook_request": start_battle_request.payload,
                    },
                )
            setup_completion_gate = SetupCompletionGate()
            invalid_status = setup_completion_gate.invalid_status_if_not_ready(
                state=state,
                decisions=decisions,
                config=config,
                reaction_frame_count=reaction_frame_count,
            )
            if invalid_status is not None:
                return invalid_status
            battle_start = setup_completion_gate.complete_setup_and_enter_battle(
                state=state,
                decisions=decisions,
                config=config,
                reaction_frame_count=reaction_frame_count,
            )
            battle_start_payload = cast(dict[str, JsonValue], battle_start.to_payload())
            completed_step = battle_start.completed_setup_step
            decisions.event_log.append(
                "setup_completion_gate_passed",
                {
                    "game_id": state.game_id,
                    "setup_step": completed_step.value,
                    "setup_legality_report": battle_start.setup_legality_report.to_payload(),
                    "pre_battle_checkpoint": battle_start.pre_battle_checkpoint.to_payload(),
                },
            )
            decisions.event_log.append("battle_started", battle_start_payload)
        else:
            completed_step = state.complete_current_setup_step()
        decisions.event_log.append(
            "setup_step_completed",
            {
                "game_id": state.game_id,
                "step": completed_step.value,
                "stage": state.stage.value,
                "next_setup_step": (
                    None if state.current_setup_step is None else state.current_setup_step.value
                ),
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "battle_phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
            },
        )
        return LifecycleStatus.advanced(
            stage=state.stage,
            payload={
                "completed_setup_step": completed_step.value,
                "current_setup_step": (
                    None if state.current_setup_step is None else state.current_setup_step.value
                ),
                "battle_phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "battle_start_record": battle_start_payload,
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        if result.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
            request = decisions.record_for_result(result).request
            if (
                state.setup_step_index is not None
                and state.setup_step_index + 1 == len(state.setup_sequence)
                and self.start_battle_hooks.apply_result(
                    StartBattleResultContext(
                        state=state,
                        decisions=decisions,
                        config=config,
                        request=request,
                        result=result,
                    )
                )
            ):
                return
            if self.battle_formation_hooks.apply_result(
                BattleFormationResultContext(
                    state=state,
                    decisions=decisions,
                    config=config,
                    request=request,
                    result=result,
                )
            ):
                return
            raise GameLifecycleError("Faction rule setup decision was not handled.")
        if result.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE:
            apply_reserve_declaration_decision(
                state=state,
                config=config,
                request=decisions.record_for_result(result).request,
                result=result,
                decisions=decisions,
            )
            return
        if result.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
            self._apply_deployment_unit_selection(
                state=state,
                result=result,
                decisions=decisions,
                config=config,
            )
            return
        if result.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE:
            self._apply_deployment_placement(
                state=state,
                result=result,
                decisions=decisions,
                config=config,
            )
            return
        if result.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE:
            self._apply_redeploy_selection(
                state=state,
                result=result,
                decisions=decisions,
                config=config,
            )
            return
        if result.decision_type == SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE:
            apply_redeploy_placement(
                state=state,
                request=decisions.record_for_result(result).request,
                result=result,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            )
            return
        if result.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE:
            self._apply_prebattle_action_selection(
                state=state,
                result=result,
                decisions=decisions,
                config=config,
            )
            return
        if result.decision_type == SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE:
            apply_scout_reserve_setup(
                state=state,
                request=decisions.record_for_result(result).request,
                result=result,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            )
            return
        if result.decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE:
            apply_scout_move(
                state=state,
                request=decisions.record_for_result(result).request,
                result=result,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            )
            return
        if result.decision_type != SECONDARY_MISSION_DECISION_TYPE:
            raise GameLifecycleError("SetupFlow received an unsupported decision_type.")
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Secondary mission decisions can be applied only in setup.")
        if state.current_setup_step is not SetupStep.SELECT_SECONDARY_MISSIONS:
            raise GameLifecycleError(
                "Secondary mission decisions can be applied only during SELECT_SECONDARY_MISSIONS."
            )
        if result.actor_id is None:
            raise GameLifecycleError("Secondary mission decisions require an actor_id.")
        payload = _decision_payload_object(result.payload)
        mode = secondary_mission_mode_from_token(_payload_string(payload, key="mode"))
        fixed_mission_ids = _payload_string_list(payload, key="fixed_mission_ids")
        choice = SecondaryMissionChoice(
            player_id=result.actor_id,
            mode=mode,
            fixed_mission_ids=fixed_mission_ids,
        )
        state.record_secondary_mission_choice(choice)
        decisions.event_log.append(
            "secondary_mission_choice_recorded",
            {
                "game_id": state.game_id,
                "player_id": result.actor_id,
                "setup_step": SetupStep.SELECT_SECONDARY_MISSIONS.value,
                "mode_recorded": True,
                "fixed_choice_count": len(choice.fixed_mission_ids),
            },
        )
        if state.secondary_mission_choices_are_revealed():
            decisions.event_log.append(
                "secondary_missions_revealed",
                {
                    "game_id": state.game_id,
                    "setup_step": SetupStep.SELECT_SECONDARY_MISSIONS.value,
                    "choices": [
                        selected_choice.to_payload()
                        for selected_choice in state.secondary_mission_choices
                    ],
                },
            )

    def _next_secondary_mission_player_id(self, state: GameState) -> str | None:
        missing_players = state.missing_secondary_mission_player_ids()
        if not missing_players:
            return None
        return missing_players[0]

    def _muster_armies(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        missing_player_ids = set(state.missing_army_player_ids())
        if not missing_player_ids:
            return
        army_definitions: list[ArmyDefinition] = []
        for request in config.army_muster_requests:
            if request.player_id not in missing_player_ids:
                continue
            try:
                army_definitions.append(muster_army(catalog=config.army_catalog, request=request))
            except ArmyMusteringError as exc:
                raise GameLifecycleError("MUSTER_ARMIES failed during army mustering.") from exc
        for army_definition in army_definitions:
            state.record_army_definition(army_definition)
            cargo_states, transport_consequences = _record_dedicated_transport_manifests(
                state=state,
                army_definition=army_definition,
            )
            decisions.event_log.append(
                "army_mustered",
                {
                    "game_id": state.game_id,
                    "setup_step": SetupStep.MUSTER_ARMIES.value,
                    "player_id": army_definition.player_id,
                    "army_id": army_definition.army_id,
                    "unit_count": len(army_definition.units),
                    "roster_legality_report": army_definition.roster_legality_report.to_payload(),
                },
            )
            for ledger in state.unit_resource_ledgers:
                if ledger.player_id != army_definition.player_id:
                    continue
                for transaction in ledger.transactions:
                    decisions.event_log.append(
                        "unit_resource_initialized",
                        {
                            "game_id": state.game_id,
                            "setup_step": SetupStep.MUSTER_ARMIES.value,
                            "transaction": transaction.to_payload(),
                        },
                    )
            for cargo_state in cargo_states:
                decisions.event_log.append(
                    "battle_formation_transport_manifest_recorded",
                    {
                        "game_id": state.game_id,
                        "setup_step": SetupStep.MUSTER_ARMIES.value,
                        "player_id": army_definition.player_id,
                        "army_id": army_definition.army_id,
                        "transport_unit_instance_id": cargo_state.transport_unit_instance_id,
                        "transport_cargo_state": cargo_state.to_payload(),
                    },
                )
            for consequence in transport_consequences:
                decisions.event_log.append(
                    "dedicated_transport_setup_consequence_recorded",
                    {
                        "game_id": state.game_id,
                        "setup_step": SetupStep.MUSTER_ARMIES.value,
                        "player_id": army_definition.player_id,
                        "army_id": army_definition.army_id,
                        "transport_unit_instance_id": consequence.transport_unit_instance_id,
                        "consequence": consequence.to_payload(),
                    },
                )
        if state.missing_army_player_ids():
            raise GameLifecycleError("MUSTER_ARMIES requires an army for every player.")

    def _create_battlefield(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> None:
        if state.battlefield_state is not None:
            return
        if state.mission_setup is None:
            raise GameLifecycleError("CREATE_BATTLEFIELD requires source-backed MissionSetup.")
        battlefield_state = create_empty_deployment_battlefield_state(state=state)
        state.record_battlefield_state(battlefield_state)
        decisions.event_log.append(
            "battlefield_created",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.CREATE_BATTLEFIELD.value,
                "battlefield_id": battlefield_state.battlefield_id,
                "mission_pack_id": state.mission_setup.mission_pack_id,
                "deployment_map_id": state.mission_setup.deployment_map_id,
                "terrain_layout_id": state.mission_setup.terrain_layout_id,
                "objective_marker_count": len(state.mission_setup.objective_markers),
                "terrain_feature_count": len(state.mission_setup.terrain_features),
                "placed_model_count": 0,
            },
        )

    def _advance_declare_battle_formations(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> LifecycleStatus | None:
        if state.battlefield_state is None:
            raise GameLifecycleError("DECLARE_BATTLE_FORMATIONS requires CREATE_BATTLEFIELD first.")
        if state.missing_army_player_ids():
            raise GameLifecycleError(
                "DECLARE_BATTLE_FORMATIONS requires mustered armies for every player."
            )
        apply_mandatory_aircraft_reserve_declarations(
            state=state,
            config=config,
            decisions=decisions,
        )
        hook_request = self.battle_formation_hooks.next_request_for(
            BattleFormationRequestContext(
                state=state,
                decisions=decisions,
                config=config,
            )
        )
        if hook_request is not None:
            decisions.request_decision(hook_request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.SETUP,
                decision_request=hook_request,
                payload={
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "battle_formation_hook_request": hook_request.payload,
                },
            )
        setup_state = reserve_declaration_state_for_state(
            state=state,
            config=config,
            decisions=decisions,
        )
        request = reserve_declaration_request_for_next_player(
            state=state,
            config=config,
            decisions=decisions,
        )
        if request is None:
            return None
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.SETUP,
            decision_request=request,
            payload={
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "battle_formation_declaration_state": cast(
                    JsonValue,
                    setup_state.to_payload(),
                ),
            },
        )

    def _advance_deploy_armies(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> LifecycleStatus | None:
        if state.battlefield_state is None:
            raise GameLifecycleError("DEPLOY_ARMIES requires CREATE_BATTLEFIELD first.")
        if state.missing_army_player_ids():
            raise GameLifecycleError("DEPLOY_ARMIES requires mustered armies for every player.")
        setup_state = deployment_setup_state_for_state(state)
        if setup_state.next_player_id is not None:
            request = deployment_unit_selection_request(
                state=state,
                ruleset_descriptor=config.ruleset_descriptor,
                player_id=setup_state.next_player_id,
            )
            decisions.request_decision(request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.SETUP,
                decision_request=request,
                payload={
                    "setup_step": SetupStep.DEPLOY_ARMIES.value,
                    "deployment_setup_state": cast(JsonValue, setup_state.to_payload()),
                },
            )
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(
            deployment_completion_accounted_model_ids(state)
        )
        assert_battlefield_units_in_coherency(
            scenario=scenario,
            ruleset_descriptor=config.ruleset_descriptor,
        )
        return None

    def _advance_redeploy_units(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> LifecycleStatus | None:
        setup_state = redeploy_timing_state_for_state(state)
        sequencing_request = prebattle_sequencing_request_for_timing_state(
            state=state,
            decisions=decisions,
            timing_state=setup_state,
        )
        if sequencing_request is not None:
            decisions.request_decision(sequencing_request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.SETUP,
                decision_request=sequencing_request,
                payload={
                    "setup_step": SetupStep.REDEPLOY_UNITS.value,
                    "prebattle_timing_state": cast(JsonValue, setup_state.to_payload()),
                },
            )
        next_player_id = prebattle_next_player_id_for_timing_state(
            decisions=decisions,
            timing_state=setup_state,
        )
        if next_player_id is None:
            return None
        effective_setup_state = replace(setup_state, next_player_id=next_player_id)
        request = redeploy_unit_selection_request(
            state=state,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            player_id=next_player_id,
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.SETUP,
            decision_request=request,
            payload={
                "setup_step": SetupStep.REDEPLOY_UNITS.value,
                "prebattle_timing_state": cast(JsonValue, effective_setup_state.to_payload()),
            },
        )

    def _advance_resolve_prebattle_actions(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> LifecycleStatus | None:
        setup_state = prebattle_timing_state_for_state(
            state,
            army_catalog=config.army_catalog,
        )
        sequencing_request = prebattle_sequencing_request_for_timing_state(
            state=state,
            decisions=decisions,
            timing_state=setup_state,
        )
        if sequencing_request is not None:
            decisions.request_decision(sequencing_request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.SETUP,
                decision_request=sequencing_request,
                payload={
                    "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                    "prebattle_timing_state": cast(JsonValue, setup_state.to_payload()),
                },
            )
        next_player_id = prebattle_next_player_id_for_timing_state(
            decisions=decisions,
            timing_state=setup_state,
        )
        if next_player_id is None:
            return None
        effective_setup_state = replace(setup_state, next_player_id=next_player_id)
        request = prebattle_action_selection_request(
            state=state,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            player_id=next_player_id,
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.SETUP,
            decision_request=request,
            payload={
                "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                "prebattle_timing_state": cast(JsonValue, effective_setup_state.to_payload()),
            },
        )

    def _apply_deployment_unit_selection(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Deployment unit selection can be applied only in setup.")
        if state.current_setup_step is not SetupStep.DEPLOY_ARMIES:
            raise GameLifecycleError("Deployment unit selection requires DEPLOY_ARMIES.")
        if result.actor_id is None:
            raise GameLifecycleError("Deployment unit selection requires actor_id.")
        if not isinstance(result.payload, dict):
            raise GameLifecycleError("Deployment unit selection payload must be an object.")
        selected_unit_id = result.payload.get("unit_instance_id")
        if type(selected_unit_id) is not str:
            raise GameLifecycleError("Deployment unit selection payload missing unit_instance_id.")
        selection_record = decisions.record_for_result(result)
        placement_request = deployment_placement_request_from_selection(
            state=state,
            ruleset_descriptor=config.ruleset_descriptor,
            selection_request=selection_record.request,
            result=result,
        ).to_decision_request()
        decisions.event_log.append(
            "deployment_unit_selected",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DEPLOY_ARMIES.value,
                "deployment_order_policy": "defender_first_alternating",
                "player_id": result.actor_id,
                "unit_instance_id": selected_unit_id,
                "selected_option_id": result.selected_option_id,
                "source_decision_record_id": selection_record.record_id,
                "source_decision_request_id": selection_record.request.request_id,
                "source_decision_result_id": result.result_id,
                "placement_request_id": placement_request.request_id,
            },
        )
        decisions.request_decision(placement_request)

    def _apply_deployment_placement(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Deployment placement can be applied only in setup.")
        if state.current_setup_step is not SetupStep.DEPLOY_ARMIES:
            raise GameLifecycleError("Deployment placement requires DEPLOY_ARMIES.")
        placement_record = decisions.record_for_result(result)
        resolution = apply_deployment_placement(
            state=state,
            request=placement_record.request,
            result=result,
            ruleset_descriptor=config.ruleset_descriptor,
        )
        if resolution.transition_batch is None:
            raise GameLifecycleError("Deployment placement requires a transition batch.")
        if state.battlefield_state is None:
            raise GameLifecycleError("Deployment placement requires battlefield_state.")
        decisions.event_log.append(
            "deployment_unit_placed",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DEPLOY_ARMIES.value,
                "battlefield_id": state.battlefield_state.battlefield_id,
                "deployment_order_policy": "defender_first_alternating",
                "player_id": result.actor_id,
                "unit_instance_id": resolution.proposal.unit_instance_id,
                "placement_kind": resolution.proposal.placement_kind.value,
                "placed_model_count": len(resolution.proposal.model_placements),
                "source_decision_record_id": placement_record.record_id,
                "resolution": resolution.to_payload(),
            },
        )
        decisions.event_log.append(
            "battlefield_models_placed",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DEPLOY_ARMIES.value,
                "battlefield_id": state.battlefield_state.battlefield_id,
                "placement_kind": resolution.proposal.placement_kind.value,
                "placed_model_count": len(resolution.proposal.model_placements),
                "transition_batch": resolution.transition_batch.to_payload(),
            },
        )

    def _apply_redeploy_selection(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Redeploy selection can be applied only in setup.")
        if state.current_setup_step is not SetupStep.REDEPLOY_UNITS:
            raise GameLifecycleError("Redeploy selection requires REDEPLOY_UNITS.")
        if result.actor_id is None:
            raise GameLifecycleError("Redeploy selection requires actor_id.")
        if not isinstance(result.payload, dict):
            raise GameLifecycleError("Redeploy selection payload must be an object.")
        selection_record = decisions.record_for_result(result)
        action_kind = _prebattle_action_kind_from_payload(result.payload)
        if action_kind is PreBattleActionKind.COMPLETE_REDEPLOYS:
            apply_redeploy_completion(
                state=state,
                result=result,
                request=selection_record.request,
                decisions=decisions,
            )
            return
        if action_kind is PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES:
            unit_instance_id = _payload_string(result.payload, key="unit_instance_id")
            apply_redeploy_to_strategic_reserves(
                state=state,
                request=selection_record.request,
                result=result,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                points_contribution=_redeploy_points_contribution(
                    state=state,
                    config=config,
                    unit_instance_id=unit_instance_id,
                ),
            )
            return
        placement_request = redeploy_placement_request_from_selection(
            state=state,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            selection_request=selection_record.request,
            result=result,
        ).to_decision_request()
        decisions.event_log.append(
            "prebattle_redeploy_unit_selected",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.REDEPLOY_UNITS.value,
                "player_id": result.actor_id,
                "unit_instance_id": _payload_string(result.payload, key="unit_instance_id"),
                "selected_option_id": result.selected_option_id,
                "source_decision_record_id": selection_record.record_id,
                "source_decision_request_id": selection_record.request.request_id,
                "source_decision_result_id": result.result_id,
                "placement_request_id": placement_request.request_id,
            },
        )
        decisions.request_decision(placement_request)

    def _apply_prebattle_action_selection(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Pre-battle action selection can be applied only in setup.")
        if state.current_setup_step is not SetupStep.RESOLVE_PREBATTLE_ACTIONS:
            raise GameLifecycleError(
                "Pre-battle action selection requires RESOLVE_PREBATTLE_ACTIONS."
            )
        if result.actor_id is None:
            raise GameLifecycleError("Pre-battle action selection requires actor_id.")
        if not isinstance(result.payload, dict):
            raise GameLifecycleError("Pre-battle action selection payload must be an object.")
        selection_record = decisions.record_for_result(result)
        action_kind = _prebattle_action_kind_from_payload(result.payload)
        if action_kind is PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS:
            apply_prebattle_completion(
                state=state,
                result=result,
                request=selection_record.request,
                decisions=decisions,
            )
            return
        proposal_request = prebattle_proposal_request_from_selection(
            state=state,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            selection_request=selection_record.request,
            result=result,
        ).to_decision_request()
        decisions.event_log.append(
            "prebattle_action_selected",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                "player_id": result.actor_id,
                "unit_instance_id": _payload_string(result.payload, key="unit_instance_id"),
                "action_kind": action_kind.value,
                "selected_option_id": result.selected_option_id,
                "source_decision_record_id": selection_record.record_id,
                "source_decision_request_id": selection_record.request.request_id,
                "source_decision_result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
            },
        )
        decisions.request_decision(proposal_request)

    def _secondary_mission_request(
        self,
        *,
        state: GameState,
        config: GameConfig,
        player_id: str,
    ) -> DecisionRequest:
        return DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SECONDARY_MISSION_DECISION_TYPE,
            actor_id=player_id,
            payload={
                "game_id": state.game_id,
                "setup_step": SetupStep.SELECT_SECONDARY_MISSIONS.value,
                "secret": True,
                "fixed_choices_required": 2,
            },
            options=_secondary_mission_options(config.fixed_secondary_mission_ids),
        )


def _secondary_mission_options(
    fixed_secondary_mission_ids: tuple[str, ...],
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id="tactical",
            label="Tactical",
            payload={
                "mode": SecondaryMissionMode.TACTICAL.value,
                "fixed_mission_ids": [],
            },
        )
    ]
    for first_id, second_id in combinations(fixed_secondary_mission_ids, 2):
        options.append(
            DecisionOption(
                option_id=f"fixed:{first_id}:{second_id}",
                label=f"Fixed {first_id} {second_id}",
                payload={
                    "mode": SecondaryMissionMode.FIXED.value,
                    "fixed_mission_ids": [first_id, second_id],
                },
            )
        )
    return tuple(options)


def _invalid_authoritative_setup_request_status(
    *,
    state: GameState,
    detail: str,
    source_request: DecisionRequest | None,
) -> LifecycleStatus:
    if (
        source_request is not None
        and source_request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration request no longer matches setup state.",
            payload={
                "invalid_reason": "reserve_declaration_request_drift",
                "field": "setup_step",
                "request_id": source_request.request_id,
            },
        )
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Setup submission is stale.",
        payload={
            "invalid_reason": _setup_request_drift_reason(source_request),
            "field": "authoritative_request",
            "detail": detail,
        },
    )


def _last_issued_setup_request(decisions: DecisionController) -> DecisionRequest:
    for event in reversed(decisions.event_log.records):
        if event.event_type != "decision_requested":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Setup decision_requested payload must be an object.")
        try:
            return DecisionRequest.from_payload(cast(DecisionRequestPayload, event.payload))
        except (KeyError, TypeError, DecisionError) as exc:
            raise GameLifecycleError("Setup decision_requested payload is invalid.") from exc
    raise GameLifecycleError("Setup pending request has no decision_requested event.")


def _setup_request_drift_reason(request: DecisionRequest | None) -> str:
    if request is None:
        return "invalid_authoritative_setup_request"
    if request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
        return "invalid_faction_rule_setup_option_result"
    if request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE:
        return "invalid_tracked_target_result"
    if request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE:
        return "reserve_declaration_request_drift"
    return "invalid_authoritative_setup_request"


def _start_battle_invalid_status_context(request: DecisionRequest) -> tuple[str, str]:
    if request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
        return (
            "invalid_faction_rule_setup_option_result",
            "Start-battle faction rule submission is stale.",
        )
    if request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE:
        return (
            "invalid_tracked_target_result",
            "Start-battle tracked target submission is stale.",
        )
    return (
        "invalid_start_battle_request",
        "Start-battle submission is stale.",
    )


def _record_dedicated_transport_manifests(
    *,
    state: GameState,
    army_definition: ArmyDefinition,
) -> tuple[tuple[TransportCargoState, ...], tuple[DedicatedTransportSetupConsequence, ...]]:
    cargo_states: list[TransportCargoState] = []
    consequences: list[DedicatedTransportSetupConsequence] = []
    for manifest in army_definition.dedicated_transport_manifests:
        transport_unit_instance_id = manifest.transport_unit_instance_id(
            army_id=army_definition.army_id
        )
        if not manifest.embarked_unit_selection_ids:
            consequence = DedicatedTransportSetupConsequence.empty_dedicated_transport(
                player_id=army_definition.player_id,
                transport_unit_instance_id=transport_unit_instance_id,
                source_id=manifest.source_id,
            )
            state.record_dedicated_transport_setup_consequence(consequence)
            consequences.append(consequence)
            continue
        cargo_states.append(
            state.declare_battle_formation_embarkation(
                player_id=army_definition.player_id,
                transport_unit_instance_id=transport_unit_instance_id,
                embarked_unit_instance_ids=manifest.embarked_unit_instance_ids(
                    army_id=army_definition.army_id,
                ),
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id=manifest.capacity_profile.transport_datasheet_id,
                    max_model_count=manifest.capacity_profile.max_model_count,
                    allowed_keywords=manifest.capacity_profile.allowed_keywords,
                    excluded_keywords=manifest.capacity_profile.excluded_keywords,
                    source_id=manifest.capacity_profile.source_id,
                ),
            )
        )
    return tuple(cargo_states), tuple(consequences)


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _redeploy_points_contribution(
    *,
    state: GameState,
    config: GameConfig,
    unit_instance_id: str,
) -> int:
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    unit_ids = set(view.component_unit_instance_ids)
    cargo_state = state.transport_cargo_state_for_transport(unit_instance_id)
    if cargo_state is not None:
        unit_ids.update(cargo_state.embarked_unit_instance_ids)
    points_by_unit_id = {
        entry.unit_instance_id: entry.points for entry in config.reserve_unit_points
    }
    missing = unit_ids - set(points_by_unit_id)
    if missing:
        raise GameLifecycleError("Redeploy Strategic Reserves units require point values.")
    return sum(points_by_unit_id[unit_id] for unit_id in unit_ids)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


def _prebattle_action_kind_from_payload(payload: dict[str, JsonValue]) -> PreBattleActionKind:
    value = _payload_string(payload, key="action_kind")
    try:
        return PreBattleActionKind(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported pre-battle action kind: {value}.") from exc


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be a string list: {key}.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Decision payload key must contain strings: {key}.")
        strings.append(item)
    return tuple(strings)
