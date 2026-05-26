from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.rules.parsed_tokens import (
    DiceExpressionToken,
    DistancePredicateKind,
    DistancePredicateToken,
    ParsedRuleText,
    ParsedRuleTextPayload,
    RangeExpressionToken,
    RuleTokenError,
    TextSpan,
    distance_predicate_kind_from_token,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.source_data import (
    RuleSourceText,
    RuleSourceTextPayload,
    SourceDataError,
)
from warhammer40k_core.rules.text_normalization import (
    NormalizedRuleText,
    NormalizedRuleTextPayload,
    TextNormalizationError,
    normalize_rule_text,
)


def test_rule_text_normalization_canonicalizes_phase_three_inputs() -> None:
    raw = (
        "\u201cdevastating wounds\u201d\u00a0\u2013 roll \uff12 d \uff16 \u2212 1\uff1b "
        "within \uff11\uff12 inches \u00d7 2. feel no pain"
    )

    assert normalize_rule_text(raw) == (
        '"Devastating Wounds" - roll 2D6-1; within 12" x 2. Feel No Pain'
    )


def test_normalized_rule_text_serialization_round_trips_exactly() -> None:
    normalized = NormalizedRuleText.from_raw("rapid fire: D6 + 2 attacks within 24 in.")
    payload = cast(
        NormalizedRuleTextPayload,
        json.loads(json.dumps(normalized.to_payload(), sort_keys=True)),
    )

    assert NormalizedRuleText.from_payload(payload).to_payload() == normalized.to_payload()
    assert normalized.normalized_text == 'Rapid Fire: D6+2 attacks within 24".'


def test_normalization_rejects_invalid_raw_text() -> None:
    with pytest.raises(TextNormalizationError):
        normalize_rule_text(cast(str, 1))
    with pytest.raises(TextNormalizationError):
        normalize_rule_text(" ")
    with pytest.raises(TextNormalizationError):
        normalize_rule_text("bad\u0000text")
    with pytest.raises(TextNormalizationError):
        NormalizedRuleText(raw_text="D6", normalized_text="d6")


def test_parsed_tokens_are_structured_and_deterministic() -> None:
    parsed = parse_normalized_tokens(
        'Blast weapon makes D6+3 attacks within 18". Sustained Hits applies.'
    )

    assert parsed.dice_expressions[0].expression == DiceExpression(
        quantity=1,
        sides=6,
        modifier=3,
    )
    assert parsed.distance_predicates[0].kind is DistancePredicateKind.WITHIN
    assert parsed.distance_predicates[0].distance_inches == 18.0
    assert parsed.range_expressions == ()
    assert tuple(keyword.keyword for keyword in parsed.keywords) == ("Blast", "Sustained Hits")


def test_parsed_rule_text_serialization_round_trips_exactly() -> None:
    parsed = parse_normalized_tokens('Torrent attacks hit targets within 12" with D3 hits.')
    payload = cast(
        ParsedRuleTextPayload,
        json.loads(json.dumps(parsed.to_payload(), sort_keys=True)),
    )

    assert ParsedRuleText.from_payload(payload).to_payload() == parsed.to_payload()


def test_parsed_rule_text_rejects_tokens_not_matching_normalized_text() -> None:
    with pytest.raises(RuleTokenError):
        ParsedRuleText(
            normalized_text="No dice here.",
            dice_expressions=(
                DiceExpressionToken(
                    span=TextSpan(text="D6", start=0, end=2),
                    expression=DiceExpression(quantity=1, sides=6),
                ),
            ),
        )


def test_parsed_rule_text_rejects_corrupted_payload_text_mismatch() -> None:
    payload = parse_normalized_tokens("Roll D6.").to_payload()
    payload["normalized_text"] = "No dice."

    with pytest.raises(RuleTokenError):
        ParsedRuleText.from_payload(payload)


def test_parsed_rule_text_rejects_out_of_order_tokens() -> None:
    with pytest.raises(RuleTokenError):
        ParsedRuleText(
            normalized_text='Targets within 12" and 18".',
            range_expressions=(
                RangeExpressionToken(
                    span=TextSpan(text='18"', start=23, end=26),
                    distance_inches=18,
                ),
                RangeExpressionToken(
                    span=TextSpan(text='12"', start=15, end=18),
                    distance_inches=12,
                ),
            ),
        )


def test_distance_predicates_preserve_source_semantics_without_bare_ranges() -> None:
    parsed = parse_normalized_tokens(
        'Targets within 12", more than 8", at least 3", at most 9", and exactly 6".'
    )

    assert parsed.range_expressions == ()
    assert tuple(predicate.kind for predicate in parsed.distance_predicates) == (
        DistancePredicateKind.WITHIN,
        DistancePredicateKind.MORE_THAN,
        DistancePredicateKind.AT_LEAST,
        DistancePredicateKind.AT_MOST,
        DistancePredicateKind.EXACTLY,
    )
    assert tuple(predicate.distance_inches for predicate in parsed.distance_predicates) == (
        12.0,
        8.0,
        3.0,
        9.0,
        6.0,
    )


def test_named_distance_predicates_parse_without_distances() -> None:
    normalized = normalize_rule_text(
        "while within engagement range, outside detection range, or at half range"
    )
    parsed = parse_normalized_tokens(normalized)

    assert normalized == (
        "while within Engagement Range, outside Detection Range, or at Half Range"
    )
    assert parsed.range_expressions == ()
    assert tuple(predicate.kind for predicate in parsed.distance_predicates) == (
        DistancePredicateKind.WITHIN_ENGAGEMENT_RANGE,
        DistancePredicateKind.OUTSIDE_DETECTION_RANGE,
        DistancePredicateKind.HALF_RANGE,
    )
    assert all(predicate.distance_inches is None for predicate in parsed.distance_predicates)


def test_distance_predicate_qualifier_round_trips() -> None:
    parsed = parse_normalized_tokens('Move within 1" if possible.')
    predicate = parsed.distance_predicates[0]
    payload = cast(
        ParsedRuleTextPayload,
        json.loads(json.dumps(parsed.to_payload(), sort_keys=True)),
    )

    assert predicate.kind is DistancePredicateKind.WITHIN
    assert predicate.distance_inches == 1.0
    assert predicate.qualifier == "if possible"
    assert parsed.range_expressions == ()
    assert ParsedRuleText.from_payload(payload).to_payload() == parsed.to_payload()
    assert "<" not in json.dumps(parsed.to_payload())
    assert "object at 0x" not in json.dumps(parsed.to_payload())


def test_bare_range_expression_remains_available_for_weapon_range_text() -> None:
    parsed = parse_normalized_tokens('The weapon has a 24" range.')

    assert parsed.distance_predicates == ()
    assert parsed.range_expressions[0].distance_inches == 24


def test_distance_predicate_rejects_corrupted_payload_text_mismatch() -> None:
    with pytest.raises(RuleTokenError):
        ParsedRuleText(
            normalized_text='Move within 1".',
            distance_predicates=(
                DistancePredicateToken(
                    span=TextSpan(text='within 2"', start=5, end=14),
                    kind=DistancePredicateKind.WITHIN,
                    distance_inches=2.0,
                ),
            ),
        )


def test_distance_predicate_validation_failures_are_token_domain_errors() -> None:
    span = TextSpan(text='within 1"', start=0, end=9)

    assert (
        distance_predicate_kind_from_token(DistancePredicateKind.WITHIN)
        is DistancePredicateKind.WITHIN
    )

    with pytest.raises(RuleTokenError):
        distance_predicate_kind_from_token(cast(str, 1))
    with pytest.raises(RuleTokenError):
        distance_predicate_kind_from_token("near")
    with pytest.raises(RuleTokenError):
        DistancePredicateToken(
            span=span,
            kind=cast(DistancePredicateKind, "within"),
            distance_inches=1.0,
        )
    with pytest.raises(RuleTokenError):
        DistancePredicateToken(span=span, kind=DistancePredicateKind.WITHIN)
    with pytest.raises(RuleTokenError):
        DistancePredicateToken(
            span=span,
            kind=DistancePredicateKind.WITHIN,
            distance_inches=0.0,
        )
    with pytest.raises(RuleTokenError):
        DistancePredicateToken(
            span=TextSpan(text="within Engagement Range", start=0, end=23),
            kind=DistancePredicateKind.WITHIN_ENGAGEMENT_RANGE,
            distance_inches=1.0,
        )
    with pytest.raises(RuleTokenError):
        DistancePredicateToken(
            span=span,
            kind=DistancePredicateKind.WITHIN,
            distance_inches=1.0,
            qualifier=" ",
        )


@pytest.mark.parametrize(
    ("raw_text", "expected_normalized"),
    [
        ('Range 12-24"', 'Range 12-24"'),
        ('Range 12 - 24"', 'Range 12 - 24"'),
        ("Range 12 \u2013 24 inches", 'Range 12 - 24"'),
    ],
)
def test_hyphenated_range_intervals_fail_explicitly(
    raw_text: str,
    expected_normalized: str,
) -> None:
    normalized = normalize_rule_text(raw_text)
    assert normalized == expected_normalized

    with pytest.raises(RuleTokenError):
        parse_normalized_tokens(normalized)


def test_parsed_tokens_fail_explicitly_for_invalid_inputs() -> None:
    with pytest.raises(RuleTokenError):
        parse_normalized_tokens(" ")
    with pytest.raises(RuleTokenError):
        parse_normalized_tokens("D1")


def test_rule_source_text_normalizes_and_parses_once_at_boundary() -> None:
    source = RuleSourceText.from_raw(
        source_id="datasheet:intercessors:bolt-rifle",
        raw_text="assault weapon: roll d6 attacks within 24 inches.",
    )

    assert source.normalized_text == 'Assault weapon: roll D6 attacks within 24".'
    assert source.parsed_tokens.dice_expressions[0].expression == DiceExpression(
        quantity=1,
        sides=6,
    )
    assert source.parsed_tokens.distance_predicates[0].kind is DistancePredicateKind.WITHIN
    assert source.parsed_tokens.distance_predicates[0].distance_inches == 24.0
    assert source.parsed_tokens.range_expressions == ()
    assert source.parsed_tokens.keywords[0].keyword == "Assault"


def test_rule_source_text_payload_round_trips_and_rejects_mismatch() -> None:
    source = RuleSourceText.from_raw(source_id="rule:blast", raw_text="blast: D6 attacks.")
    payload = cast(
        RuleSourceTextPayload,
        json.loads(json.dumps(source.to_payload(), sort_keys=True)),
    )

    assert RuleSourceText.from_payload(payload).to_payload() == source.to_payload()

    payload["normalized_text"] = "Blast: D3 attacks."
    with pytest.raises(SourceDataError):
        RuleSourceText.from_payload(payload)


def test_rule_source_text_rejects_invalid_source_id() -> None:
    with pytest.raises(SourceDataError):
        RuleSourceText.from_raw(source_id=" ", raw_text="Blast")
