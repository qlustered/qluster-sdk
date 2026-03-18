import json
import uuid
from typing import Any
import pytest

from pydantic import ValidationError
from qluster_sdk.rule import RuleResult, Issue, RuleMetadata, IssueSeverity, IssueType, RuleAlertAction


def test_round_trip_alias_json():
    """Test that RuleResult can be serialized to alias-keyed JSON and deserialized back."""
    # Build a non-trivial result
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    issues = [Issue(dataset_rule_id=rid, issue_reason="x", field_names=["price"], publisher="Mike")]
    rr = RuleResult(
        issues=issues,
        corrections={"price": 100.0},
        enrichments={},
        modification_reasons_per_field={"price": "cap"}
    )

    # Dump with aliases
    wire = rr.dump_wire()
    assert set(wire.keys()) == {"i", "c", "m"}  # "e" omitted (empty); "i"/"c"/"m" present
    assert ['rid', 'r', 'f', 'pb'] == list(wire['i'][0].keys())

    # Use Pydantic's model_dump_json for proper JSON serialization
    blob = rr.model_dump_json(by_alias=True, exclude_none=True, exclude_defaults=True)
    rr2 = RuleResult.load_wire(blob)

    # Same data after round-trip
    assert rr2.issues and len(rr2.issues) == 1
    assert rr2.issues[0].dataset_rule_id == rid
    assert rr2.corrections == {"price": 100.0}
    assert rr2.enrichments == {}  # default factory still results in empty dict
    assert rr2.modification_reasons_per_field["price"] == "cap"


def test_noop_serializes_minimal():
    """Test that a no-op RuleResult produces an empty wire dict."""
    rr = RuleResult()  # pure no-op
    wire = rr.dump_wire()
    # With exclude_defaults/none, should be empty dict
    assert wire == {}


def test_is_noop_method():
    """Test the is_noop helper method."""
    # Empty result should be noop
    assert RuleResult().is_noop()

    # Result with issues should not be noop
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    rr_with_issues = RuleResult(issues=[Issue(dataset_rule_id=rid, issue_reason="test", field_names=["col"])])
    assert not rr_with_issues.is_noop()

    # Result with corrections should not be noop
    rr_with_corrections = RuleResult(corrections={"price": 100.0})
    assert not rr_with_corrections.is_noop()

    # Result with enrichments should not be noop
    rr_with_enrichments = RuleResult(enrichments={"category": "electronics"})
    assert not rr_with_enrichments.is_noop()

    # Result with modification reasons should not be noop
    rr_with_reasons = RuleResult(modification_reasons_per_field={"price": "corrected"})
    assert not rr_with_reasons.is_noop()


def test_issue_alias_keys_present_on_dump():
    """Test that Issue uses alias keys when dumped."""
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    issue = Issue(dataset_rule_id=rid, issue_reason="bad", field_names=["col"])
    d = issue.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)

    # Expect alias keys, not canonical names
    assert set(d.keys()) <= {"rid", "r", "f", "p", "sv", "a", "t", "s"}
    assert "rid" in d and d["rid"] == rid  # UUID object in model_dump
    assert "r" in d and d["r"] == "bad"
    assert "f" in d and d["f"] == ["col"]


def test_issue_full_alias_mapping():
    """Test all possible Issue fields with their aliases."""
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    issue = Issue(
        dataset_rule_id=rid,
        issue_reason="test reason",
        field_names=["col1", "col2"],
        issue_pattern="pattern123",
        suggested_values_per_field={"col1": ["val1", "val2"]},
        allowed_alert_actions=[RuleAlertAction.overwrite_value],
        issue_type=IssueType.validation,
        severity=IssueSeverity.warning
    )

    d = issue.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)

    # Check all alias mappings
    expected_keys = {"rid", "r", "f", "p", "sv", "a", "t", "s"}
    assert set(d.keys()) == expected_keys

    assert d["rid"] == rid
    assert d["r"] == "test reason"
    assert d["f"] == ["col1", "col2"]
    assert d["p"] == "pattern123"
    assert d["sv"] == {"col1": ["val1", "val2"]}
    assert d["a"] == ["overwrite_value"]
    assert d["t"] == "validation"
    assert d["s"] == "warning"


def test_load_wire_accepts_alias_dict_directly():
    """Test that load_wire can accept an alias-keyed dict directly."""
    # Alias-keyed dict for a simple RR
    data = {"c": {"price": 80.0}}
    rr = RuleResult.load_wire(data)
    assert rr.corrections == {"price": 80.0}


def test_load_wire_accepts_json_string():
    """Test that load_wire can accept a JSON string."""
    # Create RuleResult and get its wire format
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    original = RuleResult(
        issues=[Issue(dataset_rule_id=rid, issue_reason="test", field_names=["col"])],
        corrections={"price": 50.0}
    )

    # Convert to JSON string using Pydantic's method
    json_string = original.model_dump_json(by_alias=True, exclude_none=True, exclude_defaults=True)

    # Load from JSON string
    loaded = RuleResult.load_wire(json_string)

    assert len(loaded.issues) == 1
    assert loaded.issues[0].dataset_rule_id == rid
    assert loaded.corrections == {"price": 50.0}


