from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    payload_bool as _payload_bool,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_int as _payload_int,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_object as _payload_object,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_string as _payload_string,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_string_tuple as _payload_string_tuple,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.shooting_targets import (
    shooting_dynamic_model_blockers,
    shooting_visibility_cache_key,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.triggered_movement import (
    TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
    TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND,
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.unit_abilities import unit_has_lone_operative
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.visibility import TerrainVisibilityContext
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers"
HOOK_ID = "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"
MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID = f"{HOOK_ID}:mortal-wound-feel-no-pain"
SOURCE_RULE_ID = "phase17f:phase17e:thousand-sons:army-rule"
THOUSAND_SONS_FACTION_ID = "thousand-sons"
THOUSAND_SONS_FACTION_KEYWORD = "THOUSAND SONS"
SCINTILLATING_LEGIONS_KEYWORD = "SCINTILLATING LEGIONS"
CABAL_SELECTION_KIND = "thousand_sons_cabal_of_sorcerers_ritual"
CABAL_DONE_STATE_KIND = "thousand_sons_cabal_of_sorcerers_shooting_phase_done"
CABAL_ATTEMPT_STATE_KIND = "thousand_sons_cabal_of_sorcerers_ritual_attempt"
CABAL_DONE_OPTION_ID = "thousand-sons:cabal-of-sorcerers:done"
CABAL_PSYCHIC_TEST_ROLL_TYPE = "thousand_sons.cabal_of_sorcerers.psychic_test"
CABAL_PERILS_MORTAL_WOUNDS_ROLL_TYPE = "thousand_sons.cabal_of_sorcerers.perils_mortal_wounds"
CABAL_DOOMBOLT_MORTAL_WOUNDS_ROLL_TYPE = "thousand_sons.cabal_of_sorcerers.doombolt"
CABAL_TEMPORAL_SURGE_DISTANCE_ROLL_TYPE = "thousand_sons.cabal_of_sorcerers.temporal_surge"
CABAL_MORTAL_WOUND_SOURCE_KIND = "thousand_sons_cabal_of_sorcerers_mortal_wounds"
CABAL_DESTINY_EFFECT_KIND = "thousand_sons_destinys_ruin"
CABAL_TWIST_EFFECT_KIND = "thousand_sons_twist_of_fate"
CABAL_TEMPORAL_CHARGE_FORBIDDEN_EFFECT_KIND = "thousand_sons_temporal_surge_charge_forbidden"
CABAL_HIT_REROLL_EFFECT_KIND = "thousand_sons_destinys_ruin_hit_reroll"
RITUAL_RANGE_INCHES = 24.0
DOOMBOLT_LONE_OPERATIVE_RANGE_INCHES = 12.0


class CabalRitualId(StrEnum):
    DESTINYS_RUIN = "destinys_ruin"
    TEMPORAL_SURGE = "temporal_surge"
    DOOMBOLT = "doombolt"
    TWIST_OF_FATE = "twist_of_fate"


class CabalTargetKind(StrEnum):
    ENEMY = "enemy"
    FRIENDLY = "friendly"


@dataclass(frozen=True, slots=True)
class CabalRitualDefinition:
    ritual_id: CabalRitualId
    name: str
    warp_charge: int
    high_result_threshold: int
    target_kind: CabalTargetKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "ritual_id", _cabal_ritual_id_from_token(self.ritual_id))
        object.__setattr__(self, "name", _validate_identifier("ritual name", self.name))
        object.__setattr__(
            self,
            "warp_charge",
            _validate_positive_int("ritual warp_charge", self.warp_charge),
        )
        object.__setattr__(
            self,
            "high_result_threshold",
            _validate_positive_int(
                "ritual high_result_threshold",
                self.high_result_threshold,
            ),
        )
        object.__setattr__(
            self,
            "target_kind",
            _cabal_target_kind_from_token(self.target_kind),
        )


@dataclass(frozen=True, slots=True)
class CabalManifestingModel:
    rules_unit: RulesUnitView
    component_unit: UnitInstance
    model: ModelInstance

    def __post_init__(self) -> None:
        if type(self.rules_unit) is not RulesUnitView:
            raise GameLifecycleError("Cabal manifesting model requires a rules unit.")
        if type(self.component_unit) is not UnitInstance:
            raise GameLifecycleError("Cabal manifesting model requires a component unit.")
        if type(self.model) is not ModelInstance:
            raise GameLifecycleError("Cabal manifesting model requires a model.")
        if self.component_unit.unit_instance_id not in self.rules_unit.component_unit_instance_ids:
            raise GameLifecycleError("Cabal manifesting component is not in its rules unit.")
        if self.model.model_instance_id not in self.component_unit.own_model_ids():
            raise GameLifecycleError("Cabal manifesting model is not in its component unit.")


@dataclass(frozen=True, slots=True)
class CabalRitualOption:
    manifesting_model: CabalManifestingModel
    ritual: CabalRitualDefinition
    target_rules_unit: RulesUnitView
    channel_the_warp: bool

    def __post_init__(self) -> None:
        if type(self.manifesting_model) is not CabalManifestingModel:
            raise GameLifecycleError("Cabal ritual option requires a manifesting model.")
        if type(self.ritual) is not CabalRitualDefinition:
            raise GameLifecycleError("Cabal ritual option requires a ritual definition.")
        if type(self.target_rules_unit) is not RulesUnitView:
            raise GameLifecycleError("Cabal ritual option requires a target rules unit.")
        if type(self.channel_the_warp) is not bool:
            raise GameLifecycleError("Cabal ritual option channel flag must be bool.")


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        shooting_phase_start_hook_bindings=(
            ShootingPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=cabal_of_sorcerers_request,
                result_handler=apply_cabal_of_sorcerers_result,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=cabal_weapon_profile_modifier,
            ),
        ),
        mortal_wound_feel_no_pain_hook_bindings=(
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id=MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                source_kind=CABAL_MORTAL_WOUND_SOURCE_KIND,
                handler=apply_cabal_mortal_wound_feel_no_pain_decision,
            ),
        ),
    )


def cabal_of_sorcerers_request(
    context: ShootingPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not ShootingPhaseStartRequestContext:
        raise GameLifecycleError("Cabal of Sorcerers requires request context.")
    active_player_id = _active_player_id(context.state)
    army = _thousand_sons_army_for_player(context.state, player_id=active_player_id)
    if army is None:
        return None
    if _cabal_done_this_shooting_phase(context.state, player_id=army.player_id):
        return None

    options = _eligible_cabal_options(context, army=army)
    if not options:
        return None

    common_payload = _common_request_payload(context.state, player_id=army.player_id)
    decision_options = tuple(_ritual_decision_option(option, common_payload) for option in options)
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(
            {
                **common_payload,
                "eligible_ritual_option_ids": [_ritual_option_id(option) for option in options],
                "attempted_model_instance_ids": list(
                    _cabal_attempted_model_ids_this_turn(context.state, player_id=army.player_id)
                ),
                "attempted_ritual_ids": list(
                    _cabal_attempted_ritual_ids_this_turn(context.state, player_id=army.player_id)
                ),
            }
        ),
        options=(
            *decision_options,
            DecisionOption(
                option_id=CABAL_DONE_OPTION_ID,
                label="No more Rituals",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": CABAL_SELECTION_KIND,
                        "selected_cabal_option": "done",
                    }
                ),
            ),
        ),
    )


