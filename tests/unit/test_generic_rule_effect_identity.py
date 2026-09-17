"""R42-003: persisted identity belongs to one activation, binding and effect slot."""

from dataclasses import replace
from typing import Any, cast

import pytest
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.generic_rule_effect_identity import generic_rule_persisting_effect_id
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_source,
)


def _scene() -> tuple[RuleIR, RuleExecutionContext]:
    lifecycle, units = fight_lifecycle(
        game_id="order42-effect-identity",
        alpha_unit_ids=("first", "second"),
        enemy_unit_ids=("enemy",),
        origins={
            "first": Pose.at(10, 10),
            "second": Pose.at(20, 10),
            "enemy": Pose.at(40, 10),
        },
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
    )
    state = lifecycle.state
    assert state is not None
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="order42:identity-stealth-grant",
        raw_text="That unit gains Stealth until the end of the phase.",
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    assert rule_ir.is_supported
    return rule_ir, RuleExecutionContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
        timing_window_id="order42:first-activation",
        source_unit_instance_id=units["first"].unit_instance_id,
        source_model_instance_id=units["first"].own_models[0].model_instance_id,
        target_unit_instance_ids=(units["first"].unit_instance_id,),
        target_player_id="player-a",
        trigger_payload={"decision_result_id": "order42:first-result"},
        state=state,
        event_log=EventLog(),
    )


@pytest.mark.parametrize("change", ["owner", "activation", "binding"])
def test_separate_generic_activations_and_bindings_coexist(change: str) -> None:
    rule_ir, context = _scene()
    first = execute_rule_ir(rule_ir=rule_ir, context=context)
    if change == "owner":
        second_context = replace(
            context,
            player_id="player-b",
            source_unit_instance_id="army-beta:enemy",
            source_model_instance_id="army-beta:enemy:core-character-leader:001",
            target_unit_instance_ids=("army-beta:enemy",),
            target_player_id="player-b",
        )
    elif change == "activation":
        second_context = replace(
            context,
            timing_window_id="order42:second-activation",
            trigger_payload={"decision_result_id": "order42:second-result"},
        )
    else:
        second_context = replace(context, target_unit_instance_ids=("army-alpha:second",))
    second = execute_rule_ir(rule_ir=rule_ir, context=second_context)
    assert first.status is RuleExecutionStatus.APPLIED
    assert second.status is RuleExecutionStatus.APPLIED
    first_effect = first.created_persisting_effects[0]
    second_effect = second.created_persisting_effects[0]
    assert first_effect.effect_id != second_effect.effect_id
    assert first_effect.expiration == second_effect.expiration
    state = context.state
    assert state is not None
    assert state.persisting_effects == sorted(
        [first_effect, second_effect], key=lambda effect: effect.effect_id
    )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="already exists for effect_id"):
        execute_rule_ir(rule_ir=rule_ir, context=second_context)
    assert state.to_payload() == before


@pytest.mark.parametrize("shared_object", [False, True])
def test_identical_effect_slots_have_separate_persisted_identities(shared_object: bool) -> None:
    rule_ir, context = _scene()
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]
    repeated = effect if shared_object else replace(effect)
    rule_ir = replace(rule_ir, clauses=(replace(clause, effects=(effect, repeated)),))
    result = execute_rule_ir(rule_ir=rule_ir, context=context)
    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 2
    assert len({effect.effect_id for effect in result.created_persisting_effects}) == 2
    assert [payload["effect_index"] for payload in result.effect_payloads] == [0, 1]
    restored_ir = RuleIR.from_payload(rule_ir.to_payload())
    _, fresh = _scene()
    replayed = execute_rule_ir(rule_ir=restored_ir, context=fresh)
    assert replayed.to_payload() == result.to_payload()


