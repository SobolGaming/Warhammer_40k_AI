from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from functools import lru_cache
from typing import cast

import pytest
from tests.chaos_defiler_catalog_helpers import (
    instantiate_defiler,
    july_defiler_catalog_package,
)
from tests.phase11c_command_phase_helpers import (
    battle_state,
)
from tests.phase13b_shooting_declaration_helpers import (
    proposal_from_request,
    shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction_aliases import (
    CHAOS_DAEMONS_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ALIAS_SOURCE_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
    faction_alias_for_id,
    faction_aliases,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightTypeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    _request_source_backed_wound_reroll_if_available,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHandler,
    AttackSequenceCompletedHookBinding,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHandler,
    MortalWoundFeelNoPainContinuationHookBinding,
    MortalWoundFeelNoPainContinuationHookRegistry,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
    _apply_shooting_unit_selected_grant_decision,
    _request_shooting_unit_selected_grant_decision_if_available,
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose


def test_faction_aliases_include_common_faction_keyword_references() -> None:
    chaos_space_marines = faction_alias_for_id(CHAOS_SPACE_MARINES_FACTION_ID)

    assert chaos_space_marines is not None
    assert chaos_space_marines.name == "Chaos Space Marines"
    assert "Heretic Astartes" in chaos_space_marines.reference_tokens()
    assert chaos_space_marines.source_ids == (CHAOS_SPACE_MARINES_FACTION_ALIAS_SOURCE_ID,)
    assert faction_reference_matches(
        faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
        reference="HERETIC ASTARTES",
    )
    assert faction_reference_matches(
        faction_id=CHAOS_DAEMONS_FACTION_ID,
        reference="Legiones Daemonica",
    )
    assert all(definition.source_ids for definition in faction_aliases())
    assert len(
        {source_id for definition in faction_aliases() for source_id in definition.source_ids}
    ) == len(faction_aliases())


@pytest.mark.stubbed
def test_attack_sequence_completed_hook_registry_requires_pure_typed_candidates() -> None:
    state = _csm_battle_state()
    decisions = DecisionController()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    attack_sequence = AttackSequence(
        sequence_id="dark-pact-registry-sequence",
        source_phase=BattlePhase.SHOOTING,
        attacker_player_id="player-a",
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_pools=(
            _attack_pool(
                attacker=unit,
                target=target,
                weapon_profile=_weapon_profile(melee=False),
            ),
        ),
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    expected_status = LifecycleStatus.advanced(stage=GameLifecycleStage.BATTLE)
    seen_hooks: list[str] = []

    def no_status_handler(hook_context: AttackSequenceCompletedContext) -> None:
        assert hook_context is context
        seen_hooks.append("a")

    def status_handler(hook_context: AttackSequenceCompletedContext) -> LifecycleStatus:
        assert hook_context is context
        seen_hooks.append("b")
        return expected_status

    registry = AttackSequenceCompletedHookRegistry.from_bindings(
        (
            AttackSequenceCompletedHookBinding(
                hook_id="b-status",
                source_id="test-source",
                handler=status_handler,
            ),
            AttackSequenceCompletedHookBinding(
                hook_id="a-none",
                source_id="test-source",
                handler=no_status_handler,
            ),
        )
    )

    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        "a-none",
        "b-status",
    )
    assert (
        attack_sequence_completed_event_id(
            decisions=decisions,
            attack_sequence=attack_sequence,
        )
        == completed_event.event_id
    )
    with pytest.raises(GameLifecycleError, match="require pure candidate discovery"):
        registry.candidates_for(context)
    assert seen_hooks == []
    assert AttackSequenceCompletedHookRegistry.empty().all_bindings() == ()

    duplicate_binding = AttackSequenceCompletedHookBinding(
        hook_id="duplicate",
        source_id="test-source",
        handler=no_status_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        AttackSequenceCompletedHookRegistry.from_bindings((duplicate_binding, duplicate_binding))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        AttackSequenceCompletedHookRegistry.from_bindings(
            cast(tuple[AttackSequenceCompletedHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="handler is not callable"):
        AttackSequenceCompletedHookBinding(
            hook_id="bad-handler",
            source_id="test-source",
            handler=cast(AttackSequenceCompletedHandler, None),
        )
    from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

    with pytest.raises(GameLifecycleError, match="requires typed candidates"):
        AttackSequenceCompletedHookRegistry.from_bindings(
            (
                AttackSequenceCompletedHookBinding(
                    hook_id="bad-status",
                    source_id="test-source",
                    handler=lambda _context: cast(LifecycleStatus, "bad-status"),
                    candidate_handler=lambda _context: cast(
                        tuple[TimingRuleCandidate, ...], "bad-candidates"
                    ),
                ),
            )
        ).candidates_for(context)
    with pytest.raises(GameLifecycleError, match="Completed attack sequence event is missing"):
        attack_sequence_completed_event_id(
            decisions=DecisionController(),
            attack_sequence=attack_sequence,
        )


def test_dark_pacts_runtime_contribution_registers_engine_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert {
        binding.hook_id for binding in contribution.shooting_unit_selected_grant_hook_bindings
    } == {
        army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
    }
    assert {
        binding.hook_id for binding in contribution.fight_unit_selected_grant_hook_bindings
    } == {
        army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }
    assert not contribution.attack_sequence_completed_hook_bindings
    assert (
        contribution.mortal_wound_feel_no_pain_hook_bindings[0].hook_id
        == army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID
    )
    assert (
        contribution.weapon_profile_modifier_bindings[0].modifier_id
        == army_rule.WEAPON_PROFILE_MODIFIER_ID
    )
    assert (
        contribution.attack_reroll_permission_bindings[0].modifier_id
        == army_rule.DEFILER_DAEMONFORGE_WOUND_REROLL_MODIFIER_ID
    )


def test_defiler_daemonforge_rerolls_wound_rolls_of_one_after_dark_pact() -> None:
    state = _csm_battle_state()
    defiler = _replace_first_unit_with_csm_defiler(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    contribution = army_rule.runtime_contribution()
    registry = RuntimeModifierRegistry.from_bindings(
        attack_reroll_permission_bindings=(contribution.attack_reroll_permission_bindings)
    )
    context = AttackRerollPermissionContext(
        state=state,
        player_id="player-a",
        attacking_unit_instance_id=defiler.unit_instance_id,
        attacker_model_instance_id=defiler.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
    )

    assert registry.attack_reroll_permission_context(context) is None

    _record_dark_pact_effect(
        state,
        unit=defiler,
        phase=BattlePhase.SHOOTING,
        pact=army_rule.DarkPactKind.LETHAL_HITS,
    )
    permission_context = registry.attack_reroll_permission_context(context)

    assert permission_context is not None
    assert permission_context.permission.source_id == army_rule.DEFILER_DAEMONFORGE_ABILITY_ID
    assert permission_context.permission.to_payload() == {
        "source_id": army_rule.DEFILER_DAEMONFORGE_ABILITY_ID,
        "timing_window": "attack_sequence.wound",
        "owning_player_id": "player-a",
        "eligible_roll_type": "attack_sequence.wound",
        "component_selection_policy": "whole_roll",
        "allowed_component_selections": None,
    }
    assert permission_context.source_payload == {
        "conditional_wound_reroll": {"reroll_unmodified_values": [1]},
        "dark_pacts_source_ability_id": army_rule.DARK_PACTS_SOURCE_ABILITY_ID,
        "datasheet_id": army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
        "source_ability_id": army_rule.DEFILER_DAEMONFORGE_ABILITY_ID,
    }


@pytest.mark.parametrize(
    ("reroll_option_id", "resolved_event_type"),
    [("reroll:0", "dice_reroll_resolved"), ("decline", "dice_reroll_declined")],
)
def test_defiler_daemonforge_runs_through_catalog_lifecycle_and_replay(
    reroll_option_id: str,
    resolved_event_type: str,
) -> None:
    session, status = _daemonforge_shooting_status(
        game_id="order56-daemonforge-12:d07:10",
        declaration_result_id="order56-daemonforge-12:d07:10:declaration:d07-vector:43",
        attacker_datasheet_id=army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
        choose_dark_pact=True,
    )
    request = _decision_request(status.decision_request)

    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    request_payload = cast(dict[str, JsonValue], request.payload)
    permission_payload = cast(dict[str, JsonValue], request_payload["permission"])
    attack_context = cast(dict[str, JsonValue], request_payload["attack_context"])
    wound_roll_state = cast(dict[str, JsonValue], attack_context["wound_roll_state"])
    assert wound_roll_state["current_values"] == [1]
    assert attack_context["phase"] == BattlePhase.SHOOTING.value
    assert permission_payload["source_id"] == army_rule.DEFILER_DAEMONFORGE_ABILITY_ID
    state = cast(GameState, session.lifecycle.state)
    attacker = _unit_for_player(state, player_id="player-a")
    assert (
        army_rule.active_dark_pact_for_unit(
            state,
            unit_instance_id=attacker.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is army_rule.DarkPactKind.LETHAL_HITS
    )
    initial_reroll_lifecycle_payload = copy.deepcopy(session.lifecycle.to_payload())

    resolved = session.submit_option(
        request_id=request.request_id,
        option_id=reroll_option_id,
        result_id=f"phase17g-csm-daemonforge-{reroll_option_id}",
    )

    assert resolved.status_kind is not LifecycleStatusKind.INVALID
    assert _event_count(session.lifecycle.decision_controller, resolved_event_type) == 1
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id=f"replay:phase17g:csm:daemonforge:{reroll_option_id}",
            initial_lifecycle_payload=initial_reroll_lifecycle_payload,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_defiler_daemonforge_runs_through_catalog_fight_lifecycle_and_replay() -> None:
    session, status = _daemonforge_fight_status(
        game_id="order56-daemonforge-fight-26:d07:4",
        declaration_result_id="order56-daemonforge-fight-26:d07:4:melee-declaration:d07-vector:134",
    )
    request = _decision_request(status.decision_request)

    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    request_payload = cast(dict[str, JsonValue], request.payload)
    permission_payload = cast(dict[str, JsonValue], request_payload["permission"])
    attack_context = cast(dict[str, JsonValue], request_payload["attack_context"])
    wound_roll_state = cast(dict[str, JsonValue], attack_context["wound_roll_state"])
    assert wound_roll_state["current_values"] == [1]
    assert attack_context["phase"] == BattlePhase.FIGHT.value
    assert permission_payload["source_id"] == army_rule.DEFILER_DAEMONFORGE_ABILITY_ID
    state = cast(GameState, session.lifecycle.state)
    attacker = _unit_for_player(state, player_id="player-a")
    assert (
        army_rule.active_dark_pact_for_unit(
            state,
            unit_instance_id=attacker.unit_instance_id,
            phase=BattlePhase.FIGHT,
        )
        is army_rule.DarkPactKind.LETHAL_HITS
    )
    initial_reroll_lifecycle_payload = copy.deepcopy(session.lifecycle.to_payload())

    resolved = session.submit_option(
        request_id=request.request_id,
        option_id="decline",
        result_id="phase17g-csm-daemonforge-fight-decline",
    )

    assert resolved.status_kind is not LifecycleStatusKind.INVALID
    assert _event_count(session.lifecycle.decision_controller, "dice_reroll_declined") == 1
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="replay:phase17g:csm:daemonforge:fight:decline",
            initial_lifecycle_payload=initial_reroll_lifecycle_payload,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize(
    ("game_id", "attacker_datasheet_id", "choose_dark_pact", "expected_wound_roll"),
    [
        (
            "order56-daemonforge-other-roll-8-order64-2",
            army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
            True,
            5,
        ),
        (
            "order56-daemonforge-no-pact-8-order64-3",
            army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
            False,
            1,
        ),
        ("order56-daemonforge-other-unit-12-order64-20", "000004209", False, 1),
    ],
)
def test_defiler_daemonforge_does_not_offer_ineligible_wound_rerolls(
    game_id: str,
    attacker_datasheet_id: str,
    choose_dark_pact: bool,
    expected_wound_roll: int,
) -> None:
    if game_id == "order56-daemonforge-no-pact-8-order64-3":
        game_id = "order56-daemonforge-no-pact-8-order64-3:d07:31"
    if game_id == "order56-daemonforge-other-roll-8-order64-2":
        game_id = "order56-daemonforge-other-roll-8-order64-2:d07:19"
    if game_id == "order56-daemonforge-other-unit-12-order64-20":
        game_id = "order56-daemonforge-other-unit-12-order64-20:d07:14"
    declaration_result_ids = {
        "order56-daemonforge-no-pact-8-order64-3:d07:31": (
            "order56-daemonforge-no-pact-8-order64-3:d07:31:declaration:d07-vector:48"
        ),
        "order56-daemonforge-other-roll-8-order64-2:d07:19": (
            "order56-daemonforge-other-roll-8-order64-2:d07:19:declaration:d07-vector:72"
        ),
        "order56-daemonforge-other-unit-12-order64-20:d07:14": (
            "order56-daemonforge-other-unit-12-order64-20:d07:14:declaration:d07-vector:13"
        ),
    }
    session, status = _daemonforge_shooting_status(
        game_id=game_id,
        attacker_datasheet_id=attacker_datasheet_id,
        choose_dark_pact=choose_dark_pact,
        declaration_result_id=declaration_result_ids[game_id],
    )

    assert status.decision_request is None or (
        status.decision_request.decision_type != DICE_REROLL_DECISION_TYPE
    )
    assert not any(
        record.request.decision_type == DICE_REROLL_DECISION_TYPE
        for record in session.lifecycle.decision_controller.records
    )
    wound_steps = tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], event.payload)["step"] == "wound"
    )
    assert len(wound_steps) == 1
    wound_payload = cast(dict[str, JsonValue], wound_steps[0]["payload"])
    assert wound_payload["unmodified_roll"] == expected_wound_roll


def test_defiler_daemonforge_rejects_non_attack_phases_through_loaded_consumer() -> None:
    session, _status = _daemonforge_shooting_status(
        game_id="phase17g-csm-daemonforge-other-phase",
        attacker_datasheet_id=army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
        choose_dark_pact=True,
    )
    state = cast(GameState, session.lifecycle.state)
    attacker = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    profile = _catalog_weapon_profile(
        catalog=session.lifecycle.config.army_catalog,
        profile_id="000000969:excruciator-cannon:standard",
    )
    pool = _attack_pool(attacker=attacker, target=target, weapon_profile=profile)
    for source_phase in (BattlePhase.COMMAND, BattlePhase.MOVEMENT, BattlePhase.CHARGE):
        decisions = DecisionController()
        wound_roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_fixed(
            attack_sequence_wound_roll_spec(
                weapon_profile_id=profile.profile_id,
                attack_context_id=f"phase17g-csm-daemonforge-{source_phase.value}:attack-001",
                attacker_player_id="player-a",
            ),
            [1],
        )

        assert (
            _request_source_backed_wound_reroll_if_available(
                state=state,
                decisions=decisions,
                roll_state=wound_roll,
                pool=pool,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                attacker_keywords=attacker.keywords,
                attack_context_id=(f"phase17g-csm-daemonforge-{source_phase.value}:attack-001"),
                source_phase=source_phase,
                runtime_modifier_registry=_runtime_content_bundle(
                    session.lifecycle
                ).runtime_modifier_registry,
            )
            is None
        )
        assert not decisions.queue.pending_requests


def test_mortal_wound_feel_no_pain_continuation_registry_dispatches_by_source_kind() -> None:
    calls: list[str] = []
    expected_status = LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload={"handler": "dark-pacts-test"},
    )

    def matching_handler(
        context: MortalWoundFeelNoPainContinuationContext,
    ) -> LifecycleStatus:
        source_kind = cast(dict[str, JsonValue], context.source_context)["source_kind"]
        if type(source_kind) is not str:
            raise AssertionError("Expected source_kind string.")
        calls.append(source_kind)
        return expected_status

    def none_handler(_: MortalWoundFeelNoPainContinuationContext) -> None:
        return None

    registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        (
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id="dark-pacts-test:z",
                source_id="dark-pacts-test:z-source",
                source_kind="dark-pacts-test:z-kind",
                handler=matching_handler,
            ),
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id="dark-pacts-test:a",
                source_id="dark-pacts-test:a-source",
                source_kind="dark-pacts-test:a-kind",
                handler=none_handler,
            ),
        )
    )

    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        "dark-pacts-test:a",
        "dark-pacts-test:z",
    )
    assert registry.handles_source_context({"source_kind": " dark-pacts-test:z-kind "})
    assert (
        registry.apply_decision(
            _mortal_wound_fnp_continuation_context(source_kind="dark-pacts-test:z-kind")
        )
        == expected_status
    )
    assert calls == ["dark-pacts-test:z-kind"]
    assert (
        registry.apply_decision(
            _mortal_wound_fnp_continuation_context(source_kind="dark-pacts-test:a-kind")
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="source kind is not registered"):
        registry.apply_decision(
            _mortal_wound_fnp_continuation_context(source_kind="dark-pacts-test:missing-kind")
        )


def test_mortal_wound_feel_no_pain_continuation_hooks_are_fail_fast() -> None:
    valid_binding = MortalWoundFeelNoPainContinuationHookBinding(
        hook_id="dark-pacts-test:hook",
        source_id="dark-pacts-test:source",
        source_kind="dark-pacts-test:kind",
        handler=lambda _: None,
    )
    context = _mortal_wound_fnp_continuation_context(source_kind="dark-pacts-test:kind")

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        MortalWoundFeelNoPainContinuationContext(
            state=cast(GameState, object()),
            decisions=context.decisions,
            request=context.request,
            result=context.result,
            source_context=context.source_context,
            dice_manager=context.dice_manager,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    with pytest.raises(GameLifecycleError, match="requires DecisionController"):
        MortalWoundFeelNoPainContinuationContext(
            state=context.state,
            decisions=cast(DecisionController, object()),
            request=context.request,
            result=context.result,
            source_context=context.source_context,
            dice_manager=context.dice_manager,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    with pytest.raises(GameLifecycleError, match="requires request"):
        MortalWoundFeelNoPainContinuationContext(
            state=context.state,
            decisions=context.decisions,
            request=cast(DecisionRequest, object()),
            result=context.result,
            source_context=context.source_context,
            dice_manager=context.dice_manager,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    with pytest.raises(GameLifecycleError, match="requires result"):
        MortalWoundFeelNoPainContinuationContext(
            state=context.state,
            decisions=context.decisions,
            request=context.request,
            result=cast(DecisionResult, object()),
            source_context=context.source_context,
            dice_manager=context.dice_manager,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    with pytest.raises(GameLifecycleError, match="requires dice manager"):
        MortalWoundFeelNoPainContinuationContext(
            state=context.state,
            decisions=context.decisions,
            request=context.request,
            result=context.result,
            source_context=context.source_context,
            dice_manager=cast(DiceRollManager, object()),
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    with pytest.raises(GameLifecycleError, match="requires runtime modifier registry"):
        MortalWoundFeelNoPainContinuationContext(
            state=context.state,
            decisions=context.decisions,
            request=context.request,
            result=context.result,
            source_context=context.source_context,
            dice_manager=context.dice_manager,
            runtime_modifier_registry=cast(RuntimeModifierRegistry, object()),
        )
    with pytest.raises(GameLifecycleError, match="hook hook_id must be a string"):
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id=cast(str, 1),
            source_id="dark-pacts-test:source",
            source_kind="dark-pacts-test:kind",
            handler=lambda _: None,
        )
    with pytest.raises(GameLifecycleError, match="hook source_id must not be empty"):
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id="dark-pacts-test:hook",
            source_id=" ",
            source_kind="dark-pacts-test:kind",
            handler=lambda _: None,
        )
    with pytest.raises(GameLifecycleError, match="handler is not callable"):
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id="dark-pacts-test:hook",
            source_id="dark-pacts-test:source",
            source_kind="dark-pacts-test:kind",
            handler=cast(MortalWoundFeelNoPainContinuationHandler, object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        MortalWoundFeelNoPainContinuationHookRegistry(
            bindings=cast(tuple[MortalWoundFeelNoPainContinuationHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="bindings must contain"):
        MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            cast(tuple[MortalWoundFeelNoPainContinuationHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        MortalWoundFeelNoPainContinuationHookRegistry.from_bindings((valid_binding, valid_binding))
    with pytest.raises(GameLifecycleError, match="source kinds must be unique"):
        MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            (
                valid_binding,
                MortalWoundFeelNoPainContinuationHookBinding(
                    hook_id="dark-pacts-test:other-hook",
                    source_id="dark-pacts-test:other-source",
                    source_kind=valid_binding.source_kind,
                    handler=lambda _: None,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source context must be an object"):
        MortalWoundFeelNoPainContinuationHookRegistry.empty().handles_source_context(
            "dark-pacts-test:kind"
        )
    with pytest.raises(GameLifecycleError, match="source context is missing source_kind"):
        _mortal_wound_fnp_continuation_context(source_context={})
    with pytest.raises(GameLifecycleError, match="requires context"):
        MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            (valid_binding,)
        ).apply_decision(cast(MortalWoundFeelNoPainContinuationContext, object()))

    def wrong_return(_: MortalWoundFeelNoPainContinuationContext) -> LifecycleStatus:
        return cast(LifecycleStatus, object())

    with pytest.raises(GameLifecycleError, match="handlers must return status or None"):
        MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            (
                MortalWoundFeelNoPainContinuationHookBinding(
                    hook_id="dark-pacts-test:wrong-return",
                    source_id="dark-pacts-test:wrong-return-source",
                    source_kind="dark-pacts-test:kind",
                    handler=wrong_return,
                ),
            )
        ).apply_decision(context)


def test_dark_pacts_shooting_decision_records_effect_and_grants_lethal_hits() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    selection = _shooting_selection(state, unit)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    decisions = DecisionController()
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )

    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status.decision_request)
    assert request.decision_type == "select_shooting_unit_grant"
    assert {option.option_id for option in request.options} == {
        "decline_shooting_unit_grant",
        f"{army_rule.SOURCE_RULE_ID}:commit",
    }
    engine = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=army_rule.runtime_contribution().weapon_profile_modifier_bindings
    )
    result = DecisionResult.for_request(
        result_id="commit-dark-pact",
        request=request,
        selected_option_id=f"{army_rule.SOURCE_RULE_ID}:commit",
    )
    decisions.submit_result(result)
    choice = _apply_shooting_unit_selected_grant_decision(
        state=state,
        decisions=decisions,
        result=result,
        registry=registry,
        runtime_modifier_registry=engine,
    )
    assert choice is not None
    request = _decision_request(choice.decision_request)
    assert {option.option_id for option in request.options} == {
        army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
    }
    lethal_option = _option_payload(request, army_rule.SHOOTING_LETHAL_HITS_HOOK_ID)
    selected_grants = cast(
        list[dict[str, JsonValue]],
        lethal_option["selected_shooting_unit_grants"],
    )
    effect_payload = cast(dict[str, JsonValue], selected_grants[0]["unit_effect_payload"])
    assert effect_payload["selected_dark_pact"] == army_rule.DarkPactKind.LETHAL_HITS.value
    assert effect_payload["phase"] == BattlePhase.SHOOTING.value

    result = DecisionResult.for_request(
        result_id="dark-pact-shooting-result",
        request=request,
        selected_option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    _apply_shooting_unit_selected_grant_decision(
        runtime_modifier_registry=RuntimeModifierRegistry.from_bindings(
            weapon_profile_modifier_bindings=army_rule.runtime_contribution().weapon_profile_modifier_bindings
        ),
        state=state,
        result=result,
        decisions=decisions,
        registry=registry,
    )

    assert (
        army_rule.active_dark_pact_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is army_rule.DarkPactKind.LETHAL_HITS
    )
    modified = army_rule.dark_pact_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=_weapon_profile(melee=False),
        )
    )
    assert WeaponKeyword.LETHAL_HITS in modified.keywords


def test_dark_pacts_out_of_phase_shooting_requests_grant_before_declaration() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    assert state.battlefield_state is not None
    for placed_unit, x in ((unit, 10.0), (target, 20.0)):
        placement = state.battlefield_state.unit_placement_by_id(placed_unit.unit_instance_id)
        state.replace_battlefield_state(
            state.battlefield_state.with_unit_placement(
                replace(
                    placement,
                    model_placements=tuple(
                        replace(model, pose=Pose.at(x, 10.0 + index * 1.8))
                        for index, model in enumerate(placement.model_placements)
                    ),
                )
            )
        )
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    contribution = army_rule.runtime_contribution()
    grant_registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        contribution.shooting_unit_selected_grant_hook_bindings
    )

    grant_status = request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-csm-out-of-phase"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id=FIRE_OVERWATCH_RULE_ID,
        source_decision_request_id="fire-overwatch-target-request",
        source_decision_result_id="fire-overwatch-target-result",
        source_context={
            "source_kind": "fire_overwatch",
            "triggering_enemy_unit_instance_id": target.unit_instance_id,
        },
        target_unit_ids=(target.unit_instance_id,),
        shooting_unit_selected_grant_hooks=grant_registry,
    )
    request = _decision_request(grant_status.decision_request)

    assert request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.target_unit_ids == (target.unit_instance_id,)

    handler = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-csm-out-of-phase"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        shooting_unit_selected_grant_hooks=grant_registry,
    )
    result = DecisionResult.for_request(
        result_id="commit-overwatch-pact",
        request=request,
        selected_option_id=f"{army_rule.SOURCE_RULE_ID}:commit",
    )
    decisions.submit_result(result)
    choice = handler.apply_decision(state=state, result=result, decisions=decisions)
    assert choice is not None
    request = _decision_request(choice.decision_request)
    result = DecisionResult.for_request(
        result_id="fire-overwatch-dark-pact-result",
        request=request,
        selected_option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    declaration_status = handler.apply_decision(state=state, result=result, decisions=decisions)
    declaration_request = _decision_request(
        None if declaration_status is None else declaration_status.decision_request
    )

    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    assert (
        army_rule.active_dark_pact_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is army_rule.DarkPactKind.LETHAL_HITS
    )
    assert state.out_of_phase_shooting_state is not None
    assert not state.out_of_phase_shooting_state.grant_effect_ids


def test_dark_pacts_fight_grant_and_melee_profile_add_sustained_hits() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    activation = _fight_activation(state, unit)
    grants = registry.grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type=activation.fight_type.value,
            ordering_band=activation.ordering_band.value,
            request_id=activation.request_id,
            result_id=activation.result_id,
        )
    )

    assert {grant.hook_id for grant in grants} == {
        army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.FIGHT,
        pact=army_rule.DarkPactKind.SUSTAINED_HITS_1,
    )
    modified = army_rule.dark_pact_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=_weapon_profile(melee=True),
        )
    )

    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert any(ability.ability_id == "sustained-hits:1" for ability in modified.abilities)


