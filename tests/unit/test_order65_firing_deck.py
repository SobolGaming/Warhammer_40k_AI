"""All cargo receives one authenticated shooting restriction through turn end."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest
from tests.firing_deck_helpers import PASSENGERS, TRANSPORT, firing_deck_session, submit_firing_deck

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_eligibility_state import shooting_state_restriction_reason


@pytest.mark.parametrize("contribute", [False, True])
def test_all_cargo_is_restricted_even_with_zero_contributors(contribute: bool) -> None:
    session, request, proposal = firing_deck_session(contribute=contribute)
    for player in ("player-a", "player-b"):
        pending = session.view(viewer_player_id=player)["pending_decision"]
        assert pending is not None
        payload = pending["payload"]
        assert isinstance(payload, dict)
        advertised = payload["proposal_request"]
        assert isinstance(advertised, dict)
        assert advertised["firing_deck_embarked_unit_instance_ids"] == list(PASSENGERS)
    status = submit_firing_deck(session, request, proposal)
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    effect = next(e for e in state.persisting_effects if firing_deck_restriction_payload(e))
    assert effect.target_unit_instance_ids == PASSENGERS
    assert state.shooting_phase_state is not None
    assert not set(PASSENGERS).intersection(state.shooting_phase_state.shot_unit_ids)
    assert TRANSPORT in state.shooting_phase_state.shot_unit_ids
    restored = GameLifecycle.from_payload(copy.deepcopy(session.lifecycle.to_payload()))
    assert restored.to_payload() == session.lifecycle.to_payload()
    persisted = session.to_persistence_payload()
    clone = LocalGameSession.from_persistence_payload(persisted)
    assert clone.to_persistence_payload() == persisted
    for player in state.player_ids:
        assert clone.view(viewer_player_id=player) == session.view(viewer_player_id=player)
        events = session.events_since(EventStreamCursor(), viewer_player_id=player)
        assert clone.events_since(EventStreamCursor(), viewer_player_id=player) == events
        accepted = next(
            e for e in events["events"] if e["event_type"] == "shooting_declaration_accepted"
        )
        accepted_payload = accepted["payload"]
        assert isinstance(accepted_payload, dict)
        assert accepted_payload["ineligible_unit_instance_ids"] == list(PASSENGERS)
    encoded = json.dumps(persisted, sort_keys=True)
    assert "object at 0x" not in encoded


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.CHARGE, BattlePhase.FIGHT])
def test_restriction_survives_phase_and_cargo_changes_and_expires_at_turn_end(
    phase: BattlePhase,
) -> None:
    session, request, proposal = firing_deck_session()
    submit_firing_deck(session, request, proposal)
    state = session.lifecycle.state
    assert state is not None
    # The query uses the accepted snapshot, never current cargo membership or phase-local shot IDs.
    state.transport_cargo_states.clear()
    state.shooting_phase_state = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    for unit_id in PASSENGERS:
        assert (
            shooting_state_restriction_reason(
                state=state,
                rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
                player_id="player-a",
            )
            == "firing_deck"
        )
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(
            battle_round=state.battle_round,
            player_id="player-b",
        )
    )
    assert any(firing_deck_restriction_payload(e) for e in state.persisting_effects)
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(
            battle_round=state.battle_round,
            player_id="player-a",
        )
    )
    assert not any(firing_deck_restriction_payload(e) for e in state.persisting_effects)
    for unit_id in PASSENGERS:
        assert (
            shooting_state_restriction_reason(
                state=state,
                rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
                player_id="player-a",
            )
            is None
        )


def test_noncontributor_cargo_drift_rejects_before_queue_pop_or_mutation() -> None:
    session, request, proposal = firing_deck_session()
    state = session.lifecycle.state
    assert state is not None
    state.transport_cargo_states[0] = replace(
        state.transport_cargo_states[0],
        embarked_unit_instance_ids=(PASSENGERS[0],),
    )
    before = copy.deepcopy(session.lifecycle.to_payload())
    status = submit_firing_deck(session, request, proposal)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert "firing_deck_cargo_drift" in json.dumps(status.payload)
    assert session.lifecycle.to_payload() == before


def test_restore_rejects_pending_noncontributor_snapshot_drift() -> None:
    session, _request, _proposal = firing_deck_session()
    state = session.lifecycle.state
    assert state is not None
    state.transport_cargo_states[0] = replace(
        state.transport_cargo_states[0],
        embarked_unit_instance_ids=(PASSENGERS[0],),
    )
    with pytest.raises(GameLifecycleError, match="pending cargo snapshot drifted"):
        GameLifecycle.from_payload(session.lifecycle.to_payload())


@pytest.mark.parametrize("drift", ["omit", "target", "duration", "source", "snapshot"])
def test_restore_rejects_restriction_drift(drift: str) -> None:
    session, request, proposal = firing_deck_session()
    submit_firing_deck(session, request, proposal)
    payload = copy.deepcopy(session.lifecycle.to_payload())
    assert payload["state"] is not None
    effects = payload["state"]["persisting_effects"]
    effect = next(row for row in effects if row["effect_id"] == "firing-deck:order65-declaration")
    if drift == "omit":
        effects.remove(effect)
    elif drift == "target":
        effect["target_unit_instance_ids"] = [PASSENGERS[0]]
    elif drift == "duration":
        effect["expiration"]["player_id"] = "player-b"
    elif drift == "source":
        effect["source_rule_id"] = "forged"
    else:
        assert isinstance(effect["effect_payload"], dict)
        effect["effect_payload"]["embarked_unit_instance_ids"] = [PASSENGERS[0]]
    with pytest.raises(GameLifecycleError, match="Firing Deck"):
        GameLifecycle.from_payload(payload)


def test_attached_cargo_restricts_canonical_unit_and_both_components() -> None:
    session, request, proposal = firing_deck_session(attached=True)
    submit_firing_deck(session, request, proposal)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=PASSENGERS[0])
    assert view.attached_unit is not None
    for unit_id in (view.unit_instance_id, *PASSENGERS):
        assert (
            shooting_state_restriction_reason(
                state=state,
                rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
                player_id="player-a",
            )
            == "firing_deck"
        )
    assert session.fork().lifecycle.state == state


def test_resolver_snapshots_noncontributors_and_zero_selected_weapons() -> None:
    from warhammer40k_core.engine.transports import (
        FiringDeckResolution,
        resolve_firing_deck_selection,
    )

    session, _request, proposal = firing_deck_session()
    state = session.lifecycle.state
    assert state is not None
    cargo = state.transport_cargo_state_for_transport(TRANSPORT)
    assert cargo is not None
    selection = proposal.firing_deck_selection
    assert selection is not None
    for selected in (selection, replace(selection, weapon_selections=())):
        result = resolve_firing_deck_selection(
            cargo_state=cargo,
            selection=selected,
            embarked_units=tuple(
                rules_unit_view_by_id(state=state, unit_instance_id=uid).components[0].unit
                for uid in PASSENGERS
            ),
        )
        assert result.is_valid
        assert result.ineligible_unit_instance_ids == PASSENGERS
        assert FiringDeckResolution.from_payload(result.to_payload()) == result
        forged = result.to_payload()
        forged["ineligible_unit_instance_ids"] = [PASSENGERS[0]]
        with pytest.raises(GameLifecycleError, match="ineligible unit drift"):
            FiringDeckResolution.from_payload(forged)


def test_source_row_is_hash_pinned_and_authorized() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_firing_deck_2026_09 as source,
    )

    assert (
        source.source_package().source_catalog.package_id.package_name == source.SOURCE_PACKAGE_ID
    )
    (rule,) = source.source_rules()
    assert rule.section_id == "24.14"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "Until the end of the turn" in rule.source_text
    with pytest.raises(source.FiringDeckSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(b"{}")


def test_out_of_phase_entry_rejects_restricted_noncontributor_before_mutation() -> None:
    from warhammer40k_core.engine.phases.shooting_requests import (
        request_out_of_phase_shooting_declaration,
    )

    session, request, proposal = firing_deck_session()
    submit_firing_deck(session, request, proposal)
    state = session.lifecycle.state
    assert state is not None
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="firing_deck"):
        request_out_of_phase_shooting_declaration(
            state=state,
            decisions=session.lifecycle.decision_controller,
            ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
            army_catalog=session.lifecycle.config.army_catalog,
            player_id="player-a",
            unit_instance_id=PASSENGERS[1],
            parent_phase=BattlePhase.SHOOTING,
            source_rule_id="core:fire-overwatch",
            source_decision_request_id=request.request_id,
            source_decision_result_id="order65-declaration",
            source_context={},
        )
    assert state.to_payload() == before


def test_engine_turn_boundary_expires_restriction_and_restores_exactly() -> None:
    session, request, proposal = firing_deck_session()
    status = submit_firing_deck(session, request, proposal)
    for index in range(32):
        state = session.lifecycle.state
        assert state is not None
        if state.active_player_id == "player-b":
            break
        assert any(firing_deck_restriction_payload(e) for e in state.persisting_effects)
        pending = status.decision_request
        assert pending is not None
        request = pending
        assert request.decision_type in {
            "select_attack_weapon_group",
            "select_damage_allocation_model",
        }
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"order65-drain-{index}",
        )
    else:
        pytest.fail("Firing Deck fixture did not complete the owner's turn.")
    assert not any(firing_deck_restriction_payload(e) for e in state.persisting_effects)
    assert session.fork().lifecycle.state == state
    persisted = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(persisted).to_persistence_payload() == persisted
    )
