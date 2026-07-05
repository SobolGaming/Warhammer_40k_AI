from __future__ import annotations

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.rule_templates import (
    DESPERATE_ESCAPE_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
)

from .faction_generic_ir_static_payloads_2026_27 import (
    static_characteristic_modifier_clause,
    static_duration,
    static_effect,
    static_effect_clause,
    static_grant_ability_clause,
    static_keyword_gate_clause,
    static_parameter,
    static_rule_ir_payload,
    static_target,
)

_CHAOS_DAEMONS_CAVALCADE_UNHOLY_AVALANCHE = "chaos-daemons:cavalcade-of-chaos:rule"
_CHAOS_DAEMONS_CAVALCADE_APOCALYPTIC_STEEDS = (
    "enhancement:chaos-daemons:cavalcade-of-chaos:"
    "chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade"
)
_CHAOS_DAEMONS_CAVALCADE_SOUL_SHATTERING_CHARGE = (
    "enhancement:chaos-daemons:cavalcade-of-chaos:"
    "chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade"
)
_CHAOS_DAEMONS_CAVALCADE_FROM_BEYOND_THE_VEIL = (
    "stratagem:chaos-daemons:cavalcade-of-chaos:"
    "chaos-daemons:cavalcade-of-chaos:from-beyond-the-veil"
)
_CHAOS_DAEMONS_CAVALCADE_INESCAPABLE_MANIFESTATIONS = (
    "stratagem:chaos-daemons:cavalcade-of-chaos:"
    "chaos-daemons:cavalcade-of-chaos:inescapable-manifestations"
)
_CHAOS_DAEMONS_CAVALCADE_WARP_RIDERS = (
    "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:warp-riders"
)
_CAVALCADE_TARGET_PARAMETERS = (
    static_parameter("required_keyword_sequence", ("LEGIONES_DAEMONICA", "MOUNTED")),
)
_CAVALCADE_UNHOLY_AVALANCHE_TEXT = (
    "LEGIONES DAEMONICA MOUNTED units from your army are eligible to shoot "
    "and declare a charge in a turn in which they Fell Back."
)
_CAVALCADE_APOCALYPTIC_STEEDS_TEXT = (
    "LEGIONES DAEMONICA MOUNTED model only. Add 1 to the Move characteristic "
    "of models in the bearer's unit."
)
_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT = (
    "LEGIONES DAEMONICA MOUNTED model only. After the bearer's unit makes a "
    "Charge move, when it is selected to fight, it can target enemy units "
    "within 3 inches."
)
_CAVALCADE_FROM_BEYOND_TEXT = (
    "Select one friendly LEGIONES DAEMONICA MOUNTED unit in Strategic "
    "Reserves. That unit can be set up from Strategic Reserves from the "
    "start of the battle."
)
_CAVALCADE_INESCAPABLE_TEXT = (
    "Select one friendly LEGIONES DAEMONICA MOUNTED unit engaged with the "
    "enemy unit selected to Fall Back. That enemy unit must take Desperate "
    "Escape tests."
)
_CAVALCADE_WARP_RIDERS_TEXT = (
    "Until the end of the phase, select one friendly LEGIONES DAEMONICA "
    "MOUNTED unit selected to move. That unit has MOBILE."
)

