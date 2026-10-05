from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.order97_gap_probes_18_25 import probe_attack_sequence_grant_retention

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
    DatasheetCatalogError,
)
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_abilities import (
    deadly_demise_profile_for_unit,
    firing_deck_value_for_unit,
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
    unit_has_deadly_demise,
    unit_has_deep_strike,
    unit_has_firing_deck,
    unit_has_infiltrators,
    unit_has_leader,
    unit_has_scouts,
    unit_has_support,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


def test_attached_conferring_bearer_survives_as_ability_source_until_attacks_finish() -> None:
    observation = probe_attack_sequence_grant_retention()
    observed_value = observation["observed"]
    assert isinstance(observed_value, dict)
    observed = cast(dict[str, object], observed_value)
    assert observed["grant_before_attack"] is True
    assert observed["remaining_sequence"] is True
    windows_value = observed["damage_window_observations"]
    assert isinstance(windows_value, list)
    windows = cast(list[dict[str, object]], windows_value)
    assert windows
    assert windows[0]["attack_index"] == 0
    assert windows[0]["surviving_target_models"] == 5
    assert windows[0]["grant_active"] is True


@pytest.mark.parametrize("phase_token", ["shooting", "fight"])
@pytest.mark.parametrize("source_role", ["bodyguard", "leader", "support"])
def test_attached_source_lifetime_facade_restore_replay(phase_token: str, source_role: str) -> None:
    import json

    from tests.lethal_hits_helpers import attack_completed
    from tests.order118_source_helpers import (
        reach_source_casualty,
        source_grant_active,
        source_retention_session,
        submit_source_choice,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.retained_destruction_state import retained_destructions
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, model_id = source_retention_session(BattlePhase(phase_token), source_role=source_role)
    assert source_grant_active(session)
    request = reach_source_casualty(session, source_model_id=model_id)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert not model_by_id(state=state, model_instance_id=model_id).is_alive
    assert state.battlefield_state.model_placement_or_none(model_id) is None
    assert retained_destructions(state=state) == ()
    assert source_grant_active(session)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
    presence = ability_presence(state=state, rules_unit=view)
    assert model_id in presence.active_model_ids
    assert model_id not in presence.battlefield_model_ids
    saved = session.to_persistence_payload()
    json.dumps(saved, allow_nan=False)
    restored = LocalGameSession.from_persistence_payload(saved)
    fork = session.fork()
    assert restored.to_persistence_payload() == saved
    assert source_grant_active(restored)
    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == delta
        assert "attack_ability_source_retained" not in str(delta)
    from warhammer40k_core.engine.decision import DecisionError

    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id,
            result_id="order118:malformed",
            option_id="order118:nonexistent-option",
        )
    assert restored.to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order118:mid")).run().status
        is ReplayRunStatus.REPRODUCED
    )
    for current in (session, restored):
        for _ in range(150):
            if attack_completed(current):
                break
            submit_source_choice(current, pending_request(current), source_model_id=model_id)
        assert attack_completed(current)
        assert not source_grant_active(current)
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="order118:done"))
            .run()
            .status
            is ReplayRunStatus.REPRODUCED
        )
        complete = current.to_persistence_payload()
        assert (
            LocalGameSession.from_persistence_payload(complete).to_persistence_payload() == complete
        )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert fork.to_persistence_payload() == saved
    assert source_grant_active(fork)


@pytest.mark.parametrize("phase_token", ["shooting", "fight"])
def test_equipped_attached_source_lifetime_uses_shared_catalog_consumer(phase_token: str) -> None:
    from tests.order118_source_helpers import (
        reach_source_casualty,
        source_grant_active,
        source_retention_session,
    )

    from warhammer40k_core.engine.phase import BattlePhase

    session, model_id = source_retention_session(BattlePhase(phase_token), source_wargear=True)
    assert source_grant_active(session)
    reach_source_casualty(session, source_model_id=model_id)
    assert source_grant_active(session)