def apply_cabal_of_sorcerers_result(
    context: ShootingPhaseStartResultContext,
) -> bool | LifecycleStatus:
    if type(context) is not ShootingPhaseStartResultContext:
        raise GameLifecycleError("Cabal of Sorcerers requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Cabal of Sorcerers result requires an actor.")
    player_id = result.actor_id
    army = _thousand_sons_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Cabal of Sorcerers actor does not own Thousand Sons.")
    if _cabal_done_this_shooting_phase(context.state, player_id=player_id):
        raise GameLifecycleError("Cabal of Sorcerers was already completed this Shooting phase.")

    payload = _payload_object(result.payload)
    selected = _payload_string(payload, key="selected_cabal_option")
    if selected == "done":
        if result.selected_option_id != CABAL_DONE_OPTION_ID:
            raise GameLifecycleError("Cabal of Sorcerers done option ID drift.")
        _record_cabal_done(context, player_id=player_id)
        return True
    if selected != "attempt":
        raise GameLifecycleError("Cabal of Sorcerers selection is unsupported.")

    current_options = {
        _ritual_option_id(option): option for option in _eligible_cabal_options(context, army=army)
    }
    option = current_options.get(result.selected_option_id)
    if option is None:
        raise GameLifecycleError("Cabal of Sorcerers ritual is no longer eligible.")
    _assert_result_matches_option(payload, option)
    return _resolve_cabal_ritual_attempt(context, player_id=player_id, option=option)


def apply_cabal_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError("Cabal of Sorcerers FNP continuation requires context.")
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=context.state,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    source_context = _cabal_mortal_wound_source_context(routed.progress.source_context)
    return _resolve_routed_cabal_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=context.result.result_id,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
        dice_manager=context.dice_manager,
        source_context=source_context,
    )


def cabal_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Cabal of Sorcerers weapon modifier requires context.")
    profile = context.weapon_profile
    if context.source_phase is not BattlePhase.SHOOTING:
        return profile
    if profile.range_profile.kind is RangeProfileKind.MELEE:
        return profile
    attacking_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if not _rules_unit_has_thousand_sons_or_scintillating(attacking_rules_unit):
        return profile
    effect = _active_twist_of_fate_effect_for_target(
        context.state,
        player_id=attacking_rules_unit.owner_player_id,
        target_rules_unit_instance_id=context.target_unit_instance_id,
    )
    if effect is None:
        return profile
    payload = _payload_object(effect.effect_payload)
    bonus = _payload_int(payload, key="armor_penetration_bonus")
    return replace(
        profile,
        armor_penetration=_improve_armor_penetration(profile.armor_penetration, bonus),
        source_ids=_source_ids_with_cabal(profile.source_ids),
    )


def _resolve_cabal_ritual_attempt(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
    option: CabalRitualOption,
) -> bool | LifecycleStatus:
    _record_cabal_attempt(context, player_id=player_id, option=option)
    dice_manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    psychic_roll = dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(
                quantity=3 if option.channel_the_warp else 2,
                sides=6,
            ),
            reason=f"Cabal of Sorcerers Psychic test for {option.ritual.name}",
            roll_type=CABAL_PSYCHIC_TEST_ROLL_TYPE,
            actor_id=player_id,
        )
    )
    source_payload = _ritual_resolution_payload(
        context=context,
        player_id=player_id,
        option=option,
        psychic_roll=validate_json_value(psychic_roll.to_payload()),
        psychic_test_result=psychic_roll.current_total,
        ritual_manifested=False,
        mortal_wound_application=None,
    )
    if option.channel_the_warp and _psychic_roll_has_doubles_or_triples(
        psychic_roll.current_values
    ):
        d3_result = dice_manager.roll_d3(
            reason=(
                f"Cabal of Sorcerers perils for {option.manifesting_model.model.model_instance_id}"
            ),
            roll_type=CABAL_PERILS_MORTAL_WOUNDS_ROLL_TYPE,
            actor_id=player_id,
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{context.result.result_id}:cabal:{option.ritual.ritual_id.value}:"
                f"{option.manifesting_model.model.model_instance_id}:perils"
            ),
            source_rule_id=SOURCE_RULE_ID,
            source_context=_cabal_mortal_wound_source_context_payload(
                mortal_wound_kind="psychic_test_perils",
                resolution_payload={
                    **source_payload,
                    "perils_d3_result": validate_json_value(d3_result.to_payload()),
                },
            ),
            target_unit_instance_id=option.manifesting_model.rules_unit.unit_instance_id,
            defender_player_id=player_id,
            mortal_wounds=d3_result.value,
            spill_over=True,
        )
        routed = continue_mortal_wound_application(
            state=context.state,
            request_id=context.state.next_decision_request_id(),
            progress=progress,
            dice_manager=dice_manager,
        )
        status = _resolve_routed_cabal_mortal_wounds(
            state=context.state,
            decisions=context.decisions,
            feel_no_pain_result_id=None,
            routed_request=routed.request,
            routed_application=routed.application,
            routed_progress=routed.progress,
            dice_manager=dice_manager,
            source_context=_cabal_mortal_wound_source_context(progress.source_context),
        )
        if status is not None:
            return status
        return True

    status = _resolve_ritual_after_psychic_test(
        state=context.state,
        decisions=context.decisions,
        dice_manager=dice_manager,
        resolution_payload=source_payload,
        mortal_wound_application=None,
    )
    return True if status is None else status


