from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.weapon_profiles import canonical_weapon_keyword_tokens
from warhammer40k_core.rules.attack_target_parser import (
    has_this_model_attack_target,
    parse_this_model_attack_target_conditions,
    parse_this_model_attack_target_trigger,
    this_model_attack_target_match_ranges,
)
from warhammer40k_core.rules.hit_success_threshold_parser import (
    has_hit_success_threshold,
    hit_success_threshold_effects,
)
from warhammer40k_core.rules.parsed_tokens import DistancePredicateToken, ParsedRuleText, TextSpan
from warhammer40k_core.rules.rule_characteristic_parser import (
    parse_characteristic_effects as _parse_characteristic_effects,
)
from warhammer40k_core.rules.rule_clause_merging import merge_rule_clause_spans
from warhammer40k_core.rules.rule_duration_parser import parse_rule_duration
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRError,
    RuleParameterValue,
    RuleParseDiagnostic,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_keyword_sequences import (
    keyword_sequence_parameter_pairs as _keyword_sequence_parameter_pairs,
)
from warhammer40k_core.rules.rule_keyword_sequences import (
    keyword_sequence_tokens as _keyword_sequence_tokens,
)
from warhammer40k_core.rules.rule_templates import (
    AURA_TEMPLATE_ID,
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CHARACTERISTIC_SET_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    DESPERATE_ESCAPE_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    DISTANCE_PREDICATE_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    OUT_OF_PHASE_ACTION_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    RESOURCE_MODIFIER_TEMPLATE_ID,
    RETURN_ON_DEATH_TEMPLATE_ID,
    SELECTED_TARGET_TEMPLATE_ID,
    TIMING_WINDOW_TEMPLATE_ID,
    TRACKED_TARGET_SELECTION_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
    rule_template_by_id,
)
from warhammer40k_core.rules.rule_token_normalization import (
    keyword_any_tokens as _keyword_any_tokens,
)
from warhammer40k_core.rules.rule_token_normalization import (
    keyword_list_tokens as _keyword_list_tokens,
)
from warhammer40k_core.rules.rule_token_normalization import (
    model_keyword_any_token as _model_keyword_any_token,
)
from warhammer40k_core.rules.rule_token_normalization import (
    movement_modes_token as _movement_modes_token,
)
from warhammer40k_core.rules.selected_target_parser import (
    is_structural_target_keyword,
    selected_target_spec_from_text,
)
from warhammer40k_core.rules.setup_reactive_parser import (
    compile_setup_reactive_shoot_charge_clause,
)

RULE_PARSER_VERSION = "phase17c-rule-parser-v1"

