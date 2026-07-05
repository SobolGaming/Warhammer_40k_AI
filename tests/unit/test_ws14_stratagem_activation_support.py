from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
    source_backed_stratagem_activation_source_package_id,
)
from warhammer40k_core.engine.faction_content.stratagem_record_merge import (
    merge_stratagem_records_with_contribution_overrides,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
)
from warhammer40k_core.engine.phase import GameLifecycleStage
from warhammer40k_core.engine.rule_execution import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    RuleExecutionContext,
    RuleExecutionStatus,
    default_rule_execution_registry,
    execute_rule_ir,
)
from warhammer40k_core.engine.selected_target_context import SELECTED_TARGET_UNIT_CONTEXT_KEY
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27,
    faction_stratagem_activation_2026_27,
    faction_subrules_2026_27,
)


def test_ws14_stratagem_activation_profiles_cover_source_only_detachment_rows() -> None:
    source_only_rows = tuple(
        row for row in faction_subrules_2026_27.stratagem_rows() if not row.runtime_consumer_ids
    )
    profiles = faction_stratagem_activation_2026_27.stratagem_activation_profiles()
    source_only_row_ids = {row.source_row_id for row in source_only_rows}
    profile_source_row_ids = {profile.source_row_id for profile in profiles}
    cavalcade_generic_row_ids = set(
        faction_generic_ir_support_2026_27.supported_cavalcade_of_chaos_stratagem_source_row_ids()
    )

    assert len(source_only_rows) == 1083
    assert len(profiles) == 1080
    assert cavalcade_generic_row_ids <= source_only_row_ids
    assert profile_source_row_ids == source_only_row_ids - cavalcade_generic_row_ids

    for profile in profiles:
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, profile.rule_ir_payload()))
        assert rule_ir.is_supported
        assert rule_ir.ir_hash() == profile.rule_ir_hash


def test_ws14_generated_stratagem_rule_ir_freezes_supported_effect_durations() -> None:
    profiles = faction_stratagem_activation_2026_27.stratagem_activation_profiles()
    effect_profiles = [
        profile
        for profile in profiles
        if any(
            clause.effects
            for clause in RuleIR.from_payload(
                cast(RuleIRPayload, profile.rule_ir_payload())
            ).clauses
        )
    ]
    duration_profiles = [
        profile
        for profile in effect_profiles
        if any(
            clause.effects and clause.duration is not None
            for clause in RuleIR.from_payload(
                cast(RuleIRPayload, profile.rule_ir_payload())
            ).clauses
        )
    ]

    assert len(effect_profiles) == 171
    assert len(duration_profiles) == 167

    payload = effect_profiles[0].rule_ir_payload()
    payload["rule_id"] = "tampered"

    assert effect_profiles[0].rule_ir_payload()["rule_id"] == effect_profiles[0].profile_id


def test_ws14_source_backed_stratagem_activation_records_are_runtime_loadable() -> None:
    records = source_backed_detachment_stratagem_activation_records()
    profiles = faction_stratagem_activation_2026_27.stratagem_activation_profiles()

    assert source_backed_stratagem_activation_source_package_id() == (
        faction_stratagem_activation_2026_27.SOURCE_PACKAGE_ID
    )
    assert len(records) == sum(len(profile.phase_tokens) for profile in profiles)
    assert len(records) == 1264
    assert StratagemCatalogIndex.from_records(records).all_records() == tuple(
        sorted(records, key=lambda record: record.record_id)
    )
    assert {record.definition.handler_id for record in records} == {
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    }

    more_dakka = {
        record.definition.stratagem_id: record
        for record in records
        if record.detachment_id == "more-dakka"
    }
    get_stuck_in = more_dakka["000009992003"]
    assert get_stuck_in.definition.target_spec.target_policy_id == "friendly_unit"
    assert get_stuck_in.definition.target_spec.excluded_keywords == ("GRETCHIN",)
    huge_show_offs = more_dakka["000009992004"]
    assert huge_show_offs.definition.target_spec.required_keywords == ("WALKER",)
    assert huge_show_offs.definition.target_spec.excluded_keywords == ("KILLA KANS",)

    for record in more_dakka.values():
        payload = record.definition.effect_payload
        assert isinstance(payload, dict)
        rule_ir_payload = payload["rule_ir"]
        assert isinstance(rule_ir_payload, dict)
        RuleIR.from_payload(cast(RuleIRPayload, rule_ir_payload))