def _daemonforge_fight_status(
    *, game_id: str, declaration_result_id: str | None = None
) -> tuple[LocalGameSession, LifecycleStatus]:
    catalog = _daemonforge_catalog()
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("defiler-attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "defiler-attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id=game_id,
        alpha_unit_specs={
            "defiler-attacker": (
                army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
                f"{army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID}:defiler",
                1,
            )
        },
        enemy_unit_specs={"enemy": ("000004209", "000004209:defiler", 1)},
        catalog=catalog,
        alpha_faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
        alpha_detachment_ids=("pactbound-zealots",),
        enemy_faction_id="death-guard",
        enemy_detachment_ids=("champions-of-contagion",),
    )
    bundle = _runtime_content_bundle(lifecycle)
    assert (
        army_rule.DEFILER_DAEMONFORGE_WOUND_REROLL_MODIFIER_ID
        in bundle.to_summary_payload()["attack_reroll_permission_modifier_ids"]
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = _drain_daemonforge_fight_movement_requests(
        session=session,
        status=session.advance_until_decision_or_terminal(),
        result_id_prefix=game_id,
    )
    activation_request = _decision_request(status.decision_request)
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=fight_activation_option_id(
            unit_instance_id=units["defiler-attacker"].unit_instance_id,
            fight_type=FightTypeKind.NORMAL,
        ),
        result_id=f"{game_id}:select-fight-activation",
    )
    grant_request = _decision_request(status.decision_request)
    assert grant_request.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE
    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=f"{army_rule.SOURCE_RULE_ID}:commit",
        result_id=f"{game_id}:dark-pact-commit",
    )
    grant_request = _decision_request(status.decision_request)
    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        result_id=f"{game_id}:dark-pact",
    )
    status = _drain_daemonforge_fight_movement_requests(
        session=session,
        status=status,
        result_id_prefix=game_id,
    )
    declaration_request = _decision_request(status.decision_request)
    assert declaration_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    return session, session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=_daemonforge_melee_declaration_payload(
            request=declaration_request,
            target_unit_instance_id=units["enemy"].unit_instance_id,
        ),
        result_id=f"{game_id}:melee-declaration"
        if declaration_result_id is None
        else declaration_result_id,
    )


