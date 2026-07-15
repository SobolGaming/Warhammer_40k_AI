from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import CatalogAbilitySupport
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    record_prebattle_action,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID = "catalog-ir:prebattle-redeploy-permission"


class RedeploySelectionPayloadFactory(Protocol):
    def __call__(
        self,
        *,
        state: GameState,
        ruleset_descriptor: RulesetDescriptor,
        army_catalog: ArmyCatalog,
        mission_setup: MissionSetup,
        view: RulesUnitView,
        setup_step: SetupStep,
        action_kind: PreBattleActionKind,
        source_rule_id: str,
        proposal_kind: str,
    ) -> JsonValue: ...


@dataclass(frozen=True, slots=True)
class CatalogPrebattleRedeployPermission:
    source_rule_id: str
    source_unit_instance_id: str
    required_keyword: str
    maximum_units: int
    allow_strategic_reserves: bool
    ignore_strategic_reserves_limit: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_identifier("source_unit_instance_id", self.source_unit_instance_id),
        )
        object.__setattr__(
            self,
            "required_keyword",
            _validate_identifier("required_keyword", self.required_keyword),
        )
        if type(self.maximum_units) is not int or self.maximum_units <= 0:
            raise GameLifecycleError("Catalog redeploy maximum_units must be positive.")
        if type(self.allow_strategic_reserves) is not bool:
            raise GameLifecycleError("Catalog redeploy Strategic Reserves flag must be bool.")
        if type(self.ignore_strategic_reserves_limit) is not bool:
            raise GameLifecycleError("Catalog redeploy reserve-limit flag must be bool.")


def clause_is_prebattle_redeploy_permission(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog redeploy classifier requires RuleClause.")
    if (
        not clause.is_supported
        or clause.template_id != "phase17c:placement-permission-restriction"
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.SETUP
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT
        or clause.duration is not None
    ):
        return False
    trigger = parameter_payload(clause.trigger.parameters)
    target = parameter_payload(clause.target.parameters)
    if not (
        trigger == {"edge": "after", "timing_window": "after_both_armies_deployed"}
        and target.get("allegiance") == "friendly"
        and type(target.get("required_keyword")) is str
        and frozenset(target) == frozenset({"allegiance", "required_keyword"})
    ):
        return False
    source_gate = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    )
    frequency = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    if len(source_gate) != 1 or len(frequency) != 1 or len(clause.conditions) != 2:
        return False
    source_gate_parameters = parameter_payload(source_gate[0].parameters)
    frequency_parameters = parameter_payload(frequency[0].parameters)
    effects_by_action = {
        parameter_payload(effect.parameters).get("action"): effect
        for effect in clause.effects
        if effect_is_prebattle_redeploy_permission(effect)
    }
    redeploy = effects_by_action.get("redeploy")
    strategic = effects_by_action.get("redeploy_to_strategic_reserves")
    if redeploy is None or strategic is None or len(effects_by_action) != 2:
        return False
    redeploy_parameters = parameter_payload(redeploy.parameters)
    strategic_parameters = parameter_payload(strategic.parameters)
    maximum_uses = frequency_parameters.get("maximum_uses")
    return (
        source_gate_parameters
        == {
            "gate_subject": "source_unit",
            "relationship": "source_unit_or_embarked_transport_on_battlefield",
        }
        and frequency_parameters.get("scope") == "battle"
        and type(maximum_uses) is int
        and maximum_uses > 0
        and redeploy_parameters
        == {"action": "redeploy", "allowed": True, "maximum_units": maximum_uses}
        and strategic_parameters
        == {
            "action": "redeploy_to_strategic_reserves",
            "allowed": True,
            "ignore_strategic_reserves_limit": True,
            "maximum_units": maximum_uses,
            "placement_kind": "strategic_reserves",
        }
    )


