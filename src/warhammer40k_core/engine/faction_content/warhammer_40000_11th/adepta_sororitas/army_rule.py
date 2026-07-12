from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.damaged_effects import (
    CatalogDamagedAbilitySelectionLimit,
    catalog_damaged_ability_selection_limit_for_model,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_identifier_tuple as _payload_identifier_tuple,
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
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    AdvanceRollModifierBinding,
    AdvanceRollModifierContext,
    ChargeRollModifierBinding,
    ChargeRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    adepta_sororitas_triumph_sources_2026_27 as _triumph_sources,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


ADEPTA_SORORITAS_FACTION_ID = "adepta-sororitas"
ADEPTA_SORORITAS_FACTION_KEYWORD = "ADEPTA SORORITAS"
ACTS_OF_FAITH_ABILITY_NAME = "Acts of Faith"
SOURCE_RULE_ID = "phase17f:phase17e:adepta-sororitas:army-rule"

HOOK_ID = "warhammer_40000_11th:adepta_sororitas:army_rule:acts_of_faith"
CONTRIBUTION_ID = HOOK_ID
BATTLE_ROUND_START_HOOK_ID = f"{HOOK_ID}:battle-round-start"
UNIT_DESTROYED_HOOK_ID = f"{HOOK_ID}:unit-destroyed"
TRIUMPH_RELICS_HOOK_ID = (
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs"
)
TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID = f"{TRIUMPH_RELICS_HOOK_ID}:battle-round-start"
TRIUMPH_FIERY_HEART_MOVEMENT_MODIFIER_ID = f"{TRIUMPH_RELICS_HOOK_ID}:fiery-heart:movement"
TRIUMPH_FIERY_HEART_ADVANCE_MODIFIER_ID = f"{TRIUMPH_RELICS_HOOK_ID}:fiery-heart:advance"
TRIUMPH_FIERY_HEART_CHARGE_MODIFIER_ID = f"{TRIUMPH_RELICS_HOOK_ID}:fiery-heart:charge"
TRIUMPH_BLOODY_ROSE_WEAPON_PROFILE_MODIFIER_ID = (
    f"{TRIUMPH_RELICS_HOOK_ID}:bloody-rose:weapon-profile"
)
MIRACLE_DIE_GAIN_ROLL_TYPE = "adepta_sororitas_miracle_die_gain"
MIRACLE_DIE_GAIN_STATE_KIND = "adepta_sororitas_miracle_die_gain"
MIRACLE_DIE_SPEND_STATE_KIND = "adepta_sororitas_miracle_die_spent"
MIRACLE_DIE_GAINED_EVENT = "adepta_sororitas_miracle_die_gained"
MIRACLE_DIE_SPENT_EVENT = "adepta_sororitas_miracle_die_spent"
TRIUMPH_RELICS_SELECTED_EVENT = "adepta_sororitas_relics_of_the_matriarchs_selected"
TRIUMPH_RELICS_SELECTION_KIND = "adepta_sororitas_relics_of_the_matriarchs"
TRIUMPH_RELICS_EFFECT_KIND = "adepta_sororitas_triumph_relics_of_the_matriarchs"
TRIUMPH_RELICS_STATE_KIND = "adepta_sororitas_relics_of_the_matriarchs_selected"
TRIUMPH_RELICS_PERSISTING_EFFECT_KIND = "adepta_sororitas_triumph_relics_selection"
TRIUMPH_RELICS_REROLL_EFFECT_KIND = "adepta_sororitas_triumph_relics_reroll"
TRIUMPH_RELICS_FEEL_NO_PAIN_SOURCE_PREFIX = f"{TRIUMPH_RELICS_HOOK_ID}:feel-no-pain"
BATTLE_ROUND_START_TRIGGER = "battle_round_start"
UNIT_DESTROYED_TRIGGER = "adepta_sororitas_unit_destroyed"
_SUPPORTED_GAIN_TRIGGERS = frozenset({BATTLE_ROUND_START_TRIGGER, UNIT_DESTROYED_TRIGGER})
TRIUMPH_OF_SAINT_KATHERINE_DATASHEET_ID = "000002063"
TRIUMPH_RELICS_SELECTION_GROUP = "Relics of the Matriarchs ability"
TRIUMPH_RELICS_AURA_RANGE_INCHES = 6.0
TRIUMPH_RELICS_SOURCE_RULE_ID = _triumph_sources.TRIUMPH_RELICS_SOURCE_RULE_ID
TRIUMPH_RELICS_DAMAGED_SOURCE_RULE_ID = _triumph_sources.TRIUMPH_RELICS_DAMAGED_SOURCE_RULE_ID


class TriumphRelic(StrEnum):
    FIERY_HEART = "the_fiery_heart"
    CENSER_OF_THE_SACRED_ROSE = "censer_of_the_sacred_rose"
    SIMULACRUM_OF_THE_EBON_CHALICE = "simulacrum_of_the_ebon_chalice"
    SIMULACRUM_OF_THE_ARGENT_SHROUD = "simulacrum_of_the_argent_shroud"
    ICON_OF_THE_VALOROUS_HEART = "icon_of_the_valorous_heart"
    PETALS_OF_THE_BLOODY_ROSE = "petals_of_the_bloody_rose"


_TRIUMPH_RELIC_LABELS: dict[TriumphRelic, str] = {
    TriumphRelic.FIERY_HEART: "The Fiery Heart",
    TriumphRelic.CENSER_OF_THE_SACRED_ROSE: "Censer of the Sacred Rose",
    TriumphRelic.SIMULACRUM_OF_THE_EBON_CHALICE: "Simulacrum of the Ebon Chalice",
    TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD: "Simulacrum of the Argent Shroud",
    TriumphRelic.ICON_OF_THE_VALOROUS_HEART: "Icon of the Valorous Heart",
    TriumphRelic.PETALS_OF_THE_BLOODY_ROSE: "Petals of the Bloody Rose",
}

_TRIUMPH_RELIC_SOURCE_RULE_IDS: dict[TriumphRelic, str] = {
    relic: _triumph_sources.TRIUMPH_RELIC_SOURCE_RULE_IDS_BY_RELIC_ID[relic.value]
    for relic in TriumphRelic
}


@dataclass(frozen=True, slots=True)
class _TriumphRelicsEligibleSource:
    army: ArmyDefinition
    unit: UnitInstance
    model_instance_id: str
    selection_limit: CatalogDamagedAbilitySelectionLimit

    def __post_init__(self) -> None:
        if type(self.army) is not ArmyDefinition:
            raise GameLifecycleError("Triumph Relics source requires ArmyDefinition.")
        if type(self.unit) is not UnitInstance:
            raise GameLifecycleError("Triumph Relics source requires UnitInstance.")
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("Triumph Relics source model_instance_id", self.model_instance_id),
        )
        if type(self.selection_limit) is not CatalogDamagedAbilitySelectionLimit:
            raise GameLifecycleError("Triumph Relics source requires DAMAGED selection limit.")