def _resolve_routed_cabal_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    feel_no_pain_result_id: str | None,
    routed_request: DecisionRequest | None,
    routed_application: MortalWoundApplication | None,
    routed_progress: MortalWoundApplicationProgress,
    dice_manager: DiceRollManager,
    source_context: dict[str, JsonValue],
) -> LifecycleStatus | None:
    resolution_payload = _payload_object(source_context["resolution_payload"])
    if routed_request is not None:
        decisions.request_decision(routed_request)
        decisions.event_log.append(
            "thousand_sons_cabal_mortal_wounds_pending",
            validate_json_value(
                {
                    **resolution_payload,
                    "request_id": routed_request.request_id,
                    "remaining_mortal_wounds": routed_progress.remaining_mortal_wounds,
                    "mortal_wound_kind": source_context["mortal_wound_kind"],
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed_request,
            payload=validate_json_value(
                {
                    "phase": BattlePhase.SHOOTING.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "source_rule_id": SOURCE_RULE_ID,
                    "source_kind": CABAL_MORTAL_WOUND_SOURCE_KIND,
                    "mortal_wound_kind": source_context["mortal_wound_kind"],
                    "target_unit_instance_id": routed_progress.target_unit_instance_id,
                    "pending_request_id": routed_request.request_id,
                }
            ),
        )
    if routed_application is None:
        raise GameLifecycleError("Cabal of Sorcerers mortal wound routing did not complete.")
    resolved_payload = {
        **resolution_payload,
        "mortal_wound_application": validate_json_value(routed_application.to_payload()),
        "mortal_wound_kind": source_context["mortal_wound_kind"],
    }
    if feel_no_pain_result_id is not None:
        resolved_payload["feel_no_pain_result_id"] = feel_no_pain_result_id
    decisions.event_log.append(
        "thousand_sons_cabal_mortal_wounds_resolved",
        validate_json_value(resolved_payload),
    )
    if source_context["mortal_wound_kind"] != "psychic_test_perils":
        return None
    return _resolve_ritual_after_psychic_test(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        resolution_payload=cast(dict[str, JsonValue], validate_json_value(resolved_payload)),
        mortal_wound_application=routed_application,
    )


def _resolve_ritual_after_psychic_test(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager,
    resolution_payload: dict[str, JsonValue],
    mortal_wound_application: MortalWoundApplication | None,
) -> LifecycleStatus | None:
    ritual = _ritual_by_id(_payload_string(resolution_payload, key="ritual_id"))
    manifesting_model_id = _payload_string(resolution_payload, key="manifesting_model_instance_id")
    if not _model_is_alive(state, model_instance_id=manifesting_model_id):
        decisions.event_log.append(
            "thousand_sons_cabal_manifesting_model_destroyed",
            validate_json_value(
                {
                    **resolution_payload,
                    "ritual_manifested": False,
                    "mortal_wound_application": (
                        None
                        if mortal_wound_application is None
                        else validate_json_value(mortal_wound_application.to_payload())
                    ),
                }
            ),
        )
        return None
    psychic_result = _payload_int(resolution_payload, key="psychic_test_result")
    if psychic_result < ritual.warp_charge:
        decisions.event_log.append(
            "thousand_sons_cabal_ritual_failed",
            validate_json_value(
                {
                    **resolution_payload,
                    "ritual_manifested": False,
                    "mortal_wound_application": (
                        None
                        if mortal_wound_application is None
                        else validate_json_value(mortal_wound_application.to_payload())
                    ),
                }
            ),
        )
        return None
    return _manifest_cabal_ritual(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        ritual=ritual,
        resolution_payload={
            **resolution_payload,
            "ritual_manifested": True,
            "mortal_wound_application": (
                None
                if mortal_wound_application is None
                else validate_json_value(mortal_wound_application.to_payload())
            ),
        },
    )


def _manifest_cabal_ritual(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager,
    ritual: CabalRitualDefinition,
    resolution_payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    if ritual.ritual_id is CabalRitualId.DESTINYS_RUIN:
        _record_destinys_ruin_effects(
            state=state,
            decisions=decisions,
            ritual=ritual,
            resolution_payload=resolution_payload,
        )
        return None
    if ritual.ritual_id is CabalRitualId.TWIST_OF_FATE:
        _record_twist_of_fate_effect(
            state=state,
            decisions=decisions,
            ritual=ritual,
            resolution_payload=resolution_payload,
        )
        return None
    if ritual.ritual_id is CabalRitualId.DOOMBOLT:
        return _resolve_doombolt(
            state=state,
            decisions=decisions,
            dice_manager=dice_manager,
            ritual=ritual,
            resolution_payload=resolution_payload,
        )
    if ritual.ritual_id is CabalRitualId.TEMPORAL_SURGE:
        return _resolve_temporal_surge(
            state=state,
            decisions=decisions,
            dice_manager=dice_manager,
            ritual=ritual,
            resolution_payload=resolution_payload,
        )
    raise GameLifecycleError("Cabal of Sorcerers ritual is unsupported.")


def _record_destinys_ruin_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    ritual: CabalRitualDefinition,
    resolution_payload: dict[str, JsonValue],
) -> None:
    player_id = _payload_string(resolution_payload, key="player_id")
    target_id = _payload_string(resolution_payload, key="target_rules_unit_instance_id")
    psychic_result = _payload_int(resolution_payload, key="psychic_test_result")
    reroll_mode = "full" if psychic_result >= ritual.high_result_threshold else "ones"
    expiration = EffectExpiration.end_phase(
        battle_round=state.battle_round,
        phase=BattlePhaseKind.SHOOTING,
        player_id=player_id,
    )
    attacker_effect_ids: list[str] = []
    for attacker in _eligible_cabal_attacker_rules_units(state, player_id=player_id):
        effect = PersistingEffect(
            effect_id=(
                f"thousand-sons:cabal:destinys-ruin:{state.game_id}:"
                f"round-{state.battle_round:02d}:{player_id}:{attacker.unit_instance_id}:"
                f"{target_id}:{_payload_string(resolution_payload, key='result_id')}"
            ),
            source_rule_id=SOURCE_RULE_ID,
            owner_player_id=player_id,
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.SHOOTING,
            expiration=expiration,
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(attacker.unit_instance_id,),
                permission=_destinys_ruin_hit_reroll_permission(
                    player_id=player_id,
                    reroll_mode=reroll_mode,
                ),
                source_payload=validate_json_value(
                    {
                        "effect_kind": CABAL_HIT_REROLL_EFFECT_KIND,
                        "cabal_effect_kind": CABAL_DESTINY_EFFECT_KIND,
                        "target_unit_instance_id": target_id,
                        "reroll_mode": reroll_mode,
                        **_source_context_subset(resolution_payload),
                        **(
                            {}
                            if reroll_mode == "full"
                            else {
                                "conditional_hit_reroll": {
                                    "reroll_unmodified_values": [1],
                                }
                            }
                        ),
                    }
                ),
            ),
        )
        state.record_persisting_effect(effect)
        attacker_effect_ids.append(effect.effect_id)
    decisions.event_log.append(
        "thousand_sons_destinys_ruin_manifested",
        validate_json_value(
            {
                **resolution_payload,
                "reroll_mode": reroll_mode,
                "hit_reroll_effect_ids": attacker_effect_ids,
            }
        ),
    )


def _record_twist_of_fate_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    ritual: CabalRitualDefinition,
    resolution_payload: dict[str, JsonValue],
) -> None:
    player_id = _payload_string(resolution_payload, key="player_id")
    target_id = _payload_string(resolution_payload, key="target_rules_unit_instance_id")
    psychic_result = _payload_int(resolution_payload, key="psychic_test_result")
    bonus = 2 if psychic_result >= ritual.high_result_threshold else 1
    effect = PersistingEffect(
        effect_id=(
            f"thousand-sons:cabal:twist-of-fate:{state.game_id}:"
            f"round-{state.battle_round:02d}:{player_id}:{target_id}:"
            f"{_payload_string(resolution_payload, key='result_id')}"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(target_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": CABAL_TWIST_EFFECT_KIND,
                "target_unit_instance_id": target_id,
                "target_owner_player_id": resolution_payload["target_owner_player_id"],
                "armor_penetration_bonus": bonus,
                **_source_context_subset(resolution_payload),
            }
        ),
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "thousand_sons_twist_of_fate_manifested",
        validate_json_value(
            {
                **resolution_payload,
                "armor_penetration_bonus": bonus,
                "persisting_effect": effect.to_payload(),
            }
        ),
    )


