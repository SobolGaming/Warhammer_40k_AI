from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.engine.advance_hooks import SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackSequence,
    current_legal_damage_allocation_model_ids,
    invalid_destroyed_transport_disembark_proposal_status,
    is_destroyed_transport_disembark_proposal_request,
)
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.charge_declaration_hooks import (
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    invalid_deployment_placement_status,
    is_deployment_placement_request,
)
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.enhancement_effects import apply_enhancement_effects
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
)
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
    runtime_content_activation_for_armies,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    apply_recorded_healing_model_decision,
    healing_effect_from_request,
    invalid_healing_model_decision_status,
)
from warhammer40k_core.engine.mission_decisions import (
    MISSION_DECISION_TYPES,
    START_MISSION_ACTION_DECISION_TYPE,
    apply_mission_decision,
    invalid_mission_decision_status,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
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
    SetupStep,
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
    invalid_command_phase_decision_status,
)
from warhammer40k_core.engine.phases.fight import (
    FightPhaseHandler,
    invalid_fight_activation_ability_status,
    invalid_fight_activation_status,
    invalid_fight_attack_sequence_selection_status,
    invalid_fight_interrupt_status,
    invalid_fight_movement_proposal_status,
    invalid_melee_declaration_status,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_DISEMBARK_UNIT_DECISION_TYPE,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    MovementPhaseHandler,
)
from warhammer40k_core.engine.phases.shooting import (
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
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueuePayload,
)
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
    invalid_reserve_declaration_status,
)
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingDecision,
    apply_sequencing_decision_from_request,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    STRATAGEM_WINDOW_DECLINED_EVENT_TYPE,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    apply_command_reroll_decision,
    apply_explosives_mortal_wound_feel_no_pain_decision,
    apply_heroic_intervention_charge_move,
    apply_stratagem_decision,
    apply_stratagem_placement_proposal,
    apply_stratagem_target_proposal,
    invalid_command_reroll_decision_status,
    invalid_heroic_intervention_charge_move_status,
    invalid_stratagem_placement_proposal_status,
    invalid_stratagem_target_proposal_status,
    invalid_stratagem_use_status,
    is_command_reroll_decision_request,
    is_heroic_intervention_charge_move_request,
    is_stratagem_placement_proposal_request,
    is_stratagem_window_decline_result,
    stratagem_window_decline_allowed,
    stratagem_window_decline_event_payload,
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
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency


class GameLifecyclePayload(TypedDict):
    config: GameConfigPayload | None
    parameterized_movement_proposals: bool
    state: GameStatePayload
    decisions: DecisionControllerPayload
    reaction_queue: ReactionQueuePayload
    runtime_content_audit: NotRequired[dict[str, JsonValue]]


