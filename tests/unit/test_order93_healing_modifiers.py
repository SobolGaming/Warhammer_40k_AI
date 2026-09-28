from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.phase15c_fight_order_helpers import fight_config, fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.army_mustering import EnhancementAssignment
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
    enhancements,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("ignore", [False, True])
def test_soulstealer_healing_modifier_choice_reenters_without_reroll(ignore: bool) -> None:
    session = _soulstealer_session()
    initial = session.lifecycle.to_payload()
    selected = False
    for _ in range(70):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            assert subject["kind"] == "healing_roll"
            assert subject["model_instance_id"] is not None
            operations = cast(list[dict[str, JsonValue]], payload["modifiers"])
            assert len(operations) == 1
            assert cast(dict[str, JsonValue], operations[0]["operation"])["operand"] == 1
            assert not _healing_dice(session)
            assert GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload() == (
                session.lifecycle.to_payload()
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:healing-choice",
                option_id="ignore-remaining" if ignore else "keep-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            selected = True
        else:
            submit_fixture_request(session, request)
        resolved = tuple(
            event
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == enhancements.SOULSTEALER_RESOLVED_EVENT
        )
        if resolved:
            assert selected, "The actual +1 model-roll modifier requires a player choice."
            payload = cast(dict[str, JsonValue], resolved[0].payload)
            assert payload["shadow_bonus"] == 1
            raw = cast(dict[str, JsonValue], payload["d6_result"])
            assert payload["roll_total"] == cast(int, raw["current_total"]) + (0 if ignore else 1)
            assert len(_healing_dice(session)) == 1
            restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
            assert restored.to_payload() == session.lifecycle.to_payload()
            replay = ReplayRunner(
                ReplayArtifact.capture(
                    artifact_id="order93-healing",
                    final_lifecycle=session.lifecycle,
                    initial_lifecycle_payload=initial,
                )
            ).run()
            assert replay.status is ReplayRunStatus.REPRODUCED, replay
            return
    raise AssertionError("No Soulstealer resolution reached.")


def _healing_dice(session: LocalGameSession) -> tuple[object, ...]:
    return tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == enhancements.SOULSTEALER_D6_ROLL_TYPE
    )


def _soulstealer_session() -> LocalGameSession:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    source = base.datasheet_by_id("core-character-leader")
    daemon = replace(
        source,
        datasheet_id="order93-slaanesh-character",
        keywords=DatasheetKeywordSet(
            keywords=("INFANTRY", "CHARACTER", "SLAANESH"),
            faction_keywords=("LEGIONES DAEMONICA",),
        ),
    )
    faction = replace(
        base.factions[0], faction_id="chaos-daemons", faction_keywords=("LEGIONES DAEMONICA",)
    )
    detachment = replace(
        next(item for item in base.detachments if item.detachment_id == "core-combined-arms"),
        canonical_detachment_id="daemonic-incursion",
        detachment_id="daemonic-incursion",
        faction_id="chaos-daemons",
        unit_datasheet_ids=(daemon.datasheet_id,),
    )
    catalog = replace(
        base,
        datasheets=(*base.datasheets, daemon),
        factions=(*base.factions, faction),
        detachments=(*base.detachments, detachment),
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(10),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        damage_profile=DamageProfile.fixed(99),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            for wargear in base.wargear
        ),
    )
    config = fight_config(
        game_id="order93-soulstealer",
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs={"source": (daemon.datasheet_id, "core-character-leader", 1)},
        catalog=catalog,
        alpha_faction_id="chaos-daemons",
        alpha_detachment_ids=("daemonic-incursion",),
    )
    assert config.mission_setup is not None
    config = replace(
        config,
        army_muster_requests=(
            replace(
                config.army_muster_requests[0],
                enhancement_assignments=(
                    EnhancementAssignment(
                        model_profile_id="core-character-leader",
                        model_index=1,
                        enhancement_id=enhancements.SOULSTEALER_ENHANCEMENT_ID,
                        target_unit_selection_id="source",
                        source_id=enhancements.SOULSTEALER_SOURCE_RULE_ID,
                    ),
                ),
            ),
            config.army_muster_requests[1],
        ),
        mission_setup=replace(
            config.mission_setup,
            deployment_zones=tuple(
                DeploymentZone.rectangle(
                    f"zone:{player}", player, min_x=0, min_y=y, max_x=100, max_y=y + 20
                )
                for player, y in (("player-a", 0), ("player-b", 80))
            ),
        ),
    )
    lifecycle, _units = fight_lifecycle(
        config=config,
        game_id=config.game_id,
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        fights_first_unit_keys=("source",),
    )
    state = lifecycle.state
    assert state is not None
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=model.initial_wounds - 1)
                        for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in state.army_definitions
    ]
    effect = generic_effect(
        effect_id="order93-healing-permission",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:source",),
        target_kind="this_unit",
        effect_kind="grant_ability",
        parameters={"ability": "modifier_ignore_permission", "selection": "any_or_all"},
    )
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    context = cast(dict[str, JsonValue], payload["context"])
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.FIGHT,
            effect_payload={**payload, "context": {**context, "phase": "fight"}},
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.FIGHT, player_id="player-a"
            ),
        )
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
