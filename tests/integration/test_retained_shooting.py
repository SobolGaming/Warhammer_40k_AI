from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _compact_shooting_lifecycle,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import (
    for_the_chapter_catalog,
    pending_retained_attack,
    unending_fidelity_catalog,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import DamageProfile
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DamageKind,
    DestructionReactionKind,
    FeelNoPainSource,
    apply_damage_to_model,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    retained_attack_sources_2026_09 as retained_sources,
)


def test_order_30_retained_shooter_keeps_range_restriction_and_ability_geometry() -> None:
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.catalog_attack_context_rule_runtime import rules_units_within
    from warhammer40k_core.engine.lone_operative import lone_operative_target_allowed
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.unit_abilities import LoneOperativeAbilityProfile

    session, model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
    )
    state = session.lifecycle.state
    assert state is not None
    for army in state.army_definitions:
        if army.player_id != "player-a":
            continue
        for unit in army.units:
            state.record_persisting_effect(
                generic_effect(
                    effect_id=f"retained-range:{unit.unit_instance_id}",
                    owner_player_id=army.player_id,
                    target_unit_instance_ids=(unit.unit_instance_id,),
                    target_kind="this_unit",
                    effect_kind="set_contextual_status",
                    parameters={
                        "status": "shooting_target_range_restriction",
                        "targeting_max_range_inches": 100.0,
                        "source_effect_kind": "source_backed_range_limit",
                    },
                )
            )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="retain-for-range-restricted-shots",
        option_id="order-30-fight-on-death",
    )
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    assert isinstance(request.payload, dict)
    proposal = request.payload["proposal_request"]
    assert isinstance(proposal, dict)
    candidates = proposal["target_candidates"]
    assert isinstance(candidates, list)
    candidate = next(item for item in candidates if isinstance(item, dict) and item["is_legal"])
    assert isinstance(candidate, dict)
    target_id = candidate["target_unit_instance_id"]
    assert isinstance(target_id, str)
    state = session.lifecycle.state
    assert state is not None
    source_id = state.unit_instance_id_for_model(model_id)
    assert rules_units_within(
        state, source_id, target_id, 100.0, attacker_model_instance_id=model_id
    )
    source_view = rules_unit_view_by_id(state=state, unit_instance_id=source_id)
    assert lone_operative_target_allowed(
        scenario=battlefield_scenario_for_state(state=state),
        attacker_unit=source_view.components[0].unit,
        attacker_model_instance_id=model_id,
        target_rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=target_id),
        profile=LoneOperativeAbilityProfile(
            source_id="test-source:retained-range", range_inches=100
        ),
    )
    shooting_proposal = _proposal_from_request(request=request, target_unit_id=target_id)
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="retained-range-declaration",
        payload=validate_json_value(shooting_proposal.to_payload()),
    )
    for _ in range(30):
        submit_fixture_request(session, pending_request(session))
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload() == (
        session.lifecycle.to_payload()
    )


@pytest.mark.parametrize("with_feel_no_pain", [False, True])
def test_order_30_for_the_chapter_shoots_after_own_hazardous_death(with_feel_no_pain: bool) -> None:
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=for_the_chapter_catalog(hazardous=True),
        game_id="order34-own-hazard-True-16" if with_feel_no_pain else "order36-own-hazard-False-3",
        enemy_model_count=5,
    )
    state = lifecycle.state
    assert state is not None
    alpha = units["intercessor-1"]
    model_id = alpha.own_models[0].model_instance_id
    if with_feel_no_pain:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model_id,
            decline_allowed=True,
            sources=(FeelNoPainSource(source_id="own-hazard-fnp", threshold=6),),
        )
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=alpha.unit_instance_id,
        model_instance_id=model_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    accepted = False
    saw_feel_no_pain = False
    for index in range(50):
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain":
            saw_feel_no_pain = True
        if request.decision_type == "select_destruction_reaction":
            if request.actor_id == "player-a":
                assert not accepted
                accepted = True
                option = next(
                    option
                    for option in request.options
                    if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
                )
                session.submit_option(
                    request_id=request.request_id,
                    result_id="accept-own-hazardous-death",
                    option_id=option.option_id,
                )
            else:
                session.submit_option(
                    request_id=request.request_id,
                    result_id=f"decline-{index}",
                    option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
                )
        else:
            submit_fixture_request(session, request)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        assert (
            GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
            == session.lifecycle.to_payload()
        )
        if model_id in state.battlefield_state.removed_model_ids:
            break
    assert accepted, "Own Hazardous destruction must consult the source-backed shooting grant."
    assert saw_feel_no_pain is with_feel_no_pain
    events = session.lifecycle.decision_controller.event_log.records
    assert (
        sum(
            event.event_type == "retained_shooting_hazardous_automatically_passed"
            for event in events
        )
        == 1
    )
    assert sum(event.event_type == "hazardous_test_resolved" for event in events) == 1
    assert (
        sum(
            event.event_type == "attack_sequence_models_attacked"
            and isinstance(event.payload, dict)
            and model_id in cast(list[str], event.payload["model_instance_ids"])
            for event in events
        )
        == 2
    )
    assert (
        sum(
            event.event_type == "model_destroyed"
            and isinstance(event.payload, dict)
            and event.payload.get("model_instance_id") == model_id
            for event in events
        )
        == 1
    )


def test_order_30_for_the_chapter_loads_from_source_backed_catalog() -> None:
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=for_the_chapter_catalog(),
        game_id="order-30-catalog-shoot",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_model_count=3,
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    pending_request(LocalGameSession(lifecycle=lifecycle))
    state = lifecycle.state
    assert state is not None
    for model in units["enemy"].own_models:
        sources = state.destruction_reaction_sources_for_model(
            model_instance_id=model.model_instance_id
        )
        assert len(sources) == 1
        assert sources[0].source_rule_id == retained_sources.FOR_THE_CHAPTER_SOURCE_ID
        assert sources[0].reaction_kind is DestructionReactionKind.SHOOT_ON_DEATH
        assert isinstance(sources[0].payload, dict)
        assert sources[0].payload["trigger_roll_threshold"] == 3
        assert sources[0].payload["shooting_hazardous_tests_automatically_pass"] is True
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.to_payload() == lifecycle.to_payload()


