from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
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
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHandler,
    AttackSequenceCompletedHookBinding,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
    feel_no_pain_roll_spec,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.fight_unit_selected_hooks import (
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
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
    _apply_shooting_unit_selected_grant_decision,  # pyright: ignore[reportPrivateUsage]
    _request_shooting_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


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


def test_attack_sequence_completed_hook_registry_is_ordered_and_fail_fast() -> None:
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
    assert registry.resolve_completed_sequence(context) is expected_status
    assert seen_hooks == ["a", "b"]
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
    with pytest.raises(GameLifecycleError, match="must return status or None"):
        AttackSequenceCompletedHookRegistry.from_bindings(
            (
                AttackSequenceCompletedHookBinding(
                    hook_id="bad-status",
                    source_id="test-source",
                    handler=lambda _context: cast(LifecycleStatus, "bad-status"),
                ),
            )
        ).resolve_completed_sequence(context)
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
    assert (
        contribution.attack_sequence_completed_hook_bindings[0].hook_id
        == army_rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    )
    assert (
        contribution.mortal_wound_feel_no_pain_hook_bindings[0].hook_id
        == army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID
    )
    assert (
        contribution.weapon_profile_modifier_bindings[0].modifier_id
        == army_rule.WEAPON_PROFILE_MODIFIER_ID
    )


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

    result = DecisionResult.for_request(
        result_id="fire-overwatch-dark-pact-result",
        request=request,
        selected_option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    declaration_status = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-csm-out-of-phase"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        shooting_unit_selected_grant_hooks=grant_registry,
    ).apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )
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
    assert state.out_of_phase_shooting_state.grant_effect_ids


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


def test_dark_pacts_failed_leadership_test_applies_d3_mortal_wounds() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.SHOOTING,
        pact=army_rule.DarkPactKind.LETHAL_HITS,
    )
    decisions = DecisionController()
    attack_sequence = AttackSequence(
        sequence_id="dark-pact-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_pools=(
            _attack_pool(
                attacker=unit,
                target=target,
                weapon_profile=_weapon_profile(melee=False),
            ),
        ),
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=(0,),
        pool_index=1,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="dark-pact-leadership-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=2, sides=6),
                    reason=f"Dark Pact Leadership test for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_LEADERSHIP_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1, 1),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="dark-pact-mortal-wounds-roll",
                spec=DiceRollManager.d3_source_spec(
                    reason=f"Dark Pact mortal wounds for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(5,),
                source="fixed",
            ),
        ),
    )
    starting_wounds = sum(model.wounds_remaining for model in unit.own_models)

    army_rule.resolve_dark_pact_attack_sequence_completion(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=attack_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )

    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["passed"] is False
    assert cast(dict[str, JsonValue], payload["d3_result"])["value"] == 3
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 3
    refreshed_unit = _unit_for_player(state, player_id="player-a")
    ending_wounds = sum(model.wounds_remaining for model in refreshed_unit.own_models)
    assert starting_wounds - ending_wounds == 3