def effect_is_prebattle_redeploy_permission(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog redeploy effect classifier requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.PLACEMENT_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    maximum_units = parameters.get("maximum_units")
    if type(maximum_units) is not int or maximum_units <= 0:
        return False
    action = parameters.get("action")
    if action == "redeploy":
        return parameters == {
            "action": "redeploy",
            "allowed": True,
            "maximum_units": maximum_units,
        }
    return action == "redeploy_to_strategic_reserves" and parameters == {
        "action": "redeploy_to_strategic_reserves",
        "allowed": True,
        "ignore_strategic_reserves_limit": True,
        "maximum_units": maximum_units,
        "placement_kind": "strategic_reserves",
    }


def rule_has_prebattle_redeploy_permission(rule_ir: RuleIR) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog redeploy support requires RuleIR.")
    return any(clause_is_prebattle_redeploy_permission(clause) for clause in rule_ir.clauses)


def available_catalog_redeploy_permissions(
    *,
    state: GameState,
    player_id: str,
) -> tuple[CatalogPrebattleRedeployPermission, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Catalog redeploy player has no mustered army.")
    permissions: list[CatalogPrebattleRedeployPermission] = []
    for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
        for ability in unit.datasheet_abilities:
            if (
                ability.support is not CatalogAbilitySupport.GENERIC_RULE_IR
                or ability.rule_ir_payload is None
            ):
                continue
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
            for clause in rule_ir.clauses:
                if not clause_is_prebattle_redeploy_permission(clause):
                    continue
                permission = _permission_from_clause(
                    clause=clause,
                    rule_ir=rule_ir,
                    source_unit=unit,
                )
                use_count = _permission_use_count(state=state, permission=permission)
                source_is_available = _source_unit_is_available(state=state, unit=unit)
                # The source gate is checked when the sequential "up to" choice begins.
                # Once the permission has produced an action, keep that activation live
                # so redeploying the source unit itself does not discard its remaining
                # selections.
                if (source_is_available or use_count > 0) and use_count < permission.maximum_units:
                    permissions.append(permission)
    return tuple(
        sorted(
            permissions,
            key=lambda permission: (
                permission.source_rule_id,
                permission.source_unit_instance_id,
            ),
        )
    )


def catalog_redeploy_permission_for_view(
    *,
    state: GameState,
    player_id: str,
    view: RulesUnitView,
) -> CatalogPrebattleRedeployPermission | None:
    if type(view) is not RulesUnitView:
        raise GameLifecycleError("Catalog redeploy target requires RulesUnitView.")
    if view.owner_player_id != player_id:
        raise GameLifecycleError("Catalog redeploy target player_id drift.")
    for permission in available_catalog_redeploy_permissions(state=state, player_id=player_id):
        required = permission.required_keyword.strip().upper()
        if required in {
            keyword.strip().upper() for keyword in (*view.keywords, *view.faction_keywords)
        }:
            return permission
    return None


def catalog_redeploy_selection_options(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    mission_setup: MissionSetup,
    player_id: str,
    candidates: tuple[RulesUnitView, ...],
    core_source_rule_id: str,
    proposal_kind: str,
    payload_factory: RedeploySelectionPayloadFactory,
) -> tuple[DecisionOption, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    core_source_id = _validate_identifier("core_source_rule_id", core_source_rule_id)
    requested_proposal_kind = _validate_identifier("proposal_kind", proposal_kind)
    options: list[DecisionOption] = []
    for view in candidates:
        permission = catalog_redeploy_permission_for_view(
            state=state,
            player_id=requested_player_id,
            view=view,
        )
        source_rule_id = core_source_id if permission is None else permission.source_rule_id
        options.append(
            DecisionOption(
                option_id=f"redeploy:{view.unit_instance_id}",
                label=f"Redeploy {view.unit_instance_id}",
                payload=payload_factory(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=view,
                    setup_step=SetupStep.REDEPLOY_UNITS,
                    action_kind=PreBattleActionKind.REDEPLOY,
                    source_rule_id=source_rule_id,
                    proposal_kind=requested_proposal_kind,
                ),
            )
        )
        if permission is None or not permission.allow_strategic_reserves:
            continue
        strategic_payload_value = payload_factory(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            mission_setup=mission_setup,
            view=view,
            setup_step=SetupStep.REDEPLOY_UNITS,
            action_kind=PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES,
            source_rule_id=source_rule_id,
            proposal_kind=requested_proposal_kind,
        )
        if not isinstance(strategic_payload_value, dict):
            raise GameLifecycleError("Redeploy Strategic Reserves payload must be an object.")
        strategic_payload = strategic_payload_value
        strategic_payload["ignore_strategic_reserves_limit"] = (
            permission.ignore_strategic_reserves_limit
        )
        options.append(
            DecisionOption(
                option_id=f"redeploy_to_strategic_reserves:{view.unit_instance_id}",
                label=f"Put {view.unit_instance_id} into Strategic Reserves",
                payload=validate_json_value(strategic_payload),
            )
        )
    return tuple(options)


def apply_redeploy_to_strategic_reserves(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    points_contribution: int,
) -> ReserveState:
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Redeploy to Strategic Reserves requires setup stage.")
    if state.current_setup_step is not SetupStep.REDEPLOY_UNITS:
        raise GameLifecycleError("Redeploy to Strategic Reserves requires REDEPLOY_UNITS.")
    if result.actor_id is None or not isinstance(result.payload, dict):
        raise GameLifecycleError("Redeploy to Strategic Reserves requires a finite result.")
    payload = result.payload
    try:
        action_kind = PreBattleActionKind(_payload_string(payload, "action_kind"))
    except ValueError as exc:
        raise GameLifecycleError("Redeploy to Strategic Reserves action kind is invalid.") from exc
    if action_kind is not PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES:
        raise GameLifecycleError("Redeploy to Strategic Reserves action kind drift.")
    if payload.get("ignore_strategic_reserves_limit") is not True:
        raise GameLifecycleError("Redeploy to Strategic Reserves requires cap exemption.")
    player_id = _payload_string(payload, "player_id")
    if player_id != result.actor_id:
        raise GameLifecycleError("Redeploy to Strategic Reserves player drift.")
    unit_instance_id = _payload_string(payload, "unit_instance_id")
    source_rule_id = _payload_string(payload, "source_rule_id")
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    permission = catalog_redeploy_permission_for_view(
        state=state,
        player_id=player_id,
        view=view,
    )
    if permission is None or permission.source_rule_id != source_rule_id:
        raise GameLifecycleError("Redeploy to Strategic Reserves permission is unavailable.")
    if state.reserve_state_for_unit(view.unit_instance_id) is not None:
        raise GameLifecycleError("Redeployed unit already has a ReserveState.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Redeploy to Strategic Reserves requires battlefield_state.")
    rules_unit_placement = RulesUnitPlacement.from_battlefield(
        view=view,
        battlefield_state=battlefield,
    )
    embarked_unit_ids: set[str] = set()
    for component_unit_id in view.component_unit_instance_ids:
        cargo_state = state.transport_cargo_state_for_transport(component_unit_id)
        if cargo_state is not None:
            embarked_unit_ids.update(cargo_state.embarked_unit_instance_ids)
    reserve_state = ReserveState(
        player_id=player_id,
        unit_instance_id=view.unit_instance_id,
        reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        declared_during_step=SetupStep.REDEPLOY_UNITS.value,
        entered_reserves_battle_round=None,
        entered_reserves_phase=None,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            ruleset_descriptor.mission_policy
        ),
        source_rule_ids=(source_rule_id,),
        points_contribution=points_contribution,
        embarked_unit_instance_ids=tuple(sorted(embarked_unit_ids)),
    )
    updated_battlefield = rules_unit_placement.without_from_battlefield(battlefield)
    state.record_reserve_state(reserve_state)
    state.replace_battlefield_state(updated_battlefield)
    event_payload = validate_json_value(
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.REDEPLOY_UNITS.value,
            "player_id": player_id,
            "unit_instance_id": view.unit_instance_id,
            "component_unit_instance_ids": list(view.component_unit_instance_ids),
            "source_rule_id": source_rule_id,
            "ignore_strategic_reserves_limit": True,
            "reserve_state": reserve_state.to_payload(),
        }
    )
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES,
        unit_instance_id=view.unit_instance_id,
        source_rule_id=source_rule_id,
        payload=event_payload,
    )
    decisions.event_log.append("prebattle_redeploy_to_strategic_reserves", event_payload)
    return reserve_state


