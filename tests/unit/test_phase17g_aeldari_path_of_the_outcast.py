from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectBinding,
    EnhancementEffectContext,
    EnhancementEffectRegistry,
    EnhancementPersistingEffectGrant,
    apply_enhancement_effects,
)
from warhammer40k_core.engine.faction_content.activation import (
    RuntimeContentActivation,
    RuntimeEnhancementAssignment,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerContext,
    StratagemHandlerExecutionStatus,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.path_of_the_outcast import (  # noqa: E501
    enhancements,
    manifest,
    rule,
    stratagems,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phases.shooting import (
    apply_hidden_status_loss_after_ranged_attacks,
)
from warhammer40k_core.engine.ranged_rule_effects import (
    character_target_ap_bonus_payload,
    detection_range_bonus_inches_for_effects,
    detection_range_bonus_payload,
    unit_hidden_payload,
    unit_is_hidden_by_effects,
    weapon_profile_with_character_target_ap_effects,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedEffectGrant,
    ShootingUnitSelectedHookBinding,
    ShootingUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.stratagems import (
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    HIT_ENEMY_UNIT_CONTEXT_KEY,
    HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    HIT_TARGET_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemUseRecord,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose

_RANGERS_UNIT_ID = "army-a:rangers"
_SHROUD_RUNNERS_UNIT_ID = "army-a:shroud-runners"
_ENEMY_UNIT_ID = "army-b:target"


def test_path_of_the_outcast_runtime_contribution_registers_content() -> None:
    contribution = manifest.runtime_contribution()

    assert contribution.contribution_id.endswith("path_of_the_outcast:manifest:scaffold")
    assert {record.definition.stratagem_id for record in contribution.stratagem_records} == {
        stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
    }
    assert {record.definition.handler_id for record in contribution.stratagem_records} == {
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    }
    assert all(
        isinstance(record.definition.effect_payload, dict)
        and isinstance(record.definition.effect_payload.get("rule_ir"), dict)
        for record in contribution.stratagem_records
    )
    assert contribution.stratagem_handler_bindings == ()
    assert contribution.enhancement_effect_bindings == ()
    assert {binding.hook_id for binding in contribution.shooting_unit_selected_hook_bindings} == {
        rule.FAR_REACHING_DOOM_HOOK_ID,
    }


def test_path_of_the_outcast_generic_runtime_bundle_materializes_upgrade_hooks() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state(
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                target_unit_selection_id="rangers",
                source_id="assignment:camouflaged-snipers",
            ),
            EnhancementAssignment(
                enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
                target_unit_selection_id="shroud-runners",
                source_id="assignment:assassins-eye",
            ),
        )
    )
    bindings = _path_runtime_bundle(state).enhancement_effect_registry.all_bindings()

    assert {
        (binding.effect_id, binding.source_id, binding.enhancement_id)
        for binding in bindings
        if binding.enhancement_id
        in {
            enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
        }
    } == {
        (
            enhancements.CAMOUFLAGED_SNIPERS_EFFECT_ID,
            enhancements.CAMOUFLAGED_SNIPERS_SOURCE_RULE_ID,
            enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
        ),
        (
            enhancements.ASSASSINS_EYE_EFFECT_ID,
            enhancements.ASSASSINS_EYE_SOURCE_RULE_ID,
            enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
        ),
    }


def test_far_reaching_doom_selection_hook_grants_detection_effect() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    registry = ShootingUnitSelectedHookRegistry.from_bindings(
        manifest.runtime_contribution().shooting_unit_selected_hook_bindings
    )
    context = ShootingUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_RANGERS_UNIT_ID,
        request_id="request:selected-rangers",
        result_id="result:selected-rangers",
    )

    grants = registry.grants_for(context)

    assert len(grants) == 1
    grant = grants[0]
    assert grant.hook_id == rule.FAR_REACHING_DOOM_HOOK_ID
    assert grant.event_type == "far_reaching_doom_detection_range_granted"
    assert grant.persisting_effect.target_unit_instance_ids == (_ENEMY_UNIT_ID,)
    payload = _json_object(grant.persisting_effect.effect_payload)
    assert payload["effect_kind"] == "detection_range_bonus"
    assert payload["bonus_inches"] == 6
    assert payload["source_unit_instance_id"] == _RANGERS_UNIT_ID
    assert payload["expires_when_source_unit_has_shot"] is True
    assert grant.to_payload()["hook_id"] == rule.FAR_REACHING_DOOM_HOOK_ID


def test_shooting_unit_selected_hook_registry_rejects_malformed_handlers() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    context = ShootingUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_RANGERS_UNIT_ID,
        request_id="request:selected-rangers",
        result_id="result:selected-rangers",
    )
    valid_grant = rule.apply_far_reaching_doom(context)[0]
    valid_binding = ShootingUnitSelectedHookBinding(
        hook_id="hook:valid",
        source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
        handler=lambda _context: (
            ShootingUnitSelectedEffectGrant(
                hook_id="hook:valid",
                source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
                unit_instance_id=_RANGERS_UNIT_ID,
                persisting_effect=replace(
                    valid_grant.persisting_effect,
                    effect_id="effect:valid",
                ),
            ),
        ),
    )

    assert ShootingUnitSelectedHookRegistry.empty().all_bindings() == ()
    assert ShootingUnitSelectedHookRegistry.from_bindings((valid_binding,)).grants_for(context)

    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        ShootingUnitSelectedHookRegistry(
            bindings=cast(tuple[ShootingUnitSelectedHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        ShootingUnitSelectedHookRegistry.from_bindings((valid_binding, valid_binding))
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        ShootingUnitSelectedHookBinding(
            hook_id="hook:not-callable",
            source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
            handler=cast(
                Callable[
                    [ShootingUnitSelectedContext], tuple[ShootingUnitSelectedEffectGrant, ...]
                ],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="handlers must return a tuple"):
        ShootingUnitSelectedHookRegistry.from_bindings(
            (
                ShootingUnitSelectedHookBinding(
                    hook_id="hook:list",
                    source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
                    handler=lambda _context: cast(
                        tuple[ShootingUnitSelectedEffectGrant, ...],
                        [],
                    ),
                ),
            )
        ).grants_for(context)
    with pytest.raises(GameLifecycleError, match="ShootingUnitSelectedEffectGrant values"):
        ShootingUnitSelectedHookRegistry.from_bindings(
            (
                ShootingUnitSelectedHookBinding(
                    hook_id="hook:object",
                    source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
                    handler=lambda _context: cast(
                        tuple[ShootingUnitSelectedEffectGrant, ...],
                        (object(),),
                    ),
                ),
            )
        ).grants_for(context)
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        ShootingUnitSelectedHookRegistry.from_bindings(
            (
                ShootingUnitSelectedHookBinding(
                    hook_id="hook:expected",
                    source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
                    handler=lambda _context: (
                        ShootingUnitSelectedEffectGrant(
                            hook_id="hook:actual",
                            source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
                            unit_instance_id=_RANGERS_UNIT_ID,
                            persisting_effect=replace(
                                valid_grant.persisting_effect,
                                effect_id="effect:drift",
                            ),
                        ),
                    ),
                ),
            )
        ).grants_for(context)


def test_shooting_unit_selected_hooks_reject_invalid_inputs() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    valid_context = ShootingUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_RANGERS_UNIT_ID,
        request_id="request:selected-rangers",
        result_id="result:selected-rangers",
    )
    valid_grant = rule.apply_far_reaching_doom(valid_context)[0]

    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        ShootingUnitSelectedContext(
            state=cast(GameState, object()),
            player_id="player-a",
            battle_round=1,
            unit_instance_id=_RANGERS_UNIT_ID,
            request_id="request:selected-rangers",
            result_id="result:selected-rangers",
        )

    movement_state, *_ = _path_state()
    movement_state.battle_phase_index = tuple(movement_state.battle_phase_sequence).index(
        BattlePhase.MOVEMENT
    )
    with pytest.raises(GameLifecycleError, match="requires the Shooting phase"):
        ShootingUnitSelectedContext(
            state=movement_state,
            player_id="player-a",
            battle_round=1,
            unit_instance_id=_RANGERS_UNIT_ID,
            request_id="request:selected-rangers",
            result_id="result:selected-rangers",
        )

    with pytest.raises(GameLifecycleError, match="battle_round must be an int"):
        ShootingUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=cast(int, "1"),
            unit_instance_id=_RANGERS_UNIT_ID,
            request_id="request:selected-rangers",
            result_id="result:selected-rangers",
        )
    with pytest.raises(GameLifecycleError, match="battle_round must be positive"):
        ShootingUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=0,
            unit_instance_id=_RANGERS_UNIT_ID,
            request_id="request:selected-rangers",
            result_id="result:selected-rangers",
        )

    with pytest.raises(GameLifecycleError, match="persisting_effect"):
        ShootingUnitSelectedEffectGrant(
            hook_id=rule.FAR_REACHING_DOOM_HOOK_ID,
            source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
            unit_instance_id=_RANGERS_UNIT_ID,
            persisting_effect=cast(PersistingEffect, object()),
        )
    with pytest.raises(GameLifecycleError, match="source_id must match"):
        ShootingUnitSelectedEffectGrant(
            hook_id=rule.FAR_REACHING_DOOM_HOOK_ID,
            source_id="source:other",
            unit_instance_id=_RANGERS_UNIT_ID,
            persisting_effect=valid_grant.persisting_effect,
        )
    with pytest.raises(GameLifecycleError, match="require a context"):
        ShootingUnitSelectedHookRegistry.empty().grants_for(
            cast(ShootingUnitSelectedContext, object())
        )
    with pytest.raises(GameLifecycleError, match="bindings must contain"):
        ShootingUnitSelectedHookRegistry(
            bindings=cast(tuple[ShootingUnitSelectedHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="hook_id must be a string"):
        ShootingUnitSelectedHookBinding(
            hook_id=cast(str, 123),
            source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
            handler=lambda _context: (),
        )
    with pytest.raises(GameLifecycleError, match="hook_id must not be empty"):
        ShootingUnitSelectedHookBinding(
            hook_id=" ",
            source_id=rule.FAR_REACHING_DOOM_SOURCE_RULE_ID,
            handler=lambda _context: (),
        )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        ShootingUnitSelectedHookRegistry.from_bindings(
            (
                ShootingUnitSelectedHookBinding(
                    hook_id="hook:source-drift",
                    source_id="source:expected",
                    handler=lambda _context: (
                        ShootingUnitSelectedEffectGrant(
                            hook_id="hook:source-drift",
                            source_id="source:actual",
                            unit_instance_id=_RANGERS_UNIT_ID,
                            persisting_effect=replace(
                                valid_grant.persisting_effect,
                                effect_id="effect:source-drift",
                                source_rule_id="source:actual",
                            ),
                        ),
                    ),
                ),
            )
        ).grants_for(valid_context)


def test_path_of_the_outcast_post_shot_records_use_structured_context() -> None:
    contribution = manifest.runtime_contribution()
    by_id = {record.definition.stratagem_id: record for record in contribution.stratagem_records}

    eldritch = by_id[stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID].definition
    casting = by_id[stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID].definition
    nomads = by_id[stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID].definition

    assert eldritch.target_spec.target_policy_id == "just_shot_unit"
    assert casting.target_spec.target_policy_id == "just_shot_unit"
    assert nomads.target_spec.target_policy_id == "just_shot_unit"
    assert eldritch.target_spec.required_keywords_any == ("RANGERS", "SHROUD RUNNERS")
    assert casting.target_spec.required_keywords_any == ("RANGERS", "SHROUD RUNNERS")
    assert nomads.target_spec.required_keywords_any == ("RANGERS", "SHROUD RUNNERS")
    assert isinstance(eldritch.effect_payload, dict)
    assert isinstance(casting.effect_payload, dict)
    assert isinstance(nomads.effect_payload, dict)
    assert isinstance(eldritch.effect_payload.get("rule_ir"), dict)
    assert isinstance(casting.effect_payload.get("rule_ir"), dict)
    assert isinstance(nomads.effect_payload.get("rule_ir"), dict)
    assert eldritch.effect_payload["effect_selection_kind"] == "hit_enemy_unit"
    assert casting.effect_payload["effect_selection_kind"] == "hit_enemy_unit"
    assert (
        eldritch.effect_payload["effect_selection_unit_forbidden_if_battle_shocked"]
        == HIT_ENEMY_UNIT_CONTEXT_KEY
    )


def test_character_target_ap_bonus_only_modifies_character_targets() -> None:
    profile = _test_weapon_profile(ap=0)
    effect = PersistingEffect(
        effect_id="assassins-eye:unit-a",
        source_rule_id=enhancements.ASSASSINS_EYE_SOURCE_RULE_ID,
        owner_player_id="player-a",
        target_unit_instance_ids=("unit-a",),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=character_target_ap_bonus_payload(
            enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
            assignment_source_id="assignment:assassins-eye",
            ap_bonus=1,
        ),
    )

    modified = weapon_profile_with_character_target_ap_effects(
        profile,
        (effect,),
        owner_player_id="player-a",
        target_keywords=("CHARACTER",),
    )
    unmodified = weapon_profile_with_character_target_ap_effects(
        profile,
        (effect,),
        owner_player_id="player-a",
        target_keywords=("INFANTRY",),
    )

    assert modified.armor_penetration.final == -1
    assert enhancements.ASSASSINS_EYE_SOURCE_RULE_ID in modified.source_ids
    assert unmodified == profile


def test_detection_bonus_payload_respects_source_shot_expiry_flag() -> None:
    effect = PersistingEffect(
        effect_id="far-reaching-doom:unit-b",
        source_rule_id="phase17f:phase17e:aeldari:path-of-the-outcast:far-reaching-doom",
        owner_player_id="player-a",
        target_unit_instance_ids=("unit-b",),
        started_battle_round=1,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload=detection_range_bonus_payload(
            bonus_inches=6,
            source_rule_kind="aeldari_path_of_the_outcast_far_reaching_doom",
            source_unit_instance_id="unit-a",
            source_decision_request_id="request-1",
            source_decision_result_id="result-1",
            expires_when_source_unit_has_shot=True,
        ),
    )

    assert detection_range_bonus_inches_for_effects((effect,), source_unit_has_shot=False) == 6
    assert detection_range_bonus_inches_for_effects((effect,), source_unit_has_shot=True) == 0


def test_path_enhancement_handlers_grant_structured_persisting_effects() -> None:
    state, army, rangers, shroud_runners, _enemy = _path_state()

    camouflaged = enhancements.camouflaged_snipers_effect(
        _enhancement_context(
            state=state,
            army=army,
            unit=rangers,
            enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
        )
    )
    assassins_eye = enhancements.assassins_eye_effect(
        _enhancement_context(
            state=state,
            army=army,
            unit=shroud_runners,
            enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
        )
    )

    assert camouflaged[0].target_unit_instance_id == _RANGERS_UNIT_ID
    assert _json_object(camouflaged[0].persisting_effect.effect_payload)["effect_kind"] == (
        "ranged_attacks_keep_hidden"
    )
    assert assassins_eye[0].target_unit_instance_id == _SHROUD_RUNNERS_UNIT_ID
    assert _json_object(assassins_eye[0].persisting_effect.effect_payload)["effect_kind"] == (
        "character_target_ap_bonus"
    )
    assert _json_object(assassins_eye[0].replay_payload)["armor_penetration_bonus"] == 1


def test_path_enhancement_handlers_reject_invalid_assignments_and_targets() -> None:
    state, army, rangers, shroud_runners, _enemy = _path_state()
    wrong_assignment = enhancements.camouflaged_snipers_effect(
        _enhancement_context(
            state=state,
            army=army,
            unit=rangers,
            enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
        )
    )
    assert wrong_assignment == ()

    with pytest.raises(GameLifecycleError, match="RANGERS"):
        enhancements.camouflaged_snipers_effect(
            _enhancement_context(
                state=state,
                army=army,
                unit=shroud_runners,
                enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            )
        )

    wrong_detachment_army = replace(
        army,
        detachment_selection=DetachmentSelection(
            faction_id="aeldari",
            detachment_ids=("other-detachment",),
        ),
    )
    with pytest.raises(GameLifecycleError, match="Path of the Outcast"):
        enhancements.assassins_eye_effect(
            _enhancement_context(
                state=state,
                army=wrong_detachment_army,
                unit=rangers,
                enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
            )
        )


def test_post_shot_stratagem_options_enumerate_hit_enemy_effect_choices() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    state.gain_command_points(
        player_id="player-a",
        amount=3,
        source_id="test:outcast-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    context = _post_shot_context(state=state, hit_target_ids=(_ENEMY_UNIT_ID,))
    index = StratagemCatalogIndex.from_records(manifest.runtime_contribution().stratagem_records)

    options = stratagem_use_options_from_index(state=state, index=index, context=context)
    payloads_by_stratagem_id = {
        _stratagem_id_from_option_payload(_json_object(option.payload)): _json_object(
            option.payload
        )
        for option in options
    }

    assert set(payloads_by_stratagem_id) == {
        stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
    }
    assert (
        payloads_by_stratagem_id[stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID][
            "effect_selection"
        ]
        is None
    )
    for stratagem_id in (
        stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
    ):
        effect_selection = _json_object(payloads_by_stratagem_id[stratagem_id]["effect_selection"])
        assert effect_selection == {
            "effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            HIT_ENEMY_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
        }

    no_hit_context = _post_shot_context(state=state, hit_target_ids=())
    assert tuple(
        _stratagem_id_from_option_payload(_json_object(option.payload))
        for option in stratagem_use_options_from_index(
            state=state, index=index, context=no_hit_context
        )
    ) == (stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,)


def test_casting_back_the_veil_applies_detection_effect_to_hit_enemy() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    context = _stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        handler_id=stratagems.CASTING_BACK_THE_VEIL_HANDLER_ID,
        use_id="use:casting-back",
        destroyed_hit_enemy=False,
    )

    result = stratagems.apply_casting_back_the_veil(context)

    assert result.status is StratagemHandlerExecutionStatus.APPLIED
    assert len(state.persisting_effects) == 1
    effect = state.persisting_effects[0]
    payload = _json_object(effect.effect_payload)
    assert effect.target_unit_instance_ids == (_ENEMY_UNIT_ID,)
    assert payload["effect_kind"] == "detection_range_bonus"
    assert payload["bonus_inches"] == 6
    assert payload["source_unit_instance_id"] == _RANGERS_UNIT_ID


def test_detection_range_effect_makes_hidden_target_legal_for_shooting() -> None:
    state, _army, rangers, _shroud_runners, _enemy = _path_state(enemy_x=18.0)
    state.record_persisting_effect(
        _hidden_effect(effect_id="hidden:enemy", target_id=_ENEMY_UNIT_ID)
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_battlefield_state(state),
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    profile = _test_weapon_profile(ap=0)

    without_bonus = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        attacker_unit=rangers,
        attacker_model_instance_id=rangers.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=_ENEMY_UNIT_ID,
        hidden_target_unit_ids=(_ENEMY_UNIT_ID,),
    )

    assert not without_bonus.is_legal
    assert without_bonus.violation_code is ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE

    state.record_persisting_effect(
        PersistingEffect(
            effect_id="casting-back:enemy-detection",
            source_rule_id=stratagems.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(_ENEMY_UNIT_ID,),
            started_battle_round=1,
            started_phase=BattlePhase.SHOOTING,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhase.SHOOTING,
                player_id="player-a",
            ),
            effect_payload=detection_range_bonus_payload(
                bonus_inches=6,
                source_rule_kind="aeldari_path_of_the_outcast_casting_back_the_veil",
                source_unit_instance_id=_RANGERS_UNIT_ID,
                source_decision_request_id="request:casting-back",
                source_decision_result_id="result:casting-back",
            ),
        )
    )
    with_bonus = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        attacker_unit=rangers,
        attacker_model_instance_id=rangers.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=_ENEMY_UNIT_ID,
        hidden_target_unit_ids=(_ENEMY_UNIT_ID,),
        target_detection_range_bonus_inches=detection_range_bonus_inches_for_effects(
            state.persisting_effects_for_unit(_ENEMY_UNIT_ID),
        ),
    )

    assert with_bonus.is_legal


def test_far_reaching_doom_detection_effect_makes_hidden_target_legal_until_source_shoots() -> None:
    state, _army, rangers, _shroud_runners, _enemy = _path_state(enemy_x=18.0)
    state.record_persisting_effect(
        _hidden_effect(effect_id="hidden:enemy", target_id=_ENEMY_UNIT_ID)
    )
    grant = rule.apply_far_reaching_doom(
        ShootingUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=1,
            unit_instance_id=_RANGERS_UNIT_ID,
            request_id="request:selected-rangers",
            result_id="result:selected-rangers",
        )
    )[0]
    state.record_persisting_effect(grant.persisting_effect)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_battlefield_state(state),
    )

    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attacker_unit=rangers,
        attacker_model_instance_id=rangers.own_models[0].model_instance_id,
        weapon_profile=_test_weapon_profile(ap=0),
        target_unit_id=_ENEMY_UNIT_ID,
        hidden_target_unit_ids=(_ENEMY_UNIT_ID,),
        target_detection_range_bonus_inches=detection_range_bonus_inches_for_effects(
            state.persisting_effects_for_unit(_ENEMY_UNIT_ID),
            shot_source_unit_ids=(),
        ),
    )

    assert candidate.is_legal
    assert (
        detection_range_bonus_inches_for_effects(
            state.persisting_effects_for_unit(_ENEMY_UNIT_ID),
            shot_source_unit_ids=(_RANGERS_UNIT_ID,),
        )
        == 0
    )