@dataclass(frozen=True, slots=True)
class MiracleDie:
    miracle_die_id: str
    player_id: str
    value: int
    gain_trigger: str
    source_id: str
    battle_round: int
    phase: BattlePhase
    roll_state: DiceRollState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "miracle_die_id",
            _validate_identifier("MiracleDie miracle_die_id", self.miracle_die_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MiracleDie player_id", self.player_id),
        )
        object.__setattr__(self, "gain_trigger", _validate_gain_trigger(self.gain_trigger))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MiracleDie source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MiracleDie battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("MiracleDie roll_state must be DiceRollState.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("MiracleDie value must match the Miracle dice roll.")
        if self.value < 1 or self.value > 6:
            raise GameLifecycleError("MiracleDie value must be between 1 and 6.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "miracle_die_id": self.miracle_die_id,
            "player_id": self.player_id,
            "value": self.value,
            "gain_trigger": self.gain_trigger,
            "source_id": self.source_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "roll_state": validate_json_value(self.roll_state.to_payload()),
        }

    @classmethod
    def from_payload(cls, payload: object) -> MiracleDie:
        payload_object = _payload_object(payload, field_name="MiracleDie payload")
        return cls(
            miracle_die_id=_payload_string(payload_object, key="miracle_die_id"),
            player_id=_payload_string(payload_object, key="player_id"),
            value=_payload_int(payload_object, key="value"),
            gain_trigger=_payload_string(payload_object, key="gain_trigger"),
            source_id=_payload_string(payload_object, key="source_id"),
            battle_round=_payload_int(payload_object, key="battle_round"),
            phase=_battle_phase_from_token(_payload_string(payload_object, key="phase")),
            roll_state=DiceRollState.from_payload(
                cast(
                    DiceRollStatePayload,
                    _payload_object(payload_object.get("roll_state"), field_name="roll_state"),
                )
            ),
        )

    @classmethod
    def from_state(cls, state: FactionRuleState) -> MiracleDie:
        if type(state) is not FactionRuleState:
            raise GameLifecycleError("MiracleDie state must be FactionRuleState.")
        if state.faction_id != ADEPTA_SORORITAS_FACTION_ID:
            raise GameLifecycleError("MiracleDie state faction drift.")
        if state.source_rule_id != SOURCE_RULE_ID:
            raise GameLifecycleError("MiracleDie state source drift.")
        if state.state_kind != MIRACLE_DIE_GAIN_STATE_KIND:
            raise GameLifecycleError("MiracleDie state kind drift.")
        return cls.from_payload(state.payload)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=BATTLE_ROUND_START_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=resolve_battle_round_start,
            ),
            BattleRoundStartHookBinding(
                hook_id=TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
                source_id=TRIUMPH_RELICS_SOURCE_RULE_ID,
                request_handler=triumph_relics_selection_request,
                result_handler=apply_triumph_relics_selection_result,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=resolve_adepta_sororitas_unit_destroyed,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id=TRIUMPH_FIERY_HEART_MOVEMENT_MODIFIER_ID,
                source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.FIERY_HEART],
                handler=triumph_fiery_heart_movement_modifier,
            ),
        ),
        advance_roll_modifier_bindings=(
            AdvanceRollModifierBinding(
                modifier_id=TRIUMPH_FIERY_HEART_ADVANCE_MODIFIER_ID,
                source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.FIERY_HEART],
                handler=triumph_fiery_heart_advance_modifier,
            ),
        ),
        charge_roll_modifier_bindings=(
            ChargeRollModifierBinding(
                modifier_id=TRIUMPH_FIERY_HEART_CHARGE_MODIFIER_ID,
                source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.FIERY_HEART],
                handler=triumph_fiery_heart_charge_modifier,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=TRIUMPH_BLOODY_ROSE_WEAPON_PROFILE_MODIFIER_ID,
                source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.PETALS_OF_THE_BLOODY_ROSE],
                handler=triumph_bloody_rose_weapon_profile_modifier,
            ),
        ),
    )