def test_order_30_for_the_chapter_executes_with_automatic_hazardous_success() -> None:
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=for_the_chapter_catalog(hazardous=True),
        game_id="order-30-chapter-hazardous",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_model_count=3,
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("For the Chapter! did not reach its source-backed grant.")
    state = session.lifecycle.state
    assert state is not None
    retained = retained_destructions(state=state)
    assert len(retained) == 1
    model_id = retained[0].model_instance_id
    assert model_id in units["enemy"].own_model_ids()
    source = retained[0].eligible_sources[0]
    assert source.source_rule_id == retained_sources.FOR_THE_CHAPTER_SOURCE_ID
    session.submit_option(
        request_id=request.request_id, result_id="chapter-accept", option_id=source.source_id
    )
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    proposal = _proposal_from_request(request=request, target_unit_id="army-alpha:intercessor-1")
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="chapter-shoot",
        payload=validate_json_value(proposal.to_payload()),
    )
    for _ in range(40):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        assert (
            GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
            == session.lifecycle.to_payload()
        )
        if model_id in state.battlefield_state.removed_model_ids:
            break
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            session.submit_option(
                request_id=request.request_id,
                result_id=f"decline-{request.request_id}",
                option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
            )
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("For the Chapter! did not complete its retained shooting.")
    automatic = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "retained_shooting_hazardous_automatically_passed"
    ]
    assert len(automatic) == 1
    assert isinstance(automatic[0].payload, dict)
    assert automatic[0].payload["model_instance_id"] == model_id
    assert automatic[0].payload["source_rule_id"] == retained_sources.FOR_THE_CHAPTER_SOURCE_ID
    _assert_completed_retained_shooting_history_is_authenticated(session, model_id)


def _assert_completed_retained_shooting_history_is_authenticated(
    session: LocalGameSession, model_id: str
) -> None:
    from warhammer40k_core.engine.model_attack_history import validate_retained_model_attack_history
    from warhammer40k_core.engine.retained_shooting_history import (
        validate_retained_shooting_history,
    )

    state = session.lifecycle.state
    assert state is not None
    events = session.lifecycle.decision_controller.event_log.records
    validate_retained_shooting_history(state=state, event_records=events)
    changes: tuple[tuple[str, str, JsonValue, str], ...] = (
        ("retained_shooting_started", "attacks_completed", True, "entitlement drift"),
        ("retained_shooting_started", "suspended_shooting", [], "suspended state"),
        ("retained_shooting_attacks_completed", "extra", True, "drifted fields"),
        ("retained_shooting_attacks_completed", "attack_pools", {}, "pools are invalid"),
        ("retained_shooting_attacks_completed", "attack_pools", [], "discarded its declared"),
        ("retained_shooting_attacks_completed", "attack_pools", [{}], "exact declaration"),
        ("out_of_phase_shooting_completed", "source_rule_id", "forged", "authority drift"),
        ("out_of_phase_shooting_completed", "player_id", "forged", "authority drift"),
        ("retained_shooting_resumed_parent", "extra", True, "resumed before completing"),
        ("retained_shooting_resumed_parent", "model_instance_id", "forged", "innermost"),
        (
            "retained_shooting_hazardous_automatically_passed",
            "weapon_instance_ids",
            [],
            "weapon identity drift",
        ),
        (
            "retained_shooting_hazardous_automatically_passed",
            "source_rule_id",
            "forged",
            "weapon identity drift",
        ),
    )
    for event_type, field, value, diagnostic in changes:
        event = next(event for event in events if event.event_type == event_type)
        assert isinstance(event.payload, dict)
        altered = replace(event, payload={**event.payload, field: value})
        history = tuple(altered if item == event else item for item in events)
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retained_shooting_history(state=state, event_records=history)

    for event_type, diagnostic in (
        ("fight_on_death_retention_selected", "original destruction selection"),
        ("attack_sequence_completed", "before its attack sequence"),
        ("out_of_phase_shooting_completed", "ordinary executor completion"),
        ("fight_on_death_destruction_completed", "physical destruction completed"),
        ("out_of_phase_shooting_declaration_accepted", "exception lacks source authority"),
    ):
        history = tuple(event for event in events if event.event_type != event_type)
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retained_shooting_history(state=state, event_records=history)
    for event_type, diagnostic in (
        ("retained_shooting_started", "parent differs from chronological history"),
        ("retained_shooting_attacks_completed", "completed more than once"),
        ("retained_shooting_hazardous_automatically_passed", "weapon identity drift"),
    ):
        event = next(event for event in events if event.event_type == event_type)
        index = events.index(event)
        history = (*events[:index], event, *events[index:])
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retained_shooting_history(state=state, event_records=history)

    model_ids = frozenset({model_id})
    validate_retained_model_attack_history(event_records=events, model_instance_ids=model_ids)
    participation = next(
        event
        for event in events
        if event.event_type == "attack_sequence_models_attacked"
        and isinstance(event.payload, dict)
        and model_id in cast(list[str], event.payload["model_instance_ids"])
    )
    assert isinstance(participation.payload, dict)
    participation_changes: tuple[tuple[str, JsonValue], ...] = (
        ("phase", "charge"),
        ("battle_round", 99),
        ("active_player_id", "wrong-player"),
        ("attack_phase", "fight"),
        ("model_instance_ids", []),
    )
    for field, value in participation_changes:
        altered = replace(participation, payload={**participation.payload, field: value})
        history = tuple(altered if item == participation else item for item in events)
        with pytest.raises(GameLifecycleError, match="differs from its declaration"):
            validate_retained_model_attack_history(
                event_records=history, model_instance_ids=model_ids
            )
    for event_type, diagnostic in (
        ("attack_sequence_models_attacked", "missing its completed attacks"),
        ("out_of_phase_shooting_declaration_accepted", "lacks its declaration"),
    ):
        history = tuple(event for event in events if event.event_type != event_type)
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retained_model_attack_history(
                event_records=history, model_instance_ids=model_ids
            )

    declaration = next(
        event
        for event in events
        if event.event_type == "out_of_phase_shooting_declaration_accepted"
    )
    assert isinstance(declaration.payload, dict)
    malformed_declarations: tuple[tuple[JsonValue, str], ...] = (
        (None, "requires an object"),
        ({**declaration.payload, "result_id": ""}, "requires an identifier"),
        ({**declaration.payload, "attack_pools": None}, "requires weapon entries"),
    )
    for payload, diagnostic in malformed_declarations:
        altered = replace(declaration, payload=payload)
        history = tuple(altered if item == declaration else item for item in events)
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retained_model_attack_history(
                event_records=history, model_instance_ids=model_ids
            )
    index = events.index(declaration)
    with pytest.raises(GameLifecycleError, match="duplicate declarations"):
        validate_retained_model_attack_history(
            event_records=(*events[:index], declaration, *events[index:]),
            model_instance_ids=model_ids,
        )
    altered = replace(
        participation,
        payload={**participation.payload, "sequence_id": "forged", "model_instance_ids": {}},
    )
    with pytest.raises(GameLifecycleError, match="requires model identifiers"):
        validate_retained_model_attack_history(
            event_records=tuple(altered if item == participation else item for item in events),
            model_instance_ids=model_ids,
        )

    from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase

    malformed_participations: tuple[tuple[JsonValue, str], ...] = (
        (None, "history fields drift"),
        ({**participation.payload, "model_instance_ids": [None]}, "IDs are invalid"),
    )
    for payload, diagnostic in malformed_participations:
        with pytest.raises(GameLifecycleError, match=diagnostic):
            model_has_attacked_this_phase(
                event_records=(replace(participation, payload=payload),),
                model_instance_id=model_id,
                battle_round=1,
                active_player_id="player-a",
                phase="shooting",
            )


