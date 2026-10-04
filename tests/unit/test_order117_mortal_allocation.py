from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.hazard_all_models_helpers import hazard_scene
from tests.lethal_hits_helpers import attack_completed
from tests.order116_mortal_helpers import additional_mortal_session
from tests.order117_allocation_helpers import (
    PERMISSION_ID,
    SOURCE_ID,
    allocation_permission_session,
    complete_allocation_attack,
)
from tests.order120_psychic_damage_helpers import (
    SOURCE_ID as PSYCHIC_DAMAGE_SOURCE_ID,
)
from tests.order120_psychic_damage_helpers import (
    official_psychic_damage_source,
    psychic_ability_damage_session,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.ability_damage_context import (
    ability_damage_is_psychic_attack,
    ability_damage_source_context,
)
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainAttackCondition,
    FeelNoPainSource,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.direct_mortal_wound_application import (
    apply_direct_mortal_wounds_to_unit,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mortal_wound_allocation_permissions import (
    mortal_wound_allocation_permission_effect,
    mortal_wound_allocation_preventions,
    validate_mortal_wound_allocation_permission,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.ability_damage_source import (
    AbilityDamageClassification,
    AbilityDamageSource,
    AbilityDamageSourceError,
    AbilityDamageSourcePayload,
    ability_damage_source_at_data_boundary,
)
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_data import RuleSourceText


def test_order120_real_psychic_damage_source_and_historical_core_pins() -> None:
    root = Path(__file__).parents[2]
    audit = json.loads((root / "data/source_audits/order120/source.audit.json").read_text())
    example = audit["official_example"]
    assert hashlib.sha256((root / example["path"]).read_bytes()).hexdigest() == example["sha256"]
    assert (
        hashlib.sha256(example["operative_text"].encode()).hexdigest()
        == example["operative_text_sha256"]
    )
    selected = root / "data/source_audits/order97/selected-sources.json"
    assert hashlib.sha256(selected.read_bytes()).hexdigest() == audit["selected_sources_sha256"]
    assert audit["selected_core_row"] in json.loads(selected.read_bytes())
    descriptor = official_psychic_damage_source()
    assert descriptor.classification is AbilityDamageClassification.PSYCHIC_ATTACK
    assert descriptor.source_rule_id == PSYCHIC_DAMAGE_SOURCE_ID
    assert AbilityDamageSource.from_payload(descriptor.to_payload()) == descriptor


@pytest.mark.parametrize(
    ("title", "psychic"),
    [
        ("Gift (Psychic):", True),
        ("Gift (Aura, Psychic):", True),
        ("Gift (Psychic level 2):", True),
        ("Psychic Gift:", False),
        ("Gift (Aura):", False),
        ("Gift: This is a Psychic test.", False),
    ],
)
def test_order120_classifies_explicit_source_title_once(title: str, psychic: bool) -> None:
    source = ability_damage_source_at_data_boundary(
        RuleSourceText.from_raw(
            source_id="order120:source",
            raw_text=f"{title} The target suffers 1 mortal wound.",
            objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
        )
    )
    assert (source.classification is AbilityDamageClassification.PSYCHIC_ATTACK) is psychic


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("decline", [False, True])
def test_order120_ability_classification_survives_real_pending_fork_viewers_and_replay(
    phase: BattlePhase,
    decline: bool,
) -> None:
    session = psychic_ability_damage_session(phase)
    for _ in range(100):
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain":
            break
        assert not attack_completed(session)
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Psychic ability mortal prevention was not offered.")
    context = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["lost_wound_context"]
    )
    source_context = cast(dict[str, JsonValue], context["source_context"])
    assert ability_damage_is_psychic_attack(source_context)
    evidence = cast(dict[str, JsonValue], context["destruction_evidence"])
    attribution = cast(dict[str, JsonValue], evidence["destruction_attribution"])
    provenance = cast(dict[str, JsonValue], attribution["destruction_provenance"])
    assert provenance["destruction_source_kind"] == "attack"
    assert '"psychic"' not in json.dumps(provenance["source_weapon_profile"])
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = LocalGameSession.from_persistence_payload(checkpoint)
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id, result_id="order120:invalid", option_id="wrong-source"
        )
    assert restored.to_persistence_payload() == checkpoint
    complete_allocation_attack(restored, decline=decline)
    assert fork.to_persistence_payload() == checkpoint
    complete_allocation_attack(fork, decline=decline)
    assert fork.to_persistence_payload() == restored.to_persistence_payload()
    applications = [
        cast(dict[str, JsonValue], e.payload)["mortal_wound_application"]
        for e in restored.lifecycle.decision_controller.event_log.records
        if e.event_type == "additional_attack_mortal_wounds_applied"
    ]
    assert applications
    resolutions = [
        cast(dict[str, JsonValue], resolution)
        for application in applications
        for resolution in cast(
            list[JsonValue], cast(dict[str, JsonValue], application)["feel_no_pain_resolutions"]
        )
    ]
    assert resolutions
    assert any(resolution["source"] is not None for resolution in resolutions) is (not decline)
    if decline:
        assert all(resolution["rolls"] == [] for resolution in resolutions)
    _assert_restore_and_replay(restored, artifact_id=f"order120-{phase.value}-{decline}")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_order120_non_psychic_ability_never_uses_psychic_only_protection(
    phase: BattlePhase,
) -> None:
    session = psychic_ability_damage_session(phase, psychic=False)
    complete_allocation_attack(session)
    assert not any(
        e.event_type == "dice_rolled" and "order120:psychic-only-fnp" in json.dumps(e.payload)
        for e in session.lifecycle.decision_controller.event_log.records
    )
    _assert_restore_and_replay(session, artifact_id=f"order120-nonpsychic-{phase.value}")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_order120_ordinary_extra_mortals_keep_the_originating_psychic_weapon(
    phase: BattlePhase,
) -> None:
    session = psychic_ability_damage_session(phase, psychic=False, weapon_psychic=True)
    complete_allocation_attack(session)
    assert any(
        e.event_type == "dice_rolled" and "order120:psychic-only-fnp" in json.dumps(e.payload)
        for e in session.lifecycle.decision_controller.event_log.records
    )
    _assert_restore_and_replay(session, artifact_id=f"order120-psychic-weapon-{phase.value}")


@pytest.mark.parametrize("psychic", [False, True])
@pytest.mark.parametrize("optional", [False, True])
def test_order120_non_attack_direct_ability_damage_preserves_classification_before_mutation(
    psychic: bool,
    optional: bool,
) -> None:
    session = additional_mortal_session(BattlePhase.SHOOTING, enemy_models=1)
    state = session.lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    descriptor = (
        official_psychic_damage_source()
        if psychic
        else ability_damage_source_at_data_boundary(
            RuleSourceText.from_raw(
                source_id=PSYCHIC_DAMAGE_SOURCE_ID,
                raw_text="Ordinary ability: Target loses wounds.",
                objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
            )
        )
    )
    for model in target.own_models:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model.model_instance_id,
            sources=(
                FeelNoPainSource(
                    source_id="order120:direct-fnp",
                    threshold=2,
                    attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
                ),
            ),
            decline_allowed=optional,
        )
    decisions = session.lifecycle.decision_controller
    source_context = ability_damage_source_context(
        source=descriptor,
        source_context={"source_kind": "ability", "source_rule_id": descriptor.source_rule_id},
    )
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.SHOOTING,
        source_step="order120:provider-authorized-outcome",
    )
    assert evidence.destruction_source_kind is DestructionSourceKind.ABILITY
    before = session.to_persistence_payload()

    def apply() -> MortalWoundApplication:
        return apply_direct_mortal_wounds_to_unit(
            state=state,
            decisions=decisions,
            application_id="order120:direct",
            source_rule_id=descriptor.source_rule_id,
            source_context=source_context,
            destruction_evidence=evidence,
            target_unit_instance_id=target.unit_instance_id,
            mortal_wounds=1,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            defender_player_id="player-b",
        )

    if psychic and optional:
        with pytest.raises(GameLifecycleError, match="choices require lifecycle routing"):
            apply()
        assert session.to_persistence_payload() == before
    else:
        result = apply()
        assert bool(result.feel_no_pain_resolutions) is psychic
        assert (
            bool(
                [
                    e
                    for e in decisions.event_log.records
                    if e.event_type == "dice_rolled"
                    and "order120:direct-fnp" in json.dumps(e.payload)
                ]
            )
            is psychic
        )
        restored = LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(session.to_persistence_payload()))
        )
        assert restored.to_persistence_payload() == session.to_persistence_payload()


