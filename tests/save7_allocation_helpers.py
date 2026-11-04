"""Effective-save contracts and real native profiles; no native army admission claim."""

from dataclasses import replace
from pathlib import Path
from typing import cast

from tests.daemons_native_source_helpers import BELAKOR, native_definitions
from tests.phase15c_fight_order_helpers import mission_setup
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.section03_fixtures import placement
from tests.support.section04_fixtures import (
    body,
    choose,
    combat_session,
    combat_state,
    declare_shooting,
    pending,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierStack, ModifierTerm
from warhammer40k_core.engine.damage_allocation import AllocationGroup, AllocationGroupRole
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose

BLOODLETTERS = "000001114"


def effective_value(kind: Characteristic, raw: int, delta: int) -> CharacteristicValue:
    """Explicit Core modifier control, not a newly admitted native granting rule."""
    modifier = ModifierTerm(ModifierOperation.ADD, delta).bind(
        modifier_id=f"save7:contract:{kind.value}:{delta}",
        source_id="save7:constructed-characteristic-control",
        characteristic=kind,
    )
    return ModifierStack(kind, raw, (modifier,)).resolve()


def modified_model(model: ModelInstance, kind: Characteristic, delta: int) -> ModelInstance:
    value = effective_value(kind, model.characteristic(kind).final, delta)
    return replace(
        model,
        characteristics=tuple(
            value if item.characteristic is kind else item for item in model.characteristics
        ),
    )


def allocation_group(save: int | None = 7, invulnerable: int | None = 5) -> AllocationGroup:
    return AllocationGroup(
        group_id="save7:group",
        target_unit_instance_id="save7:target",
        model_ids=("save7:model",),
        role=AllocationGroupRole.NON_CHARACTER,
        wounds=1,
        save=save,
        invulnerable_save=invulnerable,
    )


def native_target(index: Path | None, datasheet: str = BLOODLETTERS) -> UnitInstance:
    definitions = native_definitions(index)
    return definitions.unit(
        datasheet,
        identity="target",
        army_id="enemy",
        composition=tuple(
            ModelProfileSelection(part.model_profile_id, part.max_models)
            for part in definitions.package.army_catalog.datasheet_by_id(datasheet).composition
        ),
    )


def native_attack_session(
    index: Path | None,
    phase: BattlePhase,
    *,
    target_sheet: str = BLOODLETTERS,
) -> tuple[LocalGameSession, UnitInstance]:
    """Canonical terrain-free facade checkpoint with native units/runtime content.

    The selected native catalog has no admitted detachments. This exercises live
    declaration/dispatch, not native army muster or full lifecycle restoration.
    """
    definitions = native_definitions(index)
    target = native_target(index, target_sheet)
    attacker = definitions.unit(BELAKOR)
    state = combat_state(
        definitions,
        attacker,
        target=target,
        phase=phase,
        distance=3.2 if phase is BattlePhase.FIGHT else 8,
    )
    state.game_id = f"save7-native:{phase.value}:{target_sheet}"
    native_mission = mission_setup()
    owners = {"player-a": "owner", "player-b": "opponent"}
    native_mission = replace(
        native_mission,
        attacker_player_id="owner",
        defender_player_id="opponent",
        primary_mission_assignments=tuple(
            replace(item, player_id=owners[item.player_id])
            for item in native_mission.primary_mission_assignments
        ),
    )
    # Compact native bases in two columns, outside the attacker's physical base.
    diameter = (
        definitions.package.army_catalog.datasheet_by_id(target_sheet)
        .model_profiles[0]
        .base_size.diameter_mm
    )
    assert diameter is not None
    spacing = diameter / 25.4 + 0.05
    x = 13.2 if phase is BattlePhase.FIGHT else 18.0
    poses = tuple(
        Pose.at(x + spacing * (i % 2), 10 + spacing * (i // 2))
        for i in range(len(target.own_models))
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(army, unit_placements=(placement(target, poses, enemy=True),))
                if army.player_id == "opponent"
                else army
                for army in state.battlefield_state.placed_armies
            ),
        )
    )
    for owner in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=owner,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    session = combat_session(definitions, state, native_mission)
    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    if phase is BattlePhase.SHOOTING:
        request = shooting_request(session, attacker.unit_instance_id)
    else:
        for _ in range(12):
            request = pending(session)
            if request.decision_type == "submit_melee_declaration":
                break
            if request.decision_type == "select_fight_activation":
                choose(
                    session,
                    request,
                    next(
                        option.option_id
                        for option in request.options
                        if attacker.unit_instance_id in option.option_id
                    ),
                )
            else:
                submit_fixture_request(session, request)
        else:
            raise AssertionError("Native melee declaration was not reached")
    profile = BELAKOR + (
        ":the-blade-of-shadows:strike"
        if phase is BattlePhase.FIGHT
        else ":betraying-shades:witchfire"
    )
    row = next(item for item in weapon_rows(request) if item["weapon_profile_id"] == profile)
    if phase is BattlePhase.SHOOTING:
        declare_shooting(session, request, [row], [target.unit_instance_id])
    else:
        proposal = cast(dict[str, JsonValue], body(request)["proposal_request"])
        payload: dict[str, JsonValue] = {
            key: proposal[key]
            for key in (
                "battle_round",
                "unit_instance_id",
                "source_decision_request_id",
                "source_decision_result_id",
            )
        }
        payload.update(
            player_id=request.actor_id,
            proposal_kind="melee_declaration",
            proposal_request_id=request.request_id,
            declarations=[
                {
                    "attacker_model_instance_id": row["model_instance_id"],
                    "weapon_instance_id": row["weapon_instance_id"],
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "selected_weapon_ability_ids": [],
                    "target_allocations": [{"target_unit_instance_id": target.unit_instance_id}],
                }
            ],
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=request.request_id + ":save7-native",
            payload=validate_json_value(payload),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    return session, target


def effective_save_session() -> LocalGameSession:
    """Admitted canonical fixture, with a predeclared Core modifier control.

    Its source armour3 becomes effective7 through ModifierStack before mustering.
    The small Torrent/S20/A3 contract ensures a real save/damage interruption;
    these are constructed test inputs, not native Bloodletters or granting rules.
    """
    from tests.phase13b_shooting_declaration_helpers import (
        _canonical_catalog,
        _compact_shooting_lifecycle,
    )
    from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword

    catalog = _canonical_catalog()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            effective_value(Characteristic.SAVE, value.final, 7 - value.final)
                            if value.characteristic is Characteristic.SAVE
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                weapon,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(3),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        damage_profile=DamageProfile.fixed(1),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, 0
                        ),
                        keywords=(WeaponKeyword.TORRENT,),
                        abilities=(),
                    )
                    for profile in weapon.weapon_profiles
                ),
            )
            for weapon in catalog.wargear
        ),
    )
    lifecycle, _units = _compact_shooting_lifecycle(
        catalog=catalog,
        enemy_model_count=2,
        game_id="save7-admitted-session",
    )
    # Match existing admitted-session helpers: hydrate runtime content/audit at
    # the initial checkpoint before any tested decision is emitted.
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(80):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_damage_allocation_model":
            return session
        submit_fixture_request(session, request)
    raise AssertionError("Effective7 session did not reach a real damage allocation choice")
