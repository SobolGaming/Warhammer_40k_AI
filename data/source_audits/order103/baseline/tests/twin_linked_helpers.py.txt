"""Canonical facade drivers for optional wound rerolls."""

from __future__ import annotations

from tests.lethal_hits_helpers import attack_completed
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload


def submit_next(
    session: LocalGameSession, request: DecisionRequest, *, reroll: bool = False
) -> None:
    if request.decision_type == "select_dice_reroll":
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            option_id="reroll:0" if reroll else "decline",
        )
    elif request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            payload=stratagem_decline_payload(),
        )
    elif request.decision_type == "use_stratagem":
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:fixture-choice",
            option_id="decline_stratagem_window",
        )
    else:
        submit_fixture_request(session, request)
        return
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def reach_wound_reroll(session: LocalGameSession) -> DecisionRequest:
    for _ in range(100):
        request = pending_request(session)
        if request.decision_type == "select_dice_reroll":
            assert isinstance(request.payload, dict)
            assert request.payload["roll_type"] == "attack_sequence.wound"
            return request
        assert not attack_completed(session), "No optional wound reroll was offered."
        submit_next(session, request)
    raise AssertionError("No optional wound reroll was reached.")


def complete_optional_attack(session: LocalGameSession, *, reroll: bool = False) -> None:
    for _ in range(150):
        if attack_completed(session):
            return
        submit_next(session, pending_request(session), reroll=reroll)
    raise AssertionError("Attack did not complete.")


def sustained_twin_session(phase: BattlePhase) -> LocalGameSession:
    from dataclasses import replace

    from tests.psychic_modifier_helpers import psychic_session
    from warhammer40k_core.core.weapon_profiles import (
        AbilityDescriptor,
        AttackProfile,
        WeaponKeyword,
    )

    return psychic_session(
        phase,
        psychic=False,
        weapon_profile_transform=lambda profile: replace(
            profile,
            attack_profile=AttackProfile.fixed(12),
            keywords=(WeaponKeyword.TWIN_LINKED, WeaponKeyword.SUSTAINED_HITS),
            abilities=(AbilityDescriptor.sustained_hits("D3"),),
        ),
    )


def interrupt_twin_session() -> LocalGameSession:
    from dataclasses import replace

    from tests.dice_result_semantics_helpers import open_phase
    from tests.phase13b_shooting_declaration_helpers import (
        _canonical_catalog,
        _compact_intercessor_catalog,
    )
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
    from warhammer40k_core.geometry.pose import Pose

    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        keywords=(WeaponKeyword.TORRENT, WeaponKeyword.TWIN_LINKED),
                        abilities=(),
                        attack_profile=AttackProfile.fixed(2),
                        damage_profile=DamageProfile.fixed(1),
                    )
                    for profile in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("parent",),
        enemy_unit_ids=("enemy",),
        origins={"parent": Pose.at(10, 20), "enemy": Pose.at(12, 20)},
        game_id="review-twin-interrupt",
        fight_interrupt_unit_keys=("enemy",),
        catalog=catalog,
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        record_deployment=True,
    )
    open_phase(lifecycle)
    return LocalGameSession(lifecycle)


def retained_twin_session(*, shooting: bool) -> tuple[LocalGameSession, str]:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import _compact_shooting_lifecycle
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.retained_attack_helpers import lethal_retained_attack_catalog
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.geometry.pose import Pose

    catalog = lethal_retained_attack_catalog()
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(profile, keywords=(*profile.keywords, WeaponKeyword.TWIN_LINKED))
                    for profile in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    if shooting:
        lifecycle, units = _compact_shooting_lifecycle(
            catalog=catalog,
            game_id="order-30-presence",
            alpha_unit_ids=("intercessor-1", "intercessor-2"),
            enemy_model_count=3,
        )
    else:
        lifecycle, units = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="order96-retained-fight",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
            record_deployment=True,
        )
    state = lifecycle.state
    assert state is not None
    model_id = units["enemy"].own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="order96-retained",
                source_rule_id="order96-retained",
                reaction_kind=(
                    DestructionReactionKind.SHOOT_ON_DEATH
                    if shooting
                    else DestructionReactionKind.FIGHT_ON_DEATH
                ),
            ),
        ),
    )
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload())), model_id


def start_twin_overwatch(session: LocalGameSession, *, reaction: bool = False) -> None:
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.stratagem_catalog import (
        eleventh_edition_stratagem_catalog_records,
    )
    from warhammer40k_core.engine.stratagems import (
        StratagemEligibilityContext,
        StratagemTargetBinding,
        StratagemTargetKind,
        StratagemTargetProposal,
        request_stratagem_target_proposal,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    state = session.lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="order96:overwatch-cp",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    record = next(
        row
        for row in eleventh_edition_stratagem_catalog_records()
        if row.definition.stratagem_id == "fire-overwatch"
    )
    proposal = StratagemTargetProposal.for_request(
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=record,
    )
    if reaction:
        from warhammer40k_core.engine.decision_request import parameterized_decision_option
        from warhammer40k_core.engine.stratagems_requests import (
            stratagem_target_proposal_request_payload,
        )
        from warhammer40k_core.engine.timing_windows import (
            ReactionWindow,
            TimingWindow,
            TimingWindowDescriptor,
        )

        window = TimingWindow(
            window_id="order96:phase-end-overwatch",
            descriptor=TimingWindowDescriptor(
                descriptor_id="order96:phase-end-overwatch",
                trigger_kind=TimingTriggerKind.END_PHASE,
                source_rule_id=record.definition.source_id,
                phase=BattlePhase.MOVEMENT,
            ),
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=BattlePhase.MOVEMENT,
            trigger_event_id="order96:phase-end",
        )
        triggered = session.lifecycle.reaction_queue.emit_decision_request(
            state=state,
            decisions=session.lifecycle.decision_controller,
            reaction_window=ReactionWindow(timing_window=window, eligible_player_ids=("player-a",)),
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="phase-end",
            resume_token="order96:overwatch-parent",
            actor_id="player-a",
            decision_type="submit_stratagem_target_proposal",
            options=(parameterized_decision_option(),),
            payload_factory=lambda request_id, decision_type, actor_id: (
                stratagem_target_proposal_request_payload(
                    proposal,
                    request_id=request_id,
                    decision_type=decision_type,
                    actor_id=actor_id,
                )
            ),
        )
        request = triggered.decision_request
    else:
        status = request_stratagem_target_proposal(
            state=state,
            decisions=session.lifecycle.decision_controller,
            proposal_request=proposal,
        )
        pending = status.decision_request
        assert pending is not None
        request = pending
    assert pending_request(session) == request
    proposal = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-1",
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order96:overwatch",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
