from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
    DatasheetCatalogError,
)
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_abilities import (
    deadly_demise_profile_for_unit,
    firing_deck_value_for_unit,
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
    unit_has_deadly_demise,
    unit_has_deep_strike,
    unit_has_firing_deck,
    unit_has_infiltrators,
    unit_has_leader,
    unit_has_scouts,
    unit_has_support,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


def test_core_keyword_ability_descriptors_enable_boolean_families_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(ability_id="source-deep-strike", name="Core Deep Strike"),
        _ability(ability_id="source-infiltrators", name="Infiltrators"),
        _ability(ability_id="source-leader", name="Leader"),
        _ability(ability_id="source-support", name="Support"),
    )

    assert unit_has_deep_strike(unit)
    assert unit_has_infiltrators(unit)
    assert unit_has_leader(unit)
    assert unit_has_support(unit)


def test_parameterized_core_keyword_ability_descriptors_parse_values_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(
            ability_id="source-scouts",
            name='Scouts 6"',
            parameter_tokens=('6"',),
        ),
        _ability(
            ability_id="source-firing-deck",
            name="Firing Deck 2",
            parameter_tokens=("2",),
        ),
        _ability(
            ability_id="source-deadly-demise",
            name="Deadly Demise D3",
            parameter_tokens=("d3",),
        ),
    )

    scouts_descriptors = scouts_ability_descriptors_for_unit(unit)
    deadly_demise = deadly_demise_profile_for_unit(unit)

    assert unit_has_scouts(unit)
    assert unit_has_firing_deck(unit)
    assert unit_has_deadly_demise(unit)
    assert len(scouts_descriptors) == 1
    assert scouts_distance_inches_from_descriptor(scouts_descriptors[0]) == 6.0
    assert firing_deck_value_for_unit(unit) == 2
    assert deadly_demise is not None
    assert deadly_demise.mortal_wounds_token == "D3"


def test_catalog_ability_descriptor_validates_wargear_ir_metadata() -> None:
    with pytest.raises(DatasheetCatalogError, match="requires source_wargear_id"):
        DatasheetAbilityDescriptor(
            ability_id="test-icon",
            name="Test Icon",
            source_id="datasheet:test:ability:test-icon",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.WARGEAR,
            effect_description="Test icon descriptor.",
        )
    with pytest.raises(DatasheetCatalogError, match="must not include source_wargear_id"):
        DatasheetAbilityDescriptor(
            ability_id="test-core",
            name="Test Core",
            source_id="datasheet:test:ability:test-core",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            source_wargear_id="test-wargear",
            effect_description="Test core descriptor.",
        )
    with pytest.raises(DatasheetCatalogError, match="requires rule_ir_payload"):
        DatasheetAbilityDescriptor(
            ability_id="test-instrument",
            name="Test Instrument",
            source_id="datasheet:test:ability:test-instrument",
            support=CatalogAbilitySupport.GENERIC_RULE_IR,
            source_kind=CatalogAbilitySourceKind.WARGEAR,
            source_wargear_id="test-instrument",
            effect_description="Test instrument descriptor.",
        )


def test_catalog_ability_descriptor_rejects_non_json_ir_payload_values() -> None:
    valid = DatasheetAbilityDescriptor(
        ability_id="test-json",
        name="Test JSON",
        source_id="datasheet:test:ability:test-json",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Test JSON descriptor.",
        rule_ir_payload={"nested": [None, True, 1.5, {"value": "ok"}]},
    )

    assert valid.rule_ir_payload == {"nested": [None, True, 1.5, {"value": "ok"}]}
    with pytest.raises(DatasheetCatalogError, match="must be finite"):
        DatasheetAbilityDescriptor(
            ability_id="test-inf",
            name="Test Infinity",
            source_id="datasheet:test:ability:test-inf",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test infinity descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {"bad": math.inf}),
        )
    with pytest.raises(DatasheetCatalogError, match="must be a JSON object"):
        DatasheetAbilityDescriptor(
            ability_id="test-container",
            name="Test Container",
            source_id="datasheet:test:ability:test-container",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test container descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, "not-object"),
        )
    with pytest.raises(DatasheetCatalogError, match="key must be a string"):
        DatasheetAbilityDescriptor(
            ability_id="test-key",
            name="Test Key",
            source_id="datasheet:test:ability:test-key",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test key descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {1: "bad"}),
        )
    with pytest.raises(DatasheetCatalogError, match="JSON-safe"):
        DatasheetAbilityDescriptor(
            ability_id="test-object",
            name="Test Object",
            source_id="datasheet:test:ability:test-object",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description="Test object descriptor.",
            rule_ir_payload=cast(CatalogJsonObject, {"bad": object()}),
        )


