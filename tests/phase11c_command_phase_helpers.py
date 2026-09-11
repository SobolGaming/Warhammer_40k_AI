from __future__ import annotations

from collections.abc import Callable

from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_state import UnitPlacement
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartContext,
    CommandPhaseStartEffectContext,
    CommandPhaseStartHandler,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.setup_flow import SetupFlow
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def resolve_deferred_battle_shock_outcomes(
    state: GameState,
    decisions: DecisionController,
    registry: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    """Resume the engine's deferred outcome owner in low-level Command hook tests."""
    from warhammer40k_core.engine.battle_shock_outcome_triggers import resolve_battle_shock_trigger
    from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history

    while ready := rule_trigger_history(decisions).ready():
        trigger = ready[0]
        if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
            from warhammer40k_core.engine.model_destruction_triggers import (
                record_model_destruction_occurrences,
                resolve_model_destruction_trigger,
            )
            from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

            destruction_registry = UnitDestroyedHookRegistry.empty()
            record_model_destruction_occurrences(
                state=state, decisions=decisions, registry=destruction_registry
            )
            status = resolve_model_destruction_trigger(
                state=state, decisions=decisions, trigger=trigger, registry=destruction_registry
            )
            assert status is None or status.status_kind is LifecycleStatusKind.ADVANCED
            continue
        assert trigger.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME
        status = resolve_battle_shock_trigger(
            state=state,
            decisions=decisions,
            trigger=trigger,
            registry=registry,
        )
        if status is not None and status.status_kind is not LifecycleStatusKind.ADVANCED:
            return status
    return None


def advance_command_phase_with_outcomes(
    *,
    handler: CommandPhaseHandler,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus:
    status = handler.begin_phase(state=state, decisions=decisions)
    if status.status_kind is not LifecycleStatusKind.ADVANCED:
        return status
    outcome = resolve_deferred_battle_shock_outcomes(state, decisions, handler.battle_shock_hooks)
    return status if outcome is None else outcome


def automatic_command_contract_candidate(
    context: CommandPhaseStartEffectContext, handler: CommandPhaseStartHandler
) -> tuple[TimingRuleCandidate, ...]:
    """Exercise provider contract rejection with real engine contexts and state."""
    return command_contract_candidate(
        context,
        lambda: handler(
            CommandPhaseStartContext(
                state=context.state,
                decisions=context.decisions,
                active_player_id=context.active_player_id,
            )
        ),
    )


def command_contract_candidate(
    context: CommandPhaseStartEffectContext,
    activate: Callable[[], LifecycleStatus | None],
) -> tuple[TimingRuleCandidate, ...]:
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id="command-provider-contract-audit",
                source_rule_id="command-provider-contract-audit-source",
                player_id=context.active_player_id,
                requirement=SequencingRequirement.MANDATORY,
            ),
            activate=activate,
        ),
    )


def command_request_contract_candidate(
    context: CommandPhaseStartEffectContext, template: DecisionRequest
) -> tuple[TimingRuleCandidate, ...]:
    return (
        timing_candidate_for_request(
            template=template,
            participant_id="command-provider-contract-audit",
            source_rule_id="command-provider-contract-audit-source",
            requirement=SequencingRequirement.MANDATORY,
            next_request_id=context.state.next_decision_request_id,
        ),
    )


def battle_shock_request_for_unit(
    state: GameState,
    unit: UnitInstance,
) -> BattleShockTestRequest:
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=unit,
        starting_strength=state.starting_strength_record_for_unit(unit.unit_instance_id),
        current_model_ids=unit.own_model_ids(),
    )
    return BattleShockTestRequest.for_unit(
        request_id=f"phase11c-battle-shock:{unit.unit_instance_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=context,
    )


def battle_state_with_center_objective_positions(
    *,
    player_a_offsets: tuple[tuple[float, float], ...],
    player_b_offsets: tuple[tuple[float, float], ...],
) -> GameState:
    state = battle_state()
    assert state.battlefield_state is not None
    marker = center_marker_definition(state)
    player_a = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    player_b = state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-3")
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(player_a, marker, offsets=player_a_offsets)
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(player_b, marker, offsets=player_b_offsets)
    )
    state.battlefield_state = battlefield_state
    return state


def with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement = placements[index]
        placements[index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def remove_first_models(state: GameState, *, unit_instance_id: str, count: int) -> None:
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    removed_ids = tuple(
        placement.model_instance_id for placement in unit_placement.model_placements[:count]
    )
    models_by_id = {
        model.model_instance_id: model for model in unit_by_id(state, unit_instance_id).own_models
    }
    for model_id in removed_ids:
        model = models_by_id[model_id]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit_instance_id,
            model_instance_id=model_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )


