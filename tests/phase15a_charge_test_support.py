from __future__ import annotations

from dataclasses import replace
from typing import cast

from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.charge_target_selection_helpers import choose_charge_targets
from tests.phase15a_charge_config_helpers import (
    _army_muster_request as _army_muster_request,
)
from tests.phase15a_charge_config_helpers import (
    _config as _config,
)
from tests.phase15a_charge_config_helpers import (
    _mission_setup as _mission_setup,
)
from tests.phase15a_charge_config_helpers import (
    _mustered_armies as _mustered_armies,
)
from tests.phase15a_charge_config_helpers import (
    _unit_selection as _unit_selection,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from tests.support.selected_target_charge_fixtures import (
    selected_target_charge_persisting_effect,
)
from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_conditional_charge_runtime import (
    catalog_conditional_charge_declaration_hook_bindings,
)
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollRequest,
    ChargeRollResult,
    ChargeRollResultPayload,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationHookBinding,
    ChargeDeclarationHookRegistry,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    ChargeMoveProposal,
    ChargeMoveResolution,
    ChargePhaseHandler,
    ChargePhaseState,
    resolve_charge_move,
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierBinding,
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    StratagemUseRecord,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathWitness,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_ATTACHED_CHARGE_TARGET_ID = "attached-unit:army-beta:marked-bodyguard"
_END_PHASE_CHARGE_GRANT_ID = "phase15a:test-charge-grant:end-phase"
_END_TURN_CHARGE_GRANT_ID = "phase15a:test-charge-grant:end-turn"


def _charge_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_model_poses: tuple[Pose, ...],
    game_id: str,
    catalog: ArmyCatalog | None = None,
    alpha_datasheet_ids_by_selection_id: dict[str, str] | None = None,
    alpha_origins: dict[str, Pose] | None = None,
    enemy_unit_ids: tuple[str, ...] = ("enemy",),
    enemy_origins: dict[str, Pose] | None = None,
    enemy_attached_unit_ids: tuple[str, str] | None = None,
    selected_attached_target_effect_id: str | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
        enemy_attached_unit_ids=enemy_attached_unit_ids,
        catalog=catalog,
        alpha_datasheet_ids_by_selection_id=alpha_datasheet_ids_by_selection_id,
    )
    armies = _mustered_armies(config)
    mission_setup = config.mission_setup
    assert mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15a-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    origins = {} if alpha_origins is None else alpha_origins
    resolved_enemy_origins = {} if enemy_origins is None else enemy_origins
    battlefield = scenario.battlefield_state
    alpha_index = 0
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-alpha":
            origin = origins.get(key, Pose.at(10.0, 20.0 + (alpha_index * 15.0)))
            poses = _compact_test_unit_poses(origin=origin, model_count=len(unit.own_models))
            alpha_index += 1
        else:
            enemy_origin = resolved_enemy_origins.get(key)
            poses = (
                enemy_model_poses
                if enemy_origin is None
                else _compact_test_unit_poses(
                    origin=enemy_origin,
                    model_count=len(unit.own_models),
                )
            )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = "player-a"
    decision_controller = GameLifecycle().decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decision_controller)
    record_current_battlefield_placements_for_fixture(state, decisions=decision_controller)
    if enemy_attached_unit_ids is not None:
        if selected_attached_target_effect_id is None:
            raise AssertionError("Attached Charge target fixture requires a selected effect ID.")
        source = units[alpha_unit_ids[0]]
        state.record_persisting_effect(
            selected_target_charge_persisting_effect(
                state=state,
                effect_id=selected_attached_target_effect_id,
                owner_player_id="player-a",
                source_rules_unit_instance_id=source.unit_instance_id,
                source_component_unit_instance_id=source.unit_instance_id,
                selected_target_unit_instance_id=_ATTACHED_CHARGE_TARGET_ID,
            )
        )
    elif selected_attached_target_effect_id is not None:
        raise AssertionError("Selected Attached Unit target fixture requires a formation.")
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _charge_lifecycle_with_declaration_grants(
    *,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id=game_id,
    )
    registry = ChargeDeclarationHookRegistry.from_bindings(
        (
            ChargeDeclarationHookBinding(
                hook_id=_END_PHASE_CHARGE_GRANT_ID,
                source_id="phase15a:test-charge-grant-source:end-phase",
                handler=_end_phase_charge_declaration_grant,
            ),
            ChargeDeclarationHookBinding(
                hook_id=_END_TURN_CHARGE_GRANT_ID,
                source_id="phase15a:test-charge-grant-source:end-turn",
                handler=_end_turn_charge_declaration_grant,
            ),
        )
    )
    _install_charge_declaration_registry(lifecycle, registry)
    return lifecycle, units