_PHASES = "command|movement|shooting|charge|fight"
_ROLL_TYPES = (
    "advance|battle-shock|charge|critical hit|critical wound|damage|desperate escape|"
    "feel no pain|hazardous|hit|invulnerable save|leadership|save|wound"
)
_TIMING_OWNER_PATTERN = r"your\s+opponent's|the\s+opponent's|opponent's|your|the"
_START_END_PHASE_RE = re.compile(
    rf"\bat\s+the\s+(?P<edge>start|end)\s+of\s+"
    rf"(?:(?P<owner>{_TIMING_OWNER_PATTERN})\s+)?(?P<phase>{_PHASES})\s+phase\b",
    re.IGNORECASE,
)
_START_END_TURN_RE = re.compile(
    r"\bat\s+the\s+(?P<edge>start|end)\s+of\s+"
    rf"(?P<owner>{_TIMING_OWNER_PATTERN})\s+turn\b",
    re.IGNORECASE,
)
_BATTLE_ROUND_ORDINAL_PATTERN = r"first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)?"
_START_END_BATTLE_ROUND_RE = re.compile(
    r"\bat\s+the\s+(?P<edge>start|end)\s+of\s+the\s+"
    rf"(?P<ordinal>{_BATTLE_ROUND_ORDINAL_PATTERN})\s+battle\s+round\b",
    re.IGNORECASE,
)
_IN_PHASE_RE = re.compile(
    rf"\b(?:in|during)\s+(?:(?P<owner>{_TIMING_OWNER_PATTERN})\s+)?"
    rf"(?P<phase>{_PHASES})\s+phase\b",
    re.IGNORECASE,
)
_IN_TURN_RE = re.compile(
    rf"\b(?:in|during)\s+(?P<owner>{_TIMING_OWNER_PATTERN})\s+turn\b",
    re.IGNORECASE,
)
_DESTROYED_UNIT_RE = re.compile(r"\bwhen\s+this\s+unit\s+is\s+destroyed\b", re.IGNORECASE)
_FIRST_DEATH_RETURN_TRIGGER_RE = re.compile(
    r"\bthe\s+first\s+time\s+(?P<target>this\s+model|this\s+unit)\s+is\s+destroyed,\s+"
    r"at\s+the\s+end\s+of\s+the\s+phase\b",
    re.IGNORECASE,
)
_RETURN_ON_DEATH_ROLL_GATE_RE = re.compile(
    r"\broll\s+(?:(?P<roll_count>one|a|an|\d+)\s+)?"
    r"(?P<roll_expression>(?:\d+)?D\d+(?:[+-]\d+)?)\s*:\s*"
    r"on\s+a\s+(?P<success_threshold>\d+)\+(?=[\s,.;)]|$)",
    re.IGNORECASE,
)
_RETURN_ON_DEATH_SET_UP_RE = re.compile(
    r"\bset\s+(?P<target>this\s+model|this\s+unit)\s+back\s+up\s+on\s+the\s+battlefield\s+"
    r"as\s+close\s+as\s+possible\s+to\s+where\s+it\s+was\s+destroyed\s+and\s+"
    r"not\s+within\s+Engagement\s+Range\s+of\s+one\s+or\s+more\s+enemy\s+units,\s+"
    r"(?:(?:with\s+(?P<wounds_remaining>\d+)\s+wounds?\s+remaining)|"
    r"(?P<full_health>at\s+full\s+health))\b",
    re.IGNORECASE,
)
_THIS_MODEL_MELEE_ATTACK_TARGET_RE = re.compile(
    r"\beach\s+time\s+this\s+model\s+makes\s+a\s+melee\s+attack\s+that\s+targets\s+"
    r"(?:a|an)\s+(?P<keyword>Character\s+or\s+Monster)\s+unit\b",
    re.IGNORECASE,
)
_THIS_MODEL_DESTROYS_ENEMY_KEYWORD_UNIT_RE = re.compile(
    r"\beach\s+time\s+this\s+model\s+destroys\s+an\s+enemy\s+"
    r"(?P<keyword>Character\s+or\s+Monster)\s+unit\b",
    re.IGNORECASE,
)
_TRACKED_TARGET_ROLE_PATTERN = "prey|quarry"
_TRACKED_TARGET_SELECTION_RE = re.compile(
    r"\bselect\s+one\s+(?P<replacement>new\s+)?(?P<allegiance>enemy|friendly)\s+unit\s+"
    r"to\s+be\s+(?P<owner>this\s+model|this\s+unit)'s\s+"
    rf"(?P<role>{_TRACKED_TARGET_ROLE_PATTERN})\b",
    re.IGNORECASE,
)
_TRACKED_TARGET_ATTACK_RE = re.compile(
    r"\beach\s+time\s+(?P<actor>this\s+model|a\s+model\s+in\s+this\s+model's\s+unit)\s+"
    r"makes\s+a\s+(?P<attack_kind>melee|ranged)\s+attack\s+that\s+targets\s+its\s+"
    rf"(?P<role>{_TRACKED_TARGET_ROLE_PATTERN})\b",
    re.IGNORECASE,
)
_TRACKED_TARGET_DESTROYED_RE = re.compile(
    r"\beach\s+time\s+(?P<owner>this\s+model|this\s+unit)'s\s+"
    rf"(?P<role>{_TRACKED_TARGET_ROLE_PATTERN})\s+is\s+destroyed\b",
    re.IGNORECASE,
)
_DESTROYED_MODEL_RE = re.compile(r"\bwhen\s+.*\bmodel\s+is\s+destroyed\b", re.IGNORECASE)
_CHARGE_MOVE_END_RE = re.compile(
    r"\b(?:each\s+time|when)\s+(?P<subject>that\s+unit|this\s+unit|a\s+unit)\s+ends\s+"
    r"a\s+charge\s+move\b",
    re.IGNORECASE,
)
_THIS_MODEL_NORMAL_OR_ADVANCE_MOVE_RE = re.compile(
    r"\beach\s+time\s+this\s+model\s+makes\s+a\s+"
    r"(?P<modes>Normal(?:\s+or\s+Advance)?|Advance(?:\s+or\s+Normal)?)\s+move\b",
    re.IGNORECASE,
)
_THIS_UNIT_NORMAL_ADVANCE_FALL_BACK_MOVE_RE = re.compile(
    r"\beach\s+time\s+this\s+unit\s+makes\s+a\s+"
    r"(?P<modes>(?:Normal|Advance|Fall\s+Back)"
    r"(?:(?:\s*,\s*|\s+or\s+|\s+and\s+)(?:Normal|Advance|Fall\s+Back))*)"
    r"\s+move\b",
    re.IGNORECASE,
)
_ENEMY_UNIT_FALLS_BACK_NEAR_ABILITY_RE = re.compile(
    r"\beach\s+time\s+an?\s+enemy\s+unit"
    r"(?:\s+\(excluding\s+(?P<excluded_keywords>[^)]+)\))?\s+"
    r"(?:that\s+is\s+)?"
    r"within\s+Engagement\s+Range\s+of\s+one\s+or\s+more\s+units\s+from\s+your\s+army\s+"
    r"with\s+this\s+ability\s+(?:Falls\s+Back|is\s+selected\s+to\s+Fall\s+Back)\b",
    re.IGNORECASE,
)
_POST_SHOOT_HIT_TARGET_SELECTION_RE = re.compile(
    r"\b(?:(?:(?:in|during)\s+your\s+Shooting\s+phase,\s*)?"
    r"(?:(?:after|each\s+time)\s+)?"
    r"(?P<subject>this\s+model|this\s+unit|the\s+bearer|bearer)\s+has\s+shot,\s+"
    r")?"
    r"select\s+one\s+enemy\s+unit\s+(?:that\s+was\s+)?hit\s+by\s+one\s+or\s+more\s+of\s+"
    r"those\s+attacks\b",
    re.IGNORECASE,
)
_WHEN_DOING_SO_RE = re.compile(r"\bwhen\s+doing\s+so\b", re.IGNORECASE)
_SETUP_RE = re.compile(r"\b(?:deployment|before\s+the\s+battle|set\s+up)\b", re.IGNORECASE)
_DICE_TRIGGER_RE = re.compile(
    rf"\b(?:after|when|each\s+time)\s+.*\b(?P<roll>{_ROLL_TYPES})\s+roll", re.IGNORECASE
)
_ONCE_PER_RE = re.compile(
    r"\bonce\s+per\s+(?P<scope>phase|turn|battle|battle round)\b", re.IGNORECASE
)
_AURA_RE = re.compile(r"(?:\bAura\b|^\s*Aura\s*:)", re.IGNORECASE)
_LEADING_UNIT_RE = re.compile(
    r"\bwhile\s+this\s+model\s+is\s+leading\s+a\s+unit\b",
    re.IGNORECASE,
)
_TARGET_RE = re.compile(
    r"\b(?:select\s+)?(?:one\s+)?(?:new\s+)?(?P<allegiance>friendly|enemy)\s+"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?:model|unit)\b",
    re.IGNORECASE,
)
_THIS_UNIT_RE = re.compile(r"\bthis\s+unit\b", re.IGNORECASE)
_THIS_MODEL_RE = re.compile(r"\bthis\s+model\b", re.IGNORECASE)
_THIS_MODEL_UNIT_RE = re.compile(
    r"\b(?:a\s+)?models?\s+in\s+this\s+model's\s+unit\b",
    re.IGNORECASE,
)
_BEARER_APOSTROPHE_RE = r"'?"
_BEARERS_UNIT_RE = re.compile(
    rf"\b(?:models\s+in\s+)?(?:the\s+)?bearer{_BEARER_APOSTROPHE_RE}s\s+unit\b|"
    rf"\bmade\s+for\s+(?:the\s+)?bearer{_BEARER_APOSTROPHE_RE}s\s+unit\b",
    re.IGNORECASE,
)
_BEARER_MODEL_RE = re.compile(
    r"\b(?:the\s+)?bearer\b|\bmade\s+for\s+(?:the\s+)?bearer\b",
    re.IGNORECASE,
)
_THAT_UNIT_RE = re.compile(r"\b(?:that|selected|target)\s+unit\b", re.IGNORECASE)
_PLAYER_RE = re.compile(r"\b(?:you|that\s+player|the\s+player)\b", re.IGNORECASE)
_RESOURCE_TARGET_RE = re.compile(
    r"\b(?:gain|score|add|spend|lose|remove|refund)\s+\d+\s*"
    r"(?:CP|VP|Command Points?|Command point|Victory Points?)\b",
    re.IGNORECASE,
)
_HAS_KEYWORD_RE = re.compile(
    r"\b(?:has|have|with)\s+the\s+(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})"
    r"\s+keyword\b"
)
_KEYWORD_UNIT_RE = re.compile(
    r"\b(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+(?:model|unit)\b"
)
_ADD_ROLL_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)\s+(?:to|from)\s+"
    rf"(?:(?:the|each\s+of\s+those|each\s+of\s+these)\s+)?"
    rf"(?P<roll>{_ROLL_TYPES})\s+(?:rolls?|tests?)\b",
    re.IGNORECASE,
)
_SIGNED_ROLL_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<sign>[+-])(?P<value>\d+)\s+to\s+"
    rf"(?:(?:the|each\s+of\s+those|each\s+of\s+these)\s+)?"
    rf"(?P<roll>{_ROLL_TYPES})\s+(?:rolls?|tests?)\b",
    re.IGNORECASE,
)
_REROLL_ROLL_LIST_RE = re.compile(
    rf"\b(?:(?:you\s+)?can\s+)?(?:re-roll|reroll)\s+"
    rf"(?:the\s+)?(?P<rolls>(?:{_ROLL_TYPES})(?:\s*,\s*|\s+and\s+)"
    rf"(?:{_ROLL_TYPES})(?:(?:\s*,\s*|\s+and\s+)(?:{_ROLL_TYPES}))*)\s+rolls?\b"
    r"(?:\s+made\s+for\s+(?:this|that|selected|target)\s+(?:unit|model))?",
    re.IGNORECASE,
)
_REROLL_RE = re.compile(
    rf"\b(?:(?:you\s+)?can\s+)?(?:re-roll|reroll)\s+"
    rf"(?:an?\s+|the\s+)?(?P<roll>{_ROLL_TYPES})\s+rolls?\b"
    r"(?:\s+of\s+(?P<reroll_value>[1-6]))?"
    r"(?:\s+made\s+for\s+(?:this|that|selected|target)\s+(?:unit|model))?",
    re.IGNORECASE,
)
_OBJECTIVE_REROLL_INSTEAD_RE = re.compile(
    r"\bif\s+the\s+target\s+of\s+that\s+attack\s+is\s+within\s+range\s+of\s+"
    r"an?\s+objective\s+marker,\s+you\s+can\s+(?:re-roll|reroll)\s+"
    r"(?:the\s+)?(?P<roll>hit|wound|damage|save)\s+roll\s+instead\b",
    re.IGNORECASE,
)
_SELECTED_UNIT_MAKES_ATTACK_RE = re.compile(
    r"\b(?:a\s+model|models?)\s+in\s+"
    r"(?:that\s+enemy\s+unit|that\s+unit|selected\s+unit|target\s+unit)\s+"
    r"makes?\s+an?\s+attack\b",
    re.IGNORECASE,
)
_CP_RE = re.compile(
    r"\b(?P<verb>gain|add|refund|spend|lose|remove)\s+(?P<value>\d+)\s*"
    r"(?:CP|Command Points?|Command point)\b",
    re.IGNORECASE,
)
_VP_RE = re.compile(
    r"\b(?P<verb>score|gain|add)\s+(?P<value>\d+)\s*(?:VP|Victory Points?)\b",
    re.IGNORECASE,
)
_GRANT_ABILITY_RE = re.compile(
    r"\b(?:gains?|have|has)\s+(?P<ability>[A-Z][A-Za-z0-9 -]*(?:\s+\d+)?)\s+until\b",
    re.IGNORECASE,
)
_CHARGE_ELIGIBILITY_AFTER_MOVE_RE = re.compile(
    r"\b(?:(?:this|that|selected|target)\s+unit\s+)?"
    r"(?:is\s+)?eligible\s+to\s+declare\s+a\s+charge\s+in\s+a\s+turn\s+"
    r"in\s+which\s+(?:it|this\s+unit|that\s+unit|the\s+unit)\s+"
    r"(?P<movement>Advanced|Fell\s+Back)\b",
    re.IGNORECASE,
)
_SHOOT_ELIGIBILITY_AFTER_FALL_BACK_RE = re.compile(
    r"\b(?:(?:this|that|selected|target)\s+unit\s+)?"
    r"(?:is\s+)?eligible\s+to\s+shoot\s+in\s+a\s+turn\s+"
    r"in\s+which\s+(?:it|this\s+unit|that\s+unit|the\s+unit)\s+Fell\s+Back\b",
    re.IGNORECASE,
)
_FEEL_NO_PAIN_ABILITY_RE = re.compile(
    r"\b(?:gains?|have|has)\s+(?:the\s+)?Feel\s+No\s+Pain\s+"
    r"(?P<threshold>[2-6])\+\s+ability"
    r"(?:\s+against\s+(?P<qualifier>"
    r"Psychic\s+Attacks?(?:\s+and\s+mortal\s+wounds)?"
    r"))?\b",
    re.IGNORECASE,
)
_SHADOW_OF_CHAOS_STATUS_RE = re.compile(
    r"\b(?:that|selected|target)\s+unit\s+is\s+within\s+your\s+"
    r"army's\s+Shadow\s+of\s+Chaos\b",
    re.IGNORECASE,
)
_CONTEXTUAL_STATUS_DENIAL_RE = re.compile(
    r"\b(?P<subject>"
    r"that\s+enemy\s+unit|that\s+unit|selected\s+unit|target\s+unit|"
    r"models\s+in\s+that\s+enemy\s+unit|models\s+in\s+that\s+unit|"
    r"models\s+in\s+the\s+selected\s+unit|models\s+in\s+the\s+target\s+unit"
    r")\s+cannot\s+have\s+(?:the\s+)?"
    r"(?P<status>[A-Z][A-Za-z0-9 +'_-]+?)(?=\s*(?:\.|,|;|$))",
    re.IGNORECASE,
)
_TARGET_BATTLE_SHOCKED_RE = re.compile(
    r"\bif\s+(?P<subject>that\s+enemy\s+unit|that\s+unit|target\s+unit|selected\s+unit)\s+"
    r"is\s+(?:also\s+)?Battle-shocked\b",
    re.IGNORECASE,
)
_DESPERATE_ESCAPE_TESTS_RE = re.compile(
    r"\bmodels\s+in\s+(?:that\s+enemy|that|the\s+target|the\s+selected)\s+unit\s+"
    r"must\s+take\s+Desperate\s+Escape\s+tests\b",
    re.IGNORECASE,
)
_MOVE_OVER_FRIENDLY_MONSTER_VEHICLE_AND_TERRAIN_RE = re.compile(
    r"\bit\s+can\s+move\s+over\s+friendly\s+"
    r"(?P<first_model_keyword>Monster|Vehicle)\s+and\s+"
    r"(?P<second_model_keyword>Monster|Vehicle)\s+models\s+and\s+"
    r"terrain\s+features\s+that\s+are\s+"
    r"(?P<height>\d+(?:\.\d+)?)(?:\")?\s+or\s+less\s+in\s+height\s+"
    r"as\s+if\s+they\s+were\s+not\s+there\b",
    re.IGNORECASE,
)
_MOVE_THROUGH_MODELS_AND_TERRAIN_RE = re.compile(
    r"\bit\s+can\s+move\s+through\s+models"
    r"(?:\s+\(excluding\s+(?P<excluded_model_keywords>[^)]+)\))?"
    r"\s+and\s+terrain\s+features\b",
    re.IGNORECASE,
)
_MOVE_THROUGH_ENGAGEMENT_AUTO_PASS_RE = re.compile(
    r"\bwhen\s+doing\s+so,\s+it\s+can\s+move\s+within\s+Engagement\s+Range\s+of\s+"
    r"enemy\s+models,\s+but\s+cannot\s+end\s+that\s+move\s+within\s+Engagement\s+"
    r"Range\s+of\s+them,\s+and\s+any\s+Desperate\s+Escape\s+test\s+is\s+"
    r"automatically\s+passed\b",
    re.IGNORECASE,
)
_WEAPON_KEYWORD_PATTERN = "|".join(
    re.escape(keyword)
    for keyword in sorted(canonical_weapon_keyword_tokens(), key=len, reverse=True)
)
_WEAPON_ABILITY_VALUE_PATTERN = r"D3|\d+"
_ABILITY_CHOICE_PREFIX_RE = re.compile(
    r"\bselect\s+one\s+of\s+the\s+following\s+abilities\s*:",
    re.IGNORECASE,
)
_WEAPON_ABILITY_CHOICE_TOKEN_RE = re.compile(
    rf"\[\s*(?P<ability>{_WEAPON_KEYWORD_PATTERN})"
    rf"(?:\s+(?P<ability_value>{_WEAPON_ABILITY_VALUE_PATTERN}))?\s*\]",
    re.IGNORECASE,
)
_NAMED_WEAPON_ABILITY_CHOICE_RE = re.compile(
    r"\bselect\s+one\s+of\s+the\s+following\s+abilities\s*:\s+(?P<abilities>.+?)\.\s+"
    r"Until\s+the\s+end\s+of\s+the\s+(?:phase|turn|battle\s+round|battle),\s+"
    r"(?P<target_scope>this\s+model|this\s+unit|that\s+unit|selected\s+unit)'?s\s+"
    r"(?P<weapon_names>.+?)\s+(?:has|have)\s+that\s+ability\b",
    re.IGNORECASE | re.DOTALL,
)
_WEAPON_ABILITY_RE = re.compile(
    rf"\b(?P<weapon_scope>(?:all\s+)?weapons?|ranged\s+weapons?|melee\s+weapons?)"
    rf".{{0,100}}\b(?:gain|gains|have|has)\s+"
    rf"(?:the\s+)?\[?(?P<ability>{_WEAPON_KEYWORD_PATTERN})"
    rf"(?:\s+(?P<ability_value>{_WEAPON_ABILITY_VALUE_PATTERN}))?\]?"
    rf"(?:\s+ability)?\b",
    re.IGNORECASE,
)
_NAMED_WEAPON_ABILITY_RE = re.compile(
    rf"\b(?P<weapon_name>[A-Z][A-Za-z0-9 ':-]+?)\s+equipped\s+by\s+models\s+"
    rf"in\s+(?:that|this|the\s+selected)\s+unit\s+(?:gain|gains|have|has)\s+"
    rf"(?:the\s+)?\[?(?P<ability>{_WEAPON_KEYWORD_PATTERN})"
    rf"(?:\s+(?P<ability_value>{_WEAPON_ABILITY_VALUE_PATTERN}))?\]?"
    rf"(?:\s+ability)?\b",
    re.IGNORECASE,
)
_PLACEMENT_PERMISSION_RE = re.compile(r"\bcan\s+be\s+set\s+up\b", re.IGNORECASE)
_PLACEMENT_RESTRICTION_RE = re.compile(
    r"\b(?:cannot|can't|can\s+only)\s+be\s+set\s+up\b",
    re.IGNORECASE,
)
_REMOVE_TO_STRATEGIC_RESERVES_RE = re.compile(
    r"\b(?:you\s+can\s+)?remove\s+it\s+from\s+the\s+battlefield\s+and\s+"
    r"place\s+it\s+into\s+Strategic\s+Reserves\b",
    re.IGNORECASE,
)
_RESTORE_LOST_WOUNDS_RE = re.compile(
    r"\bthis\s+model\s+regains\s+up\s+to\s+(?P<amount>D6|D3|\d+)\s+lost\s+wounds\b",
    re.IGNORECASE,
)
_PER_MODEL_MORTAL_WOUNDS_RE = re.compile(
    r"\broll\s+(?:(?P<roll_count>one|a|an|\d+)\s+)?"
    r"(?P<roll_expression>(?:\d+)?D\d+(?:[+-]\d+)?)\s+for\s+each\s+model\s+"
    r"in\s+this\s+unit:\s+for\s+each\s+(?P<success_threshold>[2-6])\+,\s+"
    r"(?P<target>that\s+enemy\s+unit|that\s+unit|selected\s+unit|target\s+unit)\s+"
    r"suffers\s+(?P<mortal_wounds>D6|D3|\d+)\s+mortal\s+wounds\b",
    re.IGNORECASE,
)
_DISTANCE_RELATION_RE = re.compile(
    r"\b(?:(?P<subject>this\s+unit|this\s+model|that\s+unit|selected\s+unit|"
    r"target\s+unit)\s+is\s+)?"
    r"(?P<negated>not\s+)?"
    r"(?P<predicate>wholly\s+within|within)\s+"
    r"(?P<range>Engagement\s+Range|Objective\s+Marker\s+Range|\d+(?:\.\d+)?\")\s+"
    r"of\s+"
    r"(?:(?P<quantity>one\s+or\s+more|any|a|an)\s+)?"
    r"(?:(?P<allegiance>enemy|friendly)\s+)?"
    r"(?:(?P<object_reference>this|that|selected|target)\s+)?"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?P<object_kind>units?|models?|objective\s+markers?)"
    r"(?:\s+from\s+(?P<object_owner>your\s+army)"
    r"(?:\s+with\s+(?P<object_ability_scope>this\s+ability))?)?\b",
    re.IGNORECASE,
)
_RESIDUAL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+'-]*")
_RESIDUAL_CONNECTOR_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "are",
        "away",
        "be",
        "by",
        "can",
        "cannot",
        "each",
        "enemies",
        "enemy",
        "equipped",
        "every",
        "for",
        "friendly",
        "from",
        "has",
        "have",
        "if",
        "in",
        "into",
        "is",
        "its",
        "melee",
        "model",
        "models",
        "of",
        "on",
        "one",
        "only",
        "opponent",
        "opponents",
        "or",
        "phase",
        "player",
        "ranged",
        "select",
        "selected",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "towards",
        "turn",
        "unit",
        "units",
        "weapon",
        "weapons",
        "when",
        "while",
        "with",
        "within",
        "without",
        "your",
    }
)
_CLAUSE_TRIGGER_ANCHOR_RE = re.compile(
    r"\b(?:each\s+time|when|after|at\s+the\s+(?:start|end)\s+of)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _RuleParserContext:
    source_keyword_sequence_parts: tuple[str, ...]


def _validate_source_keyword_sequence_parts(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise RuleIRError("Rule parser source_keyword_sequence_parts must be a tuple.")
    if not value:
        raise RuleIRError("Rule parser source_keyword_sequence_parts must not be empty.")
    parts: list[str] = []
    for raw_part in cast(tuple[object, ...], value):
        if type(raw_part) is not str:
            raise RuleIRError("Rule parser source_keyword_sequence_parts must contain strings.")
        canonical = " ".join(raw_part.strip().upper().replace("-", " ").split())
        if not canonical:
            raise RuleIRError(
                "Rule parser source_keyword_sequence_parts must not contain empty strings."
            )
        if canonical != raw_part:
            raise RuleIRError(
                "Rule parser source_keyword_sequence_parts must contain canonical uppercase "
                "source keyword sequences."
            )
        parts.append(canonical)
    if len(set(parts)) != len(parts):
        raise RuleIRError("Rule parser source_keyword_sequence_parts must not duplicate values.")
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class _ClauseText:
    span: TextSpan

    @property
    def text(self) -> str:
        return self.span.text

    @property
    def start(self) -> int:
        return self.span.start


def parse_rule_ir(
    *,
    source_id: str,
    parsed_text: ParsedRuleText,
    source_keyword_sequence_parts: tuple[str, ...],
    rule_id: str | None = None,
) -> RuleIR:
    if type(source_id) is not str or not source_id.strip():
        raise RuleIRError("Rule parser source_id must be a non-empty string.")
    if type(parsed_text) is not ParsedRuleText:
        raise RuleIRError("Rule parser parsed_text must be ParsedRuleText.")
    parser_context = _RuleParserContext(
        source_keyword_sequence_parts=_validate_source_keyword_sequence_parts(
            source_keyword_sequence_parts
        )
    )
    compiled_clauses = tuple(
        _compile_clause(
            source_id=source_id.strip(),
            clause_index=index,
            clause_text=clause_text,
            parsed_text=parsed_text,
            parser_context=parser_context,
        )
        for index, clause_text in enumerate(
            _split_clause_text(parsed_text.normalized_text), start=1
        )
    )
    return RuleIR(
        rule_id=source_id.strip() if rule_id is None else rule_id,
        source_id=source_id.strip(),
        normalized_text=parsed_text.normalized_text,
        parser_version=RULE_PARSER_VERSION,
        clauses=compiled_clauses,
        diagnostics=tuple(
            diagnostic for clause in compiled_clauses for diagnostic in clause.diagnostics
        ),
    )


def _split_clause_text(normalized_text: str) -> tuple[_ClauseText, ...]:
    coarse_clauses: list[_ClauseText] = []
    start = 0
    for index, character in enumerate(normalized_text):
        if character not in {"\n", ";", "."}:
            continue
        if character == ";" and _semicolon_inside_ability_choice_list(
            normalized_text=normalized_text,
            start=start,
            index=index,
        ):
            continue
        if (
            character == "."
            and index + 1 < len(normalized_text)
            and not normalized_text[index + 1].isspace()
        ):
            continue
        split_end = index + 1 if character == "." else index
        _append_clause_span(
            clauses=coarse_clauses,
            normalized_text=normalized_text,
            start=start,
            end=split_end,
        )
        start = index + 1
    _append_clause_span(
        clauses=coarse_clauses,
        normalized_text=normalized_text,
        start=start,
        end=len(normalized_text),
    )
    clauses = [
        split_clause
        for coarse_clause in coarse_clauses
        for split_clause in _split_repeated_trigger_anchors(coarse_clause)
    ]
    clauses = [
        _ClauseText(span=span)
        for span in merge_rule_clause_spans(
            normalized_text,
            tuple(clause.span for clause in clauses),
        )
    ]
    if not clauses:
        full_span = TextSpan(text=normalized_text, start=0, end=len(normalized_text))
        return (_ClauseText(span=full_span),)
    return tuple(clauses)


def _semicolon_inside_ability_choice_list(
    *,
    normalized_text: str,
    start: int,
    index: int,
) -> bool:
    segment = normalized_text[start:index]
    return _ABILITY_CHOICE_PREFIX_RE.search(segment) is not None and "." not in segment


def _split_repeated_trigger_anchors(clause_text: _ClauseText) -> tuple[_ClauseText, ...]:
    anchors = tuple(_CLAUSE_TRIGGER_ANCHOR_RE.finditer(clause_text.text))
    if len(anchors) < 2:
        return (clause_text,)
    clauses: list[_ClauseText] = []
    start = clause_text.span.start
    for anchor in anchors[1:]:
        split_at = clause_text.span.start + anchor.start()
        _append_clause_span(
            clauses=clauses,
            normalized_text=clause_text.span.text,
            start=start - clause_text.span.start,
            end=split_at - clause_text.span.start,
        )
        start = split_at
    _append_clause_span(
        clauses=clauses,
        normalized_text=clause_text.span.text,
        start=start - clause_text.span.start,
        end=clause_text.span.end - clause_text.span.start,
    )
    return tuple(
        _ClauseText(
            span=TextSpan(
                text=clause.span.text,
                start=clause_text.span.start + clause.span.start,
                end=clause_text.span.start + clause.span.end,
            )
        )
        for clause in clauses
    )


def _append_clause_span(
    *,
    clauses: list[_ClauseText],
    normalized_text: str,
    start: int,
    end: int,
) -> None:
    while start < end and normalized_text[start].isspace():
        start += 1
    while end > start and normalized_text[end - 1].isspace():
        end -= 1
    if start == end:
        return
    clauses.append(
        _ClauseText(span=TextSpan(text=normalized_text[start:end], start=start, end=end))
    )


def _compile_clause(
    *,
    source_id: str,
    clause_index: int,
    clause_text: _ClauseText,
    parsed_text: ParsedRuleText,
    parser_context: _RuleParserContext,
) -> RuleClause:
    setup_reactive_clause = compile_setup_reactive_shoot_charge_clause(
        source_id=source_id,
        clause_index=clause_index,
        clause_text=clause_text,
    )
    if setup_reactive_clause is not None:
        return setup_reactive_clause
    trigger = _parse_trigger(clause_text)
    conditions = _dedupe_conditions(
        (
            *_parse_aura_conditions(clause_text),
            *_parse_leading_unit_conditions(clause_text),
            *_parse_tracked_target_conditions(clause_text),
            *parse_this_model_attack_target_conditions(clause_text.span),
            *_parse_return_on_death_conditions(clause_text),
            *_parse_frequency_conditions(clause_text),
            *_parse_keyword_conditions(clause_text, parser_context=parser_context),
            *_parse_distance_conditions(
                clause_text,
                parsed_text,
                parser_context=parser_context,
            ),
            *_parse_status_conditions(clause_text),
        )
    )
    target = _parse_target(clause_text, parser_context=parser_context)
    duration = _parse_duration(clause_text)
    effects = _dedupe_effects(
        (
            *_parse_dice_roll_modifier_effects(clause_text),
            *_parse_reroll_effects(clause_text),
            *_parse_characteristic_effects(clause_text.span),
            *_parse_resource_effects(clause_text),
            *_parse_tracked_target_selection_effects(clause_text),
            *_parse_return_on_death_effects(clause_text),
            *_parse_grant_ability_effects(clause_text),
            *_parse_contextual_status_effects(clause_text, parser_context=parser_context),
            *_parse_weapon_ability_effects(clause_text),
            *_parse_placement_effects(clause_text),
            *_parse_restore_lost_wounds_effects(clause_text),
            *_parse_mortal_wound_effects(clause_text),
            *_parse_desperate_escape_effects(clause_text),
            *_parse_movement_transit_permission_effects(clause_text),
        )
    )
    template_id = _template_id_for_clause(
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
    )
    clause_id = f"{source_id}:clause:{clause_index:03d}"
    residual_diagnostic = _residual_diagnostic(
        clause_text=clause_text,
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
    )
    if trigger is None and not conditions and target is None and not effects and duration is None:
        diagnostic = RuleParseDiagnostic(
            reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
            message="Rule clause is not represented by Phase 17C language templates.",
            source_span=clause_text.span,
        )
        return RuleClause(
            clause_id=clause_id,
            source_span=clause_text.span,
            unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
            diagnostics=(diagnostic,),
            template_id=None,
        )
    diagnostics = () if residual_diagnostic is None else (residual_diagnostic,)
    return RuleClause(
        clause_id=clause_id,
        source_span=clause_text.span,
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
        unsupported_reason=(
            None if residual_diagnostic is None else RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
        ),
        diagnostics=diagnostics,
        template_id=template_id,
    )


def _parse_trigger(clause_text: _ClauseText) -> RuleTrigger | None:
    attack_target_trigger = parse_this_model_attack_target_trigger(clause_text.span)
    if attack_target_trigger is not None:
        return attack_target_trigger
    melee_target_match = _THIS_MODEL_MELEE_ATTACK_TARGET_RE.search(clause_text.text)
    if melee_target_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, melee_target_match),
            parameters=parameters_from_pairs(
                (
                    ("roll_type", "wound"),
                    ("timing_window", "attack_sequence.wound"),
                    ("attack_kind", "melee"),
                    ("actor", "this_model"),
                )
            ),
        )
    destroys_enemy_match = _THIS_MODEL_DESTROYS_ENEMY_KEYWORD_UNIT_RE.search(clause_text.text)
    if destroys_enemy_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.UNIT_DESTROYED,
            source_span=_span_from_match(clause_text, destroys_enemy_match),
            parameters=parameters_from_pairs(
                (
                    ("actor", "this_model"),
                    ("destroyed_allegiance", "enemy"),
                    ("destroyed_unit_kind", "unit"),
                )
            ),
        )
    tracked_attack_match = _TRACKED_TARGET_ATTACK_RE.search(clause_text.text)
    if tracked_attack_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, tracked_attack_match),
            parameters=parameters_from_pairs(
                _tracked_target_attack_trigger_parameter_pairs(
                    clause_text=clause_text,
                    match=tracked_attack_match,
                )
            ),
        )
    tracked_destroyed_match = _TRACKED_TARGET_DESTROYED_RE.search(clause_text.text)
    if tracked_destroyed_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.UNIT_DESTROYED,
            source_span=_span_from_match(clause_text, tracked_destroyed_match),
            parameters=parameters_from_pairs(
                (
                    ("destroyed_unit_kind", "unit"),
                    ("timing_window", "tracked_target_destroyed"),
                    ("tracked_target_owner", _tracked_target_owner_token(tracked_destroyed_match)),
                    ("tracked_target_role", _lower_group(tracked_destroyed_match, "role")),
                )
            ),
        )
    first_death_return_match = _FIRST_DEATH_RETURN_TRIGGER_RE.search(clause_text.text)
    if first_death_return_match is not None:
        target = _return_on_death_target_token(first_death_return_match.group("target"))
        trigger_kind = (
            RuleTriggerKind.MODEL_DESTROYED
            if target == "this_model"
            else RuleTriggerKind.UNIT_DESTROYED
        )
        return RuleTrigger(
            kind=trigger_kind,
            source_span=_span_from_match(clause_text, first_death_return_match),
            parameters=parameters_from_pairs(
                (
                    ("destroyed_target", target),
                    ("event_order", "first"),
                    ("resolution_timing", "phase_end"),
                    ("timing_window", "phase_end_after_destroyed"),
                )
            ),
        )
    post_shoot_match = _POST_SHOOT_HIT_TARGET_SELECTION_RE.search(clause_text.text)
    if post_shoot_match is not None and post_shoot_match.group("subject") is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, post_shoot_match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "after"),
                    ("owner", "active_player"),
                    ("phase", "shooting"),
                    ("subject", _post_shoot_subject_token(post_shoot_match.group("subject"))),
                    ("timing_window", "just_after_friendly_unit_has_shot"),
                    ("target_relationship", "hit_by_those_attacks"),
                )
            ),
        )
    for match in _START_END_BATTLE_ROUND_RE.finditer(clause_text.text):
        edge = _lower_group(match, "edge")
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("battle_round", _battle_round_number(match.group("ordinal"))),
                    ("edge", edge),
                    ("phase", "battle_round"),
                    ("timing_window", f"battle_round_{edge}"),
                )
            ),
        )
    for match in _START_END_PHASE_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", _lower_group(match, "edge")),
                    ("phase", _lower_group(match, "phase")),
                    ("owner", _owner_token(match.group("owner"))),
                )
            ),
        )
    for match in _START_END_TURN_RE.finditer(clause_text.text):
        edge = _lower_group(match, "edge")
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", edge),
                    ("phase", "turn"),
                    ("owner", _owner_token(match.group("owner"))),
                    ("timing_window", f"turn_{edge}"),
                )
            ),
        )
    for match in _IN_PHASE_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", _lower_group(match, "phase")),
                    ("owner", _owner_token(match.group("owner"))),
                )
            ),
        )
    for match in _IN_TURN_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", "turn"),
                    ("owner", _owner_token(match.group("owner"))),
                    ("timing_window", "turn_during"),
                )
            ),
        )
    unit_destroyed_match = _DESTROYED_UNIT_RE.search(clause_text.text)
    if unit_destroyed_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.UNIT_DESTROYED,
            source_span=_span_from_match(clause_text, unit_destroyed_match),
        )
    model_destroyed_match = _DESTROYED_MODEL_RE.search(clause_text.text)
    if model_destroyed_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.MODEL_DESTROYED,
            source_span=_span_from_match(clause_text, model_destroyed_match),
        )
    charge_move_end_match = _CHARGE_MOVE_END_RE.search(clause_text.text)
    if charge_move_end_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, charge_move_end_match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "after"),
                    ("phase", "charge"),
                    ("timing_window", "charge_move_end"),
                    ("subject", _lower_group(charge_move_end_match, "subject")),
                )
            ),
        )
    normal_or_advance_move_match = _THIS_MODEL_NORMAL_OR_ADVANCE_MOVE_RE.search(clause_text.text)
    if normal_or_advance_move_match is not None:
        movement_modes = _movement_modes_token(normal_or_advance_move_match.group("modes"))
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, normal_or_advance_move_match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", "movement"),
                    ("timing_window", "model_makes_move"),
                    ("subject", "this_model"),
                    ("movement_modes", movement_modes),
                )
            ),
        )
    unit_move_match = _THIS_UNIT_NORMAL_ADVANCE_FALL_BACK_MOVE_RE.search(clause_text.text)
    if unit_move_match is not None:
        movement_modes = _movement_modes_token(unit_move_match.group("modes"))
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, unit_move_match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", "movement"),
                    ("timing_window", "unit_makes_move"),
                    ("subject", "this_unit"),
                    ("movement_modes", movement_modes),
                )
            ),
        )
    fall_back_match = _ENEMY_UNIT_FALLS_BACK_NEAR_ABILITY_RE.search(clause_text.text)
    if fall_back_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.UNIT_SELECTED,
            source_span=_span_from_match(clause_text, fall_back_match),
            parameters=parameters_from_pairs(
                (
                    ("selected_unit_allegiance", "enemy"),
                    ("selection", "fall_back"),
                    ("timing_window", "just_after_enemy_unit_selected_to_fall_back"),
                )
            ),
        )
    doing_so_match = _WHEN_DOING_SO_RE.search(clause_text.text)
    if (
        doing_so_match is not None
        and "desperate escape" in clause_text.text.lower()
        and _TARGET_BATTLE_SHOCKED_RE.search(clause_text.text) is not None
    ):
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, doing_so_match),
            parameters=parameters_from_pairs(
                (
                    ("roll_type", "desperate_escape"),
                    ("source_context", "previous_effect"),
                    ("timing_window", "desperate_escape_test"),
                )
            ),
        )
    battle_shocked_match = _TARGET_BATTLE_SHOCKED_RE.search(clause_text.text)
    if battle_shocked_match is not None and "desperate escape" in clause_text.text.lower():
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, battle_shocked_match),
            parameters=parameters_from_pairs(
                (
                    ("roll_type", "desperate_escape"),
                    ("source_context", "previous_effect"),
                    ("timing_window", "desperate_escape_test"),
                )
            ),
        )
    dice_trigger_match = _DICE_TRIGGER_RE.search(clause_text.text)
    if dice_trigger_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, dice_trigger_match),
            parameters=parameters_from_pairs(
                (("roll_type", _roll_type(dice_trigger_match.group("roll"))),)
            ),
        )
    setup_match = _SETUP_RE.search(clause_text.text)
    if setup_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.SETUP, source_span=_span_from_match(clause_text, setup_match)
        )
    return None


