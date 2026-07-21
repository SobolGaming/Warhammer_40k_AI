from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceEvent,
    AttackSequenceStep,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    ShootingPhaseStartRequestContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.unit_factory import (
    UnitInstance,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def player_ability_index(
    *,
    package: CanonicalCatalogPackage,
    army: ArmyDefinition,
) -> AbilityCatalogIndex:
    return build_player_ability_index(
        catalog_ability_records_from_catalog(package.army_catalog),
        army=army,
        catalog=package.army_catalog,
    )


def battle_state_with_army(
    *,
    army: ArmyDefinition,
    battlefield: BattlefieldRuntimeState,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="phase17k-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id=army.player_id,
        player_ids=(army.player_id, "player-opponent"),
        turn_order=(army.player_id, "player-opponent"),
        tactical_secondary_draw_count=2,
    )
    state.record_army_definition(army)
    state.battlefield_state = battlefield
    return state


def battle_state_with_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield: BattlefieldRuntimeState,
    active_player_id: str,
    phase: BattlePhase,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    battle_phase_sequence = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="phase17k-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=battle_phase_sequence,
        setup_step_index=None,
        battle_phase_index=battle_phase_sequence.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=tuple(army.player_id for army in armies),
        turn_order=tuple(army.player_id for army in armies),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = battlefield
    return state


def bloodcrushers_battlefield_state(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
) -> BattlefieldRuntimeState:
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(12.0 + (index * 2.0), 12.0),
        )
        for index, model in enumerate(unit.own_models)
    )
    return BattlefieldRuntimeState(
        battlefield_id="phase17k-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_placements=placements,
                    ),
                ),
            ),
        ),
    )


def single_model_unit_placement(
    army: ArmyDefinition, unit: UnitInstance, *, x: float
) -> UnitPlacement:
    model = unit.own_models[0]
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x, 12.0),
            ),
        ),
    )


def flesh_hounds_battlefield_state(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    enemy_army: ArmyDefinition,
    enemy_unit: UnitInstance,
    enemy_x: float,
) -> BattlefieldRuntimeState:
    friendly_placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(12.0 + (index * 2.0), 12.0),
        )
        for index, model in enumerate(unit.own_models)
    )
    enemy_placements = tuple(
        ModelPlacement(
            army_id=enemy_army.army_id,
            player_id=enemy_army.player_id,
            unit_instance_id=enemy_unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(enemy_x + (index * 2.0), 12.0),
        )
        for index, model in enumerate(enemy_unit.own_models)
    )
    return BattlefieldRuntimeState(
        battlefield_id="phase17k-flesh-hounds-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_placements=friendly_placements,
                    ),
                ),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=enemy_army.army_id,
                        player_id=enemy_army.player_id,
                        unit_instance_id=enemy_unit.unit_instance_id,
                        model_placements=enemy_placements,
                    ),
                ),
            ),
        ),
    )