@pytest.mark.parametrize("direct", [True, False])
@pytest.mark.parametrize("attack", [True, False])
def test_mortal_application_routes_retain_only_attack_conferring_sources(
    direct: bool, attack: bool
) -> None:
    from tests.order118_source_helpers import source_grant_active, source_retention_session

    from warhammer40k_core.engine.attack_ability_source_retention import (
        expire_attack_ability_sources,
    )
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        model_by_id,
    )
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.direct_mortal_wound_application import (
        apply_direct_mortal_wounds_to_unit,
    )
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.game_state import GameConfig, GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, model_id = source_retention_session(BattlePhase.SHOOTING, optional_fnp=False)
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
    attacker = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:attacker")
    config_payload = session.lifecycle.to_payload()["config"]
    assert config_payload is not None
    config = GameConfig.from_payload(config_payload)
    weapon = next(
        row for row in config.army_catalog.wargear if row.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    evidence = (
        MortalWoundDestructionEvidence.for_attack_state(
            state=state,
            destroying_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacking_model_instance_id=attacker.alive_models()[0].model_instance_id,
            weapon_profile=weapon,
            attack_context_id="order118:mortal-attack",
            action_phase=BattlePhase.SHOOTING,
            source_step="order118:mortal-consumer",
        )
        if attack
        else MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id="player-a",
            source_rules_unit_instance_id=attacker.unit_instance_id,
            source_model_instance_id=attacker.alive_models()[0].model_instance_id,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.SHOOTING,
            source_step="order118:mortal-consumer",
        )
    )
    context: JsonValue = {
        "sequence_id": "order118:mortal-sequence",
        "source_kind": "attack" if attack else "ability",
    }
    if direct:
        application = apply_direct_mortal_wounds_to_unit(
            state=state,
            decisions=decisions,
            application_id="order118:mortal-application",
            source_rule_id="order118:mortal-source",
            source_context=context,
            destruction_evidence=evidence,
            target_unit_instance_id=target.unit_instance_id,
            mortal_wounds=1,
        )
    else:
        routed = continue_mortal_wound_application(
            state=state,
            decisions=decisions,
            request_id="order118:mortal-request",
            progress=MortalWoundApplicationProgress.start(
                application_id="order118:mortal-application",
                source_rule_id="order118:mortal-source",
                source_context=context,
                destruction_evidence=evidence,
                target_unit_instance_id=target.unit_instance_id,
                defender_player_id="player-b",
                mortal_wounds=1,
                spill_over=True,
            ),
        )
        assert routed.request is None
        assert routed.application is not None
        application = routed.application
    assert application.applications[0].model_instance_id == model_id
    assert not model_by_id(state=state, model_instance_id=model_id).is_alive
    assert source_grant_active(session) is attack
    restored_state = GameState.from_payload(state.to_payload())
    assert restored_state.to_payload() == state.to_payload()
    expire_attack_ability_sources(
        state=state, decisions=decisions, sequence_id="order118:mortal-sequence"
    )
    assert not source_grant_active(session)


def test_retained_model_aura_keeps_attached_ability_without_external_geometry() -> None:
    from tests.lethal_hits_helpers import attack_completed
    from tests.order118_source_helpers import (
        reach_source_casualty,
        source_retention_session,
        source_stealth_granted_model_ids,
        submit_source_choice,
    )
    from tests.psychic_modifier_helpers import pending_request
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleEffectSpec, RuleParameter

    text = (
        'Aura: while a friendly unit is within 6" of this model, '
        "that unit has the [STEALTH] ability."
    )
    ir = compiled_ability_rule(text, source_id="test:order118:stealth-aura")
    # The canonical catalog provider supplies the supported structured grant;
    # the rule-text compiler alone does not provide this ability-grant effect.
    ir = replace(
        ir,
        clauses=tuple(
            replace(
                clause,
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=clause.source_span,
                        parameters=(RuleParameter("ability", "stealth"),),
                    ),
                ),
            )
            for clause in ir.clauses
        ),
    )
    session, model_id = source_retention_session(
        BattlePhase.SHOOTING,
        ability_text=text,
        ability_rule_ir=ir,
    )

    def granted(current: LocalGameSession, target_id: str) -> tuple[str, ...]:
        return source_stealth_granted_model_ids(current, target_unit_instance_id=target_id)

    assert granted(session, "army-beta:enemy")
    assert granted(session, "army-beta:other")
    reach_source_casualty(session, source_model_id=model_id)
    assert granted(session, "army-beta:enemy")
    assert granted(session, "army-beta:other") == ()
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert granted(restored, "army-beta:enemy") == granted(session, "army-beta:enemy")
    assert granted(restored, "army-beta:other") == ()
    for _ in range(150):
        if attack_completed(session):
            break
        submit_source_choice(session, pending_request(session), source_model_id=model_id)
    assert attack_completed(session)
    assert granted(session, "army-beta:enemy") == ()
    assert granted(session, "army-beta:other") == ()


