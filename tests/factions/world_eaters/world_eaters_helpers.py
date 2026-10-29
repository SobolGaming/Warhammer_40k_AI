from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    default_unit_selection,
)
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceRollResult, DiceRollSpec
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

WORLD_EATERS_DATASHEET_ID = "phase17g-world-eaters-berzerkers"

WORLD_EATERS_UNIT_ID = "army-alpha:berzerkers"

ENEMY_UNIT_ID = "army-beta:enemy-unit"

ICON_OF_KHORNE_WARGEAR_ID = "icon-of-khorne"

ICON_OF_KHORNE_OPTION_ID = "world-eaters-icon-of-khorne"


def _world_eaters_config() -> GameConfig:
    catalog = _world_eaters_catalog()
    return GameConfig(
        game_id="phase17g-world-eaters-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-world-eaters-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                    detachment_ids=("berzerker-warband",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="berzerkers",
                        datasheet_id=WORLD_EATERS_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                        wargear_selections=(
                            WargearSelection(
                                option_id=ICON_OF_KHORNE_OPTION_ID,
                                model_profile_id="core-intercessor-like",
                                wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
                            ),
                        ),
                    ),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(default_unit_selection("enemy-unit"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _world_eaters_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, _world_eaters_datasheet(base_datasheet)),
        wargear=(
            *base_catalog.wargear,
            Wargear(
                wargear_id=ICON_OF_KHORNE_WARGEAR_ID,
                name="Icon of Khorne",
                source_ids=(army_rule.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                name="World Eaters",
                faction_keywords=("WORLD EATERS",),
                source_ids=("gw-11e-world-eaters-faction-pack-2026-06:faction:world-eaters",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="berzerker-warband",
                detachment_id="berzerker-warband",
                name="Berzerker Warband",
                faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(WORLD_EATERS_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-world-eaters-faction-pack-2026-06:detachment:berzerker-warband",
                ),
            ),
        ),
    )


def _world_eaters_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=WORLD_EATERS_DATASHEET_ID,
        name="Khorne Berzerkers",
        keywords=DatasheetKeywordSet(
            keywords=("INFANTRY", "BATTLELINE"),
            faction_keywords=("WORLD EATERS",),
        ),
        wargear_options=(
            *base_datasheet.wargear_options,
            DatasheetWargearOption(
                option_id=ICON_OF_KHORNE_OPTION_ID,
                model_profile_id="core-intercessor-like",
                default_wargear_ids=(),
                allowed_wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
                max_selections=1,
                source_ids=(army_rule.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,),
                effects=(
                    DatasheetWargearOptionEffect(
                        kind=WargearOptionEffectKind.ADD_WARGEAR,
                        wargear_id=ICON_OF_KHORNE_WARGEAR_ID,
                        model_count=1,
                        wargear_count=1,
                    ),
                ),
            ),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:world-eaters:khorne-berzerkers",),
    )


def _battle_ready_lifecycle() -> GameLifecycle:
    config = _world_eaters_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                with_unit_keywords(
                    unit, keywords=tuple(keyword.upper() for keyword in unit.keywords)
                )
                for unit in army.units
            ),
        )
        if army.player_id == "player-b"
        else army
        for army in state.army_definitions
    ]
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-world-eaters-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    complete_setup_through_gate(
        state=state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _battle_ready_state() -> GameState:
    return _require_state(_battle_ready_lifecycle())


def _record_total_carnage_selection(*, state: GameState, decisions: DecisionController) -> None:
    options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=state.battle_round,
        dice_values=(3, 3, 1, 1, 1, 1, 1, 1),
        bloodshed_points=0,
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    result = DecisionResult.for_request(
        result_id="phase17g-total-carnage-result",
        request=request,
        selected_option_id="world_eaters:blessings:total_carnage",
    )
    handled = army_rule.apply_blessings_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    if not handled:
        raise AssertionError("Total Carnage selection must be handled")


def _advance_to_player_b_fight(state: GameState, *, battle_round: int) -> None:
    for _attempt in range(20):
        if (
            state.battle_round == battle_round
            and state.active_player_id == "player-b"
            and state.current_battle_phase is BattlePhase.FIGHT
        ):
            return
        state.advance_to_next_battle_phase()
    raise AssertionError(f"state did not reach round {battle_round} player-b Fight phase")


def _cloned_battle_ready_state() -> GameState:
    return GameState.from_payload(_battle_ready_state().to_payload())


def _dummy_battle_round_request(state: GameState) -> DecisionRequest:
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": "phase17g-test:dummy-battle-round-hook"}),
        options=(
            DecisionOption(
                option_id="phase17g-battle-round-hooks-option",
                label="Dummy Battle Round Hook",
                payload=validate_json_value({"selected": True}),
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _record_active_blessings(
    state: GameState,
    *,
    blessings: tuple[army_rule.BlessingOfKhorne, ...],
    unit_instance_id: str = WORLD_EATERS_UNIT_ID,
    player_id: str = "player-a",
) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{army_rule.HOOK_ID}:{player_id}:round-01:test-active-blessings",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id=player_id,
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=validate_json_value(
                {
                    "effect_kind": army_rule.BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "player_id": player_id,
                    "faction_id": army_rule.WORLD_EATERS_FACTION_ID,
                    "source_rule_id": army_rule.SOURCE_RULE_ID,
                    "hook_id": army_rule.HOOK_ID,
                    "selected_blessing_ids": [blessing.value for blessing in blessings],
                    "selected_blessing_labels": _blessing_labels(blessings),
                    "selected_option_id": "phase17g-test",
                    "request_id": "phase17g-test-request",
                    "result_id": "phase17g-test-result",
                    "dice_values": [6, 6, 5, 5, 4, 4, 3, 3],
                    "consumed_dice_by_blessing_id": {},
                    "bloodshed_points_spent": 0,
                    "rules_update_sources": [army_rule.UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE],
                }
            ),
        )
    )


def _world_eaters_state_for_melee_fixture(
    *,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
    attacker: UnitInstance,
) -> GameState:
    world_eaters_attacker = with_unit_keywords(
        attacker, faction_keywords=(army_rule.WORLD_EATERS_FACTION_KEYWORD,)
    )
    armies = (
        replace(scenario.armies[0], units=(world_eaters_attacker,)),
        scenario.armies[1],
    )
    return GameState(
        game_id="phase17g-world-eaters-melee-state",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.FIGHT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(armies),
        battlefield_state=scenario.battlefield_state,
    )


def _melee_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-world-eaters-chainblade",
        name="Chainblade",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
    )