def _permission_from_clause(
    *,
    clause: RuleClause,
    rule_ir: RuleIR,
    source_unit: UnitInstance,
) -> CatalogPrebattleRedeployPermission:
    target = parameter_payload(clause.target.parameters) if clause.target is not None else {}
    frequency = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    maximum_units = parameter_payload(frequency.parameters).get("maximum_uses")
    required_keyword = target.get("required_keyword")
    if type(maximum_units) is not int or type(required_keyword) is not str:
        raise GameLifecycleError("Catalog redeploy descriptor is malformed.")
    return CatalogPrebattleRedeployPermission(
        source_rule_id=rule_ir.source_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        required_keyword=required_keyword,
        maximum_units=maximum_units,
        allow_strategic_reserves=True,
        ignore_strategic_reserves_limit=True,
    )


def _permission_use_count(
    *,
    state: GameState,
    permission: CatalogPrebattleRedeployPermission,
) -> int:
    return sum(
        1
        for record in state.prebattle_action_records
        if record.setup_step is SetupStep.REDEPLOY_UNITS
        and record.source_rule_id == permission.source_rule_id
        and record.action_kind
        in {
            PreBattleActionKind.REDEPLOY,
            PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES,
        }
    )


def _source_unit_is_available(*, state: GameState, unit: UnitInstance) -> bool:
    if not any(model.is_alive for model in unit.own_models):
        return False
    battlefield = state.battlefield_state
    if battlefield is None:
        return False
    if battlefield.unit_placement_or_none(unit.unit_instance_id) is not None:
        return True
    for cargo_state in state.transport_cargo_states:
        if unit.unit_instance_id not in cargo_state.embarked_unit_instance_ids:
            continue
        if battlefield.unit_placement_or_none(cargo_state.transport_unit_instance_id) is not None:
            return True
    return False


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