def resolve_battle_round_start(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Acts of Faith battle-round start requires hook context.")
    active_player_id = _active_player_id(context.state)
    for army in context.state.army_definitions:
        if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
            continue
        gain_miracle_die(
            context.state,
            context.decisions,
            player_id=army.player_id,
            trigger=BATTLE_ROUND_START_TRIGGER,
            source_id=_battle_round_start_source_id(
                player_id=army.player_id,
                battle_round=context.state.battle_round,
            ),
            source_context={
                "active_player_id": active_player_id,
                "timing": "start_of_battle_round",
            },
        )
    return None


def triumph_relics_selection_request(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Relics of the Matriarchs requires request context.")
    for source in _eligible_triumph_relic_sources(context.state):
        if (
            _triumph_relic_selection_state_for_unit(
                context.state,
                player_id=source.army.player_id,
                unit_instance_id=source.unit.unit_instance_id,
                battle_round=context.state.battle_round,
            )
            is not None
        ):
            continue
        common_payload = _triumph_relics_common_payload(context=context, source=source)
        options = _triumph_relics_selection_options(
            common_payload=common_payload,
            max_selections=source.selection_limit.max_selections,
        )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=source.army.player_id,
            payload=validate_json_value(common_payload),
            options=options,
        )
    return None


def apply_triumph_relics_selection_result(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Relics of the Matriarchs requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Relics of the Matriarchs selection requires an actor.")
    if result.actor_id != context.request.actor_id:
        raise GameLifecycleError("Relics of the Matriarchs actor drift.")
    try:
        expected_option = context.request.option_by_id(result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError(
            "Relics of the Matriarchs selected option is not available."
        ) from exc
    if result.payload != expected_option.payload:
        raise GameLifecycleError("Relics of the Matriarchs selected option payload drift.")

    player_id = _payload_string(request_payload, key="player_id")
    if player_id != result.actor_id:
        raise GameLifecycleError("Relics of the Matriarchs player drift.")
    source_unit_id = _payload_string(request_payload, key="source_unit_instance_id")
    source = _eligible_triumph_relic_source_by_unit_id(
        context.state,
        player_id=player_id,
        source_unit_instance_id=source_unit_id,
    )
    if source is None:
        raise GameLifecycleError("Relics of the Matriarchs source unit is no longer eligible.")
    _validate_triumph_relics_request_matches_current_state(context=context, source=source)
    if (
        _triumph_relic_selection_state_for_unit(
            context.state,
            player_id=player_id,
            unit_instance_id=source_unit_id,
            battle_round=context.state.battle_round,
        )
        is not None
    ):
        raise GameLifecycleError("Relics of the Matriarchs selection already exists.")

    option_payload = _payload_object(result.payload)
    selected_relics = _triumph_relic_tuple_from_payload(option_payload)
    if len(selected_relics) > source.selection_limit.max_selections:
        raise GameLifecycleError("Relics of the Matriarchs selection exceeds current limit.")
    state_record = _triumph_relic_selection_state(
        context=context,
        source=source,
        selected_relics=selected_relics,
    )
    context.state.record_faction_rule_state(state_record)
    selection_effect = _triumph_relic_selection_effect(
        context=context,
        source=source,
        selected_relics=selected_relics,
        state_record=state_record,
    )
    context.state.record_persisting_effect(selection_effect)
    for reroll_effect in _triumph_relic_source_backed_reroll_effects(
        context=context,
        source=source,
        selected_relics=selected_relics,
    ):
        context.state.record_persisting_effect(reroll_effect)
    sync_triumph_relic_feel_no_pain_sources(context.state, player_id=player_id)
    context.decisions.event_log.append(
        TRIUMPH_RELICS_SELECTED_EVENT,
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "source_rule_id": TRIUMPH_RELICS_SOURCE_RULE_ID,
                "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.model_instance_id,
                "selected_relic_ids": [relic.value for relic in selected_relics],
                "selected_option_id": result.selected_option_id,
                "damaged_effect_id": source.selection_limit.damaged_effect_id,
                "damaged_profile_active": source.selection_limit.damaged_profile_active,
                "max_selections": source.selection_limit.max_selections,
                "baseline_max_selections": source.selection_limit.baseline_max_selections,
                "faction_rule_state": state_record.to_payload(),
                "selection_effect": selection_effect.to_payload(),
            }
        ),
    )
    return True


def active_triumph_relics_for_unit(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[TriumphRelic, ...]:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    state_record = _triumph_relic_selection_state_for_unit(
        state,
        player_id=requested_player_id,
        unit_instance_id=requested_unit_id,
        battle_round=state.battle_round,
    )
    if state_record is None:
        return ()
    payload = _payload_object(state_record.payload)
    return _triumph_relic_tuple_from_payload(payload)


def acts_of_faith_phase_limit_for_unit(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> int:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=requested_unit_id)
    if army.player_id != requested_player_id:
        raise GameLifecycleError("Acts of Faith phase limit player drift.")
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        raise GameLifecycleError("Acts of Faith phase limit requires Adepta Sororitas.")
    if not _is_adepta_sororitas_unit(unit):
        raise GameLifecycleError("Acts of Faith phase limit requires an Adepta Sororitas unit.")
    if _unit_has_active_triumph_relic_aura(
        state,
        player_id=requested_player_id,
        target_unit_instance_id=requested_unit_id,
        relic=TriumphRelic.SIMULACRUM_OF_THE_EBON_CHALICE,
    ):
        return 2
    return 1


def triumph_fiery_heart_movement_modifier(context: MovementBudgetModifierContext) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("The Fiery Heart movement modifier requires context.")
    unit, army = _unit_and_army_by_id(context.state, unit_instance_id=context.unit_instance_id)
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return context.current_movement_inches
    if not _is_adepta_sororitas_unit(unit):
        return context.current_movement_inches
    if _unit_has_active_triumph_relic_aura(
        context.state,
        player_id=army.player_id,
        target_unit_instance_id=unit.unit_instance_id,
        relic=TriumphRelic.FIERY_HEART,
    ):
        return context.current_movement_inches + 2.0
    return context.current_movement_inches


def triumph_fiery_heart_advance_modifier(
    context: AdvanceRollModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not AdvanceRollModifierContext:
        raise GameLifecycleError("The Fiery Heart advance modifier requires context.")
    unit, army = _unit_and_army_by_id(context.state, unit_instance_id=context.unit_instance_id)
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return context.current_roll_modifiers
    if not _is_adepta_sororitas_unit(unit):
        return context.current_roll_modifiers
    if not _unit_has_active_triumph_relic_aura(
        context.state,
        player_id=army.player_id,
        target_unit_instance_id=unit.unit_instance_id,
        relic=TriumphRelic.FIERY_HEART,
    ):
        return context.current_roll_modifiers
    modifier = RollModifier(
        modifier_id=(
            f"{TRIUMPH_FIERY_HEART_ADVANCE_MODIFIER_ID}:"
            f"{context.state.battle_round:02d}:{unit.unit_instance_id}"
        ),
        source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.FIERY_HEART],
        operand=1,
    )
    return (*context.current_roll_modifiers, modifier)


def triumph_fiery_heart_charge_modifier(
    context: ChargeRollModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not ChargeRollModifierContext:
        raise GameLifecycleError("The Fiery Heart charge modifier requires context.")
    unit, army = _unit_and_army_by_id(context.state, unit_instance_id=context.unit_instance_id)
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return context.current_roll_modifiers
    if not _is_adepta_sororitas_unit(unit):
        return context.current_roll_modifiers
    if not _unit_has_active_triumph_relic_aura(
        context.state,
        player_id=army.player_id,
        target_unit_instance_id=unit.unit_instance_id,
        relic=TriumphRelic.FIERY_HEART,
    ):
        return context.current_roll_modifiers
    modifier = RollModifier(
        modifier_id=(
            f"{TRIUMPH_FIERY_HEART_CHARGE_MODIFIER_ID}:"
            f"{context.state.battle_round:02d}:{unit.unit_instance_id}"
        ),
        source_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[TriumphRelic.FIERY_HEART],
        operand=1,
    )
    return (*context.current_roll_modifiers, modifier)


def triumph_bloody_rose_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Petals of the Bloody Rose weapon modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    unit, army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return context.weapon_profile
    if not _is_adepta_sororitas_unit(unit):
        return context.weapon_profile
    if not _unit_has_active_triumph_relic_aura(
        context.state,
        player_id=army.player_id,
        target_unit_instance_id=unit.unit_instance_id,
        relic=TriumphRelic.PETALS_OF_THE_BLOODY_ROSE,
    ):
        return context.weapon_profile
    return replace(
        context.weapon_profile,
        armor_penetration=_improve_armor_penetration(
            context.weapon_profile.armor_penetration,
            bonus=1,
        ),
        source_ids=_source_ids_with_triumph_relic(
            context.weapon_profile.source_ids,
            relic=TriumphRelic.PETALS_OF_THE_BLOODY_ROSE,
        ),
    )


def triumph_argent_shroud_wound_reroll_values(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
    weapon_profile: WeaponProfile,
) -> tuple[int, ...]:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("Argent Shroud wound reroll requires WeaponProfile.")
    if weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return ()
    unit, army = _unit_and_army_by_id(state, unit_instance_id=requested_unit_id)
    if army.player_id != requested_player_id:
        raise GameLifecycleError("Argent Shroud wound reroll player drift.")
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return ()
    if not _is_adepta_sororitas_unit(unit):
        return ()
    if not _unit_has_active_triumph_relic_aura(
        state,
        player_id=requested_player_id,
        target_unit_instance_id=requested_unit_id,
        relic=TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD,
    ):
        return ()
    return (1,)


def sync_triumph_relic_feel_no_pain_sources(state: GameState, *, player_id: str) -> None:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    army = _adepta_sororitas_army_for_player(state, player_id=requested_player_id)
    if army is None:
        raise GameLifecycleError("Triumph Relics Feel No Pain sync requires Adepta Sororitas.")
    for unit in army.units:
        if not _is_adepta_sororitas_unit(unit):
            continue
        active = _unit_has_active_triumph_relic_aura(
            state,
            player_id=requested_player_id,
            target_unit_instance_id=unit.unit_instance_id,
            relic=TriumphRelic.ICON_OF_THE_VALOROUS_HEART,
        )
        for model in unit.own_models:
            existing = tuple(
                source
                for source in state.feel_no_pain_sources_for_model(
                    model_instance_id=model.model_instance_id,
                )
                if not source.source_id.startswith(TRIUMPH_RELICS_FEEL_NO_PAIN_SOURCE_PREFIX)
            )
            updated = existing
            if active and model.is_alive:
                updated = tuple(
                    sorted(
                        (
                            *existing,
                            FeelNoPainSource(
                                source_id=(
                                    f"{TRIUMPH_RELICS_FEEL_NO_PAIN_SOURCE_PREFIX}:"
                                    f"{unit.unit_instance_id}:{model.model_instance_id}:"
                                    f"round-{state.battle_round:02d}"
                                ),
                                threshold=6,
                            ),
                        ),
                        key=lambda source: source.source_id,
                    )
                )
            if updated:
                state.record_model_feel_no_pain_sources(
                    model_instance_id=model.model_instance_id,
                    sources=updated,
                )
            else:
                state.clear_model_feel_no_pain_sources(
                    model_instance_id=model.model_instance_id,
                )


def resolve_adepta_sororitas_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Acts of Faith unit-destroyed hook requires context.")
    army = _adepta_sororitas_army_for_player(context.state, player_id=context.destroyed_player_id)
    if army is None:
        return
    destroyed_unit = _unit_by_id(army, unit_instance_id=context.destroyed_unit_instance_id)
    if destroyed_unit is None:
        raise GameLifecycleError("Destroyed Adepta Sororitas unit was not found in its army.")
    if not _is_adepta_sororitas_unit(destroyed_unit):
        return
    gain_miracle_die(
        context.state,
        context.decisions,
        player_id=context.destroyed_player_id,
        trigger=UNIT_DESTROYED_TRIGGER,
        source_id=_unit_destroyed_source_id(
            player_id=context.destroyed_player_id,
            model_destroyed_event_id=context.model_destroyed_event_id,
        ),
        source_context={
            "completed_phase": context.completed_phase.value,
            "destroying_player_id": context.destroying_player_id,
            "destroyed_player_id": context.destroyed_player_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "model_destroyed_payload": validate_json_value(context.model_destroyed_payload),
        },
    )


def gain_miracle_die(
    state: GameState,
    decisions: DecisionController,
    *,
    player_id: str,
    trigger: str,
    source_id: str,
    source_context: object,
) -> MiracleDie | None:
    _validate_state(state)
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Acts of Faith requires a DecisionController.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_trigger = _validate_gain_trigger(trigger)
    validated_source_context = _payload_object(source_context, field_name="source_context")
    if _adepta_sororitas_army_for_player(state, player_id=requested_player_id) is None:
        raise GameLifecycleError("Acts of Faith can gain Miracle dice only for Adepta Sororitas.")
    if _gain_source_exists(state, player_id=requested_player_id, source_id=requested_source_id):
        return None
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Acts of Faith Miracle dice gain requires a battle phase.")

    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Acts of Faith Miracle dice gain",
            roll_type=MIRACLE_DIE_GAIN_ROLL_TYPE,
            actor_id=requested_player_id,
            reroll_forbidden_rule_ids=(SOURCE_RULE_ID,),
        )
    )
    die_index = _next_miracle_die_index(state, player_id=requested_player_id)
    die = MiracleDie(
        miracle_die_id=f"{requested_player_id}:miracle-die-{die_index:06d}",
        player_id=requested_player_id,
        value=roll_state.current_total,
        gain_trigger=requested_trigger,
        source_id=requested_source_id,
        battle_round=state.battle_round,
        phase=current_phase,
        roll_state=roll_state,
    )
    state_record = FactionRuleState(
        state_id=f"{HOOK_ID}:{requested_player_id}:miracle-die-{die_index:06d}",
        player_id=requested_player_id,
        faction_id=ADEPTA_SORORITAS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=MIRACLE_DIE_GAIN_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=f"{requested_source_id}:request",
        result_id=f"{requested_source_id}:result",
        payload=validate_json_value(
            {
                **die.to_payload(),
                "pool_index": die_index,
                "source_context": validate_json_value(validated_source_context),
            }
        ),
    )
    state.record_faction_rule_state(state_record)
    decisions.event_log.append(
        MIRACLE_DIE_GAINED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": current_phase.value,
            "player_id": requested_player_id,
            "faction_id": ADEPTA_SORORITAS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "trigger": requested_trigger,
            "source_id": requested_source_id,
            "miracle_die": die.to_payload(),
            "faction_rule_state": state_record.to_payload(),
            "source_context": validate_json_value(validated_source_context),
        },
    )
    return die