def _resolve_doombolt(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager,
    ritual: CabalRitualDefinition,
    resolution_payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    psychic_result = _payload_int(resolution_payload, key="psychic_test_result")
    d3_result = dice_manager.roll_d3(
        reason=(
            f"Cabal of Sorcerers Doombolt for {resolution_payload['target_rules_unit_instance_id']}"
        ),
        roll_type=CABAL_DOOMBOLT_MORTAL_WOUNDS_ROLL_TYPE,
        actor_id=_payload_string(resolution_payload, key="player_id"),
    )
    mortal_wounds = d3_result.value
    if psychic_result >= ritual.high_result_threshold:
        mortal_wounds += 3
    target_id = _payload_string(resolution_payload, key="target_rules_unit_instance_id")
    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"{_payload_string(resolution_payload, key='result_id')}:cabal:doombolt:{target_id}"
        ),
        source_rule_id=SOURCE_RULE_ID,
        source_context=_cabal_mortal_wound_source_context_payload(
            mortal_wound_kind="doombolt",
            resolution_payload={
                **resolution_payload,
                "doombolt_d3_result": validate_json_value(d3_result.to_payload()),
                "doombolt_mortal_wounds": mortal_wounds,
            },
        ),
        target_unit_instance_id=target_id,
        defender_player_id=_payload_string(resolution_payload, key="target_owner_player_id"),
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=state,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
    )
    return _resolve_routed_cabal_mortal_wounds(
        state=state,
        decisions=decisions,
        feel_no_pain_result_id=None,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
        dice_manager=dice_manager,
        source_context=_cabal_mortal_wound_source_context(progress.source_context),
    )


def _resolve_temporal_surge(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager,
    ritual: CabalRitualDefinition,
    resolution_payload: dict[str, JsonValue],
) -> LifecycleStatus:
    player_id = _payload_string(resolution_payload, key="player_id")
    target_id = _payload_string(resolution_payload, key="target_rules_unit_instance_id")
    psychic_result = _payload_int(resolution_payload, key="psychic_test_result")
    if psychic_result >= ritual.high_result_threshold:
        max_distance = 6.0
        distance_roll_payload: JsonValue = None
    else:
        distance_roll = dice_manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Cabal of Sorcerers Temporal Surge distance for {target_id}",
                roll_type=CABAL_TEMPORAL_SURGE_DISTANCE_ROLL_TYPE,
                actor_id=player_id,
            )
        )
        max_distance = float(distance_roll.current_total)
        distance_roll_payload = validate_json_value(distance_roll.to_payload())
    charge_effect = PersistingEffect(
        effect_id=(
            f"thousand-sons:cabal:temporal-surge:no-charge:{state.game_id}:"
            f"round-{state.battle_round:02d}:{player_id}:{target_id}:"
            f"{_payload_string(resolution_payload, key='result_id')}"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(target_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": CABAL_TEMPORAL_CHARGE_FORBIDDEN_EFFECT_KIND,
                "charge_forbidden": True,
                "target_unit_instance_id": target_id,
                "max_distance_inches": max_distance,
                "temporal_surge_distance_roll": distance_roll_payload,
                **_source_context_subset(resolution_payload),
            }
        ),
    )
    state.record_persisting_effect(charge_effect)
    request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING.value,
        unit_instance_id=target_id,
        proposal_kind=ProposalKind.SURGE_MOVE,
        source_decision_request_id=_payload_string(resolution_payload, key="request_id"),
        source_decision_result_id=_payload_string(resolution_payload, key="result_id"),
        movement_phase_action=TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
        context={
            "context_kind": TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND,
            "descriptor": validate_json_value(
                TriggeredMovementDescriptor(
                    movement_kind=TriggeredMovementKind.TRIGGERED,
                    source_rule_id=SOURCE_RULE_ID,
                    trigger_timing=ReactionWindow(
                        phase=BattlePhaseKind.SHOOTING,
                        window_kind=ReactionWindowKind.RULE_TRIGGER,
                        source_step="cabal_of_sorcerers_temporal_surge",
                    ),
                    max_distance_inches=max_distance,
                    movement_mode=MovementMode.NORMAL,
                    allow_battle_shocked=True,
                    allow_within_engagement_range=False,
                    one_per_phase=False,
                    optional=True,
                ).to_payload()
            ),
            "ritual_resolution": validate_json_value(resolution_payload),
            "charge_forbidden_effect_id": charge_effect.effect_id,
        },
    ).to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "thousand_sons_temporal_surge_manifested",
        validate_json_value(
            {
                **resolution_payload,
                "max_distance_inches": max_distance,
                "temporal_surge_distance_roll": distance_roll_payload,
                "charge_forbidden_effect": charge_effect.to_payload(),
                "proposal_request_id": request.request_id,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": player_id,
                "unit_instance_id": target_id,
                "decision_type": MOVEMENT_PROPOSAL_DECISION_TYPE,
                "phase_body_status": "thousand_sons_temporal_surge_proposal_pending",
                "pending_request_id": request.request_id,
            }
        ),
    )


