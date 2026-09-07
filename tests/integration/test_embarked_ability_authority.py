from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.characteristic_modifier_helpers import (
    resolve_characteristic_handler,
    resolve_historical_handler,
)
from tests.support.ability_presence_fixtures import ability_presence_fixture, compiled_ability_rule

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_command_point_runtime import CatalogCommandPointRuntime
from warhammer40k_core.engine.catalog_command_point_support import (
    clause_is_supported_stratagem_cost_modifier,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    eligible_selection_target_unit_ids,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_catalog_records
from warhammer40k_core.engine.stratagem_cost_choice_hooks import StratagemCostChoiceRequestContext
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleConditionKind
from warhammer40k_core.rules.source_data import RuleSourceText


@pytest.mark.parametrize("embarked", [True, False])
@pytest.mark.parametrize("restricted", [True, False])
def test_embarked_command_point_ability_uses_its_own_battlefield_restriction(
    embarked: bool,
    restricted: bool,
) -> None:
    config, state, decisions = ability_presence_fixture(embarked=embarked)
    text = (
        "At the end of your Command phase, if this model is on the battlefield, you gain 1CP."
        if restricted
        else "At the end of your Command phase, roll one D6: on a 1+, you gain 1CP."
    )
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="test:p01c:command-point",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=("INFANTRY",),
    ).rule_ir
    record = AbilityCatalogRecord(
        record_id="test:p01c:command-point",
        definition=AbilityDefinition(
            ability_id="test:p01c:command-point",
            name="Command point ability",
            source_id=rule_ir.source_id,
            when_descriptor="End of own Command phase.",
            effect_descriptor=text,
            restrictions_descriptor="Roll a 1+.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.END_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-character-leader",
    )
    runtime = CatalogCommandPointRuntime(
        ability_indexes_by_player_id={
            player: AbilityCatalogIndex.from_records((record,) if player == "player-a" else ())
            for player in state.player_ids
        },
        armies=tuple(state.army_definitions),
    )
    registry = RuntimeContentEventHandlerRegistry.from_bindings(runtime.event_handler_bindings())
    index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(), handler_registry=registry
    )
    before = state.command_point_total("player-a")
    index.dispatch(
        RuntimeContentEvent(
            event_id="p01c-command-end",
            game_id=state.game_id,
            player_id="player-a",
            battle_round=state.battle_round,
            trigger_kind=TimingTriggerKind.END_PHASE,
            phase=BattlePhase.COMMAND,
            active_player_id="player-a",
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert state.command_point_total("player-a") == before + int(not restricted or not embarked)


@pytest.mark.parametrize("presence", ["embarked", "reserves", "battlefield"])
@pytest.mark.parametrize("restricted", [True, False])
@pytest.mark.parametrize("optional", [True, False])
def test_stratagem_cost_sources_enforce_their_own_battlefield_restriction(
    presence: str, restricted: bool, optional: bool
) -> None:
    _, state, decisions = ability_presence_fixture(
        embarked=presence == "embarked", reserves=presence == "reserves", attached=False
    )
    restriction = "if this model is on the battlefield, " if restricted else ""
    text = (
        f"Once per battle round, {restriction}"
        "you can target a friendly unit with a Stratagem for 0CP."
    )
    rule_ir = compiled_ability_rule(text)
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]
    # Exercise both supported runtime modes without adding an automatic parser shape.
    effect = replace(
        effect,
        parameters=tuple(
            replace(parameter, value=optional) if parameter.key == "optional" else parameter
            for parameter in effect.parameters
        ),
    )
    clause = replace(clause, effects=(effect,))
    assert clause_is_supported_stratagem_cost_modifier(clause)
    assert (
        any(
            parameter.key == "relationship" and parameter.value == "source_model_on_battlefield"
            for condition in clause.conditions
            for parameter in condition.parameters
        )
        is restricted
    )
    rule_ir = replace(rule_ir, clauses=(clause,))
    record = AbilityCatalogRecord(
        record_id="test:p01c:stratagem-cost",
        definition=AbilityDefinition(
            ability_id="test:p01c:stratagem-cost",
            name="Stratagem cost ability",
            source_id=rule_ir.source_id,
            when_descriptor="When a friendly unit is targeted with a Stratagem.",
            effect_descriptor=text,
            restrictions_descriptor=restriction or "Once per battle round.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-character-leader",
    )
    runtime = CatalogCommandPointRuntime(
        ability_indexes_by_player_id={
            player: AbilityCatalogIndex.from_records((record,) if player == "player-a" else ())
            for player in state.player_ids
        },
        armies=tuple(state.army_definitions),
    )
    definition = next(
        record.definition
        for record in eleventh_edition_stratagem_catalog_records()
        if record.definition.stratagem_id == "insane-bravery"
    )
    eligibility = StratagemEligibilityContext.from_state(
        state=state, player_id="player-a", trigger_kind=TimingTriggerKind.START_PHASE
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id="army-alpha:passengers",
    )
    eligible = not restricted or presence == "battlefield"
    if optional:
        # Only enumerate the opportunity here; no player choice or mutation is bypassed.
        source_request = DecisionRequest(
            request_id="p01c:stratagem-request",
            decision_type=STRATAGEM_DECISION_TYPE,
            actor_id="player-a",
            payload={"finite": True},
            options=(
                DecisionOption(
                    option_id="p01c:stratagem-use",
                    label="Use Stratagem",
                    payload={"submission_kind": STRATAGEM_DECISION_TYPE},
                ),
            ),
        )
        request = runtime.stratagem_cost_choice_request(
            StratagemCostChoiceRequestContext(
                state=state,
                decisions=decisions,
                source_request=source_request,
                source_result=DecisionResult.for_request(
                    result_id="p01c:stratagem-result",
                    request=source_request,
                    selected_option_id=source_request.options[0].option_id,
                ),
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
        assert (request is not None) is eligible
    else:
        registry = StratagemCostModifierRegistry.from_bindings(
            runtime.stratagem_cost_modifier_bindings()
        )
        cost = registry.modified_command_point_cost(
            StratagemCostModifierContext(
                state=state,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
                base_command_point_cost=definition.command_point_cost,
                current_command_point_cost=definition.command_point_cost,
            )
        )
        assert cost == definition.command_point_cost - int(eligible)


@pytest.mark.parametrize("anchor", ["this model", "this unit"])
def test_embarked_aura_can_affect_its_own_rules_unit_only(anchor: str) -> None:
    _, state, decisions = ability_presence_fixture()
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="test:p01c:aura",
            raw_text=(
                f'Aura: while a friendly unit is within 6" of {anchor}, '
                "subtract 1 from wound rolls."
            ),
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=("INFANTRY",),
    ).rule_ir
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="player-a",
            source_unit_instance_id="army-alpha:leader",
            source_model_instance_id=source.components[-1].unit.own_model_ids()[0],
            state=state,
            event_log=decisions.event_log,
        ),
    )
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [source.unit_instance_id]


@pytest.mark.parametrize("condition", ["range", "visibility", "none"])
@pytest.mark.parametrize("embarked", [True, False])
def test_target_selection_uses_spatial_conditions_instead_of_source_suppression(
    condition: str,
    embarked: bool,
) -> None:
    _, state, _ = ability_presence_fixture(embarked=embarked)
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    model_id = source.component_unit_for_model(
        source.components[-1].unit.own_model_ids()[0]
    ).own_model_ids()[0]
    clause = compiled_ability_rule(
        'At the start of the Fight phase, select one friendly unit within 18" of and visible '
        "to this model. Until the end of the phase, add 1 to the Strength characteristic "
        "of melee weapons equipped by models in that unit."
    ).clauses[0]
    keep = {
        "range": {RuleConditionKind.DISTANCE_PREDICATE},
        "visibility": {RuleConditionKind.VISIBILITY_PREDICATE},
        "none": set[RuleConditionKind](),
    }[condition]
    clause = replace(clause, conditions=tuple(c for c in clause.conditions if c.kind in keep))
    targets = eligible_selection_target_unit_ids(
        state=state,
        source_player_id="player-a",
        source_unit_instance_id="army-alpha:leader",
        source_model_instance_id=model_id,
        selection_clause=clause,
        explicit_target_unit_ids=None,
    )
    assert source.unit_instance_id in targets
    if embarked and condition != "none":
        assert targets == (source.unit_instance_id,)
    if condition == "none":
        assert "army-alpha:transport" in targets


def _ability_session(*, attached: bool = True, reserves: bool = False) -> LocalGameSession:
    config, state, decisions = ability_presence_fixture(
        attached=attached,
        reserves=reserves,
        ability_text=(
            "Once per battle, at the start of any phase, this model can use this ability. "
            "If it does, until the end of the phase, add 3 to the Attacks characteristic of "
            "melee weapons equipped by this model and those weapons have "
            "the [DEVASTATING WOUNDS] ability."
        ),
    )
    return LocalGameSession(
        lifecycle=GameLifecycle.from_payload(
            cast(
                Any,
                {
                    "config": config.to_payload(),
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                    "parameterized_movement_proposals": True,
                },
            )
        )
    )


@pytest.mark.parametrize(("attached", "reserves"), [(True, False), (False, False), (False, True)])
@pytest.mark.parametrize("activate", [True, False])
def test_embarked_activation_facade_restores_and_replays_exactly(
    attached: bool,
    reserves: bool,
    activate: bool,
) -> None:
    session = _ability_session(attached=attached, reserves=reserves)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE
    option = next(
        option
        for option in request.options
        if cast(dict[str, Any], option.payload)["activate"] is activate
    )
    pending = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(copy.deepcopy(pending)).to_persistence_payload()
        == pending
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="p01c-activation",
    )
    assert status.status_kind not in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(copy.deepcopy(checkpoint))
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(
            EventStreamCursor(),
            viewer_player_id=viewer,
        )
    json.dumps(checkpoint, allow_nan=False)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="replay:p01c")).run()
    assert replay.reproduced_exactly, replay.to_payload()