def _parse_aura_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    match = _AURA_RE.search(clause_text.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.AURA,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("source", "aura"),)),
        ),
    )


def _parse_leading_unit_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    match = _LEADING_UNIT_RE.search(clause_text.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.TARGET_CONSTRAINT,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("relationship", "this_model_leading_unit"),)),
        ),
    )


def _parse_tracked_target_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _TRACKED_TARGET_ATTACK_RE.finditer(clause_text.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("actor", _tracked_attack_actor_token(match.group("actor"))),
                        ("attack_kind", _lower_group(match, "attack_kind")),
                        ("gate_subject", "attack_target"),
                        ("relationship", "attack_targets_tracked_target"),
                        ("target_reference", "tracked_target"),
                        ("tracked_target_owner", "this_model"),
                        ("tracked_target_role", _lower_group(match, "role")),
                    )
                ),
            )
        )
    for match in _TRACKED_TARGET_DESTROYED_RE.finditer(clause_text.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "destroyed_unit"),
                        ("relationship", "tracked_target_destroyed"),
                        ("target_reference", "tracked_target"),
                        ("tracked_target_owner", _tracked_target_owner_token(match)),
                        ("tracked_target_role", _lower_group(match, "role")),
                    )
                ),
            )
        )
    return tuple(conditions)


