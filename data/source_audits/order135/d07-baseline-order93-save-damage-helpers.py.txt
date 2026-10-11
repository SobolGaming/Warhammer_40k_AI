"""Real shooting session with distinct source operations for save and Damage choices."""

from __future__ import annotations

from dataclasses import replace

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle


def save_damage_session(
    *,
    random_damage: bool = False,
    model_scoped_save: bool = False,
    modified_ap: bool = False,
    damage_zero_replacement: bool = False,
) -> LocalGameSession:
    catalog = _canonical_catalog()
    if damage_zero_replacement:
        from typing import cast

        from warhammer40k_core.core.datasheet import (
            CatalogAbilitySourceKind,
            CatalogAbilitySupport,
            CatalogJsonObject,
        )
        from warhammer40k_core.core.datasheet_ability import DatasheetAbilityDescriptor
        from warhammer40k_core.rules.rule_ir import RuleIR
        from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
            faction_pack_rule_ir,
        )

        source_payload = faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id(
            "000002532:4"
        )
        assert source_payload is not None
        rule = RuleIR.from_payload(source_payload)
        descriptor = DatasheetAbilityDescriptor(
            ability_id="order93-source-damage-zero",
            name="Channeller Stones",
            source_id=rule.source_id,
            support=CatalogAbilitySupport.GENERIC_RULE_IR,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description=rule.normalized_text,
            rule_ir_payload=cast(CatalogJsonObject, source_payload),
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(datasheet, abilities=(*datasheet.abilities, descriptor))
                if datasheet.datasheet_id == "core-intercessor-like-infantry"
                else datasheet
                for datasheet in catalog.datasheets
            ),
        )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(4 if damage_zero_replacement else 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        damage_profile=DamageProfile.dice(DiceExpression(1, 3))
                        if random_damage
                        else DamageProfile.fixed(1),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        keywords=(WeaponKeyword.TORRENT,),
                        abilities=(),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=catalog,
        game_id="order93-save-damage",
        enemy_model_count=2,
    )
    state = lifecycle.state
    assert state is not None
    attacker, defender = units["intercessor-1"], units["enemy"]
    for owner, unit in (("player-a", attacker), ("player-b", defender)):
        state.record_persisting_effect(
            generic_effect(
                effect_id=f"save-damage:permission:{owner}",
                owner_player_id=owner,
                target_unit_instance_ids=(unit.unit_instance_id,),
                target_kind="this_model"
                if owner == "player-b" and model_scoped_save
                else "this_unit",
                source_model_instance_id=(
                    unit.own_models[0].model_instance_id
                    if owner == "player-b" and model_scoped_save
                    else None
                ),
                effect_kind="grant_ability",
                parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
            )
        )
    for identity, delta in (("bonus", 2), ("penalty", -2)):
        state.record_persisting_effect(
            generic_effect(
                effect_id=f"save:{identity}",
                owner_player_id="player-b",
                target_unit_instance_ids=(defender.unit_instance_id,),
                target_kind="this_unit",
                effect_kind="modify_dice_roll",
                parameters={"roll_type": "save", "delta": delta, "attack_role": "target"},
            )
        )
        state.record_persisting_effect(
            generic_effect(
                effect_id=f"damage:{identity}",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                target_kind="this_unit",
                effect_kind="modify_characteristic",
                parameters={"characteristic": "damage", "delta": delta},
            )
        )
        if modified_ap:
            state.record_persisting_effect(
                generic_effect(
                    effect_id=f"ap:{identity}",
                    owner_player_id="player-a",
                    target_unit_instance_ids=(attacker.unit_instance_id,),
                    target_kind="this_unit",
                    effect_kind="modify_characteristic",
                    parameters={"characteristic": "armor_penetration", "delta": delta},
                )
            )
        if random_damage:
            state.record_persisting_effect(
                generic_effect(
                    effect_id=f"damage-roll:{identity}",
                    owner_player_id="player-a",
                    target_unit_instance_ids=(attacker.unit_instance_id,),
                    target_kind="this_unit",
                    effect_kind="modify_dice_roll",
                    parameters={"roll_type": "damage", "delta": delta, "attack_role": "attacker"},
                )
            )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def reach_save_damage_request(
    session: LocalGameSession, *, kind: str = "save_roll", stage: str | None = None
) -> DecisionRequest:
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    for _ in range(80):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = request.payload
            assert isinstance(payload, dict)
            subject = payload["subject"]
            assert isinstance(subject, dict)
            source_context = payload["source_context"]
            assert isinstance(source_context, dict)
            if subject["kind"] == kind and (
                stage is None or source_context["evaluation_stage"] == stage
            ):
                return request
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:keep",
                option_id="keep-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
    raise AssertionError(f"Did not reach {kind} evaluation.")