@pytest.mark.parametrize("source_wargear", [False, True])
def test_retained_passive_stealth_source_grants_only_living_attached_recipients(
    source_wargear: bool,
) -> None:
    from tests.lethal_hits_helpers import attack_completed
    from tests.order118_source_helpers import (
        reach_source_casualty,
        source_retention_session,
        source_stealth_granted_model_ids,
        submit_source_choice,
    )
    from tests.psychic_modifier_helpers import pending_request
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.rules.rule_ir import (
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleParameter,
        RuleTargetKind,
        RuleTargetSpec,
    )

    text = "Ranged weapons equipped by models in this unit have the [LETHAL HITS] ability."
    ir = compiled_ability_rule(text, source_id="test:order118:passive-stealth")
    # Supply the same typed passive-self grant used by the catalog provider.
    ir = replace(
        ir,
        clauses=tuple(
            replace(
                clause,
                template_id="phase17p:passive-self-ability-grant",
                trigger=None,
                conditions=(),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_UNIT, source_span=clause.source_span
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.WHILE_CONDITION_TRUE, source_span=clause.source_span
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=clause.source_span,
                        parameters=(
                            RuleParameter("ability", "stealth"),
                            RuleParameter("target_scope", "this_unit"),
                        ),
                    ),
                ),
            )
            for clause in ir.clauses
        ),
    )
    session, model_id = source_retention_session(
        BattlePhase.FIGHT, ability_rule_ir=ir, source_wargear=source_wargear
    )

    def granted(current: LocalGameSession) -> tuple[str, ...]:
        return source_stealth_granted_model_ids(current, target_unit_instance_id="army-beta:enemy")

    before = granted(session)
    assert model_id in before
    assert len(before) == 3
    reach_source_casualty(session, source_model_id=model_id)
    assert set(granted(session)) == set(before) - {model_id}
    saved = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    assert granted(restored) == granted(session)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order118:passive-mid"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    for _ in range(150):
        if attack_completed(session):
            break
        submit_source_choice(session, pending_request(session), source_model_id=model_id)
    assert attack_completed(session)
    assert granted(session) == ()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order118:passive-done"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("phase_token", ["shooting", "fight"])