def _parse_return_on_death_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    trigger_match = _FIRST_DEATH_RETURN_TRIGGER_RE.search(clause_text.text)
    roll_match = _RETURN_ON_DEATH_ROLL_GATE_RE.search(clause_text.text)
    setup_match = _RETURN_ON_DEATH_SET_UP_RE.search(clause_text.text)
    if trigger_match is None or roll_match is None or setup_match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.FREQUENCY_LIMIT,
            source_span=_span_from_match(clause_text, trigger_match),
            parameters=parameters_from_pairs(
                (
                    ("event", "target_destroyed"),
                    ("event_order", "first"),
                    ("scope", "battle"),
                )
            ),
        ),
        RuleCondition(
            kind=RuleConditionKind.DICE_ROLL_GATE,
            source_span=_span_from_match(clause_text, roll_match),
            parameters=parameters_from_pairs(
                (
                    ("comparison", "greater_or_equal"),
                    ("roll_count", _roll_count_value(roll_match.group("roll_count"))),
                    (
                        "roll_expression",
                        _dice_expression_token(roll_match.group("roll_expression")),
                    ),
                    ("success_threshold", int(roll_match.group("success_threshold"))),
                )
            ),
        ),
    )


def _parse_frequency_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _ONCE_PER_RE.finditer(clause_text.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("scope", _lower_group(match, "scope")),)),
            )
        )
    return tuple(conditions)


