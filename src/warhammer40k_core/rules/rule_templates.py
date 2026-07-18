from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class RuleTemplateError(ValueError):
    """Raised when Phase 17C language template metadata is invalid."""


class RuleTemplateFamily(StrEnum):
    AURA = "aura"
    CHARACTERISTIC_MODIFICATION = "characteristic_modification"
    CHARACTERISTIC_SET = "characteristic_set"
    CONDITIONAL_WEAPON_ABILITY_GRANT = "conditional_weapon_ability_grant"
    CONTEXTUAL_STATUS = "contextual_status"
    DESPERATE_ESCAPE_REQUIREMENT = "desperate_escape_requirement"
    DICE_ROLL_MODIFICATION = "dice_roll_modification"
    DICE_ROLL_OVERRIDE = "dice_roll_override"
    DISTANCE_PREDICATE = "distance_predicate"
    GRANT_ABILITY = "grant_ability"
    KEYWORD_GATE = "keyword_gate"
    MOVEMENT_DISTANCE_MODIFICATION = "movement_distance_modification"
    OUT_OF_PHASE_ACTION = "out_of_phase_action"
    PLACEMENT_PERMISSION_RESTRICTION = "placement_permission_restriction"
    REROLL_PERMISSION = "reroll_permission"
    RESOURCE_MODIFICATION = "resource_modification"
    RETURN_ON_DEATH = "return_on_death"
    SELECTED_TARGET_CONSTRAINT = "selected_target_constraint"
    TRACKED_TARGET_SELECTION = "tracked_target_selection"
    TIMING_WINDOW = "timing_window"


class RuleTemplatePayload(TypedDict):
    template_id: str
    family: str
    description: str
    canonical_patterns: list[str]


@dataclass(frozen=True, slots=True)
class RuleTemplate:
    template_id: str
    family: RuleTemplateFamily
    description: str
    canonical_patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "template_id", _validate_identifier("template_id", self.template_id)
        )
        if type(self.family) is not RuleTemplateFamily:
            raise RuleTemplateError("RuleTemplate family must be RuleTemplateFamily.")
        object.__setattr__(
            self, "description", _validate_identifier("description", self.description)
        )
        object.__setattr__(
            self,
            "canonical_patterns",
            _validate_identifier_tuple("canonical_patterns", self.canonical_patterns),
        )

    def stable_identity(self) -> str:
        return f"rule-template:{self.family.value}:{self.template_id}"

    def to_payload(self) -> RuleTemplatePayload:
        return {
            "template_id": self.template_id,
            "family": self.family.value,
            "description": self.description,
            "canonical_patterns": list(self.canonical_patterns),
        }

    @classmethod
    def from_payload(cls, payload: RuleTemplatePayload) -> Self:
        return cls(
            template_id=payload["template_id"],
            family=rule_template_family_from_token(payload["family"]),
            description=payload["description"],
            canonical_patterns=tuple(payload["canonical_patterns"]),
        )


KEYWORD_GATE_TEMPLATE_ID = "phase17c:keyword-gate"
TIMING_WINDOW_TEMPLATE_ID = "phase17c:timing-window"
DISTANCE_PREDICATE_TEMPLATE_ID = "phase17c:distance-predicate"
SELECTED_TARGET_TEMPLATE_ID = "phase17c:selected-target-constraint"
TRACKED_TARGET_SELECTION_TEMPLATE_ID = "phase17c:tracked-target-selection"
DICE_ROLL_MODIFIER_TEMPLATE_ID = "phase17c:dice-roll-modifier"
DICE_ROLL_OVERRIDE_TEMPLATE_ID = "phase17c:dice-roll-override"
REROLL_PERMISSION_TEMPLATE_ID = "phase17c:reroll-permission"
CHARACTERISTIC_MODIFIER_TEMPLATE_ID = "phase17c:characteristic-modifier"
CHARACTERISTIC_SET_TEMPLATE_ID = "phase17c:characteristic-set"
CONTEXTUAL_STATUS_TEMPLATE_ID = "phase17c:contextual-status"
DESPERATE_ESCAPE_TEMPLATE_ID = "phase17c:desperate-escape-requirement"
RESOURCE_MODIFIER_TEMPLATE_ID = "phase17c:resource-modifier"
RETURN_ON_DEATH_TEMPLATE_ID = "phase17c:first-death-return"
GRANT_ABILITY_TEMPLATE_ID = "phase17c:grant-ability"
WEAPON_ABILITY_GRANT_TEMPLATE_ID = "phase17c:weapon-ability-grant"
MOVEMENT_DISTANCE_TEMPLATE_ID = "phase17c:movement-distance-modifier"
OUT_OF_PHASE_ACTION_TEMPLATE_ID = "phase17c:out-of-phase-action"
PLACEMENT_TEMPLATE_ID = "phase17c:placement-permission-restriction"
AURA_TEMPLATE_ID = "phase17c:aura"


