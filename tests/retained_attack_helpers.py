from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,  # pyright: ignore[reportPrivateUsage]
    _compact_intercessor_catalog,  # pyright: ignore[reportPrivateUsage]
    _compact_shooting_lifecycle,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.detachment import StratagemDefinition as CatalogStratagemDefinition
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    retained_attack_sources_2026_09 as retained_sources,
)


def for_the_chapter_catalog(*, hazardous: bool = False) -> ArmyCatalog:
    catalog = lethal_retained_attack_catalog()
    if hazardous:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    wargear,
                    weapon_profiles=tuple(
                        replace(profile, keywords=(*profile.keywords, WeaponKeyword.HAZARDOUS))
                        for profile in wargear.weapon_profiles
                    ),
                )
                for wargear in catalog.wargear
            ),
        )
    rule_ir = retained_sources.rule_ir_for_source(retained_sources.FOR_THE_CHAPTER_SOURCE_ID)
    ability = DatasheetAbilityDescriptor(
        ability_id=rule_ir.source_id,
        name="For the Chapter!",
        source_id=rule_ir.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=rule_ir.normalized_text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )
    return replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, ability)) for sheet in catalog.datasheets
        ),
    )


def unending_fidelity_catalog() -> ArmyCatalog:
    catalog = _compact_intercessor_catalog(lethal_retained_attack_catalog())
    profile = retained_sources.stratagem_profile()
    detachment = replace(
        catalog.detachments[0],
        detachment_id=profile.detachment_id,
        name="Hallowed Conclave rule consumer fixture",
        stratagem_ids=(profile.stratagem_id,),
    )
    return replace(
        catalog,
        factions=tuple(
            replace(faction, faction_keywords=(*faction.faction_keywords, "GREY KNIGHTS"))
            for faction in catalog.factions
        ),
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    faction_keywords=(*sheet.keywords.faction_keywords, "GREY KNIGHTS"),
                ),
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=("core-leader-blade", "core-bolt-rifle"),
                        allowed_wargear_ids=("core-leader-blade", "core-bolt-rifle"),
                        min_selections=2,
                        max_selections=2,
                    )
                    for option in sheet.wargear_options
                )
                if sheet.datasheet_id == "core-character-leader"
                else sheet.wargear_options,
            )
            for sheet in catalog.datasheets
        ),
        detachments=(*catalog.detachments, detachment),
        stratagems=(
            *catalog.stratagems,
            CatalogStratagemDefinition(
                stratagem_id=profile.stratagem_id,
                name=profile.name,
                source_id=profile.source_id,
                command_point_cost=profile.command_point_cost,
            ),
        ),
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(weapon, keywords=(*weapon.keywords, WeaponKeyword.PISTOL))
                    for weapon in wargear.weapon_profiles
                ),
            )
            if wargear.wargear_id == "core-bolt-rifle"
            else wargear
            for wargear in catalog.wargear
        ),
    )


def lethal_retained_attack_catalog() -> ArmyCatalog:
    catalog = _canonical_catalog()
    return replace(
        catalog,
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        damage_profile=DamageProfile.fixed(100),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 100),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -10
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


def pending_retained_attack(
    *,
    deadly_demise: bool = False,
    cleanup_feel_no_pain: bool = False,
    collateral_retention: bool = False,
    trigger_threshold: int | None = None,
    parent_retention: bool = True,
    conditional_grant: bool = False,
    additional_grant: bool = False,
    counter_shooting: bool = False,
    stop_after_removal: bool = False,
    reaction_kind: DestructionReactionKind = DestructionReactionKind.FIGHT_ON_DEATH,
) -> tuple[LocalGameSession, str]:
    lifecycle, units = _compact_shooting_lifecycle(
        catalog=lethal_retained_attack_catalog(),
        game_id="order-30-presence",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_model_count=3,
    )
    state = lifecycle.state
    assert state is not None
    model_id = units["enemy"].own_models[0].model_instance_id
    if counter_shooting:
        state.record_model_destruction_reaction_sources(
            model_instance_id=units["intercessor-1"].own_models[0].model_instance_id,
            sources=(
                DestructionReactionSource(
                    source_id="order-30-counter-shooting",
                    source_rule_id="order-30-counter-shooting",
                    reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
                ),
            ),
        )
    if conditional_grant:
        state.record_persisting_effect(
            PersistingEffect(
                effect_id="order-30-grant-effect",
                source_rule_id="order-30-grant-rule",
                owner_player_id="player-b",
                target_unit_instance_ids=(units["enemy"].unit_instance_id,),
                started_battle_round=state.battle_round,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_phase(
                    battle_round=state.battle_round,
                    phase=BattlePhase.SHOOTING,
                    player_id="player-a",
                ),
                effect_payload={"effect_kind": "order-30-test-grant"},
            )
        )
    mandatory_sources = (
        (
            DestructionReactionSource(
                source_id="order-30-deadly-demise",
                source_rule_id="order-30-deadly-demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                optional=False,
                payload={
                    "trigger_roll_threshold": 1,
                    "range_inches": 25.0 if collateral_retention or cleanup_feel_no_pain else 6.0,
                    "mortal_wounds": {"kind": "fixed", "value": 100 if collateral_retention else 1},
                },
            ),
        )
        if deadly_demise
        else ()
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            *(
                (
                    DestructionReactionSource(
                        source_id="order-30-fight-on-death",
                        source_rule_id="order-30-fight-on-death",
                        reaction_kind=reaction_kind,
                        payload={
                            "requires_active_persisting_effect": {
                                "source_rule_id": "order-30-grant-rule",
                                "target_unit_instance_id": units["enemy"].unit_instance_id,
                            }
                        }
                        if conditional_grant
                        else None
                        if trigger_threshold is None
                        else {"trigger_roll_threshold": trigger_threshold},
                    ),
                )
                if parent_retention
                else ()
            ),
            *mandatory_sources,
            *(
                (
                    DestructionReactionSource(
                        source_id="order-30-alternate-grant",
                        source_rule_id="order-30-alternate-grant-rule",
                        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                    ),
                )
                if additional_grant
                else ()
            ),
        ),
    )
    if collateral_retention:
        state.record_model_destruction_reaction_sources(
            model_instance_id=units["intercessor-1"].own_models[0].model_instance_id,
            sources=(
                DestructionReactionSource(
                    source_id="order-30-collateral-fight-on-death",
                    source_rule_id="order-30-collateral-fight-on-death",
                    reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                ),
            ),
        )
    if cleanup_feel_no_pain:
        state.record_model_feel_no_pain_sources(
            model_instance_id=units["intercessor-1"].own_models[0].model_instance_id,
            decline_allowed=True,
            sources=(FeelNoPainSource(source_id="order-30-fnp", threshold=6),),
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(30):
        current = session.lifecycle.state
        assert current is not None
        assert current.battlefield_state is not None
        if stop_after_removal and model_id in current.battlefield_state.removed_model_ids:
            return session, model_id
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            return session, model_id
        submit_fixture_request(session, request)
    raise AssertionError("Fight On Death choice was not reached.")