def test_nomads_of_the_hidden_way_records_restriction_and_move_request() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    context = _stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
        handler_id=stratagems.NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
        use_id="use:nomads",
        destroyed_hit_enemy=False,
    )

    result = stratagems.apply_nomads_of_the_hidden_way(context)

    assert result.status is StratagemHandlerExecutionStatus.APPLIED
    assert len(state.persisting_effects) == 1
    restriction_payload = _json_object(state.persisting_effects[0].effect_payload)
    assert restriction_payload["effect_kind"] == "aeldari_path_of_the_outcast_nomads_restriction"
    assert restriction_payload["charge_forbidden"] is True
    assert restriction_payload["embark_transport_forbidden"] is True
    request = context.decisions.queue.pending_requests[0]
    assert request.decision_type == "select_triggered_movement"
    assert request.actor_id == "player-a"


def test_eldritch_suppression_forces_battle_shock_with_destroyed_model_modifier() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    context = _stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        handler_id=stratagems.ELDRITCH_SUPPRESSION_HANDLER_ID,
        use_id="use:eldritch",
        destroyed_hit_enemy=True,
    )

    result = stratagems.apply_eldritch_suppression(context)

    assert result.status is StratagemHandlerExecutionStatus.APPLIED
    replay_payload = _json_object(result.replay_payload)
    assert replay_payload["enemy_unit_instance_id"] == _ENEMY_UNIT_ID
    assert replay_payload["destroyed_model_modifier_applied"] is True
    assert any(
        record.event_type == "battle_shock_test_resolved"
        for record in context.decisions.event_log.records
    )