def _drain_daemonforge_fight_movement_requests(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    result_id_prefix: str,
) -> LifecycleStatus:
    current = status
    movement_number = 1
    while (
        current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        context = cast(dict[str, JsonValue], proposal.context)
        current = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal.request_id,
                    "proposal_kind": proposal.proposal_kind.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "movement_phase_action": proposal.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                },
            ),
            result_id=f"{result_id_prefix}:fight-no-move:{movement_number}",
        )
        movement_number += 1
    return current


def _daemonforge_melee_declaration_payload(
    *,
    request: DecisionRequest,
    target_unit_instance_id: str,
) -> JsonValue:
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    weapon = next(
        cast(dict[str, JsonValue], available_weapon)
        for available_weapon in proposal.available_weapons
        if cast(dict[str, JsonValue], available_weapon)["weapon_profile_id"]
        == "000000969:shearing-claws:strike"
    )
    return cast(
        JsonValue,
        {
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind,
            "player_id": proposal.actor_id,
            "battle_round": proposal.battle_round,
            "unit_instance_id": proposal.unit_instance_id,
            "source_decision_request_id": proposal.source_decision_request_id,
            "source_decision_result_id": proposal.source_decision_result_id,
            "declarations": [
                {
                    "attacker_model_instance_id": weapon["model_instance_id"],
                    "wargear_id": weapon["wargear_id"],
                    "weapon_profile_id": weapon["weapon_profile_id"],
                    "target_allocations": [{"target_unit_instance_id": target_unit_instance_id}],
                }
            ],
        },
    )


