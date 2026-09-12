"""Order 40: one source-aware Cover consequence through shared attack authority."""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.smokescreen_helpers import smoke_grant, smoke_scene

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def test_order40_source_uses_start_phase_and_generic_execution() -> None:
    record = next(
        row
        for row in eleventh_edition_core_stratagem_catalog_records()
        if row.definition.stratagem_id == "smokescreen"
    )
    assert record.definition.timing.trigger_kind is TimingTriggerKind.START_PHASE
    assert record.definition.target_spec.target_policy_id == "friendly_smoke_unit"
    assert record.definition.handler_id == "generic:rule-ir"


@pytest.mark.parametrize(
    ("smoke_y", "direct", "ignore", "expected"),
    [(10, False, False, 1), (20, False, False, 0), (20, True, False, 1), (10, False, True, 0)],
)
def test_order40_cover_is_attack_specific_and_never_a_hit_modifier(
    smoke_y: float, direct: bool, ignore: bool, expected: int
) -> None:
    lifecycle, units, pool = smoke_scene(smoke_y=smoke_y)
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(smoke_grant(units["smoke"].unit_instance_id))
    if direct:
        pool = replace(pool, target_unit_instance_id=units["smoke"].unit_instance_id)
    if ignore:
        pool = replace(
            pool,
            weapon_profile=replace(pool.weapon_profile, keywords=(WeaponKeyword.IGNORES_COVER,)),
        )
    snapshots = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=BattlePhase.SHOOTING,
        runtime_modifier_registry=RuntimeModifierRegistry(),
    )
    assert sum(item.modifier.operand for item in snapshots if item.kind == "skill") == expected
    assert not [item for item in snapshots if item.kind == "hit_roll"]


def test_order40_source_artifact_is_eagerly_validated_and_reproducible() -> None:
    import importlib
    import json
    from pathlib import Path

    from tools.build_core_smokescreen_source import build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_smokescreen_2026_09 as source,
    )

    raw = Path(source.__file__).with_name("artifacts").joinpath("package.json").read_bytes()
    payload, audit = build_payloads()
    assert json.loads(raw) == payload
    assert (
        json.loads(
            Path(
                "data/source_audits/maintained_app_mirrors/smokescreen_2026_09_12.audit.json"
            ).read_bytes()
        )
        == audit
    )
    assert (
        source.validate_source_artifact_bytes(raw).execution_payload == source.execution_payload()
    )
    assert source.source_package().evidence_required_source_ids == (source.SMOKESCREEN_SOURCE_ID,)
    for consumer in source.source_rules()[0].runtime_consumer_ids:
        module, name = consumer.split(":")
        assert callable(vars(importlib.import_module(module))[name])
    with pytest.raises(source.SmokescreenSourceError, match="source bytes drifted"):
        source.validate_source_artifact_bytes(raw + b"\n")