def test_queued_source_destruction_survives_native_deferred_mortal_checkpoint(
    phase_token: str,
) -> None:
    from tests.order118_source_helpers import (
        reach_source_casualty,
        source_grant_active,
        source_retention_session,
        submit_source_choice,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.attack_ability_source_retention import (
        ATTACK_ABILITY_SOURCE_EXPIRED_EVENT,
        ATTACK_ABILITY_SOURCE_KIND,
    )
    from warhammer40k_core.engine.decision import DecisionError
    from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, model_id = source_retention_session(
        BattlePhase(phase_token),
        source_role="leader",
        native_deferred_mortals=True,
        death_reaction=True,
    )
    reach_source_casualty(session, source_model_id=model_id)
    state = session.lifecycle.state
    assert state is not None
    sequence = active_attack_sequence_for_state(state)
    assert sequence is not None
    assert sequence.pending_attack_destructions
    sequence_id = sequence.sequence_id

    def original_attack_completed(current: LocalGameSession) -> bool:
        return any(
            event.event_type == "attack_sequence_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("sequence_id") == sequence_id
            for event in current.lifecycle.decision_controller.event_log.records
        )

    assert source_grant_active(session)
    for _ in range(180):
        request = pending_request(session)
        payload = request.payload
        assert isinstance(payload, dict)
        lost_wound = payload.get("lost_wound_context")
        source_context = lost_wound.get("source_context") if isinstance(lost_wound, dict) else None
        if (
            isinstance(source_context, dict)
            and source_context.get("source_kind") == "devastating_wounds"
        ):
            assert request.decision_type == "select_feel_no_pain"
            break
        submit_source_choice(session, request, source_model_id=model_id)
    else:
        raise AssertionError("Native deferred mortal checkpoint was not reached.")
    sequence = active_attack_sequence_for_state(state)
    assert sequence is not None
    assert sequence.pending_attack_destructions
    assert source_grant_active(session)
    saved = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    assert source_grant_active(restored)
    fork = session.fork()
    assert fork.to_persistence_payload() == saved
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id,
            result_id="order118:native-malformed",
            option_id="order118:nonexistent-native-option",
        )
    assert restored.to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order118:native-mid"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    for current in (session, restored):
        for _ in range(250):
            if original_attack_completed(current):
                break
            submit_source_choice(current, pending_request(current), source_model_id=model_id)
        assert original_attack_completed(current)
        current_state = current.lifecycle.state
        assert current_state is not None
        assert not any(
            isinstance(effect.effect_payload, dict)
            and effect.effect_payload.get("effect_kind") == ATTACK_ABILITY_SOURCE_KIND
            for effect in current_state.persisting_effects
        )
        events = current.lifecycle.decision_controller.event_log.records
        expired = next(
            index
            for index, event in enumerate(events)
            if event.event_type == ATTACK_ABILITY_SOURCE_EXPIRED_EVENT
            and isinstance(event.payload, dict)
            and event.payload.get("sequence_id") == sequence_id
        )
        completed = next(
            index
            for index, event in enumerate(events)
            if event.event_type == "attack_sequence_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("sequence_id") == sequence_id
        )
        assert expired < completed
        complete = current.to_persistence_payload()
        assert (
            LocalGameSession.from_persistence_payload(complete).to_persistence_payload() == complete
        )
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="order118:native-done"))
            .run()
            .status
            is ReplayRunStatus.REPRODUCED
        )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert fork.to_persistence_payload() == saved


def test_core_keyword_ability_descriptors_enable_boolean_families_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(ability_id="source-deep-strike", name="Core Deep Strike"),
        _ability(ability_id="source-infiltrators", name="Infiltrators"),
        _ability(ability_id="source-leader", name="Leader"),
        _ability(ability_id="source-support", name="Support"),
    )

    assert unit_has_deep_strike(unit)
    assert unit_has_infiltrators(unit)
    assert unit_has_leader(unit)
    assert unit_has_support(unit)


def test_parameterized_core_keyword_ability_descriptors_parse_values_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(
            ability_id="source-scouts",
            name='Scouts 6"',
            parameter_tokens=('6"',),
        ),
        _ability(
            ability_id="source-firing-deck",
            name="Firing Deck 2",
            parameter_tokens=("2",),
        ),
        _ability(
            ability_id="source-deadly-demise",
            name="Deadly Demise D3",
            parameter_tokens=("d3",),
        ),
    )

    scouts_descriptors = scouts_ability_descriptors_for_unit(unit)
    deadly_demise = deadly_demise_profile_for_unit(unit)

    assert unit_has_scouts(unit)
    assert unit_has_firing_deck(unit)
    assert unit_has_deadly_demise(unit)
    assert len(scouts_descriptors) == 1
    assert scouts_distance_inches_from_descriptor(scouts_descriptors[0]) == 6.0
    assert firing_deck_value_for_unit(unit) == 2
    assert deadly_demise is not None
    assert deadly_demise.mortal_wounds_token == "D3"


