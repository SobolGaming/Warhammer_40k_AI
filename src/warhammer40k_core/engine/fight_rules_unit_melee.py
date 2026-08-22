from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.fight_resolution import (
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
    melee_attack_sequence_from_proposal,
    melee_target_unit_ids,
    melee_targeting_permission_sources_for_model_target,
    record_one_shot_melee_weapon_uses,
    target_model_ids_for_melee_attack,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.movement_proposals import ProposalKind, ProposalValidationResult
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord
    from warhammer40k_core.engine.unit_factory import UnitInstance


def rules_unit_melee_target_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    state: GameState,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _canonical_target_unit_id(state=state, unit_instance_id=target_id)
                for unit in _present_component_units(state=state, rules_unit=rules_unit)
                for target_id in melee_target_unit_ids(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    unit_instance_id=unit.unit_instance_id,
                    state=state,
                )
            }
        )
    )


def rules_unit_available_melee_weapons_payloads(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    state: GameState,
    source_decision_result_id: str,
) -> tuple[JsonValue, ...]:
    if not rules_unit.is_attached_rules_unit:
        unit = rules_unit.components[0].unit
        physical_rows = available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit=unit,
            army_catalog=army_catalog,
            state=state,
            source_decision_result_id=source_decision_result_id,
        )
        canonical_rows: list[JsonValue] = []
        for payload in physical_rows:
            if not isinstance(payload, dict):
                raise GameLifecycleError("Melee weapon availability payload must be an object.")
            physical_target_ids = _payload_string_list(
                payload,
                "engaged_target_unit_instance_ids",
            )
            canonical_target_ids = _canonical_target_unit_ids(
                state=state,
                unit_instance_ids=physical_target_ids,
            )
            if all(
                _canonical_target_unit_id(state=state, unit_instance_id=target_id) == target_id
                for target_id in physical_target_ids
            ):
                canonical_rows.append(payload)
                continue
            canonical_rows.append(
                validate_json_value(
                    {
                        **payload,
                        "engaged_target_unit_instance_ids": list(canonical_target_ids),
                    }
                )
            )
        return tuple(canonical_rows)

    rows: list[dict[str, JsonValue]] = []
    for unit in _present_component_units(state=state, rules_unit=rules_unit):
        for payload in available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit=unit,
            army_catalog=army_catalog,
            state=state,
            source_decision_result_id=source_decision_result_id,
        ):
            if not isinstance(payload, dict):
                raise GameLifecycleError("Melee weapon availability payload must be an object.")
            physical_target_ids = _payload_string_list(
                payload,
                "engaged_target_unit_instance_ids",
            )
            rows.append(
                cast(
                    dict[str, JsonValue],
                    validate_json_value(
                        {
                            **payload,
                            "engaged_target_unit_instance_ids": list(
                                _canonical_target_unit_ids(
                                    state=state,
                                    unit_instance_ids=physical_target_ids,
                                )
                            ),
                            "rules_unit_instance_id": rules_unit.unit_instance_id,
                            "component_unit_instance_id": unit.unit_instance_id,
                        }
                    ),
                )
            )
    rows.sort(
        key=lambda row: (
            _payload_string(row, "component_unit_instance_id"),
            _payload_string(row, "model_instance_id"),
            _payload_string(row, "wargear_id"),
            _payload_string(row, "weapon_profile_id"),
        )
    )
    return tuple(rows)