def test_apply_enhancement_effects_records_persisting_grant_once() -> None:
    assignment = EnhancementAssignment(
        enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
        target_unit_selection_id="rangers",
        source_id="assignment:camouflaged-snipers",
    )
    state, _army, _rangers, _shroud_runners, _enemy = _path_state(
        enhancement_assignments=(assignment,)
    )
    registry = _path_runtime_bundle(state).enhancement_effect_registry
    decisions = DecisionController()

    apply_enhancement_effects(state=state, registry=registry, decisions=decisions)
    apply_enhancement_effects(state=state, registry=registry, decisions=decisions)

    assert len(state.persisting_effects) == 1
    assert state.persisting_effects[0].target_unit_instance_ids == (_RANGERS_UNIT_ID,)
    assert [
        record.event_type
        for record in decisions.event_log.records
        if record.event_type == "enhancement_effects_applied"
    ] == ["enhancement_effects_applied"]


def test_camouflaged_snipers_preserves_hidden_status_after_ranged_attacks() -> None:
    ruleset = _ruleset_with_hidden_detection()
    normal_state, _normal_army, _normal_rangers, _normal_shroud, _normal_enemy = _path_state()
    normal_state.record_persisting_effect(
        _hidden_effect(effect_id="hidden:normal-rangers", target_id=_RANGERS_UNIT_ID)
    )
    normal_decisions = DecisionController()

    apply_hidden_status_loss_after_ranged_attacks(
        state=normal_state,
        decisions=normal_decisions,
        unit_instance_id=_RANGERS_UNIT_ID,
        request_id="request:normal-shooting",
        result_id="result:normal-shooting",
        ruleset_descriptor=ruleset,
        event_type="unit_hidden_status_lost_after_shooting",
    )

    assert not unit_is_hidden_by_effects(normal_state.persisting_effects_for_unit(_RANGERS_UNIT_ID))
    assert any(
        record.event_type == "unit_hidden_status_lost_after_shooting"
        for record in normal_decisions.event_log.records
    )

    camo_state, camo_army, camo_rangers, _camo_shroud, _camo_enemy = _path_state()
    camo_state.record_persisting_effect(
        _hidden_effect(effect_id="hidden:camouflaged-rangers", target_id=_RANGERS_UNIT_ID)
    )
    camo_grants = enhancements.camouflaged_snipers_effect(
        _enhancement_context(
            state=camo_state,
            army=camo_army,
            unit=camo_rangers,
            enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
        )
    )
    camo_state.record_persisting_effect(camo_grants[0].persisting_effect)
    camo_decisions = DecisionController()

    apply_hidden_status_loss_after_ranged_attacks(
        state=camo_state,
        decisions=camo_decisions,
        unit_instance_id=_RANGERS_UNIT_ID,
        request_id="request:camouflaged-shooting",
        result_id="result:camouflaged-shooting",
        ruleset_descriptor=ruleset,
        event_type="unit_hidden_status_lost_after_shooting",
    )

    assert unit_is_hidden_by_effects(camo_state.persisting_effects_for_unit(_RANGERS_UNIT_ID))
    assert any(
        record.event_type == "unit_hidden_status_preserved_after_shooting"
        for record in camo_decisions.event_log.records
    )