def test_order_30_shoot_on_death_without_available_weapons_completes_once() -> None:
    from tests.retained_attack_helpers import lethal_retained_attack_catalog

    from warhammer40k_core.engine.damage_allocation import DestructionReactionSource

    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=lethal_retained_attack_catalog(),
        enemy_datasheet=("core-character-leader", "core-character-leader", 1),
        enemy_pose=Pose.at(30, 35),
        game_id="order-30-no-retained-weapons",
    )
    state = lifecycle.state
    assert state is not None
    model_id = units["enemy"].own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="no-weapons-shooting-grant",
                source_rule_id="no-weapons-shooting-grant",
                reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
            ),
        ),
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(40):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("The weaponless model did not reach its retained choice.")
    status = session.submit_option(
        request_id=request.request_id,
        result_id="retain-without-weapons",
        option_id="no-weapons-shooting-grant",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    for _ in range(10):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload() == (
        session.lifecycle.to_payload()
    )
    events = session.lifecycle.decision_controller.event_log.records
    completions = [
        event for event in events if event.event_type == "retained_shooting_attacks_completed"
    ]
    assert len(completions) == 1
    assert isinstance(completions[0].payload, dict)
    assert completions[0].payload["attack_pools"] == []
    assert (
        sum(
            event.event_type == "model_destroyed"
            and isinstance(event.payload, dict)
            and event.payload.get("model_instance_id") == model_id
            for event in events
        )
        == 1
    )


@pytest.mark.parametrize("action", [RetainedAttackAction.SHOOT, RetainedAttackAction.FIGHT])
@pytest.mark.parametrize("attached", [False, True])
def test_order_30_unending_fidelity_executes_one_selected_attack(
    action: RetainedAttackAction,
    attached: bool,
) -> None:
    profile = retained_sources.stratagem_profile()
    lifecycle, units = fight_lifecycle(
        catalog=unending_fidelity_catalog(),
        game_id="order-30-fidelity",
        alpha_unit_ids=("alpha",),
        enemy_unit_ids=("enemy", "leader") if attached else ("enemy",),
        enemy_unit_specs={"enemy": ("core-intercessor-like-infantry", "core-intercessor-like", 1)}
        if attached
        else None,
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="enemy"
            ),
        )
        if attached
        else (),
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        origins={
            "alpha": Pose.at(10, 10),
            "enemy": Pose.at(12, 10),
            "leader": Pose.at(12, 11.5),
        },
        fights_first_unit_keys=("alpha",),
        enemy_detachment_ids=(profile.detachment_id,),
    )
    state = lifecycle.state
    assert state is not None
    target_view = rules_unit_view_by_id(
        state=state, unit_instance_id=units["enemy"].unit_instance_id
    )
    assert (target_view.unit_instance_id != units["enemy"].unit_instance_id) is attached
    state.gain_command_points(
        player_id="player-b",
        amount=1,
        source_id="fixture-starting-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    used = False
    for _ in range(40):
        request = pending_request(session)
        option = next(
            (
                option
                for option in request.options
                if option.option_id
                == f"use-stratagem:{profile.stratagem_id}:target:{units['enemy'].unit_instance_id}"
            ),
            None,
        )
        if option is not None:
            status = session.submit_option(
                request_id=request.request_id, result_id="use-fidelity", option_id=option.option_id
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
            used = True
            from warhammer40k_core.engine.retained_attack_grants import (
                persisted_retained_attack_sources,
            )

            current = session.lifecycle.state
            assert current is not None
            grants = [
                effect
                for effect in current.persisting_effects
                if effect.source_rule_id == profile.source_id
            ]
            assert len(grants) == 1
            assert grants[0].target_unit_instance_ids == (target_view.unit_instance_id,)
            for model in target_view.own_models:
                sources = persisted_retained_attack_sources(
                    state=current, model_instance_id=model.model_instance_id
                )
                assert len(sources) == 1, (target_view.unit_instance_id, model.model_instance_id)
            continue
        if request.decision_type == "select_destruction_reaction":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Unending Fidelity did not reach retention.")
    assert used
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-b") == 0
    record = retained_destructions(state=state)[0]
    model_id = units["enemy"].own_models[0].model_instance_id
    assert record.model_instance_id == model_id
    assert len(record.eligible_sources) == 1
    source = record.eligible_sources[0]
    assert source.source_rule_id == profile.source_id
    assert source.reaction_kind is DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH
    assert len(request.options) == 3
    session.submit_option(
        request_id=request.request_id,
        result_id="choose-fidelity-action",
        option_id=f"{source.source_id}:{action.value}",
    )
    checked_scope_orders: set[tuple[str, ...]] = set()
    for _ in range(40):
        checkpoint = session.lifecycle.to_payload()
        assert checkpoint["state"] is not None
        scopes = checkpoint["state"]["active_player_scopes"]
        if len(scopes) > 1:
            # R36-001: restore must preserve the complete nesting order, including moves.
            checked_scope_orders.add(tuple(scope["kind"] for scope in scopes))
            forged = deepcopy(checkpoint)
            assert forged["state"] is not None
            forged["state"]["active_player_scopes"].reverse()
            with pytest.raises(GameLifecycleError, match=r"scope stack.*action order"):
                GameLifecycle.from_payload(forged)
        restored = GameLifecycle.from_payload(checkpoint)
        assert restored.to_payload() == checkpoint
        session = LocalGameSession(lifecycle=restored)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            assert action is RetainedAttackAction.SHOOT
            proposal = _proposal_from_request(
                request=request, target_unit_id=units["alpha"].unit_instance_id
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="fidelity-shot",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        elif attached and request.decision_type == "submit_melee_declaration":
            from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest

            melee = MeleeDeclarationProposalRequest.from_decision_request(request)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="fidelity-attached-fight",
                payload={
                    "proposal_request_id": melee.request_id,
                    "proposal_kind": melee.proposal_kind,
                    "player_id": melee.actor_id,
                    "battle_round": melee.battle_round,
                    "unit_instance_id": melee.unit_instance_id,
                    "source_decision_request_id": melee.source_decision_request_id,
                    "source_decision_result_id": melee.source_decision_result_id,
                    "declarations": [
                        {
                            "attacker_model_instance_id": weapon["model_instance_id"],
                            "wargear_id": weapon["wargear_id"],
                            "weapon_profile_id": weapon["weapon_profile_id"],
                            "target_allocations": [
                                {"target_unit_instance_id": units["alpha"].unit_instance_id}
                            ],
                        }
                        for weapon in cast(
                            tuple[dict[str, JsonValue], ...], melee.available_weapons
                        )
                    ],
                },
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Unending Fidelity attack did not complete.")
    if action is RetainedAttackAction.SHOOT:
        assert ("fight", "out_of_phase_shoot") in checked_scope_orders
    events = session.lifecycle.decision_controller.event_log.records
    participations = [
        event.payload
        for event in events
        if event.event_type == "attack_sequence_models_attacked"
        and isinstance(event.payload, dict)
        and model_id in cast(list[str], event.payload["model_instance_ids"])
    ]
    assert len(participations) == 1
    assert isinstance(participations[0], dict)
    assert participations[0]["attack_phase"] == (
        "shooting" if action is RetainedAttackAction.SHOOT else "fight"
    )
    assert (
        sum(
            event.event_type == "model_destroyed"
            and isinstance(event.payload, dict)
            and event.payload.get("model_instance_id") == model_id
            for event in events
        )
        == 1
    )
    assert not retained_destructions(state=state)

    if attached and action is RetainedAttackAction.FIGHT:
        # The first weapon group destroyed the sole target. The remaining
        # declared group must finish without allocating or attacking again.
        skipped = [event for event in events if event.event_type == "attack_pool_not_allocated"]
        assert len(skipped) == 1
        assert isinstance(skipped[0].payload, dict)
        assert skipped[0].payload["reason"] == "target_destroyed_and_removed"


@pytest.mark.parametrize(
    "field",
    ["source_id", "model_instance_id", "source_result_id", "attacks_completed", "parent_cause_id"],
)
def test_order_30_retained_shooting_restoration_rejects_execution_forgery(field: str) -> None:
    session, _model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="retain-for-forgery",
        option_id="order-30-fight-on-death",
    )
    pending_request(session)
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    effect = next(
        effect
        for effect in payload["state"]["persisting_effects"]
        if effect["effect_payload"].get("effect_kind") == "retained_destruction_shooting"
    )
    effect["effect_payload"]["execution"][field] = (
        True if field == "attacks_completed" else "forged-authority"
    )
    with pytest.raises(GameLifecycleError, match="Retained shooting"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_effect_field",
        "effect_source",
        "missing_execution_field",
        "non_boolean_completion",
        "extra_host_context",
        "foreign_host_model",
        "foreign_host_result",
        "missing_execution_owner",
        "foreign_owner",
        "missing_host",
    ],
)
def test_order_30_retained_shooting_host_and_effect_authority_fail_closed(mutation: str) -> None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.retained_shooting import current_retained_shooter
    from warhammer40k_core.engine.retained_shooting_history import (
        validate_retained_shooting_history,
    )

    session, _model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="retain-for-host-integrity",
        option_id="order-30-fight-on-death",
    )
    pending_request(session)
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    state_payload = payload["state"]
    effect = next(
        effect
        for effect in state_payload["persisting_effects"]
        if effect["effect_payload"].get("effect_kind") == "retained_destruction_shooting"
    )
    execution = effect["effect_payload"]["execution"]
    host = state_payload["out_of_phase_shooting_state"]
    if mutation == "extra_effect_field":
        effect["effect_payload"]["unregistered"] = True
    elif mutation == "effect_source":
        effect["source_rule_id"] = "forged-source"
    elif mutation == "missing_execution_field":
        del execution["attacks_completed"]
    elif mutation == "non_boolean_completion":
        execution["attacks_completed"] = "false"
    elif mutation == "extra_host_context":
        host["source_context"]["unregistered"] = True
    elif mutation == "foreign_host_model":
        host["source_context"]["model_instance_id"] = (
            "army-alpha:intercessor-1:core-intercessor-like:001"
        )
    elif mutation == "foreign_host_result":
        host["source_decision_result_id"] = "forged-result"
    elif mutation == "missing_execution_owner":
        state_payload["persisting_effects"].remove(effect)
    elif mutation == "foreign_owner":
        effect["owner_player_id"] = "player-a"
    else:
        state_payload["out_of_phase_shooting_state"] = None

    def validate_runtime_authority() -> None:
        restored_state = GameState.from_payload(state_payload)
        if mutation in {"foreign_owner", "missing_host"}:
            validate_retained_shooting_history(
                state=restored_state,
                event_records=session.lifecycle.decision_controller.event_log.records,
            )
        else:
            current_retained_shooter(state=restored_state)

    with pytest.raises(GameLifecycleError, match="Retained shooting"):
        validate_runtime_authority()
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_order_30_shoot_on_death_entitles_only_the_destroyed_model() -> None:
    session, model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
    )
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_or_none(model_id)
    assert placement is not None, "Shoot On Death must retain the original base before selection."
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-retained-shooting",
        option_id="order-30-fight-on-death",
    )
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    assert state.out_of_phase_shooting_state is not None
    outer = request.payload
    assert isinstance(outer, dict)
    payload = outer["proposal_request"]
    assert isinstance(payload, dict)
    assert payload["unit_instance_id"] == placement.unit_instance_id
    weapons = payload["available_weapons"]
    assert isinstance(weapons, list)
    assert weapons
    assert all(
        isinstance(weapon, dict) and weapon["model_instance_id"] == model_id for weapon in weapons
    )
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    proposal = _proposal_from_request(request=request, target_unit_id="army-alpha:intercessor-1")
    before_records = session.lifecycle.decision_controller.records
    for field in ("source_decision_result_id", "attacker_model_instance_id"):
        invalid_payload = proposal.to_payload()
        if field == "source_decision_result_id":
            invalid_payload["source_decision_result_id"] = "stale-retained-source-result"
        else:
            invalid_payload["declarations"][0]["attacker_model_instance_id"] = "unentitled-model"
        invalid = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"invalid-retained-{field}",
            payload=validate_json_value(invalid_payload),
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.decision_controller.records == before_records
        assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="declare-retained-shooting",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    for _ in range(30):
        assert (
            GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
            == session.lifecycle.to_payload()
        )
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Retained shooting did not finish and remove its model.")
    completed = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "retained_shooting_attacks_completed"
    ]
    assert len(completed) == 1
    assert not retained_destructions(state=state)


