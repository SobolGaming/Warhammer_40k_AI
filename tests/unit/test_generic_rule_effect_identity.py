from typing import Any, cast

from tests.shared.category_migration.generic_rule_effect_identity import (
    BattlePhase,
    EventLog,
    GameLifecycleError,
    ObjectiveRuleScope,
    Pose,
    RuleClause,
    RuleExecutionContext,
    RuleExecutionStatus,
    RuleIR,
    RuleSourceText,
    _scene,
    compile_rule_source_text,
    execute_rule_ir,
    fight_lifecycle,
    generic_rule_persisting_effect_id,
    keyword_source,
    pytest,
    replace,
)


def test_both_players_accept_fidelity_in_fight_and_replay_through_completion() -> None:
    from tests.dice_result_semantics_helpers import assert_active_player_history, open_phase
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
        game_id="order103-fixture-08-01",
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
    open_phase(session.lifecycle)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    accepted: set[str] = set()
    coexistence_checked = False
    for _ in range(60):
        assert_active_player_history(session.lifecycle)
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


__all__: list[str] = []
__all__ += ["Any", "EventLog", "GameLifecycleError", "ObjectiveRuleScope", "RuleClause"]
__all__ += ["RuleExecutionContext", "RuleExecutionStatus", "RuleIR", "RuleSourceText", "_scene"]
__all__ += ["cast", "compile_rule_source_text", "execute_rule_ir"]
__all__ += ["generic_rule_persisting_effect_id", "keyword_source", "pytest"]
