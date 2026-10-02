import pytest
from pydantic import ValidationError

from qluster_sdk.rule import (
    EnrichedFieldSchema,
    IssueSeverity,
    RuleMetadata,
    RuleSeverity,
)


def test_enriched_field_schema_accepts_extra_model_schema_keys():
    s = EnrichedFieldSchema(type="Decimal", is_nullable=True, precision=18, scale=6)
    assert s.type == "Decimal"
    assert s.is_nullable is True
    # extra Atlas model-schema keys are preserved
    s2 = EnrichedFieldSchema(type="Date", datetime_formats=["%m/%d/%y"])
    assert s2.model_dump().get("datetime_formats") == ["%m/%d/%y"]


def test_rule_metadata_accepts_enriched_field_schemas():
    md = RuleMetadata(
        release="1.0.0",
        enriches_columns=["gross_premium"],
        enriched_field_schemas={
            "gross_premium": EnrichedFieldSchema(type="Decimal", is_nullable=True),
        },
    )
    assert md.enriched_field_schemas["gross_premium"].type == "Decimal"


def test_rule_metadata_defaults_to_empty():
    md = RuleMetadata(release="1.0.0")
    assert md.enriched_field_schemas == {}


def test_enriched_field_schemas_keys_must_be_enriched_columns():
    with pytest.raises(ValidationError):
        RuleMetadata(
            release="1.0.0",
            enriches_columns=["gross_premium"],
            enriched_field_schemas={"unknown_col": EnrichedFieldSchema(type="Decimal")},
        )


def test_enriched_field_schema_round_trips_precision_scale():
    md = RuleMetadata(
        release="1.0.0",
        enriches_columns=["gross_premium"],
        enriched_field_schemas={
            "gross_premium": EnrichedFieldSchema(type="Decimal", precision=18, scale=6),
        },
    )
    dumped = md.model_dump()["enriched_field_schemas"]["gross_premium"]
    assert dumped["precision"] == 18
    assert dumped["scale"] == 6


def test_optional_columns_accepts_read_side_subset():
    md = RuleMetadata(
        release="1.0.0",
        input_columns=["value", "value_2"],
        validates_columns=["value"],
        optional_columns=["value_2"],
        column_field_types={"value": "any", "value_2": "any"},
    )
    assert md.optional_columns == ["value_2"]


def test_optional_columns_accepts_validates_only_name():
    md = RuleMetadata(
        release="1.0.0",
        validates_columns=["flag"],
        optional_columns=["flag"],
        column_field_types={"flag": ["Boolean"]},
    )
    assert md.optional_columns == ["flag"]


def test_optional_columns_defaults_to_empty():
    assert RuleMetadata(release="1.0.0").optional_columns == []


def test_optional_columns_rejects_unknown_names():
    with pytest.raises(ValidationError, match="optional_columns"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["value"],
            optional_columns=["nope"],
            column_field_types={"value": "any"},
        )


def test_optional_columns_rejects_wildcard():
    with pytest.raises(ValidationError, match="wildcard"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["*"],
            optional_columns=["*"],
        )


def test_optional_columns_rejects_write_side_columns():
    # "target" is read-side declared too, so only the disjointness rule fires.
    with pytest.raises(ValidationError, match="write-side"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["value", "target"],
            enriches_columns=["target"],
            optional_columns=["target"],
            column_field_types={"value": "any", "target": "any"},
            enriched_field_schemas={"target": EnrichedFieldSchema(type="Text")},
        )


def test_enriched_field_schema_optional_fields_default_when_omitted():
    # Switching the Field specifiers to named `default=` must preserve the
    # runtime defaults the positional form produced: is_nullable True,
    # precision/scale None. exclude_none drops the None numerics, so the
    # persisted shape stays minimal (matches the seeded value_map_rule schema).
    s = EnrichedFieldSchema(type="Decimal")
    assert s.is_nullable is True
    assert s.precision is None
    assert s.scale is None
    assert s.model_dump(exclude_none=True) == {"type": "Decimal", "is_nullable": True}


def test_default_severity_defaults_to_as_declared():
    """Omitting the field leaves every issue at the severity the rule gave it."""
    assert RuleMetadata(release="1.0.0").default_severity is RuleSeverity.as_declared


def test_default_severity_can_be_declared_warning():
    """A warning-only rule declares itself non-blocking."""
    md = RuleMetadata(release="1.0.0", default_severity=RuleSeverity.warning)
    assert md.default_severity is RuleSeverity.warning


def test_default_severity_survives_round_trip():
    """model_dump/model_validate keeps the declaration — the submit path
    reads metadata as a plain dict."""
    md = RuleMetadata(release="1.0.0", default_severity=RuleSeverity.warning)
    assert (
        RuleMetadata.model_validate(md.model_dump()).default_severity
        is RuleSeverity.warning
    )