@pytest.mark.integration
@pytest.mark.parametrize("decline", [False, True])
def test_order40_facade_phase_start_restores_replays_and_expires(decline: bool) -> None:
    from tests.smokescreen_helpers import smoke_session

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, _, pool = smoke_session()
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "use_stratagem"
    assert request.actor_id == "player-b"
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is None
    pending = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(pending)
    assert session.to_persistence_payload() == pending
    for viewer in ("player-a", "player-b"):
        view = canonical_json(session.view(viewer_player_id=viewer))
        assert "Smokescreen" in view
        assert "object at 0x" not in view
    option = (
        "decline_stratagem_window"
        if decline
        else "use-stratagem:smokescreen:target:army-beta:smoke"
    )
    status = session.submit_option(
        request_id=request.request_id, result_id="order40:use", option_id=option
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-b") == (2 if decline else 1)
    assert len(state.stratagem_use_records) == (0 if decline else 1)
    snapshots = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=BattlePhase.SHOOTING,
        runtime_modifier_registry=RuntimeModifierRegistry(),
    )
    assert sum(s.modifier.operand for s in snapshots if s.kind == "skill") == (0 if decline else 1)
    assert not [s for s in snapshots if s.kind == "hit_roll"]
    if not decline:
        (effect,) = state.persisting_effects
        assert effect.expiration.player_id == "player-a"
        assert effect.source_rule_id == "gw-11e-core-stratagems:core:smokescreen"
    persisted = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(persisted)
    assert session.to_persistence_payload() == persisted
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order40:activation"))
    assert replay.run().status is ReplayRunStatus.REPRODUCED
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    session.submit_option(
        request_id=request.request_id,
        result_id="order40:expire",
        option_id="complete_shooting_phase",
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.CHARGE
    assert not state.persisting_effects
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order40:expiry"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.integration
@pytest.mark.parametrize("drift", ["keyword", "cost"])
def test_order40_pending_target_or_cost_drift_is_rejected_without_mutation(drift: str) -> None:
    from tests.core_stratagem_helpers import _replace_unit_keywords
    from tests.smokescreen_helpers import smoke_session

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, _, _ = smoke_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    state = session.lifecycle.state
    assert state is not None
    if drift == "keyword":
        _replace_unit_keywords(state, unit_instance_id="army-beta:smoke", keywords=("INFANTRY",))
    else:
        state.spend_command_points(player_id="player-b", amount=2, source_id="order40:cost-drift")
    before = state.to_payload()
    count = len(session.lifecycle.decision_controller.records)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order40:invalid",
        option_id="use-stratagem:smokescreen:target:army-beta:smoke",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert len(session.lifecycle.decision_controller.records) == count
    assert session.lifecycle.decision_controller.queue.pending_requests[0] == request


@pytest.mark.parametrize(
    "change", ["move_source", "move_observer", "remove_source", "expire", "replace_source"]
)
def test_order40_query_rechecks_geometry_lifetime_and_source_identity(change: str) -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses

    from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_sources
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units, pool = smoke_scene()
    state = lifecycle.state
    assert state is not None
    effect = smoke_grant(units["smoke"].unit_instance_id)
    state.record_persisting_effect(effect)
    first = obscuring_model_cover_sources(state=state, pool=pool)
    assert first is not None
    if change in {"move_source", "move_observer"}:
        key = "smoke" if change == "move_source" else "attacker"
        _replace_unit_poses(
            state, unit_instance_id=units[key].unit_instance_id, poses=(Pose.at(20, 20),)
        )
    elif change == "remove_source":
        assert state.battlefield_state is not None
        state.battlefield_state = state.battlefield_state.with_removed_models(
            (units["smoke"].own_models[0].model_instance_id,)
        )
    elif change == "expire":
        state.persisting_effects.clear()
    else:
        state.persisting_effects[:] = [replace(effect, effect_id="replacement-source")]
    second = obscuring_model_cover_sources(state=state, pool=pool)
    assert second != first
    assert (second is not None) == (change == "replace_source")


@pytest.mark.parametrize("other_cover", ["terrain", "indirect", "denial", "melee"])
def test_order40_cover_consequences_share_nonstacking_and_denial(other_cover: str) -> None:
    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.core.weapon_profiles import RangeProfile
    from warhammer40k_core.engine.shooting_targets import BENEFIT_OF_COVER_RULE_ID
    from warhammer40k_core.engine.weapon_abilities import INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID

    lifecycle, units, pool = smoke_scene()
    state = lifecycle.state
    assert state is not None
    effect = smoke_grant(units["smoke"].unit_instance_id)
    state.record_persisting_effect(effect)
    if other_cover in {"terrain", "indirect"}:
        pool = replace(
            pool,
            targeting_rule_ids=(
                BENEFIT_OF_COVER_RULE_ID
                if other_cover == "terrain"
                else INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
            ),
        )
    elif other_cover == "denial":
        state.record_persisting_effect(
            replace(
                effect,
                effect_id="cover-denial",
                target_unit_instance_ids=(units["target"].unit_instance_id,),
                effect_payload={
                    "effect_kind": "generic_stratagem_benefit_of_cover_denial",
                    "benefit_of_cover_denied": True,
                },
            )
        )
    else:
        pool = replace(
            pool,
            weapon_profile=replace(
                pool.weapon_profile,
                range_profile=RangeProfile.melee(),
                skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
            ),
        )
    snapshots = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=BattlePhase.SHOOTING,
        runtime_modifier_registry=RuntimeModifierRegistry(),
    )
    assert sum(s.modifier.operand for s in snapshots if s.kind == "skill") == int(
        other_cover in {"terrain", "indirect"}
    )
    assert not [s for s in snapshots if s.kind == "hit_roll"]


