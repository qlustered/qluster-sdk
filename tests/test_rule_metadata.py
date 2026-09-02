import pytest
from pydantic import ValidationError

from qluster_sdk.rule import EnrichedFieldSchema, RuleMetadata


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
    )
    assert md.optional_columns == ["value_2"]


def test_optional_columns_accepts_validates_only_name():
    md = RuleMetadata(
        release="1.0.0",
        validates_columns=["flag"],
        optional_columns=["flag"],
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


def test_default_treat_as_alert_defaults_to_true():
    """Omitting the field preserves today's behaviour: instances are born blocking."""
    assert RuleMetadata(release="1.0.0").default_treat_as_alert is True


def test_default_treat_as_alert_can_be_declared_false():
    """A warning-only rule declares itself non-blocking."""
    md = RuleMetadata(release="1.0.0", default_treat_as_alert=False)
    assert md.default_treat_as_alert is False


def test_default_treat_as_alert_survives_round_trip():
    """model_dump/model_validate keeps the declaration — the submit path
    reads metadata as a plain dict."""
    md = RuleMetadata(release="1.0.0", default_treat_as_alert=False)
    assert RuleMetadata.model_validate(md.model_dump()).default_treat_as_alert is False