def test_catalog_ability_descriptor_validates_wargear_ir_metadata() -> None:
    with pytest.raises(DatasheetCatalogError, match="requires source_wargear_id"):
        DatasheetAbilityDescriptor(
            ability_id="test-icon",
            name="Test Icon",
            source_id="datasheet:test:ability:test-icon",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.WARGEAR,
            effect_description="Test icon descriptor.",
        )
    with pytest.raises(DatasheetCatalogError, match="must not include source_wargear_id"):
        DatasheetAbilityDescriptor(
            ability_id="test-core",
            name="Test Core",
            source_id="datasheet:test:ability:test-core",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            source_wargear_id="test-wargear",
            effect_description="Test core descriptor.",
        )
    with pytest.raises(DatasheetCatalogError, match="requires rule_ir_payload"):
        DatasheetAbilityDescriptor(
            ability_id="test-instrument",
            name="Test Instrument",
            source_id="datasheet:test:ability:test-instrument",
            support=CatalogAbilitySupport.GENERIC_RULE_IR,
            source_kind=CatalogAbilitySourceKind.WARGEAR,
            source_wargear_id="test-instrument",
            effect_description="Test instrument descriptor.",
        )


def test_catalog_ability_descriptor_rejects_non_json_ir_payload_values() -> None:
    valid = DatasheetAbilityDescriptor(
        ability_id="test-json",
        name="Test JSON",
        source_id="datasheet:test:ability:test-json",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Test JSON descriptor.",
        rule_ir_payload={"nested": [None, True, 1.5, {"value": "ok"}]},
    )

    assert valid.rule_ir_payload == {"nested": [None, True, 1.5, {"value": "ok"}]}
    with pytest.raises(DatasheetCatalogError, match="must be finite"):
        DatasheetAbilityDescriptor(
            ability_id="test-inf",
            name="Test Infinity",
            source_id="datasheet:test:ability:test-inf",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test infinity descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {"bad": math.inf}),
        )
    with pytest.raises(DatasheetCatalogError, match="must be a JSON object"):
        DatasheetAbilityDescriptor(
            ability_id="test-container",
            name="Test Container",
            source_id="datasheet:test:ability:test-container",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test container descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, "not-object"),
        )
    with pytest.raises(DatasheetCatalogError, match="key must be a string"):
        DatasheetAbilityDescriptor(
            ability_id="test-key",
            name="Test Key",
            source_id="datasheet:test:ability:test-key",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test key descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {1: "bad"}),
        )
    with pytest.raises(DatasheetCatalogError, match="JSON-safe"):
        DatasheetAbilityDescriptor(
            ability_id="test-object",
            name="Test Object",
            source_id="datasheet:test:ability:test-object",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test object descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {"bad": object()}),
        )


def _unit_with_abilities(*abilities: DatasheetAbilityDescriptor) -> UnitInstance:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="army-alpha",
        selection=UnitMusterSelection(
            unit_selection_id="ability-unit",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
        datasheet=datasheet,
    )
    return replace(unit, datasheet_abilities=abilities)


def _ability(
    *,
    ability_id: str,
    name: str,
    parameter_tokens: tuple[str, ...] = (),
) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name=name,
        source_id=f"datasheet:core-intercessor-like-infantry:ability:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description=f"{name} descriptor.",
        timing_tags=(),
        parameter_tokens=parameter_tokens,
    )


@pytest.mark.parametrize(
    "source_kind", [CatalogAbilitySourceKind.CORE, CatalogAbilitySourceKind.DATASHEET]
)
def test_order56_core_family_is_normalized_at_the_descriptor_boundary(
    source_kind: CatalogAbilitySourceKind,
) -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily

    descriptor = _ability(
        ability_id="source-scouts", name='Core Scouts 8"', parameter_tokens=("8",)
    )
    descriptor = replace(descriptor, source_kind=source_kind)
    assert descriptor.core_family is CoreAbilityFamily.SCOUTS
    assert (
        DatasheetAbilityDescriptor.from_payload(descriptor.to_payload()).core_family
        is CoreAbilityFamily.SCOUTS
    )
    identified = replace(descriptor, ability_id="core-scouts", name="Localized display label")
    assert identified.core_family is CoreAbilityFamily.SCOUTS
    assert scouts_ability_descriptors_for_unit(_unit_with_abilities(identified)) == (identified,)