def test_enhancement_framework_rejects_malformed_persisting_grants_and_handlers() -> None:
    state, army, _rangers, _shroud_runners, _enemy = _path_state()
    context = _enhancement_context(
        state=state,
        army=army,
        unit=army.units[0],
        enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
    )
    valid_grant = _test_persisting_effect_grant(
        effect_id="effect:test",
        source_id="source:test",
        enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
        target_unit_id=_RANGERS_UNIT_ID,
    )

    with pytest.raises(GameLifecycleError, match="persisting_effect"):
        EnhancementPersistingEffectGrant(
            effect_id="effect:test",
            source_id="source:test",
            enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            target_unit_instance_id=_RANGERS_UNIT_ID,
            persisting_effect=cast(PersistingEffect, object()),
        )
    with pytest.raises(GameLifecycleError, match="source drift"):
        EnhancementPersistingEffectGrant(
            effect_id="effect:test",
            source_id="source:test",
            enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            target_unit_instance_id=_RANGERS_UNIT_ID,
            persisting_effect=replace(valid_grant.persisting_effect, source_rule_id="source:other"),
        )
    with pytest.raises(GameLifecycleError, match="target drift"):
        EnhancementPersistingEffectGrant(
            effect_id="effect:test",
            source_id="source:test",
            enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            target_unit_instance_id=_RANGERS_UNIT_ID,
            persisting_effect=replace(
                valid_grant.persisting_effect,
                target_unit_instance_ids=("army-a:other",),
            ),
        )

    def effects_for(
        handler: Callable[[EnhancementEffectContext], tuple[object, ...]],
    ) -> tuple[object, ...]:
        registry = EnhancementEffectRegistry.from_bindings(
            (
                EnhancementEffectBinding(
                    effect_id="effect:test",
                    source_id="source:test",
                    enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                    handler=handler,
                ),
            )
        )
        return registry.effects_for(context)

    def non_tuple_handler(_context: EnhancementEffectContext) -> tuple[object, ...]:
        return cast(tuple[object, ...], [valid_grant])

    def unsupported_handler(_context: EnhancementEffectContext) -> tuple[object, ...]:
        return (object(),)

    with pytest.raises(GameLifecycleError, match="return a tuple"):
        effects_for(non_tuple_handler)
    with pytest.raises(GameLifecycleError, match="supported enhancement effects"):
        effects_for(unsupported_handler)
    with pytest.raises(GameLifecycleError, match="effect_id drift"):
        effects_for(
            lambda _context: (
                _test_persisting_effect_grant(
                    effect_id="effect:other",
                    source_id="source:test",
                    enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                    target_unit_id=_RANGERS_UNIT_ID,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        effects_for(
            lambda _context: (
                _test_persisting_effect_grant(
                    effect_id="effect:test",
                    source_id="source:other",
                    enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                    target_unit_id=_RANGERS_UNIT_ID,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="enhancement_id drift"):
        effects_for(
            lambda _context: (
                _test_persisting_effect_grant(
                    effect_id="effect:test",
                    source_id="source:test",
                    enhancement_id="enhancement:other",
                    target_unit_id=_RANGERS_UNIT_ID,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="target unit drift"):
        effects_for(
            lambda _context: (
                _test_persisting_effect_grant(
                    effect_id="effect:test",
                    source_id="source:test",
                    enhancement_id=enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                    target_unit_id=_SHROUD_RUNNERS_UNIT_ID,
                ),
            )
        )


def test_path_stratagem_validators_reject_drifted_contexts() -> None:
    state, _army, _rangers, _shroud_runners, _enemy = _path_state()
    valid_context = _stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        handler_id=stratagems.CASTING_BACK_THE_VEIL_HANDLER_ID,
        use_id="use:valid-casting",
        destroyed_hit_enemy=False,
    )
    wrong_stratagem_context = _stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        handler_id=stratagems.ELDRITCH_SUPPRESSION_HANDLER_ID,
        use_id="use:wrong-stratagem",
        destroyed_hit_enemy=False,
    )
    wrong_timing_context = replace(
        valid_context,
        eligibility_context=replace(
            valid_context.eligibility_context,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    wrong_target_context = replace(
        valid_context,
        target_binding=replace(
            valid_context.target_binding,
            target_unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        ),
    )
    wrong_detachment_state, wrong_detachment_army, *_ = _path_state()
    wrong_detachment_state.army_definitions[0] = replace(
        wrong_detachment_army,
        detachment_selection=DetachmentSelection(
            faction_id="aeldari",
            detachment_ids=("other-detachment",),
        ),
    )
    wrong_detachment_context = _stratagem_handler_context(
        state=wrong_detachment_state,
        stratagem_id=stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        handler_id=stratagems.CASTING_BACK_THE_VEIL_HANDLER_ID,
        use_id="use:wrong-detachment",
        destroyed_hit_enemy=False,
    )
    friendly_hit_context = replace(
        valid_context,
        use_record=replace(
            valid_context.use_record,
            effect_selection={
                "effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                HIT_ENEMY_UNIT_CONTEXT_KEY: _RANGERS_UNIT_ID,
            },
        ),
    )
    shocked_state, _shocked_army, *_ = _path_state()
    shocked_state.battle_shocked_unit_ids.append(_ENEMY_UNIT_ID)
    already_shocked_context = _stratagem_handler_context(
        state=shocked_state,
        stratagem_id=stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        handler_id=stratagems.ELDRITCH_SUPPRESSION_HANDLER_ID,
        use_id="use:already-shocked",
        destroyed_hit_enemy=False,
    )

    assert (
        stratagems.validate_casting_back_the_veil(wrong_stratagem_context).reason
        == "wrong_stratagem"
    )
    assert stratagems.validate_casting_back_the_veil(wrong_timing_context).reason == "wrong_timing"
    assert (
        stratagems.validate_casting_back_the_veil(wrong_target_context).reason
        == "target_not_just_shot"
    )
    assert (
        stratagems.validate_casting_back_the_veil(wrong_detachment_context).reason
        == "detachment_missing"
    )
    assert stratagems.validate_casting_back_the_veil(friendly_hit_context).reason == (
        "hit_unit_not_enemy"
    )
    assert stratagems.validate_eldritch_suppression(already_shocked_context).reason == (
        "target_already_battle_shocked"
    )


def test_ranged_rule_effect_helpers_validate_payload_shapes() -> None:
    ignored_effect = PersistingEffect(
        effect_id="ignored-detection",
        source_rule_id="source:ignored",
        owner_player_id="player-a",
        target_unit_instance_ids=("unit-b",),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=None,
    )
    invalid_detection_effect = replace(
        ignored_effect,
        effect_id="invalid-detection",
        effect_payload={"effect_kind": "detection_range_bonus", "bonus_inches": "6"},
    )
    invalid_ap_effect = replace(
        ignored_effect,
        effect_id="invalid-ap",
        effect_payload={"effect_kind": "character_target_ap_bonus", "ap_bonus": "1"},
    )

    assert detection_range_bonus_inches_for_effects((ignored_effect,)) == 0
    with pytest.raises(GameLifecycleError, match="bonus_inches"):
        detection_range_bonus_inches_for_effects((invalid_detection_effect,))
    with pytest.raises(GameLifecycleError, match="ap_bonus"):
        weapon_profile_with_character_target_ap_effects(
            _test_weapon_profile(ap=0),
            (invalid_ap_effect,),
            owner_player_id="player-a",
            target_keywords=("CHARACTER",),
        )
    with pytest.raises(GameLifecycleError, match="positive"):
        character_target_ap_bonus_payload(
            enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
            assignment_source_id="assignment:bad",
            ap_bonus=0,
        )


def test_ranged_rule_effect_helpers_reject_invalid_types_and_ignore_unrelated_effects() -> None:
    profile = _test_weapon_profile(ap=0)
    ignored_effect = PersistingEffect(
        effect_id="ignored-effect",
        source_rule_id="source:ignored",
        owner_player_id="player-a",
        target_unit_instance_ids=("unit-b",),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={"effect_kind": "other"},
    )
    owner_mismatch_effect = replace(
        ignored_effect,
        effect_id="owner-mismatch-ap",
        owner_player_id="player-b",
        effect_payload=character_target_ap_bonus_payload(
            enhancement_id=enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
            assignment_source_id="assignment:assassins-eye",
            ap_bonus=1,
        ),
    )

    assert detection_range_bonus_inches_for_effects((ignored_effect,)) == 0
    assert (
        weapon_profile_with_character_target_ap_effects(
            profile,
            (owner_mismatch_effect, ignored_effect, replace(ignored_effect, effect_payload=None)),
            owner_player_id="player-a",
            target_keywords=("character",),
        )
        == profile
    )
    with pytest.raises(GameLifecycleError, match="effect tuple"):
        detection_range_bonus_inches_for_effects(
            cast(tuple[PersistingEffect, ...], [ignored_effect])
        )
    with pytest.raises(GameLifecycleError, match="PersistingEffect"):
        detection_range_bonus_inches_for_effects(cast(tuple[PersistingEffect, ...], ("bad",)))
    with pytest.raises(GameLifecycleError, match="WeaponProfile"):
        weapon_profile_with_character_target_ap_effects(
            cast(WeaponProfile, object()),
            (),
            owner_player_id="player-a",
            target_keywords=("CHARACTER",),
        )
    with pytest.raises(GameLifecycleError, match="effect tuple"):
        weapon_profile_with_character_target_ap_effects(
            profile,
            cast(tuple[PersistingEffect, ...], [ignored_effect]),
            owner_player_id="player-a",
            target_keywords=("CHARACTER",),
        )
    with pytest.raises(GameLifecycleError, match="PersistingEffect"):
        weapon_profile_with_character_target_ap_effects(
            profile,
            cast(tuple[PersistingEffect, ...], ("bad",)),
            owner_player_id="player-a",
            target_keywords=("CHARACTER",),
        )
    with pytest.raises(GameLifecycleError, match="keyword"):
        weapon_profile_with_character_target_ap_effects(
            profile,
            (),
            owner_player_id="player-a",
            target_keywords=cast(tuple[str, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="source_rule_kind"):
        detection_range_bonus_payload(bonus_inches=1, source_rule_kind="")
    with pytest.raises(GameLifecycleError, match="bonus_inches"):
        detection_range_bonus_payload(
            bonus_inches=cast(int, "6"),
            source_rule_kind="source:rule",
        )
    with pytest.raises(GameLifecycleError, match="bool"):
        detection_range_bonus_payload(
            bonus_inches=1,
            source_rule_kind="source:rule",
            expires_when_source_unit_has_shot=cast(bool, "yes"),
        )


def _test_weapon_profile(*, ap: int) -> WeaponProfile:
    return WeaponProfile(
        profile_id="ranger-long-rifle",
        name="Ranger long rifle",
        range_profile=RangeProfile.distance(36),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, ap),
        damage_profile=DamageProfile.fixed(1),
    )


def _ruleset_with_hidden_detection() -> RulesetDescriptor:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    return replace(
        ruleset,
        terrain_visibility_policy=replace(
            ruleset.terrain_visibility_policy,
            hidden_supported=True,
            hidden_detection_range_inches=6.0,
            hidden_lost_after_shooting=True,
        ),
        descriptor_hash="",
    )


def _hidden_effect(*, effect_id: str, target_id: str) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id="test:hidden",
        owner_player_id="player-a" if target_id.startswith("army-a:") else "player-b",
        target_unit_instance_ids=(target_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=unit_hidden_payload(source_rule_kind="test_hidden_state"),
    )


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise AssertionError("Expected test battlefield state.")
    return state.battlefield_state


def _path_state(
    *,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    enemy_x: float = 12.0,
) -> tuple[GameState, ArmyDefinition, UnitInstance, UnitInstance, UnitInstance]:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    rangers = _unit(
        unit_instance_id=_RANGERS_UNIT_ID,
        datasheet_id="aeldari-rangers",
        name="Rangers",
        keywords=("RANGERS", "INFANTRY"),
        faction_keywords=("AELDARI",),
        leadership=7,
    )
    shroud_runners = _unit(
        unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        datasheet_id="aeldari-shroud-runners",
        name="Shroud Runners",
        keywords=("SHROUD RUNNERS", "MOUNTED"),
        faction_keywords=("AELDARI",),
        leadership=7,
    )
    enemy = _unit(
        unit_instance_id=_ENEMY_UNIT_ID,
        datasheet_id="enemy-target",
        name="Enemy Target",
        keywords=("INFANTRY",),
        faction_keywords=("OPFOR",),
        leadership=7,
    )
    army = _army(
        army_id="army-a",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        faction_id="aeldari",
        detachment_id="path-of-the-outcast",
        units=(rangers, shroud_runners),
        enhancement_assignments=enhancement_assignments,
    )
    enemy_army = _army(
        army_id="army-b",
        player_id="player-b",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        faction_id="opfor",
        detachment_id="target-practice",
        units=(enemy,),
    )
    battle_phases = tuple(ruleset.battle_phase_sequence.phases)
    state = GameState(
        game_id="path-outcast-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=battle_phases,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phases.index(BattlePhase.SHOOTING),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=[army, enemy_army],
        starting_strength_records=[
            StartingStrengthRecord.from_unit(player_id="player-a", unit=rangers),
            StartingStrengthRecord.from_unit(player_id="player-a", unit=shroud_runners),
            StartingStrengthRecord.from_unit(player_id="player-b", unit=enemy),
        ],
        battlefield_state=BattlefieldRuntimeState(
            battlefield_id="battlefield-alpha",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            placed_armies=(
                PlacedArmy(
                    army_id="army-a",
                    player_id="player-a",
                    unit_placements=(_unit_placement("army-a", "player-a", rangers, x=0.0),),
                ),
                PlacedArmy(
                    army_id="army-b",
                    player_id="player-b",
                    unit_placements=(_unit_placement("army-b", "player-b", enemy, x=enemy_x),),
                ),
            ),
        ),
    )
    return state, army, rangers, shroud_runners, enemy


def _path_runtime_bundle(state: GameState) -> RuntimeContentBundle:
    armies = tuple(state.army_definitions)
    return RuntimeContentBundle.from_contributions(
        activation=_path_runtime_activation(armies),
        armies=armies,
        catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        contributions=(manifest.runtime_contribution(),),
    )


def _path_runtime_activation(armies: tuple[ArmyDefinition, ...]) -> RuntimeContentActivation:
    army = next(army for army in armies if army.player_id == "player-a")
    return RuntimeContentActivation(
        selected_faction_ids=("aeldari", "opfor"),
        selected_detachment_ids=("path-of-the-outcast", "target-practice"),
        selected_enhancement_ids=tuple(
            sorted(assignment.enhancement_id for assignment in army.enhancement_assignments)
        ),
        selected_stratagem_ids=(),
        selected_datasheet_ids=tuple(
            sorted(unit.datasheet_id for active_army in armies for unit in active_army.units)
        ),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=tuple(
            sorted(unit.unit_instance_id for active_army in armies for unit in active_army.units)
        ),
        selected_enhancement_assignments=tuple(
            _runtime_assignment(army=army, assignment=assignment)
            for assignment in army.enhancement_assignments
        ),
        selected_execution_record_ids=(
            enhancements.ASSASSINS_EYE_SOURCE_RULE_ID,
            enhancements.CAMOUFLAGED_SNIPERS_SOURCE_RULE_ID,
        ),
    )


def _runtime_assignment(
    *,
    army: ArmyDefinition,
    assignment: EnhancementAssignment,
) -> RuntimeEnhancementAssignment:
    return RuntimeEnhancementAssignment(
        assignment_id=(
            f"{army.army_id}:{assignment.enhancement_id}:{assignment.target_unit_selection_id}"
        ),
        player_id=army.player_id,
        army_id=army.army_id,
        enhancement_id=assignment.enhancement_id,
        target_unit_selection_id=assignment.target_unit_selection_id,
        bearer_unit_instance_id=f"{army.army_id}:{assignment.target_unit_selection_id}",
        source_id=assignment.source_id,
    )


def _army(
    *,
    army_id: str,
    player_id: str,
    catalog_id: str,
    source_package_id: str,
    ruleset_id: RulesetId,
    faction_id: str,
    detachment_id: str,
    units: tuple[UnitInstance, ...],
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog_id,
        source_package_id=source_package_id,
        ruleset_id=ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
            enhancement_ids=(
                enhancements.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
                enhancements.ASSASSINS_EYE_ENHANCEMENT_ID,
            ),
            stratagem_ids=(
                stratagems.ELDRITCH_SUPPRESSION_STRATAGEM_ID,
                stratagems.CASTING_BACK_THE_VEIL_STRATAGEM_ID,
                stratagems.NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
            ),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        enhancement_assignments=enhancement_assignments,
    )


def _unit(
    *,
    unit_instance_id: str,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    leadership: int,
) -> UnitInstance:
    model = _model(
        model_instance_id=f"{unit_instance_id}:model-001",
        datasheet_id=datasheet_id,
        model_profile_id=f"{datasheet_id}-profile",
        name=f"{name} model",
        keywords=keywords,
        leadership=leadership,
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name=name,
        keywords=keywords,
        faction_keywords=faction_keywords,
        datasheet_abilities=(),
        datasheet_source_ids=(f"source:{datasheet_id}",),
        own_models=(model,),
        wargear_selections=(),
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    name: str,
    keywords: tuple[str, ...],
    leadership: int,
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(32.0)
    return ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=name,
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 1),
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=keywords,
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=1,
        wounds_remaining=1,
        wargear_ids=(),
        source_ids=(f"source:{model_profile_id}",),
    )


def _unit_placement(
    army_id: str,
    player_id: str,
    unit: UnitInstance,
    *,
    x: float,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=Pose.at(x=x, y=0.0, facing_degrees=0.0),
            ),
        ),
    )


def _enhancement_context(
    *,
    state: GameState,
    army: ArmyDefinition,
    unit: UnitInstance,
    enhancement_id: str,
) -> EnhancementEffectContext:
    return EnhancementEffectContext(
        state=state,
        army=army,
        assignment=EnhancementAssignment(
            enhancement_id=enhancement_id,
            target_unit_selection_id="path-enhancement-target",
            source_id=f"assignment:{enhancement_id}",
        ),
        target_unit=unit,
    )


def _stratagem_handler_context(
    *,
    state: GameState,
    stratagem_id: str,
    handler_id: str,
    use_id: str,
    destroyed_hit_enemy: bool,
) -> StratagemHandlerContext:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    definition = _stratagem_definition(stratagem_id)
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id=_RANGERS_UNIT_ID,
    )
    eligibility_context = _post_shot_context(
        state=state,
        hit_target_ids=(_ENEMY_UNIT_ID,),
        destroyed_target_ids=(_ENEMY_UNIT_ID,) if destroyed_hit_enemy else (),
    )
    result = DecisionResult(
        result_id=f"{use_id}:result",
        request_id=f"{use_id}:request",
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id="player-a",
        selected_option_id=f"{use_id}:option",
        payload=None,
    )
    use_record = StratagemUseRecord(
        use_id=use_id,
        player_id="player-a",
        stratagem_id=stratagem_id,
        source_id=definition.source_id,
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        timing_window_id="friendly-unit-has-shot:event-000001",
        request_id=result.request_id,
        result_id=result.result_id,
        selected_option_id=result.selected_option_id,
        target_binding=target_binding,
        targeted_unit_instance_ids=(_RANGERS_UNIT_ID,),
        affected_unit_instance_ids=tuple(sorted((_RANGERS_UNIT_ID, _ENEMY_UNIT_ID))),
        command_point_cost=1,
        command_point_transaction_id=f"{use_id}:cp",
        handler_id=handler_id,
        effect_selection={
            "effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            HIT_ENEMY_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
        },
        effect_payload=definition.effect_payload,
    )
    return StratagemHandlerContext(
        state=state,
        decisions=DecisionController(),
        result=result,
        eligibility_context=eligibility_context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=ruleset,
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
    )


def _post_shot_context(
    *,
    state: GameState,
    hit_target_ids: tuple[str, ...],
    destroyed_target_ids: tuple[str, ...] = (),
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        timing_window_id="friendly-unit-has-shot:event-000001",
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _RANGERS_UNIT_ID,
            HIT_TARGET_UNIT_CONTEXT_KEY: list(hit_target_ids),
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(destroyed_target_ids),
            "attack_sequence_id": "attack-sequence-001",
            "attack_sequence_completed_event_id": "event-000001",
        },
    )


def _stratagem_definition(stratagem_id: str) -> StratagemDefinition:
    for record in manifest.runtime_contribution().stratagem_records:
        if record.definition.stratagem_id == stratagem_id:
            return record.definition
    raise AssertionError(f"Missing test stratagem definition: {stratagem_id}")


def _test_persisting_effect_grant(
    *,
    effect_id: str,
    source_id: str,
    enhancement_id: str,
    target_unit_id: str,
) -> EnhancementPersistingEffectGrant:
    effect = PersistingEffect(
        effect_id=f"{effect_id}:{target_unit_id}",
        source_rule_id=source_id,
        owner_player_id="player-a",
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={"effect_kind": "test"},
    )
    return EnhancementPersistingEffectGrant(
        effect_id=effect_id,
        source_id=source_id,
        enhancement_id=enhancement_id,
        target_unit_instance_id=target_unit_id,
        persisting_effect=effect,
    )


def _json_object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _stratagem_id_from_option_payload(payload: dict[str, object]) -> str:
    catalog_record = _json_object(payload["catalog_record"])
    definition = _json_object(catalog_record["definition"])
    stratagem_id = definition["stratagem_id"]
    assert isinstance(stratagem_id, str)
    return stratagem_id