def test_order_30_unending_fidelity_rejects_a_model_that_already_fought() -> None:
    profile = retained_sources.stratagem_profile()
    catalog = unending_fidelity_catalog()
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(weapon, damage_profile=DamageProfile.fixed(1))
                    for weapon in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    lifecycle, units = fight_lifecycle(
        catalog=catalog,
        game_id="order-30-fidelity-prior-fight",
        alpha_unit_ids=("alpha",),
        enemy_unit_ids=("enemy",),
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        origins={"alpha": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        fights_first_unit_keys=("enemy",),
        enemy_detachment_ids=(profile.detachment_id,),
    )
    state = lifecycle.state
    assert state is not None
    model = units["enemy"].own_models[0]
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=units["enemy"].unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.wounds_remaining - 1,
        damage_kind=DamageKind.NORMAL,
    )
    state.gain_command_points(
        player_id="player-b",
        amount=1,
        source_id="fixture-starting-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    used = False
    for _ in range(40):
        request = pending_request(session)
        assert request.decision_type != "select_destruction_reaction"
        option = next(
            (
                option
                for option in request.options
                if option.option_id
                == f"use-stratagem:{profile.stratagem_id}:target:{units['enemy'].unit_instance_id}"
            ),
            None,
        )
        if option is not None:
            session.submit_option(
                request_id=request.request_id,
                result_id="use-fidelity-after-fight",
                option_id=option.option_id,
            )
            used = True
        elif request.decision_type == "submit_stratagem_target_proposal":
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"decline-{request.request_id}",
                payload=stratagem_decline_payload(),
            )
        elif any(option.option_id == "decline_stratagem_window" for option in request.options):
            session.submit_option(
                request_id=request.request_id,
                result_id=f"decline-{request.request_id}",
                option_id="decline_stratagem_window",
            )
        else:
            submit_fixture_request(session, request)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model.model_instance_id in state.battlefield_state.removed_model_ids:
            break
        assert state.current_battle_phase is BattlePhase.FIGHT
    assert used
    events = session.lifecycle.decision_controller.event_log.records
    trigger = next(
        event
        for event in events
        if event.event_type == "fight_on_death_retention_trigger_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == model.model_instance_id
    )
    assert isinstance(trigger.payload, dict)
    assert trigger.payload["applicable"] is False
    assert trigger.payload["trigger_roll"] is None
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    forged = session.lifecycle.to_payload()
    participation = next(
        event
        for event in forged["decisions"]["event_log"]
        if event["event_type"] == "attack_sequence_models_attacked"
        and isinstance(event["payload"], dict)
        and model.model_instance_id in cast(list[str], event["payload"]["model_instance_ids"])
    )
    payload = participation["payload"]
    assert isinstance(payload, dict)
    payload["model_instance_ids"] = []
    with pytest.raises(GameLifecycleError, match=r"attack|applicability"):
        GameLifecycle.from_payload(forged)