def test_ws14_court_of_the_phoenician_stratagem_profiles_use_court_rule_ir() -> None:
    profiles = {
        profile.stratagem_id: profile
        for profile in faction_stratagem_activation_2026_27.stratagem_activation_profiles()
        if profile.detachment_id == "court-of-the-phoenician"
    }

    assert set(profiles) == {
        "000010655002",
        "000010655003",
        "000010655004",
        "000010655005",
        "000010655006",
        "000010655007",
    }
    assert profiles["000010655004"].required_keywords == ("DAEMON",)
    assert profiles["000010655006"].required_keywords == ("DAEMON",)
    for profile in profiles.values():
        expected_payload = court_ir.stratagem_activation_rule_ir_payload_by_profile_id(
            profile.profile_id
        )
        assert expected_payload is not None
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, profile.rule_ir_payload()))
        expected_rule_ir = RuleIR.from_payload(expected_payload)
        assert rule_ir == expected_rule_ir
        assert rule_ir.is_supported
        assert any(clause.effects for clause in rule_ir.clauses)


def test_ws14_selected_target_activation_rule_ir_executes_from_structured_context() -> None:
    profile = next(
        profile
        for profile in faction_stratagem_activation_2026_27.stratagem_activation_profiles()
        if profile.target_policy_id == "selected_target_unit"
    )
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, profile.rule_ir_payload()))
    target_unit_id = "army-alpha:selected-target-unit"

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id="ws14-selected-target-activation",
            player_id="player-a",
            battle_round=1,
            phase=None,
            active_player_id="player-b",
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings[0]["target_kind"] == "selected_target"
    assert result.target_bindings[0]["target_unit_instance_ids"] == [target_unit_id]


def test_ws14_source_backed_stratagem_effect_duration_persists_and_expires() -> None:
    profile = next(
        profile
        for profile in faction_stratagem_activation_2026_27.stratagem_activation_profiles()
        if profile.profile_id
        == "phase17s:stratagem:adeptus-mechanicus:eradication-cohort:000010748002"
    )
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, profile.rule_ir_payload()))
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    target_unit = _unit(
        catalog=catalog,
        army_id="army-alpha",
        unit_selection_id="duration-target-unit",
    )
    state = _state(
        _army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit=target_unit,
        ),
        active_player_id="player-b",
    )

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.FIGHT,
            active_player_id="player-b",
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            state=state,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 1
    created = result.created_persisting_effects[0]
    assert created.expiration.to_payload() == {
        "expiration_kind": "end_phase",
        "battle_round": 1,
        "phase": "fight",
        "player_id": "player-b",
    }
    assert state.persisting_effects_for_unit(target_unit.unit_instance_id) == (created,)

    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1,
            phase=BattlePhaseKind.FIGHT,
            player_id="player-b",
        )
    )

    assert state.persisting_effects_for_unit(target_unit.unit_instance_id) == ()


def test_ws14_source_backed_stratagem_activation_does_not_shadow_named_records() -> None:
    records = source_backed_detachment_stratagem_activation_records()
    source_backed = next(
        record
        for record in records
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992003"
    )
    retained = next(
        record
        for record in records
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992004"
    )
    named_record = replace(
        source_backed,
        record_id="ws14:named-handler:more-dakka:000009992003",
        definition=replace(
            source_backed.definition,
            handler_id="ws14:named-handler",
        ),
    )

    merged = merge_stratagem_records_with_contribution_overrides(records, (named_record,))

    assert named_record in merged
    assert retained in merged
    assert tuple(
        record
        for record in merged
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992003"
    ) == (named_record,)


def _unit(*, catalog: ArmyCatalog, army_id: str, unit_selection_id: str) -> UnitInstance:
    datasheet = catalog.datasheet_by_id("core-character-leader")
    profile = datasheet.model_profiles[0]
    option = datasheet.wargear_options[0]
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=profile.model_profile_id,
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=profile.model_profile_id,
                    wargear_ids=option.default_wargear_ids,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _army(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit: UnitInstance,
) -> ArmyDefinition:
    detachment = catalog.detachments[0]
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=detachment.faction_id,
            detachment_ids=(detachment.detachment_id,),
        ),
        units=(unit,),
    )


def _state(*armies: ArmyDefinition, active_player_id: str) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="ws14-stratagem-duration-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    return state