MAX_LIFECYCLE_TRANSITIONS = 128
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
        SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
        SELECT_DISEMBARK_UNIT_DECISION_TYPE,
        SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
    )
)
_TRIGGERED_MOVEMENT_DECISION_TYPES = frozenset((SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,))
_SHOOTING_DECISION_TYPES = frozenset(
    (
        SELECT_SHOOTING_UNIT_DECISION_TYPE,
        SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
        SELECT_SHOOTING_TYPE_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
    )
)
_CHARGE_DECISION_TYPES = frozenset(
    (
        SELECT_CHARGING_UNIT_DECISION_TYPE,
        SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
    )
)
_COMMAND_DECISION_TYPES = frozenset(
    (
        TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
        TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
    )
)
_FIGHT_DECISION_TYPES = frozenset(
    (
        FIGHT_ACTIVATION_DECISION_TYPE,
        FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
)
_REACTION_FRAME_DECISION_TYPES = frozenset(
    (
        REACTION_DECISION_TYPE,
        FIGHT_INTERRUPT_DECISION_TYPE,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        SELECT_HEALING_MODEL_DECISION_TYPE,
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
        SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    )
)
_BATTLE_ROUND_DECISION_TYPES = frozenset((SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,))


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
    payload = validate_json_value(
        {
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
    )
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
    if type(base_indexes) is not tuple:
        raise GameLifecycleError("Runtime Stratagem index base indexes must be a tuple.")
    records_by_id: dict[str, StratagemCatalogRecord] = {}
    for base_index in base_indexes:
        if type(base_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("Runtime Stratagem index base value must be an index.")
        for record in base_index.all_records():
            existing = records_by_id.get(record.record_id)
            if existing is not None and existing != record:
                raise GameLifecycleError("Base Stratagem record ID drift across phase indexes.")
            records_by_id[record.record_id] = record
    for player_index in bundle.stratagem_indexes_by_player_id.values():
        for record in player_index.all_records():
            existing = records_by_id.get(record.record_id)
            if existing is not None and existing != record:
                raise GameLifecycleError("Runtime Stratagem record ID drift across player indexes.")
            records_by_id[record.record_id] = record
    return StratagemCatalogIndex.from_records(
        tuple(records_by_id[record_id] for record_id in sorted(records_by_id))
    )


@dataclass(slots=True)
class GameLifecycle:
    decision_controller: DecisionController = field(default_factory=_new_decision_controller)
    reaction_queue: ReactionQueue = field(default_factory=ReactionQueue)
    state: GameState | None = None
    parameterized_movement_proposals: bool = True
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

    def __post_init__(self) -> None:
        if type(self.parameterized_movement_proposals) is not bool:
            raise GameLifecycleError(
                "GameLifecycle parameterized_movement_proposals must be a bool."
            )
        if not self.parameterized_movement_proposals:
            raise GameLifecycleError("GameLifecycle requires parameterized movement proposals.")

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
            phase_end_objective_control_hooks=(
                self._runtime_content_bundle.phase_end_objective_control_hook_registry
                if self._runtime_content_bundle is not None
                else None
            ),
            runtime_modifier_registry=(
                self._runtime_content_bundle.runtime_modifier_registry
                if self._runtime_content_bundle is not None
                else None
            ),
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
        for _transition_index in range(MAX_LIFECYCLE_TRANSITIONS):
            status = self._advance_once()
            if status.status_kind in (
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            ):
                return status
        raise GameLifecycleError("GameLifecycle exceeded deterministic transition guard.")

    def _advance_once(self) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        if pending_request is not None:
            return LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=pending_request,
                payload={
                    "game_id": state.game_id,
                    "pending_request_id": pending_request.request_id,
                },
            )
        out_of_phase_status = self._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
            state=state,
            decisions=self.decision_controller,
        )
        if out_of_phase_status is not None:
            return out_of_phase_status
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
        return self._require_battle_round_flow().advance(
            state=state,
            decisions=self.decision_controller,
            reaction_queue=self.reaction_queue,
        )

    def submit_decision(self, result: DecisionResult) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        sequencing_decision: SequencingDecision | None = None
        stratagem_placement_request: DecisionRequest | None = None
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and _is_opportunity_window_request(pending_request)
        ):
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
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and is_stratagem_placement_proposal_request(pending_request)
        ):
            stratagem_placement_request = pending_request
        if stratagem_placement_request is not None:
            result.validate_for_request(stratagem_placement_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_stratagem_placement_proposal_status(
                state=state,
                request=stratagem_placement_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        destroyed_transport_placement_request = (
            pending_request
            if (
                type(result) is DecisionResult
                and pending_request is not None
                and is_destroyed_transport_disembark_proposal_request(pending_request)
            )
            else None
        )
        if destroyed_transport_placement_request is not None:
            result.validate_for_request(destroyed_transport_placement_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            attack_sequence = _destroyed_transport_attack_sequence_for_request(
                state=state,
                request=destroyed_transport_placement_request,
            )
            invalid_status = invalid_destroyed_transport_disembark_proposal_status(
                state=state,
                request=destroyed_transport_placement_request,
                result=result,
                decisions=self.decision_controller,
                attack_sequence=attack_sequence,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and is_deployment_placement_request(pending_request)
        ):
            result.validate_for_request(pending_request)
            invalid_status = invalid_deployment_placement_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and is_prebattle_proposal_request(pending_request)
        ):
            result.validate_for_request(pending_request)
            invalid_status = invalid_prebattle_proposal_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type in _MOVEMENT_PROPOSAL_DECISION_TYPES
            and stratagem_placement_request is None
            and destroyed_transport_placement_request is None
        ):
            result.validate_for_request(pending_request)
            if is_heroic_intervention_charge_move_request(pending_request):
                malformed_status = invalid_heroic_intervention_charge_move_status(
                    state=state,
                    request=pending_request,
                    result=result,
                )
            elif is_triggered_movement_proposal_request(pending_request):
                malformed_status = invalid_triggered_movement_proposal_status(
                    state=state,
                    request=pending_request,
                    result=result,
                    decisions=self.decision_controller,
                )
            elif _is_fight_movement_proposal_request(pending_request):
                malformed_status = invalid_fight_movement_proposal_status(
                    state=state,
                    request=pending_request,
                    result=result,
                    decisions=self.decision_controller,
                    ruleset_descriptor=self._require_config().ruleset_descriptor,
                )
            elif _is_charge_move_proposal_request(pending_request):
                malformed_status = invalid_charge_move_proposal_status(
                    state=state,
                    request=pending_request,
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
                    request=pending_request,
                    result=result,
                    decisions=self.decision_controller,
                )
            if malformed_status is not None:
                return malformed_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            invalid_status = self._shooting_phase_handler.invalid_shooting_type_selection_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
        ):
            invalid_status = (
                self._shooting_phase_handler.invalid_shooting_unit_selected_grant_status(
                    state=state,
                    request=pending_request,
                    result=result,
                )
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = self._shooting_phase_handler.invalid_declaration_submission_status(
                state=state,
                request=pending_request,
                result=result,
                decisions=self.decision_controller,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_melee_declaration_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type
            in (
                SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
            )
        ):
            if _fight_attack_sequence_is_active_for_request(
                state=state,
                request=pending_request,
            ):
                invalid_status = invalid_fight_attack_sequence_selection_status(
                    state=state,
                    request=pending_request,
                    result=result,
                )
            else:
                invalid_status = (
                    self._shooting_phase_handler.invalid_attack_sequence_selection_status(
                        state=state,
                        request=pending_request,
                        result=result,
                    )
                )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
        ):
            invalid_status = _invalid_damage_allocation_model_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
        ):
            invalid_status = invalid_charging_unit_selection_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                charge_target_restriction_hooks=(
                    self._require_runtime_content_bundle().charge_target_restriction_hook_registry
                ),
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE
        ):
            invalid_status = invalid_charge_declaration_grant_status(
                state=state,
                request=pending_request,
                result=result,
                charge_declaration_hooks=(self._charge_phase_handler.charge_declaration_hooks),
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
        ):
            invalid_status = invalid_fight_activation_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE
        ):
            invalid_status = invalid_fight_activation_ability_status(
                state=state,
                request=pending_request,
                result=result,
                decisions=self.decision_controller,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == FIGHT_INTERRUPT_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_fight_interrupt_status(
                state=state,
                request=pending_request,
                result=result,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            and is_mortal_wound_feel_no_pain_request(pending_request)
        ):
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=pending_request,
                result=result,
                invalid_reason="invalid_mortal_wound_feel_no_pain_result",
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
        ):
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_healing_model_decision_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and is_command_reroll_decision_request(pending_request)
        ):
            invalid_status = invalid_command_reroll_decision_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        ):
            invalid_status = _invalid_destruction_reaction_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
        ):
            invalid_status = invalid_reserve_declaration_status(
                state=state,
                config=self._require_config(),
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
        ):
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=pending_request,
                result=result,
                invalid_reason="invalid_faction_rule_setup_option_result",
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type
            == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
        ):
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=pending_request,
                result=result,
                invalid_reason="invalid_faction_rule_battle_round_option_result",
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type in _COMMAND_DECISION_TYPES
        ):
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=pending_request,
                result=result,
                invalid_reason="invalid_command_phase_decision_result",
            )
            if invalid_status is not None:
                return invalid_status
            invalid_status = invalid_command_phase_decision_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type in MISSION_DECISION_TYPES
        ):
            result.validate_for_request(pending_request)
            invalid_status = invalid_mission_decision_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == REACTION_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            self.reaction_queue.validate_result(result)
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == STRATAGEM_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            if is_stratagem_window_decline_result(result) and not stratagem_window_decline_allowed(
                request=pending_request,
                result=result,
            ):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Stratagem window decline is not allowed for this request.",
                    payload={"invalid_reason": "decline_not_allowed"},
                )
            if not is_stratagem_window_decline_result(result):
                invalid_status = invalid_stratagem_use_status(
                    state=state,
                    request=pending_request,
                    result=result,
                )
                if invalid_status is not None:
                    return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            if is_stratagem_window_decline_result(result) and not stratagem_window_decline_allowed(
                request=pending_request,
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
                    request=pending_request,
                    result=result,
                    ruleset_descriptor=self._require_config().ruleset_descriptor,
                    army_catalog=self._require_config().army_catalog,
                )
                if invalid_status is not None:
                    return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SEQUENCING_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            sequencing_decision = apply_sequencing_decision_from_request(
                request=pending_request,
                result=result,
            )
        record = self.decision_controller.submit_result(result)
        if record.request.decision_type in _SETUP_DECISION_TYPES:
            self._setup_flow.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                config=self._require_config(),
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _BATTLE_ROUND_DECISION_TYPES:
            self._require_battle_round_flow().apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _COMMAND_DECISION_TYPES:
            self._command_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in MISSION_DECISION_TYPES:
            apply_mission_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if record.request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
                return LifecycleStatus.advanced(
                    stage=state.stage,
                    payload={
                        "decision_type": START_MISSION_ACTION_DECISION_TYPE,
                        "result_id": result.result_id,
                    },
                )
            return self.advance_until_decision_or_terminal()
        if is_stratagem_placement_proposal_request(record.request):
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            placement_status = apply_stratagem_placement_proposal(
                state=state,
                request=record.request,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
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
        if is_command_reroll_decision_request(record.request):
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            apply_command_reroll_decision(
                state=state,
                request=record.request,
                result=result,
                decisions=self.decision_controller,
            )
            if resolves_reaction_frame:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
        if (
            record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
            and is_heroic_intervention_charge_move_request(record.request)
        ):
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            heroic_status = apply_heroic_intervention_charge_move(
                state=state,
                request=record.request,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if heroic_status is not None:
                if resolves_reaction_frame:
                    retry_request = self._pending_decision_request()
                    if retry_request is not None and is_heroic_intervention_charge_move_request(
                        retry_request
                    ):
                        self.reaction_queue.continue_reaction(
                            result=result,
                            next_request_id=retry_request.request_id,
                            decisions=self.decision_controller,
                        )
                return heroic_status
            if resolves_reaction_frame:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
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
        if (
            record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
            and _is_charge_move_proposal_request(record.request)
        ):
            charge_status = self._charge_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if charge_status is not None:
                return charge_status
            return self.advance_until_decision_or_terminal()
        if (
            record.request.decision_type == DICE_REROLL_DECISION_TYPE
            and state.current_battle_phase is BattlePhase.CHARGE
        ):
            charge_status = self._charge_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if charge_status is not None:
                return charge_status
            return self.advance_until_decision_or_terminal()
        if is_destroyed_transport_disembark_proposal_request(record.request):
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
        if record.request.decision_type in _MOVEMENT_DECISION_TYPES:
            movement_status = self._movement_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                reaction_queue=self.reaction_queue,
            )
            if movement_status is not None:
                return movement_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            healing_effect = healing_effect_from_request(request=record.request)
            _updated_effect, follow_up_request = apply_recorded_healing_model_decision(
                state=state,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                request=record.request,
                result=result,
                effect=healing_effect,
            )
            if follow_up_request is not None:
                healing_status = LifecycleStatus.waiting_for_decision(
                    stage=state.stage,
                    decision_request=follow_up_request,
                    payload={
                        "decision_type": SELECT_HEALING_MODEL_DECISION_TYPE,
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
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
                if advanced_status.decision_request is not None:
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
        if record.request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            fight_status = self._fight_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                reaction_queue=self.reaction_queue,
            )
            if resolves_reaction_frame and fight_status is not None:
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=fight_status,
                )
            if fight_status is not None:
                return fight_status
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
            return advanced_status
        if (
            record.request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            and is_mortal_wound_feel_no_pain_request(record.request)
        ):
            source_context = mortal_wound_feel_no_pain_source_context(record.request)
            if (
                isinstance(source_context, dict)
                and source_context.get("source_kind") == "explosives"
            ):
                explosives_status = apply_explosives_mortal_wound_feel_no_pain_decision(
                    state=state,
                    result=result,
                    decisions=self.decision_controller,
                )
                if explosives_status is not None:
                    return explosives_status
                return self.advance_until_decision_or_terminal()
            if (
                isinstance(source_context, dict)
                and source_context.get("source_kind") == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
            ):
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
        if record.request.decision_type in _FIGHT_DECISION_TYPES and _fight_decision_owns_request(
            state=state,
            request=record.request,
        ):
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
        if record.request.decision_type in _SHOOTING_DECISION_TYPES:
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
        if record.request.decision_type in _CHARGE_DECISION_TYPES:
            charge_status = self._charge_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if charge_status is not None:
                return charge_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _FIGHT_DECISION_TYPES:
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
        if record.request.decision_type == FIGHT_INTERRUPT_DECISION_TYPE:
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
            if resolves_reaction_frame:
                advanced_status = self.advance_until_decision_or_terminal()
                self._continue_or_resolve_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
                return advanced_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _TRIGGERED_MOVEMENT_DECISION_TYPES:
            triggered_status = self._triggered_movement_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if triggered_status is not None:
                return triggered_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == REACTION_DECISION_TYPE:
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == STRATAGEM_DECISION_TYPE:
            if is_stratagem_window_decline_result(result):
                self._record_stratagem_window_declined(result)
                if self._result_resolves_active_reaction_frame(result):
                    self.reaction_queue.resolve_reaction(
                        result=result,
                        decisions=self.decision_controller,
                    )
                return self.advance_until_decision_or_terminal()
            apply_stratagem_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
                stratagem_handler_registry=self._require_runtime_content_bundle().stratagem_handler_registry,
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
        if record.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
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
            apply_stratagem_target_proposal(
                state=state,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
                stratagem_handler_registry=self._require_runtime_content_bundle().stratagem_handler_registry,
            )
            advanced_status = self.advance_until_decision_or_terminal()
            if resolves_reaction_frame:
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
        if record.request.decision_type == SEQUENCING_DECISION_TYPE:
            if sequencing_decision is None:
                sequencing_decision = apply_sequencing_decision_from_request(
                    request=record.request,
                    result=result,
                )
            self.decision_controller.event_log.append(
                "sequencing_order_resolved",
                sequencing_decision.to_payload(),
            )
            return self.advance_until_decision_or_terminal()
        raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")

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
        return payload

    @classmethod
    def from_payload(cls, payload: GameLifecyclePayload) -> Self:
        config_payload = payload["config"]
        config = None if config_payload is None else GameConfig.from_payload(config_payload)
        parameterized_movement_proposals = _payload_bool(
            "GameLifecycle parameterized_movement_proposals",
            payload["parameterized_movement_proposals"],
        )
        lifecycle = cls(
            decision_controller=DecisionController.from_payload(payload["decisions"]),
            reaction_queue=ReactionQueue.from_payload(payload["reaction_queue"]),
            state=GameState.from_payload(payload["state"]),
            parameterized_movement_proposals=parameterized_movement_proposals,
            _config=config,
            _runtime_content_audit=_runtime_content_audit_from_payload(
                payload.get("runtime_content_audit")
            ),
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
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
        _validate_payload_consistency(state=lifecycle._require_state(), config=lifecycle._config)
        _validate_reaction_queue_consistency(
            state=lifecycle._require_state(),
            reaction_queue=lifecycle.reaction_queue,
            pending_request=lifecycle._pending_decision_request(),
        )
        lifecycle._refresh_runtime_content_bundle_if_armies_mustered()
        lifecycle._battle_round_flow = BattleRoundFlow(
            phase_handlers=lifecycle._phase_handlers(),
            battle_round_start_hooks=(
                lifecycle._runtime_content_bundle.battle_round_start_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            phase_end_objective_control_hooks=(
                lifecycle._runtime_content_bundle.phase_end_objective_control_hook_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
            runtime_modifier_registry=(
                lifecycle._runtime_content_bundle.runtime_modifier_registry
                if lifecycle._runtime_content_bundle is not None
                else None
            ),
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

    def _pending_decision_request(self) -> DecisionRequest | None:
        pending_requests = self.decision_controller.queue.pending_requests
        if not pending_requests:
            return None
        return pending_requests[0]

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

    def _refresh_runtime_content_bundle_if_armies_mustered(self) -> None:
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
        if (
            self._runtime_content_bundle is not None
            and self._runtime_content_bundle.activation.activation_hash
            == activation.activation_hash
        ):
            self._runtime_content_activation_input_hash = activation_input_hash
            return
        self._runtime_content_bundle = build_runtime_content_bundle_for_armies(
            config=self._config,
            armies=armies,
        )
        self._setup_flow = replace(
            self._setup_flow,
            battle_formation_hooks=self._runtime_content_bundle.battle_formation_hook_registry,
        )
        runtime_stratagem_index = _combined_runtime_stratagem_index(
            self._runtime_content_bundle,
            base_indexes=(
                self._command_phase_handler.stratagem_index,
                self._movement_phase_handler.stratagem_index,
                self._shooting_phase_handler.stratagem_index,
                self._fight_phase_handler.stratagem_index,
            ),
        )
        apply_enhancement_effects(
            state=state,
            registry=self._runtime_content_bundle.enhancement_effect_registry,
            decisions=self.decision_controller,
        )
        self._command_phase_handler = CommandPhaseHandler(
            stratagem_index=runtime_stratagem_index,
            battle_shock_hooks=self._runtime_content_bundle.battle_shock_hook_registry,
            command_phase_start_hooks=(
                self._runtime_content_bundle.command_phase_start_hook_registry
            ),
            ability_indexes_by_player_id=(
                self._runtime_content_bundle.ability_indexes_by_player_id
            ),
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._movement_phase_handler = MovementPhaseHandler(
            ruleset_descriptor=self._movement_phase_handler.ruleset_descriptor,
            parameterized_proposals=self._movement_phase_handler.parameterized_proposals,
            stratagem_index=runtime_stratagem_index,
            advance_eligibility_hooks=(
                self._runtime_content_bundle.advance_eligibility_hook_registry
            ),
            advance_move_hooks=self._runtime_content_bundle.advance_move_hook_registry,
            fall_back_hooks=self._runtime_content_bundle.fall_back_hook_registry,
            movement_end_surge_hooks=(
                self._runtime_content_bundle.movement_end_surge_hook_registry
            ),
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._charge_phase_handler = ChargePhaseHandler(
            ruleset_descriptor=self._charge_phase_handler.ruleset_descriptor,
            charge_declaration_hooks=self._runtime_content_bundle.charge_declaration_hook_registry,
            charge_target_restriction_hooks=(
                self._runtime_content_bundle.charge_target_restriction_hook_registry
            ),
            ability_indexes_by_player_id=(
                self._runtime_content_bundle.ability_indexes_by_player_id
            ),
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._shooting_phase_handler = ShootingPhaseHandler(
            ruleset_descriptor=self._shooting_phase_handler.ruleset_descriptor,
            army_catalog=self._shooting_phase_handler.army_catalog,
            stratagem_index=runtime_stratagem_index,
            shooting_unit_selected_hooks=(
                self._runtime_content_bundle.shooting_unit_selected_hook_registry
            ),
            shooting_unit_selected_grant_hooks=(
                self._runtime_content_bundle.shooting_unit_selected_grant_hook_registry
            ),
            shooting_target_restriction_hooks=(
                self._runtime_content_bundle.shooting_target_restriction_hook_registry
            ),
            shooting_end_surge_hooks=self._runtime_content_bundle.shooting_end_surge_hook_registry,
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._fight_phase_handler = FightPhaseHandler(
            ruleset_descriptor=self._fight_phase_handler.ruleset_descriptor,
            army_catalog=self._fight_phase_handler.army_catalog,
            stratagem_index=runtime_stratagem_index,
            fight_activation_ability_hooks=(
                self._runtime_content_bundle.fight_activation_ability_hook_registry
            ),
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._battle_round_flow = BattleRoundFlow(
            phase_handlers=self._phase_handlers(),
            battle_round_start_hooks=self._runtime_content_bundle.battle_round_start_hook_registry,
            phase_end_objective_control_hooks=(
                self._runtime_content_bundle.phase_end_objective_control_hook_registry
            ),
            unit_destroyed_hooks=self._runtime_content_bundle.unit_destroyed_hook_registry,
            runtime_modifier_registry=self._runtime_content_bundle.runtime_modifier_registry,
        )
        self._runtime_content_activation_input_hash = _runtime_content_activation_input_hash(
            config=self._config,
            armies=tuple(state.army_definitions),
        )
        summary = self._runtime_content_bundle.to_summary_payload()
        self._runtime_content_audit = cast(
            Mapping[str, JsonValue],
            validate_json_value(summary),
        )

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


def _payload_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


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
    sequence_id = _proposal_context_string(proposal_request, key="attack_sequence_id")
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
    sequence_id = _proposal_context_string(proposal_request, key="attack_sequence_id")
    fight_state = state.fight_phase_state
    return (
        fight_state is not None
        and fight_state.attack_sequence is not None
        and fight_state.attack_sequence.sequence_id == sequence_id
    )


def _proposal_context_string(
    proposal_request: MovementProposalRequest,
    *,
    key: str,
) -> str:
    context = proposal_request.context or {}
    value = context.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Proposal request context missing string key: {key}.")
    return value


def _is_charge_move_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Charge proposal routing requires a DecisionRequest.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return (
        proposal_request.phase == BattlePhase.CHARGE.value
        or proposal_request.proposal_kind is ProposalKind.CHARGE_MOVE
    )


def _is_fight_movement_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Fight proposal routing requires a DecisionRequest.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return proposal_request.phase == BattlePhase.FIGHT.value or proposal_request.proposal_kind in {
        ProposalKind.PILE_IN,
        ProposalKind.CONSOLIDATE,
    }


def _is_opportunity_window_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Opportunity request routing requires a DecisionRequest.")
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    return payload.get("submission_family") == OPPORTUNITY_REQUEST_FAMILY


def _fight_attack_sequence_is_active_for_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> bool:
    if request.decision_type not in (
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    ):
        return False
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.attack_sequence is None:
        return False
    if request.decision_type in (
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    ):
        return True
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    sequence_id = payload.get("sequence_id")
    return type(sequence_id) is str and sequence_id == fight_state.attack_sequence.sequence_id


def _fight_decision_owns_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> bool:
    if request.decision_type in {
        FIGHT_ACTIVATION_DECISION_TYPE,
        FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    }:
        return True
    if _is_fight_movement_proposal_request(request):
        return True
    return _fight_attack_sequence_is_active_for_request(state=state, request=request)


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _invalid_damage_allocation_model_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_damage_allocation_model_result",
    )
    if invalid_status is not None:
        return invalid_status
    request_payload = request.payload
    if not isinstance(request_payload, Mapping):
        raise GameLifecycleError("Damage allocation model request payload must be an object.")
    attack_context = request_payload.get("attack_context")
    if not isinstance(attack_context, Mapping):
        raise GameLifecycleError("Damage allocation model attack context must be an object.")
    attack_sequence = _active_attack_sequence_for_state(state)
    if attack_sequence is None or attack_sequence.pending_grouped_damage is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model has no pending grouped damage.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "pending_grouped_damage",
            },
        )
    pending = attack_sequence.pending_grouped_damage
    if pending.next_index >= len(pending.sorted_save_dice):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model pending die is exhausted.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "next_index",
            },
        )
    current_context = pending.sorted_save_dice[pending.next_index]["attack_context"]
    expected_fields: tuple[tuple[str, object], ...] = (
        ("sequence_id", attack_sequence.sequence_id),
        ("attack_context_id", current_context["attack_context_id"]),
        ("pool_index", attack_sequence.pool_index),
        ("attack_index", current_context["attack_index"]),
        ("generated_hit_index", current_context["generated_hit_index"]),
    )
    for field_name, expected_value in expected_fields:
        if attack_context.get(field_name) != expected_value:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Damage allocation model attack context no longer matches state.",
                payload={
                    "invalid_reason": "invalid_damage_allocation_model_result",
                    "field": field_name,
                },
            )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if not isinstance(selected_payload, Mapping):
        raise GameLifecycleError("Damage allocation model option payload must be an object.")
    selected_model_id = selected_payload.get("selected_model_id")
    if selected_model_id != result.selected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model selected model does not match the option.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "selected_model_id",
            },
        )
    legal_model_ids = current_legal_damage_allocation_model_ids(
        state=state,
        attack_sequence=attack_sequence,
    )
    if legal_model_ids is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model has no current allocation group.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "allocation_group",
            },
        )
    if selected_model_id not in legal_model_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model selected model is no longer legal.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "selected_model_id",
            },
        )
    return None