def test_order120_malformed_or_wrong_source_descriptor_fails_closed() -> None:
    descriptor = official_psychic_damage_source()
    for change in ({"classification": "unknown"}, {"normalized_text_sha256": "x"}, {"extra": True}):
        with pytest.raises(AbilityDamageSourceError):
            AbilityDamageSource.from_payload(
                cast(AbilityDamageSourcePayload, {**descriptor.to_payload(), **change})
            )
    context = ability_damage_source_context(
        source=descriptor, source_context={"source_rule_id": descriptor.source_rule_id}
    )
    context_changes: tuple[dict[str, JsonValue], ...] = (
        {"source_rule_id": "wrong-source"},
        {"ability_damage_source": []},
    )
    for context_change in context_changes:
        with pytest.raises(GameLifecycleError):
            ability_damage_is_psychic_attack({**context, **context_change})
    with pytest.raises(GameLifecycleError):
        ability_damage_source_context(source=descriptor, source_context=context)
    with pytest.raises(GameLifecycleError):
        ability_damage_source_context(source=descriptor, source_context={"source_rule_id": "wrong"})
    with pytest.raises(GameLifecycleError, match="application source identity"):
        ability_damage_is_psychic_attack(context, source_rule_id="wrong-application-source")


def test_order120_invalid_descriptor_rejects_before_zero_prevention_mutation() -> None:
    session = additional_mortal_session(BattlePhase.SHOOTING, enemy_models=1)
    state = session.lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    decisions = session.lifecycle.decision_controller
    descriptor = official_psychic_damage_source()
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.SHOOTING,
        source_step="order120:invalid-provider-outcome",
    )
    context: dict[str, JsonValue] = {
        "source_rule_id": descriptor.source_rule_id,
        "ability_damage_source": {
            "source_rule_id": descriptor.source_rule_id,
            "normalized_text_sha256": descriptor.normalized_text_sha256,
            "classification": "unknown",
        },
    }
    before = session.to_persistence_payload()
    with pytest.raises(GameLifecycleError, match="malformed"):
        apply_direct_mortal_wounds_to_unit(
            state=state,
            decisions=decisions,
            application_id="order120:invalid-direct",
            source_rule_id=descriptor.source_rule_id,
            source_context=context,
            destruction_evidence=evidence,
            target_unit_instance_id=target.unit_instance_id,
            mortal_wounds=1,
        )
    assert session.to_persistence_payload() == before
    progress = MortalWoundApplicationProgress.start(
        application_id="order120:invalid-progress",
        source_rule_id=descriptor.source_rule_id,
        source_context=context,
        target_unit_instance_id=target.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
        destruction_evidence=evidence,
    )
    with pytest.raises(GameLifecycleError, match="malformed"):
        continue_mortal_wound_application(
            state=state,
            decisions=decisions,
            request_id="order120:invalid-progress-request",
            progress=progress,
        )
    assert session.to_persistence_payload() == before


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_allocation_trigger_executes_source_backed_prevention_before_wound_loss(
    phase: BattlePhase,
) -> None:
    session = allocation_permission_session(phase)
    complete_allocation_attack(session)
    events = session.lifecycle.decision_controller.event_log.records
    allocated = [e for e in events if e.event_type == "mortal_wound_model_allocated"]
    applied = [e for e in events if e.event_type == "mortal_wound_allocation_rule_applied"]
    assert allocated
    assert applied
    assert len(applied) == len(allocated)
    for allocation, execution in zip(allocated, applied, strict=True):
        assert isinstance(allocation.payload, dict)
        assert isinstance(execution.payload, dict)
        assert execution.payload["allocation_occurrence_id"] == allocation.payload["occurrence_id"]
        assert execution.payload["source_rule_id"] == SOURCE_ID
        assert execution.payload["permission_effect_id"] == PERMISSION_ID
        assert execution.payload["trigger_kind"] == "mortal_wound_allocated"
        assert events.index(allocation) < events.index(execution)
        source = cast(dict[str, JsonValue], execution.payload["feel_no_pain_source"])
        rolls = [
            e
            for e in events[events.index(execution) + 1 :]
            if e.event_type == "dice_rolled"
            and isinstance(e.payload, dict)
            and cast(str, source["source_id"]) in json.dumps(e.payload)
        ]
        assert rolls
    resolved = [e for e in events if e.event_type == "additional_attack_mortal_wounds_applied"]
    assert resolved
    application = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], resolved[0].payload)["mortal_wound_application"],
    )
    assert cast(int, application["ignored_mortal_wounds"]) > 0
    _assert_restore_and_replay(session, artifact_id=f"order117-{phase.value}-completed")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("decline", [False, True])