def test_dark_pacts_failed_leadership_mortal_wounds_route_feel_no_pain_choice() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.SHOOTING,
        pact=army_rule.DarkPactKind.LETHAL_HITS,
    )
    source_a = FeelNoPainSource(source_id="dark-pact-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="dark-pact-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=unit.own_models[0].model_instance_id,
        sources=(source_a, source_b),
    )
    decisions = DecisionController()
    attack_sequence = AttackSequence(
        sequence_id="dark-pact-fnp-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_pools=(
            _attack_pool(
                attacker=unit,
                target=target,
                weapon_profile=_weapon_profile(melee=False),
            ),
        ),
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=(0,),
        pool_index=1,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="dark-pact-fnp-leadership-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=2, sides=6),
                    reason=f"Dark Pact Leadership test for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_LEADERSHIP_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1, 1),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="dark-pact-fnp-mortal-wounds-roll",
                spec=DiceRollManager.d3_source_spec(
                    reason=f"Dark Pact mortal wounds for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1,),
                source="fixed",
            ),
        ),
    )
    starting_wounds = sum(model.wounds_remaining for model in unit.own_models)

    status = army_rule.resolve_dark_pact_attack_sequence_completion(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=attack_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )
    request = _decision_request(None if status is None else status.decision_request)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert is_mortal_wound_feel_no_pain_request(request)
    source_context = mortal_wound_feel_no_pain_source_context(request)
    assert isinstance(source_context, dict)
    assert source_context["source_kind"] == army_rule.DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND
    assert {option.option_id for option in request.options} == {
        source_a.source_id,
        source_b.source_id,
    }
    assert not _has_event(decisions, "chaos_space_marines_dark_pact_resolved")
    assert (
        sum(
            model.wounds_remaining
            for model in _unit_for_player(state, player_id="player-a").own_models
        )
        == starting_wounds
    )

    result = DecisionResult.for_request(
        result_id="dark-pact-fnp-source-a",
        request=request,
        selected_option_id=source_a.source_id,
    )
    decisions.submit_result(result)
    continuation_status = army_rule.apply_dark_pact_mortal_wound_feel_no_pain_decision(
        MortalWoundFeelNoPainContinuationContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_context=source_context,
            dice_manager=DiceRollManager(
                state.game_id,
                event_log=decisions.event_log,
                injected_results=(
                    DiceRollResult.from_values(
                        roll_id="dark-pact-fnp-roll",
                        spec=feel_no_pain_roll_spec(
                            source=source_a,
                            player_id="player-a",
                            model_instance_id=unit.own_models[0].model_instance_id,
                            wound_index=1,
                        ),
                        values=(1,),
                        source="fixed",
                    ),
                ),
            ),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert continuation_status is None
    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["feel_no_pain_result_id"] == result.result_id
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 1
    assert (
        starting_wounds
        - sum(
            model.wounds_remaining
            for model in _unit_for_player(state, player_id="player-a").own_models
        )
        == 1
    )


def test_dark_pacts_completion_hook_runs_once_through_shooting_phase_handler() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.SHOOTING,
        pact=army_rule.DarkPactKind.SUSTAINED_HITS_1,
    )
    decisions = DecisionController()
    attack_pool = _attack_pool(
        attacker=unit,
        target=target,
        weapon_profile=_weapon_profile(melee=False),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(unit.unit_instance_id,),
        shot_unit_ids=(unit.unit_instance_id,),
        attack_pools=(attack_pool,),
        attack_sequence=AttackSequence(
            sequence_id="dark-pact-handler-completed-sequence",
            attacker_player_id="player-a",
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_pools=(attack_pool,),
            source_phase=BattlePhase.SHOOTING,
            used_pool_indices=(0,),
            pool_index=1,
        ),
    )
    contribution = army_rule.runtime_contribution()
    handler = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-csm-handler"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        attack_sequence_completed_hooks=AttackSequenceCompletedHookRegistry.from_bindings(
            contribution.attack_sequence_completed_hook_bindings
        ),
    )

    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert _event_count(decisions, "chaos_space_marines_dark_pact_resolved") == 1
    assert _event_count(decisions, "attack_sequence_completed") == 1
    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert payload["hook_id"] == army_rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    handler.begin_phase(state=state, decisions=decisions)
    assert _event_count(decisions, "chaos_space_marines_dark_pact_resolved") == 1


def _csm_battle_state() -> GameState:
    state = _battle_state()
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
                    replace(unit, faction_keywords=("Heretic Astartes",)) for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


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


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event {event_type}.")


def _has_event(decisions: DecisionController, event_type: str) -> bool:
    return any(event.event_type == event_type for event in decisions.event_log.records)


def _event_count(decisions: DecisionController, event_type: str) -> int:
    return sum(1 for event in decisions.event_log.records if event.event_type == event_type)
