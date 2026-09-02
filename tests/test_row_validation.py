import pytest
import uuid
from typing import Any
from pydantic import BaseModel, Field
from qluster_sdk.rule import Rule, RuleMetadata, RuleResult, Issue, ProblemDomainBinding, _auto_slugify, _validate_slug, VALID_SLUG_RE

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
    business_summary = "Flags shoes priced above the allowed maximum and optionally caps the price to the limit."
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
        assert PriceShoesRule.name == "PriceShoesRule"
        assert PriceShoesRule.slug == "price-shoes-rule"

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
            name = "My Custom Rule"
            metadata = RuleMetadata(release="0.0.1")
            business_summary = "Test rule with explicit name."
            class ParamsModel(BaseModel):
                pass
            def apply(self, row):
                return RuleResult()

        assert MyCustomRule.name == "My Custom Rule"
        assert MyCustomRule.slug == "my-custom-rule"

    def test_invalid_explicit_slug_raises(self):
        with pytest.raises(ValueError, match="Invalid rule name"):
            class BadSlugRule(Rule):
                slug = "Not A Valid Slug"
                metadata = RuleMetadata(release="0.0.1")
                class ParamsModel(BaseModel):
                    pass
                def apply(self, row):
                    return RuleResult()

    def test_auto_generated_name_still_works(self):
        class AutoNameRule(Rule):
            metadata = RuleMetadata(release="0.0.1")
            business_summary = "Test rule with auto-generated name."
            class ParamsModel(BaseModel):
                pass
            def apply(self, row):
                return RuleResult()

        assert AutoNameRule.name == "AutoNameRule"
        assert AutoNameRule.slug == "auto-name-rule"

    def test_error_suggests_auto_slug(self):
        with pytest.raises(ValueError, match="commission-math-rule"):
            class CommissionMathRule(Rule):
                slug = "CommissionMathRule"
                metadata = RuleMetadata(release="0.0.1")
                class ParamsModel(BaseModel):
                    pass
                def apply(self, row):
                    return RuleResult()


class TestProblemDomainBinding:
    def test_valid_single_binding(self):
        m = RuleMetadata(
            release="1.0.0",
            validates_columns=["Gross Amount", "Agency Comm Amount"],
            problem_domain_bindings=[
                ProblemDomainBinding(
                    problem_domain_slug="broker-commission-bordereau",
                    field_kind_slug_by_rule_field={
                        "Gross Amount": "gross_amount",
                        "Agency Comm Amount": "agency_comm_amount",
                    },
                ),
            ],
        )
        assert len(m.problem_domain_bindings) == 1
        assert m.problem_domain_bindings[0].problem_domain_slug == "broker-commission-bordereau"

    def test_valid_multiple_bindings(self):
        m = RuleMetadata(
            release="1.0.0",
            validates_columns=["col-a"],
            problem_domain_bindings=[
                ProblemDomainBinding("kind-one", {"col-a": "field-a"}),
                ProblemDomainBinding("kind-two", {"col-a": "field-b"}),
            ],
        )
        assert len(m.problem_domain_bindings) == 2

    def test_empty_bindings_allowed(self):
        m = RuleMetadata(release="1.0.0", validates_columns=["col-a"])
        assert m.problem_domain_bindings == []

    def test_invalid_problem_domain_slug(self):
        with pytest.raises(ValueError, match="Invalid dataset kind slug"):
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col"],
                problem_domain_bindings=[
                    ProblemDomainBinding("INVALID_SLUG", {"col": "ok"}),
                ],
            )

    def test_invalid_field_kind_slug(self):
        with pytest.raises(ValueError, match="Invalid dataset field kind slug"):
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col"],
                problem_domain_bindings=[
                    ProblemDomainBinding("valid-kind", {"col": "BAD SLUG"}),
                ],
            )

    def test_duplicate_problem_domain_slug(self):
        with pytest.raises(ValueError, match="Duplicate dataset kind binding"):
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col"],
                problem_domain_bindings=[
                    ProblemDomainBinding("same-kind", {"col": "slug-a"}),
                    ProblemDomainBinding("same-kind", {"col": "slug-b"}),
                ],
            )

    def test_missing_affected_columns(self):
        with pytest.raises(ValueError, match="missing field-kind bindings for affected columns"):
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col-a", "col-b"],
                problem_domain_bindings=[
                    ProblemDomainBinding("my-kind", {"col-a": "slug-a"}),
                ],
            )

    def test_extra_unknown_field_names(self):
        with pytest.raises(ValueError, match="unknown rule field names"):
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col-a"],
                problem_domain_bindings=[
                    ProblemDomainBinding("my-kind", {"col-a": "slug-a", "extra": "slug-x"}),
                ],
            )

    def test_affected_columns_across_all_column_types(self):
        """Bindings must cover all affected columns (input + validates + corrects + enriches)."""
        m = RuleMetadata(
            release="1.0.0",
            input_columns=["inp"],
            validates_columns=["val"],
            corrects_columns=["cor"],
            enriches_columns=["enr"],
            problem_domain_bindings=[
                ProblemDomainBinding("my-kind", {
                    "inp": "slug-inp",
                    "val": "slug-val",
                    "cor": "slug-cor",
                    "enr": "slug-enr",
                }),
            ],
        )
        assert set(m.affected_columns) == {"inp", "val", "cor", "enr"}
        assert len(m.problem_domain_bindings) == 1

    def test_missing_affected_column_names_in_error(self):
        """Error message should name the missing columns."""
        with pytest.raises(ValueError, match="col-b") as exc_info:
            RuleMetadata(
                release="1.0.0",
                validates_columns=["col-a", "col-b"],
                problem_domain_bindings=[
                    ProblemDomainBinding("my-kind", {"col-a": "slug-a"}),
                ],
            )
        assert "my-kind" in str(exc_info.value)

    def test_binding_is_namedtuple(self):
        b = ProblemDomainBinding("my-kind", {"col": "slug"})
        assert b.problem_domain_slug == "my-kind"
        assert b.field_kind_slug_by_rule_field == {"col": "slug"}
        # NamedTuple indexing
        assert b[0] == "my-kind"
        assert b[1] == {"col": "slug"}

    def test_rule_class_with_bindings(self):
        """ProblemDomainBinding works correctly when used in a Rule subclass."""
        class MyParams(BaseModel):
            pass

        class MyRule(Rule[MyParams]):
            metadata = RuleMetadata(
                release="1.0.0",
                validates_columns=["amount"],
                problem_domain_bindings=[
                    ProblemDomainBinding("broker-commission-bordereau", {"amount": "gross_amount"}),
                ],
            )
            ParamsModel = MyParams
            business_summary = "Test rule."

            def apply(self, row):
                return RuleResult()

        assert len(MyRule.metadata.problem_domain_bindings) == 1


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
            business_summary = "Enriches column y with a derived value when column x matches a target."
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