def test_allocation_trigger_pending_choice_retry_fork_and_lethal_continuation(
    phase: BattlePhase, decline: bool
) -> None:
    session = allocation_permission_session(phase, decline_allowed=True)
    for _ in range(100):
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain":
            break
        assert not attack_completed(session)
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Allocation-trigger Feel No Pain choice was not reached.")
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = LocalGameSession.from_persistence_payload(checkpoint)
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:invalid-option",
            option_id="missing-source",
        )
    assert restored.to_persistence_payload() == checkpoint
    complete_allocation_attack(restored, decline=decline)
    assert fork.to_persistence_payload() == checkpoint
    complete_allocation_attack(fork, decline=decline)
    assert fork.to_persistence_payload() == restored.to_persistence_payload()
    assert attack_completed(restored)
    occurrences = [
        cast(dict[str, JsonValue], e.payload)["occurrence_id"]
        for e in restored.lifecycle.decision_controller.event_log.records
        if e.event_type == "mortal_wound_model_allocated"
    ]
    assert len(occurrences) == len(set(cast(list[str], occurrences)))
    _assert_restore_and_replay(restored, artifact_id=f"order117-{phase.value}-{decline}")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("existing_fnp", [False, True])
def test_allocation_boundary_is_independent_of_prevention_configuration(
    phase: BattlePhase, existing_fnp: bool
) -> None:
    session = additional_mortal_session(
        phase, mortal_wounds=12, attacks=3, armor_penetration=0, optional_fnp=existing_fnp
    )
    complete_allocation_attack(session, decline=True)
    events = session.lifecycle.decision_controller.event_log.records
    occurrences = [e for e in events if e.event_type == "mortal_wound_model_allocated"]
    assert occurrences
    assert not any(e.event_type == "mortal_wound_allocation_rule_applied" for e in events)
    _assert_restore_and_replay(session, artifact_id=f"order117-plain-{phase.value}-{existing_fnp}")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_allocation_permission_does_not_protect_another_rules_unit(phase: BattlePhase) -> None:
    session = allocation_permission_session(phase, permission_target_is_attacker=True)
    complete_allocation_attack(session)
    assert not any(
        e.event_type == "mortal_wound_allocation_rule_applied"
        for e in session.lifecycle.decision_controller.event_log.records
    )