def _conditional_charge_lifecycle(
    *,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        base_catalog,
        datasheets=tuple(
            replace(
                datasheet,
                keywords=replace(
                    datasheet.keywords,
                    keywords=(*datasheet.keywords.keywords, "PSYKER"),
                ),
            )
            if datasheet.datasheet_id == "core-intercessor-like-infantry"
            else datasheet
            for datasheet in base_catalog.datasheets
        ),
    )
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger", "psyker-anchor-1", "psyker-anchor-2"),
        alpha_origins={
            "charger": Pose.at(6.0, 20.0),
            "psyker-anchor-1": Pose.at(18.0, 20.0),
            "psyker-anchor-2": Pose.at(18.0, 28.0),
        },
        enemy_unit_ids=("enemy-1", "enemy-2"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(18.0, 21.05),
            model_count=5,
        ),
        enemy_origins={
            "enemy-1": Pose.at(18.0, 21.05),
            "enemy-2": Pose.at(18.0, 29.05),
        },
        game_id=game_id,
        catalog=catalog,
    )
    state = _state(lifecycle)
    record, _clauses = _conditional_charge_ability_record()
    ability_indexes = {
        "player-a": AbilityCatalogIndex.from_records((record,)),
        "player-b": AbilityCatalogIndex.from_records(()),
    }
    registry = ChargeDeclarationHookRegistry.from_bindings(
        catalog_conditional_charge_declaration_hook_bindings(
            ability_indexes_by_player_id=ability_indexes,
            armies=tuple(state.army_definitions),
        )
    )
    _install_charge_declaration_registry(lifecycle, registry)
    return lifecycle, units