def spend_miracle_die(
    state: GameState,
    decisions: DecisionController,
    *,
    player_id: str,
    unit_instance_id: str,
    miracle_die_id: str,
    source_id: str,
    source_context: object,
) -> MiracleDie:
    _validate_state(state)
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Acts of Faith requires a DecisionController.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_die_id = _validate_identifier("miracle_die_id", miracle_die_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    validated_source_context = _payload_object(source_context, field_name="source_context")
    if _spend_source_exists(state, player_id=requested_player_id, source_id=requested_source_id):
        raise GameLifecycleError("Acts of Faith spend source has already been recorded.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Acts of Faith Miracle dice spend requires a battle phase.")
    unit, army = _unit_and_army_by_id(state, unit_instance_id=requested_unit_id)
    if army.player_id != requested_player_id:
        raise GameLifecycleError("Acts of Faith Miracle dice spend player drift.")
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        raise GameLifecycleError("Acts of Faith can spend Miracle dice only for Adepta Sororitas.")
    if not _is_adepta_sororitas_unit(unit):
        raise GameLifecycleError("Acts of Faith spend requires an Adepta Sororitas unit.")
    phase_limit = acts_of_faith_phase_limit_for_unit(
        state,
        player_id=requested_player_id,
        unit_instance_id=requested_unit_id,
    )
    for die in miracle_dice_pool(state, player_id=requested_player_id):
        if die.miracle_die_id != requested_die_id:
            continue
        spent_this_phase = _miracle_die_spend_count_for_unit_phase(
            state,
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
            battle_round=state.battle_round,
            phase=current_phase,
        )
        if spent_this_phase >= phase_limit:
            raise GameLifecycleError("Acts of Faith phase limit has already been reached.")
        spend_index = _next_miracle_die_spend_index(state, player_id=requested_player_id)
        state_record = FactionRuleState(
            state_id=f"{HOOK_ID}:{requested_player_id}:miracle-die-spent-{spend_index:06d}",
            player_id=requested_player_id,
            faction_id=ADEPTA_SORORITAS_FACTION_ID,
            source_rule_id=SOURCE_RULE_ID,
            state_kind=MIRACLE_DIE_SPEND_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id=f"{requested_source_id}:request",
            result_id=f"{requested_source_id}:result",
            payload=validate_json_value(
                {
                    "miracle_die_id": die.miracle_die_id,
                    "player_id": requested_player_id,
                    "value": die.value,
                    "source_id": requested_source_id,
                    "source_rule_id": SOURCE_RULE_ID,
                    "battle_round": state.battle_round,
                    "phase": current_phase.value,
                    "unit_instance_id": requested_unit_id,
                    "acts_of_faith_phase_limit": phase_limit,
                    "source_context": validate_json_value(validated_source_context),
                }
            ),
        )
        state.record_faction_rule_state(state_record)
        decisions.event_log.append(
            MIRACLE_DIE_SPENT_EVENT,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": current_phase.value,
                "player_id": requested_player_id,
                "faction_id": ADEPTA_SORORITAS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "source_id": requested_source_id,
                "unit_instance_id": requested_unit_id,
                "acts_of_faith_phase_limit": phase_limit,
                "miracle_die": die.to_payload(),
                "faction_rule_state": state_record.to_payload(),
                "source_context": validate_json_value(validated_source_context),
            },
        )
        return die
    raise GameLifecycleError("Requested Miracle die is not available in the pool.")


