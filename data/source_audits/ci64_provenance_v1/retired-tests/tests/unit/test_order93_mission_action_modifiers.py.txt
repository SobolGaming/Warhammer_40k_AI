from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.action_movement_interruption_helpers import action_opportunity_session
from tests.order93_nonattack_helpers import add_nonattack_effects
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner


@pytest.mark.parametrize(
    "selection", ["keep-all", "ignore-positive", "ignore-negative", "ignore-zero"]
)
def test_automatic_action_oc_choices_control_eligibility_restore_and_replay(selection: str) -> None:
    session, unit_id = _action_modifier_session(replacement=selection == "ignore-zero")
    initial = session.lifecycle.to_payload()
    selected_models: set[str] = set()
    for _ in range(11):
        request = pending_request(session)
        if request.decision_type != "select_modifier_ignores":
            break
        payload = cast(dict[str, JsonValue], request.payload)
        subject = cast(dict[str, JsonValue], payload["subject"])
        source = cast(dict[str, JsonValue], payload["source_context"])
        assert request.actor_id == "player-b"
        assert subject["unit_instance_id"] == unit_id
        assert subject["kind"] == "objective_control_characteristic"
        assert source["source_kind"] == "mission_action_objective_control"
        assert source["continuation"] == "phase"
        selected_models.add(cast(str, subject["model_instance_id"]))
        snapshot = session.lifecycle.to_payload()
        session = LocalGameSession(GameLifecycle.from_payload(snapshot))
        assert session.lifecycle.to_payload() == snapshot
        opponent_view = canonical_json(session.view(viewer_player_id="player-a"))
        assert "mission_action_objective_control" not in opponent_view
        assert "source_context" not in opponent_view
        operations = cast(list[dict[str, JsonValue]], payload["modifiers"])
        decided = cast(list[str], payload["decided_modifier_ids"])
        current = cast(dict[str, JsonValue], operations[len(decided)]["operation"])
        ignore = (
            (selection == "ignore-positive" and cast(int, current["operand"]) > 0)
            or (selection == "ignore-negative" and cast(int, current["operand"]) < 0)
            or (selection == "ignore-zero" and current["operation"] == "set")
        )
        prefix = "ignore:" if ignore else "keep:"
        option_id = next(
            (option.option_id for option in request.options if option.option_id.startswith(prefix)),
            "ignore-remaining" if ignore else "keep-remaining",
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:oc-choice",
            option_id=option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    else:
        raise AssertionError("Mission Action modifier choices did not finish.")
    assert len(selected_models) == 5
    if selection == "ignore-positive":
        assert request.decision_type != "start_mission_action"
    else:
        assert request.decision_type == "start_mission_action"
        action_payload = cast(dict[str, JsonValue], request.payload)
        assert action_payload["mission_action_opportunity"] is True
        assert action_payload["objective_control_modifier_scope_id"] is not None
        snapshot = session.lifecycle.to_payload()
        session = LocalGameSession(GameLifecycle.from_payload(snapshot))
        assert session.lifecycle.to_payload() == snapshot
        option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict)
            and (
                option.option_id == "continue_to_shooting"
                if selection == "keep-all"
                else option.payload.get("mission_action_id") == "maintain-control"
                and option.payload.get("unit_instance_id") == unit_id
            )
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:start",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        state = session.lifecycle.state
        assert state is not None
        assert any(
            action.unit_instance_id == unit_id for action in state.mission_action_states
        ) is (selection != "keep-all")
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id=f"mission-action-oc:{selection}",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


def _action_modifier_session(*, replacement: bool = False) -> tuple[LocalGameSession, str]:
    session, unit_id = action_opportunity_session(
        catalog_transform=lambda catalog: _oc_catalog(catalog, replacement=replacement)
    )
    state = session.lifecycle.state
    assert state is not None
    add_nonattack_effects(
        state,
        unit_id=unit_id,
        owner="player-b",
        characteristic="objective_control",
        operations=False,
    )
    return LocalGameSession(GameLifecycle.from_payload(session.lifecycle.to_payload())), unit_id


