import pytest
import uuid
from typing import Any
from pydantic import BaseModel, Field
from qluster_sdk.rule import Rule, RuleMetadata, RuleResult, Issue, _auto_slugify, _validate_slug, VALID_SLUG_RE

class PriceShoesParams(BaseModel):
    max_price: float = Field(
        ..., 
        title="Maximum allowed price for shoes",
        description="Any price ≥ this will be flagged."
    )
    correction_strategy: str = Field(
        "cap",
        title="Correction Strategy",
        description="Either 'cap' or 'quarantine'"
    )


class PriceShoesRule(Rule):
    """
    Example custom rule:
      - Alerts if price ≥ max_price for shoes.
      - If strategy=='cap', auto-corrects price → max_price.
    """
    metadata = RuleMetadata(release="0.0.1")
    ParamsModel = PriceShoesParams
    # ResolveActionsParams = {
    #     "resolve_action1": ResolveAction1Params
    # }

    def apply(self, row: dict[str, Any]) -> RuleResult:
        price = row.get("price")
        ptype = row.get("product_type")

        # Only shoes are inspected
        if ptype == "shoes" and price is not None and price >= self.params.max_price:
            reason = f"Price {price} exceeds maximum {self.params.max_price}"
            alert = Issue(
                dataset_rule_id=self.dataset_rule_id,
                issue_reason=reason,
                field_names=["price"],
                issue_pattern=None,
            )

            corrections: dict[str, Any] = {}
            mods: dict[str, str] = {}
            if self.params.correction_strategy == "cap":
                capped = self.params.max_price
                corrections["price"] = capped
                mods["price"] = f"Corrected price from {price} to {capped}"

            return RuleResult(
                issues=[alert],
                corrections=corrections,
                enrichments={},
                modification_reasons_per_field=mods,
            )

        # No alert → valid pass
        return RuleResult(issues=None)

    # def resolve_action1(self, row, p_type):
    #     row["product_type"] = p_type


class TestPriceShoesRule:
    @pytest.fixture(autouse=True)
    def setup_rules(self):
        # use a fixed UUID so tests can compare it
        self.dataset_rule_id = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
        self.cap_rule = PriceShoesRule(
            self.dataset_rule_id,
            {"max_price": 100.0, "correction_strategy": "cap"},
        )
        self.quarantine_rule = PriceShoesRule(
            self.dataset_rule_id,
            {"max_price": 100.0, "correction_strategy": "quarantine"},
        )
        assert "price-shoes-rule" == PriceShoesRule.name

    def test_non_shoes_row_passes(self):
        row = {"product_type": "hat", "price": 1000.0}
        result: RuleResult = self.cap_rule.apply(row)
        assert result.issues is None
        assert result.corrections == {}
        assert result.modification_reasons_per_field == {}

    @pytest.mark.parametrize("price", [50.0, 99.99])
    def test_shoes_below_max_pass(self, price):
        row = {"product_type": "shoes", "price": price}
        result = self.cap_rule.apply(row)
        assert result.issues is None

    def test_shoes_equal_to_max_alert_and_cap(self):
        row = {"product_type": "shoes", "price": 100.0}
        result = self.cap_rule.apply(row)

        # Must block
        assert result.issues is not None
        assert len(result.issues) == 1
        assert isinstance(result.issues[0], Issue)
        assert result.issues[0].dataset_rule_id == self.dataset_rule_id
        assert "exceeds maximum" in result.issues[0].issue_reason
        assert result.issues[0].field_names == ["price"]

        # Must correct
        assert result.corrections == {"price": 100.0}
        assert result.modification_reasons_per_field == {
            "price": "Corrected price from 100.0 to 100.0"
        }

    def test_shoes_above_max_alert_and_cap(self):
        row = {"product_type": "shoes", "price": 150.5}
        result = self.cap_rule.apply(row)
        assert result.corrections == {"price": 100.0}
        # original price in reason
        assert "150.5" in result.modification_reasons_per_field["price"]

    def test_quarantine_strategy_blocks_without_correction(self):
        row = {"product_type": "shoes", "price": 200.0}
        result = self.quarantine_rule.apply(row)

        # No auto-correction
        assert result.corrections == {}
        assert result.modification_reasons_per_field == {}

    def test_missing_price_does_not_alert(self):
        row = {"product_type": "shoes"}  # no price key
        result = self.cap_rule.apply(row)
        assert result.issues is None
        assert result.corrections == {}


