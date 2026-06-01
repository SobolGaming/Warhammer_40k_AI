from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

EDITION_ID = "warhammer_40000_10th"
SOURCE_PACKAGE_ID = "gw-10e-core-stratagems"
SOURCE_TITLE = "Warhammer 40,000 10th Edition Core Stratagems"
SOURCE_VERSION = "10e-core-rules"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-stratagem-source-v1"


@dataclass(frozen=True, slots=True)
class SourceStratagemRow:
    stratagem_id: str
    name: str
    command_point_cost: int
    category: str
    availability_kind: str
    detachment_id: str | None
    source_id: str
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    trigger_kind: str
    phase: str | None
    target_kind: str
    enumerable: bool
    target_policy_id: str
    handler_id: str
    eligible_roll_types: tuple[str, ...] = ()
    once_per_turn: bool = False
    once_per_battle: bool = False
    once_per_target_per_phase: bool = False
    allow_battle_shocked_targets: bool = False
    disabled: bool = False

    def to_payload(self) -> dict[str, bool | int | str | None | list[str]]:
        return {
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "command_point_cost": self.command_point_cost,
            "category": self.category,
            "availability_kind": self.availability_kind,
            "detachment_id": self.detachment_id,
            "source_id": self.source_id,
            "when_descriptor": self.when_descriptor,
            "target_descriptor": self.target_descriptor,
            "effect_descriptor": self.effect_descriptor,
            "restrictions_descriptor": self.restrictions_descriptor,
            "trigger_kind": self.trigger_kind,
            "phase": self.phase,
            "target_kind": self.target_kind,
            "enumerable": self.enumerable,
            "target_policy_id": self.target_policy_id,
            "handler_id": self.handler_id,
            "eligible_roll_types": list(self.eligible_roll_types),
            "once_per_turn": self.once_per_turn,
            "once_per_battle": self.once_per_battle,
            "once_per_target_per_phase": self.once_per_target_per_phase,
            "allow_battle_shocked_targets": self.allow_battle_shocked_targets,
            "disabled": self.disabled,
        }


