from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.engine import attack_sequence_decision_family as _asdf
from warhammer40k_core.engine import battle_formation_hooks as _bf
from warhammer40k_core.engine import battle_round_hooks as _br
from warhammer40k_core.engine import battle_shock_continuation_restore as _bs_restore
from warhammer40k_core.engine import battle_shock_lifecycle_authority as _bsa
from warhammer40k_core.engine import catalog_model_materialization_decision_dispatch as _cmmd
from warhammer40k_core.engine import (
    catalog_selected_target_battle_shock_continuation as _selected_target_bs,
)
from warhammer40k_core.engine import catalog_start_battle_keyword_choice as _sbkc
from warhammer40k_core.engine import (
    catalog_unit_move_completed_mortal_wounds_runtime as _catalog_move_mw,
)
from warhammer40k_core.engine import charge_declaration_hooks as _cd
from warhammer40k_core.engine import charge_roll_dispatch as _charge_rerolls
from warhammer40k_core.engine import command_phase_start_hooks as _cs
from warhammer40k_core.engine import core_stratagem_mortal_wound_continuation as _stratagem_mw
from warhammer40k_core.engine import fight_activation_abilities as _fa
from warhammer40k_core.engine import fight_unit_selected_hooks as _fu
from warhammer40k_core.engine import mortal_wound_model_allocation as _mw_model
from warhammer40k_core.engine import movement_phase_end_mortal_wounds as _movement_mw
from warhammer40k_core.engine import physical_proposal_context as _physical_context
from warhammer40k_core.engine import primary_mission_pending_request_integrity as _pmpri
from warhammer40k_core.engine import primary_mission_restore_integrity as _pmri
from warhammer40k_core.engine import primary_reserve_entry_lifecycle_integrity as _preli
from warhammer40k_core.engine import psychic_modifier_history_origin as _pmh
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine import target_replacement_dispatch as _target_replacement_dispatch
from warhammer40k_core.engine import unit_split_dispatch as _unit_split_dispatch
from warhammer40k_core.engine.advance_hooks import SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    invalid_destroyed_transport_disembark_proposal_status,
    is_destroyed_transport_disembark_proposal_request,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_shock_test_service import (
    is_stratagem_battle_shock_reroll_request,
)
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    invalid_any_phase_once_per_battle_status,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    CatalogModelMaterializationRuntime,
)
from warhammer40k_core.engine.catalog_movement_end_selected_target_effects import (
    SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE,
    invalid_catalog_movement_end_target_effect_status,
)
from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
    SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE,
    invalid_catalog_movement_target_pair_status,
)
from warhammer40k_core.engine.catalog_post_fight_selected_target_runtime import (
    SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
    SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
)
from warhammer40k_core.engine.charge_selected_target_validation import (
    invalid_charge_roll_reroll_context_status,
)
from warhammer40k_core.engine.cult_ambush import (
    SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
    SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE,
    apply_cult_ambush_marker_placement_decision,
    apply_cult_ambush_placement,
    apply_cult_ambush_resurgence_decision,
    invalid_cult_ambush_marker_placement_status,
    invalid_cult_ambush_placement_status,
    invalid_cult_ambush_resurgence_status,
    is_cult_ambush_placement_request,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_dispatch import (
    DecisionDispatchContract,
    DecisionDispatchHandler,
    DecisionDispatchRegistry,
    build_decision_dispatch_registry,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    invalid_deployment_placement_status,
    is_deployment_placement_request,
)
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.enhancement_effects import apply_enhancement_effects
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
    runtime_content_activation_for_armies,
)
from warhammer40k_core.engine.faction_content.stratagem_record_merge import (
    combine_stratagem_indexes_with_runtime_overrides,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_phase_decisions import (
    FIGHT_PHASE_FACTION_RULE_DECISION_TYPES,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.finite_decision_validation import (
    invalid_finite_decision_status as _invalid_finite_decision_status,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.hazard import CORE_HAZARD_ROLLS_RULE_ID
from warhammer40k_core.engine.healing_decision_dispatch import (
    HEALING_DECISION_TYPES,
    PARAMETERIZED_HEALING_DECISION_TYPES,
    apply_recorded_healing_decision,
    invalid_healing_decision_status,
)
from warhammer40k_core.engine.lifecycle_attack_prevalidation import (
    fight_attack_sequence_is_active_for_request,
)
from warhammer40k_core.engine.lifecycle_payload_consistency import (
    validate_pending_battlefield_request_consistency,
)
from warhammer40k_core.engine.lifecycle_reaction_queue import (
    validate_reaction_queue_consistency,
)
from warhammer40k_core.engine.lifecycle_restore_consistency import validate_payload_consistency
from warhammer40k_core.engine.lifecycle_runtime_payloads import (
    payload_bool as _payload_bool,
)
from warhammer40k_core.engine.lifecycle_runtime_payloads import (
    runtime_mortal_wound_source_context_phase as _runtime_mortal_wound_source_context_phase,
)
from warhammer40k_core.engine.lifecycle_setup_reactive import (
    apply_setup_reactive_lifecycle_decision_if_applicable,
    invalid_setup_reactive_lifecycle_status,
    is_setup_reactive_lifecycle_request,
)
from warhammer40k_core.engine.mission_decisions import (
    MISSION_DECISION_TYPES,
    apply_mission_decision,
    invalid_mission_decision_status,
    mission_decision_pauses_after_apply,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    required_movement_proposal_context_string,
)
from warhammer40k_core.engine.opportunity_windows import (
    OPPORTUNITY_REQUEST_FAMILY,
    opportunity_boundary_game_state_payload,
    opportunity_boundary_state_hash,
    opportunity_submission_invalid_reason,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
)
from warhammer40k_core.engine.phase_proposal_routing import (
    is_charge_move_proposal_request as _is_charge_move_proposal_request,
)
from warhammer40k_core.engine.phase_proposal_routing import (
    is_fight_movement_proposal_request as _is_fight_movement_proposal_request,
)
from warhammer40k_core.engine.phases.charge import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseHandler,
    invalid_charge_declaration_grant_status,
    invalid_charge_move_proposal_status,
    invalid_charging_unit_selection_status,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.fight import (
    FightPhaseHandler,
    invalid_fight_interrupt_status,
    invalid_fight_movement_proposal_status,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseHandler,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.prebattle import (
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SELECT_REDEPLOY_UNIT_DECISION_TYPE,
    SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    invalid_prebattle_proposal_status,
    is_prebattle_proposal_request,
)
from warhammer40k_core.engine.primary_mission_choices import (
    locate_and_deny_start_battle_binding,
)
from warhammer40k_core.engine.psychic_ability_decisions import invalid_psychic_activation_status
from warhammer40k_core.engine.psychic_ability_restore import validate_psychic_usage_history
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueuePayload,
)
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
    invalid_reserve_declaration_status,
)
from warhammer40k_core.engine.return_on_death import (
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    apply_return_on_death_placement_decision,
    invalid_return_on_death_placement_status,
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    runtime_rule_ir_authority_index_from_bundle,
)
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    sequencing_decision_event_from_request,
    validate_sequencing_result_from_request,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.start_battle_hooks import StartBattleHookRegistry
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    source_selection_for_cost_choice,
    stratagem_cost_choice_source_result,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    STRATAGEM_WINDOW_DECLINED_EVENT_TYPE,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    apply_stratagem_decision,
    apply_stratagem_placement_proposal,
    apply_stratagem_target_proposal,
    invalid_command_reroll_decision_status,
    invalid_stratagem_placement_proposal_status,
    invalid_stratagem_target_proposal_status,
    invalid_stratagem_use_status,
    is_command_reroll_decision_request,
    is_stratagem_placement_proposal_request,
    is_stratagem_window_decline_result,
    stratagem_selection_from_decision_result,
    stratagem_selection_from_target_proposal_result,
    stratagem_window_decline_allowed,
    stratagem_window_decline_event_payload,
)
from warhammer40k_core.engine.stratagems_unaffordable_resolution import (
    invalid_status_is_unaffordable_cost_increase,
)
from warhammer40k_core.engine.tracked_targets import (
    SELECT_TRACKED_TARGET_DECISION_TYPE,
    apply_select_tracked_target_decision,
    invalid_select_tracked_target_status,
)
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
    apply_transport_hazard_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TriggeredMovementHandler,
    invalid_triggered_movement_proposal_status,
    is_triggered_movement_proposal_request,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
)


class GameLifecyclePayload(TypedDict):
    config: GameConfigPayload | None
    parameterized_movement_proposals: bool
    state: GameStatePayload
    decisions: DecisionControllerPayload
    reaction_queue: ReactionQueuePayload
    runtime_content_audit: NotRequired[dict[str, JsonValue]]
    psychic_modifier_history_origin: NotRequired[dict[str, JsonValue]]


_MOVEMENT_PROPOSAL_DECISION_TYPES = frozenset(
    (
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
    )
)
_MOVEMENT_DECISION_TYPES = frozenset(
    (
        SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
        SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
        SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE,
        SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
    )
)
_TRIGGERED_MOVEMENT_DECISION_TYPES = frozenset((SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,))
_SHOOTING_DECISION_TYPES = frozenset(
    (
        SELECT_SHOOTING_UNIT_DECISION_TYPE,
        SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
        SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
        SELECT_SHOOTING_TYPE_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        *_asdf.ATTACK_SEQUENCE_DECISION_TYPES,
        DICE_REROLL_DECISION_TYPE,
    )
)
_SHOOTING_PHASE_DISPATCH_DECISION_TYPES = _SHOOTING_DECISION_TYPES - (
    _asdf.ATTACK_SEQUENCE_DECISION_TYPES | frozenset((DICE_REROLL_DECISION_TYPE,))
)
_CHARGE_DECISION_TYPES = frozenset(
    (
        SELECT_CHARGING_UNIT_DECISION_TYPE,
        _cd.SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
    )
)
_CHARGE_PHASE_DISPATCH_DECISION_TYPES = _CHARGE_DECISION_TYPES - frozenset(
    (
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
    )
)
_COMMAND_DECISION_TYPES = frozenset(
    (
        _cs.SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
        TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
    )
)
_FIGHT_DECISION_TYPES = frozenset(
    (
        *FIGHT_PHASE_FACTION_RULE_DECISION_TYPES,
        FIGHT_ACTIVATION_DECISION_TYPE,
        _fu.SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
        _fa.FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        *_asdf.ATTACK_SEQUENCE_DECISION_TYPES,
        DICE_REROLL_DECISION_TYPE,
        SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
    )
)
_FIGHT_PHASE_DISPATCH_DECISION_TYPES = _FIGHT_DECISION_TYPES - (
    _asdf.ATTACK_SEQUENCE_DECISION_TYPES
    | frozenset(
        (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            DICE_REROLL_DECISION_TYPE,
        )
    )
)
_REACTION_FRAME_DECISION_TYPES = frozenset(
    (
        REACTION_DECISION_TYPE,
        FIGHT_INTERRUPT_DECISION_TYPE,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
        SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        *_asdf.ATTACK_SEQUENCE_DECISION_TYPES,
        DICE_REROLL_DECISION_TYPE,
        SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
        *HEALING_DECISION_TYPES,
    )
)
_SETUP_DECISION_TYPES = frozenset(
    (
        SECONDARY_MISSION_DECISION_TYPE,
        SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
        _bf.SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    )
)
_BATTLE_ROUND_DECISION_TYPES = frozenset(
    (
        SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
        _br.SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    )
)
_PARAMETERIZED_DISPATCH_DECISION_TYPES = frozenset(
    (
        SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
        SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
        *_cmmd.PARAMETERIZED_DECISION_TYPES,
        *PARAMETERIZED_HEALING_DECISION_TYPES,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    )
)