def _invalid_destruction_reaction_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_destruction_reaction_result",
    )
    if invalid_status is not None:
        return invalid_status
    request_payload = request.payload
    if not isinstance(request_payload, Mapping):
        raise GameLifecycleError("Destruction reaction request payload must be an object.")
    destruction_context = request_payload.get("destruction_context")
    if not isinstance(destruction_context, Mapping):
        raise GameLifecycleError("Destruction reaction context must be an object.")
    attack_context = destruction_context.get("attack_context")
    if not isinstance(attack_context, Mapping):
        raise GameLifecycleError("Destruction reaction attack context must be an object.")
    attack_sequence = _active_attack_sequence_for_state(state)
    if attack_sequence is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Destruction reaction has no active attack sequence.",
            payload={
                "invalid_reason": "invalid_destruction_reaction_result",
                "field": "attack_sequence",
            },
        )
    expected_fields: tuple[tuple[str, object], ...] = (
        ("sequence_id", attack_sequence.sequence_id),
        ("attack_context_id", attack_sequence.attack_context_id()),
        ("pool_index", attack_sequence.pool_index),
        ("attack_index", attack_sequence.attack_index),
        ("generated_hit_index", attack_sequence.generated_hit_index),
    )
    for field_name, expected_value in expected_fields:
        if attack_context.get(field_name) != expected_value:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Destruction reaction attack context no longer matches state.",
                payload={
                    "invalid_reason": "invalid_destruction_reaction_result",
                    "field": field_name,
                },
            )
    return None