def _parse_keyword_conditions(
    clause_text: _ClauseText,
    *,
    parser_context: _RuleParserContext,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    target_match_ranges: list[tuple[int, int]] = []
    for match in _TRACKED_TARGET_SELECTION_RE.finditer(clause_text.text):
        target_match_ranges.append((match.start(), match.end()))
    target_match_ranges.extend(this_model_attack_target_match_ranges(clause_text.text))
    for match in _ENEMY_UNIT_FALLS_BACK_NEAR_ABILITY_RE.finditer(clause_text.text):
        target_match_ranges.append((match.start(), match.end()))
        excluded_keywords = match.group("excluded_keywords")
        if excluded_keywords is None:
            continue
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "falling_back_unit"),
                        ("excluded_keyword_any", _keyword_list_tokens(excluded_keywords)),
                    )
                ),
            )
        )
    for match in _THIS_MODEL_MELEE_ATTACK_TARGET_RE.finditer(clause_text.text):
        target_match_ranges.append((match.start(), match.end()))
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("relationship", "this_model_makes_attack"),
                        ("attack_kind", "melee"),
                        ("gate_subject", "attack_target"),
                    )
                ),
            )
        )
        conditions.extend(
            _keyword_any_gate_conditions_from_match(
                clause_text=clause_text,
                match=match,
                gate_subject="attack_target",
            )
        )
    for match in _THIS_MODEL_DESTROYS_ENEMY_KEYWORD_UNIT_RE.finditer(clause_text.text):
        target_match_ranges.append((match.start(), match.end()))
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("relationship", "this_model_destroyed_unit"),
                        ("destroyed_allegiance", "enemy"),
                        ("gate_subject", "destroyed_unit"),
                    )
                ),
            )
        )
        conditions.extend(
            _keyword_any_gate_conditions_from_match(
                clause_text=clause_text,
                match=match,
                gate_subject="destroyed_unit",
            )
        )
    for match in _TARGET_RE.finditer(clause_text.text):
        if _match_inside_ranges(match, target_match_ranges):
            continue
        keyword_text = match.group("keyword")
        if keyword_text is None or is_structural_target_keyword(keyword_text):
            continue
        target_match_ranges.append((match.start(), match.end()))
        conditions.extend(
            _keyword_gate_conditions_from_match(
                clause_text=clause_text,
                match=match,
                parser_context=parser_context,
            )
        )
    for pattern in (_HAS_KEYWORD_RE, _KEYWORD_UNIT_RE):
        for match in pattern.finditer(clause_text.text):
            if pattern is _KEYWORD_UNIT_RE and _match_inside_ranges(match, target_match_ranges):
                continue
            conditions.extend(
                _keyword_gate_conditions_from_match(
                    clause_text=clause_text,
                    match=match,
                    parser_context=parser_context,
                )
            )
    return tuple(conditions)


def _keyword_gate_conditions_from_match(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    parser_context: _RuleParserContext,
) -> tuple[RuleCondition, ...]:
    return tuple(
        RuleCondition(
            kind=RuleConditionKind.KEYWORD_GATE,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("required_keyword", keyword),)),
        )
        for keyword in _keyword_sequence_tokens(
            match.group("keyword"),
            source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
        )
    )


def _keyword_any_gate_conditions_from_match(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    gate_subject: str,
) -> tuple[RuleCondition, ...]:
    keywords = _keyword_any_tokens(match.group("keyword"))
    return (
        RuleCondition(
            kind=RuleConditionKind.KEYWORD_GATE,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("gate_subject", gate_subject),
                    ("required_keyword_any", keywords),
                )
            ),
        ),
    )


def _parse_distance_conditions(
    clause_text: _ClauseText,
    parsed_text: ParsedRuleText,
    *,
    parser_context: _RuleParserContext,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for token in parsed_text.distance_predicates:
        if not _token_inside_clause(token, clause_text):
            continue
        relation_match = _distance_relation_match_for_token(clause_text=clause_text, token=token)
        pairs: tuple[tuple[str, RuleParameterValue], ...] = (
            ("predicate", token.kind.value),
            ("distance_inches", token.distance_inches),
            ("qualifier", token.qualifier),
            *_distance_relation_parameter_pairs(
                relation_match,
                parser_context=parser_context,
            ),
        )
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=(
                    token.span
                    if relation_match is None
                    else _span_from_match(clause_text, relation_match)
                ),
                parameters=parameters_from_pairs(pairs),
            )
        )
    return tuple(conditions)


def _parse_status_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _TARGET_BATTLE_SHOCKED_RE.finditer(clause_text.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("relationship", "target_unit_has_status"),
                        ("gate_subject", _subject_token(match.group("subject"))),
                        ("status", "battle_shocked"),
                    )
                ),
            )
        )
    return tuple(conditions)


def _parse_target(
    clause_text: _ClauseText,
    *,
    parser_context: _RuleParserContext,
) -> RuleTargetSpec | None:
    if _AURA_RE.search(clause_text.text) is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.AURA_UNITS,
            source_span=clause_text.span,
            parameters=parameters_from_pairs(
                _aura_target_parameter_pairs(
                    clause_text,
                    parser_context=parser_context,
                )
            ),
        )
    if (
        _THIS_MODEL_MELEE_ATTACK_TARGET_RE.search(clause_text.text) is not None
        or has_this_model_attack_target(clause_text.text)
        or _RESTORE_LOST_WOUNDS_RE.search(clause_text.text) is not None
    ):
        match = _THIS_MODEL_RE.search(clause_text.text)
        if match is not None:
            return RuleTargetSpec(
                kind=RuleTargetKind.THIS_MODEL,
                source_span=_span_from_match(clause_text, match),
            )
    if has_hit_success_threshold(clause_text.text):
        match = _THIS_UNIT_RE.search(clause_text.text)
        if match is not None:
            return RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=_span_from_match(clause_text, match),
            )
    return_on_death_match = _FIRST_DEATH_RETURN_TRIGGER_RE.search(clause_text.text)
    if (
        return_on_death_match is not None
        and _RETURN_ON_DEATH_SET_UP_RE.search(clause_text.text) is not None
    ):
        target = _return_on_death_target_token(return_on_death_match.group("target"))
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL if target == "this_model" else RuleTargetKind.THIS_UNIT,
            source_span=_span_from_match(clause_text, return_on_death_match),
        )
    selected_target_spec = selected_target_spec_from_text(
        text=clause_text.text,
        source_start=clause_text.start,
        source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
    )
    if selected_target_spec is not None:
        return selected_target_spec
    tracked_selection_match = _TRACKED_TARGET_SELECTION_RE.search(clause_text.text)
    if tracked_selection_match is not None:
        allegiance = _lower_group(tracked_selection_match, "allegiance")
        target_kind = (
            RuleTargetKind.FRIENDLY_UNIT if allegiance == "friendly" else RuleTargetKind.ENEMY_UNIT
        )
        return RuleTargetSpec(
            kind=target_kind,
            source_span=_span_from_match(clause_text, tracked_selection_match),
            parameters=parameters_from_pairs((("allegiance", allegiance),)),
        )
    hit_target_match = _POST_SHOOT_HIT_TARGET_SELECTION_RE.search(clause_text.text)
    if hit_target_match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span_from_match(clause_text, hit_target_match),
            parameters=parameters_from_pairs(
                (("allegiance", "enemy"), ("target_relationship", "hit_by_those_attacks"))
            ),
        )
    match = _TARGET_RE.search(clause_text.text)
    if match is not None:
        allegiance = _lower_group(match, "allegiance")
        target_kind = (
            RuleTargetKind.FRIENDLY_UNIT if allegiance == "friendly" else RuleTargetKind.ENEMY_UNIT
        )
        pairs: list[tuple[str, RuleParameterValue]] = [("allegiance", allegiance)]
        keyword_text = match.group("keyword")
        if keyword_text is not None and not is_structural_target_keyword(keyword_text):
            pairs.extend(
                _keyword_sequence_parameter_pairs(
                    keyword_text,
                    source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
                )
            )
        return RuleTargetSpec(
            kind=target_kind,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(tuple(pairs)),
        )
    match = _THIS_MODEL_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("scope", "this_models_unit"),)),
        )
    match = _THIS_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT, source_span=_span_from_match(clause_text, match)
        )
    match = _BEARERS_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT, source_span=_span_from_match(clause_text, match)
        )
    match = _BEARER_MODEL_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL, source_span=_span_from_match(clause_text, match)
        )
    match = _THAT_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.SELECTED_UNIT,
            source_span=_span_from_match(clause_text, match),
        )
    match = _THIS_MODEL_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span_from_match(clause_text, match),
        )
    match = _PLAYER_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.PLAYER, source_span=_span_from_match(clause_text, match)
        )
    match = _RESOURCE_TARGET_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.PLAYER, source_span=_span_from_match(clause_text, match)
        )
    return None


def _aura_target_parameter_pairs(
    clause_text: _ClauseText,
    *,
    parser_context: _RuleParserContext,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    pairs: list[tuple[str, RuleParameterValue]] = [("eligible_target", "aura_units")]
    match = _TARGET_RE.search(clause_text.text)
    if match is None:
        pairs.append(("allegiance", "any"))
        return tuple(pairs)
    pairs.append(("allegiance", _lower_group(match, "allegiance")))
    keyword_text = match.group("keyword")
    if keyword_text is not None:
        pairs.extend(
            _keyword_sequence_parameter_pairs(
                keyword_text,
                source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
            )
        )
    return tuple(pairs)


def _parse_duration(clause_text: _ClauseText) -> RuleDuration | None:
    return parse_rule_duration(text=clause_text.text, span=clause_text.span)


def _parse_dice_roll_modifier_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _ADD_ROLL_RE.finditer(clause_text.text):
        value = int(match.group("value"))
        delta = value if _lower_group(match, "verb") == "add" else -value
        effects.append(_dice_modifier_effect(clause_text=clause_text, match=match, delta=delta))
    for match in _SIGNED_ROLL_RE.finditer(clause_text.text):
        value = int(match.group("value"))
        delta = value if match.group("sign") == "+" else -value
        effects.append(_dice_modifier_effect(clause_text=clause_text, match=match, delta=delta))
    return tuple(effects)


def _dice_modifier_effect(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    delta: int,
) -> RuleEffectSpec:
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("roll_type", _roll_type(match.group("roll"))),
        ("delta", delta),
    ]
    if _SELECTED_UNIT_MAKES_ATTACK_RE.search(clause_text.text) is not None:
        pairs.append(("attack_role", "attacker"))
    return RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_DICE_ROLL,
        source_span=_span_from_match(clause_text, match),
        parameters=parameters_from_pairs(tuple(pairs)),
    )