def _daemonforge_shooting_status(
    *,
    game_id: str,
    attacker_datasheet_id: str,
    choose_dark_pact: bool,
    declaration_result_id: str | None = None,
) -> tuple[LocalGameSession, LifecycleStatus]:
    catalog = _daemonforge_catalog()
    attacker_is_csm = attacker_datasheet_id == army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID
    attacker_model_profile_id = f"{attacker_datasheet_id}:defiler"
    target_datasheet_id = "000004209" if attacker_is_csm else "000000969"
    lifecycle, units = shooting_lifecycle(
        alpha_unit_ids=("defiler-attacker",),
        game_id=game_id,
        alpha_unit_specs=(
            (
                "defiler-attacker",
                attacker_datasheet_id,
                attacker_model_profile_id,
                1,
            ),
        ),
        enemy_datasheet=(target_datasheet_id, f"{target_datasheet_id}:defiler", 1),
        catalog=catalog,
        alpha_faction_id=(CHAOS_SPACE_MARINES_FACTION_ID if attacker_is_csm else "death-guard"),
        alpha_detachment_ids=(
            ("pactbound-zealots",) if attacker_is_csm else ("champions-of-contagion",)
        ),
        enemy_faction_id=("death-guard" if attacker_is_csm else CHAOS_SPACE_MARINES_FACTION_ID),
        enemy_detachment_ids=(
            ("champions-of-contagion",) if attacker_is_csm else ("pactbound-zealots",)
        ),
    )
    bundle = _runtime_content_bundle(lifecycle)
    assert (
        army_rule.DEFILER_DAEMONFORGE_WOUND_REROLL_MODIFIER_ID
        in (bundle.to_summary_payload()["attack_reroll_permission_modifier_ids"])
    )
    session = LocalGameSession(lifecycle=lifecycle)
    selection_request = _decision_request(
        session.advance_until_decision_or_terminal().decision_request
    )
    assert selection_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=units["defiler-attacker"].unit_instance_id,
        result_id=f"{game_id}:select-attacker",
    )
    request = _decision_request(status.decision_request)
    if attacker_is_csm:
        assert request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
        status = session.submit_option(
            request_id=request.request_id,
            option_id=(
                f"{army_rule.SOURCE_RULE_ID}:commit"
                if choose_dark_pact
                else DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID
            ),
            result_id=f"{game_id}:dark-pact-commit",
        )
        request = _decision_request(status.decision_request)
        if choose_dark_pact:
            status = session.submit_option(
                request_id=request.request_id,
                option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
                result_id=f"{game_id}:dark-pact",
            )
            request = _decision_request(status.decision_request)
    assert request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    status = session.submit_option(
        request_id=request.request_id,
        option_id=ShootingType.NORMAL.value,
        result_id=f"{game_id}:shooting-type",
    )
    declaration_request = _decision_request(status.decision_request)
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=(
            "000000969:excruciator-cannon:standard"
            if attacker_is_csm
            else "000004209:excruciator-cannon:standard"
        ),
    )
    return session, session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=cast(JsonValue, proposal.to_payload()),
        result_id=f"{game_id}:declaration"
        if declaration_result_id is None
        else declaration_result_id,
    )