def _active_attack_sequence_for_state(state: GameState) -> AttackSequence | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        return out_of_phase_state.attack_sequence
    fight_state = state.fight_phase_state
    if fight_state is not None and fight_state.attack_sequence is not None:
        return fight_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and shooting_state.attack_sequence is not None:
        return shooting_state.attack_sequence
    return None


def _validate_payload_consistency(*, state: GameState, config: GameConfig | None) -> None:
    _validate_reserve_state_consistency(state=state)
    _validate_transport_cargo_state_consistency(state=state)
    _validate_battlefield_state_consistency(state=state, config=config)
    _validate_movement_phase_state_consistency(state=state)
    _validate_shooting_phase_state_consistency(state=state)
    _validate_charge_phase_state_consistency(state=state)
    _validate_fight_phase_state_consistency(state=state)
    _validate_disembarked_unit_state_consistency(state=state)
    _validate_advanced_unit_state_consistency(state=state)
    _validate_fell_back_unit_state_consistency(state=state)
    _validate_surge_move_state_consistency(state=state)
    if config is None:
        return
    if state.game_id != config.game_id:
        raise GameLifecycleError("Lifecycle state game_id does not match config.")
    if state.player_ids != config.player_ids:
        raise GameLifecycleError("Lifecycle state player_ids do not match config.")
    if state.turn_order != config.turn_order:
        raise GameLifecycleError("Lifecycle state turn_order does not match config.")
    if state.tactical_secondary_draw_count != config.tactical_secondary_draw_count:
        raise GameLifecycleError(
            "Lifecycle state tactical secondary draw count does not match config."
        )
    expected_hash = config.ruleset_descriptor.descriptor_hash
    if state.ruleset_descriptor_hash != expected_hash:
        raise GameLifecycleError("Lifecycle state ruleset hash does not match config.")
    expected_setup = tuple(config.ruleset_descriptor.setup_sequence.steps)
    if state.setup_sequence != expected_setup:
        raise GameLifecycleError("Lifecycle state setup sequence does not match config.")
    expected_battle = tuple(config.ruleset_descriptor.battle_phase_sequence.phases)
    if state.battle_phase_sequence != expected_battle:
        raise GameLifecycleError("Lifecycle state battle phase sequence does not match config.")
    _validate_mustered_army_consistency(state=state, config=config)