def test_full_clause_identity_distinguishes_equal_suffixes() -> None:
    rule_ir, context = _scene()
    clause = rule_ir.clauses[0]
    rule_ir = replace(
        rule_ir,
        clauses=(
            replace(clause, clause_id="order42:first:grant"),
            replace(clause, clause_id="order42:second:grant"),
        ),
    )
    result = execute_rule_ir(rule_ir=rule_ir, context=context)
    assert result.status is RuleExecutionStatus.APPLIED
    assert len({effect.effect_id for effect in result.created_persisting_effects}) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("game_id", "another-game"),
        ("player_id", "player-b"),
        ("battle_round", 2),
        ("phase", BattlePhase.SHOOTING),
        ("active_player_id", "player-b"),
        ("timing_window_id", "another-window"),
        ("source_unit_instance_id", "army-alpha:second"),
        ("source_model_instance_id", "army-alpha:second:core-character-leader:001"),
        ("target_unit_instance_ids", ("army-alpha:second",)),
        ("target_player_id", "player-b"),
        ("trigger_payload", {"decision_result_id": "another-recorded-activation"}),
    ],
)
def test_identity_binds_recorded_activation_context(field: str, value: object) -> None:
    rule_ir, context = _scene()

    def derive(current: RuleExecutionContext) -> str:
        return generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=0,
            target_unit_instance_ids=context.target_unit_instance_ids,
            context=current,
        )

    identity = derive(context)
    changed = derive(replace(context, **cast(dict[str, Any], {field: value})))
    assert identity != changed
    assert identity == derive(replace(context, state=None, event_log=EventLog()))
    assert identity == derive(replace(context, record_persisting_effects=False))


@pytest.mark.parametrize("index", [-1, 1, True, "0"])
def test_identity_rejects_invalid_effect_slots(index: object) -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match="valid effect slot"):
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=cast(int, index),
            context=context,
            target_unit_instance_ids=context.target_unit_instance_ids,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rule_ir", None, "typed source IR"),
        ("clause", None, "typed source IR"),
        ("context", None, "RuleExecutionContext"),
        ("targets", ["army-alpha:first"], "inventory is invalid"),
        ("targets", ("",), "inventory is invalid"),
        ("targets", (42,), "inventory is invalid"),
        ("targets", ("army-alpha:first", "army-alpha:first"), "inventory is duplicated"),
    ],
)
def test_identity_rejects_malformed_authority(field: str, value: object, message: str) -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match=message):
        generic_rule_persisting_effect_id(
            rule_ir=cast(RuleIR, value) if field == "rule_ir" else rule_ir,
            clause=cast(RuleClause, value) if field == "clause" else rule_ir.clauses[0],
            effect_index=0,
            context=cast(RuleExecutionContext, value) if field == "context" else context,
            target_unit_instance_ids=cast(tuple[str, ...], value)
            if field == "targets"
            else context.target_unit_instance_ids,
        )


def test_identity_requires_loaded_clause_and_canonicalizes_effect_target_set() -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match="loaded source clause"):
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=replace(rule_ir.clauses[0], clause_id="another-source:grant"),
            effect_index=0,
            context=context,
            target_unit_instance_ids=context.target_unit_instance_ids,
        )
    targets = ("army-alpha:first", "army-alpha:second")
    identities = {
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=0,
            context=context,
            target_unit_instance_ids=order,
        )
        for order in (targets, tuple(reversed(targets)))
    }
    assert len(identities) == 1