def _generated_snarling_protector_charge_lifecycle(
    *,
    game_id: str,
    maulerfiend_selection_ids: tuple[str, ...] = ("maulerfiend",),
    ordinary_selection_ids: tuple[str, ...] = ("psyker-anchor",),
    alpha_origins: dict[str, Pose] | None = None,
    enemy_origin: Pose | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    generated = _ability_support_catalog_package(datasheet_ids=("000001029",)).army_catalog
    generated_maulerfiend = generated.datasheet_by_id("000001029")
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_anchor = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    anchor_datasheet_id = "phase15a-thousand-sons-psyker-anchor"
    thousand_sons_anchor = replace(
        base_anchor,
        datasheet_id=anchor_datasheet_id,
        name="Phase 15A Thousand Sons Psyker Anchor",
        keywords=replace(
            base_anchor.keywords,
            keywords=(*base_anchor.keywords.keywords, "PSYKER"),
            faction_keywords=("THOUSAND SONS",),
        ),
        source_ids=("phase15a:thousand-sons:psyker-anchor",),
    )
    base_detachment = next(
        detachment
        for detachment in base_catalog.detachments
        if detachment.detachment_id == "core-combined-arms"
    )
    thousand_sons_detachment = replace(
        base_detachment,
        canonical_detachment_id="phase15a-thousand-sons-detachment",
        detachment_id="phase15a-thousand-sons-detachment",
        name="Phase 15A Thousand Sons Detachment",
        faction_id="TS",
        unit_datasheet_ids=("000001029", anchor_datasheet_id),
        source_ids=("phase15a:thousand-sons:detachment",),
    )
    catalog = replace(
        base_catalog,
        catalog_id="phase15a-generated-thousand-sons-maulerfiend-catalog",
        source_package_id=("data-package:phase15a:generated-thousand-sons-maulerfiend:2026-08-23"),
        factions=(*base_catalog.factions, *generated.factions),
        army_rules=(*base_catalog.army_rules, *generated.army_rules),
        datasheets=(
            *base_catalog.datasheets,
            generated_maulerfiend,
            thousand_sons_anchor,
        ),
        wargear=(*base_catalog.wargear, *generated.wargear),
        detachments=(*base_catalog.detachments, thousand_sons_detachment),
    )
    resolved_alpha_origins = (
        {
            "maulerfiend": Pose.at(6.0, 20.0),
            "psyker-anchor": Pose.at(18.0, 20.0),
        }
        if alpha_origins is None
        else alpha_origins
    )
    resolved_enemy_origin = Pose.at(18.0, 21.05) if enemy_origin is None else enemy_origin
    return _charge_lifecycle(
        alpha_unit_ids=(*maulerfiend_selection_ids, *ordinary_selection_ids),
        alpha_datasheet_ids_by_selection_id={
            **dict.fromkeys(maulerfiend_selection_ids, "000001029"),
            **dict.fromkeys(ordinary_selection_ids, anchor_datasheet_id),
        },
        alpha_origins=resolved_alpha_origins,
        enemy_unit_ids=("enemy",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=resolved_enemy_origin,
            model_count=5,
        ),
        game_id=game_id,
        catalog=catalog,
    )


def _end_charge_heroic_session(
    *,
    game_id: str,
    maulerfiend_selection_ids: tuple[str, ...],
    ordinary_selection_ids: tuple[str, ...],
    command_points: int,
) -> tuple[LocalGameSession, dict[str, UnitInstance]]:
    maulerfiend_origins = (Pose.at(24.0, 30.0), Pose.at(42.0, 30.0))
    if len(maulerfiend_selection_ids) > len(maulerfiend_origins):
        raise AssertionError("Heroic Intervention fixture supports at most two Maulerfiends.")
    alpha_origins = {
        **{
            selection_id: maulerfiend_origins[index]
            for index, selection_id in enumerate(maulerfiend_selection_ids)
        },
        **{
            selection_id: Pose.at(30.0, 24.0 - (index * 8.0))
            for index, selection_id in enumerate(ordinary_selection_ids)
        },
    }
    lifecycle, units = _generated_snarling_protector_charge_lifecycle(
        game_id=game_id,
        maulerfiend_selection_ids=maulerfiend_selection_ids,
        ordinary_selection_ids=ordinary_selection_ids,
        alpha_origins=alpha_origins,
        enemy_origin=Pose.at(30.0, 30.0),
    )
    state = _state(lifecycle)
    state.active_player_id = "player-b"
    state.replace_charge_phase_state(
        ChargePhaseState(
            battle_round=state.battle_round,
            active_player_id="player-b",
            selected_unit_ids=(units["enemy"].unit_instance_id,),
            declared_target_unit_instance_ids_by_unit={
                units["enemy"].unit_instance_id: (
                    next(
                        unit.unit_instance_id
                        for unit in units.values()
                        if unit.unit_instance_id.startswith("army-alpha:")
                    ),
                )
            },
        ).with_phase_complete()
    )
    enemy = units["enemy"]
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{game_id}:enemy-charge-move",
            source_rule_id=f"{game_id}:enemy-charge-move-source",
            owner_player_id="player-b",
            target_unit_instance_ids=(enemy.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-b",
            ),
            effect_payload={"effect_kind": "charge_grants_fights_first"},
        )
    )
    if command_points:
        state.gain_command_points(
            player_id="player-a",
            amount=command_points,
            source_id=f"{game_id}:command-points",
            source_kind=CommandPointSourceKind.OTHER,
        )
    return LocalGameSession(lifecycle=lifecycle), units