def destroy_models_with_recorded_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    model_instance_ids: tuple[str, ...],
    application_id: str,
    destroying_player_id: str,
) -> None:
    """Create pre-existing casualties with full physical and decision history for restore tests."""
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import resolve_mortal_wound_decision
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    models = {model.model_instance_id: model for model in target.alive_models()}
    assert model_instance_ids
    assert set(model_instance_ids).issubset(models)
    phase = state.current_battle_phase
    assert phase is not None
    first_event = len(decisions.event_log.records)
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=f"{application_id}:request:0",
        progress=MortalWoundApplicationProgress.start(
            application_id=application_id,
            source_rule_id=f"{application_id}:source",
            source_context={"source_kind": "fixture_preexisting_casualties"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id=destroying_player_id,
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=phase,
                source_step="fixture_preexisting_casualties",
            ),
            target_unit_instance_id=unit_instance_id,
            defender_player_id=target.owner_player_id,
            mortal_wounds=sum(
                models[identifier].wounds_remaining for identifier in model_instance_ids
            ),
            spill_over=True,
        ),
    )
    index = 0
    while routed.request is not None:
        request = decisions.request_decision(routed.request)
        option_id = next(
            option.option_id for option in request.options if option.option_id in model_instance_ids
        )
        result = DecisionResult.for_request(
            request=request,
            result_id=f"{application_id}:result:{index}",
            selected_option_id=option_id,
        )
        decisions.submit_result(result)
        index += 1
        routed = resolve_mortal_wound_decision(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            next_request_id=f"{application_id}:request:{index}",
        )
    assert routed.application is not None
    assert {
        damage.model_instance_id for damage in routed.application.applications if damage.destroyed
    } == set(model_instance_ids)
    from warhammer40k_core.engine.primary_historical_events import (
        record_primary_battlefield_departure_event,
    )
    from warhammer40k_core.engine.primary_unit_destruction_tracking import (
        record_primary_destroyed_model_departures,
    )

    for event in decisions.event_log.records[first_event:]:
        if event.event_type != "model_destroyed":
            continue
        assert isinstance(event.payload, dict)
        identifier = event.payload["model_instance_id"]
        assert isinstance(identifier, str)
        assert identifier in model_instance_ids
        for departure in record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(identifier,),
            source_id=f"core-rules:primary-unit-destruction-tracking:{event.event_id}",
            occurrence_id=event.event_id,
        ):
            record_primary_battlefield_departure_event(
                event_log=decisions.event_log, departure=departure
            )


def unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if is_center_objective_id(marker.objective_marker_id):
            return marker
    raise AssertionError("missing center objective marker")


def is_center_objective_id(objective_id: str) -> bool:
    return objective_id.endswith(("-center", "-center-central"))


def battle_state(
    *,
    game_id: str = "phase11c-game",
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_b_units: tuple[UnitMusterSelection, ...] | None = None,
    player_a_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    player_b_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    decisions: DecisionController | None = None,
) -> GameState:
    config = phase11c_config(
        game_id=game_id,
        player_a_units=player_a_units,
        player_b_units=player_b_units,
        player_a_attachment_declarations=player_a_attachment_declarations,
        player_b_attachment_declarations=player_b_attachment_declarations,
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11c-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=player_a_secondary)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=player_b_secondary)
    )
    resolved_decisions = DecisionController() if decisions is None else decisions
    complete_setup_through_gate(state=state, decisions=resolved_decisions, config=config)
    return state


def complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )


def setup_state_at_declare_battle_formations(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    decisions = DecisionController()
    flow = SetupFlow()
    flow.advance(state=state, decisions=decisions, config=config)
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        state.complete_current_setup_step()
    return state


def secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring-it-down"),
    )


def phase11c_config(
    *,
    game_id: str = "phase11c-game",
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_b_units: tuple[UnitMusterSelection, ...] | None = None,
    player_a_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    player_b_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    (default_unit_selection("intercessor-unit-1"),)
                    if player_a_units is None
                    else player_a_units
                ),
                attachment_declarations=player_a_attachment_declarations,
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(
                    (default_unit_selection("intercessor-unit-3"),)
                    if player_b_units is None
                    else player_b_units
                ),
                attachment_declarations=player_b_attachment_declarations,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup(),
    )


def mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11c-test"
    )


def army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=unit_selections,
        attachment_declarations=attachment_declarations,
    )


def default_unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )


def unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