@pytest.mark.parametrize("drift", ["actor", "payload", "cargo", "phase"])
def test_embarked_activation_rejects_drift_before_queue_pop(drift: str) -> None:
    session = _ability_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    result = DecisionResult.for_request(
        result_id="p01c-invalid",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    state = session.lifecycle.state
    assert state is not None
    if drift == "actor":
        result = replace(result, actor_id="player-b")
    elif drift == "payload":
        result = replace(result, payload={})
    elif drift == "cargo":
        state.transport_cargo_states.clear()
    else:
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    before = session.lifecycle.decision_controller.to_payload()
    status = session.lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.decision_controller.to_payload() == before


def test_firing_deck_preserves_attached_ability_ownership() -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
    from warhammer40k_core.engine.catalog_rule_consumption import CatalogWeaponKeywordGrantRuntime
    from warhammer40k_core.engine.phases.shooting_firing_deck import _available_firing_deck_weapons
    from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext

    config, state, _ = ability_presence_fixture(
        ability_text=(
            "While this model is leading a unit, ranged weapons equipped by models in that unit "
            "have the [LETHAL HITS] ability."
        )
    )
    transport = next(
        unit
        for unit in state.army_definitions[0].units
        if unit.unit_instance_id == "army-alpha:transport"
    )
    weapons = _available_firing_deck_weapons(
        state=state, transport_unit=transport, army_catalog=config.army_catalog
    )
    weapon = next(
        weapon
        for weapon in weapons
        if weapon.get("firing_deck_source_unit_instance_id") == "army-alpha:passengers"
    )
    assert weapon["model_instance_id"] == transport.own_models[0].model_instance_id
    records = catalog_ability_records_from_catalog(config.army_catalog)
    runtime = CatalogWeaponKeywordGrantRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=transport.unit_instance_id,
        attacker_model_instance_id=weapon["model_instance_id"],
        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
        weapon_profile=weapon["weapon_profile"],
    )
    assert runtime.weapon_profile_modifier(context) == weapon["weapon_profile"]
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    assert "firing_deck_source_model_instance_id" in weapon
    own_profile = runtime.weapon_profile_modifier(
        replace(
            context,
            attacking_unit_instance_id=source.unit_instance_id,
            attacker_model_instance_id=weapon["firing_deck_source_model_instance_id"],
        )
    )
    assert WeaponKeyword.LETHAL_HITS in own_profile.keywords