def current_model_ids(
    *,
    battlefield: BattlefieldRuntimeState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    return tuple(
        placement.model_instance_id
        for placement in battlefield.unit_placement_by_id(unit.unit_instance_id).model_placements
    )


def record_by_runtime_clause_suffix(
    records: tuple[AbilityCatalogRecord, ...],
    *,
    suffix: str,
) -> AbilityCatalogRecord:
    matches = tuple(record for record in records if _runtime_clause_id(record).endswith(suffix))
    if len(matches) != 1:
        raise ValueError(f"Expected one runtime clause suffix match, found {len(matches)}.")
    return matches[0]


def _runtime_clause_id(record: AbilityCatalogRecord) -> str:
    payload = record.definition.replay_payload
    if not isinstance(payload, dict):
        raise TypeError("Runtime clause fixture requires a mapping replay payload.")
    value = payload.get("runtime_clause_id")
    if type(value) is not str:
        raise ValueError("Runtime clause fixture requires a string runtime_clause_id.")
    return value


def set_state_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = tuple(state.battle_phase_sequence).index(phase)


def set_current_model_wounds(
    state: GameState, *, model_instance_id: str, wounds_remaining: int
) -> None:
    armies: list[ArmyDefinition] = []
    updated = False
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            models = tuple(
                replace(model, wounds_remaining=wounds_remaining)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            if models != unit.own_models:
                updated = True
            units.append(replace(unit, own_models=models))
        armies.append(replace(army, units=tuple(units)))
    if not updated:
        raise ValueError(f"Missing current model: {model_instance_id}.")
    state.army_definitions = armies


def pending_completed_attack_sequence_for_test(state: GameState) -> AttackSequence | None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise ValueError("Attack-sequence fixture requires shooting phase state.")
    return shooting_state.pending_completed_attack_sequence


def shooting_phase_start_request_context(
    *,
    state: GameState,
    decisions: DecisionController,
    army_catalog: ArmyCatalog,
) -> ShootingPhaseStartRequestContext:
    return ShootingPhaseStartRequestContext(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
    )


def weapon_profile_by_name(catalog: ArmyCatalog, name: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        for profile in wargear.weapon_profiles:
            if profile.name == name:
                return profile
    raise ValueError(f"Missing weapon profile: {name}.")


def datasheet_weapon_profile(
    catalog: ArmyCatalog, *, datasheet_id: str, profile_name: str
) -> WeaponProfile:
    wargear_prefix = f"{datasheet_id}:"
    for wargear in catalog.wargear:
        if not wargear.wargear_id.startswith(wargear_prefix):
            continue
        for profile in wargear.weapon_profiles:
            if profile.name == profile_name:
                return profile
    raise ValueError(f"Missing {datasheet_id} weapon profile: {profile_name}.")


def model_characteristic(unit: UnitInstance, characteristic: Characteristic) -> int:
    for value in unit.own_models[0].characteristics:
        if value.characteristic is characteristic:
            return value.final
    raise ValueError(f"Missing model characteristic: {characteristic.value}.")


def _wargear_id_for_weapon_profile(catalog: ArmyCatalog, weapon_profile_id: str) -> str:
    for wargear in catalog.wargear:
        for profile in wargear.weapon_profiles:
            if profile.profile_id == weapon_profile_id:
                return wargear.wargear_id
    raise ValueError(f"Missing wargear for weapon profile: {weapon_profile_id}.")


def completed_post_shoot_attack_sequence(
    *,
    package: CanonicalCatalogPackage,
    attacker: UnitInstance,
    attacker_player_id: str = "player-daemons",
    target: UnitInstance,
    attacker_model_instance_ids: tuple[str, ...] | None = None,
) -> AttackSequence:
    bolt_profile = weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    target_model_ids = tuple(model.model_instance_id for model in target.own_models)
    attacker_model_ids = (
        (attacker.own_models[0].model_instance_id,)
        if attacker_model_instance_ids is None
        else attacker_model_instance_ids
    )
    wargear_id = _wargear_id_for_weapon_profile(package.army_catalog, bolt_profile.profile_id)
    attack_pools = tuple(
        RangedAttackPool(
            attacker_model_instance_id=attacker_model_id,
            wargear_id=wargear_id,
            weapon_profile_id=bolt_profile.profile_id,
            weapon_profile=bolt_profile,
            target_unit_instance_id=target.unit_instance_id,
            shooting_type=ShootingType.NORMAL,
            attacks=1,
            target_visible_model_ids=target_model_ids,
            target_in_range_model_ids=target_model_ids,
        )
        for attacker_model_id in attacker_model_ids
    )
    return AttackSequence(
        sequence_id="phase17k-post-shoot-cover-denial-sequence",
        attacker_player_id=attacker_player_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=attack_pools,
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=tuple(range(len(attack_pools))),
        pool_index=len(attack_pools),
    )


def emit_successful_hit(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    successful: bool,
    pool_index: int = 0,
) -> None:
    decisions.event_log.append(
        "attack_sequence_step",
        AttackSequenceEvent(
            step=AttackSequenceStep.HIT,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{pool_index + 1:03d}:attack-001"
            ),
            pool_index=pool_index,
            attack_index=0,
            payload={"successful": successful},
        ).to_payload(),
    )


def emit_wound_result(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    successful: bool,
    pool_index: int = 0,
) -> None:
    decisions.event_log.append(
        "attack_sequence_step",
        AttackSequenceEvent(
            step=AttackSequenceStep.WOUND,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{pool_index + 1:03d}:attack-001"
            ),
            pool_index=pool_index,
            attack_index=0,
            payload={"successful": successful},
        ).to_payload(),
    )