def initial_rule_templates() -> tuple[RuleTemplate, ...]:
    return INITIAL_RULE_TEMPLATES


def rule_template_by_id(template_id: str) -> RuleTemplate:
    requested = _validate_identifier("template_id", template_id)
    for template in INITIAL_RULE_TEMPLATES:
        if template.template_id == requested:
            return template
    raise RuleTemplateError(f"Unsupported RuleTemplate id: {requested}.")


def rule_template_family_from_token(token: object) -> RuleTemplateFamily:
    if type(token) is RuleTemplateFamily:
        return token
    if type(token) is not str:
        raise RuleTemplateError("RuleTemplateFamily token must be a string.")
    try:
        return RuleTemplateFamily(token)
    except ValueError as exc:
        raise RuleTemplateError(f"Unsupported RuleTemplateFamily token: {token}.") from exc


_validate_identifier = IdentifierValidator(RuleTemplateError)


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise RuleTemplateError(f"RuleTemplate {field_name} must be a tuple.")
    if not values:
        raise RuleTemplateError(f"RuleTemplate {field_name} must not be empty.")
    return tuple(_validate_identifier(field_name, value) for value in values)


INITIAL_RULE_TEMPLATES: tuple[RuleTemplate, ...] = (
    RuleTemplate(
        template_id=KEYWORD_GATE_TEMPLATE_ID,
        family=RuleTemplateFamily.KEYWORD_GATE,
        description="Keyword-gated source, target, or eligible-unit clause.",
        canonical_patterns=("if this unit has the <keyword> keyword", "one <keyword> unit"),
    ),
    RuleTemplate(
        template_id=TIMING_WINDOW_TEMPLATE_ID,
        family=RuleTemplateFamily.TIMING_WINDOW,
        description="Start, end, phase, setup, dice-roll, and destruction timing clauses.",
        canonical_patterns=(
            "at the start of <phase>",
            "at the end of <phase>",
            "when this unit is destroyed",
        ),
    ),
    RuleTemplate(
        template_id=DISTANCE_PREDICATE_TEMPLATE_ID,
        family=RuleTemplateFamily.DISTANCE_PREDICATE,
        description="Within, wholly within, more-than, and related distance predicates.",
        canonical_patterns=("within <distance>", "more than <distance>"),
    ),
    RuleTemplate(
        template_id=SELECTED_TARGET_TEMPLATE_ID,
        family=RuleTemplateFamily.SELECTED_TARGET_CONSTRAINT,
        description="Selected friendly, enemy, this-unit, selected-unit, or player target clauses.",
        canonical_patterns=("select one friendly unit", "select one enemy unit", "that unit"),
    ),
    RuleTemplate(
        template_id=TRACKED_TARGET_SELECTION_TEMPLATE_ID,
        family=RuleTemplateFamily.TRACKED_TARGET_SELECTION,
        description=(
            "Named target selections such as prey or quarry that can be replaced when destroyed."
        ),
        canonical_patterns=(
            "select one enemy unit to be this model's prey",
            "each time this model's quarry is destroyed, select one new enemy unit",
        ),
    ),
    RuleTemplate(
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        family=RuleTemplateFamily.DICE_ROLL_MODIFICATION,
        description="Additive or subtractive dice-roll modifier clauses.",
        canonical_patterns=("add <n> to <roll> rolls", "-<n> to <roll> rolls"),
    ),
    RuleTemplate(
        template_id=DICE_ROLL_OVERRIDE_TEMPLATE_ID,
        family=RuleTemplateFamily.DICE_ROLL_OVERRIDE,
        description="Replace an eligible unmodified dice-roll result with a fixed value.",
        canonical_patterns=("change the result of one <roll> roll to an unmodified <value>",),
    ),
    RuleTemplate(
        template_id=REROLL_PERMISSION_TEMPLATE_ID,
        family=RuleTemplateFamily.REROLL_PERMISSION,
        description="Roll-specific reroll permission clauses.",
        canonical_patterns=("re-roll <roll> rolls", "reroll <roll> rolls"),
    ),
    RuleTemplate(
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        family=RuleTemplateFamily.CHARACTERISTIC_MODIFICATION,
        description="Characteristic modifier clauses.",
        canonical_patterns=("add <n> to the <characteristic> characteristic",),
    ),
    RuleTemplate(
        template_id=CHARACTERISTIC_SET_TEMPLATE_ID,
        family=RuleTemplateFamily.CHARACTERISTIC_SET,
        description="Characteristic replacement clauses.",
        canonical_patterns=(
            "models in the bearer's unit have a <characteristic> characteristic of <value>",
        ),
    ),
    RuleTemplate(
        template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
        family=RuleTemplateFamily.CONTEXTUAL_STATUS,
        description="Contextual rules-status clauses such as within a named army rule zone.",
        canonical_patterns=("that unit is within your army's <named rule>",),
    ),
    RuleTemplate(
        template_id=DESPERATE_ESCAPE_TEMPLATE_ID,
        family=RuleTemplateFamily.DESPERATE_ESCAPE_REQUIREMENT,
        description="Fall Back clauses that require Desperate Escape tests.",
        canonical_patterns=(
            "enemy unit within Engagement Range of units with this ability Falls Back",
            "models in that enemy unit must take Desperate Escape tests",
        ),
    ),
    RuleTemplate(
        template_id=RESOURCE_MODIFIER_TEMPLATE_ID,
        family=RuleTemplateFamily.RESOURCE_MODIFICATION,
        description="Command Point and Victory Point resource modification clauses.",
        canonical_patterns=("gain <n>CP", "score <n>VP"),
    ),
    RuleTemplate(
        template_id=RETURN_ON_DEATH_TEMPLATE_ID,
        family=RuleTemplateFamily.RETURN_ON_DEATH,
        description=(
            "First-destruction return effects gated by a dice roll and resolved at phase end."
        ),
        canonical_patterns=(
            "The first time this model is destroyed, at the end of the phase, roll one D6",
            "set this unit back up on the battlefield at full health",
        ),
    ),
    RuleTemplate(
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        family=RuleTemplateFamily.GRANT_ABILITY,
        description="Unit or model ability grants, usually with an explicit duration.",
        canonical_patterns=(
            "that unit gains <ability> until <endpoint>",
            "this unit is eligible to shoot in a turn in which it Fell Back",
        ),
    ),
    RuleTemplate(
        template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
        family=RuleTemplateFamily.CONDITIONAL_WEAPON_ABILITY_GRANT,
        description="Weapon ability grants attached to a selected unit or weapon scope.",
        canonical_patterns=(
            "weapons equipped by models in that unit gain <weapon ability>",
            "select one of the following abilities: <weapon ability list>; "
            "this model's <weapon name> has that ability",
        ),
    ),
    RuleTemplate(
        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
        family=RuleTemplateFamily.MOVEMENT_DISTANCE_MODIFICATION,
        description="Move characteristic and additional movement distance modifier clauses.",
        canonical_patterns=("add <n> to the Move characteristic", "move an additional <n>"),
    ),
    RuleTemplate(
        template_id=OUT_OF_PHASE_ACTION_TEMPLATE_ID,
        family=RuleTemplateFamily.OUT_OF_PHASE_ACTION,
        description="Out-of-phase action choice clauses.",
        canonical_patterns=(
            "at the end of your opponent's Movement phase select a set-up unit within <n>",
            "this model can either shoot or declare a charge without Charge bonus",
        ),
    ),
    RuleTemplate(
        template_id=PLACEMENT_TEMPLATE_ID,
        family=RuleTemplateFamily.PLACEMENT_PERMISSION_RESTRICTION,
        description="Set-up placement permissions and restrictions.",
        canonical_patterns=("can be set up", "cannot be set up"),
    ),
    RuleTemplate(
        template_id=AURA_TEMPLATE_ID,
        family=RuleTemplateFamily.AURA,
        description="Aura source, range, eligible target, and effect clauses.",
        canonical_patterns=("Aura: while a friendly unit is within <distance>",),
    ),
)