def test_both_players_accept_fidelity_in_fight_and_replay_through_completion() -> None:
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
    from tests.phase15c_fight_order_helpers import submit_minimal_melee_declaration
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.target_replacement_reaction_helpers import fidelity_replacement_catalog

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        retained_attack_sources_2026_09 as retained_sources,
    )

    profile = retained_sources.stratagem_profile()
    catalog, rifle, second = fidelity_replacement_catalog(distinct_weapon_groups=True)
    lifecycle, units = fight_lifecycle(
        catalog=catalog,
        game_id="order56-two-fidelity-0",
        alpha_unit_ids=("alpha", "ally"),
        enemy_unit_ids=("enemy",),
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        origins={"alpha": Pose.at(10, 10), "ally": Pose.at(40, 20), "enemy": Pose.at(12, 10)},
        fights_first_unit_keys=("alpha",),
        alpha_detachment_ids=(profile.detachment_id,),
        enemy_detachment_ids=(profile.detachment_id,),
    )
    state = lifecycle.state
    assert state is not None
    for player in state.player_ids:
        state.gain_command_points(
            player_id=player,
            amount=1,
            source_id="order42:fidelity-starting-cp",
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    pending_request(session)
    initial = session.lifecycle.to_payload()
    accepted: set[str] = set()
    coexistence_checked = False
    for _ in range(60):
        checkpoint = session.lifecycle.to_payload()
        session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
        assert session.lifecycle.to_payload() == checkpoint
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "out_of_phase_shooting_completed" for event in events):
            break
        assert session.lifecycle.state is not None
        assert session.lifecycle.state.battle_round == 1, accepted
        request = pending_request(session)
        use_options = [
            option
            for option in request.options
            if option.option_id.startswith(f"use-stratagem:{profile.stratagem_id}:target:")
        ]
        if use_options:
            assert request.actor_id is not None
            assert request.actor_id not in accepted
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"order42:use-fidelity:{request.actor_id}",
                option_id=use_options[0].option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
            accepted.add(request.actor_id)
            current = session.lifecycle.state
            assert current is not None
            assert current.command_point_total(request.actor_id) == 0
            effects = [
                effect
                for effect in current.persisting_effects
                if effect.source_rule_id == profile.source_id
                and isinstance(effect.effect_payload, dict)
                and effect.effect_payload.get("effect_kind") == "generic_rule_execution"
            ]
            assert len(effects) == len(accepted)
            if len(accepted) == 2:
                assert len({effect.effect_id for effect in effects}) == 2
                assert {effect.owner_player_id for effect in effects} == accepted
                coexistence_checked = True
        elif request.decision_type == "select_destruction_reaction":
            option = next(
                option for option in request.options if option.option_id.endswith(":shoot")
            )
            session.submit_option(
                request_id=request.request_id,
                result_id=f"order42:choose-retained-shooting:{request.request_id}",
                option_id=option.option_id,
            )
        elif request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(
                request=request,
                target_unit_id=units["alpha"].unit_instance_id,
                weapon_profile_id=rifle.weapon_profiles[0].profile_id,
            )
            other = _proposal_from_request(
                request=request,
                target_unit_id=units["alpha"].unit_instance_id,
                weapon_profile_id=second.weapon_profiles[0].profile_id,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order42:retained-declaration:{request.request_id}",
                payload=validate_json_value(
                    replace(
                        proposal, declarations=(*proposal.declarations, *other.declarations)
                    ).to_payload()
                ),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "submit_melee_declaration":
            status = submit_minimal_melee_declaration(
                session.lifecycle,
                request=request,
                result_id=f"order42:parent-melee:{request.request_id}",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "submit_stratagem_target_proposal":
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"decline:{request.request_id}",
                payload=stratagem_decline_payload(),
            )
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("The two Unending Fidelity uses did not complete retained Shooting.")
    assert accepted == {"player-a", "player-b"}
    assert coexistence_checked
    final_state = session.lifecycle.state
    assert final_state is not None
    assert final_state.out_of_phase_shooting_state is None
    assert final_state.battlefield_state is not None
    assert (
        units["enemy"].own_models[0].model_instance_id
        in final_state.battlefield_state.removed_model_ids
    )
    uses = [
        use for use in final_state.stratagem_use_records if use.stratagem_id == profile.stratagem_id
    ]
    assert len(uses) == 2
    assert {use.phase for use in uses} == {BattlePhase.FIGHT}
    artifact = ReplayArtifact.capture(
        artifact_id="order42:two-fidelity-uses",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