def test_order40_attached_source_uses_leader_blocker_and_retained_presence() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
    from tests.phase13b_shooting_declaration_helpers import (
        _attack_pool_for_test,
        _canonical_catalog,
        _compact_intercessor_catalog,
        _first_weapon_profile,
        _shooting_lifecycle,
    )

    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_sources
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("attacker",),
        alpha_unit_specs=(
            ("attacker", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_unit_specs=(
            ("smoke", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            ("leader", "core-character-leader", "core-character-leader", 1),
            ("target", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="smoke"
            ),
        ),
        catalog=_compact_intercessor_catalog(_canonical_catalog()),
    )
    state = lifecycle.state
    assert state is not None
    for key, x, y in (
        ("attacker", 10, 10),
        ("smoke", 20, 13),
        ("leader", 20, 10),
        ("target", 30, 10),
    ):
        _replace_unit_poses(
            state, unit_instance_id=units[key].unit_instance_id, poses=(Pose.at(x, y),)
        )
    source = rules_unit_view_by_id(state=state, unit_instance_id=units["smoke"].unit_instance_id)
    state.record_persisting_effect(smoke_grant(source.unit_instance_id))
    pool = _attack_pool_for_test(
        attacker=units["attacker"],
        defender=units["target"],
        weapon_profile=_first_weapon_profile(lifecycle, units["attacker"]),
        attacks=1,
    )
    assert obscuring_model_cover_sources(state=state, pool=pool) is not None
    leader_id = units["leader"].own_models[0].model_instance_id
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.model_placement_by_id(leader_id)
    state.army_definitions[:] = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
                if unit.unit_instance_id == units["leader"].unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    state.battlefield_state = battlefield.with_removed_models((leader_id,))
    retain_destroyed_model_for_fixture(
        state=state,
        placement=placement,
        effect_id="order40:retained",
        source_rule_id="order40:retained-source",
        source_phase=BattlePhase.SHOOTING,
        decisions=lifecycle.decision_controller,
    )
    assert obscuring_model_cover_sources(state=state, pool=pool) is not None


@pytest.mark.integration
def test_order40_facade_attack_consumes_cover_without_hit_penalty() -> None:
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
    from tests.smokescreen_helpers import smoke_session

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, _, _ = smoke_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    session.submit_option(
        request_id=request.request_id,
        result_id="order40:attack-smoke",
        option_id="use-stratagem:smokescreen:target:army-beta:smoke",
    )
    hits: list[JsonValue] = []
    for _ in range(25):
        hits = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "hit"
        ]
        if hits:
            break
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(request=request, target_unit_id="army-beta:target")
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:shoot",
                payload=validate_json_value(proposal.to_payload()),
            )
        else:
            option = next(
                (
                    o
                    for o in request.options
                    if o.option_id == "army-alpha:attacker"
                    or "decline" in o.option_id
                    or "keep" in o.option_id
                ),
                request.options[0],
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:resolve",
                option_id=option.option_id,
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    assert hits
    hit = hits[0]
    assert isinstance(hit, dict)
    payload = hit["payload"]
    assert isinstance(payload, dict)
    assert payload["target_number"] == 4
    assert payload["modifier"] == 0
    for viewer in ("player-a", "player-b"):
        events = canonical_json(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "object at 0x" not in events
        assert "obscuring_model_cover" not in events
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order40:attack"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("drift", ["schema", "identity", "text_hash", "status", "execution_source"])
def test_order40_source_loader_rejects_invalid_reviewed_content(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    import hashlib
    import json

    from tools.build_core_smokescreen_source import build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_smokescreen_2026_09 as source,
    )

    # Keep the transport pin consistent to exercise each inner validation boundary.
    payload = json.loads(json.dumps(build_payloads()[0]))
    if drift == "schema":
        payload["unexpected"] = True
    elif drift == "identity":
        payload["source_package_id"] = "wrong-package"
    elif drift == "text_hash":
        payload["rules"][0]["source_text"] += " drift"
    elif drift == "status":
        payload["rules"][0]["runtime_consumer_ids"] = []
    else:
        from warhammer40k_core.rules.rule_ir import RuleIR

        rule = RuleIR.from_payload(payload["execution_payload"]["rule_ir"])
        payload["execution_payload"]["rule_ir"] = replace(
            rule, source_id="wrong-source"
        ).to_payload()
    raw = json.dumps(payload).encode()
    monkeypatch.setattr(source, "EXPECTED_ARTIFACT_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(source.SmokescreenSourceError):
        source.validate_source_artifact_bytes(raw)


@pytest.mark.parametrize("missing", ["battlefield", "attacker", "target"])
def test_order40_geometry_requires_complete_present_attack_context(missing: str) -> None:
    from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_sources
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, units, pool = smoke_scene()
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(smoke_grant(units["smoke"].unit_instance_id))
    if missing == "battlefield":
        state.battlefield_state = None
    elif missing == "attacker":
        pool = replace(pool, attacker_model_instance_id="missing-attacker")
    else:
        assert state.battlefield_state is not None
        state.battlefield_state = state.battlefield_state.with_removed_models(
            (units["target"].own_models[0].model_instance_id,)
        )
    with pytest.raises(GameLifecycleError, match="Cover requires"):
        obscuring_model_cover_sources(state=state, pool=pool)