@pytest.mark.parametrize("reserves", [True, False])
@pytest.mark.parametrize("keyword", ["Infantry Character", "Vehicle Transport"])
def test_live_and_historical_proximity_use_the_same_off_battlefield_self_exception(
    reserves: bool,
    keyword: str,
) -> None:
    from tests.battle_shock_historical_helpers import historical_battle_shock_context_for_unit

    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
    from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
    from warhammer40k_core.engine.runtime_modifiers import UnitCharacteristicModifierContext

    config, state, decisions = ability_presence_fixture(
        reserves=reserves,
        attached=not reserves,
        ability_text=(
            f'While this unit is within 12" of one or more friendly {keyword} models, '
            "models in this unit have a Leadership characteristic of 6+ and each time a model "
            "in this unit makes an attack, add 1 to the Hit roll."
        ),
    )
    records = catalog_ability_records_from_catalog(config.army_catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    (binding,) = runtime.unit_characteristic_modifier_bindings()
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    current = resolve_characteristic_handler(
        binding.handler,
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=source.unit_instance_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=7,
            current_value=7,
        ),
    )
    history = historical_battle_shock_context_for_unit(
        state=state,
        decisions=decisions,
        unit_instance_id=source.unit_instance_id,
        active_player_id="player-a",
    )
    assert binding.historical_leadership_handler is not None
    historical = resolve_historical_handler(binding.historical_leadership_handler, history, 7)
    assert current == historical == (6 if keyword == "Infantry Character" else 7)