@lru_cache(maxsize=1)
def _daemonforge_catalog() -> ArmyCatalog:
    source_catalog = july_defiler_catalog_package().army_catalog
    factions = tuple(
        replace(
            faction,
            faction_id=(
                CHAOS_SPACE_MARINES_FACTION_ID if faction.faction_id == "CSM" else "death-guard"
            ),
        )
        if faction.faction_id in {"CSM", "DG"}
        else faction
        for faction in source_catalog.factions
    )
    detachments = (
        DetachmentDefinition(
            canonical_detachment_id="pactbound-zealots",
            detachment_id="pactbound-zealots",
            name="Pactbound Zealots",
            faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
            detachment_point_cost=1,
            unit_datasheet_ids=(army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,),
            force_disposition_ids=("purge-the-foe",),
            source_ids=("test:daemonforge:pactbound-zealots",),
        ),
        DetachmentDefinition(
            canonical_detachment_id="champions-of-contagion",
            detachment_id="champions-of-contagion",
            name="Champions of Contagion",
            faction_id="death-guard",
            detachment_point_cost=1,
            unit_datasheet_ids=("000004209",),
            force_disposition_ids=("purge-the-foe",),
            source_ids=("test:daemonforge:champions-of-contagion",),
        ),
    )
    wargear = tuple(
        replace(
            item,
            weapon_profiles=tuple(
                replace(profile, attack_profile=AttackProfile.fixed(1))
                if profile.profile_id
                in {
                    "000000969:excruciator-cannon:standard",
                    "000000969:shearing-claws:strike",
                    "000004209:excruciator-cannon:standard",
                }
                else profile
                for profile in item.weapon_profiles
            ),
        )
        for item in source_catalog.wargear
    )
    return replace(
        source_catalog,
        factions=factions,
        detachments=detachments,
        wargear=wargear,
    )