def take_cover_rattlejoint_session() -> LocalGameSession:
    """Load the real Astra and Death Guard providers over canonical physical units."""
    from tests.phase13b_shooting_declaration_helpers import (
        _compact_intercessor_catalog,
        _shooting_lifecycle,
    )
    from warhammer40k_core.core.datasheet import DatasheetKeywordSet
    from warhammer40k_core.core.detachment import DetachmentDefinition
    from warhammer40k_core.core.faction import FactionDefinition
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.astra_militarum import (
        army_rule as astra,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
        army_rule as death_guard,
    )
    from warhammer40k_core.engine.faction_rule_states import FactionRuleState
    from warhammer40k_core.engine.phase import BattlePhase, SetupStep
    from warhammer40k_core.geometry.pose import Pose

    catalog = _compact_intercessor_catalog(_canonical_catalog())
    base_sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    factions = (
        (
            death_guard.DEATH_GUARD_FACTION_ID,
            "DEATH GUARD",
            "plague-company",
            "order93:plague-marine",
        ),
        (
            astra.ASTRA_MILITARUM_FACTION_ID,
            "ASTRA MILITARUM",
            "combined-regiment",
            "order93:guardsman",
        ),
    )
    catalog = replace(
        catalog,
        factions=(
            *catalog.factions,
            *(
                FactionDefinition(
                    faction_id=faction,
                    name=keyword,
                    faction_keywords=(keyword,),
                    source_ids=(f"source:{faction}",),
                )
                for faction, keyword, _detachment, _sheet in factions
            ),
        ),
        detachments=(
            *catalog.detachments,
            *(
                DetachmentDefinition(
                    canonical_detachment_id=detachment,
                    detachment_id=detachment,
                    name=detachment,
                    faction_id=faction,
                    detachment_point_cost=1,
                    unit_datasheet_ids=(sheet,),
                    force_disposition_ids=("take-and-hold", "purge-the-foe"),
                    source_ids=(f"source:{detachment}",),
                )
                for faction, _keyword, detachment, sheet in factions
            ),
        ),
        datasheets=(
            *catalog.datasheets,
            *(
                replace(
                    base_sheet,
                    datasheet_id=sheet,
                    keywords=DatasheetKeywordSet(
                        keywords=("INFANTRY", "REGIMENT"), faction_keywords=(keyword,)
                    ),
                    abilities=(),
                    source_ids=(f"source:{sheet}",),
                )
                for _faction, keyword, _detachment, sheet in factions
            ),
        ),
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, 0
                        ),
                        damage_profile=DamageProfile.fixed(1),
                        keywords=(WeaponKeyword.TORRENT,),
                        abilities=(),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in catalog.wargear
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        alpha_unit_specs=(("intercessor-1", "order93:plague-marine", "core-intercessor-like", 1),),
        enemy_datasheet=("order93:guardsman", "core-intercessor-like", 1),
        enemy_pose=Pose.at(14, 35),
        catalog=catalog,
        game_id="order93-take-cover-rattlejoint",
        alpha_faction_id=death_guard.DEATH_GUARD_FACTION_ID,
        alpha_detachment_ids=("plague-company",),
        enemy_faction_id=astra.ASTRA_MILITARUM_FACTION_ID,
        enemy_detachment_ids=("combined-regiment",),
    )
    state = lifecycle.state
    assert state is not None
    target = units["enemy"]
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"{death_guard.HOOK_ID}:player-a:plague-selection",
            player_id="player-a",
            faction_id=death_guard.DEATH_GUARD_FACTION_ID,
            source_rule_id=death_guard.SOURCE_RULE_ID,
            state_kind=death_guard.NURGLES_GIFT_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="order93:plague-request",
            result_id="order93:plague-result",
            payload={
                "plague_id": death_guard.NurglesGiftPlague.RATTLEJOINT_AGUE.value,
                "hook_id": death_guard.HOOK_ID,
            },
        )
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order93:take-cover",
            source_rule_id=astra.SOURCE_RULE_ID,
            owner_player_id="player-b",
            target_unit_instance_ids=(target.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.start_turn(battle_round=2, player_id="player-b"),
            effect_payload={
                "effect_kind": astra.VOICE_OF_COMMAND_EFFECT_KIND,
                "order_id": astra.VoiceOfCommandOrder.TAKE_COVER.value,
                "ordered_rules_unit_instance_id": target.unit_instance_id,
                "ordered_component_unit_instance_ids": [target.unit_instance_id],
                "source_rule_id": astra.SOURCE_RULE_ID,
                "hook_id": astra.HOOK_ID,
                "player_id": "player-b",
                "game_id": state.game_id,
                "battle_round": 1,
                "phase": "command",
            },
        )
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="order93:bounded-save-permission",
            owner_player_id="player-b",
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        )
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
