# Qluster SDK

The Qluster SDK lets you write custom **validation**, **correction**, and **enrichment** rules that run inside the Qluster data pipeline. You subclass `Rule`, declare metadata and typed parameters, and implement an `apply()` method that inspects each row and returns a `RuleResult`.

## Installation

```bash
pip install qluster_sdk
```

## Quick Start

```python
import uuid
from pydantic import BaseModel, Field
from qluster_sdk import Rule, RuleMetadata, RuleResult, Issue


# 1. Define typed parameters for your rule
class PriceShoesParams(BaseModel):
    max_price: float = Field(..., description="Any price >= this will be flagged.")
    correction_strategy: str = Field(
        "cap", description="Either 'cap' or 'quarantine'"
    )


# 2. Subclass Rule
class PriceShoesRule(Rule):
    """Flags shoes priced above a threshold; optionally caps the price."""

    metadata = RuleMetadata(release="0.0.1")
    ParamsModel = PriceShoesParams

    def apply(self, row) -> RuleResult:
        price = row.get("price")
        ptype = row.get("product_type")

        if ptype == "shoes" and price is not None and price >= self.params.max_price:
            reason = f"Price {price} exceeds maximum {self.params.max_price}"
            issue = Issue(
                dataset_rule_id=self.dataset_rule_id,
                issue_reason=reason,
                field_names=["price"],
            )

            corrections = {}
            mods = {}
            if self.params.correction_strategy == "cap":
                capped = self.params.max_price
                corrections["price"] = capped
                mods["price"] = f"Corrected price from {price} to {capped}"

            return RuleResult(
                issues=[issue],
                corrections=corrections,
                modification_reasons_per_field=mods,
            )

        return RuleResult()


# 3. Instantiate and run
rule = PriceShoesRule(
    dataset_rule_id=uuid.uuid4(),
    params={"max_price": 100.0, "correction_strategy": "cap"},
)
result = rule.check({"product_type": "shoes", "price": 150.0})
print(result.corrections)  # {"price": 100.0}
```

## Key Concepts

### Rule

The base class for all rules. Every rule must define:

- **`ParamsModel`** -- a Pydantic `BaseModel` subclass that declares the rule's configuration parameters.
- **`metadata`** -- a `RuleMetadata` instance declaring the rule's semantic version, which columns it reads, validates, corrects, or enriches, and the allowed alert actions.
- **`apply(row) -> RuleResult`** -- the per-row logic. Access columns via `row["field_name"]` or `row.get("field_name")`.

The rule's **name** is auto-generated from the class name (e.g. `PriceShoesRule` becomes `"price-shoes-rule"`). You can set it explicitly with a class attribute `name = "my-rule"`.

### RuleResult

Returned by `apply()`. Contains:

- **`issues`** -- list of `Issue` objects (blockers or warnings).
- **`corrections`** -- `dict[str, Any]` of field-to-new-value mappings applied first.
- **`enrichments`** -- `dict[str, Any]` of field-to-new-value mappings applied second.
- **`modification_reasons_per_field`** -- `dict[str, str]` explaining each modification.

### Issue

Describes a single problem found in a row:

- **`issue_reason`** -- human-readable description shown to the SME.
- **`field_names`** -- which field(s) caused the issue.
- **`severity`** -- `IssueSeverity.blocker` (quarantines the row) or `IssueSeverity.warning`.
- **`issue_type`** -- categorizes the issue (default: `IssueType.rule_validation`).
- **`suggested_values_per_field`** -- optional suggestions for each field.
- **`allowed_alert_actions`** -- optional per-issue override of the rule's default alert actions.

### RowProxy and Column Mapping

Rules access data through a `RowProxy`, which transparently remaps logical field names to actual dataset column names. When creating a rule instance, pass a `rule_column_mapping`:

```python
mapping = {"price": "product_price", "name": "item_name"}
rule = MyRule(dataset_rule_id, params, rule_column_mapping=mapping)

# In apply(), row["price"] returns the value from the "product_price" column
result = rule.check(raw_row)
```

Call `rule.check(raw_row)` (not `apply()` directly) to get automatic column remapping on both input and output.

### ExecutionContext

Available as `self.ctx` inside `apply()`. Provides deterministic, replay-safe utilities:

- **`self.ctx.now_utc`** -- pinned UTC timestamp for the job. Use instead of `datetime.now()`.
- **`self.ctx.seed`** -- integer seed for deterministic randomness.
- **`self.ctx.rng_for(key, stream)`** -- deterministic `random.Random` instance.
- **`self.ctx.uuid_for(*parts, stream)`** -- deterministic UUID5 generation.
- **`self.ctx.locale`** / **`self.ctx.timezone`** -- locale and timezone for the job.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT -- see [LICENSE](LICENSE) for details.