def miracle_dice_pool(state: GameState, *, player_id: str) -> tuple[MiracleDie, ...]:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    spent_die_ids = _spent_miracle_die_ids(state, player_id=requested_player_id)
    return tuple(
        die
        for die in (
            MiracleDie.from_state(gain_state)
            for gain_state in _miracle_die_gain_states(state, player_id=requested_player_id)
        )
        if die.miracle_die_id not in spent_die_ids
    )


def miracle_dice_values(state: GameState, *, player_id: str) -> tuple[int, ...]:
    return tuple(die.value for die in miracle_dice_pool(state, player_id=player_id))


def _eligible_triumph_relic_sources(state: GameState) -> tuple[_TriumphRelicsEligibleSource, ...]:
    _validate_state(state)
    sources: list[_TriumphRelicsEligibleSource] = []
    for army in sorted(state.army_definitions, key=lambda item: item.player_id):
        if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
            continue
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            if not _is_triumph_unit(unit):
                continue
            alive_models = unit.alive_own_models()
            if not alive_models:
                continue
            if len(alive_models) != 1:
                raise GameLifecycleError("Triumph Relics source model is ambiguous.")
            model = alive_models[0]
            if model.model_instance_id not in _current_battlefield_model_ids(state, unit=unit):
                continue
            selection_limit = catalog_damaged_ability_selection_limit_for_model(
                unit=unit,
                model=model,
                selection_group=TRIUMPH_RELICS_SELECTION_GROUP,
            )
            if selection_limit is None:
                raise GameLifecycleError(
                    "Triumph Relics requires the source-backed DAMAGED selection limit."
                )
            sources.append(
                _TriumphRelicsEligibleSource(
                    army=army,
                    unit=unit,
                    model_instance_id=model.model_instance_id,
                    selection_limit=selection_limit,
                )
            )
    return tuple(sources)


def _eligible_triumph_relic_source_by_unit_id(
    state: GameState,
    *,
    player_id: str,
    source_unit_instance_id: str,
) -> _TriumphRelicsEligibleSource | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    for source in _eligible_triumph_relic_sources(state):
        if source.army.player_id == requested_player_id and source.unit.unit_instance_id == (
            requested_unit_id
        ):
            return source
    return None


def _triumph_relics_common_payload(
    *,
    context: BattleRoundStartRequestContext,
    source: _TriumphRelicsEligibleSource,
) -> dict[str, JsonValue]:
    return {
        "submission_kind": TRIUMPH_RELICS_SELECTION_KIND,
        "selection_kind": TRIUMPH_RELICS_SELECTION_KIND,
        "effect_kind": TRIUMPH_RELICS_EFFECT_KIND,
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": context.state.active_player_id,
        "actor_may_be_non_active": True,
        "player_id": source.army.player_id,
        "faction_id": ADEPTA_SORORITAS_FACTION_ID,
        "source_rule_id": TRIUMPH_RELICS_SOURCE_RULE_ID,
        "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
        "source_unit_instance_id": source.unit.unit_instance_id,
        "source_model_instance_id": source.model_instance_id,
        "damaged_effect_id": source.selection_limit.damaged_effect_id,
        "damaged_effect_source_id": source.selection_limit.source_id,
        "damaged_profile_active": source.selection_limit.damaged_profile_active,
        "max_selections": source.selection_limit.max_selections,
        "baseline_max_selections": source.selection_limit.baseline_max_selections,
        "selection_group": source.selection_limit.selection_group,
        "available_relic_ids": [relic.value for relic in TriumphRelic],
    }