def _validate_mustered_army_consistency(*, state: GameState, config: GameConfig) -> None:
    if not state.army_definitions and not _state_requires_mustered_armies(state):
        return
    try:
        expected_armies = tuple(
            sorted(
                (
                    muster_army(catalog=config.army_catalog, request=request)
                    for request in config.army_muster_requests
                ),
                key=lambda army: army.player_id,
            )
        )
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Lifecycle config army muster requests are invalid.") from exc
    expected_payloads = [army.to_payload() for army in expected_armies]
    state_payloads = [army.to_payload() for army in state.army_definitions]
    if _state_requires_mustered_armies(state) and not state_payloads:
        raise GameLifecycleError("Lifecycle state is missing mustered army definitions.")
    if state_payloads and state_payloads != expected_payloads:
        raise GameLifecycleError("Lifecycle state army definitions do not match config.")


def _validate_reaction_queue_consistency(
    *,
    state: GameState,
    reaction_queue: ReactionQueue,
    pending_request: DecisionRequest | None,
) -> None:
    frames = reaction_queue.frames
    if not frames:
        if pending_request is not None and pending_request.decision_type == REACTION_DECISION_TYPE:
            raise GameLifecycleError("Lifecycle pending reaction decision requires a frame.")
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Lifecycle reaction queue requires battle stage.")
    if state.current_battle_phase is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a current battle phase.")
    if pending_request is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a pending decision.")
    if pending_request.decision_type not in _REACTION_FRAME_DECISION_TYPES:
        raise GameLifecycleError("Lifecycle reaction queue pending decision_type drift.")
    if (
        pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and not is_stratagem_placement_proposal_request(pending_request)
        and not is_destroyed_transport_disembark_proposal_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending placement decision drift.")
    if (
        pending_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and not is_heroic_intervention_charge_move_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending movement decision drift.")
    seen_request_ids: set[str] = set()
    for frame in frames:
        if frame.request_id is None:
            raise GameLifecycleError("Lifecycle reaction queue frame requires request_id.")
        if frame.request_id in seen_request_ids:
            raise GameLifecycleError("Lifecycle reaction queue request_ids must be unique.")
        seen_request_ids.add(frame.request_id)
        if frame.reaction_window.timing_window.game_id != state.game_id:
            raise GameLifecycleError("Lifecycle reaction queue frame game_id drift.")
        if frame.parent_phase is not state.current_battle_phase:
            raise GameLifecycleError("Lifecycle reaction queue frame phase drift.")
    if frames[-1].request_id != pending_request.request_id:
        raise GameLifecycleError("Lifecycle reaction queue active frame request_id drift.")


def _validate_battlefield_state_consistency(
    *,
    state: GameState,
    config: GameConfig | None,
) -> None:
    if state.battlefield_state is None:
        if _state_requires_battlefield_state(state):
            raise GameLifecycleError("Lifecycle state is missing battlefield_state.")
        return
    if not _state_allows_battlefield_state(state):
        raise GameLifecycleError(
            "Lifecycle state battlefield_state must be absent before DEPLOY_ARMIES."
        )
    if _state_is_before_deploy_armies(state) and (
        state.battlefield_state.placed_armies or state.battlefield_state.removed_model_ids
    ):
        raise GameLifecycleError(
            "Lifecycle state battlefield_state must not contain placed or removed models "
            "before DEPLOY_ARMIES."
        )
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        if _state_requires_deployed_battlefield_state(state):
            scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
        if config is not None and _state_requires_deployed_battlefield_state(state):
            assert_battlefield_units_in_coherency(
                scenario=scenario,
                ruleset_descriptor=config.ruleset_descriptor,
            )
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state battlefield_state is invalid.") from exc


def _validate_reserve_state_consistency(*, state: GameState) -> None:
    if not state.reserve_states:
        return
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    for reserve_state in state.reserve_states:
        owner = unit_owner_by_id.get(reserve_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("reserve_states unit is unknown.")
        if owner != reserve_state.player_id:
            raise GameLifecycleError("reserve_states player_id does not match unit owner.")
        for embarked_unit_id in reserve_state.embarked_unit_instance_ids:
            embarked_owner = unit_owner_by_id.get(embarked_unit_id)
            if embarked_owner is None:
                raise GameLifecycleError("reserve_states embarked unit is unknown.")
            if embarked_owner != reserve_state.player_id:
                raise GameLifecycleError("reserve_states embarked unit owner drift.")

    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for reserve_state in state.reserve_states:
        reserve_model_ids = set(model_ids_by_unit_id[reserve_state.unit_instance_id])
        embarked_model_ids = {
            model_id
            for embarked_unit_id in reserve_state.embarked_unit_instance_ids
            for model_id in model_ids_by_unit_id[embarked_unit_id]
        }
        if reserve_state.status is ReserveStatus.IN_RESERVES:
            if (reserve_model_ids | embarked_model_ids) & placed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be placed.")
            if (reserve_model_ids | embarked_model_ids) & removed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be removed.")
        if reserve_state.status is ReserveStatus.ARRIVED:
            if not reserve_model_ids <= placed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must be placed.")
            if reserve_model_ids & removed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must not be removed.")
        if (
            reserve_state.status is ReserveStatus.DESTROYED
            and not (reserve_model_ids | embarked_model_ids) <= removed_model_ids
        ):
            raise GameLifecycleError("destroyed reserve models must be removed.")


def _validate_transport_cargo_state_consistency(*, state: GameState) -> None:
    if not state.transport_cargo_states:
        return
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    embarked_unit_ids: set[str] = set()
    for cargo_state in state.transport_cargo_states:
        transport = unit_by_id.get(cargo_state.transport_unit_instance_id)
        if transport is None:
            raise GameLifecycleError("transport_cargo_states transport unit is unknown.")
        if owner_by_unit_id[cargo_state.transport_unit_instance_id] != cargo_state.player_id:
            raise GameLifecycleError("transport_cargo_states player_id does not match owner.")
        if transport.datasheet_id != cargo_state.capacity_profile.transport_datasheet_id:
            raise GameLifecycleError("transport_cargo_states transport datasheet drift.")
        cargo_model_count = 0
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            embarked_unit = unit_by_id.get(embarked_unit_id)
            if embarked_unit is None:
                raise GameLifecycleError("transport_cargo_states embarked unit is unknown.")
            if owner_by_unit_id[embarked_unit_id] != cargo_state.player_id:
                raise GameLifecycleError("transport_cargo_states embarked unit owner drift.")
            if embarked_unit_id in embarked_unit_ids:
                raise GameLifecycleError("unit cannot be embarked in more than one Transport.")
            embarked_unit_ids.add(embarked_unit_id)
            if not cargo_state.capacity_profile.allows_unit(embarked_unit):
                raise GameLifecycleError("transport_cargo_states capacity profile rejects cargo.")
            cargo_model_count += len(embarked_unit.own_models)
        if cargo_model_count > cargo_state.capacity_profile.max_model_count:
            raise GameLifecycleError("transport_cargo_states capacity is exceeded.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_unit_ids = {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for cargo_state in state.transport_cargo_states:
        if cargo_state.transport_unit_instance_id not in placed_unit_ids:
            raise GameLifecycleError("transport_cargo_states transport unit must be placed.")
        transport_model_ids = set(model_ids_by_unit_id[cargo_state.transport_unit_instance_id])
        if transport_model_ids & removed_model_ids:
            raise GameLifecycleError("transport_cargo_states transport models must not be removed.")
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            model_ids = set(model_ids_by_unit_id[embarked_unit_id])
            if model_ids & placed_model_ids:
                raise GameLifecycleError("embarked unit models must not be placed.")
            if model_ids & removed_model_ids:
                raise GameLifecycleError("embarked unit models must not be removed.")


def _validate_movement_phase_state_consistency(*, state: GameState) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("movement_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("movement_phase_state requires MOVEMENT phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("movement_phase_state requires active player.")
    if movement_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("movement_phase_state active player drift.")
    if movement_state.battle_round != state.battle_round:
        raise GameLifecycleError("movement_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("movement_phase_state requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state movement_phase_state is invalid.") from exc

    try:
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
        active_player_unit_ids: set[str] = {
            placement.unit_instance_id for placement in placed_army.unit_placements
        }
    except PlacementError:
        active_player_unit_ids = set()
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_reserve_unit_ids = _unarrived_reserve_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for unit_id in (*movement_state.selected_unit_ids, *movement_state.moved_unit_ids):
        if (
            unit_id not in active_player_unit_ids
            and unit_id not in fully_removed_active_player_unit_ids
            and unit_id not in active_player_embarked_unit_ids
            and unit_id not in active_player_reserve_unit_ids
        ):
            raise GameLifecycleError(
                "movement_phase_state selected unit is not active player's unit."
            )
    if movement_state.active_selection is None:
        return
    active_unit_id = movement_state.active_selection.unit_instance_id
    if active_unit_id not in movement_state.selected_unit_ids:
        raise GameLifecycleError("movement_phase_state active selection drift.")
    if active_unit_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "movement_phase_state active selection is not active player's unit."
        )


def _validate_shooting_phase_state_consistency(*, state: GameState) -> None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("shooting_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("shooting_phase_state requires SHOOTING phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("shooting_phase_state requires active player.")
    if shooting_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("shooting_phase_state active player drift.")
    if shooting_state.battle_round != state.battle_round:
        raise GameLifecycleError("shooting_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("shooting_phase_state requires battlefield_state.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_unit_ids = {
        unit_id
        for unit_id, player_id in unit_owner_by_id.items()
        if player_id == state.active_player_id
    }
    for unit_id in (
        *shooting_state.selected_unit_ids,
        *shooting_state.shot_unit_ids,
        *shooting_state.skipped_unit_ids,
    ):
        if unit_id not in active_player_unit_ids and unit_id not in active_player_embarked_unit_ids:
            raise GameLifecycleError(
                "shooting_phase_state selected unit is not active player's unit."
            )
    active_selection = shooting_state.active_selection
    if active_selection is None:
        return
    if active_selection.unit_instance_id not in shooting_state.selected_unit_ids:
        raise GameLifecycleError("shooting_phase_state active selection drift.")
    if active_selection.unit_instance_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "shooting_phase_state active selection is not active player's unit."
        )


def _validate_charge_phase_state_consistency(*, state: GameState) -> None:
    charge_state = state.charge_phase_state
    if charge_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("charge_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.CHARGE:
        raise GameLifecycleError("charge_phase_state requires CHARGE phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("charge_phase_state requires active player.")
    if charge_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("charge_phase_state active player drift.")
    if charge_state.battle_round != state.battle_round:
        raise GameLifecycleError("charge_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("charge_phase_state requires battlefield_state.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    active_player_unit_ids = {
        unit_id
        for unit_id, player_id in unit_owner_by_id.items()
        if player_id == state.active_player_id
    }
    for unit_id in charge_state.selected_unit_ids:
        if unit_id not in active_player_unit_ids:
            raise GameLifecycleError(
                "charge_phase_state selected unit is not active player's unit."
            )
    active_selection = charge_state.active_selection
    if active_selection is not None:
        if active_selection.unit_instance_id not in charge_state.selected_unit_ids:
            raise GameLifecycleError("charge_phase_state active selection drift.")
        if active_selection.unit_instance_id not in active_player_unit_ids:
            raise GameLifecycleError(
                "charge_phase_state active selection is not active player's unit."
            )
    for distance_state in charge_state.distance_states:
        roll_result = distance_state.roll_result
        charging_unit_id = roll_result.request.unit_instance_id
        if charging_unit_id not in charge_state.selected_unit_ids:
            raise GameLifecycleError("charge_phase_state roll unit was not selected.")
        if charging_unit_id not in active_player_unit_ids:
            raise GameLifecycleError("charge_phase_state roll unit is not active player's unit.")
        for target_unit_id in roll_result.reachable_target_distances_inches:
            target_owner = unit_owner_by_id.get(target_unit_id)
            if target_owner is None:
                raise GameLifecycleError("charge_phase_state target unit is unknown.")
            if target_owner == state.active_player_id:
                raise GameLifecycleError("charge_phase_state target unit is not an enemy.")


def _validate_fight_phase_state_consistency(*, state: GameState) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("fight_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("fight_phase_state requires FIGHT phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("fight_phase_state requires active player.")
    if fight_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("fight_phase_state active player drift.")
    if fight_state.battle_round != state.battle_round:
        raise GameLifecycleError("fight_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("fight_phase_state requires battlefield_state.")
    fight_order_state = fight_state.fight_order_state
    if fight_order_state.next_player_id not in state.player_ids:
        raise GameLifecycleError("fight_phase_state next player is not in this game.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    known_unit_ids = set(unit_owner_by_id)
    for unit_id in (
        *fight_order_state.engaged_at_fight_step_start_unit_ids,
        *fight_order_state.selected_to_fight_unit_ids,
        *fight_order_state.fights_first_registry.charged_unit_ids(),
    ):
        if unit_id not in known_unit_ids:
            raise GameLifecycleError("fight_phase_state unit is unknown.")
    for player_id in fight_order_state.passed_player_ids:
        if player_id not in state.player_ids:
            raise GameLifecycleError("fight_phase_state passed player is not in this game.")
    for selection in fight_order_state.activation_selections:
        owner = unit_owner_by_id.get(selection.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("fight_phase_state activation unit is unknown.")
        if owner != selection.player_id:
            raise GameLifecycleError("fight_phase_state activation player drift.")
    for eligible_pass in fight_order_state.eligible_passes:
        if eligible_pass.player_id not in state.player_ids:
            raise GameLifecycleError("fight_phase_state pass player is not in this game.")
        for unit_id in eligible_pass.eligible_unit_ids:
            owner = unit_owner_by_id.get(unit_id)
            if owner is None:
                raise GameLifecycleError("fight_phase_state pass unit is unknown.")
            if owner != eligible_pass.player_id:
                raise GameLifecycleError("fight_phase_state pass unit player drift.")


def _validate_advanced_unit_state_consistency(*, state: GameState) -> None:
    if not state.advanced_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("advanced_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("advanced_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("advanced_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state advanced_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for advanced_state in state.advanced_unit_states:
        if advanced_state.player_id != state.active_player_id:
            raise GameLifecycleError("advanced_unit_states player drift.")
        if advanced_state.battle_round != state.battle_round:
            raise GameLifecycleError("advanced_unit_states battle round drift.")
        if (
            advanced_state.unit_instance_id not in active_player_unit_ids
            and advanced_state.unit_instance_id not in active_player_embarked_unit_ids
            and advanced_state.unit_instance_id not in fully_removed_active_player_unit_ids
        ):
            raise GameLifecycleError("advanced_unit_states unit is not active player's unit.")


def _validate_disembarked_unit_state_consistency(*, state: GameState) -> None:
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for disembarked_state in state.disembarked_unit_states:
        owner = unit_owner_by_id.get(disembarked_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("disembarked_unit_states unit is unknown.")
        if owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_owner = unit_owner_by_id.get(disembarked_state.transport_unit_instance_id)
        if transport_owner is None:
            raise GameLifecycleError("disembarked_unit_states transport unit is unknown.")
        if transport_owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")


def _validate_fell_back_unit_state_consistency(*, state: GameState) -> None:
    if not state.fell_back_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("fell_back_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("fell_back_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("fell_back_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state fell_back_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for fell_back_state in state.fell_back_unit_states:
        if fell_back_state.player_id != state.active_player_id:
            raise GameLifecycleError("fell_back_unit_states player drift.")
        if fell_back_state.battle_round != state.battle_round:
            raise GameLifecycleError("fell_back_unit_states battle round drift.")
        if (
            fell_back_state.unit_instance_id not in active_player_unit_ids
            and fell_back_state.unit_instance_id not in active_player_embarked_unit_ids
            and fell_back_state.unit_instance_id not in fully_removed_active_player_unit_ids
        ):
            raise GameLifecycleError("fell_back_unit_states unit is not active player's unit.")


def _validate_surge_move_state_consistency(*, state: GameState) -> None:
    if not state.surge_move_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("surge_move_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for surge_state in state.surge_move_states:
        owner = unit_owner_by_id.get(surge_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("surge_move_states unit is unknown.")
        if owner != surge_state.player_id:
            raise GameLifecycleError("surge_move_states player_id does not match unit owner.")


def _embarked_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        unit_id
        for cargo_state in state.transport_cargo_states
        if cargo_state.player_id == player_id
        for unit_id in cargo_state.embarked_unit_instance_ids
    }


def _unarrived_reserve_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        reserve_state.unit_instance_id
        for reserve_state in state.unarrived_reserve_states_for_player(player_id)
    }


def _fully_removed_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    if state.battlefield_state is None:
        raise GameLifecycleError("removed unit accounting requires battlefield_state.")
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    fully_removed_unit_ids: set[str] = set()
    for army_definition in state.army_definitions:
        if army_definition.player_id != player_id:
            continue
        for unit in army_definition.units:
            unit_model_ids = {model.model_instance_id for model in unit.own_models}
            if unit_model_ids and unit_model_ids <= removed_model_ids:
                fully_removed_unit_ids.add(unit.unit_instance_id)
    return fully_removed_unit_ids


def _state_requires_mustered_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        muster_step_index = state.setup_sequence.index(SetupStep.MUSTER_ARMIES)
    except ValueError as exc:
        raise GameLifecycleError(
            "Lifecycle state setup sequence must include MUSTER_ARMIES."
        ) from exc
    return state.setup_step_index > muster_step_index


def _state_requires_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        create_step_index = state.setup_sequence.index(SetupStep.CREATE_BATTLEFIELD)
    except ValueError:
        return False
    return state.setup_step_index > create_step_index


def _state_requires_deployed_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index > deploy_step_index


def _state_allows_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        create_step_index = state.setup_sequence.index(SetupStep.CREATE_BATTLEFIELD)
    except ValueError:
        return False
    return state.setup_step_index >= create_step_index


def _state_is_before_deploy_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return False
    if state.setup_step_index is None:
        return False
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index < deploy_step_index
