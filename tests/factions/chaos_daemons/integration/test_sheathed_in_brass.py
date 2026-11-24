"""Blood Legion's retained July faction-pack rule on the native Shooting path."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.daemons_native_source_helpers import BELAKOR, native_definitions
from tests.generic_modifier_helpers import generic_effect
from tests.order93_save_damage_helpers import reach_save_damage_request
from tests.phase13b_shooting_declaration_helpers import _benefit_of_cover_result
from tests.save7_allocation_helpers import BLOODLETTERS
from tests.support.faction_batch01 import Scene, anchor, events, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    body,
    choose,
    declare_shooting,
    pending,
    shooting_request,
    weapon_rows,
)
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import CoverEffect
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.native_attack_gathering import (
    _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveOption,
    SaveOptionPayload,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

STRATAGEM_ID = "000009816007"
SOURCE_ID = f"gw-11e-faction-packs-2026-07:stratagem:chaos-daemons:blood-legion:{STRATAGEM_ID}"
BLOODCRUSHERS = "000001115"
INFRACTORS = "000004080"
LORD = "000004078"
DETACHMENTS = {
    "chaos-daemons": "blood-legion",
    "emperors-children": "court-of-the-phoenician",
}
TARGET = "own:armoured"
OTHER = "own:also-targeted"
UNTARGETED = "own:untargeted"
WRONG_KEYWORD = "own:undivided"
FIRST_SHOOTER = "foe:infractors"
LATER_SHOOTER = "foe:lord"
SPARE_SHOOTER = "foe:spare"


@pytest.fixture(scope="module")
def brass_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    source = native_definitions(selected_army_source_index)
    catalog = source.package.army_catalog
    faction_ids = {"CD": "chaos-daemons", "EC": "emperors-children"}
    factions = tuple(
        replace(faction, faction_id=faction_ids[faction.faction_id]) for faction in catalog.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=faction.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(
                sheet.datasheet_id
                for sheet in catalog.datasheets
                if set(sheet.keywords.faction_keywords).intersection(faction.faction_keywords)
            ),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        for faction in factions
        for row in identities.detachment_rows()
        if row.detachment_id == DETACHMENTS[faction.faction_id]
    )
    return Section02Definitions(
        replace(
            source.package,
            army_catalog=replace(catalog, factions=factions, detachments=detachments),
        ),
        source.preparation_seconds,
    )


def _scene(
    definitions: Section02Definitions,
    *,
    cp: int,
    initial_effects: tuple[PersistingEffect, ...] = (),
) -> Scene:
    s = scene(
        definitions,
        (
            selection(definitions, BLOODLETTERS, "armoured"),
            selection(definitions, BLOODCRUSHERS, "also-targeted"),
            selection(definitions, BLOODCRUSHERS, "untargeted"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        (
            selection(definitions, INFRACTORS, "infractors"),
            selection(definitions, LORD, "lord"),
            selection(definitions, LORD, "spare"),
        ),
        phase=BattlePhase.SHOOTING,
        active="opponent",
        detachment_id_by_faction=DETACHMENTS,
        seed="sheathed-in-brass",
        rng_seed_label="sheathed-in-brass:seed-1",
    )
    # Separate the target units into lanes with no overlapping bases.
    for unit_id, x, y, spacing in (
        (TARGET, 18.0, 9.0, 1.4),
        (OTHER, 10.0, 24.0, 4.0),
        (UNTARGETED, 45.0, 18.0, 4.0),
        (WRONG_KEYWORD, 3.0, 12.0, 4.0),
        (FIRST_SHOOTER, 10.0, 10.0, 2.0),
        (LATER_SHOOTER, 16.0, 24.0, 2.0),
        (SPARE_SHOOTER, 10.0, 3.0, 2.0),
    ):
        count = len(s.units[unit_id].own_models)
        columns = 2 if unit_id == TARGET else 1
        locate(
            s,
            unit_id,
            tuple(
                Pose.at(x + spacing * (i % columns), y + spacing * (i // columns))
                for i in range(count)
            ),
        )
    if cp:
        s.state.gain_command_points(
            player_id="owner",
            amount=cp,
            source_id="brass:cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    # The modifier decision verifier replays from the initial Shooting state.
    for effect in initial_effects:
        s.state.record_persisting_effect(effect)
    anchor(s)
    start = begin(s.session)
    if start.decision_type == "start_mission_action":
        choose(s.session, start, "continue_to_shooting")
    return s


def _brass_options(request: DecisionRequest) -> dict[str, DecisionOption]:
    options = {}
    for option in request.options:
        if not option.option_id.startswith(f"use-stratagem:{STRATAGEM_ID}:"):
            continue
        binding = cast(
            dict[str, JsonValue], cast(dict[str, JsonValue], option.payload)["target_binding"]
        )
        target_id = binding["target_unit_instance_id"]
        assert isinstance(target_id, str)
        options[target_id] = option
    return options


def _first_shot(s: Scene) -> None:
    declaration = shooting_request(s.session, FIRST_SHOOTER)
    rows = [
        row for row in weapon_rows(declaration) if row["wargear_id"] == f"{INFRACTORS}:bolt-pistol"
    ]
    assert len(rows) >= 5
    declare_shooting(
        s.session, declaration, rows[:5], [WRONG_KEYWORD, TARGET, TARGET, TARGET, OTHER]
    )


def _finish_shooter(session: LocalGameSession) -> None:
    for _ in range(40):
        req = pending(session)
        if req.decision_type == "select_shooting_unit":
            return
        assert req.decision_type != "submit_shooting_declaration"
        assert not _brass_options(req)
        default = next(
            (
                option.option_id
                for option in req.options
                if option.option_id
                in {DECLINE_STRATAGEM_WINDOW_OPTION_ID, "decline", "keep", "keep_all_modifiers"}
            ),
            req.options[0].option_id,
        )
        choose(session, req, default)
    raise AssertionError("The native shooter did not finish")


def _save_payloads(session: LocalGameSession, unit_id: str) -> list[dict[str, JsonValue]]:
    payloads = []
    for record in events(session, "attack_sequence_step"):
        if record["step"] != "save":
            continue
        payload = cast(dict[str, JsonValue], record["payload"])
        if str(payload["allocated_model_id"]).startswith(unit_id + ":"):
            payloads.append(payload)
    assert payloads, unit_id
    return payloads


def _assert_save_options(
    payloads: list[dict[str, JsonValue]],
    *,
    armour: int,
    target: int,
    invulnerable: int,
) -> None:
    for payload in payloads:
        options = tuple(
            SaveOption.from_payload(item)
            for item in cast(list[SaveOptionPayload], payload["save_options"])
        )
        normal, special = options
        assert (normal.save_kind, normal.characteristic_target_number, normal.target_number) == (
            SaveKind.ARMOUR,
            armour,
            target,
        )
        assert (special.save_kind, special.target_number) == (SaveKind.INVULNERABLE, invulnerable)
        assert any(source.startswith(SOURCE_ID) for source in normal.source_rule_ids) is (
            armour == 3
        )
        assert all(not source.startswith(SOURCE_ID) for source in special.source_rule_ids)


def _assert_cover_policy(s: Scene) -> None:
    attacker = s.units[FIRST_SHOOTER]
    defender = s.units[TARGET]
    model = defender.own_models[0]
    profile = next(
        weapon.weapon_profile
        for weapon in equipped_weapon_profile_instances_for_model(
            model=attacker.own_models[0],
            army_catalog=s.session.lifecycle.config.army_catalog,
        )
        if weapon.wargear_id == f"{INFRACTORS}:bolt-pistol"
    )
    active_cover = _benefit_of_cover_result()
    assert (
        s.state.runtime_ruleset_descriptor().terrain_visibility_policy.cover_effect
        is (active_cover.cover_effect)
        is CoverEffect.ATTACKER_BS_MODIFIER
    )
    alternate = replace(active_cover, cover_effect=CoverEffect.SAVE_BONUS)
    for cover, ap, old_target, new_target, applied in (
        (active_cover, 0, 7, 3, False),
        (alternate, 0, 6, 3, False),
        (alternate, -1, 7, 3, True),
        (active_cover, -3, 10, 6, False),
    ):
        base = save_options_for_model(model=model, armor_penetration=ap, cover_result=cover)
        assert base[0].target_number == old_target
        changed = RuntimeModifierRegistry.empty().modified_save_options(
            SaveOptionModifierContext(
                state=s.state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                allocated_model_instance_id=model.model_instance_id,
                weapon_profile=profile,
                save_options=base,
            )
        )
        normal, special = changed
        assert (
            normal.characteristic_target_number,
            normal.target_number,
            normal.cover_applied,
        ) == (
            3,
            new_target,
            applied,
        )
        assert special == base[1]
        roll = DiceRollManager("brass:cover").roll_fixed(
            saving_throw_roll_spec(
                save_kind=SaveKind.INVULNERABLE,
                player_id="owner",
                allocated_model_id=model.model_instance_id,
                attack_context_id="brass:cover",
            ),
            (5 if ap == -3 else 3,),
        )
        save = resolve_saving_throw(roll_state=roll, options=changed)
        assert save.successful
        assert save.save_kind is (SaveKind.INVULNERABLE if ap == -3 else SaveKind.ARMOUR)


@pytest.mark.integration
@pytest.mark.replay
def test_sheathed_in_brass_native_accept_later_shooting_expiry_and_replay(
    brass_definitions: Section02Definitions,
) -> None:
    s = _scene(brass_definitions, cp=2)
    _first_shot(s)
    req = pending(s.session)
    assert req.decision_type == "use_stratagem"
    assert req.actor_id == "owner"
    assert set(_brass_options(req)) == {TARGET, OTHER}
    assert events(s.session, "attack_sequence_step") == []
    before = s.session.lifecycle.to_payload()
    good_option = _brass_options(req)[TARGET]
    with pytest.raises(DecisionError, match="not in the finite action space"):
        s.session.submit_option(
            request_id=req.request_id,
            result_id="brass:invalid",
            option_id=good_option.option_id.replace(TARGET, UNTARGETED),
        )
    assert s.session.lifecycle.to_payload() == before
    assert pending(s.session) == req

    choose(s.session, req, good_option.option_id)
    assert s.state.command_point_total("owner") == 1
    (use,) = [use for use in s.state.stratagem_use_records if use.stratagem_id == STRATAGEM_ID]
    assert use.targeted_unit_instance_ids == (TARGET,)
    assert use.source_id == SOURCE_ID
    (effect,) = [
        effect for effect in s.state.persisting_effects if effect.source_rule_id == SOURCE_ID
    ]
    assert effect.target_unit_instance_ids == (TARGET,)
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1,
        phase=BattlePhase.SHOOTING,
        player_id="opponent",
    )
    _assert_cover_policy(s)
    _finish_shooter(s.session)
    first = _save_payloads(s.session, TARGET)
    _assert_save_options(first, armour=3, target=4, invulnerable=5)

    declaration = shooting_request(s.session, LATER_SHOOTER)
    (high_ap,) = [
        row
        for row in weapon_rows(declaration)
        if str(row["weapon_profile_id"]).endswith(":supercharge")
    ]
    declare_shooting(s.session, declaration, [high_ap], [TARGET])
    _finish_shooter(s.session)
    later = _save_payloads(s.session, TARGET)[len(first) :]
    assert later
    _assert_save_options(later, armour=3, target=6, invulnerable=5)
    assert s.state.command_point_total("owner") == 1
    assert s.state.persisting_effects_for_unit(TARGET) == (effect,)
    finish = pending(s.session)
    choose(s.session, finish, "complete_shooting_phase")
    assert s.state.current_battle_phase is not BattlePhase.SHOOTING
    assert effect not in s.state.persisting_effects
    replay = ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="brass")).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
@pytest.mark.parametrize("cp", [0, 2], ids=["unaffordable", "decline"])
def test_sheathed_in_brass_native_decline_or_unaffordable(
    brass_definitions: Section02Definitions,
    cp: int,
) -> None:
    s = _scene(brass_definitions, cp=cp)
    _first_shot(s)
    req = pending(s.session)
    if cp:
        assert set(_brass_options(req)) == {TARGET, OTHER}
        choose(s.session, req, DECLINE_STRATAGEM_WINDOW_OPTION_ID)
    else:
        assert not _brass_options(req)
    _finish_shooter(s.session)
    _assert_save_options(_save_payloads(s.session, TARGET), armour=7, target=8, invulnerable=5)
    assert s.state.command_point_total("owner") == cp
    assert not any(use.stratagem_id == STRATAGEM_ID for use in s.state.stratagem_use_records)
    assert not any(effect.source_rule_id == SOURCE_ID for effect in s.state.persisting_effects)


@pytest.mark.integration
@pytest.mark.parametrize("use_brass", [False, True], ids=["fight-only", "sheathed-ignore"])
def test_sheathed_in_brass_native_gathering_and_save_ignore(
    brass_definitions: Section02Definitions,
    use_brass: bool,
) -> None:
    expiry = EffectExpiration.end_phase(
        battle_round=1, phase=BattlePhase.SHOOTING, player_id="opponent"
    )
    unrelated = generic_effect(
        effect_id="brass-control:fight-armour",
        owner_player_id="owner",
        target_unit_instance_ids=(TARGET,),
        target_kind="this_unit",
        effect_kind="set_characteristic",
        parameters={
            "characteristic": "save",
            "value": 2,
            "source_phase": "fight",
            "weapon_scope": "melee",
        },
    )
    permission = generic_effect(
        effect_id="brass-control:defender-ignore",
        owner_player_id="owner",
        target_unit_instance_ids=(TARGET,),
        target_kind="this_unit",
        effect_kind="grant_ability",
        parameters={
            "ability": "modifier_ignore_permission",
            "selection": "any_or_all",
            "modifier_kinds": [
                "save_characteristic",
                "invulnerable_save_characteristic",
            ],
            "attack_role": "target",
            "source_phase": "shooting",
        },
    )
    s = _scene(
        brass_definitions,
        cp=2,
        initial_effects=(
            replace(unrelated, expiration=expiry),
            replace(permission, expiration=expiry),
        ),
    )
    _first_shot(s)
    req = pending(s.session)
    choose(
        s.session,
        req,
        _brass_options(req)[TARGET].option_id if use_brass else DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    )
    if use_brass:
        request = reach_save_damage_request(s.session, kind="save_characteristic")
        assert request.actor_id == "owner"
        shooting = s.state.shooting_phase_state
        assert shooting is not None
        sequence = shooting.attack_sequence
        assert sequence is not None
        group = sequence.current_gathered_group
        assert group is not None
        assert group.target_unit_instance_id == TARGET
        assert len(group.native_snapshots) > 1
        assert len({snapshot.rules_json for snapshot in group.native_snapshots}) == 1
        bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
        rules, proof = _current_applicable_rules(
            state=s.state,
            registry=bundle.runtime_modifier_registry,
            sequence=sequence,
            pool=sequence.attack_pools[group.native_snapshots[0].pool_index],
            target_has_character=False,
        )
        templates = cast(list[dict[str, JsonValue]], rules["target_model_ignore_source_templates"])
        assert {template["kind"] for template in templates} == {"save_characteristic"}
        assert {template["effect_id"] for template in templates} == {permission.effect_id}
        assert unrelated.source_rule_id not in json.dumps(proof["generic_applicable_sources"])
        (modifier,) = cast(list[dict[str, JsonValue]], body(request)["modifiers"])
        operation = cast(dict[str, JsonValue], modifier["operation"])
        assert (operation["operation"], operation["operand"]) == ("set", 3)
        assert SOURCE_ID in json.dumps(modifier)
        choose(s.session, request, "ignore-remaining")
        _finish_shooter(s.session)
        first_save = _save_payloads(s.session, TARGET)[0]
        normal, special = tuple(
            SaveOption.from_payload(item)
            for item in cast(list[SaveOptionPayload], first_save["save_options"])
        )
        assert (normal.characteristic_target_number, normal.target_number) == (7, 8)
        assert (special.save_kind, special.target_number) == (SaveKind.INVULNERABLE, 5)
    else:
        _finish_shooter(s.session)
        _assert_save_options(_save_payloads(s.session, TARGET), armour=7, target=8, invulnerable=5)
