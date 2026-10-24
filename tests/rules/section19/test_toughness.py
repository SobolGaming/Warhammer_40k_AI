"""19.02: use current highest bodyguard T, then surviving leader/support T."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import contract_characteristic, replace_unit
from tests.support.section19_fixtures import attached_scene
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_sequence_geometry_targets import _target_unit_toughness


@pytest.mark.parametrize(
    ("body_alive", "leader_alive", "support_alive", "expected"),
    [
        (5, 1, 1, 7),
        (1, 1, 1, 3),
        (0, 1, 1, 11),
        (0, 1, 0, 9),
        (0, 0, 1, 11),
    ],
)
@pytest.mark.parametrize("alias", ["canonical", "bodyguard", "leader", "support"])
def test_attack_toughness_selects_highest_living_models_of_the_required_component(
    section19_definitions: Section02Definitions,
    body_alive: int,
    leader_alive: int,
    support_alive: int,
    expected: int,
    alias: str,
) -> None:
    s = attached_scene(section19_definitions, support=True)
    # Explicit heterogeneous T contract; native model identity/geometry/equipment retained.
    for role, values in (("bodyguard", (3, 4, 5, 6, 7)), ("leader", (9,)), ("support", (11,))):
        unit = s.component(role)
        replace_unit(
            s.state,
            replace(
                unit,
                own_models=tuple(
                    contract_characteristic(m, Characteristic.TOUGHNESS, t)
                    for m, t in zip(unit.own_models, values, strict=True)
                ),
            ),
        )
    for role, count in (
        ("bodyguard", body_alive),
        ("leader", leader_alive),
        ("support", support_alive),
    ):
        s.set_living(role, count)
    selected = (
        s.view.unit_instance_id if alias == "canonical" else s.component(alias).unit_instance_id
    )
    assert _target_unit_toughness(state=s.state, target_unit_instance_id=selected) == expected
    assert len(s.view.alive_models()) == body_alive + leader_alive + support_alive