class TestAutoSlugify:
    @pytest.mark.parametrize("input_name, expected", [
        ("MyCoolRule", "my-cool-rule"),
        ("SimpleTest", "simple-test"),
        ("Rule", "rule"),
        ("A", "a"),
        ("XMLParser", "xml-parser"),
        ("HTTPRequest", "http-request"),
        ("Rule2Test", "rule2-test"),
        ("My2ndExample", "my2nd-example"),
    ])
    def test_camel_case_and_acronyms(self, input_name, expected):
        assert _auto_slugify(input_name) == expected

    @pytest.mark.parametrize("input_name, expected", [
        ("already-slug", "already-slug"),
        ("lowercase", "lowercase"),
    ])
    def test_all_lowercase_and_hyphens_unchanged(self, input_name, expected):
        assert _auto_slugify(input_name) == expected

    def test_empty_string(self):
        assert _auto_slugify("") == ""

    @pytest.mark.parametrize("input_name, expected", [
        ("Mixed_SepTest", "mixed_sep-test"),
        ("Test_With123NumbersABC", "test_with123-numbers-abc"),
    ])
    def test_mixed_separators_and_numbers(self, input_name, expected):
        assert _auto_slugify(input_name) == expected

    @pytest.mark.parametrize("input_value", [
        None,
        123,
        ["NotAString"],
    ])
    def test_invalid_type_raises_type_error(self, input_value):
        with pytest.raises(TypeError):
            _auto_slugify(input_value)


class TestValidateSlug:
    @pytest.mark.parametrize("slug", [
        "my-cool-rule",
        "rule",
        "a",
        "xml-parser",
        "rule2-test",
        "ab3",
        "a1b2c3",
    ])
    def test_valid_slugs_pass(self, slug):
        _validate_slug(slug, "Unused")  # should not raise

    @pytest.mark.parametrize("slug", [
        "MyCoolRule",
        "my_cool_rule",
        "My Cool Rule",
        "ALLCAPS",
        "-leading-hyphen",
        "trailing-hyphen-",
        "double--hyphen",
        "123-starts-with-digit",
        "",
        "has space",
        "special!char",
    ])
    def test_invalid_slugs_raise(self, slug):
        with pytest.raises(ValueError, match="Invalid rule name"):
            _validate_slug(slug, "SomeClass")

    def test_error_message_includes_suggestion(self):
        with pytest.raises(ValueError, match="my-cool-rule") as exc_info:
            _validate_slug("MyCoolRule", "MyCoolRule")
        err = str(exc_info.value)
        assert VALID_SLUG_RE.pattern in err
        assert "Hint" in err


class TestExplicitNameValidation:
    def test_valid_explicit_name_accepted(self):
        class MyCustomRule(Rule):
            name = "my-custom-rule"
            metadata = RuleMetadata(release="0.0.1")
            class ParamsModel(BaseModel):
                pass
            def apply(self, row):
                return RuleResult()

        assert MyCustomRule.name == "my-custom-rule"

    def test_invalid_explicit_name_raises(self):
        with pytest.raises(ValueError, match="Invalid rule name"):
            class BadNameRule(Rule):
                name = "Not A Valid Slug"
                metadata = RuleMetadata(release="0.0.1")
                class ParamsModel(BaseModel):
                    pass
                def apply(self, row):
                    return RuleResult()

    def test_auto_generated_name_still_works(self):
        class AutoNameRule(Rule):
            metadata = RuleMetadata(release="0.0.1")
            class ParamsModel(BaseModel):
                pass
            def apply(self, row):
                return RuleResult()

        assert AutoNameRule.name == "auto-name-rule"

    def test_error_suggests_auto_slug(self):
        with pytest.raises(ValueError, match="commission-math-rule") as exc_info:
            class CommissionMathRule(Rule):
                name = "CommissionMathRule"
                metadata = RuleMetadata(release="0.0.1")
                class ParamsModel(BaseModel):
                    pass
                def apply(self, row):
                    return RuleResult()


class TestColumnMapping:
    @pytest.fixture(autouse=True)
    def setup(self):
        # same fixed UUID as other tests
        self.dataset_rule_id = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")

    def test_correction_mapping(self):
        # Map logical "price" → raw "cost"
        mapping = {"price": "cost"}
        rule = PriceShoesRule(
            self.dataset_rule_id,
            {"max_price": 100.0, "correction_strategy": "cap"},
            mapping,
        )

        raw_row = {"product_type": "shoes", "cost": 120.0}
        result = rule.check(raw_row)

        # Correction key should be remapped back to "cost"
        assert result.corrections == {"cost": 100.0}
        assert result.modification_reasons_per_field == {
            "cost": "Corrected price from 120.0 to 100.0"
        }

    def test_enrichment_mapping(self):
        # Define an inline rule that enriches "y" when "x" == "foo"
        class EnrichRule(Rule):
            metadata = RuleMetadata(release="0.0.1")
            class ParamsModel(BaseModel):
                pass

            def apply(self, row: dict[str, Any]) -> RuleResult:
                if row.get("x") == "foo":
                    return RuleResult(
                        enrichments={"y": "bar"},
                        modification_reasons_per_field={"y": "added bar"},
                    )
                return RuleResult()

        # Map logical "x"→raw "col_x", "y"→raw "col_y"
        mapping = {"x": "col_x", "y": "col_y"}
        rule = EnrichRule(self.dataset_rule_id, {}, mapping)

        raw_row = {"col_x": "foo"}
        result = rule.check(raw_row)

        # Enrichment key should be remapped back to "col_y"
        assert result.enrichments == {"col_y": "bar"}
        assert result.modification_reasons_per_field == {
            "col_y": "added bar"
        }