def _new_decision_controller() -> DecisionController:
    return DecisionController()


def _runtime_content_activation_input_hash(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
) -> str:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content cache key requires GameConfig.")
    if type(armies) is not tuple:
        raise GameLifecycleError("Runtime content cache key requires army tuple.")
    # canonical_json validates this complete payload before hashing it.
    payload = {
        "ruleset_descriptor": config.ruleset_descriptor.to_payload(),
        "catalog_id": config.army_catalog.catalog_id,
        "source_package_id": config.army_catalog.source_package_id,
        "army_definitions": [
            army.to_payload()
            for army in sorted(
                _validate_runtime_content_armies(armies),
                key=lambda item: item.army_id,
            )
        ],
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_runtime_content_armies(
    armies: tuple[ArmyDefinition, ...],
) -> tuple[ArmyDefinition, ...]:
    validated: list[ArmyDefinition] = []
    seen: set[str] = set()
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Runtime content cache key requires ArmyDefinition values.")
        if army.army_id in seen:
            raise GameLifecycleError("Runtime content cache key army IDs must be unique.")
        seen.add(army.army_id)
        validated.append(army)
    return tuple(validated)


def _combined_runtime_stratagem_index(
    bundle: RuntimeContentBundle,
    *,
    base_indexes: tuple[StratagemCatalogIndex, ...],
) -> StratagemCatalogIndex:
    if type(bundle) is not RuntimeContentBundle:
        raise GameLifecycleError("Runtime Stratagem index requires RuntimeContentBundle.")
    return combine_stratagem_indexes_with_runtime_overrides(
        base_indexes=base_indexes,
        runtime_indexes=tuple(bundle.stratagem_indexes_by_player_id.values()),
    )


@dataclass(slots=True)
class GameLifecycle:
    decision_controller: DecisionController = field(default_factory=_new_decision_controller)
    reaction_queue: ReactionQueue = field(default_factory=ReactionQueue)
    state: GameState | None = None
    parameterized_movement_proposals: bool = True
    _psychic_modifier_history_origin: _pmh.PsychicModifierHistoryOrigin | None = None
    _config: GameConfig | None = None
    _setup_flow: SetupFlow = field(default_factory=SetupFlow)
    _command_phase_handler: CommandPhaseHandler = field(default_factory=CommandPhaseHandler)
    _movement_phase_handler: MovementPhaseHandler = field(default_factory=MovementPhaseHandler)
    _shooting_phase_handler: ShootingPhaseHandler = field(default_factory=ShootingPhaseHandler)
    _charge_phase_handler: ChargePhaseHandler = field(default_factory=ChargePhaseHandler)
    _fight_phase_handler: FightPhaseHandler = field(default_factory=FightPhaseHandler)
    _triggered_movement_handler: TriggeredMovementHandler = field(
        default_factory=TriggeredMovementHandler
    )
    _battle_round_flow: BattleRoundFlow | None = None
    _runtime_content_bundle: RuntimeContentBundle | None = None
    _runtime_content_audit: Mapping[str, JsonValue] | None = None
    _runtime_content_activation_input_hash: str | None = None
    _decision_dispatch_registry: DecisionDispatchRegistry = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.parameterized_movement_proposals) is not bool:
            raise GameLifecycleError(
                "GameLifecycle parameterized_movement_proposals must be a bool."
            )
        if not self.parameterized_movement_proposals:
            raise GameLifecycleError("GameLifecycle requires parameterized movement proposals.")
        if self._runtime_content_bundle is not None:
            self._runtime_content_audit = cast(
                Mapping[str, JsonValue],
                validate_json_value(self._runtime_content_bundle.to_summary_payload()),
            )
        self._decision_dispatch_registry = self._build_decision_dispatch_registry()

    @property
    def config(self) -> GameConfig:
        return self._require_config()

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("GameLifecycle config must be a GameConfig.")
        if self.state is not None:
            raise GameLifecycleError("GameLifecycle has already started.")
        self._config = config
        self._movement_phase_handler = MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            parameterized_proposals=self.parameterized_movement_proposals,
        )
        self._shooting_phase_handler = ShootingPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        self._charge_phase_handler = ChargePhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor
        )
        self._fight_phase_handler = FightPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        self._triggered_movement_handler = TriggeredMovementHandler(
            ruleset_descriptor=config.ruleset_descriptor
        )
        self.state = GameState.from_config(config)
        self._battle_round_flow = BattleRoundFlow(
            phase_handlers=self._phase_handlers(),
            battle_round_start_hooks=(
                self._runtime_content_bundle.battle_round_start_hook_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            turn_end_hooks=(
                self._runtime_content_bundle.turn_end_hook_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            phase_end_objective_control_hooks=(
                self._runtime_content_bundle.phase_end_objective_control_hook_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            unit_destroyed_hooks=(
                self._runtime_content_bundle.unit_destroyed_hook_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            runtime_modifier_registry=(
                self._runtime_content_bundle.runtime_modifier_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            runtime_event_index=(
                self._runtime_content_bundle.event_index
                if self._runtime_content_bundle is not None
                else None
            ),
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        current_setup_step = self.state.current_setup_step
        if current_setup_step is None:
            raise GameLifecycleError("GameLifecycle start requires an initial setup step.")
        self.decision_controller.event_log.append(
            "lifecycle_started",
            {
                "game_id": self.state.game_id,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
                "setup_sequence": [step.value for step in self.state.setup_sequence],
                "battle_phase_sequence": [
                    phase.value for phase in self.state.battle_phase_sequence
                ],
            },
        )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.SETUP,
            payload={
                "game_id": self.state.game_id,
                "current_setup_step": current_setup_step.value,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
            },
        )

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        self._require_state()
        transition_limit = self._require_config().max_lifecycle_transitions
        for _transition_index in range(transition_limit):
            status = self._advance_once()
            if status.status_kind in (
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            ):
                return status
        return LifecycleStatus.unsupported(
            stage=self._require_state().stage,
            message="Lifecycle reached its deterministic transition safety boundary.",
            payload={
                "unsupported_reason": "transition_budget_exhausted",
                "transition_budget": transition_limit,
            },
        )

    def _advance_once(self) -> LifecycleStatus:
        state = self._require_state()
        from warhammer40k_core.engine.rule_trigger_runtime import advance_rule_triggers

        trigger_status = advance_rule_triggers(
            state=state,
            decisions=self.decision_controller,
            runtime_bundle_provider=self._require_runtime_content_bundle,
            shooting_handler_provider=lambda: self._shooting_phase_handler,
        )
        if trigger_status is not None:
            return trigger_status
        from warhammer40k_core.engine.interrupted_charge import advance_interrupted_charge

        interrupted = advance_interrupted_charge(
            state=state,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
            handler=self._charge_phase_handler,
        )
        if interrupted is not None:
            return interrupted
        from warhammer40k_core.engine.charge_target_continuation import refresh_pending_charge_move

        charge_continuation = refresh_pending_charge_move(
            state=state,
            decisions=self.decision_controller,
            handler=self._charge_phase_handler,
        )
        if charge_continuation is not None:
            return charge_continuation
        pending_request = self._pending_decision_request()
        continuation_status = (
            _selected_target_bs.advance_catalog_selected_target_battle_shock_lifecycle(
                state=state,
                decisions=self.decision_controller,
                pending_request=pending_request,
                runtime_content_bundle=self._runtime_content_bundle,
            )
        )
        if continuation_status is not None:
            return continuation_status
        from warhammer40k_core.engine.retained_shooting import advance_retained_shooting

        retained_shooting_status = advance_retained_shooting(
            state=state,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
        )
        if retained_shooting_status is not None:
            return retained_shooting_status
        out_of_phase_status = self._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
            state=state,
            decisions=self.decision_controller,
        )
        if out_of_phase_status is not None:
            if self._reconcile_catalog_model_state_changes():
                self._refresh_runtime_content_bundle_if_armies_mustered()
            return out_of_phase_status
        forced_fight_status = self._fight_phase_handler.advance_forced_fight_activations_if_needed(
            state=state,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
        )
        if forced_fight_status is not None:
            if self._reconcile_catalog_model_state_changes():
                self._refresh_runtime_content_bundle_if_armies_mustered()
            return forced_fight_status
        if state.stage is GameLifecycleStage.COMPLETE:
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game lifecycle is complete.",
                payload=state.game_result_payload(),
            )
        if state.stage is GameLifecycleStage.SETUP:
            status = self._setup_flow.advance(
                state=state,
                decisions=self.decision_controller,
                config=self._require_config(),
                reaction_frame_count=len(self.reaction_queue.frames),
            )
            self._refresh_runtime_content_bundle_if_armies_mustered()
            return status
        status = self._require_battle_round_flow().advance(
            state=state,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
        )
        if self._reconcile_catalog_model_state_changes():
            self._refresh_runtime_content_bundle_if_armies_mustered()
        return status

    def submit_decision(self, result: DecisionResult) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        if type(result) is DecisionResult and pending_request is not None:
            from warhammer40k_core.engine.rule_trigger_runtime import validate_rule_trigger_history

            validate_rule_trigger_history(
                state=state, decisions=self.decision_controller, pending_only=True
            )
            if state.stage is GameLifecycleStage.SETUP:
                setup_invalid_status = self._setup_flow.invalid_pending_request_status(
                    state=state,
                    decisions=self.decision_controller,
                    config=self._require_config(),
                    pending_request=pending_request,
                    reaction_frame_count=len(self.reaction_queue.frames),
                )
                if setup_invalid_status is not None:
                    return setup_invalid_status
            if _is_opportunity_window_request(pending_request):
                opportunity_invalid_reason = opportunity_submission_invalid_reason(
                    request=pending_request,
                    result=result,
                    current_state_hash=self._opportunity_boundary_state_hash(
                        state=state,
                        request=pending_request,
                    ),
                    current_sequence_number=self._opportunity_boundary_sequence_number(
                        request=pending_request,
                    ),
                )
                if opportunity_invalid_reason is not None:
                    return LifecycleStatus.invalid(
                        stage=state.stage,
                        message="Opportunity-window submission is no longer valid.",
                        payload={"invalid_reason": opportunity_invalid_reason},
                    )
            from warhammer40k_core.engine.lifecycle_destruction_prevalidation import (
                invalid_destruction_request_status,
            )

            destruction_invalid = invalid_destruction_request_status(
                state=state,
                decisions=self.decision_controller,
                request=pending_request,
                runtime_bundle_provider=self._require_runtime_content_bundle,
            )
            if destruction_invalid is not None:
                return destruction_invalid
            from warhammer40k_core.engine.surge_authority import invalid_surge_authority
            from warhammer40k_core.engine.triggered_movement import (
                is_triggered_movement_distance_reroll_request,
            )

            if is_triggered_movement_distance_reroll_request(pending_request):
                surge_invalid = invalid_surge_authority(
                    state=state,
                    decisions=self.decision_controller,
                    request=pending_request,
                    result=result,
                )
                if surge_invalid is not None:
                    return surge_invalid
            handler = self._decision_dispatch_registry.handler_for(pending_request.decision_type)
            invalid_status = handler.pre_validator(pending_request, result)
            if invalid_status is not None:
                return invalid_status
            psychic_invalid = invalid_psychic_activation_status(
                state=state,
                decisions=self.decision_controller,
                request=pending_request,
                result=result,
                bundle=self._runtime_content_bundle,
            )
            if psychic_invalid is not None:
                return psychic_invalid
            _bsa.validate_pre_submission_outcome_request(
                state=state,
                decisions=self.decision_controller,
                request=pending_request,
                runtime_content_bundle=self._runtime_content_bundle,
            )
        history_origin = _pmh.capture_psychic_history_origin(
            lifecycle=self,
            request=pending_request,
            existing=self._psychic_modifier_history_origin,
        )
        record = self.decision_controller.submit_result(result)
        self._psychic_modifier_history_origin = history_origin
        status = self._decision_dispatch_registry.handler_for(record.request.decision_type).applier(
            record,
            result,
        )
        from warhammer40k_core.engine.rule_trigger_runtime import (
            record_loaded_model_destruction_occurrences,
        )

        record_loaded_model_destruction_occurrences(
            state=state,
            decisions=self.decision_controller,
            runtime_bundle_provider=self._require_runtime_content_bundle,
        )
        self._reconcile_catalog_model_state_changes()
        if self._runtime_content_bundle is not None:
            self._refresh_runtime_content_bundle_if_armies_mustered()
        from warhammer40k_core.engine.interrupted_charge import continue_interrupted_charge_reaction

        continue_interrupted_charge_reaction(
            state=state,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
            result=result,
        )
        _selected_target_bs.validate_catalog_selected_target_battle_shock_submitted_status(
            state=state,
            decisions=self.decision_controller,
            status=status,
            runtime_content_bundle=self._runtime_content_bundle,
        )
        return status

    def to_payload(self) -> GameLifecyclePayload:
        state = self._require_state()
        payload: GameLifecyclePayload = {
            "config": None if self._config is None else self._config.to_payload(),
            "parameterized_movement_proposals": self.parameterized_movement_proposals,
            "state": state.to_payload(),
            "decisions": self.decision_controller.to_payload(),
            "reaction_queue": self.reaction_queue.to_payload(),
        }
        if self._runtime_content_audit is not None:
            payload["runtime_content_audit"] = dict(self._runtime_content_audit)
        if self._psychic_modifier_history_origin is not None:
            payload["psychic_modifier_history_origin"] = (
                self._psychic_modifier_history_origin.to_payload()
            )
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: GameLifecyclePayload,
        *,
        runtime_content_bundle: RuntimeContentBundle | None = None,
    ) -> Self:
        config_payload = payload["config"]
        config = None if config_payload is None else GameConfig.from_payload(config_payload)
        if runtime_content_bundle is not None and config is None:
            raise GameLifecycleError("Explicit runtime content restoration requires config.")
        parameterized_movement_proposals = _payload_bool(
            "GameLifecycle parameterized_movement_proposals",
            payload["parameterized_movement_proposals"],
        )
        lifecycle = cls(
            decision_controller=DecisionController.from_payload(payload["decisions"]),
            reaction_queue=ReactionQueue.from_payload(payload["reaction_queue"]),
            state=GameState.from_payload(payload["state"]),
            parameterized_movement_proposals=parameterized_movement_proposals,
            _psychic_modifier_history_origin=(
                _pmh.PsychicModifierHistoryOrigin.from_payload(
                    payload["psychic_modifier_history_origin"]
                )
                if "psychic_modifier_history_origin" in payload
                else None
            ),
            _config=config,
            _runtime_content_bundle=runtime_content_bundle,
            _runtime_content_audit=_runtime_content_audit_from_payload(
                payload.get("runtime_content_audit")
            ),
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
                army_catalog=None if config is None else config.army_catalog,
                parameterized_proposals=parameterized_movement_proposals,
            ),
            _shooting_phase_handler=ShootingPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
                army_catalog=None if config is None else config.army_catalog,
            ),
            _charge_phase_handler=ChargePhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor
            ),
            _fight_phase_handler=FightPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
                army_catalog=None if config is None else config.army_catalog,
            ),
            _triggered_movement_handler=TriggeredMovementHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor
            ),
        )
        validate_payload_consistency(
            state=lifecycle._require_state(),
            config=lifecycle._config,
            event_records=lifecycle.decision_controller.event_log.records,
            decision_records=lifecycle.decision_controller.records,
            pending_decision_requests=lifecycle.decision_controller.queue.pending_requests,
        )
        validate_reaction_queue_consistency(
            state=lifecycle._require_state(),
            reaction_queue=lifecycle.reaction_queue,
            pending_request=lifecycle._pending_decision_request(),
            reaction_frame_decision_types=_REACTION_FRAME_DECISION_TYPES,
        )
        lifecycle._refresh_runtime_content_bundle_if_armies_mustered(
            preserve_existing_bundle=runtime_content_bundle is not None,
        )
        from warhammer40k_core.engine.shooting_target_replacement_authority import (
            validate_restored_replacements,
        )

        validate_restored_replacements(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            handler=lifecycle._shooting_phase_handler,
        )
        from warhammer40k_core.engine.charge_target_authority import (
            validate_restored_charge_targets,
        )
        from warhammer40k_core.engine.model_movement_history import validate_model_movement_history
        from warhammer40k_core.engine.movement_decision_authority import validate_restored_movement

        validate_restored_movement(
            state=lifecycle._require_state(), decisions=lifecycle.decision_controller
        )
        from warhammer40k_core.engine.surge_authority import validate_restored_surge

        validate_restored_surge(
            state=lifecycle._require_state(), decisions=lifecycle.decision_controller
        )
        from warhammer40k_core.engine.phase_movement_history import validate_phase_movement_history

        validate_phase_movement_history(
            state=lifecycle._require_state(), events=lifecycle.decision_controller.event_log.records
        )
        validate_model_movement_history(
            lifecycle._require_state(), lifecycle.decision_controller.event_log.records
        )
        validate_restored_charge_targets(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            handler=lifecycle._charge_phase_handler,
        )
        refreshed_bundle = lifecycle._runtime_content_bundle
        validate_pending_battlefield_request_consistency(
            state=lifecycle._require_state(),
            pending_request=lifecycle._pending_decision_request(),
            decision_records=lifecycle.decision_controller.records,
            event_records=lifecycle.decision_controller.event_log.records,
            stratagem_cost_modifier_registry=(
                None
                if refreshed_bundle is None
                else refreshed_bundle.stratagem_cost_modifier_registry
            ),
        )
        _bs_restore.validate_restored_battle_shock_continuations(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            runtime_content_bundle=refreshed_bundle,
        )
        from warhammer40k_core.engine.active_player_scope_history import (
            validate_active_player_history,
        )

        validate_active_player_history(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
        )
        from warhammer40k_core.engine.rule_trigger_runtime import validate_rule_trigger_history

        validate_rule_trigger_history(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
        )
        from warhammer40k_core.engine.lifecycle_destruction_prevalidation import (
            validate_destruction_request_authority,
        )
        from warhammer40k_core.engine.sequencing_submission_authority import (
            validate_loaded_sequencing_authority,
        )

        for pending in lifecycle.decision_controller.queue.pending_requests:
            if pending.decision_type == SEQUENCING_DECISION_TYPE:
                validate_loaded_sequencing_authority(
                    state=lifecycle._require_state(),
                    decisions=lifecycle.decision_controller,
                    request=pending,
                    config=lifecycle._require_config(),
                    reaction_queue=lifecycle.reaction_queue,
                    runtime_bundle_provider=lifecycle._require_runtime_content_bundle,
                    shooting_handler_provider=lambda: lifecycle._shooting_phase_handler,
                )
            validate_destruction_request_authority(
                state=lifecycle._require_state(),
                decisions=lifecycle.decision_controller,
                request=pending,
                runtime_bundle_provider=lifecycle._require_runtime_content_bundle,
            )
        rule_ir_authority_index = (
            None
            if refreshed_bundle is None
            else runtime_rule_ir_authority_index_from_bundle(refreshed_bundle)
        )
        validate_psychic_usage_history(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            authority=rule_ir_authority_index,
        )
        faction_rule_execution_registry = (
            None if refreshed_bundle is None else refreshed_bundle.faction_rule_execution_registry
        )
        runtime_content_activation = (
            None if refreshed_bundle is None else refreshed_bundle.activation
        )
        _pmri.validate_primary_mission_restore_integrity(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            runtime_modifier_registry=lifecycle._shooting_phase_handler.runtime_modifier_registry,
            runtime_content_bundle=refreshed_bundle,
        )
        _pmpri.validate_primary_mission_pending_request_integrity(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            runtime_modifier_registry=lifecycle._shooting_phase_handler.runtime_modifier_registry,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        _preli.validate_primary_reserve_entry_lifecycle_integrity(
            state=lifecycle._require_state(),
            event_records=lifecycle.decision_controller.event_log.records,
            decision_records=lifecycle.decision_controller.records,
            stratagem_indexes_by_player_id=(
                None
                if lifecycle._runtime_content_bundle is None
                else lifecycle._runtime_content_bundle.stratagem_indexes_by_player_id
            ),
            ability_indexes_by_player_id=(
                None
                if lifecycle._runtime_content_bundle is None
                else lifecycle._runtime_content_bundle.ability_indexes_by_player_id
            ),
        )
        lifecycle._battle_round_flow = BattleRoundFlow(
            phase_handlers=lifecycle._phase_handlers(),
            battle_round_start_hooks=(
                lifecycle._runtime_content_bundle.battle_round_start_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            turn_end_hooks=(
                lifecycle._runtime_content_bundle.turn_end_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            phase_end_objective_control_hooks=(
                lifecycle._runtime_content_bundle.phase_end_objective_control_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            unit_destroyed_hooks=(
                lifecycle._runtime_content_bundle.unit_destroyed_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            runtime_modifier_registry=(
                lifecycle._runtime_content_bundle.runtime_modifier_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            runtime_event_index=(
                lifecycle._runtime_content_bundle.event_index
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            ruleset_descriptor=None if config is None else config.ruleset_descriptor,
            army_catalog=None if config is None else config.army_catalog,
        )
        from warhammer40k_core.engine.psychic_modifier_validation import (
            validate_psychic_modifier_history,
        )

        validate_psychic_modifier_history(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            runtime_modifier_registry=lifecycle._shooting_phase_handler.runtime_modifier_registry,
        )
        _pmh.validate_psychic_history_origin(
            lifecycle=lifecycle, origin=lifecycle._psychic_modifier_history_origin
        )
        return lifecycle

    def _phase_handlers(self) -> Mapping[BattlePhase, PhaseHandler]:
        return {
            BattlePhase.COMMAND: self._command_phase_handler,
            BattlePhase.MOVEMENT: self._movement_phase_handler,
            BattlePhase.SHOOTING: self._shooting_phase_handler,
            BattlePhase.CHARGE: self._charge_phase_handler,
            BattlePhase.FIGHT: self._fight_phase_handler,
        }

    def _build_decision_dispatch_registry(self) -> DecisionDispatchRegistry:
        return build_decision_dispatch_registry(
            (
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_setup_decision,
                        applier=self._apply_setup_decision,
                    )
                    for decision_type in _SETUP_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_battle_round_decision,
                        applier=self._apply_battle_round_decision,
                    )
                    for decision_type in _BATTLE_ROUND_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_movement_phase_decision,
                        applier=self._apply_movement_phase_decision,
                    )
                    for decision_type in _MOVEMENT_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_triggered_movement_decision,
                        applier=self._apply_triggered_movement_decision,
                    )
                    for decision_type in _TRIGGERED_MOVEMENT_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_shooting_phase_decision,
                        applier=self._apply_shooting_phase_decision,
                    )
                    for decision_type in _SHOOTING_PHASE_DISPATCH_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_attack_sequence_decision,
                        applier=self._apply_attack_sequence_decision,
                    )
                    for decision_type in _asdf.ATTACK_SEQUENCE_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_charge_phase_decision,
                        applier=self._apply_charge_phase_decision,
                    )
                    for decision_type in _CHARGE_PHASE_DISPATCH_DECISION_TYPES
                ),
                DecisionDispatchHandler(
                    decision_type=SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
                    pre_validator=self._pre_validate_catalog_move_completed_mortal_wounds_decision,
                    applier=self._apply_catalog_move_completed_mortal_wounds_decision,
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_fight_phase_decision,
                        applier=self._apply_fight_phase_decision,
                    )
                    for decision_type in _FIGHT_PHASE_DISPATCH_DECISION_TYPES
                ),
                DecisionDispatchHandler(
                    decision_type=FIGHT_INTERRUPT_DECISION_TYPE,
                    pre_validator=self._pre_validate_fight_interrupt_decision,
                    applier=self._apply_fight_phase_decision,
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_command_phase_decision,
                        applier=self._apply_command_phase_decision,
                    )
                    for decision_type in _COMMAND_DECISION_TYPES
                ),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_mission_decision,
                        applier=self._apply_mission_decision,
                    )
                    for decision_type in MISSION_DECISION_TYPES
                ),
                DecisionDispatchHandler(
                    decision_type=SELECT_TRACKED_TARGET_DECISION_TYPE,
                    pre_validator=self._pre_validate_tracked_target_decision,
                    applier=self._apply_tracked_target_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                    pre_validator=self._pre_validate_return_on_death_placement_decision,
                    applier=self._apply_return_on_death_placement_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
                    pre_validator=self._pre_validate_cult_ambush_resurgence_decision,
                    applier=self._apply_cult_ambush_resurgence_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE,
                    pre_validator=self._pre_validate_cult_ambush_marker_placement_decision,
                    applier=self._apply_cult_ambush_marker_placement_decision,
                ),
                *_cmmd.decision_dispatch_handlers(self),
                *_unit_split_dispatch.decision_dispatch_handlers(self),
                *_target_replacement_dispatch.decision_dispatch_handlers(self),
                *(
                    DecisionDispatchHandler(
                        decision_type=decision_type,
                        pre_validator=self._pre_validate_healing_decision,
                        applier=self._apply_healing_decision,
                    )
                    for decision_type in HEALING_DECISION_TYPES
                ),
                DecisionDispatchHandler(
                    decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
                    pre_validator=self._pre_validate_stratagem_cost_choice_decision,
                    applier=self._apply_stratagem_cost_choice_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=REACTION_DECISION_TYPE,
                    pre_validator=self._pre_validate_reaction_decision,
                    applier=self._apply_reaction_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=STRATAGEM_DECISION_TYPE,
                    pre_validator=self._pre_validate_stratagem_decision,
                    applier=self._apply_stratagem_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
                    pre_validator=self._pre_validate_stratagem_target_proposal_decision,
                    applier=self._apply_stratagem_target_proposal_decision,
                ),
                DecisionDispatchHandler(
                    decision_type=SEQUENCING_DECISION_TYPE,
                    pre_validator=self._pre_validate_sequencing_decision,
                    applier=self._apply_sequencing_decision,
                ),
            ),
            parameterized_decision_types=_PARAMETERIZED_DISPATCH_DECISION_TYPES,
        )

    def _pre_validate_setup_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        if is_deployment_placement_request(request):
            result.validate_for_request(request)
            invalid_status = invalid_deployment_placement_status(
                state=state,
                request=request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if invalid_status is not None:
                return invalid_status
        if is_prebattle_proposal_request(request):
            result.validate_for_request(request)
            invalid_status = invalid_prebattle_proposal_status(
                state=state,
                request=request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
            )
            if invalid_status is not None:
                return invalid_status
        if request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE:
            invalid_status = invalid_reserve_declaration_status(
                state=state,
                config=self._require_config(),
                request=request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if request.decision_type == _bf.SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=request,
                result=result,
                invalid_reason="invalid_faction_rule_setup_option_result",
            )
            if invalid_status is not None:
                return invalid_status
        return None

    def _apply_setup_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        self._setup_flow.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
            config=self._require_config(),
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_battle_round_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE:
            return invalid_any_phase_once_per_battle_status(
                state=self._require_state(),
                decisions=self.decision_controller,
                request=request,
                result=result,
            )
        if request.decision_type == _br.SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
            return _invalid_finite_decision_status(
                state=self._require_state(),
                request=request,
                result=result,
                invalid_reason="invalid_faction_rule_battle_round_option_result",
            )
        return None

    def _apply_battle_round_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        self._require_battle_round_flow().apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_movement_phase_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        from warhammer40k_core.engine.movement_decision_authority import invalid_movement_authority

        invalid_status = invalid_movement_authority(
            state=state, decisions=self.decision_controller, request=request, result=result
        )
        if invalid_status is not None:
            return invalid_status
        if _bsa.requires_command_prevalidation(state=state, request=request):
            invalid_status = self._pre_validate_command_phase_decision(request, result)
        if invalid_status is None and request.decision_type == DICE_REROLL_DECISION_TYPE:
            invalid_status = _bsa.invalid_live_pending(
                state,
                self.decision_controller,
                request,
                result,
                self._require_runtime_content_bundle(),
            )
        if invalid_status is not None:
            return invalid_status
        if request.decision_type == DICE_REROLL_DECISION_TYPE:
            selected_target_reroll_status = invalid_charge_roll_reroll_context_status(
                state=state,
                request=request,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                charge_target_restriction_hooks=(
                    self._require_runtime_content_bundle().charge_target_restriction_hook_registry
                ),
            )
            if selected_target_reroll_status is not None:
                return selected_target_reroll_status
        charge_status = _charge_rerolls.invalid_charge_reroll(self, request, result)
        if charge_status is not None:
            return charge_status
        if request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE:
            return self._movement_phase_handler.invalid_movement_action_selection_status(
                state=state, request=request, result=result
            )
        if request.decision_type == SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE:
            from warhammer40k_core.engine.phases.movement_grant_sequencing import (
                invalid_movement_grant_request,
            )

            result.validate_for_request(request)
            return invalid_movement_grant_request(
                state=state,
                decisions=self.decision_controller,
                request=request,
                registry=self._movement_phase_handler.advance_move_hooks,
            )
        if request.decision_type == SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE:
            return invalid_catalog_movement_target_pair_status(
                state=state,
                decisions=self.decision_controller,
                request=request,
                result=result,
                ability_indexes_by_player_id=self._movement_phase_handler.ability_indexes_by_player_id,
            )
        if request.decision_type == SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE:
            return invalid_catalog_movement_end_target_effect_status(
                state=state,
                request=request,
                result=result,
            )
        if request.decision_type in _MOVEMENT_PROPOSAL_DECISION_TYPES:
            result.validate_for_request(request)
            spatial_status = _physical_context.invalid_physical_proposal_spatial_context_status(
                state=state,
                decisions=self.decision_controller,
                request=request,
                result=result,
            )
            if spatial_status is not None:
                return spatial_status
        if is_stratagem_placement_proposal_request(request):
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_stratagem_placement_proposal_status(
                state=state,
                request=request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        elif is_cult_ambush_placement_request(request):
            invalid_status = invalid_cult_ambush_placement_status(
                state=state,
                request=request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        elif is_destroyed_transport_disembark_proposal_request(request):
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            attack_sequence = _destroyed_transport_attack_sequence_for_request(
                state=state,
                request=request,
            )
            invalid_status = invalid_destroyed_transport_disembark_proposal_status(
                state=state,
                request=request,
                result=result,
                decisions=self.decision_controller,
                attack_sequence=attack_sequence,
            )
            if invalid_status is not None:
                return invalid_status
        elif is_setup_reactive_lifecycle_request(request):
            return invalid_setup_reactive_lifecycle_status(
                state=state,
                config=self._require_config(),
                runtime_content_bundle=self._require_runtime_content_bundle(),
                decisions=self.decision_controller,
                reaction_queue=self.reaction_queue,
                request=request,
                result=result,
                resolves_reaction_frame=self._result_resolves_active_reaction_frame(result),
            )
        elif request.decision_type in _MOVEMENT_PROPOSAL_DECISION_TYPES:
            if is_triggered_movement_proposal_request(request):
                malformed_status = invalid_triggered_movement_proposal_status(
                    state=state,
                    request=request,
                    result=result,
                    decisions=self.decision_controller,
                )
            elif _is_fight_movement_proposal_request(request):
                malformed_status = invalid_fight_movement_proposal_status(
                    state=state,
                    request=request,
                    result=result,
                    decisions=self.decision_controller,
                    ruleset_descriptor=self._require_config().ruleset_descriptor,
                )
            elif _is_charge_move_proposal_request(request):
                malformed_status = invalid_charge_move_proposal_status(
                    state=state,
                    handler=self._charge_phase_handler,
                    request=request,
                    result=result,
                    decisions=self.decision_controller,
                    ruleset_descriptor=self._require_config().ruleset_descriptor,
                    charge_target_restriction_hooks=(
                        self._require_runtime_content_bundle().charge_target_restriction_hook_registry
                    ),
                )
            else:
                malformed_status = self._movement_phase_handler.invalid_proposal_submission_status(
                    state=state,
                    request=request,
                    result=result,
                    decisions=self.decision_controller,
                )
            if malformed_status is not None:
                return malformed_status
        if is_command_reroll_decision_request(request):
            invalid_status = invalid_command_reroll_decision_status(
                state=state,
                request=request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        return None

    def _apply_movement_phase_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        if is_cult_ambush_placement_request(record.request):
            placement_status = apply_cult_ambush_placement(
                state=state,
                decisions=self.decision_controller,
                request=record.request,
                result=result,
            )
            if placement_status is not None:
                return placement_status
            return self.advance_until_decision_or_terminal()
        if is_stratagem_placement_proposal_request(record.request):
            return self._apply_stratagem_placement_decision(record=record, result=result)
        runtime_bundle = self._require_runtime_content_bundle()
        reroll_status = _bsa.apply_global_reroll_if_applicable(
            state=state,
            decisions=self.decision_controller,
            request=record.request,
            result=result,
            runtime_content_bundle=runtime_bundle,
            reaction_queue=self.reaction_queue,
            resolves_reaction_frame=self._result_resolves_active_reaction_frame(result),
            advance_until_decision_or_terminal=self.advance_until_decision_or_terminal,
        )
        if reroll_status is not None:
            return reroll_status
        setup_reactive_status = apply_setup_reactive_lifecycle_decision_if_applicable(
            state=state,
            config=self._require_config(),
            runtime_content_bundle=runtime_bundle,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
            record=record,
            result=result,
            resolves_reaction_frame=self._result_resolves_active_reaction_frame(result),
            pending_decision_request=self._pending_decision_request,
            advance_until_decision_or_terminal=self.advance_until_decision_or_terminal,
        )
        if setup_reactive_status is not None:
            return setup_reactive_status
        if (
            record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
            and is_triggered_movement_proposal_request(record.request)
        ):
            triggered_status = self._triggered_movement_handler.apply_proposal_decision(
                state=state,
                request=record.request,
                result=result,
                decisions=self.decision_controller,
            )
            if triggered_status is not None:
                return triggered_status
            return self.advance_until_decision_or_terminal()
        if (
            record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
            and _is_fight_movement_proposal_request(record.request)
        ):
            return self._apply_fight_phase_decision(record, result)
        if (
            record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
            and _is_charge_move_proposal_request(record.request)
        ):
            return self._apply_charge_phase_decision(record, result)
        if (
            record.request.decision_type == DICE_REROLL_DECISION_TYPE
            and state.current_battle_phase is BattlePhase.COMMAND
        ):
            return self._apply_command_phase_decision(record, result)
        if (
            record.request.decision_type == DICE_REROLL_DECISION_TYPE
            and state.current_battle_phase is BattlePhase.CHARGE
        ):
            return self._apply_charge_phase_decision(record, result)
        if (
            record.request.decision_type == DICE_REROLL_DECISION_TYPE
            and state.current_battle_phase is BattlePhase.SHOOTING
        ):
            return self._apply_shooting_phase_decision(record, result)
        if (
            record.request.decision_type == DICE_REROLL_DECISION_TYPE
            and state.current_battle_phase is BattlePhase.FIGHT
        ):
            return self._apply_fight_phase_decision(record, result)
        if is_destroyed_transport_disembark_proposal_request(record.request):
            return self._apply_destroyed_transport_disembark_decision(record=record, result=result)
        movement_status = self._movement_phase_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
        )
        if movement_status is not None:
            return movement_status
        return self.advance_until_decision_or_terminal()

    def _apply_stratagem_placement_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        placement_status = apply_stratagem_placement_proposal(
            state=state,
            request=record.request,
            result=result,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            reserve_arrival_restriction_hooks=(
                self._require_runtime_content_bundle().reserve_arrival_restriction_hook_registry
            ),
        )
        if placement_status is not None:
            if resolves_reaction_frame:
                retry_request = self._pending_decision_request()
                if retry_request is not None and is_stratagem_placement_proposal_request(
                    retry_request
                ):
                    self.reaction_queue.continue_reaction(
                        result=result,
                        next_request_id=retry_request.request_id,
                        decisions=self.decision_controller,
                    )
            return placement_status
        if resolves_reaction_frame:
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
        return self.advance_until_decision_or_terminal()

    def _apply_destroyed_transport_disembark_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        from warhammer40k_core.engine.retained_destruction_cleanup import (
            active_retained_attack_destruction,
        )

        if active_retained_attack_destruction(state=state) is not None:
            return self._apply_attack_sequence_decision(record, result)
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        if _destroyed_transport_request_is_fight_owned(
            state=state,
            request=record.request,
        ):
            fight_status = self._fight_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                reaction_queue=self.reaction_queue,
            )
            if fight_status is not None:
                if resolves_reaction_frame:
                    self._continue_or_resolve_fight_reaction(
                        result=result,
                        status=fight_status,
                    )
                return fight_status
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
            return advanced_status
        shooting_status = self._shooting_phase_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
        )
        if resolves_reaction_frame:
            handled_status = self._continue_or_resolve_out_of_phase_reaction(
                result=result,
                status=shooting_status,
            )
            if handled_status is not None:
                return handled_status
        if shooting_status is not None:
            return shooting_status
        return self.advance_until_decision_or_terminal()

    def _pre_validate_triggered_movement_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.movement_decision_authority import invalid_movement_authority
        from warhammer40k_core.engine.surge_authority import invalid_surge_authority

        surge_status = invalid_surge_authority(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=request,
            result=result,
        )
        if surge_status is not None:
            return surge_status

        return invalid_movement_authority(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=request,
            result=result,
        )

    def _apply_triggered_movement_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        triggered_status = self._triggered_movement_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
        )
        if triggered_status is not None:
            return triggered_status
        return self.advance_until_decision_or_terminal()

    def _pre_validate_shooting_phase_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.lifecycle_shooting_prevalidation import (
            pre_validate_shooting_decision,
        )

        return pre_validate_shooting_decision(lifecycle=self, request=request, result=result)

    def _apply_shooting_phase_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        shooting_status = self._shooting_phase_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
        )
        if resolves_reaction_frame:
            handled_status = self._continue_or_resolve_out_of_phase_reaction(
                result=result,
                status=shooting_status,
            )
            if handled_status is not None:
                return handled_status
        if shooting_status is not None:
            return shooting_status
        return self.advance_until_decision_or_terminal()

    def _pre_validate_attack_sequence_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.lifecycle_attack_prevalidation import (
            pre_validate_attack_sequence_decision,
        )

        return pre_validate_attack_sequence_decision(
            state=self._require_state(),
            decisions=self.decision_controller,
            shooting_phase_handler=self._shooting_phase_handler,
            runtime_content_bundle=self._runtime_content_bundle,
            request=request,
            result=result,
        )

    def _apply_attack_sequence_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        from warhammer40k_core.engine.lifecycle_attack_dispatch import (
            AttackDecisionDispatchContext,
            apply_attack_sequence_decision,
        )

        state = self._require_state()
        context = AttackDecisionDispatchContext(
            state=state,
            decisions=self.decision_controller,
            ruleset_descriptor=lambda: self._require_config().ruleset_descriptor,
            runtime_modifier_registry=lambda: (
                self._require_runtime_content_bundle().runtime_modifier_registry
            ),
            fight_owned=_fight_decision_owns_request(state=state, request=record.request),
            resolves_reaction_frame=self._result_resolves_active_reaction_frame(result),
            fight_decision_types=_FIGHT_DECISION_TYPES,
            shooting_decision_types=_SHOOTING_DECISION_TYPES,
            advance=self.advance_until_decision_or_terminal,
            apply_fight=self._apply_fight_phase_decision,
            apply_shooting=self._apply_shooting_phase_decision,
            apply_mortal_wounds=self._apply_mortal_wound_resolution_decision,
            continue_fight_reaction=self._continue_or_resolve_fight_reaction,
            continue_shooting_reaction=self._continue_or_resolve_out_of_phase_reaction,
        )
        return apply_attack_sequence_decision(context, record=record, result=result)

    def _apply_mortal_wound_resolution_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        if rule_model_destruction.is_rule_model_destruction_mortal_wound_request(record.request):
            status = rule_model_destruction.apply_rule_model_destruction_mortal_wound_decision(
                state=state,
                decisions=self.decision_controller,
                result=result,
            )
            if status is not None:
                return status
            from warhammer40k_core.engine.retained_destruction_cleanup import (
                complete_removed_retained_destructions,
            )

            complete_removed_retained_destructions(state=state, decisions=self.decision_controller)
            return self.advance_until_decision_or_terminal()
        movement_fnp_status = _movement_mw.apply_movement_fnp_if_applicable(
            state=state,
            decisions=self.decision_controller,
            request=record.request,
            result=result,
        )
        if movement_fnp_status is not False:
            if movement_fnp_status is not None:
                return movement_fnp_status
            return self.advance_until_decision_or_terminal()
        source_context = _mw_model.mortal_wound_resolution_source_context(record.request)
        stratagem_status = _stratagem_mw.apply_core_stratagem_mortal_wound_decision_if_applicable(
            state=state,
            decisions=self.decision_controller,
            result=result,
            source_context=source_context,
        )
        if stratagem_status is not False:
            if stratagem_status is not None:
                return stratagem_status
            return self.advance_until_decision_or_terminal()
        if (
            isinstance(source_context, dict)
            and source_context.get("source_kind") == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
        ):
            from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
                RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND,
                apply_rules_unit_combat_disembark_feel_no_pain_decision,
            )

            if (
                source_context.get("disembark_payload_kind")
                == RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND
            ):
                pending_request = apply_rules_unit_combat_disembark_feel_no_pain_decision(
                    state=state,
                    result=result,
                    decisions=self.decision_controller,
                )
                if pending_request is not None:
                    return LifecycleStatus.waiting_for_decision(
                        stage=state.stage,
                        decision_request=pending_request,
                        payload={
                            "phase": state.current_battle_phase.value
                            if state.current_battle_phase is not None
                            else None,
                            "decision_type": pending_request.decision_type,
                            "source_rule_id": CORE_HAZARD_ROLLS_RULE_ID,
                            "source_kind": TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
                        },
                    )
                return self.advance_until_decision_or_terminal()
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            transport_hazard_status = apply_transport_hazard_mortal_wound_feel_no_pain_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if transport_hazard_status is not None:
                if resolves_reaction_frame:
                    if _fight_decision_owns_request(state=state, request=record.request):
                        self._continue_or_resolve_fight_reaction(
                            result=result,
                            status=transport_hazard_status,
                        )
                    else:
                        handled_status = self._continue_or_resolve_out_of_phase_reaction(
                            result=result,
                            status=transport_hazard_status,
                        )
                        if handled_status is not None:
                            return handled_status
                return transport_hazard_status
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
                if _fight_decision_owns_request(state=state, request=record.request):
                    self._continue_or_resolve_fight_reaction(
                        result=result,
                        status=advanced_status,
                    )
                else:
                    handled_status = self._continue_or_resolve_out_of_phase_reaction(
                        result=result,
                        status=advanced_status,
                    )
                    if handled_status is not None:
                        return handled_status
            return advanced_status
        runtime_bundle = self._require_runtime_content_bundle()
        runtime_mortal_wound_registry = runtime_bundle.mortal_wound_feel_no_pain_hook_registry
        if runtime_mortal_wound_registry.handles_source_context(source_context):
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            runtime_status = runtime_mortal_wound_registry.apply_decision(
                MortalWoundFeelNoPainContinuationContext(
                    state=state,
                    decisions=self.decision_controller,
                    request=record.request,
                    result=result,
                    source_context=source_context,
                    dice_manager=DiceRollManager(
                        state.game_id,
                        event_log=self.decision_controller.event_log,
                    ),
                    runtime_modifier_registry=runtime_bundle.runtime_modifier_registry,
                    battle_shock_hooks=runtime_bundle.battle_shock_hook_registry,
                    ability_indexes_by_player_id=runtime_bundle.ability_indexes_by_player_id,
                )
            )
            if runtime_status is not None:
                if resolves_reaction_frame:
                    if _runtime_mortal_wound_source_context_phase(source_context) is (
                        BattlePhase.FIGHT
                    ):
                        self._continue_or_resolve_fight_reaction(
                            result=result,
                            status=runtime_status,
                        )
                    else:
                        handled_status = self._continue_or_resolve_out_of_phase_reaction(
                            result=result,
                            status=runtime_status,
                        )
                        if handled_status is not None:
                            return handled_status
                return runtime_status
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
                if _runtime_mortal_wound_source_context_phase(source_context) is BattlePhase.FIGHT:
                    self._continue_or_resolve_fight_reaction(
                        result=result,
                        status=advanced_status,
                    )
                else:
                    handled_status = self._continue_or_resolve_out_of_phase_reaction(
                        result=result,
                        status=advanced_status,
                    )
                    if handled_status is not None:
                        return handled_status
            return advanced_status
        if _fight_decision_owns_request(state=state, request=record.request):
            return self._apply_fight_phase_decision(record, result)
        return self._apply_shooting_phase_decision(record, result)

    def _pre_validate_charge_phase_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        from warhammer40k_core.engine.movement_decision_authority import invalid_movement_authority

        invalid_status = invalid_movement_authority(
            state=state, decisions=self.decision_controller, request=request, result=result
        )
        if invalid_status is not None:
            return invalid_status
        if request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE:
            invalid_status = invalid_charging_unit_selection_status(
                state=state,
                request=request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                ability_index=self._charge_phase_handler.ability_index_for_player(
                    cast(str, request.actor_id)
                ),
                runtime_modifier_registry=(
                    self._require_runtime_content_bundle().runtime_modifier_registry
                ),
                charge_target_restriction_hooks=(
                    self._require_runtime_content_bundle().charge_target_restriction_hook_registry
                ),
            )
            if invalid_status is not None:
                return invalid_status
        if request.decision_type == _cd.SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE:
            invalid_status = invalid_charge_declaration_grant_status(
                state=state,
                request=request,
                result=result,
                charge_declaration_hooks=self._charge_phase_handler.charge_declaration_hooks,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                charge_target_restriction_hooks=(
                    self._require_runtime_content_bundle().charge_target_restriction_hook_registry
                ),
            )
            if invalid_status is not None:
                return invalid_status
        return None

    def _apply_charge_phase_decision(
        self, _record: DecisionRecord, result: DecisionResult
    ) -> LifecycleStatus:
        status = self._charge_phase_handler.apply_decision(
            state=self._require_state(), result=result, decisions=self.decision_controller
        )
        return status if status is not None else self.advance_until_decision_or_terminal()

    def _pre_validate_catalog_move_completed_mortal_wounds_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return _catalog_move_mw.invalid_catalog_unit_move_completed_mortal_wounds_target_status(
            state=self._require_state(),
            request=request,
            result=result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
        )

    def _apply_catalog_move_completed_mortal_wounds_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        target_status = (
            _catalog_move_mw.apply_catalog_unit_move_completed_mortal_wounds_target_result(
                state=state,
                decisions=self.decision_controller,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
        )
        if target_status is not None:
            return target_status
        return self.advance_until_decision_or_terminal()

    def _pre_validate_fight_phase_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.lifecycle_fight_prevalidation import (
            pre_validate_fight_decision,
        )

        return pre_validate_fight_decision(self, request, result)

    def _pre_validate_fight_interrupt_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        result.validate_for_request(request)
        if self._result_resolves_active_reaction_frame(result):
            self.reaction_queue.validate_result(result)
        return invalid_fight_interrupt_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
        )

    def _apply_fight_phase_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        fight_status = self._fight_phase_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
        )
        if fight_status is not None:
            if resolves_reaction_frame:
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=fight_status,
                )
            return fight_status
        advanced_status = self.advance_until_decision_or_terminal()
        if resolves_reaction_frame:
            self._continue_or_resolve_fight_reaction(
                result=result,
                status=advanced_status,
            )
        return advanced_status

    def _pre_validate_command_phase_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.lifecycle_command_prevalidation import (
            invalid_command_phase_submission,
        )

        return invalid_command_phase_submission(
            state=self._require_state(),
            decisions=self.decision_controller,
            config=self._require_config(),
            handler=self._command_phase_handler,
            request=request,
            result=result,
        )

    def _apply_command_phase_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        self._command_phase_handler.apply_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_mission_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        result.validate_for_request(request)
        return invalid_mission_decision_status(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=request,
            result=result,
            runtime_modifier_registry=self._shooting_phase_handler.runtime_modifier_registry,
        )

    def _apply_mission_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        bundle = self._runtime_content_bundle
        apply_mission_decision(
            state=state,
            request=record.request,
            result=result,
            decisions=self.decision_controller,
            runtime_modifier_registry=self._shooting_phase_handler.runtime_modifier_registry,
            rule_ir_authority_index=(
                None if bundle is None else runtime_rule_ir_authority_index_from_bundle(bundle)
            ),
            faction_rule_execution_registry=(
                None if bundle is None else bundle.faction_rule_execution_registry
            ),
            runtime_content_activation=None if bundle is None else bundle.activation,
        )
        if mission_decision_pauses_after_apply(record.request):
            return LifecycleStatus.advanced(
                stage=state.stage,
                payload={
                    "decision_type": record.request.decision_type,
                    "result_id": result.result_id,
                },
            )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_tracked_target_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return invalid_select_tracked_target_status(
            state=self._require_state(),
            request=request,
            result=result,
        )

    def _apply_tracked_target_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        apply_select_tracked_target_decision(
            state=self._require_state(),
            request=record.request,
            result=result,
            decisions_event_log=self.decision_controller.event_log,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_return_on_death_placement_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return invalid_return_on_death_placement_status(
            state=self._require_state(),
            request=request,
            result=result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
        )

    def _apply_return_on_death_placement_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        apply_return_on_death_placement_decision(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=record.request,
            result=result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_cult_ambush_resurgence_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return invalid_cult_ambush_resurgence_status(
            state=self._require_state(),
            request=request,
            result=result,
        )

    def _apply_cult_ambush_resurgence_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        apply_cult_ambush_resurgence_decision(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=record.request,
            result=result,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_cult_ambush_marker_placement_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return invalid_cult_ambush_marker_placement_status(
            state=self._require_state(),
            request=request,
            result=result,
        )

    def _apply_cult_ambush_marker_placement_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        apply_cult_ambush_marker_placement_decision(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=record.request,
            result=result,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_healing_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if self._result_resolves_active_reaction_frame(result):
            self.reaction_queue.validate_result(result)
        return invalid_healing_decision_status(
            state=self._require_state(),
            request=request,
            result=result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
        )

    def _apply_healing_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        healing_effect, follow_up_request = apply_recorded_healing_decision(
            state=state,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            request=record.request,
            result=result,
        )
        if follow_up_request is not None:
            healing_status = LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=follow_up_request,
                payload={
                    "decision_type": follow_up_request.decision_type,
                    "effect_id": healing_effect.effect_id,
                    "target_unit_instance_id": healing_effect.target_unit_instance_id,
                },
            )
            if resolves_reaction_frame:
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=follow_up_request.request_id,
                    decisions=self.decision_controller,
                )
            return healing_status
        command_start_nested_handled = (
            self._command_phase_handler.apply_command_phase_start_nested_result(
                state=state,
                decisions=self.decision_controller,
                request=record.request,
                result=result,
            )
        )
        if resolves_reaction_frame:
            if command_start_nested_handled:
                raise GameLifecycleError(
                    "Command-start nested healing cannot also own a reaction frame."
                )
            if self.decision_controller.queue.pending_requests:
                raise GameLifecycleError(
                    "Completed reaction healing retained an unsupported nested decision."
                )
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_stratagem_cost_choice_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        return _invalid_finite_decision_status(
            state=self._require_state(),
            request=request,
            result=result,
            invalid_reason="invalid_stratagem_cost_modifier_option_result",
        )

    def _apply_stratagem_cost_choice_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        return self._apply_stratagem_cost_choice_and_resume(
            request=record.request,
            result=result,
        )

    def _pre_validate_reaction_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        result.validate_for_request(request)
        self.reaction_queue.validate_result(result)
        return None

    def _apply_reaction_decision(
        self,
        _record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        self.reaction_queue.resolve_reaction(
            result=result,
            decisions=self.decision_controller,
        )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_stratagem_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.lifecycle_stratagem_prevalidation import (
            prevalidate_stratagem_decision,
        )

        return prevalidate_stratagem_decision(self, request, result)

    def _apply_stratagem_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        if is_stratagem_window_decline_result(result):
            self._record_stratagem_window_declined(result)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
        cost_choice_status = self._request_stratagem_cost_choice_if_available(
            source_request=record.request,
            source_result=result,
            selection=stratagem_selection_from_decision_result(result),
        )
        if cost_choice_status is not None:
            return cost_choice_status
        runtime_content_bundle = self._require_runtime_content_bundle()
        apply_stratagem_decision(
            state=state,
            result=result,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
            runtime_content_bundle=runtime_content_bundle,
            stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
            shooting_unit_selected_grant_hooks=(
                runtime_content_bundle.shooting_unit_selected_grant_hook_registry
            ),
        )
        if self._result_resolves_active_reaction_frame(result):
            follow_up_request = self._pending_decision_request()
            if follow_up_request is not None and (
                is_command_reroll_decision_request(follow_up_request)
                or is_stratagem_battle_shock_reroll_request(follow_up_request)
            ):
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=follow_up_request.request_id,
                    decisions=self.decision_controller,
                )
            else:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
        return self.advance_until_decision_or_terminal()

    def _pre_validate_stratagem_target_proposal_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        result.validate_for_request(request)
        if self._result_resolves_active_reaction_frame(result):
            self.reaction_queue.validate_result(result)
        if is_stratagem_window_decline_result(result) and not stratagem_window_decline_allowed(
            request=request,
            result=result,
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Stratagem window decline is not allowed for this request.",
                payload={"invalid_reason": "decline_not_allowed"},
            )
        if not is_stratagem_window_decline_result(result):
            invalid_status = invalid_stratagem_target_proposal_status(
                state=state,
                request=request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
                decisions=self.decision_controller,
                shooting_target_restriction_hooks=self._require_runtime_content_bundle().shooting_target_restriction_hook_registry,
                stratagem_cost_modifier_registry=(
                    self._require_runtime_content_bundle().stratagem_cost_modifier_registry
                ),
            )
            if invalid_status is not None:
                return invalid_status
        return None

    def _apply_stratagem_target_proposal_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
        if is_stratagem_window_decline_result(result):
            self._record_stratagem_window_declined(result)
            if resolves_reaction_frame:
                if self._fight_interrupt_activation_is_active():
                    advanced_status = self.advance_until_decision_or_terminal()
                    self._continue_or_resolve_fight_reaction(
                        result=result,
                        status=advanced_status,
                    )
                    return advanced_status
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
        cost_choice_status = self._request_stratagem_cost_choice_if_available(
            source_request=record.request,
            source_result=result,
            selection=stratagem_selection_from_target_proposal_result(result),
        )
        if cost_choice_status is not None:
            return cost_choice_status
        runtime_content_bundle = self._require_runtime_content_bundle()
        apply_stratagem_target_proposal(
            state=state,
            result=result,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
            runtime_content_bundle=runtime_content_bundle,
            stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
            shooting_unit_selected_grant_hooks=(
                runtime_content_bundle.shooting_unit_selected_grant_hook_registry
            ),
        )
        advanced_status = self.advance_until_decision_or_terminal()
        if resolves_reaction_frame and self._result_resolves_active_reaction_frame(result):
            if self._fight_interrupt_activation_is_active():
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
            elif advanced_status.decision_request is not None:
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=advanced_status.decision_request.request_id,
                    decisions=self.decision_controller,
                )
            else:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
        return advanced_status

    def _pre_validate_sequencing_decision(
        self,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.sequencing_submission_authority import (
            validate_loaded_sequencing_authority,
        )

        validate_sequencing_result_from_request(request=request, result=result)
        validate_loaded_sequencing_authority(
            state=self._require_state(),
            decisions=self.decision_controller,
            request=request,
            config=self._require_config(),
            reaction_queue=self.reaction_queue,
            runtime_bundle_provider=self._require_runtime_content_bundle,
            shooting_handler_provider=lambda: self._shooting_phase_handler,
        )
        return None

    def _apply_sequencing_decision(
        self,
        record: DecisionRecord,
        result: DecisionResult,
    ) -> LifecycleStatus:
        event_type, payload = sequencing_decision_event_from_request(
            request=record.request,
            result=result,
        )
        self.decision_controller.event_log.append(event_type, payload)
        return self.advance_until_decision_or_terminal()

    def pending_decision_request(self) -> DecisionRequest | None:
        return self._pending_decision_request()

    @property
    def decision_dispatch_contracts(self) -> tuple[DecisionDispatchContract, ...]:
        return self._decision_dispatch_registry.registered_contracts()

    def _pending_decision_request(self) -> DecisionRequest | None:
        pending_requests = self.decision_controller.queue.pending_requests
        if not pending_requests:
            return None
        pending_request = pending_requests[0]
        self._decision_dispatch_registry.validate_request_submission_kind(pending_request)
        return pending_request

    def _require_state(self) -> GameState:
        if self.state is None:
            raise GameLifecycleError("GameLifecycle has not started.")
        return self.state

    def _require_config(self) -> GameConfig:
        if self._config is None:
            raise GameLifecycleError("GameLifecycle config is unavailable.")
        return self._config

    def _require_battle_round_flow(self) -> BattleRoundFlow:
        if self._battle_round_flow is None:
            raise GameLifecycleError("GameLifecycle battle round flow is unavailable.")
        return self._battle_round_flow

    def _require_runtime_content_bundle(self) -> RuntimeContentBundle:
        self._refresh_runtime_content_bundle_if_armies_mustered()
        if self._runtime_content_bundle is None:
            raise GameLifecycleError("GameLifecycle runtime content bundle is unavailable.")
        return self._runtime_content_bundle

    def _refresh_runtime_content_bundle_if_armies_mustered(
        self,
        *,
        preserve_existing_bundle: bool = False,
    ) -> None:
        if self._config is None:
            return
        state = self._require_state()
        if not state.army_definitions:
            return
        armies = tuple(state.army_definitions)
        activation_input_hash = _runtime_content_activation_input_hash(
            config=self._config,
            armies=armies,
        )
        if (
            self._runtime_content_bundle is not None
            and self._runtime_content_activation_input_hash == activation_input_hash
        ):
            return
        activation = runtime_content_activation_for_armies(
            config=self._config,
            armies=armies,
        )
        if preserve_existing_bundle:
            bundle = self._runtime_content_bundle
            if bundle is None or (
                bundle.activation.roster_content_ids() != activation.roster_content_ids()
                or bundle.activation.selected_enhancement_assignments
                != activation.selected_enhancement_assignments
                or bundle.activation.loaded_unit_instance_ids != activation.loaded_unit_instance_ids
                or bundle.activation.selected_weapon_keywords != activation.selected_weapon_keywords
            ):
                raise GameLifecycleError(
                    "Explicit runtime content bundle contradicts the restored armies."
                )
        elif (
            self._runtime_content_bundle is not None
            and self._runtime_content_bundle.activation.activation_hash
            == activation.activation_hash
        ):
            bundle = self._runtime_content_bundle
        else:
            bundle = build_runtime_content_bundle_for_armies(
                config=self._config,
                armies=armies,
            )
        ability_indexes = bundle.ability_indexes_by_player_id
        _sbkc.CatalogStartBattleKeywordChoiceRuntime(ability_indexes, armies).validate_state(
            state, self.decision_controller
        )
        catalog_rules = CatalogDatasheetRuleRuntime(ability_indexes, armies)
        catalog_rules.record_static_sources(state=state)
        self._runtime_content_bundle = bundle
        self._setup_flow = replace(
            self._setup_flow,
            battle_formation_hooks=bundle.battle_formation_hook_registry,
            start_battle_hooks=StartBattleHookRegistry.from_bindings(
                (
                    *bundle.start_battle_hook_registry.all_bindings(),
                    locate_and_deny_start_battle_binding(),
                )
            ),
        )
        runtime_stratagem_index = _combined_runtime_stratagem_index(
            bundle,
            base_indexes=(
                self._command_phase_handler.stratagem_index,
                self._movement_phase_handler.stratagem_index,
                self._shooting_phase_handler.stratagem_index,
                self._charge_phase_handler.stratagem_index,
                self._fight_phase_handler.stratagem_index,
            ),
        )
        apply_enhancement_effects(
            state=state,
            registry=bundle.enhancement_effect_registry,
            decisions=self.decision_controller,
        )
        self._command_phase_handler = CommandPhaseHandler(
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
            stratagem_index=runtime_stratagem_index,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
            battle_shock_hooks=bundle.battle_shock_hook_registry,
            command_phase_start_hooks=bundle.command_phase_start_hook_registry,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
        self._movement_phase_handler = MovementPhaseHandler(
            ruleset_descriptor=self._movement_phase_handler.ruleset_descriptor,
            army_catalog=self._movement_phase_handler.army_catalog,
            parameterized_proposals=self._movement_phase_handler.parameterized_proposals,
            stratagem_index=runtime_stratagem_index,
            advance_eligibility_hooks=bundle.advance_eligibility_hook_registry,
            advance_move_hooks=bundle.advance_move_hook_registry,
            fall_back_hooks=bundle.fall_back_hook_registry,
            movement_end_surge_hooks=bundle.movement_end_surge_hook_registry,
            move_completion_rule_registry=bundle.move_completion_rule_registry,
            reserve_arrival_distance_hooks=bundle.reserve_arrival_distance_hook_registry,
            reserve_arrival_restriction_hooks=(bundle.reserve_arrival_restriction_hook_registry),
            unit_move_completed_mortal_wound_hooks=(
                bundle.unit_move_completed_mortal_wound_hook_registry
            ),
            charge_target_restriction_hooks=bundle.charge_target_restriction_hook_registry,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            battle_shock_hooks=bundle.battle_shock_hook_registry,
        )
        self._charge_phase_handler = ChargePhaseHandler(
            ruleset_descriptor=self._charge_phase_handler.ruleset_descriptor,
            stratagem_index=runtime_stratagem_index,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
            charge_declaration_hooks=bundle.charge_declaration_hook_registry,
            move_completion_rule_registry=bundle.move_completion_rule_registry,
            charge_target_restriction_hooks=bundle.charge_target_restriction_hook_registry,
            unit_move_completed_mortal_wound_hooks=(
                bundle.unit_move_completed_mortal_wound_hook_registry
            ),
            unit_move_completed_battle_shock_hooks=(
                bundle.unit_move_completed_battle_shock_hook_registry
            ),
            battle_shock_hooks=bundle.battle_shock_hook_registry,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
        self._shooting_phase_handler = ShootingPhaseHandler(
            ruleset_descriptor=self._shooting_phase_handler.ruleset_descriptor,
            army_catalog=self._shooting_phase_handler.army_catalog,
            stratagem_index=runtime_stratagem_index,
            shooting_unit_selected_hooks=bundle.shooting_unit_selected_hook_registry,
            shooting_unit_selected_grant_hooks=(bundle.shooting_unit_selected_grant_hook_registry),
            shooting_target_restriction_hooks=bundle.shooting_target_restriction_hook_registry,
            shooting_phase_start_hooks=bundle.shooting_phase_start_hook_registry,
            shooting_end_surge_hooks=bundle.shooting_end_surge_hook_registry,
            attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
            battle_shock_hooks=bundle.battle_shock_hook_registry,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
        self._fight_phase_handler = FightPhaseHandler(
            ruleset_descriptor=self._fight_phase_handler.ruleset_descriptor,
            army_catalog=self._fight_phase_handler.army_catalog,
            stratagem_index=runtime_stratagem_index,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
            fight_activation_ability_hooks=(bundle.fight_activation_ability_hook_registry),
            fight_unit_selected_hooks=bundle.fight_unit_selected_hook_registry,
            fight_unit_selected_grant_hooks=(bundle.fight_unit_selected_grant_hook_registry),
            attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
            fight_phase_start_hooks=bundle.fight_phase_start_hook_registry,
            fight_phase_end_hooks=bundle.fight_phase_end_hook_registry,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            catalog_selected_target_battle_shock_runtime=(
                _selected_target_bs.CatalogSelectedTargetBattleShockRuntime.from_bundle(bundle)
            ),
        )
        self._battle_round_flow = BattleRoundFlow(
            phase_handlers=self._phase_handlers(),
            battle_round_start_hooks=bundle.battle_round_start_hook_registry,
            turn_end_hooks=bundle.turn_end_hook_registry,
            phase_end_objective_control_hooks=bundle.phase_end_objective_control_hook_registry,
            unit_destroyed_hooks=bundle.unit_destroyed_hook_registry,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            runtime_event_index=bundle.event_index,
            ruleset_descriptor=self._config.ruleset_descriptor,
            army_catalog=self._config.army_catalog,
        )
        self._runtime_content_activation_input_hash = _runtime_content_activation_input_hash(
            config=self._config,
            armies=tuple(state.army_definitions),
        )
        summary = bundle.to_summary_payload()
        self._runtime_content_audit = cast(
            Mapping[str, JsonValue],
            validate_json_value(summary),
        )
        _bsa.validate_loaded(state, self.decision_controller, bundle)

    def _reconcile_catalog_model_state_changes(self) -> bool:
        if self._config is None or self._runtime_content_bundle is None:
            return False
        state = self._require_state()
        if not state.army_definitions:
            return False
        return CatalogModelMaterializationRuntime(
            ability_indexes_by_player_id=(
                self._runtime_content_bundle.ability_indexes_by_player_id
            ),
            armies=tuple(state.army_definitions),
            army_catalog=self._config.army_catalog,
        ).reconcile_non_attack_model_destruction_events(
            state=state,
            decisions=self.decision_controller,
        )

    def _request_stratagem_cost_choice_if_available(
        self,
        *,
        source_request: DecisionRequest,
        source_result: DecisionResult,
        selection: tuple[
            StratagemEligibilityContext,
            StratagemCatalogRecord,
            StratagemTargetBinding,
            JsonValue,
        ]
        | None,
    ) -> LifecycleStatus | None:
        if selection is None:
            raise GameLifecycleError("Prevalidated stratagem result is missing selection.")
        context, catalog_record, target_binding, effect_selection = selection
        cost_choice_hooks = (
            self._require_runtime_content_bundle().stratagem_cost_choice_hook_registry
        )
        request = cost_choice_hooks.next_request_for(
            StratagemCostChoiceRequestContext(
                state=self._require_state(),
                decisions=self.decision_controller,
                source_request=source_request,
                source_result=source_result,
                definition=catalog_record.definition,
                eligibility_context=context,
                target_binding=target_binding,
                effect_selection=effect_selection,
            )
        )
        if request is None:
            return None
        if request.decision_type != SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE:
            raise GameLifecycleError("Stratagem cost choice hook returned decision_type drift.")
        self.decision_controller.request_decision(request)
        if self._result_resolves_active_reaction_frame(source_result):
            self.reaction_queue.continue_reaction(
                result=source_result,
                next_request_id=request.request_id,
                decisions=self.decision_controller,
            )
        return LifecycleStatus.waiting_for_decision(
            stage=self._require_state().stage,
            decision_request=request,
            payload={
                "game_id": self._require_state().game_id,
                "pending_request_id": request.request_id,
                "source_decision_request_id": source_request.request_id,
                "source_decision_result_id": source_result.result_id,
            },
        )

    def _apply_stratagem_cost_choice_and_resume(
        self,
        *,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus:
        state = self._require_state()
        source_result = stratagem_cost_choice_source_result(request)
        source_record = self.decision_controller.record_for_result(source_result)
        selection = source_selection_for_cost_choice(source_record.request, source_result)
        context, catalog_record, target_binding, effect_selection = selection
        cost_choice_hooks = (
            self._require_runtime_content_bundle().stratagem_cost_choice_hook_registry
        )
        handled = cost_choice_hooks.apply_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=self.decision_controller,
                request=request,
                result=result,
                source_request=source_record.request,
                source_result=source_result,
                definition=catalog_record.definition,
                eligibility_context=context,
                target_binding=target_binding,
                effect_selection=effect_selection,
            )
        )
        if not handled:
            raise GameLifecycleError("Stratagem cost choice result was not handled.")
        next_choice_status = self._request_stratagem_cost_choice_if_available(
            source_request=source_record.request,
            source_result=source_result,
            selection=selection,
        )
        if next_choice_status is not None:
            return next_choice_status
        runtime_content_bundle = self._require_runtime_content_bundle()
        if source_record.request.decision_type == STRATAGEM_DECISION_TYPE:
            invalid_status = invalid_stratagem_use_status(
                state=state,
                request=source_record.request,
                result=source_result,
                decisions=self.decision_controller,
                stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
            )
            cost_increase_unaffordable = invalid_status_is_unaffordable_cost_increase(
                invalid_status=invalid_status,
                state=state,
                result=source_result,
                decisions=self.decision_controller,
                stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
            )
            if invalid_status is not None and not cost_increase_unaffordable:
                return invalid_status
            apply_stratagem_decision(
                state=state,
                result=source_result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
                runtime_content_bundle=runtime_content_bundle,
                stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
                shooting_unit_selected_grant_hooks=(
                    runtime_content_bundle.shooting_unit_selected_grant_hook_registry
                ),
                resolve_unaffordable_cost_increase_as_used=cost_increase_unaffordable,
            )
            if self._result_resolves_active_reaction_frame(result):
                follow_up_request = self._pending_decision_request()
                if follow_up_request is not None and is_command_reroll_decision_request(
                    follow_up_request
                ):
                    self.reaction_queue.continue_reaction(
                        result=result,
                        next_request_id=follow_up_request.request_id,
                        decisions=self.decision_controller,
                    )
                else:
                    self.reaction_queue.resolve_reaction(
                        result=result,
                        decisions=self.decision_controller,
                    )
            return self.advance_until_decision_or_terminal()
        invalid_status = invalid_stratagem_target_proposal_status(
            state=state,
            request=source_record.request,
            result=source_result,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
            decisions=self.decision_controller,
            shooting_target_restriction_hooks=runtime_content_bundle.shooting_target_restriction_hook_registry,
            stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
        )
        cost_increase_unaffordable = invalid_status_is_unaffordable_cost_increase(
            invalid_status=invalid_status,
            state=state,
            result=source_result,
            decisions=self.decision_controller,
            stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
        )
        if invalid_status is not None and not cost_increase_unaffordable:
            return invalid_status
        apply_stratagem_target_proposal(
            state=state,
            result=source_result,
            decisions=self.decision_controller,
            ruleset_descriptor=self._require_config().ruleset_descriptor,
            army_catalog=self._require_config().army_catalog,
            runtime_content_bundle=runtime_content_bundle,
            stratagem_cost_modifier_registry=runtime_content_bundle.stratagem_cost_modifier_registry,
            shooting_unit_selected_grant_hooks=(
                runtime_content_bundle.shooting_unit_selected_grant_hook_registry
            ),
            resolve_unaffordable_cost_increase_as_used=cost_increase_unaffordable,
        )
        advanced_status = self.advance_until_decision_or_terminal()
        if self._result_resolves_active_reaction_frame(result):
            if self._fight_interrupt_activation_is_active():
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
            elif advanced_status.decision_request is not None:
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=advanced_status.decision_request.request_id,
                    decisions=self.decision_controller,
                )
            else:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
        return advanced_status

    def _result_resolves_active_reaction_frame(self, result: DecisionResult) -> bool:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("Reaction frame check requires a DecisionResult.")
        frames = self.reaction_queue.frames
        return bool(frames and frames[-1].request_id == result.request_id)

    def _continue_or_resolve_fight_reaction(
        self,
        *,
        result: DecisionResult,
        status: LifecycleStatus,
    ) -> None:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("Fight reaction handling requires a DecisionResult.")
        if type(status) is not LifecycleStatus:
            raise GameLifecycleError("Fight reaction handling requires a LifecycleStatus.")
        if self._fight_interrupt_activation_is_active() and status.decision_request is not None:
            self.reaction_queue.continue_reaction(
                result=result,
                next_request_id=status.decision_request.request_id,
                decisions=self.decision_controller,
            )
            return
        if self._fight_interrupt_activation_is_active():
            pending_request = self._pending_decision_request()
            if pending_request is not None and _fight_decision_owns_request(
                state=self._require_state(),
                request=pending_request,
            ):
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=pending_request.request_id,
                    decisions=self.decision_controller,
                )
                return
        self.reaction_queue.resolve_reaction(
            result=result,
            decisions=self.decision_controller,
        )

    def _fight_interrupt_activation_is_active(self) -> bool:
        state = self._require_state()
        fight_state = state.fight_phase_state
        if fight_state is None:
            return False
        activation = fight_state.active_activation
        return activation is not None and activation.interrupt_id is not None

    def _record_stratagem_window_declined(self, result: DecisionResult) -> None:
        record = self.decision_controller.record_for_result(result)
        self.decision_controller.event_log.append(
            STRATAGEM_WINDOW_DECLINED_EVENT_TYPE,
            stratagem_window_decline_event_payload(request=record.request, result=result),
        )

    def _opportunity_boundary_state_hash(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
    ) -> str:
        records = self._opportunity_boundary_records(request=request)
        return opportunity_boundary_state_hash(
            state_payload=opportunity_boundary_game_state_payload(
                game_id=state.game_id,
                ruleset_descriptor_hash=state.ruleset_descriptor_hash,
                stage=state.stage.value,
                battle_phase_index=state.battle_phase_index,
                battle_round=state.battle_round,
                active_player_id=state.active_player_id,
                player_ids=state.player_ids,
                turn_order=state.turn_order,
                decision_request_count=state.decision_request_count,
                command_point_ledgers=cast(
                    JsonValue,
                    [ledger.to_payload() for ledger in state.command_point_ledgers],
                ),
                stratagem_use_records=cast(
                    JsonValue,
                    [record.to_payload() for record in state.stratagem_use_records],
                ),
                faction_rule_states=cast(
                    JsonValue,
                    [record.to_payload() for record in state.faction_rule_states],
                ),
            ),
            event_count=len(records),
            last_event_id=None if not records else records[-1].event_id,
        )

    def _opportunity_boundary_sequence_number(self, *, request: DecisionRequest) -> int:
        return len(self._opportunity_boundary_records(request=request))

    def _opportunity_boundary_records(self, *, request: DecisionRequest) -> tuple[EventRecord, ...]:
        records = self.decision_controller.event_log.records
        while records:
            last = records[-1]
            if last.event_type == "decision_requested":
                if not isinstance(last.payload, dict):
                    raise GameLifecycleError("decision_requested event payload must be an object.")
                if last.payload.get("request_id") != request.request_id:
                    return records
                records = records[:-1]
                continue
            if last.event_type == "reaction_window_continued":
                if not isinstance(last.payload, dict):
                    raise GameLifecycleError(
                        "reaction_window_continued event payload must be an object."
                    )
                if last.payload.get("next_request_id") != request.request_id:
                    return records
                records = records[:-1]
                continue
            return records
        return records

    def _continue_or_resolve_out_of_phase_reaction(
        self,
        *,
        result: DecisionResult,
        status: LifecycleStatus | None,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        if status is not None and status.decision_request is not None:
            self.reaction_queue.continue_reaction(
                result=result,
                next_request_id=status.decision_request.request_id,
                decisions=self.decision_controller,
            )
            return status
        if status is None and state.out_of_phase_shooting_state is not None:
            advanced_status = self._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
                state=state,
                decisions=self.decision_controller,
            )
            if advanced_status is not None and advanced_status.decision_request is not None:
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=advanced_status.decision_request.request_id,
                    decisions=self.decision_controller,
                )
                return advanced_status
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
            return advanced_status
        self.reaction_queue.resolve_reaction(
            result=result,
            decisions=self.decision_controller,
        )
        return status


def _runtime_content_audit_from_payload(value: object) -> Mapping[str, JsonValue] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GameLifecycleError("GameLifecycle runtime content audit must be a mapping.")
    payload = cast(dict[object, object], value)
    return cast(Mapping[str, JsonValue], validate_json_value(payload))


def _destroyed_transport_attack_sequence_for_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> AttackSequence:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    sequence_id = required_movement_proposal_context_string(
        proposal_request, key="attack_sequence_id"
    )
    from warhammer40k_core.engine.retained_destruction_cleanup import (
        active_retained_attack_destruction,
        attack_sequence_for_retained_destruction,
    )

    retained = active_retained_attack_destruction(state=state)
    if retained is not None:
        sequence = attack_sequence_for_retained_destruction(retained)
        if sequence.sequence_id != sequence_id:
            raise GameLifecycleError("Retained Transport placement sequence drift.")
        return sequence
    fight_state = state.fight_phase_state
    if (
        fight_state is not None
        and fight_state.attack_sequence is not None
        and fight_state.attack_sequence.sequence_id == sequence_id
    ):
        return fight_state.attack_sequence
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and out_of_phase_state.attack_sequence is not None
        and out_of_phase_state.attack_sequence.sequence_id == sequence_id
    ):
        return out_of_phase_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if (
        shooting_state is not None
        and shooting_state.attack_sequence is not None
        and shooting_state.attack_sequence.sequence_id == sequence_id
    ):
        return shooting_state.attack_sequence
    raise GameLifecycleError("Destroyed Transport placement request has no attack sequence.")


def _destroyed_transport_request_is_fight_owned(
    *,
    state: GameState,
    request: DecisionRequest,
) -> bool:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    sequence_id = required_movement_proposal_context_string(
        proposal_request, key="attack_sequence_id"
    )
    fight_state = state.fight_phase_state
    return (
        fight_state is not None
        and fight_state.attack_sequence is not None
        and fight_state.attack_sequence.sequence_id == sequence_id
    )


def _is_opportunity_window_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Opportunity request routing requires a DecisionRequest.")
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    return payload.get("submission_family") == OPPORTUNITY_REQUEST_FAMILY


def _fight_decision_owns_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> bool:
    if request.decision_type in {
        FIGHT_ACTIVATION_DECISION_TYPE,
        _fa.FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    }:
        return True
    if _is_fight_movement_proposal_request(request):
        return True
    return fight_attack_sequence_is_active_for_request(state=state, request=request)