def _catalog_weapon_profile(*, catalog: ArmyCatalog, profile_id: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        for profile in wargear.weapon_profiles:
            if profile.profile_id == profile_id:
                return profile
    raise AssertionError(f"Missing catalog weapon profile {profile_id}.")


def _runtime_content_bundle(lifecycle: object) -> RuntimeContentBundle:
    require_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_bundle()


def _csm_battle_state(*, game_id: str = "phase11c-game") -> GameState:
    state = battle_state(game_id=game_id)
    _mark_player_as_chaos_space_marines(state, player_id="player-a")
    return state


def _mark_player_as_chaos_space_marines(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
                ),
                units=tuple(
                    with_unit_keywords(unit, faction_keywords=("Heretic Astartes",))
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _replace_first_unit_with_csm_defiler(
    state: GameState,
    *,
    player_id: str,
) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    defiler = instantiate_defiler(
        package=july_defiler_catalog_package(),
        datasheet_id=army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID,
        army_id=army.army_id,
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(replace(army, units=(defiler, *army.units[1:])))
    state.army_definitions = updated_armies
    return defiler


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _shooting_selection(state: GameState, unit: UnitInstance) -> ShootingUnitSelection:
    return ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="select-shooting-unit-request",
        result_id="select-shooting-unit-result",
    )


def _fight_activation(state: GameState, unit: UnitInstance) -> FightActivationSelection:
    return FightActivationSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="fight-activation-request",
        result_id="fight-activation-result",
    )


def _record_dark_pact_effect(
    state: GameState,
    *,
    unit: UnitInstance,
    phase: BattlePhase,
    pact: army_rule.DarkPactKind,
) -> None:
    phase_kind = (
        BattlePhaseKind.SHOOTING if phase is BattlePhase.SHOOTING else BattlePhaseKind.FIGHT
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"test-dark-pact:{phase.value}:{pact.value}:{unit.unit_instance_id}",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=army_rule.dark_pact_target_unit_ids(
                state,
                unit_instance_id=unit.unit_instance_id,
            ),
            started_battle_round=state.battle_round,
            started_phase=phase_kind,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=phase_kind,
                player_id="player-a",
            ),
            effect_payload=army_rule.dark_pact_effect_payload(
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=army_rule.dark_pact_target_unit_ids(
                    state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                trigger="test",
                phase=phase,
                selected_dark_pact=pact,
                source_context={"test": True},
            ),
        )
    )