def test_allocation_permission_factory_and_schema_fail_closed() -> None:
    session = allocation_permission_session(BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    permission = next(e for e in state.persisting_effects if e.effect_id == PERMISSION_ID)
    assert isinstance(permission.effect_payload, dict)
    changes: tuple[dict[str, JsonValue], ...] = (
        {"threshold": 0},
        {"threshold": 1},
        {"threshold": True},
        {"decline_allowed": 1},
        {"trigger_kind": "start_phase"},
        {"rule_kind": "unknown"},
        {"occasion_id": ""},
        {"target_model_instance_ids": []},
    )
    for change in changes:
        with pytest.raises(GameLifecycleError, match="permission"):
            validate_mortal_wound_allocation_permission(
                replace(permission, effect_payload={**permission.effect_payload, **change})
            )
    with pytest.raises(GameLifecycleError, match="permission"):
        mortal_wound_allocation_permission_effect(
            state=state,
            effect_id="order117:bad-threshold",
            source_rule_id=SOURCE_ID,
            target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
            occasion_id="provider-occasion",
            threshold=7,
        )


@pytest.mark.parametrize("decline_allowed", [False, True])
def test_direct_route_executes_the_same_prevention_or_rejects_choice_before_mutation(
    decline_allowed: bool,
) -> None:
    session = allocation_permission_session(
        BattlePhase.SHOOTING, enemy_models=1, threshold=2, decline_allowed=decline_allowed
    )
    state = session.lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    decisions = session.lifecycle.decision_controller
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.SHOOTING,
        source_step="order117-direct-consumer",
    )
    before = session.to_persistence_payload()
    if decline_allowed:
        with pytest.raises(GameLifecycleError, match="choices require lifecycle routing"):
            apply_direct_mortal_wounds_to_unit(
                state=state,
                decisions=decisions,
                application_id="order117:direct",
                source_rule_id="order117:direct-source",
                source_context={"source_kind": "ability"},
                destruction_evidence=evidence,
                target_unit_instance_id=target.unit_instance_id,
                mortal_wounds=2,
                dice_manager=manager,
                defender_player_id="player-b",
            )
        assert session.to_persistence_payload() == before
        return
    result = apply_direct_mortal_wounds_to_unit(
        state=state,
        decisions=decisions,
        application_id="order117:direct",
        source_rule_id="order117:direct-source",
        source_context={"source_kind": "ability"},
        destruction_evidence=evidence,
        target_unit_instance_id=target.unit_instance_id,
        mortal_wounds=2,
        dice_manager=manager,
        defender_player_id="player-b",
    )
    assert len(result.feel_no_pain_resolutions) == 2
    assert all(
        r.source is not None and r.source.threshold == 2 for r in result.feel_no_pain_resolutions
    )
    assert result.ignored_mortal_wounds == sum(
        r.ignored_wounds for r in result.feel_no_pain_resolutions
    )
    allocated = [
        e for e in decisions.event_log.records if e.event_type == "mortal_wound_model_allocated"
    ]
    assert len(allocated) == 2
    assert (
        len(
            [
                e
                for e in decisions.event_log.records
                if e.event_type == "mortal_wound_allocation_rule_applied"
            ]
        )
        == 2
    )
    assert all(
        cast(dict[str, JsonValue], e.payload)["selection_disposition"] == "sole_legal_model"
        for e in allocated
    )