def _parse_reroll_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    list_spans: list[tuple[int, int]] = []
    tracked_target_pairs = _tracked_target_reroll_parameter_pairs(clause_text)
    objective_instead_matches = tuple(_OBJECTIVE_REROLL_INSTEAD_RE.finditer(clause_text.text))
    objective_instead_spans = tuple(
        (match.start(), match.end()) for match in objective_instead_matches
    )
    for match in _REROLL_ROLL_LIST_RE.finditer(clause_text.text):
        list_spans.append((match.start(), match.end()))
        for roll in _roll_list_values(match.group("rolls")):
            effects.append(
                RuleEffectSpec(
                    kind=RuleEffectKind.REROLL_PERMISSION,
                    source_span=_span_from_match(clause_text, match),
                    parameters=parameters_from_pairs(
                        (("roll_type", _roll_type(roll)), *tracked_target_pairs)
                    ),
                )
            )
    for match in _REROLL_RE.finditer(clause_text.text):
        if _match_is_within_any_span(
            match=match,
            spans=(*tuple(list_spans), *objective_instead_spans),
        ):
            continue
        roll_type = _roll_type(match.group("roll"))
        pairs: list[tuple[str, RuleParameterValue]] = [("roll_type", roll_type)]
        reroll_value = match.group("reroll_value")
        if reroll_value is not None:
            pairs.append(("reroll_unmodified_value", int(reroll_value)))
        objective_instead_match = _objective_instead_match_for_roll(
            objective_instead_matches,
            roll_type=roll_type,
            after=match.end(),
        )
        if objective_instead_match is not None:
            pairs.append(("full_reroll_if_target_within_objective_range", True))
        pairs.extend(tracked_target_pairs)
        source_span = (
            _span_from_match(clause_text, match)
            if objective_instead_match is None
            else _span_from_bounds(
                clause_text,
                start_offset=match.start(),
                end_offset=objective_instead_match.end(),
            )
        )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.REROLL_PERMISSION,
                source_span=source_span,
                parameters=parameters_from_pairs(tuple(pairs)),
            )
        )
    return tuple(effects)


def _objective_instead_match_for_roll(
    matches: tuple[re.Match[str], ...],
    *,
    roll_type: str,
    after: int,
) -> re.Match[str] | None:
    for match in matches:
        if match.start() < after:
            continue
        if _roll_type(match.group("roll")) == roll_type:
            return match
    return None


def _roll_list_values(value: str) -> tuple[str, ...]:
    rolls: list[str] = []
    for raw_roll in re.split(r"\s*,\s*|\s+and\s+", value.strip(), flags=re.IGNORECASE):
        roll = raw_roll.strip()
        if roll:
            rolls.append(roll)
    return tuple(rolls)


def _tracked_target_attack_trigger_parameter_pairs(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    roll_types = _roll_types_for_reroll_language(clause_text.text)
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("actor", _tracked_attack_actor_token(match.group("actor"))),
        ("attack_kind", _lower_group(match, "attack_kind")),
        ("target_reference", "tracked_target"),
        ("tracked_target_owner", "this_model"),
        ("tracked_target_role", _lower_group(match, "role")),
    ]
    if len(roll_types) == 1:
        roll_type = roll_types[0]
        pairs.extend(
            (
                ("roll_type", roll_type),
                ("timing_window", f"attack_sequence.{roll_type}"),
            )
        )
    elif roll_types:
        pairs.extend(
            (
                ("roll_types", roll_types),
                ("timing_window", "attack_sequence.roll"),
            )
        )
    else:
        pairs.append(("timing_window", "attack_sequence.attack"))
    return tuple(pairs)


def _tracked_target_reroll_parameter_pairs(
    clause_text: _ClauseText,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    match = _TRACKED_TARGET_ATTACK_RE.search(clause_text.text)
    if match is None:
        return ()
    return (
        ("target_reference", "tracked_target"),
        ("tracked_target_owner", "this_model"),
        ("tracked_target_role", _lower_group(match, "role")),
    )


def _roll_types_for_reroll_language(text: str) -> tuple[str, ...]:
    roll_types: list[str] = []
    list_spans: list[tuple[int, int]] = []
    for match in _REROLL_ROLL_LIST_RE.finditer(text):
        list_spans.append((match.start(), match.end()))
        roll_types.extend(_roll_type(roll) for roll in _roll_list_values(match.group("rolls")))
    for match in _REROLL_RE.finditer(text):
        if _match_is_within_any_span(match=match, spans=tuple(list_spans)):
            continue
        roll_types.append(_roll_type(match.group("roll")))
    return tuple(dict.fromkeys(roll_types))


def _tracked_attack_actor_token(actor: str) -> str:
    token = " ".join(actor.lower().split())
    if token == "this model":
        return "this_model"
    if token == "a model in this model's unit":
        return "model_in_this_models_unit"
    raise RuleIRError(f"Unsupported tracked-target attack actor: {actor}.")


def _tracked_target_owner_token(match: re.Match[str]) -> str:
    owner = " ".join(match.group("owner").lower().split())
    if owner == "this model":
        return "this_model"
    if owner == "this unit":
        return "this_unit"
    raise RuleIRError(f"Unsupported tracked-target owner: {match.group('owner')}.")


def _return_on_death_effect_parameter_pairs(
    match: re.Match[str],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    target = _return_on_death_target_token(match.group("target"))
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("action", "set_back_up"),
        ("placement_anchor", "destroyed_position"),
        ("placement_kind", "battlefield_set_up"),
        ("placement_preference", "as_close_as_possible"),
        ("target", target),
        ("target_lifecycle", "destroyed"),
        ("target_scope", "destroyed_model" if target == "this_model" else "destroyed_unit"),
    ]
    wounds_remaining = match.group("wounds_remaining")
    if wounds_remaining is not None:
        pairs.extend(
            (
                ("restore_wounds_mode", "fixed_remaining"),
                ("wounds_remaining", int(wounds_remaining)),
            )
        )
        return tuple(pairs)
    if match.group("full_health") is not None:
        pairs.append(("restore_wounds_mode", "full_health"))
        return tuple(pairs)
    raise RuleIRError("Return-on-death setup must define remaining wounds or full health.")


def _return_on_death_target_token(value: str) -> str:
    token = " ".join(value.lower().split())
    if token == "this model":
        return "this_model"
    if token == "this unit":
        return "this_unit"
    raise RuleIRError(f"Unsupported return-on-death target: {value}.")


def _roll_count_value(value: str | None) -> int:
    if value is None:
        return 1
    token = value.lower().strip()
    if token in {"one", "a", "an"}:
        return 1
    if token.isdecimal():
        return int(token)
    raise RuleIRError(f"Unsupported roll count in rule language: {value}.")


def _dice_expression_token(value: str) -> str:
    token = value.upper().strip()
    if not token:
        raise RuleIRError("Dice expression must not be empty.")
    return token


def _mortal_wounds_target_scope_token(value: str) -> str:
    token = " ".join(value.lower().split())
    if token in {"that enemy unit", "that unit", "selected unit", "target unit"}:
        return "selected_enemy_unit"
    raise RuleIRError(f"Unsupported mortal-wounds target: {value}.")


def _match_is_within_any_span(
    *,
    match: re.Match[str],
    spans: tuple[tuple[int, int], ...],
) -> bool:
    return any(start <= match.start() and match.end() <= end for start, end in spans)


def _parse_resource_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _CP_RE.finditer(clause_text.text):
        verb = _lower_group(match, "verb")
        value = int(match.group("value"))
        delta = -value if verb in {"spend", "lose", "remove"} else value
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("delta", delta),)),
            )
        )
    for match in _VP_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.ADD_VICTORY_POINTS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("delta", int(match.group("value"))),)),
            )
        )
    return tuple(effects)


def _parse_tracked_target_selection_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _TRACKED_TARGET_SELECTION_RE.finditer(clause_text.text):
        allegiance = _lower_group(match, "allegiance")
        replacement = match.group("replacement") is not None
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SELECT_TRACKED_TARGET,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("replacement", replacement),
                        ("selection_kind", "select_one"),
                        ("target_allegiance", allegiance),
                        ("target_lifecycle", "until_destroyed"),
                        ("target_scope", f"{allegiance}_unit"),
                        ("tracked_target_owner", _tracked_target_owner_token(match)),
                        ("tracked_target_role", _lower_group(match, "role")),
                    )
                ),
            )
        )
    return tuple(effects)


def _parse_return_on_death_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    trigger_match = _FIRST_DEATH_RETURN_TRIGGER_RE.search(clause_text.text)
    roll_match = _RETURN_ON_DEATH_ROLL_GATE_RE.search(clause_text.text)
    setup_match = _RETURN_ON_DEATH_SET_UP_RE.search(clause_text.text)
    if trigger_match is None or roll_match is None or setup_match is None:
        return ()
    trigger_target = _return_on_death_target_token(trigger_match.group("target"))
    setup_target = _return_on_death_target_token(setup_match.group("target"))
    if setup_target != trigger_target:
        raise RuleIRError("Return-on-death trigger and setup target must match.")
    return (
        RuleEffectSpec(
            kind=RuleEffectKind.RETURN_DESTROYED_TARGET,
            source_span=_span_from_match(clause_text, setup_match),
            parameters=parameters_from_pairs(_return_on_death_effect_parameter_pairs(setup_match)),
        ),
    )


def _parse_grant_ability_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _SHOOT_ELIGIBILITY_AFTER_FALL_BACK_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("ability", "can_fall_back_and_shoot"),)),
            )
        )
    for match in _CHARGE_ELIGIBILITY_AFTER_MOVE_RE.finditer(clause_text.text):
        movement = " ".join(match.group("movement").lower().split())
        ability = (
            "can_fall_back_and_charge" if movement == "fell back" else "can_advance_and_charge"
        )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("ability", ability),)),
            )
        )
    for match in _FEEL_NO_PAIN_ABILITY_RE.finditer(clause_text.text):
        parameter_pairs: list[tuple[str, RuleParameterValue]] = [
            ("ability", "Feel No Pain"),
            ("threshold", int(match.group("threshold"))),
        ]
        qualifier = match.group("qualifier")
        if qualifier is not None:
            parameter_pairs.extend(_feel_no_pain_qualifier_parameter_pairs(qualifier))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(tuple(parameter_pairs)),
            )
        )
    for match in _GRANT_ABILITY_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        ability = _ability_token(match.group("ability"))
        if _is_weapon_keyword(ability):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("ability", ability),)),
            )
        )
    return tuple(effects)


def _parse_contextual_status_effects(
    clause_text: _ClauseText,
    *,
    parser_context: _RuleParserContext,
) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _SHADOW_OF_CHAOS_STATUS_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("status", "within_shadow_of_chaos"),
                        ("rules_context", "shadow_of_chaos"),
                        ("owner", "your_army"),
                    )
                ),
            )
        )
    effects.extend(
        hit_success_threshold_effects(
            clause_text=clause_text.text,
            clause_start=clause_text.start,
            source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
        )
    )
    for match in _CONTEXTUAL_STATUS_DENIAL_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        status_label = _ability_token(match.group("status"))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("status", _catalog_like_token(status_label)),
                        ("status_label", status_label),
                        ("operation", "deny"),
                        ("target_scope", _contextual_status_target_scope_token(match)),
                        ("rules_context", "status_denial"),
                    )
                ),
            )
        )
    return tuple(effects)


def _parse_weapon_ability_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _NAMED_WEAPON_ABILITY_CHOICE_RE.finditer(clause_text.text):
        effects.extend(_weapon_ability_choice_effects_from_match(clause_text, match))
    for match in _NAMED_WEAPON_ABILITY_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        weapon_name = _weapon_name_token(match.group("weapon_name"))
        generic_scope = _generic_weapon_scope_from_token(weapon_name)
        pairs: list[tuple[str, RuleParameterValue]] = [
            ("weapon_ability", _ability_token(match.group("ability"))),
            ("target_scope", "models_in_selected_unit"),
        ]
        ability_value = _optional_weapon_ability_value_group(match, "ability_value")
        if ability_value is not None:
            pairs.append(("weapon_ability_value", ability_value))
        if generic_scope is None:
            pairs.append(("weapon_name", weapon_name))
        else:
            pairs.append(("weapon_scope", generic_scope))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(tuple(pairs)),
            )
        )
    for match in _WEAPON_ABILITY_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        scoped_pairs: list[tuple[str, RuleParameterValue]] = [
            ("weapon_ability", _ability_token(match.group("ability"))),
            ("weapon_scope", _weapon_scope_token(match.group("weapon_scope"))),
        ]
        ability_value = _optional_weapon_ability_value_group(match, "ability_value")
        if ability_value is not None:
            scoped_pairs.append(("weapon_ability_value", ability_value))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(tuple(scoped_pairs)),
            )
        )
    return tuple(effects)