def _eligible_cabal_options(
    context: ShootingPhaseStartRequestContext | ShootingPhaseStartResultContext,
    *,
    army: ArmyDefinition,
) -> tuple[CabalRitualOption, ...]:
    attempted_model_ids = set(
        _cabal_attempted_model_ids_this_turn(context.state, player_id=army.player_id)
    )
    attempted_ritual_ids = set(
        _cabal_attempted_ritual_ids_this_turn(context.state, player_id=army.player_id)
    )
    manifesting_models = tuple(
        manifesting_model
        for manifesting_model in _eligible_manifesting_models(
            context.state,
            player_id=army.player_id,
        )
        if manifesting_model.model.model_instance_id not in attempted_model_ids
    )
    rituals = tuple(
        ritual for ritual in RITUALS if ritual.ritual_id.value not in attempted_ritual_ids
    )
    options: list[CabalRitualOption] = []
    for manifesting_model in manifesting_models:
        for ritual in rituals:
            for target in _eligible_targets_for_ritual(
                context,
                army=army,
                manifesting_model=manifesting_model,
                ritual=ritual,
            ):
                for channel_the_warp in (False, True):
                    options.append(
                        CabalRitualOption(
                            manifesting_model=manifesting_model,
                            ritual=ritual,
                            target_rules_unit=target,
                            channel_the_warp=channel_the_warp,
                        )
                    )
    return tuple(
        sorted(
            options,
            key=lambda option: (
                option.manifesting_model.model.model_instance_id,
                option.ritual.ritual_id.value,
                option.target_rules_unit.unit_instance_id,
                option.channel_the_warp,
            ),
        )
    )


def _eligible_manifesting_models(
    state: GameState,
    *,
    player_id: str,
) -> tuple[CabalManifestingModel, ...]:
    manifesting: list[CabalManifestingModel] = []
    for rules_unit_id in _placed_friendly_rules_unit_ids(state, player_id=player_id):
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
        for component in rules_unit.components:
            if not _unit_has_cabal_of_sorcerers(component.unit):
                continue
            for model in component.unit.alive_own_models():
                if _model_has_placement(
                    state,
                    unit_instance_id=component.unit.unit_instance_id,
                    model=model,
                ):
                    manifesting.append(
                        CabalManifestingModel(
                            rules_unit=rules_unit,
                            component_unit=component.unit,
                            model=model,
                        )
                    )
    return tuple(
        sorted(
            manifesting,
            key=lambda candidate: candidate.model.model_instance_id,
        )
    )


def _eligible_targets_for_ritual(
    context: ShootingPhaseStartRequestContext | ShootingPhaseStartResultContext,
    *,
    army: ArmyDefinition,
    manifesting_model: CabalManifestingModel,
    ritual: CabalRitualDefinition,
) -> tuple[RulesUnitView, ...]:
    if ritual.target_kind is CabalTargetKind.ENEMY:
        candidate_ids = _placed_enemy_rules_unit_ids(context.state, player_id=army.player_id)
    else:
        candidate_ids = _placed_friendly_rules_unit_ids(context.state, player_id=army.player_id)
    targets: list[RulesUnitView] = []
    for target_id in candidate_ids:
        target = rules_unit_view_by_id(state=context.state, unit_instance_id=target_id)
        if (
            target.unit_instance_id == manifesting_model.rules_unit.unit_instance_id
            and ritual.target_kind is CabalTargetKind.ENEMY
        ):
            raise GameLifecycleError("Cabal enemy target cannot be the manifesting unit.")
        if ritual.target_kind is CabalTargetKind.FRIENDLY:
            if not _rules_unit_has_thousand_sons_or_scintillating(target):
                continue
            if _rules_unit_within_enemy_engagement_range(context.state, target):
                continue
        if not _manifesting_model_can_see_target(
            state=context.state,
            ruleset_descriptor=context.ruleset_descriptor,
            manifesting_model=manifesting_model,
            target_rules_unit=target,
            range_inches=RITUAL_RANGE_INCHES,
        ):
            continue
        if ritual.ritual_id is CabalRitualId.DOOMBOLT and _doombolt_lone_operative_excluded(
            state=context.state,
            manifesting_model=manifesting_model,
            target_rules_unit=target,
        ):
            continue
        targets.append(target)
    return tuple(sorted(targets, key=lambda target: target.unit_instance_id))


def _ritual_decision_option(
    option: CabalRitualOption,
    common_payload: dict[str, JsonValue],
) -> DecisionOption:
    manifesting = option.manifesting_model
    return DecisionOption(
        option_id=_ritual_option_id(option),
        label=(
            f"{manifesting.model.name} attempts {option.ritual.name} on "
            f"{_rules_unit_label(option.target_rules_unit)}"
            f"{' with Channel the Warp' if option.channel_the_warp else ''}"
        ),
        payload=validate_json_value(
            {
                **common_payload,
                "submission_kind": CABAL_SELECTION_KIND,
                "selected_cabal_option": "attempt",
                "ritual_id": option.ritual.ritual_id.value,
                "ritual_name": option.ritual.name,
                "warp_charge": option.ritual.warp_charge,
                "high_result_threshold": option.ritual.high_result_threshold,
                "target_kind": option.ritual.target_kind.value,
                "channel_the_warp": option.channel_the_warp,
                "manifesting_rules_unit_instance_id": manifesting.rules_unit.unit_instance_id,
                "manifesting_component_unit_instance_id": (
                    manifesting.component_unit.unit_instance_id
                ),
                "manifesting_model_instance_id": manifesting.model.model_instance_id,
                "manifesting_model_name": manifesting.model.name,
                "target_rules_unit_instance_id": option.target_rules_unit.unit_instance_id,
                "target_component_unit_instance_ids": list(
                    option.target_rules_unit.component_unit_instance_ids
                ),
                "target_owner_player_id": option.target_rules_unit.owner_player_id,
            }
        ),
    )


def _ritual_option_id(option: CabalRitualOption) -> str:
    return (
        "thousand-sons:cabal-of-sorcerers:"
        f"model:{option.manifesting_model.model.model_instance_id}:"
        f"ritual:{option.ritual.ritual_id.value}:"
        f"target:{option.target_rules_unit.unit_instance_id}:"
        f"channel:{str(option.channel_the_warp).lower()}"
    )


def _assert_result_matches_option(
    payload: dict[str, JsonValue],
    option: CabalRitualOption,
) -> None:
    manifesting = option.manifesting_model
    if _payload_string(payload, key="ritual_id") != option.ritual.ritual_id.value:
        raise GameLifecycleError("Cabal of Sorcerers ritual payload drift.")
    if _payload_int(payload, key="warp_charge") != option.ritual.warp_charge:
        raise GameLifecycleError("Cabal of Sorcerers warp charge payload drift.")
    if _payload_bool(payload, key="channel_the_warp") != option.channel_the_warp:
        raise GameLifecycleError("Cabal of Sorcerers channel payload drift.")
    if (
        _payload_string(payload, key="manifesting_rules_unit_instance_id")
        != manifesting.rules_unit.unit_instance_id
    ):
        raise GameLifecycleError("Cabal of Sorcerers manifesting rules unit payload drift.")
    if (
        _payload_string(payload, key="manifesting_component_unit_instance_id")
        != manifesting.component_unit.unit_instance_id
    ):
        raise GameLifecycleError("Cabal of Sorcerers manifesting component payload drift.")
    if (
        _payload_string(payload, key="manifesting_model_instance_id")
        != manifesting.model.model_instance_id
    ):
        raise GameLifecycleError("Cabal of Sorcerers manifesting model payload drift.")
    if (
        _payload_string(payload, key="target_rules_unit_instance_id")
        != option.target_rules_unit.unit_instance_id
    ):
        raise GameLifecycleError("Cabal of Sorcerers target payload drift.")
    if (
        _payload_string(payload, key="target_owner_player_id")
        != option.target_rules_unit.owner_player_id
    ):
        raise GameLifecycleError("Cabal of Sorcerers target owner payload drift.")
    if (
        _payload_string_tuple(payload, key="target_component_unit_instance_ids")
        != option.target_rules_unit.component_unit_instance_ids
    ):
        raise GameLifecycleError("Cabal of Sorcerers target component payload drift.")