def _set_snarling_source_state_for_heroic_test(
    *,
    state: GameState,
    unit: UnitInstance,
    source_state: str,
) -> None:
    if source_state == "eligible":
        return
    if source_state == "destroyed":
        _destroy_unit_models_for_test(state, unit_instance_id=unit.unit_instance_id)
        return
    if state.battlefield_state is None:
        raise AssertionError("Heroic Intervention source fixture requires battlefield state.")
    if source_state == "unplaced":
        from warhammer40k_core.engine.reserve_arrival_requirements import (
            reposition_destruction_policy,
        )
        from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

        state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                reserve_kind=ReserveKind.RESERVES,
                destruction_deadline_policy=reposition_destruction_policy(
                    mission_setup=state.mission_setup, destruction_deadline_policy=None
                ),
            )
        )
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(unit.unit_instance_id)
        )
        return
    origins = {
        "engaged": Pose.at(30.0, 27.0),
        "out_of_range": Pose.at(5.0, 5.0),
    }
    origin = origins.get(source_state)
    if origin is None:
        raise AssertionError(f"Unsupported Snarling Protector fixture state: {source_state}")
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            _unit_placement_at(
                unit,
                army_id="army-alpha",
                player_id="player-a",
                poses=_compact_test_unit_poses(
                    origin=origin,
                    model_count=len(unit.own_models),
                ),
            )
        )
    )


def _heroic_proposal_from_request(request: DecisionRequest) -> StratagemTargetProposal:
    payload = request.payload
    assert isinstance(payload, dict)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, payload["proposal_request"])
    )


def _submit_end_charge_heroic_target(
    session: LocalGameSession,
    *,
    request: DecisionRequest,
    target_unit_instance_id: str,
    result_id: str,
) -> LifecycleStatus:
    selected = _heroic_proposal_from_request(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=request.actor_id,
            target_unit_instance_id=target_unit_instance_id,
        ),
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND
        },
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value({"proposal": selected.to_payload()}),
        result_id=result_id,
    )

    from tests.heroic_intervention_helpers import drive_heroic_charge_choices

    return drive_heroic_charge_choices(
        session, status, unit_id=target_unit_instance_id, result_prefix=result_id
    )


def _submit_heroic_intervention_no_move(
    session: LocalGameSession,
    *,
    movement_request: DecisionRequest,
    result_id: str,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        movement_request.payload
    )
    return session.submit_parameterized_payload(
        request_id=movement_request.request_id,
        payload=validate_json_value(
            ChargeMoveProposal(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                unit_instance_id=proposal_request.unit_instance_id,
                movement_phase_action="charge_move",
                movement_mode=MovementMode.CHARGE,
                charge_target_unit_instance_ids=(),
                witness=None,
            ).to_payload()
        ),
        result_id=result_id,
    )


def _stratagem_use_for_result_id(
    state: GameState,
    *,
    result_id: str,
) -> StratagemUseRecord:
    matches = tuple(use for use in state.stratagem_use_records if use.result_id == result_id)
    if len(matches) != 1:
        raise AssertionError("Expected exactly one Stratagem use for result ID.")
    return matches[0]


def _require_pending_request(session: LocalGameSession) -> DecisionRequest:
    request = session.lifecycle.pending_decision_request()
    if request is None:
        raise AssertionError("Heroic Intervention session requires a pending request.")
    return request


def _conditional_charge_pair_options(
    request: DecisionRequest,
) -> dict[str, dict[str, object]]:
    pairs: dict[str, dict[str, object]] = {}
    for option in request.options:
        if option.option_id == DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID:
            continue
        payload = cast(dict[str, object], option.payload)
        grants = cast(list[dict[str, object]], payload["selected_charge_declaration_grants"])
        assert len(grants) == 1
        replay_payload = cast(dict[str, object], grants[0]["replay_payload"])
        enemy_id = cast(str, replay_payload["required_enemy_unit_instance_id"])
        assert enemy_id not in pairs
        pairs[enemy_id] = replay_payload
    return pairs