def _weapon_profile(*, melee: bool) -> WeaponProfile:
    return WeaponProfile(
        profile_id="test-melee-profile" if melee else "test-ranged-profile",
        name="Test melee weapon" if melee else "Test ranged weapon",
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            3,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("test-profile",),
    )


def _attack_pool(
    *,
    attacker: UnitInstance,
    target: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_instance_id=f"weapon-instance:test:{weapon_profile.profile_id}",
        wargear_id="test-wargear",
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=(target.own_models[0].model_instance_id,),
        target_in_range_model_ids=(target.own_models[0].model_instance_id,),
    )


def _option_payload(request: DecisionRequest, option_id: str) -> dict[str, JsonValue]:
    for option in request.options:
        if option.option_id == option_id:
            return cast(dict[str, JsonValue], option.payload)
    raise AssertionError(f"Missing option {option_id}.")


def _decision_request(request: DecisionRequest | None) -> DecisionRequest:
    if request is None:
        raise AssertionError("Expected decision request.")
    return request


def _mortal_wound_fnp_continuation_context(
    *,
    source_kind: str = "dark-pacts-test:kind",
    source_context: JsonValue | None = None,
) -> MortalWoundFeelNoPainContinuationContext:
    state = _csm_battle_state()
    decisions = DecisionController()
    default_source_context: dict[str, JsonValue] = {"source_kind": source_kind}
    resolved_source_context: JsonValue = (
        default_source_context if source_context is None else source_context
    )
    payload: dict[str, JsonValue] = {"source_context": resolved_source_context}
    request = DecisionRequest(
        request_id="dark-pacts-test:fnp-request",
        decision_type="select_feel_no_pain",
        actor_id="player-a",
        payload=payload,
        options=(
            DecisionOption(
                option_id="dark-pacts-test:fnp-source",
                label="Dark Pacts Test FNP Source",
                payload=payload,
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id="dark-pacts-test:fnp-result",
        request=request,
        selected_option_id="dark-pacts-test:fnp-source",
    )
    return MortalWoundFeelNoPainContinuationContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        source_context=resolved_source_context,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )


def _event_count(decisions: DecisionController, event_type: str) -> int:
    return sum(1 for event in decisions.event_log.records if event.event_type == event_type)
