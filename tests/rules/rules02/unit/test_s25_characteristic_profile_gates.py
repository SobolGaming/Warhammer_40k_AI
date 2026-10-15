from typing import cast

from tests.shared.category_migration.s25_characteristic_profile_gates import (
    ArmyCatalog,
    Characteristic,
    CharacteristicValue,
    DecisionError,
    GameLifecycleError,
    JsonValue,
    LifecycleStatusKind,
    MeleeDeclarationProposalRequest,
    epic_checkpoint,
    projection_melee_request,
    pytest,
    rule_ir_modified_weapon_profile,
    submit_fixture_request,
)


@pytest.mark.parametrize("melee", [False, True])
@pytest.mark.parametrize("invalid", ["delta", "source", "characteristic"])
def test_original_dispatch_validation_precedes_known_profile_noop(
    melee: bool, invalid: str
) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    weapon = next(
        w
        for w in catalog.wargear
        if w.wargear_id == ("core-leader-blade" if melee else "core-bolt-rifle")
    ).weapon_profiles[0]
    parameters: dict[str, object] = {
        "characteristic": "range" if melee else "weapon_skill",
        "delta": 1,
    }
    assert (
        rule_ir_modified_weapon_profile(
            parameters=parameters,
            profile=weapon,
            source_id="analytical:s25-noop",
            modifier_id="s25-noop",
        )
        == weapon
    )
    if invalid == "delta":
        parameters["delta"] = True
        error = "must be an integer"
    elif invalid == "characteristic":
        parameters["characteristic"] = "unknown"
        error = "characteristic is invalid"
    else:
        error = "source_id must be non-empty"
    with pytest.raises(GameLifecycleError, match=error):
        rule_ir_modified_weapon_profile(
            parameters=parameters,
            profile=weapon,
            source_id="" if invalid == "source" else "analytical:s25-noop",
            modifier_id="s25-noop",
        )
    with pytest.raises(GameLifecycleError, match="characteristic is unsupported"):
        rule_ir_modified_weapon_profile(
            parameters={"characteristic": "leadership", "delta": 1},
            profile=weapon,
            source_id="analytical:s25-unsupported-weapon",
            modifier_id="s25-unsupported-weapon",
        )


__all__: list[str] = []
__all__ += ["Characteristic", "CharacteristicValue", "DecisionError", "JsonValue"]
__all__ += ["LifecycleStatusKind", "MeleeDeclarationProposalRequest", "cast", "epic_checkpoint"]
__all__ += ["projection_melee_request", "submit_fixture_request"]