def test_complex_round_trip_with_all_fields():
    """Test round-trip with a complex RuleResult containing all possible fields."""
    rid1 = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    rid2 = uuid.UUID("fedcba98-7654-3210-fedc-ba9876543210")

    # Create complex issues
    issue1 = Issue(
        dataset_rule_id=rid1,
        issue_reason="Price too high",
        field_names=["price"],
        issue_pattern="price_high",
        suggested_values_per_field={"price": ["100", "200"]},
        allowed_alert_actions=[RuleAlertAction.overwrite_value, RuleAlertAction.map_value],
        issue_type=IssueType.out_of_range,
        severity=IssueSeverity.blocker
    )

    issue2 = Issue(
        dataset_rule_id=rid2,
        issue_reason="Category unknown",
        field_names=["category"],
        severity=IssueSeverity.warning
    )

    # Create complex RuleResult
    original = RuleResult(
        issues=[issue1, issue2],
        corrections={"price": 100.0, "name": "corrected_name"},
        enrichments={"category": "electronics", "brand": "Sony"},
        modification_reasons_per_field={
            "price": "Corrected from 500 to 100",
            "category": "Enriched with category info"
        }
    )

    # Round-trip through wire format using Pydantic's JSON methods
    json_str = original.model_dump_json(by_alias=True, exclude_none=True, exclude_defaults=True)
    loaded = RuleResult.load_wire(json_str)

    # Verify all data is preserved
    assert len(loaded.issues) == 2

    # Check first issue
    i1 = loaded.issues[0]
    assert i1.dataset_rule_id == rid1
    assert i1.issue_reason == "Price too high"
    assert i1.field_names == ["price"]
    assert i1.issue_pattern == "price_high"
    assert i1.suggested_values_per_field == {"price": ["100", "200"]}
    assert i1.allowed_alert_actions == [RuleAlertAction.overwrite_value, RuleAlertAction.map_value]
    assert i1.issue_type == IssueType.out_of_range
    assert i1.severity == IssueSeverity.blocker

    # Check second issue (defaults should be preserved)
    i2 = loaded.issues[1]
    assert i2.dataset_rule_id == rid2
    assert i2.issue_reason == "Category unknown"
    assert i2.field_names == ["category"]
    assert i2.severity == IssueSeverity.warning

    # Check other fields
    assert loaded.corrections == {"price": 100.0, "name": "corrected_name"}
    assert loaded.enrichments == {"category": "electronics", "brand": "Sony"}
    assert loaded.modification_reasons_per_field == {
        "price": "Corrected from 500 to 100",
        "category": "Enriched with category info"
    }


def test_issue_can_load_from_alias_keys():
    """Test that Issue can be loaded from alias-keyed data."""
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")

    # Alias-keyed data
    alias_data = {
        "rid": str(rid),
        "r": "test reason",
        "f": ["col1"],
        "s": "warning"
    }

    # Should be able to load from alias keys due to populate_by_name=True
    issue = Issue.model_validate(alias_data)

    assert issue.dataset_rule_id == rid
    assert issue.issue_reason == "test reason"
    assert issue.field_names == ["col1"]
    assert issue.severity == IssueSeverity.warning


def test_wire_format_compactness():
    """Test that wire format is significantly more compact than regular dump."""
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    rr = RuleResult(
        issues=[Issue(dataset_rule_id=rid, issue_reason="test", field_names=["col"])],
        corrections={"price": 100.0},
        modification_reasons_per_field={"price": "corrected"}
    )

    # Regular dump with full field names
    regular_json = rr.model_dump_json(exclude_none=True, exclude_defaults=True)

    # Wire format with aliases
    wire_json = rr.model_dump_json(by_alias=True, exclude_none=True, exclude_defaults=True)

    # Wire format should be shorter
    assert len(wire_json) < len(regular_json)

    # Verify alias keys are used in wire format
    assert "i" in wire_json and "issues" not in wire_json
    assert "c" in wire_json and "corrections" not in wire_json
    assert "m" in wire_json and "modification_reasons_per_field" not in wire_json


def test_semver_validator_raises_valueerror():
    """Test that RuleMetadata validates semantic releases correctly."""
    # Valid semver should work
    valid_metadata = RuleMetadata(release="1.2.3")
    assert valid_metadata.release == "1.2.3"

    # Invalid semver should raise ValidationError (Pydantic wraps the ValueError)
    with pytest.raises(ValidationError, match="Invalid semantic version"):
        RuleMetadata(release="not-a-semver")

    with pytest.raises(ValidationError, match="Invalid semantic version"):
        RuleMetadata(release="1.x.3")  # Invalid character

    with pytest.raises(ValidationError, match="Invalid semantic version"):
        RuleMetadata(release="")  # Empty string


def test_empty_collections_excluded_in_wire():
    """Test that empty collections are excluded from wire format."""
    # RuleResult with some empty collections
    rr = RuleResult(
        issues=None,  # None should be excluded
        corrections={"price": 100},  # Non-empty, should be included
        enrichments={},  # Empty dict, should be excluded
        modification_reasons_per_field={}  # Empty dict, should be excluded
    )

    wire = rr.dump_wire()

    # Only corrections should be present
    assert set(wire.keys()) == {"c"}
    assert wire["c"] == {"price": 100}


def test_populate_by_name_allows_canonical_names():
    """Test that models can still accept canonical field names."""
    rid = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")

    # Should work with canonical field names
    issue_canonical = Issue(
        dataset_rule_id=rid,
        issue_reason="test",
        field_names=["col"]
    )

    # Should also work with alias names
    issue_alias = Issue.model_validate({
        "rid": rid,  # Can accept UUID object directly
        "r": "test",
        "f": ["col"]
    })

    # Both should be equivalent
    assert issue_canonical.dataset_rule_id == issue_alias.dataset_rule_id
    assert issue_canonical.issue_reason == issue_alias.issue_reason
    assert issue_canonical.field_names == issue_alias.field_names
