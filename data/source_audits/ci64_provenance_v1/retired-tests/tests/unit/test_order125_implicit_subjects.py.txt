"""Selected Core default-unit subjects compile into the shared executable consumer."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.order122_helpers import submit_quiet_choice
from tests.order125_helpers import (
    SOURCE_ID,
    advance_to_default_unit_selection,
    default_unit_session,
    default_unit_text,
)
from tests.support.ability_presence_fixtures import compiled_ability_rule

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.modifiers import RollModifierOperation, resolve_roll_modifiers
from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_consumers_for_rule
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    eligible_selection_target_unit_ids,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    clause_is_shooting_start_selected_target_selection,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_unit_geometry import present_geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_ir import RuleTargetKind, parameter_payload
from warhammer40k_core.rules.rule_target_subject_parser import target_subject_matches


@pytest.mark.parametrize("noun", ["", " unit"])
def test_selected_default_subject_preserves_keyword_and_source_range(noun: str) -> None:
    rule = compiled_ability_rule(f'Select one friendly PSYKER{noun} within 6" of this model.')
    assert not rule.diagnostics
    target = rule.clauses[0].target
    assert target is not None
    assert target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(target.parameters) == {
        "allegiance": "friendly",
        "required_keyword": "PSYKER",
    }
    assert target.source_span.text == f"Select one friendly PSYKER{noun}"
    assert catalog_rule_ir_consumers_for_rule(rule) == ()


@pytest.mark.parametrize("noun", ["", " unit"])
def test_complete_default_unit_rule_has_a_shared_executable_consumer(noun: str) -> None:
    rule = compiled_ability_rule(
        f"At the start of your opponent's Shooting phase, select one friendly PSYKER{noun} "
        'within 6" of this model. Until the end of the phase, add 1 to the Charge '
        "rolls for that unit."
    )
    assert not rule.diagnostics
    assert "catalog-ir:shooting-start-selected-target-effect" in (
        catalog_rule_ir_consumers_for_rule(rule)
    )


@pytest.mark.parametrize("noun", ["", " unit"])
@pytest.mark.parametrize("attached", [True, False])
def test_catalog_loaded_selection_survives_full_lifecycle_continuations(
    noun: str, attached: bool
) -> None:
    session = default_unit_session(noun=noun, attached=attached)
    request = advance_to_default_unit_selection(session)
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["source_rule_id"] == SOURCE_ID
    assert request.payload["active_player_id"] == "player-b"
    assert request.payload["source_model_instance_id"] == "army-alpha:transport:core-transport:001"
    assert len(request.options) == 1
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    forked = session.fork()
    assert_persistence_viewers_replay(restored)
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id, option_id="decline", result_id="order125-invalid"
        )
    assert restored.to_persistence_payload() == checkpoint
    state = restored.lifecycle.state
    assert state is not None
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    assert "PSYKER" in target.keywords
    psyker_ids = tuple(m.model_instance_id for m in target.own_models if "PSYKER" in m.keywords)
    assert psyker_ids == ("army-alpha:leader:core-character-leader:001",)
    assert (
        scoped_roll_model_ids_for_effect(
            source_rules_unit=target,
            current_roll_model_instance_ids=tuple(m.model_instance_id for m in target.own_models),
            effect_parameters={"required_model_keyword": "PSYKER"},
        )
        == psyker_ids
    )
    restored.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order125-select",
    )
    assert forked.to_persistence_payload() == checkpoint
    effects = [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == (target.unit_instance_id,)
    context = ChargeRollModifierContext(
        state=state,
        unit_instance_id=target.unit_instance_id,
        current_roll_modifiers=(),
    )
    modifiers = RuntimeModifierRegistry.empty().charge_roll_modifiers(context)
    assert len(modifiers) == 1
    assert modifiers[0].operand == 1
    assert modifiers[0].operation is RollModifierOperation.ADD
    assert resolve_roll_modifiers(6, modifiers).final == 7
    assert modifiers[0].source_id is not None
    assert SOURCE_ID in modifiers[0].source_id
    assert_persistence_viewers_replay(restored)
    for index in range(180):
        status = restored.advance_until_decision_or_terminal()
        if state.battle_round == 2:
            break
        assert status.decision_request is not None
        submit_quiet_choice(restored, status.decision_request, result_id=f"order125-after-{index}")
    else:
        raise AssertionError("Full native turn continuation did not finish.")
    assert not [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert RuntimeModifierRegistry.empty().charge_roll_modifiers(context) == ()
    assert_persistence_viewers_replay(restored)


@pytest.mark.parametrize("case", ["legal", "range", "keyword", "allegiance", "source", "owner"])
def test_shared_selection_enforces_real_keyword_owner_range_and_source_boundaries(
    case: str,
) -> None:
    session = default_unit_session()
    state = session.lifecycle.state
    assert state is not None
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    source_id = "army-alpha:transport"
    source_model = "army-alpha:transport:core-transport:001"
    clause = compiled_ability_rule(default_unit_text()).clauses[0]
    if case == "range":
        assert state.battlefield_state is not None
        placement = state.battlefield_state.unit_placement_by_id(source_id)
        state.replace_battlefield_state(
            state.battlefield_state.with_unit_placement(
                replace(
                    placement,
                    model_placements=tuple(
                        replace(row, pose=Pose.at(1, 1)) for row in placement.model_placements
                    ),
                )
            )
        )
    if case == "keyword":
        clause = compiled_ability_rule(default_unit_text(keyword="TRANSPORT")).clauses[0]
    if case == "allegiance":
        clause = compiled_ability_rule(default_unit_text().replace("friendly", "enemy")).clauses[0]
    if case == "source":
        source_model = target.own_models[0].model_instance_id

    def select(*, player_id: str = "player-a") -> tuple[str, ...]:
        return eligible_selection_target_unit_ids(
            state=state,
            source_player_id=player_id,
            source_unit_instance_id=source_id,
            source_model_instance_id=source_model,
            selection_clause=clause,
            explicit_target_unit_ids=(target.unit_instance_id,),
        )

    if case == "owner":
        with pytest.raises(GameLifecycleError, match="source owner drift"):
            select(player_id="player-b")
        return
    actual = select()
    assert actual == ((target.unit_instance_id,) if case == "legal" else ())
    if case == "legal":
        source_models = present_geometry_models_for_rules_unit(
            state=state, unit_instance_id=source_id
        )
        target_models = present_geometry_models_for_rules_unit(
            state=state, unit_instance_id=target.unit_instance_id
        )
        psyker = next(
            row for row in target_models if row.model_id.endswith("core-character-leader:001")
        )
        assert min(row.range_to(psyker) for row in source_models) > 6
        assert min(row.range_to(other) for row in source_models for other in target_models) < 6


@pytest.mark.parametrize(
    "text",
    [
        'Select one friendly UNKNOWN within 6" of this model.',
        'Select one friendly PSYKERS within 6" of this model.',
        'Select one friendly PSYKER arbitrarily within 6" of this model.',
    ],
)
def test_implicit_subject_does_not_invent_keywords_aliases_or_discard_language(text: str) -> None:
    assert compiled_ability_rule(text).diagnostics


@pytest.mark.parametrize("noun", ["model", "unit"])
def test_explicit_noun_and_source_spans_remain_intact(noun: str) -> None:
    text = f'Select one friendly PSYKER {noun} within 6" of this model.'
    rule = compiled_ability_rule(text)
    assert not rule.diagnostics
    assert rule.normalized_text == text
    assert rule.clauses[0].target is not None
    assert rule.clauses[0].target.source_span.text == f"Select one friendly PSYKER {noun}"


def test_implicit_adjacent_keywords_keep_the_existing_conjunction() -> None:
    rule = compiled_ability_rule('Select one friendly PSYKER CHARACTER within 6" of this model.')
    assert not rule.diagnostics
    assert rule.clauses[0].target is not None
    assert parameter_payload(rule.clauses[0].target.parameters) == {
        "allegiance": "friendly",
        "required_keyword_sequence": ("PSYKER", "CHARACTER"),
    }


@pytest.mark.parametrize("noun", ["", " unit"])
def test_ordinary_trigger_does_not_admit_unestablished_weapon_context(noun: str) -> None:
    text = default_unit_text(noun=noun).replace(
        "Charge rolls for that unit",
        "Strength characteristic of ranged weapons equipped by models in that unit",
    )
    rule = compiled_ability_rule(text)
    assert not rule.diagnostics
    assert "catalog-ir:shooting-start-selected-target-effect" not in (
        catalog_rule_ir_consumers_for_rule(rule)
    )


@pytest.mark.parametrize("keyword", ["CHAOS DAEMONS", "A-B", "PSYKER"])
def test_subject_matcher_preserves_literal_declared_keyword_parts(keyword: str) -> None:
    text = f'Select one friendly {keyword} within 6" of this model.'
    matches = target_subject_matches(text, source_keyword_sequence_parts=(keyword,))
    assert len(matches) == 1
    assert matches[0].group("keyword") == keyword
    assert matches[0].group(0) == f"Select one friendly {keyword}"


def test_subject_matcher_keeps_explicit_overlap_and_literal_order() -> None:
    text = 'Select one friendly PSYKER unit; select one enemy PSYKER within 6".'
    matches = target_subject_matches(text, source_keyword_sequence_parts=("PSYKER",))
    assert [match.group(0) for match in matches] == [
        "Select one friendly PSYKER unit",
        "select one enemy PSYKER",
    ]
    assert [match.start() for match in matches] == [0, text.index("select one enemy")]


@pytest.mark.parametrize("noun", [" model", " MODEL"])
def test_explicit_model_subject_keeps_typed_evidence_and_no_unit_consumer(noun: str) -> None:
    rule = compiled_ability_rule(default_unit_text(noun=noun))
    assert not rule.diagnostics
    selection = rule.clauses[0]
    assert selection.target is not None
    assert selection.target.source_span.text == f"select one friendly PSYKER{noun}"
    assert parameter_payload(selection.target.parameters) == {
        "allegiance": "friendly",
        "required_keyword": "PSYKER",
    }
    assert selection.trigger is not None
    assert parameter_payload(selection.trigger.parameters) == {
        "edge": "start",
        "owner": "opponent",
        "phase": "shooting",
        "subject": "selected_model",
    }
    assert not clause_is_shooting_start_selected_target_selection(selection)
    assert catalog_rule_ir_consumers_for_rule(rule) == ()


def test_explicit_model_catalog_subject_never_offers_a_unit_selection_in_native_play() -> None:
    session = default_unit_session(noun=" model")
    state = session.lifecycle.state
    assert state is not None
    reached_opponent_shooting = False
    for index in range(180):
        status = session.advance_until_decision_or_terminal()
        reached_opponent_shooting |= (
            state.active_player_id == "player-b"
            and state.current_battle_phase is BattlePhase.SHOOTING
        )
        if state.battle_round == 2:
            break
        request = status.decision_request
        assert request is not None
        assert not (
            isinstance(request.payload, dict) and request.payload.get("source_rule_id") == SOURCE_ID
        )
        submit_quiet_choice(session, request, result_id=f"order125-model-boundary-{index}")
    else:
        raise AssertionError("Explicit model boundary did not complete the native turn.")
    assert reached_opponent_shooting
    assert not [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert_persistence_viewers_replay(session)