def test_order56_native_damage_abilities_preserve_each_source_before_selection() -> None:
    from warhammer40k_core.engine.unit_abilities import (
        deadly_demise_profiles_for_unit,
        feel_no_pain_profiles_for_unit,
    )

    unit = _unit_with_abilities(
        _ability(ability_id="fnp-a", name="Feel No Pain", parameter_tokens=("5+",)),
        _ability(ability_id="fnp-b", name="Feel No Pain", parameter_tokens=("5+",)),
        _ability(ability_id="dd-a", name="Deadly Demise", parameter_tokens=("D3",)),
        _ability(ability_id="dd-b", name="Deadly Demise", parameter_tokens=("D6",)),
    )
    fnp = feel_no_pain_profiles_for_unit(unit)
    demise = deadly_demise_profiles_for_unit(unit)
    assert tuple(profile.threshold for profile in fnp) == (5, 5)
    assert {profile.mortal_wounds_token for profile in demise} == {"D3", "D6"}
    assert (
        len(
            {profile.ability_source.instance_id for profile in fnp}
            | {profile.ability_source.instance_id for profile in demise}
        )
        == 4
    )


def test_order56_numeric_core_instances_require_and_retain_one_active_source() -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
    from warhammer40k_core.engine.core_ability_state import CoreAbilitySelection
    from warhammer40k_core.engine.phase import GameLifecycleError

    unit = _unit_with_abilities(
        _ability(ability_id="deck:a", name="Firing Deck 2", parameter_tokens=("2",)),
        _ability(ability_id="deck:b", name="Firing Deck 5", parameter_tokens=("5",)),
    )
    with pytest.raises(GameLifecycleError, match="selection"):
        firing_deck_value_for_unit(unit)
    source = next(
        source for source in unit.ability_source_instances() if source.ability_id == "deck:a"
    )
    selected = replace(
        unit,
        core_ability_selections=(
            CoreAbilitySelection(
                family=CoreAbilityFamily.FIRING_DECK,
                instance_id=source.instance_id,
                decision_result_id="choice:1",
                opportunity_id="opportunity:1",
            ),
        ),
    )
    assert firing_deck_value_for_unit(selected) == 2
    assert UnitInstance.from_payload(selected.to_payload()) == selected
    assert len(selected.ability_source_instances()) == 2
    with pytest.raises(GameLifecycleError, match="source"):
        replace(
            selected,
            core_ability_selections=(
                replace(selected.core_ability_selections[0], instance_id="forged"),
            ),
        )