def _unit_with_abilities(*abilities: DatasheetAbilityDescriptor) -> UnitInstance:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="army-alpha",
        selection=UnitMusterSelection(
            unit_selection_id="ability-unit",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
        datasheet=datasheet,
    )
    return replace(unit, datasheet_abilities=abilities)


def _ability(
    *,
    ability_id: str,
    name: str,
    parameter_tokens: tuple[str, ...] = (),
) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name=name,
        source_id=f"datasheet:core-intercessor-like-infantry:ability:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description=f"{name} descriptor.",
        timing_tags=(),
        parameter_tokens=parameter_tokens,
    )


@pytest.mark.parametrize(
    "source_kind", [CatalogAbilitySourceKind.CORE, CatalogAbilitySourceKind.DATASHEET]
)
def test_order56_core_family_is_normalized_at_the_descriptor_boundary(
    source_kind: CatalogAbilitySourceKind,
) -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily

    descriptor = _ability(
        ability_id="source-scouts", name='Core Scouts 8"', parameter_tokens=("8",)
    )
    descriptor = replace(descriptor, source_kind=source_kind)
    assert descriptor.core_family is CoreAbilityFamily.SCOUTS
    assert (
        DatasheetAbilityDescriptor.from_payload(descriptor.to_payload()).core_family
        is CoreAbilityFamily.SCOUTS
    )
    identified = replace(descriptor, ability_id="core-scouts", name="Localized display label")
    assert identified.core_family is CoreAbilityFamily.SCOUTS
    assert scouts_ability_descriptors_for_unit(_unit_with_abilities(identified)) == (identified,)


def test_order56_native_damage_abilities_preserve_each_source_before_selection() -> None:
    from warhammer40k_core.engine.unit_abilities import (
        deadly_demise_profiles_for_unit,
        feel_no_pain_profiles_for_unit,
    )

    unit = _unit_with_abilities(
        _ability(ability_id="fnp-a", name="Feel No Pain", parameter_tokens=("5+",)),
        _ability(ability_id="fnp-b", name="Feel No Pain", parameter_tokens=("5+",)),
        _ability(ability_id="dd-a", name="Deadly Demise", parameter_tokens=("D3",)),
        _ability(ability_id="dd-b", name="Deadly Demise", parameter_tokens=("D6",)),
    )
    fnp = feel_no_pain_profiles_for_unit(unit)
    demise = deadly_demise_profiles_for_unit(unit)
    assert tuple(profile.threshold for profile in fnp) == (5, 5)
    assert {profile.mortal_wounds_token for profile in demise} == {"D3", "D6"}
    assert (
        len(
            {profile.ability_source.instance_id for profile in fnp}
            | {profile.ability_source.instance_id for profile in demise}
        )
        == 4
    )


def test_order56_numeric_core_instances_require_and_retain_one_active_source() -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
    from warhammer40k_core.engine.core_ability_state import CoreAbilitySelection
    from warhammer40k_core.engine.phase import GameLifecycleError

    unit = _unit_with_abilities(
        _ability(ability_id="deck:a", name="Firing Deck 2", parameter_tokens=("2",)),
        _ability(ability_id="deck:b", name="Firing Deck 5", parameter_tokens=("5",)),
    )
    with pytest.raises(GameLifecycleError, match="selection"):
        firing_deck_value_for_unit(unit)
    source = next(
        source for source in unit.ability_source_instances() if source.ability_id == "deck:a"
    )
    selected = replace(
        unit,
        core_ability_selections=(
            CoreAbilitySelection(
                family=CoreAbilityFamily.FIRING_DECK,
                instance_id=source.instance_id,
                decision_result_id="choice:1",
                opportunity_id="opportunity:1",
            ),
        ),
    )
    assert firing_deck_value_for_unit(selected) == 2
    assert UnitInstance.from_payload(selected.to_payload()) == selected
    assert len(selected.ability_source_instances()) == 2
    with pytest.raises(GameLifecycleError, match="source"):
        replace(
            selected,
            core_ability_selections=(
                replace(selected.core_ability_selections[0], instance_id="forged"),
            ),
        )