def _weapon_ability_choice_effects_from_match(
    clause_text: _ClauseText,
    match: re.Match[str],
) -> tuple[RuleEffectSpec, ...]:
    source_span = _span_from_match(clause_text, match)
    weapon_names = _weapon_name_tokens(match.group("weapon_names"))
    target_scope = _weapon_owner_target_scope_token(match.group("target_scope"))
    selection_group_id = f"weapon_ability_choice_{source_span.start:04d}"
    effects: list[RuleEffectSpec] = []
    for option_index, (ability, ability_value) in enumerate(
        _weapon_ability_choices_from_text(match.group("abilities")),
        start=1,
    ):
        pairs: list[tuple[str, RuleParameterValue]] = [
            ("selection_group_id", selection_group_id),
            ("selection_kind", "select_one"),
            (
                "selection_option_id",
                _weapon_ability_choice_option_id(
                    option_index=option_index,
                    ability=ability,
                    ability_value=ability_value,
                ),
            ),
            ("selection_option_index", option_index),
            ("target_scope", target_scope),
            ("weapon_ability", ability),
            *_weapon_name_parameter_pairs(weapon_names),
        ]
        if ability_value is not None:
            pairs.append(("weapon_ability_value", ability_value))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                source_span=source_span,
                parameters=parameters_from_pairs(tuple(pairs)),
            )
        )
    return tuple(effects)


def _weapon_ability_choices_from_text(
    abilities_text: str,
) -> tuple[tuple[str, RuleParameterValue | None], ...]:
    choices: list[tuple[str, RuleParameterValue | None]] = []
    for option_match in _WEAPON_ABILITY_CHOICE_TOKEN_RE.finditer(abilities_text):
        ability = _ability_token(option_match.group("ability"))
        if not _is_weapon_keyword(ability):
            raise RuleIRError(f"Unsupported weapon ability choice in rule language: {ability}.")
        choices.append(
            (
                ability,
                _optional_weapon_ability_value_group(option_match, "ability_value"),
            )
        )
    if not choices:
        raise RuleIRError("Weapon ability choice list must contain weapon ability options.")
    return tuple(choices)


def _weapon_ability_choice_option_id(
    *,
    option_index: int,
    ability: str,
    ability_value: RuleParameterValue | None,
) -> str:
    token_parts = [_catalog_like_token(ability)]
    if ability_value is not None:
        token_parts.append(_catalog_like_token(str(ability_value)))
    return f"option_{option_index:03d}_{'_'.join(token_parts)}"


def _parse_placement_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _REMOVE_TO_STRATEGIC_RESERVES_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_PERMISSION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("allowed", True),
                        ("optional", True),
                        ("placement_kind", "turn_end_reserves"),
                        ("reserve_kind", "strategic_reserves"),
                        ("action", "remove_from_battlefield_to_strategic_reserves"),
                    )
                ),
            )
        )
    for match in _PLACEMENT_RESTRICTION_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_RESTRICTION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("allowed", False),)),
            )
        )
    for match in _PLACEMENT_PERMISSION_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text, match=match, effects=tuple(effects)
        ):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_PERMISSION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("allowed", True),)),
            )
        )
    return tuple(effects)


def _parse_restore_lost_wounds_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _RESTORE_LOST_WOUNDS_RE.finditer(clause_text.text):
        amount = match.group("amount").upper()
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.RESTORE_LOST_WOUNDS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("target", "this_model"),
                        ("amount", amount),
                        ("cap", "lost_wounds"),
                        ("optional", True),
                    )
                ),
            )
        )
    return tuple(effects)


def _parse_mortal_wound_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _PER_MODEL_MORTAL_WOUNDS_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.INFLICT_MORTAL_WOUNDS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("damage_kind", "mortal_wounds"),
                        (
                            "mortal_wounds_expression",
                            _dice_expression_token(match.group("mortal_wounds")),
                        ),
                        ("roll_count", _roll_count_value(match.group("roll_count"))),
                        ("roll_count_scope", "each_model_in_this_unit"),
                        (
                            "roll_expression",
                            _dice_expression_token(match.group("roll_expression")),
                        ),
                        ("success_threshold", int(match.group("success_threshold"))),
                        (
                            "target_scope",
                            _mortal_wounds_target_scope_token(match.group("target")),
                        ),
                    )
                ),
            )
        )
    return tuple(effects)


def _parse_desperate_escape_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _DESPERATE_ESCAPE_TESTS_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("required", True),
                        ("roll_type", "desperate_escape"),
                        ("target_scope", "models_in_target_unit"),
                    )
                ),
            )
        )
    return tuple(effects)


def _parse_movement_transit_permission_effects(
    clause_text: _ClauseText,
) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    trigger_match = _THIS_MODEL_NORMAL_OR_ADVANCE_MOVE_RE.search(clause_text.text)
    if trigger_match is not None:
        movement_modes = _movement_modes_token(trigger_match.group("modes"))
        for match in _MOVE_OVER_FRIENDLY_MONSTER_VEHICLE_AND_TERRAIN_RE.finditer(clause_text.text):
            keywords = _model_keyword_any_token(
                match.group("first_model_keyword"),
                match.group("second_model_keyword"),
            )
            if keywords != ("MONSTER", "VEHICLE"):
                continue
            effects.append(
                RuleEffectSpec(
                    kind=RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                    source_span=_span_from_match(clause_text, match),
                    parameters=parameters_from_pairs(
                        (
                            ("permission", "move_over_as_if_not_there"),
                            ("movement_modes", movement_modes),
                            ("model_allegiance", "friendly"),
                            ("model_keyword_any", keywords),
                            ("terrain_scope", "terrain_features"),
                            ("terrain_height_max_inches", float(match.group("height"))),
                        )
                    ),
                )
            )
        return tuple(effects)

    unit_trigger_match = _THIS_UNIT_NORMAL_ADVANCE_FALL_BACK_MOVE_RE.search(clause_text.text)
    if unit_trigger_match is None:
        return ()
    movement_modes = _movement_modes_token(unit_trigger_match.group("modes"))
    engagement_match = _MOVE_THROUGH_ENGAGEMENT_AUTO_PASS_RE.search(clause_text.text)
    engagement_auto_pass = engagement_match is not None
    for match in _MOVE_THROUGH_MODELS_AND_TERRAIN_RE.finditer(clause_text.text):
        excluded_keywords = match.group("excluded_model_keywords")
        effect_span = (
            _span_from_bounds(clause_text, match.start(), engagement_match.end())
            if engagement_match is not None
            else _span_from_match(clause_text, match)
        )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                source_span=effect_span,
                parameters=parameters_from_pairs(
                    (
                        ("permission", "move_through_models"),
                        ("movement_modes", movement_modes),
                        ("model_allegiance", "any"),
                        (
                            "excluded_model_keyword_any",
                            ()
                            if excluded_keywords is None
                            else _keyword_list_tokens(excluded_keywords),
                        ),
                        ("enemy_engagement_range_transit", engagement_auto_pass),
                        ("enemy_engagement_range_end_allowed", False),
                        ("desperate_escape_tests_auto_passed", engagement_auto_pass),
                    )
                ),
            )
        )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                source_span=effect_span,
                parameters=parameters_from_pairs(
                    (
                        ("permission", "move_through_terrain_features"),
                        ("movement_modes", movement_modes),
                        ("terrain_features", True),
                    )
                ),
            )
        )
    return tuple(effects)


def _residual_diagnostic(
    *,
    clause_text: _ClauseText,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    duration: RuleDuration | None,
) -> RuleParseDiagnostic | None:
    residual_span = _meaningful_residual_span(
        clause_text=clause_text,
        recognized_spans=_recognized_component_spans(
            trigger=trigger,
            conditions=conditions,
            target=target,
            effects=effects,
            duration=duration,
        ),
    )
    if residual_span is None:
        return None
    return RuleParseDiagnostic(
        reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        message="Rule clause contains unrepresented residual language.",
        source_span=residual_span,
    )


def _recognized_component_spans(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    duration: RuleDuration | None,
) -> tuple[TextSpan, ...]:
    spans: list[TextSpan] = []
    if trigger is not None:
        spans.append(trigger.source_span)
    spans.extend(condition.source_span for condition in conditions)
    if target is not None:
        spans.append(target.source_span)
    spans.extend(effect.source_span for effect in effects)
    if duration is not None:
        spans.append(duration.source_span)
    return tuple(spans)


def _meaningful_residual_span(
    *,
    clause_text: _ClauseText,
    recognized_spans: tuple[TextSpan, ...],
) -> TextSpan | None:
    for start, end in _residual_ranges(
        clause_start=clause_text.span.start,
        clause_end=clause_text.span.end,
        recognized_spans=recognized_spans,
    ):
        residual_text = clause_text.span.text[
            start - clause_text.span.start : end - clause_text.span.start
        ]
        token_matches = tuple(_RESIDUAL_TOKEN_RE.finditer(residual_text))
        meaningful_matches = tuple(
            match for match in token_matches if _is_meaningful_residual_token(match.group(0))
        )
        if not meaningful_matches:
            continue
        span_start = start + meaningful_matches[0].start()
        span_end = start + meaningful_matches[-1].end()
        return TextSpan(
            text=clause_text.span.text[
                span_start - clause_text.span.start : span_end - clause_text.span.start
            ],
            start=span_start,
            end=span_end,
        )
    return None


def _residual_ranges(
    *,
    clause_start: int,
    clause_end: int,
    recognized_spans: tuple[TextSpan, ...],
) -> tuple[tuple[int, int], ...]:
    merged_spans = _merged_spans(
        clause_start=clause_start,
        clause_end=clause_end,
        recognized_spans=recognized_spans,
    )
    ranges: list[tuple[int, int]] = []
    cursor = clause_start
    for start, end in merged_spans:
        if cursor < start:
            ranges.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < clause_end:
        ranges.append((cursor, clause_end))
    return tuple(ranges)


def _merged_spans(
    *,
    clause_start: int,
    clause_end: int,
    recognized_spans: tuple[TextSpan, ...],
) -> tuple[tuple[int, int], ...]:
    clipped = tuple(
        sorted(
            (
                (max(clause_start, span.start), min(clause_end, span.end))
                for span in recognized_spans
                if span.start < clause_end and clause_start < span.end
            ),
            key=lambda value: (value[0], value[1]),
        )
    )
    merged: list[tuple[int, int]] = []
    for start, end in clipped:
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return tuple(merged)


def _is_meaningful_residual_token(token: str) -> bool:
    normalized = token.lower().strip("'")
    if not normalized or normalized in _RESIDUAL_CONNECTOR_TOKENS:
        return False
    return not normalized.isdigit()