def validate_rules_unit_melee_declaration(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MeleeDeclarationProposalRequest,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    state: GameState,
) -> ProposalValidationResult:
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit and not _request_has_attached_target(
        state=state,
        request=request,
    ):
        return validate_melee_declaration_rules(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            request=request,
            proposal=proposal,
            army_catalog=army_catalog,
            state=state,
        )
    if rules_unit.unit_instance_id != request.unit_instance_id:
        return _invalid(request=request, code="melee_rules_unit_identity_drift")
    current_target_ids = rules_unit_melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        state=state,
    )
    current_target_id_set = set(current_target_ids)
    if request.target_unit_instance_ids != current_target_ids:
        return _invalid_target_identity(request=request)
    if any(
        allocation.target_unit_instance_id not in current_target_id_set
        for declaration in proposal.declarations
        for allocation in declaration.target_allocations
    ):
        return _invalid_target_identity(request=request)
    declarations_by_component: dict[str, list[MeleeWeaponDeclaration]] = {
        component.unit.unit_instance_id: [] for component in rules_unit.components
    }
    for declaration in proposal.declarations:
        try:
            component_id = rules_unit.component_unit_id_for_model(
                declaration.attacker_model_instance_id
            )
        except GameLifecycleError:
            return _invalid(request=request, code="melee_model_outside_rules_unit")
        declarations_by_component[component_id].append(declaration)
    for component in sorted(
        rules_unit.components,
        key=lambda stored: stored.unit.unit_instance_id,
    ):
        component_id = component.unit.unit_instance_id
        declarations = tuple(declarations_by_component[component_id])
        physical_rows = available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit=component.unit,
            army_catalog=army_catalog,
            state=state,
            source_decision_result_id=request.source_decision_result_id,
        )
        if not declarations and not any(_row_has_engaged_target(row) for row in physical_rows):
            continue
        physical_declarations = _physical_component_declarations(
            state=state,
            declarations=declarations,
            physical_rows=physical_rows,
        )
        validation = validate_melee_declaration_rules(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            request=replace(
                request,
                unit_instance_id=component_id,
                available_weapons=physical_rows,
                target_unit_instance_ids=_physical_target_ids_for_rows(physical_rows),
            ),
            proposal=replace(
                proposal,
                unit_instance_id=component_id,
                declarations=physical_declarations,
            ),
            army_catalog=army_catalog,
            state=state,
        )
        if not validation.is_valid:
            return validation
    return ProposalValidationResult.valid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
    )


def rules_unit_melee_attack_sequence_from_proposal(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    dice_manager: DiceRollManager,
    sequence_id: str,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> AttackSequence:
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit and not _proposal_has_attached_target(
        state=state,
        proposal=proposal,
    ):
        return melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal=proposal,
            army_catalog=army_catalog,
            dice_manager=dice_manager,
            sequence_id=sequence_id,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    pools: list[RangedAttackPool] = []
    for index, component in enumerate(
        sorted(rules_unit.components, key=lambda stored: stored.unit.unit_instance_id),
        start=1,
    ):
        declarations = tuple(
            declaration
            for declaration in proposal.declarations
            if rules_unit.component_unit_id_for_model(declaration.attacker_model_instance_id)
            == component.unit.unit_instance_id
        )
        if not declarations:
            continue
        physical_rows = available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit=component.unit,
            army_catalog=army_catalog,
            state=state,
            source_decision_result_id=proposal.source_decision_result_id,
        )
        physical_declarations = _physical_component_declarations(
            state=state,
            declarations=declarations,
            physical_rows=physical_rows,
            require_mapping=True,
        )
        component_sequence = melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal=replace(
                proposal,
                unit_instance_id=component.unit.unit_instance_id,
                declarations=physical_declarations,
            ),
            army_catalog=army_catalog,
            dice_manager=dice_manager,
            sequence_id=f"{sequence_id}:component-{index:03d}",
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        pools.extend(
            _canonical_attack_pool(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                state=state,
                pool=pool,
                attacking_unit_instance_id=component.unit.unit_instance_id,
                physical_rows=physical_rows,
                source_decision_result_id=proposal.source_decision_result_id,
            )
            for pool in component_sequence.attack_pools
        )
    if not pools:
        raise GameLifecycleError("Rules-unit melee declaration produced no attack pools.")
    return AttackSequence(
        sequence_id=sequence_id,
        source_phase=BattlePhase.FIGHT,
        attacker_player_id=proposal.player_id,
        attacking_unit_instance_id=rules_unit.unit_instance_id,
        attack_pools=tuple(pools),
    )