def _conditional_charge_ability_record() -> tuple[
    AbilityCatalogRecord, tuple[RuleClause, RuleClause, RuleClause]
]:
    span = _conditional_charge_rule_span()
    phase_use_clause = RuleClause(
        clause_id="test:conditional-charge:phase-use-exception",
        source_span=span,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.UNIT_SELECTED,
            source_span=span,
            parameters=parameters_from_pairs(
                (
                    ("selection", "stratagem_target"),
                    ("timing_window", "after_unit_selected_as_stratagem_target"),
                    ("source_relationship", "stratagem_targets_source_unit"),
                    ("selected_unit_allegiance", "friendly"),
                    ("stratagem_user", "source_player"),
                    ("usage_scope", "source_model"),
                )
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "stratagem_target"),
                        ("relationship", "stratagem_targets_source_unit"),
                        ("selected_unit_allegiance", "friendly"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.STRATAGEM_USE, source_span=span),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("ability", "stratagem_phase_use_exception"),
                        ("stratagem_id", "heroic-intervention"),
                        ("frequency_scope", "phase_per_unit"),
                        ("bypass_same_stratagem_per_phase", True),
                        ("does_not_block_other_units", True),
                    )
                ),
            ),
        ),
    )
    cost_clause = RuleClause(
        clause_id="test:conditional-charge:heroic-cost",
        source_span=span,
        trigger=phase_use_clause.trigger,
        conditions=phase_use_clause.conditions,
        target=phase_use_clause.target,
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("operation", "modify_stratagem_cost"),
                        ("affected_player", "source_player"),
                        ("delta", -1),
                        ("application_scope", "current_stratagem_use"),
                        ("minimum_cost", 0),
                        ("optional", False),
                        ("stacking", "cumulative"),
                        ("stratagem_id", "heroic-intervention"),
                    )
                ),
            ),
        ),
    )
    charge_clause = RuleClause(
        clause_id="test:conditional-charge:reroll",
        source_span=span,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.UNIT_SELECTED,
            source_span=span,
            parameters=parameters_from_pairs(
                (
                    ("selection", "charging_unit"),
                    ("timing_window", "after_charging_unit_selected_before_charge_roll"),
                    ("source_relationship", "source_unit_declares_charge"),
                )
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "friendly_anchor"),
                        ("relationship", "friendly_engaged_keyword_unit"),
                        ("exclude_source_unit", True),
                    )
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "friendly_anchor"),
                        ("required_keyword", "PSYKER"),
                    )
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("first_subject", "source_unit"),
                        ("second_subject", "friendly_anchor"),
                        ("range_kind", "numeric_range"),
                        ("distance_inches", 12),
                        ("negated", False),
                    )
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "required_enemy"),
                        (
                            "relationship",
                            "enemy_engaged_with_selected_friendly_anchor",
                        ),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        (
                            "ability",
                            "charge_reroll_with_friendly_engaged_keyword_anchor",
                        ),
                        ("roll_type", "charge_roll"),
                        ("component_selection_policy", "whole_roll"),
                        ("selection_policy", "anchor_and_enemy_pair"),
                        (
                            "required_charge_end_relationship",
                            "enemy_engaged_with_selected_anchor",
                        ),
                        ("optional", True),
                    )
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=span,
            parameters=parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    clauses = (phase_use_clause, cost_clause, charge_clause)
    rule_ir = RuleIR(
        rule_id="test:conditional-charge:rule",
        source_id="test:conditional-charge:source",
        normalized_text=span.text,
        parser_version="test:conditional-charge:v1",
        clauses=tuple(sorted(clauses, key=lambda clause: clause.clause_id)),
    )
    return (
        AbilityCatalogRecord(
            record_id="test:conditional-charge:record",
            definition=AbilityDefinition(
                ability_id="test:conditional-charge:ability",
                name="Source-backed Conditional Charge",
                source_id=rule_ir.source_id,
                when_descriptor="When this unit declares a charge.",
                effect_descriptor="Use shared Stratagem and Charge services.",
                restrictions_descriptor="Requires an engaged friendly Psyker within 12 inches.",
                timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
                handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
                replay_payload=validate_json_value(
                    {"rule_ir": cast(JsonValue, rule_ir.to_payload())}
                ),
            ),
            source_kind=AbilitySourceKind.DATASHEET,
            datasheet_id="core-intercessor-like-infantry",
        ),
        clauses,
    )


def _conditional_charge_rule_span() -> TextSpan:
    text = "Source-backed conditional Charge semantic test."
    return TextSpan(text=text, start=0, end=len(text))