@pytest.mark.parametrize(
    ("ability_name", "tokens", "expected"),
    [
        ("Firing Deck", ("2", "5"), 2),
        ("Lone Operative", ("9", "12"), 9),
        ("Fights First", ("", ""), None),
        ("Stealth", ("", ""), None),
    ],
)
@pytest.mark.parametrize("during_setup", [False, True])
def test_order56_core_instance_decision_uses_facade_and_restores(
    during_setup: bool,
    ability_name: str,
    tokens: tuple[str, str],
    expected: int | None,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.core_ability_selection import (
        SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE,
    )
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.engine.unit_abilities import lone_operative_profile_for_unit

    abilities = tuple(
        _ability(
            ability_id=f"source:{index}",
            name=ability_name,
            parameter_tokens=(token,) if token else (),
        )
        for index, token in enumerate(tokens)
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, *abilities))
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, _ = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",), catalog=catalog)
    if during_setup:
        config = lifecycle.config
        lifecycle = GameLifecycle()
        lifecycle.start(config)
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    choices = 0
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE
    ):
        request = status.decision_request
        assert len(request.options) == 2
        assert request.actor_id is not None
        assert session.view(viewer_player_id=request.actor_id)["pending_decision"] is not None
        if during_setup:
            opponent = "player-b" if request.actor_id == "player-a" else "player-a"
            pending_view = session.view(viewer_player_id=opponent)["pending_decision"]
            assert isinstance(pending_view, dict)
            assert pending_view["decision_type"] == "hidden_decision"
            assert "ability_sources" not in str(pending_view)
        lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
        session = LocalGameSession(lifecycle=lifecycle)
        source_option = next(
            option
            for option in request.options
            if cast(dict[str, object], cast(dict[str, object], option.payload)["ability_source"])[
                "ability_id"
            ]
            == "source:0"
        )
        pending_payload = lifecycle.to_payload()
        drifted = deepcopy(pending_payload)
        pending = drifted["decisions"]["queue"]["pending_requests"][0]
        pending["options"] = pending["options"][:-1]
        with pytest.raises(GameLifecycleError, match=r"inventory drift|decision_requested event"):
            GameLifecycle.from_payload(drifted)
        with pytest.raises(DecisionError, match="finite action space"):
            session.submit_option(
                request_id=request.request_id, option_id="forged", result_id=f"invalid:{choices}"
            )
        assert lifecycle.to_payload() == pending_payload
        status = session.submit_option(
            request_id=request.request_id,
            option_id=source_option.option_id,
            result_id=f"core-choice:{choices}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        if during_setup:
            from warhammer40k_core.adapters.event_stream import EventStreamCursor

            owner_events = session.events_since(
                EventStreamCursor(), viewer_player_id=request.actor_id
            )
            opponent = "player-b" if request.actor_id == "player-a" else "player-a"
            other_events = session.events_since(EventStreamCursor(), viewer_player_id=opponent)
            selected_event = next(
                event
                for event in owner_events["events"]
                if event["event_type"] == "core_ability_instance_selected"
                and isinstance(event["payload"], dict)
                and event["payload"].get("result_id") == f"core-choice:{choices}"
            )
            assert selected_event not in other_events["events"]
        choices += 1
        assert choices <= 10
    assert choices >= 2
    if during_setup:
        next_request = status.decision_request
        assert next_request is not None
        status = session.submit_option(
            request_id=next_request.request_id,
            option_id=next_request.options[0].option_id,
            result_id="order56:next-setup-step",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    for army in restored.state.army_definitions:
        for unit in army.units:
            if not unit.core_ability_selections:
                continue
            if ability_name == "Firing Deck":
                assert firing_deck_value_for_unit(unit) == expected
            if ability_name == "Lone Operative":
                profile = lone_operative_profile_for_unit(unit)
                assert profile is not None
                assert profile.range_inches == expected
            assert len(unit.ability_source_instances()) >= 2


def test_order56_keyword_grants_preserve_sources_even_when_already_present() -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
    from warhammer40k_core.engine.core_ability_state import core_instance_groups
    from warhammer40k_core.engine.model_keyword_grants import grant_unit_keywords

    native = _unit_with_abilities(_ability(ability_id="core-deep-strike", name="Deep Strike"))
    first = grant_unit_keywords(
        native, keywords=("DEEP STRIKE",), source_id="source:a", source_instance_id="effect:a"
    )
    second = grant_unit_keywords(
        first, keywords=("DEEP STRIKE",), source_id="source:b", source_instance_id="effect:b"
    )
    assert unit_has_deep_strike(second)
    sources = dict(core_instance_groups(second))[CoreAbilityFamily.DEEP_STRIKE]
    assert len(sources) == 3
    assert len({source.instance_id for source in sources}) == 3
    assert UnitInstance.from_payload(second.to_payload()) == second
    assert (
        grant_unit_keywords(
            second, keywords=("DEEP STRIKE",), source_id="source:b", source_instance_id="effect:b"
        )
        == second
    )