def _oc_catalog(catalog: ArmyCatalog, *, replacement: bool) -> ArmyCatalog:
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicModifierTrace(
                                characteristic=value.characteristic,
                                source_value=value.raw,
                                modifiers=(
                                    ModifierTerm(ModifierOperation.ADD, 2).bind(
                                        modifier_id="action-oc:bonus",
                                        source_id="source:action-oc:bonus",
                                        characteristic=value.characteristic,
                                    ),
                                    ModifierTerm(
                                        ModifierOperation.SET
                                        if replacement
                                        else ModifierOperation.ADD,
                                        0 if replacement else -2,
                                    ).bind(
                                        modifier_id="action-oc:penalty",
                                        source_id="source:action-oc:penalty",
                                        characteristic=value.characteristic,
                                    ),
                                ),
                            ).value()
                            if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )


def test_permission_candidate_probe_retains_live_generic_grants_and_malformed_candidates() -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        modifier_ignore_permission_candidates_present,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND

    state = battle_state(decisions=DecisionController())
    indexes = (AbilityCatalogIndex.from_records(()),)
    effect = generic_effect(
        effect_id="candidate:permission",
        owner_player_id="player-a",
        target_unit_instance_ids=(state.army_definitions[0].units[0].unit_instance_id,),
        target_kind="this_unit",
        effect_kind="grant_ability",
        parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
    )
    state.record_persisting_effect(
        replace(effect, effect_id="candidate:unrelated", effect_payload={"effect_kind": "other"})
    )
    assert not modifier_ignore_permission_candidates_present(state=state, ability_indexes=indexes)
    state.record_persisting_effect(effect)
    assert modifier_ignore_permission_candidates_present(state=state, ability_indexes=indexes)
    state.remove_persisting_effects_by_id((effect.effect_id,))
    assert not modifier_ignore_permission_candidates_present(state=state, ability_indexes=indexes)
    # Candidate detection is conservative: malformed generic evidence must reach
    # the ordinary strict decoder, not become a cached negative permission.
    state.record_persisting_effect(
        replace(effect, effect_payload={"effect_kind": GENERIC_RULE_EFFECT_KIND})
    )
    assert modifier_ignore_permission_candidates_present(state=state, ability_indexes=indexes)


def test_permission_candidate_probe_preserves_catalog_descriptor_activation() -> None:
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.abilities import (
        GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        AbilityCatalogIndex,
        AbilityCatalogRecord,
        AbilityDefinition,
        AbilitySourceKind,
        AbilityTimingDescriptor,
    )
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        modifier_ignore_permission_candidates_present,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleTargetKind,
        RuleTargetSpec,
        parameters_from_pairs,
    )

    state = battle_state(decisions=DecisionController())
    span = TextSpan(start=0, end=4, text="test")
    rule = RuleIR(
        rule_id="candidate:rule",
        source_id="candidate:source",
        normalized_text="test",
        parser_version="candidate-test",
        clauses=(
            RuleClause(
                clause_id="candidate:clause",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                duration=RuleDuration(kind=RuleDurationKind.WHILE_CONDITION_TRUE, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (("ability", "modifier_ignore_permission"), ("selection", "any_or_all"))
                        ),
                    ),
                ),
            ),
        ),
    )
    record = AbilityCatalogRecord(
        record_id="candidate:record",
        definition=AbilityDefinition(
            ability_id="candidate:ability",
            name="Permission",
            source_id=rule.source_id,
            when_descriptor="Passive",
            effect_descriptor="Permission",
            restrictions_descriptor="Source scope",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload={"rule_ir": cast(JsonValue, rule.to_payload())},
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=state.army_definitions[0].units[0].datasheet_id,
    )
    assert modifier_ignore_permission_candidates_present(
        state=state, ability_indexes=(AbilityCatalogIndex.from_records((record,)),)
    )
    assert not modifier_ignore_permission_candidates_present(
        state=state,
        ability_indexes=(AbilityCatalogIndex.from_records((replace(record, disabled=True),)),),
    )