def _end_phase_charge_declaration_grant(
    context: ChargeDeclarationContext,
) -> ChargeDeclarationGrant:
    return ChargeDeclarationGrant(
        hook_id=_END_PHASE_CHARGE_GRANT_ID,
        source_id="phase15a:test-charge-grant-source:end-phase",
        label="Test end-phase Charge grant",
        replay_payload={
            "unit_instance_id": context.unit_instance_id,
            "selection_result_id": context.selection_result_id,
        },
        unit_effect_payload={"effect_kind": "phase15a_test_charge_grant"},
        unit_effect_expiration="end_phase",
    )


def _end_turn_charge_declaration_grant(
    context: ChargeDeclarationContext,
) -> ChargeDeclarationGrant:
    return ChargeDeclarationGrant(
        hook_id=_END_TURN_CHARGE_GRANT_ID,
        source_id="phase15a:test-charge-grant-source:end-turn",
        label="Test end-turn Charge grant",
        replay_payload={
            "unit_instance_id": context.unit_instance_id,
            "selection_result_id": context.selection_result_id,
        },
        unit_effect_payload={
            "effect_kind": "phase15a_test_target_charge_grant",
            "target_unit_instance_ids": ["army-beta:enemy"],
        },
        unit_effect_expiration="end_turn",
    )


def _install_charge_declaration_registry(
    lifecycle: GameLifecycle,
    registry: ChargeDeclarationHookRegistry,
) -> None:
    handler = replace(
        lifecycle._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
        charge_declaration_hooks=registry,
    )
    assert isinstance(handler, ChargePhaseHandler)
    lifecycle._charge_phase_handler = handler  # pyright: ignore[reportPrivateUsage]
    flow = lifecycle._battle_round_flow  # pyright: ignore[reportPrivateUsage]
    assert flow is not None
    flow._phase_handlers[BattlePhase.CHARGE] = handler  # pyright: ignore[reportPrivateUsage]


