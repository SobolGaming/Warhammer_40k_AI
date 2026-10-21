"""Selected Aeldari consumers through normal bundle loading and native choices."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from tests.support.faction_batch01 import (
    AVENGERS,
    ELDRAD,
    LORD,
    RANGERS,
    Scene,
    anchor,
    casualty_checkpoint,
    events,
    locate,
    request,
    scene,
    selection,
    submit_translation,
    translate,
)
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    finish_attacks,
    shooting_payload,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import MovementPhaseState
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    SaveOptionModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind
from warhammer40k_core.geometry.pose import Pose


def _battle_focus_spends(s: Scene) -> list[dict[str, Any]]:
    return [
        cast(dict[str, Any], effect.effect_payload)
        for effect in s.state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == "aeldari_battle_focus_token_spent"
    ]


def _pending(s: Scene) -> DecisionRequest:
    pending = s.session.lifecycle.pending_decision_request()
    assert pending is not None
    return pending


def _choice(s: Scene, option: str) -> LifecycleStatus:
    r = _pending(s)
    return s.session.submit_option(
        request_id=r.request_id, option_id=option, result_id=f"{r.request_id}:aeldari"
    )


def _fall_back(s: Scene, unit_id: str) -> LifecycleStatus:
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    _choice(s, unit_id)
    r = request(_choice(s, "fall_back:ordered_retreat"), "submit_movement_proposal")
    context = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert context.movement_phase_action is not None
    assert s.state.battlefield_state is not None
    placements = s.state.battlefield_state.unit_placement_by_id(unit_id).model_placements
    witness = PathWitness.for_paths(
        tuple(
            (p.model_instance_id, (p.pose, Pose.at(p.pose.position.x + 4, p.pose.position.y)))
            for p in placements
        )
    )
    payload = MovementProposalPayload(
        r.request_id,
        context.proposal_kind,
        unit_id,
        context.movement_phase_action,
        witness,
        movement_mode="fall_back",
        fall_back_mode="ordered_retreat",
    )
    return s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=validate_json_value(payload.to_payload()),
        result_id=f"{r.request_id}:retreat",
    )


def _assert_normal_reaction(s: Scene, r: DecisionRequest, maneuver: str) -> float:
    assert r.actor_id == "owner"
    assert isinstance(r.payload, dict)
    descriptor = cast(dict[str, Any], r.payload["descriptor"])
    assert descriptor["movement_kind"] == "triggered"
    assert descriptor["movement_mode"] == "normal"
    assert {o.option_id for o in r.options} == {
        "decline_triggered_movement",
        "triggered:own:reactor",
    }
    eligible = cast(list[dict[str, Any]], r.payload["eligible_units"])
    assert len(eligible) == 1
    assert eligible[0]["hook_id"] == f"warhammer_40000_11th:aeldari:army_rule:{maneuver}"
    assert eligible[0]["unit_instance_id"] == "own:reactor"
    assert eligible[0]["decision_effect_payload"]["maneuver"] == maneuver
    assert eligible[0]["decision_effect_payload"]["battle_focus_token_cost"] == 1
    kind = (
        "movement_end_surge_triggered"
        if maneuver == "opportunity_seized"
        else "shooting_end_surge_triggered"
    )
    trigger = events(s.session, kind)[-1]
    assert trigger["max_distance_bonus_inches"] == 1
    roll = cast(dict[str, Any], trigger["surge_distance_roll"])
    assert descriptor["max_distance_inches"] == roll["current_total"] + 1
    return cast(float, descriptor["max_distance_inches"])


def _accept_normal_reaction(s: Scene, *, recover: bool = False) -> None:
    prior_count = len(_battle_focus_spends(s))
    r = request(_choice(s, "triggered:own:reactor"), "submit_movement_proposal")
    restored: LocalGameSession | None = None
    if recover:
        saved = json.loads(json.dumps(s.session.to_persistence_payload()))
        restored = LocalGameSession.from_persistence_payload(saved)
        assert restored.to_persistence_payload() == saved
    assert s.state.battlefield_state is not None
    before = s.state.battlefield_state.unit_placement_by_id("own:reactor")
    spends = list(_battle_focus_spends(s))
    # A well-formed over-distance path cannot move a model or spend a second token.
    invalid = submit_translation(s, r, "own:reactor", -8)
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.battlefield_state.unit_placement_by_id("own:reactor") == before
    assert _battle_focus_spends(s) == spends
    r = _pending(s)
    # Moving away, and less than the rolled allowance, is a legal Normal move.
    status = submit_translation(s, r, "own:reactor", -0.5)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    after = s.state.battlefield_state.unit_placement_by_id("own:reactor")
    assert [p.pose.position.x for p in after.model_placements] == [
        p.pose.position.x - 0.5 for p in before.model_placements
    ]
    resolved = events(s.session, "triggered_movement_resolved")
    assert len(resolved) == 1
    assert resolved[0]["triggered_movement_kind"] == "triggered"
    assert len(_battle_focus_spends(s)) == prior_count + 1
    assert _battle_focus_spends(s)[-1]["battle_focus_token_cost"] == 1
    if recover:
        assert restored is not None
        assert restored.lifecycle.state is not None
        branch = Scene(restored, restored.lifecycle.state, {})
        pending = restored.lifecycle.pending_decision_request()
        assert pending is not None
        invalid = submit_translation(branch, pending, "own:reactor", -8)
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        pending = restored.lifecycle.pending_decision_request()
        assert pending is not None
        submit_translation(branch, pending, "own:reactor", -0.5)
        assert restored.lifecycle.to_payload() == s.session.lifecycle.to_payload()
        assert (
            ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="aeldari-normal"))
            .run()
            .reproduced_exactly
        )


__all__ = [
    "AVENGERS",
    "ELDRAD",
    "LORD",
    "RANGERS",
    "Any",
    "ArmyMusteringError",
    "AttachmentDeclaration",
    "BattlePhase",
    "BattlePhaseKind",
    "DecisionRequest",
    "DecisionResult",
    "EffectExpirationBoundary",
    "LifecycleStatus",
    "LifecycleStatusKind",
    "LocalGameSession",
    "MovementPhaseState",
    "Pose",
    "ReplayRunner",
    "ReserveKind",
    "ReserveState",
    "SaveKind",
    "SaveOptionModifierContext",
    "Scene",
    "Section02Definitions",
    "WoundRollModifierContext",
    "_accept_normal_reaction",
    "_assert_normal_reaction",
    "_battle_focus_spends",
    "_choice",
    "_fall_back",
    "_pending",
    "anchor",
    "attack_modifier_snapshots",
    "cast",
    "casualty_checkpoint",
    "events",
    "finish_attacks",
    "json",
    "locate",
    "muster_army",
    "pytest",
    "replace",
    "request",
    "rules_unit_has_infiltrators",
    "rules_unit_view_by_id",
    "scene",
    "selection",
    "shooting_payload",
    "shooting_request",
    "submit_translation",
    "translate",
    "weapon_rows",
]