def _triumph_relics_selection_options(
    *,
    common_payload: dict[str, JsonValue],
    max_selections: int,
) -> tuple[DecisionOption, ...]:
    limit = _validate_positive_int("Relics of the Matriarchs max_selections", max_selections)
    relics = tuple(TriumphRelic)
    options: list[DecisionOption] = []
    for selection_count in range(limit + 1):
        for selected_relics in combinations(relics, selection_count):
            selected: tuple[TriumphRelic, ...] = tuple(selected_relics)
            selected_ids = tuple(relic.value for relic in selected)
            option_suffix = "none" if not selected_ids else "-".join(selected_ids)
            label = (
                "Select no Relics"
                if not selected
                else "Select " + " and ".join(_TRIUMPH_RELIC_LABELS[relic] for relic in selected)
            )
            options.append(
                DecisionOption(
                    option_id=f"triumph-relics-{option_suffix}",
                    label=label,
                    payload=validate_json_value(
                        {
                            "submission_kind": TRIUMPH_RELICS_SELECTION_KIND,
                            "selection_kind": TRIUMPH_RELICS_SELECTION_KIND,
                            "effect_kind": TRIUMPH_RELICS_EFFECT_KIND,
                            "game_id": common_payload["game_id"],
                            "battle_round": common_payload["battle_round"],
                            "player_id": common_payload["player_id"],
                            "source_rule_id": TRIUMPH_RELICS_SOURCE_RULE_ID,
                            "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
                            "source_unit_instance_id": common_payload["source_unit_instance_id"],
                            "selected_relic_ids": list(selected_ids),
                            "selected_relic_source_rule_ids": [
                                _TRIUMPH_RELIC_SOURCE_RULE_IDS[relic] for relic in selected
                            ],
                        }
                    ),
                )
            )
    return tuple(options)


def _validate_triumph_relics_request_matches_current_state(
    *,
    context: BattleRoundStartResultContext,
    source: _TriumphRelicsEligibleSource,
) -> None:
    payload = _payload_object(context.request.payload)
    if _payload_string(payload, key="game_id") != context.state.game_id:
        raise GameLifecycleError("Relics of the Matriarchs request game_id drift.")
    if _payload_int(payload, key="battle_round") != context.state.battle_round:
        raise GameLifecycleError("Relics of the Matriarchs request battle_round drift.")
    if _payload_string(payload, key="phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Relics of the Matriarchs request phase drift.")
    if _payload_string(payload, key="active_player_id") != context.state.active_player_id:
        raise GameLifecycleError("Relics of the Matriarchs active player drift.")
    if _payload_string(payload, key="player_id") != source.army.player_id:
        raise GameLifecycleError("Relics of the Matriarchs request player drift.")
    if _payload_string(payload, key="source_unit_instance_id") != source.unit.unit_instance_id:
        raise GameLifecycleError("Relics of the Matriarchs source unit drift.")
    if _payload_string(payload, key="source_model_instance_id") != source.model_instance_id:
        raise GameLifecycleError("Relics of the Matriarchs source model drift.")
    if _payload_string(payload, key="damaged_effect_id") != (
        source.selection_limit.damaged_effect_id
    ):
        raise GameLifecycleError("Relics of the Matriarchs DAMAGED effect drift.")
    if payload.get("damaged_profile_active") != source.selection_limit.damaged_profile_active:
        raise GameLifecycleError("Relics of the Matriarchs DAMAGED active drift.")
    if _payload_int(payload, key="max_selections") != source.selection_limit.max_selections:
        raise GameLifecycleError("Relics of the Matriarchs max selection drift.")
    if _payload_int(payload, key="baseline_max_selections") != (
        source.selection_limit.baseline_max_selections
    ):
        raise GameLifecycleError("Relics of the Matriarchs baseline selection drift.")
    if _payload_identifier_tuple(payload, "available_relic_ids") != tuple(
        relic.value for relic in TriumphRelic
    ):
        raise GameLifecycleError("Relics of the Matriarchs available relic drift.")


def _triumph_relic_tuple_from_payload(payload: dict[str, JsonValue]) -> tuple[TriumphRelic, ...]:
    relic_ids = _payload_identifier_tuple(payload, "selected_relic_ids")
    selected: list[TriumphRelic] = []
    seen: set[TriumphRelic] = set()
    for relic_id in relic_ids:
        relic = _triumph_relic_from_token(relic_id)
        if relic in seen:
            raise GameLifecycleError("Relics of the Matriarchs selection contains duplicates.")
        seen.add(relic)
        selected.append(relic)
    return tuple(selected)


def _triumph_relic_from_token(token: object) -> TriumphRelic:
    if type(token) is TriumphRelic:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Triumph Relic token must be a string.")
    try:
        return TriumphRelic(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Triumph Relic token: {token}.") from exc


def _triumph_relic_selection_state(
    *,
    context: BattleRoundStartResultContext,
    source: _TriumphRelicsEligibleSource,
    selected_relics: tuple[TriumphRelic, ...],
) -> FactionRuleState:
    return FactionRuleState(
        state_id=(
            f"{TRIUMPH_RELICS_HOOK_ID}:{source.army.player_id}:"
            f"{source.unit.unit_instance_id}:round-{context.state.battle_round:02d}:selection"
        ),
        player_id=source.army.player_id,
        faction_id=ADEPTA_SORORITAS_FACTION_ID,
        source_rule_id=TRIUMPH_RELICS_SOURCE_RULE_ID,
        state_kind=TRIUMPH_RELICS_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": TRIUMPH_RELICS_SELECTION_KIND,
                "effect_kind": TRIUMPH_RELICS_EFFECT_KIND,
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.state.active_player_id,
                "player_id": source.army.player_id,
                "faction_id": ADEPTA_SORORITAS_FACTION_ID,
                "source_rule_id": TRIUMPH_RELICS_SOURCE_RULE_ID,
                "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.model_instance_id,
                "selected_relic_ids": [relic.value for relic in selected_relics],
                "selected_relic_source_rule_ids": [
                    _TRIUMPH_RELIC_SOURCE_RULE_IDS[relic] for relic in selected_relics
                ],
                "damaged_effect_id": source.selection_limit.damaged_effect_id,
                "damaged_effect_source_id": source.selection_limit.source_id,
                "damaged_profile_active": source.selection_limit.damaged_profile_active,
                "max_selections": source.selection_limit.max_selections,
                "baseline_max_selections": source.selection_limit.baseline_max_selections,
                "selection_group": source.selection_limit.selection_group,
            }
        ),
    )


def _triumph_relic_selection_state_for_unit(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
    battle_round: int,
) -> FactionRuleState | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    states = tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=TRIUMPH_RELICS_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == TRIUMPH_RELICS_SOURCE_RULE_ID
        and _payload_object(record.payload).get("battle_round") == requested_round
        and _payload_object(record.payload).get("source_unit_instance_id") == requested_unit_id
    )
    if len(states) > 1:
        raise GameLifecycleError("Relics of the Matriarchs state is ambiguous.")
    return states[0] if states else None