def _record_cabal_done(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    done_state = FactionRuleState(
        state_id=(
            f"thousand-sons:cabal:done:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:shooting"
        ),
        player_id=player_id,
        faction_id=THOUSAND_SONS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=CABAL_DONE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                **_common_request_payload(context.state, player_id=player_id),
                "selected_cabal_option": "done",
            }
        ),
    )
    context.state.record_faction_rule_state(done_state)
    context.decisions.event_log.append(
        "thousand_sons_cabal_done",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "faction_rule_state": done_state.to_payload(),
            }
        ),
    )


def _record_cabal_attempt(
    context: ShootingPhaseStartResultContext,
    *,
    player_id: str,
    option: CabalRitualOption,
) -> None:
    manifesting = option.manifesting_model
    attempt_state = FactionRuleState(
        state_id=(
            f"thousand-sons:cabal:attempt:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:"
            f"{manifesting.model.model_instance_id}:{option.ritual.ritual_id.value}"
        ),
        player_id=player_id,
        faction_id=THOUSAND_SONS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=CABAL_ATTEMPT_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                **_common_request_payload(context.state, player_id=player_id),
                "selected_cabal_option": "attempt",
                "ritual_id": option.ritual.ritual_id.value,
                "ritual_name": option.ritual.name,
                "manifesting_rules_unit_instance_id": manifesting.rules_unit.unit_instance_id,
                "manifesting_component_unit_instance_id": (
                    manifesting.component_unit.unit_instance_id
                ),
                "manifesting_model_instance_id": manifesting.model.model_instance_id,
                "target_rules_unit_instance_id": option.target_rules_unit.unit_instance_id,
                "target_owner_player_id": option.target_rules_unit.owner_player_id,
                "channel_the_warp": option.channel_the_warp,
                "selected_option_id": context.result.selected_option_id,
            }
        ),
    )
    context.state.record_faction_rule_state(attempt_state)
    context.decisions.event_log.append(
        "thousand_sons_cabal_attempt_recorded",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "faction_rule_state": attempt_state.to_payload(),
            }
        ),
    )


def _ritual_resolution_payload(
    *,
    context: ShootingPhaseStartResultContext,
    player_id: str,
    option: CabalRitualOption,
    psychic_roll: JsonValue,
    psychic_test_result: int,
    ritual_manifested: bool,
    mortal_wound_application: JsonValue,
) -> dict[str, JsonValue]:
    manifesting = option.manifesting_model
    return _payload_object(
        validate_json_value(
            {
                **_common_request_payload(context.state, player_id=player_id),
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "selected_option_id": context.result.selected_option_id,
                "ritual_id": option.ritual.ritual_id.value,
                "ritual_name": option.ritual.name,
                "warp_charge": option.ritual.warp_charge,
                "high_result_threshold": option.ritual.high_result_threshold,
                "target_kind": option.ritual.target_kind.value,
                "channel_the_warp": option.channel_the_warp,
                "manifesting_rules_unit_instance_id": manifesting.rules_unit.unit_instance_id,
                "manifesting_component_unit_instance_id": (
                    manifesting.component_unit.unit_instance_id
                ),
                "manifesting_model_instance_id": manifesting.model.model_instance_id,
                "target_rules_unit_instance_id": option.target_rules_unit.unit_instance_id,
                "target_component_unit_instance_ids": list(
                    option.target_rules_unit.component_unit_instance_ids
                ),
                "target_owner_player_id": option.target_rules_unit.owner_player_id,
                "psychic_roll": psychic_roll,
                "psychic_test_result": psychic_test_result,
                "ritual_manifested": ritual_manifested,
                "mortal_wound_application": mortal_wound_application,
            }
        )
    )


def _common_request_payload(state: GameState, *, player_id: str) -> dict[str, JsonValue]:
    return _payload_object(
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": player_id,
                "player_id": player_id,
                "faction_id": THOUSAND_SONS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selection_kind": CABAL_SELECTION_KIND,
            }
        )
    )


def _cabal_done_this_shooting_phase(state: GameState, *, player_id: str) -> bool:
    matching = tuple(
        stored
        for stored in state.faction_rule_states_for_player(
            player_id=_validate_identifier("player_id", player_id),
            state_kind=CABAL_DONE_STATE_KIND,
        )
        if _done_state_matches_current_shooting_phase(state, stored)
    )
    if len(matching) > 1:
        raise GameLifecycleError("Cabal of Sorcerers found multiple done states.")
    return bool(matching)


def _done_state_matches_current_shooting_phase(
    state: GameState,
    stored: FactionRuleState,
) -> bool:
    payload = _payload_object(stored.payload)
    return (
        stored.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.SHOOTING.value
        and payload.get("selected_cabal_option") == "done"
    )


def _cabal_attempted_model_ids_this_turn(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(_payload_object(stored.payload), key="manifesting_model_instance_id")
            for stored in _cabal_attempt_states_this_turn(state, player_id=player_id)
        )
    )


def _cabal_attempted_ritual_ids_this_turn(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            _payload_string(_payload_object(stored.payload), key="ritual_id")
            for stored in _cabal_attempt_states_this_turn(state, player_id=player_id)
        )
    )


def _cabal_attempt_states_this_turn(
    state: GameState,
    *,
    player_id: str,
) -> tuple[FactionRuleState, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    return tuple(
        sorted(
            (
                stored
                for stored in state.faction_rule_states_for_player(
                    player_id=requested_player_id,
                    state_kind=CABAL_ATTEMPT_STATE_KIND,
                )
                if _attempt_state_matches_current_turn(state, stored)
            ),
            key=lambda stored: stored.state_id,
        )
    )


def _attempt_state_matches_current_turn(state: GameState, stored: FactionRuleState) -> bool:
    payload = _payload_object(stored.payload)
    return (
        stored.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("active_player_id") == state.active_player_id
        and payload.get("selected_cabal_option") == "attempt"
    )


def _active_twist_of_fate_effect_for_target(
    state: GameState,
    *,
    player_id: str,
    target_rules_unit_instance_id: str,
) -> PersistingEffect | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_target_id = _validate_identifier(
        "target_rules_unit_instance_id",
        target_rules_unit_instance_id,
    )
    effects = tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == SOURCE_RULE_ID
        and effect.owner_player_id == requested_player_id
        and _payload_object(effect.effect_payload).get("effect_kind") == CABAL_TWIST_EFFECT_KIND
        and _payload_object(effect.effect_payload).get("target_unit_instance_id")
        == requested_target_id
    )
    if len(effects) > 1:
        raise GameLifecycleError("Cabal of Sorcerers found multiple Twist of Fate effects.")
    return effects[0] if effects else None