def test_allocation_permission_freezes_all_attached_physical_models() -> None:
    session, units = hazard_scene("INFANTRY", attached=True)
    state = session.lifecycle.state
    assert state is not None
    group = rules_unit_view_by_id(state=state, unit_instance_id=units["shooter"].unit_instance_id)
    effect = mortal_wound_allocation_permission_effect(
        state=state,
        effect_id=PERMISSION_ID,
        source_rule_id=SOURCE_ID,
        target_unit_instance_id=units["leader"].unit_instance_id,
        occasion_id="order117:attached",
        threshold=4,
    )
    state.record_persisting_effect(effect)
    assert isinstance(effect.effect_payload, dict)
    assert effect.effect_payload["target_model_instance_ids"] == sorted(
        m.model_instance_id for m in group.alive_models()
    )
    assert len(group.component_unit_instance_ids) == 2
    for model in group.alive_models():
        assert (
            mortal_wound_allocation_preventions(
                state=state, model_instance_id=model.model_instance_id
            )[0].permission
            == effect
        )


@pytest.mark.parametrize("use_reroll", [False, True])
def test_source_permission_survives_real_save_reroll_and_lethal_continuation(
    use_reroll: bool,
) -> None:
    session = allocation_permission_session(
        BattlePhase.SHOOTING, command_reroll_player_id="player-b", enemy_models=5
    )
    reached = False
    for _ in range(180):
        if attack_completed(session):
            break
        request = pending_request(session)
        if "decline_stratagem_window" in {o.option_id for o in request.options}:
            assert isinstance(request.payload, dict)
            context = cast(dict[str, JsonValue], request.payload["stratagem_context"])
            trigger = cast(dict[str, JsonValue], context["trigger_payload"])
            option_id = "decline_stratagem_window"
            if cast(str, trigger["roll_type"]).startswith("attack_sequence.save") and not reached:
                reached = True
                session = LocalGameSession.from_persistence_payload(
                    json.loads(json.dumps(session.to_persistence_payload()))
                )
                if use_reroll:
                    option_id = next(
                        o.option_id
                        for o in request.options
                        if o.option_id.startswith("use-stratagem:command-reroll:")
                    )
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order117-reroll",
                option_id=option_id,
            )
        elif request.decision_type == "select_feel_no_pain":
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order117-source",
                option_id=request.options[-1].option_id,
            )
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Source-backed reroll continuation did not complete.")
    assert reached
    assert any(
        e.event_type == "mortal_wound_allocation_rule_applied"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    _assert_restore_and_replay(session, artifact_id=f"order117-reroll-{use_reroll}")


def _assert_restore_and_replay(session: LocalGameSession, *, artifact_id: str) -> None:
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        delta = restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert delta == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert "mortal_wound_allocation_rule_applied" not in json.dumps(delta)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=artifact_id)).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_missing_prevention_dice_authority_fails_before_allocation_and_allows_retry() -> None:
    session = allocation_permission_session(BattlePhase.SHOOTING, enemy_models=1)
    state = session.lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    decisions = session.lifecycle.decision_controller
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.SHOOTING,
        source_step="order117-missing-dice-authority",
    )
    progress = MortalWoundApplicationProgress.start(
        application_id="order117:missing-dice-authority",
        source_rule_id=SOURCE_ID,
        source_context={"source_kind": "ability"},
        target_unit_instance_id=target.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
        destruction_evidence=evidence,
    )
    state_before = state.to_payload()
    records_before = decisions.records
    with pytest.raises(GameLifecycleError, match="requires dice manager"):
        continue_mortal_wound_application(
            state=state,
            decisions=decisions,
            request_id="order117:missing-dice-request",
            progress=progress,
        )
    assert state.to_payload() == state_before
    assert decisions.records == records_before
    assert not any(
        e.event_type
        in {
            "mortal_wound_model_allocated",
            "mortal_wound_allocation_rule_applied",
            "dice_rolled",
        }
        for e in decisions.event_log.records
    )
    result = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="order117:missing-dice-request",
        progress=progress,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    assert result.application is not None
    assert len(result.application.feel_no_pain_resolutions) == 1
    assert (
        sum(e.event_type == "mortal_wound_model_allocated" for e in decisions.event_log.records)
        == 1
    )