def record_rules_unit_one_shot_melee_weapon_uses(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    result_id: str,
) -> tuple[OneShotWeaponUseRecord, ...]:
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        return record_one_shot_melee_weapon_uses(
            state=state,
            scenario=scenario,
            proposal=proposal,
            army_catalog=army_catalog,
            result_id=result_id,
        )
    records: list[OneShotWeaponUseRecord] = []
    for index, component in enumerate(
        sorted(rules_unit.components, key=lambda stored: stored.unit.unit_instance_id),
        start=1,
    ):
        declarations = tuple(
            declaration
            for declaration in proposal.declarations
            if rules_unit.component_unit_id_for_model(declaration.attacker_model_instance_id)
            == component.unit.unit_instance_id
        )
        if not declarations:
            continue
        records.extend(
            record_one_shot_melee_weapon_uses(
                state=state,
                scenario=scenario,
                proposal=replace(
                    proposal,
                    unit_instance_id=component.unit.unit_instance_id,
                    declarations=declarations,
                ),
                army_catalog=army_catalog,
                result_id=f"{result_id}:component-{index:03d}",
            )
        )
    return tuple(records)


def _canonical_rules_unit(*, state: GameState, unit_instance_id: str) -> RulesUnitView:
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.unit_instance_id != unit_instance_id:
        raise GameLifecycleError("Melee declaration requires a canonical rules-unit identity.")
    return rules_unit


def _present_component_units(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[UnitInstance, ...]:
    return tuple(
        component.unit
        for component in sorted(
            rules_unit.components,
            key=lambda stored: stored.unit.unit_instance_id,
        )
        if any(
            model_is_present_on_battlefield(
                state=state,
                model_instance_id=model.model_instance_id,
            )
            for model in component.unit.own_models
        )
    )


def _canonical_target_unit_id(*, state: GameState, unit_instance_id: str) -> str:
    return rules_unit_view_by_id(
        state=state,
        unit_instance_id=unit_instance_id,
    ).unit_instance_id


def _canonical_target_unit_ids(
    *,
    state: GameState,
    unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _canonical_target_unit_id(state=state, unit_instance_id=unit_id)
                for unit_id in unit_instance_ids
            }
        )
    )


def _proposal_has_attached_target(
    *,
    state: GameState,
    proposal: MeleeDeclarationProposal,
) -> bool:
    return any(
        rules_unit_view_by_id(
            state=state,
            unit_instance_id=allocation.target_unit_instance_id,
        ).is_attached_rules_unit
        for declaration in proposal.declarations
        for allocation in declaration.target_allocations
    )


def _request_has_attached_target(
    *,
    state: GameState,
    request: MeleeDeclarationProposalRequest,
) -> bool:
    return any(
        rules_unit_view_by_id(
            state=state,
            unit_instance_id=target_unit_instance_id,
        ).is_attached_rules_unit
        for target_unit_instance_id in request.target_unit_instance_ids
    )


def _physical_component_declarations(
    *,
    state: GameState,
    declarations: tuple[MeleeWeaponDeclaration, ...],
    physical_rows: tuple[JsonValue, ...],
    require_mapping: bool = False,
) -> tuple[MeleeWeaponDeclaration, ...]:
    targets_by_weapon = _physical_targets_by_weapon(physical_rows)
    translated: list[MeleeWeaponDeclaration] = []
    for declaration in declarations:
        physical_target_ids = targets_by_weapon.get(declaration.weapon_key)
        if physical_target_ids is None:
            translated.append(declaration)
            continue
        allocations: list[MeleeTargetAllocation] = []
        for allocation in declaration.target_allocations:
            matching_aliases = tuple(
                sorted(
                    target_id
                    for target_id in physical_target_ids
                    if _canonical_target_unit_id(state=state, unit_instance_id=target_id)
                    == allocation.target_unit_instance_id
                )
            )
            if not matching_aliases:
                if require_mapping:
                    raise GameLifecycleError(
                        "Accepted rules-unit melee target lost its physical engagement alias."
                    )
                allocations.append(allocation)
                continue
            allocations.append(
                replace(
                    allocation,
                    target_unit_instance_id=matching_aliases[0],
                )
            )
        translated.append(replace(declaration, target_allocations=tuple(allocations)))
    return tuple(translated)


def _physical_target_ids_for_rows(rows: tuple[JsonValue, ...]) -> tuple[str, ...]:
    targets: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GameLifecycleError("Melee weapon availability row must be an object.")
        targets.update(_payload_string_list(row, "engaged_target_unit_instance_ids"))
    return tuple(sorted(targets))