def _destinys_ruin_hit_reroll_permission(
    *,
    player_id: str,
    reroll_mode: str,
) -> RerollPermission:
    requested_mode = _validate_identifier("reroll_mode", reroll_mode)
    if requested_mode == "full":
        return RerollPermission(
            source_id=SOURCE_RULE_ID,
            timing_window="attack_sequence.hit",
            owning_player_id=player_id,
            eligible_roll_type="attack_sequence.hit",
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
    if requested_mode == "ones":
        return RerollPermission(
            source_id=SOURCE_RULE_ID,
            timing_window="attack_sequence.hit",
            owning_player_id=player_id,
            eligible_roll_type="attack_sequence.hit",
            component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
            allowed_component_selections=((0,),),
        )
    raise GameLifecycleError("Cabal of Sorcerers reroll mode is unsupported.")


def _eligible_cabal_attacker_rules_units(
    state: GameState,
    *,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    return tuple(
        rules_unit
        for rules_unit in (
            rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
            for rules_unit_id in _placed_friendly_rules_unit_ids(state, player_id=player_id)
        )
        if _rules_unit_has_thousand_sons_or_scintillating(rules_unit)
    )


def _model_is_alive(state: GameState, *, model_instance_id: str) -> bool:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model.is_alive
    raise GameLifecycleError("Cabal of Sorcerers manifesting model is unknown.")


def _model_has_placement(
    state: GameState,
    *,
    unit_instance_id: str,
    model: ModelInstance,
) -> bool:
    if state.battlefield_state is None:
        raise GameLifecycleError("Cabal of Sorcerers requires battlefield_state.")
    placement = state.battlefield_state.unit_placement_or_none(unit_instance_id)
    if placement is None:
        return False
    return any(
        model_placement.model_instance_id == model.model_instance_id
        for model_placement in placement.model_placements
    )


def _manifesting_model_can_see_target(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    manifesting_model: CabalManifestingModel,
    target_rules_unit: RulesUnitView,
    range_inches: float,
) -> bool:
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    observer_model = _geometry_model_for_manifesting_model(
        scenario=scenario,
        component_unit_id=manifesting_model.component_unit.unit_instance_id,
        model_instance_id=manifesting_model.model.model_instance_id,
    )
    target_models = _alive_geometry_models_for_rules_unit(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if not target_models:
        return False
    in_range_ids = {
        target.model_id
        for target in target_models
        if observer_model.range_to(target) <= float(range_inches)
    }
    if not in_range_ids:
        return False
    if observer_model.model_id in in_range_ids:
        return True
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=terrain_features,
        ),
        observer_model=observer_model,
        target_models=target_models,
        terrain_features=terrain_features,
        dynamic_model_blockers=shooting_dynamic_model_blockers(
            scenario=scenario,
            observing_unit_id=manifesting_model.component_unit.unit_instance_id,
            target_unit_id=target_rules_unit.unit_instance_id,
        ),
        observer_keywords=manifesting_model.component_unit.keywords,
        target_keywords=target_rules_unit.keywords,
    )
    witness = context.resolve_line_of_sight()
    return any(target_id in in_range_ids for target_id in witness.visible_model_ids)


def _doombolt_lone_operative_excluded(
    *,
    state: GameState,
    manifesting_model: CabalManifestingModel,
    target_rules_unit: RulesUnitView,
) -> bool:
    if target_rules_unit.is_attached_rules_unit:
        return False
    if not any(
        unit_has_lone_operative(component.unit) for component in target_rules_unit.components
    ):
        return False
    scenario = _battlefield_scenario(state)
    observer_model = _geometry_model_for_manifesting_model(
        scenario=scenario,
        component_unit_id=manifesting_model.component_unit.unit_instance_id,
        model_instance_id=manifesting_model.model.model_instance_id,
    )
    target_models = _alive_geometry_models_for_rules_unit(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    return not any(
        observer_model.range_to(target_model) <= DOOMBOLT_LONE_OPERATIVE_RANGE_INCHES
        for target_model in target_models
    )


def _geometry_model_for_manifesting_model(
    *,
    scenario: BattlefieldScenario,
    component_unit_id: str,
    model_instance_id: str,
) -> GeometryModel:
    placement = scenario.battlefield_state.unit_placement_by_id(component_unit_id)
    for model_placement in placement.model_placements:
        if model_placement.model_instance_id != model_instance_id:
            continue
        model = scenario.model_instance_for_placement(model_placement)
        if not model.is_alive:
            raise GameLifecycleError("Cabal of Sorcerers manifesting model is destroyed.")
        return geometry_model_for_placement(model=model, placement=model_placement)
    raise GameLifecycleError("Cabal of Sorcerers manifesting model is not placed.")


def _alive_geometry_models_for_rules_unit(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    for component in rules_unit.components:
        placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if placement is None:
            continue
        for model_placement in placement.model_placements:
            model = scenario.model_instance_for_placement(model_placement)
            if model.is_alive:
                models.append(geometry_model_for_placement(model=model, placement=model_placement))
    return tuple(sorted(models, key=lambda model: model.model_id))


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cabal of Sorcerers requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Cabal of Sorcerers battlefield scenario is invalid.") from exc
    return scenario


def _terrain_features_for_state(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cabal of Sorcerers requires battlefield_state.")
    return battlefield_state.terrain_features


def _rules_unit_within_enemy_engagement_range(
    state: GameState,
    rules_unit: RulesUnitView,
) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Cabal of Sorcerers engagement check requires rules unit.")
    for component in rules_unit.components:
        if unit_within_enemy_engagement_range(
            state=state,
            unit_instance_id=component.unit.unit_instance_id,
        ):
            return True
    return False


def _placed_friendly_rules_unit_ids(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return _placed_rules_unit_ids(state, player_id=player_id, include_enemies=False)


def _placed_enemy_rules_unit_ids(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return _placed_rules_unit_ids(state, player_id=player_id, include_enemies=True)


def _placed_rules_unit_ids(
    state: GameState,
    *,
    player_id: str,
    include_enemies: bool,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(include_enemies) is not bool:
        raise GameLifecycleError("Cabal of Sorcerers include_enemies must be bool.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cabal of Sorcerers requires battlefield_state.")
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placed_army in battlefield_state.placed_armies:
        is_enemy = placed_army.player_id != requested_player_id
        if is_enemy != include_enemies:
            continue
        for placement in placed_army.unit_placements:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=armies,
                unit_instance_id=placement.unit_instance_id,
            )
            if rules_unit_id in seen:
                continue
            seen.add(rules_unit_id)
            unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _thousand_sons_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = tuple(
        army
        for army in state.army_definitions
        if army.player_id == requested_player_id
        and army.detachment_selection.faction_id == THOUSAND_SONS_FACTION_ID
    )
    if len(matching) > 1:
        raise GameLifecycleError("Cabal of Sorcerers found multiple Thousand Sons armies.")
    return matching[0] if matching else None


def _unit_has_cabal_of_sorcerers(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Cabal of Sorcerers ability check requires UnitInstance.")
    return _unit_has_rule_source(unit, SOURCE_RULE_ID) or _unit_has_keyword(
        unit.faction_keywords,
        THOUSAND_SONS_FACTION_KEYWORD,
    )


def _rules_unit_has_thousand_sons_or_scintillating(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Cabal of Sorcerers faction keyword check requires rules unit.")
    return _unit_has_keyword(
        (*rules_unit.keywords, *rules_unit.faction_keywords),
        THOUSAND_SONS_FACTION_KEYWORD,
    ) or _unit_has_keyword(
        (*rules_unit.keywords, *rules_unit.faction_keywords),
        SCINTILLATING_LEGIONS_KEYWORD,
    )


def _unit_has_rule_source(unit: UnitInstance, source_rule_id: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Cabal of Sorcerers ability check requires UnitInstance.")
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    return any(
        ability.source_id == requested_source_rule_id for ability in unit.datasheet_abilities
    )


def _unit_has_keyword(keywords: tuple[str, ...], keyword: str) -> bool:
    if type(keywords) is not tuple:
        raise GameLifecycleError("Cabal of Sorcerers keyword list must be a tuple.")
    return _validate_identifier("keyword", keyword) in keywords


def _psychic_roll_has_doubles_or_triples(values: tuple[int, ...]) -> bool:
    if type(values) is not tuple:
        raise GameLifecycleError("Cabal of Sorcerers psychic roll values must be a tuple.")
    return any(count >= 2 for count in Counter(values).values())


def _cabal_mortal_wound_source_context_payload(
    *,
    mortal_wound_kind: str,
    resolution_payload: dict[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": CABAL_MORTAL_WOUND_SOURCE_KIND,
            "mortal_wound_kind": _validate_identifier("mortal_wound_kind", mortal_wound_kind),
            "phase": BattlePhase.SHOOTING.value,
            "resolution_payload": validate_json_value(resolution_payload),
        }
    )


def _cabal_mortal_wound_source_context(source_context: JsonValue) -> dict[str, JsonValue]:
    context = _payload_object(source_context)
    if context.get("source_kind") != CABAL_MORTAL_WOUND_SOURCE_KIND:
        raise GameLifecycleError("Cabal of Sorcerers mortal wound source kind drift.")
    _payload_string(context, key="mortal_wound_kind")
    _payload_string(context, key="phase")
    _payload_object(context["resolution_payload"])
    return context


def _source_context_subset(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "game_id": payload["game_id"],
        "battle_round": payload["battle_round"],
        "phase": payload["phase"],
        "active_player_id": payload["active_player_id"],
        "player_id": payload["player_id"],
        "source_rule_id": payload["source_rule_id"],
        "hook_id": payload["hook_id"],
        "request_id": payload["request_id"],
        "result_id": payload["result_id"],
        "selected_option_id": payload["selected_option_id"],
        "ritual_id": payload["ritual_id"],
        "ritual_name": payload["ritual_name"],
        "psychic_test_result": payload["psychic_test_result"],
    }


def _improve_armor_penetration(value: CharacteristicValue, bonus: int) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Cabal of Sorcerers AP modifier requires CharacteristicValue.")
    amount = _validate_positive_int("armor_penetration_bonus", bonus)
    return CharacteristicValue.from_raw(value.characteristic, value.final - amount)


def _source_ids_with_cabal(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Cabal of Sorcerers source_ids must be a tuple.")
    return tuple(sorted({*source_ids, SOURCE_RULE_ID}))


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Cabal of Sorcerers label requires rules unit.")
    if len(rules_unit.components) == 1:
        return rules_unit.components[0].unit.name
    return " / ".join(component.unit.name for component in rules_unit.components)


def _ritual_by_id(value: object) -> CabalRitualDefinition:
    ritual_id = _cabal_ritual_id_from_token(value)
    for ritual in RITUALS:
        if ritual.ritual_id is ritual_id:
            return ritual
    raise GameLifecycleError("Cabal of Sorcerers ritual definition is unknown.")


def _cabal_ritual_id_from_token(token: object) -> CabalRitualId:
    if type(token) is CabalRitualId:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Cabal ritual ID token must be a string.")
    try:
        return CabalRitualId(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Cabal ritual ID: {token}.") from exc


def _cabal_target_kind_from_token(token: object) -> CabalTargetKind:
    if type(token) is CabalTargetKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Cabal target kind token must be a string.")
    try:
        return CabalTargetKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Cabal target kind: {token}.") from exc


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Cabal of Sorcerers requires active_player_id.")
    return state.active_player_id


_validate_identifier = IdentifierValidator(
    GameLifecycleError,
    message_prefix="Cabal of Sorcerers",
)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Cabal of Sorcerers {field_name} must be an int.")
    if value < 1:
        raise GameLifecycleError(f"Cabal of Sorcerers {field_name} must be positive.")
    return value


RITUALS = (
    CabalRitualDefinition(
        ritual_id=CabalRitualId.DESTINYS_RUIN,
        name="Destiny's Ruin",
        warp_charge=5,
        high_result_threshold=10,
        target_kind=CabalTargetKind.ENEMY,
    ),
    CabalRitualDefinition(
        ritual_id=CabalRitualId.TEMPORAL_SURGE,
        name="Temporal Surge",
        warp_charge=6,
        high_result_threshold=10,
        target_kind=CabalTargetKind.FRIENDLY,
    ),
    CabalRitualDefinition(
        ritual_id=CabalRitualId.DOOMBOLT,
        name="Doombolt",
        warp_charge=7,
        high_result_threshold=11,
        target_kind=CabalTargetKind.ENEMY,
    ),
    CabalRitualDefinition(
        ritual_id=CabalRitualId.TWIST_OF_FATE,
        name="Twist of Fate",
        warp_charge=9,
        high_result_threshold=12,
        target_kind=CabalTargetKind.ENEMY,
    ),
)