def _triumph_relic_selection_states_for_player_round(
    state: GameState,
    *,
    player_id: str,
    battle_round: int,
) -> tuple[FactionRuleState, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    return tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=TRIUMPH_RELICS_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == TRIUMPH_RELICS_SOURCE_RULE_ID
        and _payload_object(record.payload).get("battle_round") == requested_round
    )


def _triumph_relic_selection_effect(
    *,
    context: BattleRoundStartResultContext,
    source: _TriumphRelicsEligibleSource,
    selected_relics: tuple[TriumphRelic, ...],
    state_record: FactionRuleState,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=(
            f"{TRIUMPH_RELICS_HOOK_ID}:{source.unit.unit_instance_id}:"
            f"{context.result.result_id}:selection"
        ),
        source_rule_id=TRIUMPH_RELICS_SOURCE_RULE_ID,
        owner_player_id=source.army.player_id,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.start_battle_round(battle_round=context.state.battle_round + 1),
        effect_payload=validate_json_value(
            {
                "effect_kind": TRIUMPH_RELICS_PERSISTING_EFFECT_KIND,
                "selection_state_id": state_record.state_id,
                "selection_result_id": context.result.result_id,
                "player_id": source.army.player_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.model_instance_id,
                "selected_relic_ids": [relic.value for relic in selected_relics],
                "source_rule_id": TRIUMPH_RELICS_SOURCE_RULE_ID,
                "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
            }
        ),
    )


