"""Fresh mutable state, nested catalog payloads and controller histories."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_contracts import command_session
from tests.support.section08_fixtures import command_state, damage_to_count, mark_shocked


def test_case_graphs_and_histories_do_not_leak_into_definitions_or_later_cases(
    section08_definitions: Section02Definitions,
) -> None:
    catalog_before = section08_definitions.package.to_payload()
    first = command_state(section08_definitions)
    later = command_state(section08_definitions)
    baseline = later.to_payload()
    damage_to_count(first, 4)
    mark_shocked(first)
    session = command_session(section08_definitions, first)
    session.lifecycle.decision_controller.event_log.append("constructed_isolation_marker", {"x": 1})
    unit = next(a for a in first.army_definitions if a.player_id == "owner").units[0]
    payload = next(a.rule_ir_payload for a in unit.datasheet_abilities if a.rule_ir_payload)
    payload["constructed_isolation_mutation"] = {"nested": [1, 2]}
    assert later.to_payload() == baseline
    assert command_state(section08_definitions).to_payload() == baseline
    assert section08_definitions.package.to_payload() == catalog_before
    assert (
        command_session(
            section08_definitions, later
        ).lifecycle.decision_controller.event_log.records
        == ()
    )