def _template_id_for_clause(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
) -> str | None:
    candidates: list[str] = []
    if any(condition.kind is RuleConditionKind.AURA for condition in conditions):
        candidates.append(AURA_TEMPLATE_ID)
    for effect in effects:
        if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
            candidates.append(WEAPON_ABILITY_GRANT_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.GRANT_ABILITY:
            candidates.append(GRANT_ABILITY_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS:
            candidates.append(CONTEXTUAL_STATUS_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS:
            candidates.append(DESPERATE_ESCAPE_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
            candidates.append(DICE_ROLL_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.REROLL_PERMISSION:
            candidates.append(REROLL_PERMISSION_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SET_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_SET_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE:
            candidates.append(MOVEMENT_DISTANCE_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.OUT_OF_PHASE_ACTION:
            candidates.append(OUT_OF_PHASE_ACTION_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.MODIFY_COMMAND_POINTS,
            RuleEffectKind.ADD_VICTORY_POINTS,
        }:
            candidates.append(RESOURCE_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.RETURN_DESTROYED_TARGET:
            candidates.append(RETURN_ON_DEATH_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SELECT_TRACKED_TARGET:
            candidates.append(TRACKED_TARGET_SELECTION_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS:
            candidates.append(TIMING_WINDOW_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.PLACEMENT_PERMISSION,
            RuleEffectKind.PLACEMENT_RESTRICTION,
        }:
            candidates.append(PLACEMENT_TEMPLATE_ID)
    if target is not None:
        candidates.append(SELECTED_TARGET_TEMPLATE_ID)
    for condition in conditions:
        if condition.kind is RuleConditionKind.KEYWORD_GATE:
            candidates.append(KEYWORD_GATE_TEMPLATE_ID)
        elif condition.kind is RuleConditionKind.DISTANCE_PREDICATE:
            candidates.append(DISTANCE_PREDICATE_TEMPLATE_ID)
    if trigger is not None:
        candidates.append(TIMING_WINDOW_TEMPLATE_ID)
    if not candidates:
        return None
    template_id = candidates[0]
    rule_template_by_id(template_id)
    return template_id


def _dedupe_conditions(conditions: tuple[RuleCondition, ...]) -> tuple[RuleCondition, ...]:
    deduped = {json_key(condition): condition for condition in conditions}
    return tuple(
        deduped[key]
        for key in sorted(
            deduped,
            key=lambda value: (
                deduped[value].source_span.start,
                deduped[value].source_span.end,
                deduped[value].kind.value,
                value,
            ),
        )
    )


def _dedupe_effects(effects: tuple[RuleEffectSpec, ...]) -> tuple[RuleEffectSpec, ...]:
    deduped = {json_key(effect): effect for effect in effects}
    return tuple(
        deduped[key]
        for key in sorted(
            deduped,
            key=lambda value: (
                deduped[value].source_span.start,
                deduped[value].source_span.end,
                deduped[value].kind.value,
                value,
            ),
        )
    )


def json_key(value: RuleCondition | RuleEffectSpec) -> str:
    if type(value) is RuleCondition or type(value) is RuleEffectSpec:
        payload = value.to_payload()
    else:
        raise RuleIRError("Unsupported rule parser dedupe value.")
    return repr(payload)


def _distance_relation_match_for_token(
    *,
    clause_text: _ClauseText,
    token: DistancePredicateToken,
) -> re.Match[str] | None:
    token_start = token.span.start - clause_text.span.start
    token_end = token.span.end - clause_text.span.start
    for match in _DISTANCE_RELATION_RE.finditer(clause_text.text):
        if match.start("predicate") <= token_start and token_end <= match.end("range"):
            return match
    return None


def _distance_relation_parameter_pairs(
    match: re.Match[str] | None,
    *,
    parser_context: _RuleParserContext,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    if match is None:
        return ()
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("negated", match.group("negated") is not None),
        ("range_kind", _range_kind_token(match.group("range"))),
        ("object_kind", _object_kind_token(match.group("object_kind"))),
    ]
    subject = match.group("subject")
    if subject is not None:
        pairs.append(("subject", _subject_token(subject)))
    quantity = match.group("quantity")
    if quantity is not None:
        pairs.append(("object_quantity", _quantity_token(quantity)))
    allegiance = match.group("allegiance")
    if allegiance is not None:
        pairs.append(("object_allegiance", allegiance.lower()))
    keyword_text = match.group("keyword")
    if keyword_text is not None:
        pairs.extend(
            _keyword_sequence_parameter_pairs(
                keyword_text,
                source_keyword_sequence_parts=parser_context.source_keyword_sequence_parts,
            )
        )
    object_owner = match.group("object_owner")
    if object_owner is not None:
        pairs.append(("object_owner", _subject_token(object_owner)))
    if match.group("object_ability_scope") is not None:
        pairs.append(("object_ability_scope", "this_ability"))
    object_reference = match.group("object_reference")
    if object_reference is not None:
        pairs.append(("object_reference", _subject_token(object_reference)))
    return tuple(pairs)


def _span_from_match(clause_text: _ClauseText, match: re.Match[str]) -> TextSpan:
    start = clause_text.start + match.start()
    end = clause_text.start + match.end()
    return TextSpan(text=clause_text.span.text[match.start() : match.end()], start=start, end=end)


def _span_from_bounds(clause_text: _ClauseText, start_offset: int, end_offset: int) -> TextSpan:
    start = clause_text.start + start_offset
    end = clause_text.start + end_offset
    return TextSpan(text=clause_text.span.text[start_offset:end_offset], start=start, end=end)


def _token_inside_clause(token: DistancePredicateToken, clause_text: _ClauseText) -> bool:
    return clause_text.span.start <= token.span.start and token.span.end <= clause_text.span.end


def _lower_group(match: re.Match[str], group_name: str) -> str:
    return match.group(group_name).lower().replace(" ", "_").replace("-", "_")


def _optional_weapon_ability_value_group(
    match: re.Match[str],
    group_name: str,
) -> RuleParameterValue | None:
    value = match.group(group_name)
    if value is None:
        return None
    stripped = value.strip().upper()
    if stripped.isdecimal():
        return int(stripped)
    if stripped == "D3":
        return stripped
    raise RuleIRError(f"Unsupported weapon ability value in rule language: {value}.")


def _owner_token(owner: str | None) -> str | None:
    if owner is None:
        return None
    lowered = owner.lower()
    if "opponent" in lowered:
        return "opponent"
    if lowered == "your":
        return "active_player"
    return None


def _battle_round_number(value: str) -> int:
    token = value.lower().strip()
    ordinal_numbers = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    ordinal = ordinal_numbers.get(token)
    if ordinal is not None:
        return ordinal
    suffixes = ("st", "nd", "rd", "th")
    for suffix in suffixes:
        if token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    if token.isdecimal():
        return int(token)
    raise RuleIRError(f"Unsupported battle round ordinal in rule language: {value}.")


def _roll_type(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _subject_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def _post_shoot_subject_token(value: str) -> str:
    token = _subject_token(value.removeprefix("the "))
    if token in {"bearer", "this_model", "this_unit"}:
        return token
    raise RuleIRError(f"Unsupported post-shoot subject in rule language: {value}.")


def _contextual_status_target_scope_token(match: re.Match[str]) -> str:
    subject = _subject_token(match.group("subject").removeprefix("the "))
    if subject.startswith("models_in_"):
        return "models_in_selected_unit"
    if subject in {"that_enemy_unit", "that_unit", "selected_unit", "target_unit"}:
        return "selected_unit"
    raise RuleIRError(f"Unsupported contextual status target in rule language: {subject}.")


def _range_kind_token(value: str) -> str:
    stripped = value.strip()
    if stripped.endswith('"'):
        return "numeric_range"
    return stripped.lower().replace(" ", "_").replace("-", "_")


def _object_kind_token(value: str) -> str:
    normalized = value.lower().replace(" ", "_").replace("-", "_")
    if normalized in {"units", "unit"}:
        return "unit"
    if normalized in {"models", "model"}:
        return "model"
    if normalized in {"objective_markers", "objective_marker"}:
        return "objective_marker"
    raise RuleIRError(f"Unsupported distance relation object kind: {value}.")


def _quantity_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def _ability_token(value: str) -> str:
    stripped = value.strip(" []().,;:")
    return " ".join(stripped.split())


def _feel_no_pain_attack_condition_token(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ")
    if normalized in {"psychic attack", "psychic attacks"}:
        return "psychic_attack"
    raise RuleIRError(f"Unsupported Feel No Pain attack qualifier: {value}.")


def _feel_no_pain_qualifier_parameter_pairs(
    value: str,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    parameter_pairs: list[tuple[str, RuleParameterValue]] = []
    has_attack_condition = False
    has_mortal_wound_scope = False
    for raw_part in re.split(r"\s+and\s+", value.strip(), flags=re.IGNORECASE):
        normalized = raw_part.strip().lower().replace("-", " ")
        if normalized in {"psychic attack", "psychic attacks"}:
            parameter_pairs.append(
                ("attack_condition", _feel_no_pain_attack_condition_token(raw_part))
            )
            has_attack_condition = True
        elif normalized == "mortal wounds":
            parameter_pairs.append(("mortal_wounds", True))
            has_mortal_wound_scope = True
        elif normalized:
            raise RuleIRError(f"Unsupported Feel No Pain attack qualifier: {value}.")
    if has_mortal_wound_scope and not has_attack_condition:
        raise RuleIRError(f"Unsupported Feel No Pain attack qualifier: {value}.")
    return tuple(parameter_pairs)


def _weapon_name_token(value: str) -> str:
    stripped = value.strip(" []().,;:")
    return " ".join(stripped.split())


def _weapon_name_tokens(value: str) -> tuple[str, ...]:
    names: list[str] = []
    for raw_name in re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", value.strip()):
        name = _weapon_name_token(raw_name)
        if name:
            names.append(name)
    if not names:
        raise RuleIRError("Named weapon ability grant requires a weapon name.")
    return tuple(dict.fromkeys(names))


def _weapon_name_parameter_pairs(
    weapon_names: tuple[str, ...],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    if not weapon_names:
        raise RuleIRError("Named weapon ability grant requires weapon names.")
    if len(weapon_names) == 1:
        return (("weapon_name", weapon_names[0]),)
    return (("weapon_names", weapon_names),)


def _weapon_owner_target_scope_token(value: str) -> str:
    token = _subject_token(value)
    if token == "this_model":
        return "this_model"
    if token == "this_unit":
        return "models_in_this_unit"
    if token in {"that_unit", "selected_unit"}:
        return "models_in_selected_unit"
    raise RuleIRError(f"Unsupported named weapon owner scope in rule language: {value}.")


def _generic_weapon_scope_from_token(value: str) -> str | None:
    normalized = " ".join(value.strip().lower().replace("-", " ").split())
    if normalized in {"melee weapon", "melee weapons"}:
        return "melee"
    if normalized in {"ranged weapon", "ranged weapons"}:
        return "ranged"
    if normalized in {"weapon", "weapons", "all weapon", "all weapons"}:
        return "all"
    return None


def _weapon_scope_token(value: str) -> str:
    scope = _generic_weapon_scope_from_token(value)
    if scope is None:
        raise RuleIRError(f"Unsupported weapon scope in rule language: {value}.")
    return scope


def _is_weapon_keyword(value: str) -> bool:
    return value.lower() in {keyword.lower() for keyword in canonical_weapon_keyword_tokens()}


def _catalog_like_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _span_matches_existing_effect(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    effects: tuple[RuleEffectSpec, ...],
) -> bool:
    span = _span_from_match(clause_text, match)
    return any(
        span.start >= effect.source_span.start and span.end <= effect.source_span.end
        for effect in effects
    )


def _match_inside_ranges(
    match: re.Match[str],
    ranges: list[tuple[int, int]],
) -> bool:
    return any(start <= match.start() and match.end() <= end for start, end in ranges)