def test_direct_unconditional_allocation_keeps_existing_prevention_dice_sequence() -> None:
    session = additional_mortal_session(BattlePhase.SHOOTING, enemy_models=1)
    state = session.lifecycle.state
    assert state is not None
    target = state.army_definitions[1].units[0]
    state.record_model_feel_no_pain_sources(
        model_instance_id=target.own_models[0].model_instance_id,
        sources=(FeelNoPainSource(source_id="review:existing-automatic-fnp", threshold=4),),
        decline_allowed=False,
    )
    lifecycle = session.lifecycle.from_payload(
        json.loads(json.dumps(session.lifecycle.to_payload()))
    )
    state = lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    decisions = lifecycle.decision_controller
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.SHOOTING,
        source_step="review-direct-neutrality",
    )
    application = apply_direct_mortal_wounds_to_unit(
        state=state,
        decisions=decisions,
        application_id="review:direct-neutrality",
        source_rule_id="review:direct-source",
        source_context={"source_kind": "ability"},
        destruction_evidence=evidence,
        target_unit_instance_id=target.unit_instance_id,
        mortal_wounds=2,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        defender_player_id="player-b",
    )
    # Correct neutral packet-start accounting gives the same sequence with or
    # without allocation audits, independently checked against the prior owner.
    assert [r.rolls[0].roll_state.current_values for r in application.feel_no_pain_resolutions] == [
        (5,),
        (4,),
    ]
    assert application.ignored_mortal_wounds == 2
    assert state.army_definitions[1].units[0].own_models[0].wounds_remaining == 2
    assert (
        sum(e.event_type == "mortal_wound_model_allocated" for e in decisions.event_log.records)
        == 2
    )