@pytest.mark.parametrize("fault", ["absent", "conflicting", "incomplete", "dead"])
def test_ability_presence_requires_current_living_and_explicit_presence_authority(
    fault: str,
) -> None:
    from warhammer40k_core.engine.ability_presence import (
        ability_presence,
        active_ability_model_ids_for_unit,
    )
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

    _, state, _ = ability_presence_fixture()
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    leader = next(
        component.unit
        for component in source.components
        if component.unit.unit_instance_id == "army-alpha:leader"
    )
    if fault == "absent":
        state.transport_cargo_states.clear()
        assert ability_presence(state=state, rules_unit=source).active_model_ids == ()
    elif fault == "conflicting":
        state.battlefield_state = create_deterministic_battlefield_scenario(
            battlefield_id="conflict", armies=tuple(state.army_definitions)
        ).battlefield_state
        with pytest.raises(GameLifecycleError, match="conflicting"):
            ability_presence(state=state, rules_unit=source)
    elif fault == "incomplete":
        cargo = state.transport_cargo_states[0]
        state.transport_cargo_states[0] = replace(
            cargo, embarked_unit_instance_ids=("army-alpha:leader",)
        )
        with pytest.raises(GameLifecycleError, match=r"incomplete|membership"):
            ability_presence(state=state, rules_unit=source)
    else:
        model = leader.own_models[0]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=source.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
        assert active_ability_model_ids_for_unit(state=state, unit=leader) == ()


def test_embarked_source_artifacts_preserve_reviewed_transcript_and_observation_pins() -> None:
    import hashlib

    from tools.build_core_embarked_abilities_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_embarked_abilities_2026_09 as source,
    )

    payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    rules = source.source_rules()
    assert set(package.evidence_required_source_ids) == {rule.source_id for rule in rules}
    for rule in rules:
        assert rule.load_support_status == "loaded"
        assert rule.semantic_execution_status == "executable_engine_runtime"
        assert hashlib.sha256(rule.source_text.encode()).hexdigest() == rule.transcription_sha256
    evidence = source.source_evidence_records()
    assert len(evidence) == 4
    assert evidence[1].provider_name == "Game Datamissions"
    assert evidence[1].app_version == "931"
    assert evidence[3].provider_name == "40k.app"
    assert evidence[3].observed_at == "2026-09-07T00:02:56Z"
    with pytest.raises(source.EmbarkedAbilitiesSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")