def source_package_identity_payload() -> dict[str, str]:
    return {
        "edition_id": EDITION_ID,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_commit_or_import_hash": _import_hash(),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def core_stratagem_rows() -> tuple[SourceStratagemRow, ...]:
    source_prefix = f"{SOURCE_PACKAGE_ID}:core"
    return (
        SourceStratagemRow(
            stratagem_id="command-reroll",
            name="Command Re-roll",
            command_point_cost=1,
            category="battle_tactic",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:command-reroll",
            when_descriptor="after dice roll",
            target_descriptor="one eligible dice roll made by the player",
            effect_descriptor="reroll that dice roll",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_dice_roll",
            phase=None,
            target_kind="none",
            enumerable=True,
            target_policy_id="none",
            handler_id="core:command-reroll",
            eligible_roll_types=(
                "advance_roll",
                "charge_roll",
                "damage_roll",
                "desperate_escape_roll",
                "hazardous_test",
                "hit_roll",
                "number_of_attacks_roll",
                "save_roll",
                "wound_roll",
            ),
        ),
        SourceStratagemRow(
            stratagem_id="counter-offensive",
            name="Counter-offensive",
            command_point_cost=2,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:counter-offensive",
            when_descriptor="after an enemy unit has fought",
            target_descriptor="one eligible unit from the player's army that can fight",
            effect_descriptor="the target unit fights next",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="just_after_enemy_unit_has_fought",
            phase="fight",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="unsupported:phase-14e:fight-order-interrupt-unit",
            handler_id="unsupported:phase-14e:counter-offensive",
        ),
        SourceStratagemRow(
            stratagem_id="epic-challenge",
            name="Epic Challenge",
            command_point_cost=1,
            category="epic_deed",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:epic-challenge",
            when_descriptor="fight phase before resolving attacks",
            target_descriptor="one character model from the player's army",
            effect_descriptor="character attacks gain precision for that fight",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="start_phase",
            phase="fight",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="unsupported:phase-14e:character-model-fight-binding",
            handler_id="unsupported:phase-14e:epic-challenge",
        ),
        SourceStratagemRow(
            stratagem_id="fire-overwatch",
            name="Fire Overwatch",
            command_point_cost=1,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:fire-overwatch",
            when_descriptor=(
                "opponent movement or charge phase after an enemy unit is set up "
                "or starts or ends a move"
            ),
            target_descriptor="one eligible unit from the player's army that can shoot",
            effect_descriptor="the target unit shoots as if it were the shooting phase",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_enemy_unit_ends_move",
            phase="movement",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="out_of_phase_shooting_unit",
            handler_id="core:fire-overwatch",
        ),
        SourceStratagemRow(
            stratagem_id="go-to-ground",
            name="Go to Ground",
            command_point_cost=1,
            category="battle_tactic",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:go-to-ground",
            when_descriptor="opponent shooting phase after an enemy unit selects targets",
            target_descriptor="one infantry unit from the player's army selected as a target",
            effect_descriptor="the target unit gains benefit of cover and a defensive save effect",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_unit_selected_as_target",
            phase="shooting",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="selected_target_infantry_unit",
            handler_id="core:go-to-ground",
        ),
        SourceStratagemRow(
            stratagem_id="grenade",
            name="Grenade",
            command_point_cost=1,
            category="wargear",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:grenade",
            when_descriptor="shooting phase before selecting targets",
            target_descriptor=(
                "one grenades unit from the player's army and one enemy unit in range"
            ),
            effect_descriptor="roll six dice and inflict mortal wounds for each high result",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="start_phase",
            phase="shooting",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="grenades_unit_and_enemy_target",
            handler_id="core:grenade",
        ),
        SourceStratagemRow(
            stratagem_id="heroic-intervention",
            name="Heroic Intervention",
            command_point_cost=1,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:heroic-intervention",
            when_descriptor="opponent charge phase after an enemy unit ends a charge move",
            target_descriptor="one eligible nearby unit from the player's army",
            effect_descriptor="the target unit declares a charge against the enemy unit",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_enemy_unit_ends_move",
            phase="charge",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="unsupported:phase-14e:heroic-intervention-charge-unit",
            handler_id="unsupported:phase-14e:heroic-intervention",
        ),
        SourceStratagemRow(
            stratagem_id="insane-bravery",
            name="Insane Bravery",
            command_point_cost=1,
            category="epic_deed",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:insane-bravery",
            when_descriptor="before a battle-shock test",
            target_descriptor="one unit from the player's army about to take the test",
            effect_descriptor="the battle-shock test is automatically passed",
            restrictions_descriptor="once per battle",
            trigger_kind="start_phase",
            phase="command",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="battle_shock_test_unit",
            handler_id="core:insane-bravery",
            once_per_battle=True,
            allow_battle_shocked_targets=True,
        ),
        SourceStratagemRow(
            stratagem_id="rapid-ingress",
            name="Rapid Ingress",
            command_point_cost=1,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:rapid-ingress",
            when_descriptor="end of the opponent movement phase",
            target_descriptor="one unit from the player's army in reserves",
            effect_descriptor="arrive from reserves as if it were the reinforcements step",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="end_phase",
            phase="movement",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="reserves_unit",
            handler_id="core:rapid-ingress",
        ),
        SourceStratagemRow(
            stratagem_id="new-orders",
            name="New Orders",
            command_point_cost=1,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:new-orders",
            when_descriptor="command phase tactical secondary mission step",
            target_descriptor="one active tactical secondary mission card",
            effect_descriptor="discard the card and draw a replacement",
            restrictions_descriptor="chapter approved tactical mission support",
            trigger_kind="start_phase",
            phase="command",
            target_kind="tactical_secondary_card",
            enumerable=True,
            target_policy_id="active_tactical_secondary_card",
            handler_id="core:new-orders",
        ),
        SourceStratagemRow(
            stratagem_id="smokescreen",
            name="Smokescreen",
            command_point_cost=1,
            category="wargear",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:smokescreen",
            when_descriptor="opponent shooting phase after an enemy unit selects targets",
            target_descriptor="one smoke unit from the player's army selected as a target",
            effect_descriptor="the target unit gains stealth and benefit of cover",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_unit_selected_as_target",
            phase="shooting",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="selected_target_smoke_unit",
            handler_id="core:smokescreen",
        ),
        SourceStratagemRow(
            stratagem_id="tank-shock",
            name="Tank Shock",
            command_point_cost=1,
            category="strategic_ploy",
            availability_kind="core",
            detachment_id=None,
            source_id=f"{source_prefix}:tank-shock",
            when_descriptor="charge phase after a vehicle unit ends a charge move",
            target_descriptor=(
                "one vehicle unit from the player's army and one enemy unit within engagement range"
            ),
            effect_descriptor="roll dice based on strength and inflict mortal wounds",
            restrictions_descriptor="matched play same stratagem per phase",
            trigger_kind="after_unit_ends_charge_move",
            phase="charge",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="unsupported:phase-14e:vehicle-charge-target-binding",
            handler_id="unsupported:phase-14e:tank-shock",
        ),
    )


def detachment_stratagem_rows() -> tuple[SourceStratagemRow, ...]:
    source_prefix = f"{SOURCE_PACKAGE_ID}:detachment:gladius-task-force"
    return (
        SourceStratagemRow(
            stratagem_id="armour-of-contempt",
            name="Armour of Contempt",
            command_point_cost=1,
            category="battle_tactic",
            availability_kind="detachment",
            detachment_id="gladius-task-force",
            source_id=f"{source_prefix}:armour-of-contempt",
            when_descriptor="after an enemy unit selects targets",
            target_descriptor="one selected adeptus astartes unit from the player's army",
            effect_descriptor="improve the targeted unit's armour resilience for the attack",
            restrictions_descriptor="gladius task force detachment stratagem",
            trigger_kind="after_unit_selected_as_target",
            phase="shooting",
            target_kind="friendly_unit",
            enumerable=False,
            target_policy_id="unsupported:phase-13:selected-target-unit",
            handler_id="unsupported:phase-13:armour-of-contempt",
        ),
    )


def stratagem_rows() -> tuple[SourceStratagemRow, ...]:
    return tuple(
        sorted(
            (*core_stratagem_rows(), *detachment_stratagem_rows()),
            key=lambda row: (row.availability_kind, row.stratagem_id),
        )
    )


def _import_hash() -> str:
    encoded = json.dumps(
        {
            "edition_id": EDITION_ID,
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_title": SOURCE_TITLE,
            "source_version": SOURCE_VERSION,
            "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
            "stratagems": [row.to_payload() for row in stratagem_rows()],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