def _triumph_relic_source_backed_reroll_effects(
    *,
    context: BattleRoundStartResultContext,
    source: _TriumphRelicsEligibleSource,
    selected_relics: tuple[TriumphRelic, ...],
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    target_unit_ids = _friendly_adepta_unit_ids(source.army)
    if TriumphRelic.CENSER_OF_THE_SACRED_ROSE in selected_relics and target_unit_ids:
        effects.append(
            _triumph_relic_reroll_effect(
                context=context,
                source=source,
                target_unit_ids=target_unit_ids,
                relic=TriumphRelic.CENSER_OF_THE_SACRED_ROSE,
                roll_kind="battle_shock",
                timing_window="battle_shock_test",
                eligible_roll_type="battle_shock_roll",
            )
        )
    if TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD in selected_relics and target_unit_ids:
        effects.append(
            _triumph_relic_reroll_effect(
                context=context,
                source=source,
                target_unit_ids=target_unit_ids,
                relic=TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD,
                roll_kind="ranged_wound",
                timing_window="attack_sequence.wound",
                eligible_roll_type="wound_roll",
            )
        )
    return tuple(effects)


def _triumph_relic_reroll_effect(
    *,
    context: BattleRoundStartResultContext,
    source: _TriumphRelicsEligibleSource,
    target_unit_ids: tuple[str, ...],
    relic: TriumphRelic,
    roll_kind: str,
    timing_window: str,
    eligible_roll_type: str,
) -> PersistingEffect:
    requested_roll_kind = _validate_identifier("roll_kind", roll_kind)
    source_payload = validate_json_value(
        {
            "effect_kind": TRIUMPH_RELICS_REROLL_EFFECT_KIND,
            "relic_id": relic.value,
            "roll_kind": requested_roll_kind,
            "player_id": source.army.player_id,
            "battle_round": context.state.battle_round,
            "selection_result_id": context.result.result_id,
            "source_rule_id": _TRIUMPH_RELIC_SOURCE_RULE_IDS[relic],
            "hook_id": TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
            "source_unit_instance_id": source.unit.unit_instance_id,
            "aura_source_unit_instance_id": source.unit.unit_instance_id,
            "aura_range_inches": TRIUMPH_RELICS_AURA_RANGE_INCHES,
            **_triumph_relic_reroll_source_payload_extra(relic),
        }
    )
    permission = RerollPermission(
        source_id=(
            f"{TRIUMPH_RELICS_HOOK_ID}:{source.unit.unit_instance_id}:"
            f"{context.result.result_id}:{relic.value}:{requested_roll_kind}"
        ),
        timing_window=timing_window,
        owning_player_id=source.army.player_id,
        eligible_roll_type=eligible_roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    return PersistingEffect(
        effect_id=(
            f"{TRIUMPH_RELICS_HOOK_ID}:{source.unit.unit_instance_id}:"
            f"{context.result.result_id}:{relic.value}:{requested_roll_kind}:reroll"
        ),
        source_rule_id=_TRIUMPH_RELIC_SOURCE_RULE_IDS[relic],
        owner_player_id=source.army.player_id,
        target_unit_instance_ids=target_unit_ids,
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.start_battle_round(battle_round=context.state.battle_round + 1),
        effect_payload=source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=target_unit_ids,
            permission=permission,
            source_payload=source_payload,
        ),
    )


def _triumph_relic_reroll_source_payload_extra(relic: TriumphRelic) -> dict[str, JsonValue]:
    requested_relic = _triumph_relic_from_token(relic)
    if requested_relic is TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD:
        return {
            "attack_kind": "ranged",
            "conditional_wound_reroll": {"reroll_unmodified_values": [1]},
        }
    return {}


def _unit_has_active_triumph_relic_aura(
    state: GameState,
    *,
    player_id: str,
    target_unit_instance_id: str,
    relic: TriumphRelic,
) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_target_unit_id = _validate_identifier(
        "target_unit_instance_id",
        target_unit_instance_id,
    )
    requested_relic = _triumph_relic_from_token(relic)
    target_unit, target_army = _unit_and_army_by_id(
        state,
        unit_instance_id=requested_target_unit_id,
    )
    if target_army.player_id != requested_player_id:
        raise GameLifecycleError("Triumph Relics aura target player drift.")
    if target_army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return False
    if not _is_adepta_sororitas_unit(target_unit):
        return False
    for state_record in _triumph_relic_selection_states_for_player_round(
        state,
        player_id=requested_player_id,
        battle_round=state.battle_round,
    ):
        payload = _payload_object(state_record.payload)
        selected_relics = _triumph_relic_tuple_from_payload(payload)
        if requested_relic not in selected_relics:
            continue
        source_unit_id = _payload_string(payload, key="source_unit_instance_id")
        if (
            _eligible_triumph_relic_source_by_unit_id(
                state,
                player_id=requested_player_id,
                source_unit_instance_id=source_unit_id,
            )
            is None
        ):
            continue
        if _unit_within_range_of_source_unit(
            state,
            source_unit_instance_id=source_unit_id,
            target_unit_instance_id=requested_target_unit_id,
            range_inches=TRIUMPH_RELICS_AURA_RANGE_INCHES,
        ):
            return True
    return False


def _friendly_adepta_unit_ids(army: ArmyDefinition) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Triumph Relics friendly unit lookup requires ArmyDefinition.")
    return tuple(unit.unit_instance_id for unit in army.units if _is_adepta_sororitas_unit(unit))


def _unit_within_range_of_source_unit(
    state: GameState,
    *,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
    range_inches: float,
) -> bool:
    requested_source_id = _validate_identifier(
        "source_unit_instance_id",
        source_unit_instance_id,
    )
    requested_target_id = _validate_identifier(
        "target_unit_instance_id",
        target_unit_instance_id,
    )
    if type(range_inches) not in {float, int}:
        raise GameLifecycleError("Triumph Relics aura range must be numeric.")
    if float(range_inches) <= 0.0:
        raise GameLifecycleError("Triumph Relics aura range must be positive.")
    source_models = _unit_geometry_models(state=state, unit_instance_id=requested_source_id)
    target_models = _unit_geometry_models(state=state, unit_instance_id=requested_target_id)
    if not source_models or not target_models:
        return False
    return any(
        shapely_backend.base_footprint_distance(
            source_model.base,
            source_model.pose,
            target_model.base,
            target_model.pose,
        )
        <= float(range_inches)
        for source_model in source_models
        for target_model in target_models
    )


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Triumph Relics geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_or_none(unit_instance_id)
    if unit_placement is None:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _current_battlefield_model_ids(
    state: GameState,
    *,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Triumph Relics battlefield lookup requires battlefield_state.")
    placement = state.battlefield_state.unit_placement_or_none(unit.unit_instance_id)
    if placement is None:
        return ()
    model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Triumph Relics placement contains unknown model.")
        if model.is_alive:
            current_ids.append(model.model_instance_id)
    return tuple(sorted(current_ids))


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    _validate_state(state)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army
    raise GameLifecycleError("Unit was not found in the game state.")


def _is_triumph_unit(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Triumph Relics unit lookup requires UnitInstance.")
    return unit.datasheet_id == TRIUMPH_OF_SAINT_KATHERINE_DATASHEET_ID


def _miracle_die_spend_count_for_unit_phase(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
    battle_round: int,
    phase: BattlePhase,
) -> int:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_phase = _battle_phase_from_token(phase)
    count = 0
    for state_record in _miracle_die_spend_states(state, player_id=player_id):
        payload = _payload_object(state_record.payload)
        if payload.get("unit_instance_id") != requested_unit_id:
            continue
        if payload.get("battle_round") != requested_round:
            continue
        if payload.get("phase") != requested_phase.value:
            continue
        count += 1
    return count


def _improve_armor_penetration(
    armor_penetration: CharacteristicValue,
    *,
    bonus: int,
) -> CharacteristicValue:
    if type(armor_penetration) is not CharacteristicValue:
        raise GameLifecycleError("Triumph Relics AP modifier requires value.")
    if armor_penetration.characteristic is not Characteristic.ARMOR_PENETRATION:
        raise GameLifecycleError("Triumph Relics AP characteristic drift.")
    amount = _validate_positive_int("armor_penetration_bonus", bonus)
    return CharacteristicValue.from_raw(
        Characteristic.ARMOR_PENETRATION,
        armor_penetration.final - amount,
    )


def _source_ids_with_triumph_relic(
    source_ids: tuple[str, ...],
    *,
    relic: TriumphRelic,
) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Triumph Relics source_ids must be a tuple.")
    source_id = _TRIUMPH_RELIC_SOURCE_RULE_IDS[_triumph_relic_from_token(relic)]
    if source_id in source_ids:
        return source_ids
    return tuple(sorted((*source_ids, source_id)))


def _battle_round_start_source_id(*, player_id: str, battle_round: int) -> str:
    return f"{SOURCE_RULE_ID}:battle-round-start:round-{battle_round:02d}:player-{player_id}"


def _unit_destroyed_source_id(*, player_id: str, model_destroyed_event_id: str) -> str:
    requested_event_id = _validate_identifier("model_destroyed_event_id", model_destroyed_event_id)
    return f"{SOURCE_RULE_ID}:unit-destroyed:{requested_event_id}:player-{player_id}"


def _adepta_sororitas_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return None
    return army


def _unit_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    return None


def _is_adepta_sororitas_unit(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Acts of Faith unit lookup requires UnitInstance.")
    return any(
        _canonical_keyword(keyword) == ADEPTA_SORORITAS_FACTION_KEYWORD
        for keyword in unit.faction_keywords
    )


def _miracle_die_gain_states(state: GameState, *, player_id: str) -> tuple[FactionRuleState, ...]:
    return tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=player_id,
            state_kind=MIRACLE_DIE_GAIN_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == SOURCE_RULE_ID
    )


def _miracle_die_spend_states(state: GameState, *, player_id: str) -> tuple[FactionRuleState, ...]:
    return tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=player_id,
            state_kind=MIRACLE_DIE_SPEND_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == SOURCE_RULE_ID
    )


def _spent_miracle_die_ids(state: GameState, *, player_id: str) -> frozenset[str]:
    spent_ids: set[str] = set()
    for spend_state in _miracle_die_spend_states(state, player_id=player_id):
        payload = _payload_object(spend_state.payload, field_name="Miracle die spend payload")
        spent_ids.add(_payload_string(payload, key="miracle_die_id"))
    return frozenset(spent_ids)


def _gain_source_exists(state: GameState, *, player_id: str, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for gain_state in _miracle_die_gain_states(state, player_id=player_id):
        payload = _payload_object(gain_state.payload, field_name="Miracle die gain payload")
        if _payload_string(payload, key="source_id") == requested_source_id:
            return True
    return False


def _spend_source_exists(state: GameState, *, player_id: str, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for spend_state in _miracle_die_spend_states(state, player_id=player_id):
        payload = _payload_object(spend_state.payload, field_name="Miracle die spend payload")
        if _payload_string(payload, key="source_id") == requested_source_id:
            return True
    return False


def _next_miracle_die_index(state: GameState, *, player_id: str) -> int:
    return len(_miracle_die_gain_states(state, player_id=player_id)) + 1


def _next_miracle_die_spend_index(state: GameState, *, player_id: str) -> int:
    return len(_miracle_die_spend_states(state, player_id=player_id)) + 1


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Acts of Faith battle-round start requires active player.")
    return state.active_player_id


def _validate_state(state: object) -> GameState:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Acts of Faith requires GameState.")
    return state


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_gain_trigger(value: object) -> str:
    trigger = _validate_identifier("gain trigger", value)
    if trigger not in _SUPPORTED_GAIN_TRIGGERS:
        raise GameLifecycleError(f"Unsupported Acts of Faith gain trigger: {trigger}.")
    return trigger


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Acts of Faith phase must be a BattlePhase token.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Acts of Faith phase: {token}.") from exc