@pytest.mark.parametrize(
    ("game_id", "child_before_parent"),
    [("order-30-presence", False), ("order32-nested-retained-0", True)],
)
def test_order_30_nested_retained_shooting_restores_each_parent_and_redacts_authority(
    game_id: str,
    child_before_parent: bool,
) -> None:
    session, parent_model_id = pending_retained_attack(
        game_id=game_id,
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        counter_shooting=True,
    )
    accepted_models: set[str] = set()
    checked_child_checkpoint = False
    initial = session.lifecycle.to_payload()
    restored = session.lifecycle
    state = restored.state
    assert state is not None
    original_host = state.shooting_phase_state
    assert original_host is not None
    for _ in range(50):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            state = session.lifecycle.state
            assert state is not None
            record = next(
                record
                for record in retained_destructions(state=state)
                if record.request_id == request.request_id
            )
            accepted_models.add(record.model_instance_id)
            option = next(
                option
                for option in request.options
                if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
            )
            session.submit_option(
                request_id=request.request_id,
                result_id=f"accept-{request.request_id}",
                option_id=option.option_id,
            )
        elif request.decision_type == "submit_shooting_declaration":
            target = (
                "army-beta:enemy" if request.actor_id == "player-a" else "army-alpha:intercessor-1"
            )
            proposal = _proposal_from_request(request=request, target_unit_id=target)
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"shoot-{request.request_id}",
                payload=validate_json_value(proposal.to_payload()),
            )
        else:
            submit_fixture_request(session, request)
        checkpoint = session.lifecycle.to_payload()
        started = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "retained_shooting_started"
        ]
        if len(started) == 2:
            assert isinstance(started[0], dict)
            assert isinstance(started[1], dict)
            assert isinstance(started[0]["cause_id"], str)
            assert isinstance(started[1]["cause_id"], str)
            assert (started[1]["cause_id"] < started[0]["cause_id"]) is child_before_parent
            if not checked_child_checkpoint:
                assert pending_request(session).decision_type == "submit_shooting_declaration"
                current = session.lifecycle.state
                assert current is not None
                assert current.shooting_phase_state is not None
                assert (
                    current.shooting_phase_state.active_selection == original_host.active_selection
                )
                _assert_invalid_retained_parent_chains(checkpoint)
                checked_child_checkpoint = True
        restored = GameLifecycle.from_payload(checkpoint)
        assert restored.to_payload() == checkpoint
        session = LocalGameSession(lifecycle=restored)
        for viewer in ("player-a", "player-b"):
            public = json.dumps(
                {
                    "view": session.view(viewer_player_id=viewer),
                    "events": session.events_since(EventStreamCursor(), viewer_player_id=viewer),
                }
            )
            assert "retained_shooting_started" not in public
            assert "suspended_shooting" not in public
            assert "parent_cause_id" not in public
            assert '"cause_id"' not in public
        state = restored.state
        assert state is not None
        assert state.battlefield_state is not None
        if parent_model_id in state.battlefield_state.removed_model_ids:
            break
    assert len(accepted_models) == 2
    assert checked_child_checkpoint
    assert not retained_destructions(state=state)
    starts = [
        event
        for event in restored.decision_controller.event_log.records
        if event.event_type == "retained_shooting_started"
    ]
    assert len(starts) == 2
    assert isinstance(starts[1].payload, dict)
    assert starts[1].payload["suspended_shooting"] is not None
    completions = [
        event.payload
        for event in restored.decision_controller.event_log.records
        if event.event_type == "retained_shooting_resumed_parent"
    ]
    assert isinstance(starts[0].payload, dict)
    assert [cast(dict[str, JsonValue], payload)["cause_id"] for payload in completions] == [
        starts[1].payload["cause_id"],
        starts[0].payload["cause_id"],
    ]
    assert state.out_of_phase_shooting_state is None
    if state.shooting_phase_state is None:
        assert state.current_battle_phase is not BattlePhase.SHOOTING
    else:
        assert state.shooting_phase_state.active_selection == original_host.active_selection
    for model_id in accepted_models:
        assert (
            sum(
                event.event_type == "model_destroyed"
                and isinstance(event.payload, dict)
                and event.payload.get("model_instance_id") == model_id
                for event in restored.decision_controller.event_log.records
            )
            == 1
        )
    artifact = ReplayArtifact.capture(
        artifact_id=f"nested-retained:{game_id}",
        initial_lifecycle_payload=initial,
        final_lifecycle=restored,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def _assert_invalid_retained_parent_chains(checkpoint: object) -> None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.retained_shooting import retained_shooting_executions

    for mutation, message in (
        ("missing_field", "fields drift"),
        ("missing_parent", "missing parent"),
        ("self_parent", "own parent"),
        ("multiple_roots", "multiple children or roots"),
        ("cycle", "cyclic or disconnected"),
    ):
        forged = json.loads(json.dumps(checkpoint))
        executions = [
            effect["effect_payload"]["execution"]
            for effect in forged["state"]["persisting_effects"]
            if effect["effect_payload"].get("effect_kind") == "retained_destruction_shooting"
        ]
        root = next(item for item in executions if item["parent_cause_id"] is None)
        child = next(item for item in executions if item["parent_cause_id"] is not None)
        if mutation == "missing_field":
            del child["parent_cause_id"]
        elif mutation == "missing_parent":
            child["parent_cause_id"] = "absent-parent"
        elif mutation == "self_parent":
            child["parent_cause_id"] = child["cause_id"]
        elif mutation == "multiple_roots":
            child["parent_cause_id"] = None
        else:
            root["parent_cause_id"] = child["cause_id"]
        with pytest.raises(GameLifecycleError, match=message):
            retained_shooting_executions(state=GameState.from_payload(forged["state"]))
        with pytest.raises(GameLifecycleError, match="Retained shooting"):
            GameLifecycle.from_payload(forged)
    forged = json.loads(json.dumps(checkpoint))
    starts = [
        event
        for event in forged["decisions"]["event_log"]
        if event["event_type"] == "retained_shooting_started"
    ]
    starts[1]["payload"]["parent_cause_id"] = None
    with pytest.raises(GameLifecycleError, match="parent differs from chronological history"):
        GameLifecycle.from_payload(forged)


def test_order_30_multiple_hazardous_casualties_keep_each_pending_authority() -> None:
    catalog = for_the_chapter_catalog(hazardous=True)
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(profile, damage_profile=DamageProfile.fixed(1))
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        catalog=catalog,
        game_id="order36-multi-hazard-5",
        alpha_unit_ids=("intercessor-1",),
        alpha_unit_specs=(
            ("intercessor-1", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
        enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 5),
        enemy_pose=Pose.at(30, 35),
    )
    state = lifecycle.state
    assert state is not None
    for model in units["intercessor-1"].own_models:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=units["intercessor-1"].unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=1,
            damage_kind=DamageKind.NORMAL,
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    accepted: set[str] = set()
    pending_casualties_seen = False
    for index in range(70):
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            target = (
                "army-beta:enemy" if request.actor_id == "player-a" else "army-alpha:intercessor-1"
            )
            proposal = _proposal_from_request(request=request, target_unit_id=target)
            outer = cast(dict[str, JsonValue], request.payload)
            request_payload = cast(dict[str, JsonValue], outer["proposal_request"])
            weapons = cast(list[dict[str, JsonValue]], request_payload["available_weapons"])
            proposal = replace(
                proposal,
                declarations=tuple(
                    replace(
                        proposal.declarations[0],
                        attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
                        weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                        wargear_id=cast(str, weapon["wargear_id"]),
                        weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                    )
                    for weapon in weapons
                ),
            )
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="all-hazardous-weapons"
                if not accepted
                else f"hazard-casualty-shot-{index}",
                payload=validate_json_value(proposal.to_payload()),
            )
        elif request.decision_type == "select_destruction_reaction":
            if request.actor_id == "player-a":
                state = session.lifecycle.state
                assert state is not None
                from warhammer40k_core.engine.hazardous_retention_history import (
                    pending_hazardous_logical_deaths,
                )

                pending_casualties = pending_hazardous_logical_deaths(
                    state=state,
                    event_records=session.lifecycle.decision_controller.event_log.records,
                )
                pending_casualties_seen = pending_casualties_seen or bool(pending_casualties)
                record = next(
                    record
                    for record in retained_destructions(state=state)
                    if record.request_id == request.request_id
                )
                accepted.add(record.model_instance_id)
                option_id = next(
                    option.option_id
                    for option in request.options
                    if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
                )
            else:
                option_id = DECLINE_DESTRUCTION_REACTION_OPTION_ID
            session.submit_option(
                request_id=request.request_id,
                result_id=f"hazard-choice-{index}",
                option_id=option_id,
            )
        else:
            submit_fixture_request(session, request)
        checkpoint = session.lifecycle.to_payload()
        restored = GameLifecycle.from_payload(checkpoint)
        assert restored.to_payload() == checkpoint
        session = LocalGameSession(lifecycle=restored)
        state = restored.state
        assert state is not None
        if state.current_battle_phase is not BattlePhase.SHOOTING:
            break
    else:
        raise AssertionError("Multiple Hazardous casualties did not finish their attack host.")
    events = session.lifecycle.decision_controller.event_log.records
    started = next(
        event for event in events if event.event_type == "hazardous_destruction_routing_started"
    )
    payload = cast(dict[str, JsonValue], started.payload)
    application = cast(dict[str, JsonValue], payload["application"])
    damage = cast(list[dict[str, JsonValue]], application["applications"])
    casualties = {
        cast(str, entry["model_instance_id"]) for entry in damage if entry["destroyed"] is True
    }
    assert len(casualties) >= 2
    assert accepted
    assert pending_casualties_seen
    for model_id in casualties:
        assert (
            sum(
                event.event_type == "model_destroyed"
                and isinstance(event.payload, dict)
                and event.payload.get("model_instance_id") == model_id
                for event in events
            )
            == 1
        )