def _charge_modifier_ignore_ability_record(*, datasheet_id: str) -> AbilityCatalogRecord:
    text = "This model can ignore any or all modifiers to Move, Advance and Charge."
    span = TextSpan(text=text, start=0, end=len(text))
    clause = RuleClause(
        clause_id="test:modifier-ignore:charge-clause",
        source_span=span,
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=span),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("ability", "modifier_ignore_permission"),
                        (
                            "modifier_kinds",
                            (
                                "movement_characteristic",
                                "advance_roll",
                                "charge_roll",
                            ),
                        ),
                        ("selection", "any_or_all"),
                    )
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=span,
        ),
    )
    rule_ir = RuleIR(
        rule_id="test:modifier-ignore:charge-rule",
        source_id="test:modifier-ignore:charge-source",
        normalized_text=text,
        parser_version="test:modifier-ignore:v1",
        clauses=(clause,),
    )
    return AbilityCatalogRecord(
        record_id="test:modifier-ignore:charge-record",
        definition=AbilityDefinition(
            ability_id="test:modifier-ignore:charge-ability",
            name="Test Modifier Ignore",
            source_id=rule_ir.source_id,
            when_descriptor="Passive.",
            effect_descriptor=text,
            restrictions_descriptor="This model only.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
                phase=BattlePhaseKind.CHARGE,
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": cast(JsonValue, rule_ir.to_payload())}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _charge_modifier_ignore_registry() -> RuntimeModifierRegistry:
    return RuntimeModifierRegistry.from_bindings(
        charge_roll_modifier_bindings=(
            ChargeRollModifierBinding(
                modifier_id="test:modifier-ignore:charge-binding",
                source_id="test:modifier-ignore:charge-binding-source",
                handler=_modifier_ignore_charge_modifiers,
            ),
        )
    )


def _modifier_ignore_charge_modifiers(
    context: ChargeRollModifierContext,
) -> tuple[RollModifier, ...]:
    return (
        *context.current_roll_modifiers,
        RollModifier(
            modifier_id="test:modifier-ignore:charge-penalty",
            source_id="test:modifier-ignore:charge-penalty-source",
            operand=-1,
        ),
        RollModifier(
            modifier_id="test:modifier-ignore:charge-bonus",
            source_id="test:modifier-ignore:charge-bonus-source",
            operand=1,
        ),
    )


def _install_charge_modifier_ignore_runtime(
    lifecycle: GameLifecycle,
    *,
    ability_index: AbilityCatalogIndex,
    registry: RuntimeModifierRegistry,
) -> None:
    handler = replace(
        lifecycle._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
        ability_indexes_by_player_id={
            "player-a": ability_index,
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        runtime_modifier_registry=registry,
    )
    lifecycle._charge_phase_handler = handler  # pyright: ignore[reportPrivateUsage]
    flow = lifecycle._battle_round_flow  # pyright: ignore[reportPrivateUsage]
    assert flow is not None
    flow._phase_handlers[BattlePhase.CHARGE] = handler  # pyright: ignore[reportPrivateUsage]
    bundle = lifecycle._runtime_content_bundle  # pyright: ignore[reportPrivateUsage]
    assert bundle is not None
    lifecycle._runtime_content_bundle = replace(  # pyright: ignore[reportPrivateUsage]
        bundle,
        runtime_modifier_registry=registry,
        ability_indexes_by_player_id=handler.ability_indexes_by_player_id,
    )
    lifecycle._runtime_content_activation_input_hash = None  # pyright: ignore[reportPrivateUsage]
    lifecycle._refresh_runtime_content_bundle_if_armies_mustered(preserve_existing_bundle=True)  # pyright: ignore[reportPrivateUsage]


def _ignored_charge_modifier_ids(option: DecisionOption) -> tuple[str, ...]:
    payload = option.payload
    if not isinstance(payload, dict):
        return ()
    raw_context = payload.get("modifier_ignore_context")
    if not isinstance(raw_context, dict):
        return ()
    ignored = raw_context.get("ignored_modifiers")
    assert isinstance(ignored, list)
    return tuple(cast(str, item["modifier_id"]) for item in ignored if isinstance(item, dict))


def _charge_roll_request(*, player_id: str, unit_instance_id: str) -> ChargeRollRequest:
    return ChargeRollRequest(
        request_id=f"charge-roll-{player_id}-{unit_instance_id}",
        game_id="phase15a-value-objects",
        battle_round=1,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        source_decision_request_id="source-request-a",
        source_decision_result_id="source-result-a",
    )


def _charge_roll_result(*, player_id: str, unit_instance_id: str) -> ChargeRollResult:
    request = _charge_roll_request(player_id=player_id, unit_instance_id=unit_instance_id)
    roll_state = DiceRollManager(f"phase15a-{player_id}-{unit_instance_id}").roll_fixed(
        request.spec,
        [3, 4],
    )
    return ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _advanced_unit_state(unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:advance-roll",
        game_id="phase15a-eligibility",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase15a-advanced-state").roll_fixed(request.spec, [3])
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _charge_move_request_after_selection(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    result_id: str,
    target_ids: tuple[str, ...] = ("army-beta:enemy",),
) -> DecisionRequest:
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=result_id,
    )
    request = _decision_request(status)
    request = _decision_request(
        choose_charge_targets(
            lifecycle,
            request=request,
            target_ids=target_ids,
            result_id=f"{result_id}:targets",
        )
    )
    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.unit_instance_id == unit_instance_id
    return request


def _charge_move_proposal_request_for_value_tests() -> MovementProposalRequest:
    return MovementProposalRequest(
        request_id="request-a",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-a",
        game_id="phase15b-value-object",
        battle_round=1,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id="unit-a",
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="source-request-a",
        source_decision_result_id="source-result-a",
        spatial_context_hash="0" * 64,
        movement_phase_action="charge_move",
        context={
            "movement_mode": "charge",
            "maximum_distance_inches": 6,
            "reachable_target_unit_instance_ids": ["target-a"],
            "reachable_target_distances_inches": {"target-a": 3.0},
        },
    )


def _submit_charge_move_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: ChargeMoveProposal,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(JsonValue, proposal.to_payload()),
        ).to_result(request)
    )


def _first_proposal_validation_violation(
    status: LifecycleStatus,
) -> dict[str, object]:
    payload = cast(dict[str, object], status.payload)
    validation = cast(dict[str, object], payload["proposal_validation"])
    violations = cast(list[dict[str, object]], validation["violations"])
    assert violations
    return violations[0]


def _charge_path_witness_for_unit(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    dx: float,
    dy: float = 0.0,
    endpoint_only: bool = False,
) -> PathWitness:
    state = _state(lifecycle)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge Move witness helper requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((placement.model_instance_id, (start, end, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _destroy_unit_models_for_test(state: GameState, *, unit_instance_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    found = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                found = True
                updated_units.append(
                    replace(
                        unit,
                        own_models=tuple(
                            replace(model, wounds_remaining=0) for model in unit.own_models
                        ),
                    )
                )
            else:
                updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not found:
        raise AssertionError("Destroyed selected-target fixture unit was not found.")
    state.replace_army_definitions(updated_armies)


def _resolved_charge_move_for_tests(
    lifecycle: GameLifecycle,
    *,
    units: dict[str, UnitInstance],
    unit_key: str,
    target_key: str,
    dx: float,
) -> tuple[ChargeMoveResolution, UnitPlacement]:
    state = _state(lifecycle)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge Move resolution helper requires battlefield_state.")
    unit = units[unit_key]
    target = units[target_key]
    unit_placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    return (
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
                descriptor_version="core-v2-phase15a-test"
            ),
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=(target.unit_instance_id,),
            maximum_distance_inches=6,
            path_witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=unit.unit_instance_id,
                dx=dx,
            ),
        ),
        unit_placement,
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _assert_invalid_charge_submission_keeps_pending_clean(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    status: LifecycleStatus,
    expected_field: str,
) -> None:
    payload = cast(dict[str, object], status.payload)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert payload["invalid_reason"] == "invalid_charging_unit_result"
    assert payload["field"] == expected_field
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.decision_controller.records == ()
    assert _event_payloads(lifecycle, "charging_unit_selected") == ()
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()
    assert _event_payloads(lifecycle, "charge_move_required") == ()
    assert _event_payloads(lifecycle, "charge_no_move_possible") == ()


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _roll_result_from_event(lifecycle: GameLifecycle, event_type: str) -> ChargeRollResult:
    payload = _last_event_payload(lifecycle, event_type)
    return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _payload_has_displacements(payload: dict[str, object]) -> bool:
    transition_batch = payload.get("transition_batch")
    if not isinstance(transition_batch, dict):
        return False
    transition_payload = cast(dict[str, object], transition_batch)
    raw_displacements = transition_payload.get("displacements")
    if not isinstance(raw_displacements, list):
        return False
    displacements = cast(list[object], raw_displacements)
    return bool(displacements)


__all__ = (
    "_advanced_unit_state",
    "_assert_invalid_charge_submission_keeps_pending_clean",
    "_charge_lifecycle",
    "_charge_lifecycle_with_declaration_grants",
    "_charge_modifier_ignore_ability_record",
    "_charge_modifier_ignore_registry",
    "_charge_move_proposal_request_for_value_tests",
    "_charge_move_request_after_selection",
    "_charge_path_witness_for_unit",
    "_charge_roll_request",
    "_charge_roll_result",
    "_compact_test_unit_poses",
    "_conditional_charge_ability_record",
    "_conditional_charge_lifecycle",
    "_conditional_charge_pair_options",
    "_conditional_charge_rule_span",
    "_decision_request",
    "_destroy_unit_models_for_test",
    "_end_charge_heroic_session",
    "_end_phase_charge_declaration_grant",
    "_end_turn_charge_declaration_grant",
    "_event_payloads",
    "_first_proposal_validation_violation",
    "_generated_snarling_protector_charge_lifecycle",
    "_heroic_proposal_from_request",
    "_ignored_charge_modifier_ids",
    "_install_charge_declaration_registry",
    "_install_charge_modifier_ignore_runtime",
    "_last_event_payload",
    "_modifier_ignore_charge_modifiers",
    "_payload_has_displacements",
    "_require_pending_request",
    "_resolved_charge_move_for_tests",
    "_roll_result_from_event",
    "_set_snarling_source_state_for_heroic_test",
    "_state",
    "_stratagem_use_for_result_id",
    "_submit_charge_move_proposal",
    "_submit_end_charge_heroic_target",
    "_submit_heroic_intervention_no_move",
    "_submit_option",
    "_unit_placement_at",
)