CAVALCADE_GENERIC_RULE_IR_PAYLOAD_ROWS: tuple[tuple[str, RuleIRPayload], ...] = (
    (
        _CHAOS_DAEMONS_CAVALCADE_UNHOLY_AVALANCHE,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_UNHOLY_AVALANCHE,
            normalized_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
            clauses=(
                static_grant_ability_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_UNHOLY_AVALANCHE,
                    clause_number=1,
                    source_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    target_kind="friendly_unit",
                    target_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    target_start=0,
                    target_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    target_parameters=_CAVALCADE_TARGET_PARAMETERS,
                    effect_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    effect_start=0,
                    effect_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    ability="can_fall_back_and_shoot",
                ),
                static_grant_ability_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_UNHOLY_AVALANCHE,
                    clause_number=2,
                    source_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    target_kind="friendly_unit",
                    target_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    target_start=0,
                    target_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    target_parameters=_CAVALCADE_TARGET_PARAMETERS,
                    effect_text=_CAVALCADE_UNHOLY_AVALANCHE_TEXT,
                    effect_start=0,
                    effect_end=len(_CAVALCADE_UNHOLY_AVALANCHE_TEXT),
                    ability="can_fall_back_and_charge",
                ),
            ),
            ir_hash="2ee6c8f11da305237e36129ed3d8f4e65a274d527e28c6dba6a4278741312e6d",
        ),
    ),
    (
        _CHAOS_DAEMONS_CAVALCADE_APOCALYPTIC_STEEDS,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_APOCALYPTIC_STEEDS,
            normalized_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
            clauses=(
                static_keyword_gate_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_APOCALYPTIC_STEEDS,
                    clause_number=1,
                    source_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_APOCALYPTIC_STEEDS_TEXT),
                    keyword_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
                    keyword_start=0,
                    keyword_end=len(_CAVALCADE_APOCALYPTIC_STEEDS_TEXT),
                    required_keywords=("LEGIONES_DAEMONICA", "MOUNTED"),
                ),
                static_characteristic_modifier_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_APOCALYPTIC_STEEDS,
                    clause_number=2,
                    source_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_APOCALYPTIC_STEEDS_TEXT),
                    target_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
                    target_start=0,
                    target_end=len(_CAVALCADE_APOCALYPTIC_STEEDS_TEXT),
                    target_parameters=_CAVALCADE_TARGET_PARAMETERS,
                    effect_text=_CAVALCADE_APOCALYPTIC_STEEDS_TEXT,
                    effect_start=0,
                    effect_end=len(_CAVALCADE_APOCALYPTIC_STEEDS_TEXT),
                    characteristic="movement",
                    delta=1,
                ),
            ),
            ir_hash="85f5ad8a5ea1914af21197ba4655e888a4c296cd0063ee86b7142fd20bf648bf",
        ),
    ),
    (
        _CHAOS_DAEMONS_CAVALCADE_SOUL_SHATTERING_CHARGE,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_SOUL_SHATTERING_CHARGE,
            normalized_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
            clauses=(
                static_keyword_gate_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_SOUL_SHATTERING_CHARGE,
                    clause_number=1,
                    source_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT),
                    keyword_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
                    keyword_start=0,
                    keyword_end=len(_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT),
                    required_keywords=("LEGIONES_DAEMONICA", "MOUNTED"),
                ),
                static_grant_ability_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_SOUL_SHATTERING_CHARGE,
                    clause_number=2,
                    source_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT),
                    target_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
                    target_start=0,
                    target_end=len(_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT),
                    target_parameters=_CAVALCADE_TARGET_PARAMETERS,
                    effect_text=_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT,
                    effect_start=0,
                    effect_end=len(_CAVALCADE_SOUL_SHATTERING_CHARGE_TEXT),
                    ability="fight_activation_melee_targeting_distance",
                    effect_parameters=(
                        static_parameter("model_proximity_inches", 3.0),
                        static_parameter("requires_charge_move", True),
                    ),
                ),
            ),
            ir_hash="e02ec5fded238e676f232dbab74c9d3444aa205796f3cb889fe650d2e76fd57c",
        ),
    ),
    (
        _CHAOS_DAEMONS_CAVALCADE_FROM_BEYOND_THE_VEIL,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_FROM_BEYOND_THE_VEIL,
            normalized_text=_CAVALCADE_FROM_BEYOND_TEXT,
            clauses=(
                static_effect_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_FROM_BEYOND_THE_VEIL,
                    clause_number=1,
                    template_id=PLACEMENT_TEMPLATE_ID,
                    source_text=_CAVALCADE_FROM_BEYOND_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_FROM_BEYOND_TEXT),
                    target=static_target(
                        "friendly_unit",
                        _CAVALCADE_FROM_BEYOND_TEXT,
                        0,
                        len(_CAVALCADE_FROM_BEYOND_TEXT),
                        parameters=_CAVALCADE_TARGET_PARAMETERS,
                    ),
                    effect=static_effect(
                        "placement_permission",
                        _CAVALCADE_FROM_BEYOND_TEXT,
                        0,
                        len(_CAVALCADE_FROM_BEYOND_TEXT),
                        [
                            static_parameter("placement_kind", "strategic_reserves"),
                            static_parameter("from_start_of_battle", True),
                            static_parameter("placement_scope", "strategic_reserves_only"),
                            static_parameter("mark_movement_phase_reinforcement_arrival", True),
                        ],
                    ),
                ),
            ),
            ir_hash="dff6e19387978ed24125be5a98b472b358440357d4a4b0239bc9731c7760fd84",
        ),
    ),
    (
        _CHAOS_DAEMONS_CAVALCADE_INESCAPABLE_MANIFESTATIONS,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_INESCAPABLE_MANIFESTATIONS,
            normalized_text=_CAVALCADE_INESCAPABLE_TEXT,
            clauses=(
                static_effect_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_INESCAPABLE_MANIFESTATIONS,
                    clause_number=1,
                    template_id=DESPERATE_ESCAPE_TEMPLATE_ID,
                    source_text=_CAVALCADE_INESCAPABLE_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_INESCAPABLE_TEXT),
                    target=static_target(
                        "friendly_unit",
                        _CAVALCADE_INESCAPABLE_TEXT,
                        0,
                        len(_CAVALCADE_INESCAPABLE_TEXT),
                        parameters=_CAVALCADE_TARGET_PARAMETERS,
                    ),
                    effect=static_effect(
                        "force_desperate_escape_tests",
                        _CAVALCADE_INESCAPABLE_TEXT,
                        0,
                        len(_CAVALCADE_INESCAPABLE_TEXT),
                        [
                            static_parameter("required_fall_back_mode", "desperate_escape"),
                            static_parameter("target_scope", "falling_back_unit"),
                        ],
                    ),
                ),
            ),
            ir_hash="8679e68c3c72b52ce78c760169555a0557e965b5975e849e90b9ab88828bbfa0",
        ),
    ),
    (
        _CHAOS_DAEMONS_CAVALCADE_WARP_RIDERS,
        static_rule_ir_payload(
            source_row_id=_CHAOS_DAEMONS_CAVALCADE_WARP_RIDERS,
            normalized_text=_CAVALCADE_WARP_RIDERS_TEXT,
            clauses=(
                static_grant_ability_clause(
                    source_row_id=_CHAOS_DAEMONS_CAVALCADE_WARP_RIDERS,
                    clause_number=1,
                    source_text=_CAVALCADE_WARP_RIDERS_TEXT,
                    source_start=0,
                    source_end=len(_CAVALCADE_WARP_RIDERS_TEXT),
                    target_kind="friendly_unit",
                    target_text=_CAVALCADE_WARP_RIDERS_TEXT,
                    target_start=0,
                    target_end=len(_CAVALCADE_WARP_RIDERS_TEXT),
                    target_parameters=_CAVALCADE_TARGET_PARAMETERS,
                    effect_text=_CAVALCADE_WARP_RIDERS_TEXT,
                    effect_start=0,
                    effect_end=len(_CAVALCADE_WARP_RIDERS_TEXT),
                    ability="MOBILE",
                    duration=static_duration(
                        "until_timing_endpoint",
                        _CAVALCADE_WARP_RIDERS_TEXT,
                        0,
                        len(_CAVALCADE_WARP_RIDERS_TEXT),
                        (static_parameter("endpoint", "phase"),),
                    ),
                ),
            ),
            ir_hash="0a7d9558a6fb1f8c8ee3ea4b778fb1fad496ce32194972e7d9131b34dc7c4830",
        ),
    ),
)