@pytest.mark.parametrize("titanic", [False, True])
def test_r34_001_action_blocks_nested_retained_shooting_before_acceptance(titanic: bool) -> None:
    from tests.phase17n_secondary_mission_helpers import (
        resolved_secondary_mission_selection_for_card,
    )

    from warhammer40k_core.engine.game_state import SecondaryMissionMode
    from warhammer40k_core.engine.mission_decisions import request_mission_action_start
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.scoring import SecondaryMissionCardState

    catalog = for_the_chapter_catalog()
    if titanic:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    keywords=replace(
                        sheet.keywords, keywords=(*sheet.keywords.keywords, "TITANIC")
                    ),
                )
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=catalog,
        game_id="review-r34-nested-5",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_model_count=3,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    state.secondary_mission_choices = [
        replace(choice, mode=SecondaryMissionMode.TACTICAL, fixed_mission_ids=())
        if choice.player_id == "player-a"
        else choice
        for choice in state.secondary_mission_choices
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id="cleanse",
        battle_round=state.battle_round,
        source_result_id="review-r34-hold-cleanse",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )
    actor = units["intercessor-2"]
    marker = min(
        state.mission_setup.objective_markers,
        key=lambda marker: (marker.x_inches - 30) ** 2 + (marker.y_inches - 25) ** 2,
    )
    placement = state.battlefield_state.unit_placement_by_id(actor.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(model, pose=Pose.at(marker.x_inches + 2, marker.y_inches))
                    for model in placement.model_placements
                ),
            )
        )
    )
    for unit_id, x, y in (
        (units["intercessor-1"].unit_instance_id, 75.0, 50.0),
        (units["enemy"].unit_instance_id, 85.0, 50.0),
    ):
        placement = state.battlefield_state.unit_placement_by_id(unit_id)
        state.replace_battlefield_state(
            state.battlefield_state.with_unit_placement(
                replace(
                    placement,
                    model_placements=tuple(
                        replace(model, pose=Pose.at(x, y + index * 1.5))
                        for index, model in enumerate(placement.model_placements)
                    ),
                )
            )
        )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = waiting.decision_request
    assert request is not None, waiting
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("unit_instance_id") == actor.unit_instance_id
    )
    session = LocalGameSession(lifecycle=lifecycle)
    session.submit_option(
        request_id=request.request_id, result_id="review-r34-action", option_id=option.option_id
    )
    pending_request(session)
    initial = session.lifecycle.to_payload()
    saw_child = False
    accepted_parent = False
    for index in range(70):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        assert state.active_player_id == "player-a", [
            (event.event_type, event.payload)
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "fight_on_death_retention_trigger_resolved"
        ]
        if request.decision_type == "select_destruction_reaction":
            shooting = tuple(
                option
                for option in request.options
                if isinstance(option.payload, dict) and option.payload.get("action") == "shoot"
            )
            if request.actor_id == "player-a":
                saw_child = True
                assert bool(shooting) is titanic
                before = session.lifecycle.to_payload()
                assert (
                    GameLifecycle.from_payload(json.loads(json.dumps(before))).to_payload()
                    == before
                )
                if not titanic:
                    # An adapter cannot invent the source's unavailable shooting alternative.
                    source = next(
                        record
                        for record in retained_destructions(state=state)
                        if record.request_id == request.request_id
                    ).eligible_sources[0]
                    with pytest.raises(DecisionError, match="finite action space"):
                        session.submit_option(
                            request_id=request.request_id,
                            result_id="review-r34-forged-shoot",
                            option_id=source.source_id,
                        )
                    assert session.lifecycle.to_payload() == before
                option_id = (
                    shooting[0].option_id if titanic else DECLINE_DESTRUCTION_REACTION_OPTION_ID
                )
            elif not accepted_parent:
                accepted_parent = True
                assert shooting
                option_id = shooting[0].option_id
            else:
                option_id = DECLINE_DESTRUCTION_REACTION_OPTION_ID
            session.submit_option(
                request_id=request.request_id,
                result_id=f"review-r34-retain-{index}",
                option_id=option_id,
            )
        elif request.decision_type == "submit_shooting_declaration":
            target = actor.unit_instance_id if request.actor_id == "player-b" else "army-beta:enemy"
            proposal = _proposal_from_request(request=request, target_unit_id=target)
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"review-r34-shoot-{index}",
                payload=validate_json_value(proposal.to_payload()),
            )
        else:
            submit_fixture_request(session, request)
        checkpoint = session.lifecycle.to_payload()
        assert (
            GameLifecycle.from_payload(json.loads(json.dumps(checkpoint))).to_payload()
            == checkpoint
        )
        state = session.lifecycle.state
        assert state is not None
        if saw_child and not retained_destructions(state=state):
            break
    assert saw_child
    assert accepted_parent
    assert state.out_of_phase_shooting_state is None
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id=f"r34-001:{titanic}",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("choice", ["shoot", "fight", "decline"])
def test_r34_001_retained_selection_rechecks_action_before_mutation(choice: str) -> None:
    from warhammer40k_core.engine.actions import MissionActionState

    session, model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH,
    )
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    # A stale request must be checked against current engine-owned effects even
    # when it originally included shooting. The Action's later failure cannot
    # make that alternative legal again.
    unit_id = state.unit_instance_id_for_model(model_id)
    action = MissionActionState.start(
        action_id="r34-stale-action",
        mission_action_id="cleanse-objective",
        player_id="player-b",
        unit_instance_id=unit_id,
        target_id="phase13b-remote-objective",
        condition_target_id="phase13b-remote-objective",
        mission_id="cleanse",
        battle_round=state.battle_round,
        phase="shooting",
        start_timing="shooting_phase_action_start",
        completion_timing="turn_end",
        eligible_unit_instance_ids=(unit_id,),
        interruption_conditions=("unit_destroyed",),
        scoring_source_id="cleanse",
        victory_points=0,
        battle_shocked_unit_ids=(),
    )
    state.record_mission_action_state(action)
    state.interrupt_mission_action(action_id=action.action_id, reason="unit_destroyed")
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("action") == (None if choice == "decline" else choice)
    )
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="r34-stale-retention", option_id=option.option_id
    )
    if choice == "shoot":
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID
        selected = [
            event
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "fight_on_death_retention_selected"
        ]
        assert selected


def test_r34_001_retained_action_exclusions_are_strict_and_cannot_be_selected() -> None:
    session, _model = pending_retained_attack(reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH)
    state = session.lifecycle.state
    assert state is not None
    record = retained_destructions(state=state)[0]
    with pytest.raises(GameLifecycleError, match="excluded actions are invalid"):
        replace(record, excluded_actions=cast(tuple[RetainedAttackAction, ...], ("shoot",)))
    with pytest.raises(GameLifecycleError, match="action was excluded"):
        replace(
            record,
            excluded_actions=(RetainedAttackAction.SHOOT,),
            selected_action=RetainedAttackAction.SHOOT,
        )
    for value in (None, "shoot", ["fight"], ["shoot", "shoot"]):
        payload = record.to_payload()
        payload["excluded_actions"] = validate_json_value(value)
        with pytest.raises(GameLifecycleError, match="excluded actions are invalid"):
            type(record).from_payload(payload)
    payload = record.to_payload()
    del payload["excluded_actions"]
    with pytest.raises(GameLifecycleError, match="fields"):
        type(record).from_payload(payload)