def _destroy_enemy_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    attacking_unit_id: str,
) -> None:
    enemy = _unit_by_id(state, ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy.own_models)
    _remove_models(state, destroyed_model_ids)
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        _append_model_destroyed_event(
            state=state,
            decisions=decisions,
            destroying_player_id="player-a",
            attacking_unit_id=attacking_unit_id,
            target_unit_id=ENEMY_UNIT_ID,
            model_instance_id=model_id,
            event_suffix=f"enemy-{index:02d}",
        )


def _append_model_destroyed_event(
    *,
    state: GameState,
    decisions: DecisionController,
    destroying_player_id: str,
    attacking_unit_id: str,
    target_unit_id: str,
    model_instance_id: str,
    event_suffix: str,
) -> None:
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires battle phase")
    attacking_unit = _unit_by_id(state, attacking_unit_id)
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": phase.value,
            **ModelDestructionAttribution.for_attack(
                destroying_player_id=destroying_player_id,
                attacking_unit_instance_id=attacking_unit_id,
                attacking_model_instance_id=(attacking_unit.own_models[0].model_instance_id),
                weapon_profile=_melee_profile(),
                attack_context_id=f"attack-context:{event_suffix}",
            ).to_payload(),
            "target_unit_instance_id": target_unit_id,
            "model_instance_id": model_instance_id,
            "damage_kind": "normal",
            "damage_event_id": f"phase17g-world-eaters-damage-{event_suffix}",
            "destroyed_model_rules_triggered": True,
        },
    )


def _remove_models(state: GameState, model_instance_ids: tuple[str, ...]) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield")
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(model_instance_ids))


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _battlefield_with_unit_origins(
    state: GameState,
    *,
    world_eaters_origin: Pose,
    enemy_origin: Pose,
) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield")
    battlefield = state.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            unit=_unit_by_id(state, WORLD_EATERS_UNIT_ID),
            player_id="player-a",
            origin=world_eaters_origin,
        )
    )
    return battlefield.with_unit_placement(
        _unit_placement_at(
            unit=_unit_by_id(state, ENEMY_UNIT_ID),
            player_id="player-b",
            origin=enemy_origin,
        )
    )


def _unit_placement_at(
    *,
    unit: UnitInstance,
    player_id: str,
    origin: Pose,
) -> UnitPlacement:
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(
                unit.own_models,
                _compact_unit_poses(origin=origin, model_count=len(unit.own_models)),
                strict=True,
            )
        ),
    )


def _compact_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _attack_pool_for_world_eaters_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    attacks: int,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_instance_id=f"weapon-instance:test:{weapon_profile.profile_id}",
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=attacks,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _fixed_roll_result(
    *,
    roll_id: str,
    spec: DiceRollSpec,
    value: int,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )


def _charge_roll_result_from_event(
    decisions: DecisionController,
    event_type: str,
) -> ChargeRollResult:
    for event in reversed(decisions.event_log.records):
        if event.event_type != event_type:
            continue
        payload = cast(dict[str, object], event.payload)
        return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))
    raise AssertionError(f"missing event type {event_type}")


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _icon_bearer_model_id(state: GameState) -> str:
    unit = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    for model in unit.own_models:
        if ICON_OF_KHORNE_WARGEAR_ID in model.wargear_ids:
            return model.model_instance_id
    raise AssertionError("test unit requires Icon of Khorne bearer")


def _blessing_labels(
    blessings: tuple[army_rule.BlessingOfKhorne, ...],
) -> list[str]:
    return [
        blessing.value.replace("_", " ").title().replace("Fuelled", "fuelled")
        for blessing in blessings
    ]


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _require_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    return state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


__all__ = (
    "_advance_to_player_b_fight",
    "_append_model_destroyed_event",
    "_attack_pool_for_world_eaters_test",
    "_battle_ready_lifecycle",
    "_battle_ready_state",
    "_battlefield_with_unit_origins",
    "_blessing_labels",
    "_charge_roll_result_from_event",
    "_cloned_battle_ready_state",
    "_compact_unit_poses",
    "_destroy_enemy_unit",
    "_dummy_battle_round_request",
    "_event_payloads",
    "_fixed_roll_result",
    "_fixed_secondary_choice",
    "_icon_bearer_model_id",
    "_melee_profile",
    "_mission_setup",
    "_mustered_armies",
    "_record_active_blessings",
    "_record_total_carnage_selection",
    "_remove_models",
    "_require_state",
    "_runtime_content_bundle",
    "_state_at_phase",
    "_unit_by_id",
    "_unit_placement_at",
    "_world_eaters_catalog",
    "_world_eaters_config",
    "_world_eaters_datasheet",
    "_world_eaters_state_for_melee_fixture",
)