def test_rule_severity_resolve_maps_each_mode():
    """as_declared passes the issue's own severity through; the other two
    modes answer with themselves whatever the issue declared."""
    assert RuleSeverity.as_declared.resolve(IssueSeverity.warning) is IssueSeverity.warning
    assert RuleSeverity.as_declared.resolve(IssueSeverity.blocker) is IssueSeverity.blocker
    assert RuleSeverity.warning.resolve(IssueSeverity.blocker) is IssueSeverity.warning
    assert RuleSeverity.blocker.resolve(IssueSeverity.warning) is IssueSeverity.blocker


def test_column_field_types_declares_read_side_columns():
    md = RuleMetadata(
        release="1.0.0",
        input_columns=["premium", "effective_date"],
        validates_columns=["premium"],
        column_field_types={
            "premium": ["Decimal", "Float"],
            "effective_date": ["Date", "DateTime"],
        },
    )
    assert md.column_field_types["premium"] == ["Decimal", "Float"]
    assert md.read_side_columns == ["premium", "effective_date"]


def test_column_field_types_accepts_the_any_escape_hatch():
    md = RuleMetadata(
        release="1.0.0",
        input_columns=["value"],
        column_field_types={"value": "any"},
    )
    assert md.column_field_types["value"] == "any"


def test_column_field_types_rejects_a_missing_read_side_column():
    with pytest.raises(ValidationError, match=r"column_field_types missing: \['premium'\]"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["premium", "effective_date"],
            column_field_types={"effective_date": ["Date"]},
        )


def test_column_field_types_rejects_a_column_outside_the_read_side_set():
    # An enriches-only column is typed by enriched_field_schemas, not here.
    with pytest.raises(ValidationError, match=r"column_field_types has unknown columns: \['mapped_value'\]"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["value"],
            enriches_columns=["mapped_value"],
            enriched_field_schemas={"mapped_value": EnrichedFieldSchema(type="Text")},
            column_field_types={"value": ["Text"], "mapped_value": ["Text"]},
        )


def test_column_field_types_rejects_an_empty_list():
    with pytest.raises(ValidationError, match="is empty"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["value"],
            column_field_types={"value": []},
        )


def test_column_field_types_rejects_an_unknown_field_type_name():
    with pytest.raises(ValidationError, match="unknown field type 'Numeric'"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["value"],
            column_field_types={"value": ["Decimal", "Numeric"]},
        )


def test_column_field_types_rejects_the_wildcard_as_a_key():
    with pytest.raises(ValidationError, match="wildcard"):
        RuleMetadata(
            release="1.0.0",
            input_columns=["*"],
            column_field_types={"*": ["Text"]},
        )


def test_enriched_field_schemas_must_cover_every_enriched_column():
    with pytest.raises(ValidationError, match=r"enriched_field_schemas missing: \['b'\]"):
        RuleMetadata(
            release="1.0.0",
            enriches_columns=["a", "b"],
            enriched_field_schemas={"a": EnrichedFieldSchema(type="Text")},
        )


def test_corrected_and_enriched_column_types_must_agree():
    with pytest.raises(ValidationError, match="does not accept the produced type 'Decimal'"):
        RuleMetadata(
            release="1.0.0",
            corrects_columns=["amount"],
            enriches_columns=["amount"],
            column_field_types={"amount": ["Text"]},
            enriched_field_schemas={"amount": EnrichedFieldSchema(type="Decimal")},
        )


def test_corrected_and_enriched_column_agrees_when_the_type_is_listed():
    md = RuleMetadata(
        release="1.0.0",
        corrects_columns=["amount"],
        enriches_columns=["amount"],
        column_field_types={"amount": ["Decimal", "Float"]},
        enriched_field_schemas={"amount": EnrichedFieldSchema(type="Decimal")},
    )
    assert md.affected_columns == ["amount"]


def test_corrected_and_enriched_column_agrees_under_any():
    md = RuleMetadata(
        release="1.0.0",
        corrects_columns=["amount"],
        enriches_columns=["amount"],
        column_field_types={"amount": "any"},
        enriched_field_schemas={"amount": EnrichedFieldSchema(type="Decimal")},
    )
    assert md.column_field_types["amount"] == "any"


def test_wildcard_only_rule_needs_no_column_field_types():
    md = RuleMetadata(release="1.0.0", input_columns=["*"], validates_columns=["*"])
    assert md.column_field_types == {}
    assert md.read_side_columns == []


def test_column_field_types_survives_round_trip():
    md = RuleMetadata(
        release="1.0.0",
        input_columns=["value"],
        column_field_types={"value": ["Decimal"]},
    )
    assert RuleMetadata.model_validate(md.model_dump()).column_field_types == {
        "value": ["Decimal"]
    }