def _physical_targets_by_weapon(
    physical_rows: tuple[JsonValue, ...],
) -> dict[tuple[str, str, str], tuple[str, ...]]:
    targets_by_weapon: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for row in physical_rows:
        if not isinstance(row, dict):
            raise GameLifecycleError("Melee weapon availability row must be an object.")
        weapon_key = (
            _payload_string(row, "model_instance_id"),
            _payload_string(row, "wargear_id"),
            _payload_string(row, "weapon_profile_id"),
        )
        if weapon_key in targets_by_weapon:
            raise GameLifecycleError("Melee weapon availability keys must be unique.")
        targets_by_weapon[weapon_key] = _payload_string_list(
            row,
            "engaged_target_unit_instance_ids",
        )
    return targets_by_weapon


def _canonical_attack_pool(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    state: GameState,
    pool: RangedAttackPool,
    attacking_unit_instance_id: str,
    physical_rows: tuple[JsonValue, ...],
    source_decision_result_id: str,
) -> RangedAttackPool:
    target = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    )
    if target.unit_instance_id == pool.target_unit_instance_id:
        return pool
    physical_target_ids = _physical_targets_by_weapon(physical_rows).get(
        (pool.attacker_model_instance_id, pool.wargear_id, pool.weapon_profile_id)
    )
    if physical_target_ids is None:
        raise GameLifecycleError("Melee attack pool lost its physical availability row.")
    eligible_aliases = tuple(
        sorted(
            target_id
            for target_id in physical_target_ids
            if _canonical_target_unit_id(state=state, unit_instance_id=target_id)
            == target.unit_instance_id
        )
    )
    if pool.target_unit_instance_id not in eligible_aliases:
        raise GameLifecycleError("Melee attack pool target lost its physical engagement alias.")
    target_model_ids = tuple(
        sorted(
            {
                model_id
                for target_id in eligible_aliases
                for model_id in target_model_ids_for_melee_attack(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    unit_instance_id=attacking_unit_instance_id,
                    model_instance_id=pool.attacker_model_instance_id,
                    target_unit_instance_id=target_id,
                    state=state,
                    source_decision_result_id=source_decision_result_id,
                )
            }
        )
    )
    permission_source_ids = tuple(
        sorted(
            {
                source_id
                for target_id in eligible_aliases
                for source_id in melee_targeting_permission_sources_for_model_target(
                    scenario=scenario,
                    target_unit_instance_id=target_id,
                    attacker_model_instance_id=pool.attacker_model_instance_id,
                    state=state,
                    source_decision_result_id=source_decision_result_id,
                )
            }
        )
    )
    return replace(
        pool,
        target_unit_instance_id=target.unit_instance_id,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
        targeting_rule_ids=tuple(dict.fromkeys((*pool.targeting_rule_ids, *permission_source_ids))),
    )


def _row_has_engaged_target(row: JsonValue) -> bool:
    if not isinstance(row, dict):
        raise GameLifecycleError("Melee weapon availability row must be an object.")
    targets = row.get("engaged_target_unit_instance_ids")
    if not isinstance(targets, list):
        raise GameLifecycleError("Melee weapon availability targets must be a list.")
    return bool(targets)


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Melee weapon availability {key} must be a string.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        raise GameLifecycleError(f"Melee weapon availability {key} must be a string list.")
    return tuple(cast(list[str], value))


def _invalid(
    *,
    request: MeleeDeclarationProposalRequest,
    code: str,
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
        violation_code=code,
        message="Melee declaration does not match its canonical rules unit.",
        field="unit_instance_id",
    )


def _invalid_target_identity(
    *,
    request: MeleeDeclarationProposalRequest,
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
        violation_code="melee_target_identity_not_canonical",
        message="Melee declarations must target canonical rules-unit identities.",
        field="target_allocations",
    )


__all__ = (
    "record_rules_unit_one_shot_melee_weapon_uses",
    "rules_unit_available_melee_weapons_payloads",
    "rules_unit_melee_attack_sequence_from_proposal",
    "rules_unit_melee_target_unit_ids",
    "validate_rules_unit_melee_declaration",
)