@pytest.mark.parametrize(
    ("ability_name", "tokens", "expected"),
    [
        ("Firing Deck", ("2", "5"), 2),
        ("Lone Operative", ("9", "12"), 9),
        ("Fights First", ("", ""), None),
        ("Stealth", ("", ""), None),
    ],
)
@pytest.mark.parametrize("during_setup", [False, True])
def test_order56_core_instance_decision_uses_facade_and_restores(
    during_setup: bool,
    ability_name: str,
    tokens: tuple[str, str],
    expected: int | None,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.core_ability_selection import (
        SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE,
    )
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.engine.unit_abilities import lone_operative_profile_for_unit

    abilities = tuple(
        _ability(
            ability_id=f"source:{index}",
            name=ability_name,
            parameter_tokens=(token,) if token else (),
        )
        for index, token in enumerate(tokens)
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, *abilities))
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, _ = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",), catalog=catalog)
    if during_setup:
        config = lifecycle.config
        lifecycle = GameLifecycle()
        lifecycle.start(config)
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    choices = 0
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE
    ):
        request = status.decision_request
        assert len(request.options) == 2
        assert request.actor_id is not None
        assert session.view(viewer_player_id=request.actor_id)["pending_decision"] is not None
        if during_setup:
            opponent = "player-b" if request.actor_id == "player-a" else "player-a"
            pending_view = session.view(viewer_player_id=opponent)["pending_decision"]
            assert isinstance(pending_view, dict)
            assert pending_view["decision_type"] == "hidden_decision"
            assert "ability_sources" not in str(pending_view)
        lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
        session = LocalGameSession(lifecycle=lifecycle)
        source_option = next(
            option
            for option in request.options
            if cast(dict[str, object], cast(dict[str, object], option.payload)["ability_source"])[
                "ability_id"
            ]
            == "source:0"
        )
        pending_payload = lifecycle.to_payload()
        drifted = deepcopy(pending_payload)
        pending = drifted["decisions"]["queue"]["pending_requests"][0]
        pending["options"] = pending["options"][:-1]
        with pytest.raises(GameLifecycleError, match=r"inventory drift|decision_requested event"):
            GameLifecycle.from_payload(drifted)
        with pytest.raises(DecisionError, match="finite action space"):
            session.submit_option(
                request_id=request.request_id, option_id="forged", result_id=f"invalid:{choices}"
            )
        assert lifecycle.to_payload() == pending_payload
        status = session.submit_option(
            request_id=request.request_id,
            option_id=source_option.option_id,
            result_id=f"core-choice:{choices}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        if during_setup:
            from warhammer40k_core.adapters.event_stream import EventStreamCursor

            owner_events = session.events_since(
                EventStreamCursor(), viewer_player_id=request.actor_id
            )
            opponent = "player-b" if request.actor_id == "player-a" else "player-a"
            other_events = session.events_since(EventStreamCursor(), viewer_player_id=opponent)
            selected_event = next(
                event
                for event in owner_events["events"]
                if event["event_type"] == "core_ability_instance_selected"
                and isinstance(event["payload"], dict)
                and event["payload"].get("result_id") == f"core-choice:{choices}"
            )
            assert selected_event not in other_events["events"]
        choices += 1
        assert choices <= 10
    assert choices >= 2
    if during_setup:
        next_request = status.decision_request
        assert next_request is not None
        status = session.submit_option(
            request_id=next_request.request_id,
            option_id=next_request.options[0].option_id,
            result_id="order56:next-setup-step",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    for army in restored.state.army_definitions:
        for unit in army.units:
            if not unit.core_ability_selections:
                continue
            if ability_name == "Firing Deck":
                assert firing_deck_value_for_unit(unit) == expected
            if ability_name == "Lone Operative":
                profile = lone_operative_profile_for_unit(unit)
                assert profile is not None
                assert profile.range_inches == expected
            assert len(unit.ability_source_instances()) >= 2


def test_order56_keyword_grants_preserve_sources_even_when_already_present() -> None:
    from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
    from warhammer40k_core.engine.core_ability_state import core_instance_groups
    from warhammer40k_core.engine.model_keyword_grants import grant_unit_keywords

    native = _unit_with_abilities(_ability(ability_id="core-deep-strike", name="Deep Strike"))
    first = grant_unit_keywords(
        native, keywords=("DEEP STRIKE",), source_id="source:a", source_instance_id="effect:a"
    )
    second = grant_unit_keywords(
        first, keywords=("DEEP STRIKE",), source_id="source:b", source_instance_id="effect:b"
    )
    assert unit_has_deep_strike(second)
    sources = dict(core_instance_groups(second))[CoreAbilityFamily.DEEP_STRIKE]
    assert len(sources) == 3
    assert len({source.instance_id for source in sources}) == 3
    assert UnitInstance.from_payload(second.to_payload()) == second
    assert (
        grant_unit_keywords(
            second, keywords=("DEEP STRIKE",), source_id="source:b", source_instance_id="effect:b"
        )
        == second
    )
