# Qluster SDK 2.126.0

The Qluster SDK lets you write custom **validation**, **correction**, and **enrichment** rules that run inside the Qluster data pipeline. You subclass `Rule`, declare metadata and typed parameters, and implement an `apply()` method that inspects each row and returns a `RuleResult`.

## Installation

```bash
pip install qluster_sdk
```

## Quick Start

Save the rule as `price_shoes_rule.py`:

```python
from pydantic import BaseModel, Field
from qluster_sdk import Issue, Rule, RuleMetadata, RuleResult


# 1. Define typed parameters for your rule
class PriceShoesParams(BaseModel):
    max_price: float = Field(..., description="Any price >= this will be flagged.")
    correction_strategy: str = Field(
        "cap", description="Either 'cap' or 'quarantine'"
    )


# 2. Subclass Rule
class PriceShoesRule(Rule[PriceShoesParams]):
    """Flags shoes priced above a threshold; optionally caps the price."""

    business_summary = (
        "Flags shoes priced at or above the maximum price and, unless the "
        "strategy is 'quarantine', caps the price at that maximum."
    )
    limitations = "Checks only rows whose product_type is exactly 'shoes'."

    metadata = RuleMetadata(
        release="0.0.1",
        input_columns=["product_type", "price"],
        validates_columns=["price"],
        corrects_columns=["price"],
        column_field_types={
            "product_type": ["String", "Text"],
            "price": ["Decimal", "Float", "Integer"],
        },
    )
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
```

Run it locally:

```python
import uuid

rule = PriceShoesRule(
    dataset_rule_id=uuid.uuid4(),
    params={"max_price": 100.0, "correction_strategy": "cap"},
)
result = rule.check({"product_type": "shoes", "price": 150.0})
print(result.corrections)  # {'price': 100.0}
```

Submit it with `qctl submit rules -f price_shoes_rule.py`.

## Key Concepts

### Rule

The base class for all rules. Every rule must define:

- **`metadata`** -- a `RuleMetadata` instance declaring the rule's semantic version, which columns it reads, validates, corrects, or enriches, the field types it accepts in each column it reads, the allowed alert actions, and `default_severity` (default `as_declared`) -- set it to `warning` for a rule whose issues must never quarantine a row, or `blocker` for one whose every issue must. See [Rule metadata](#rule-metadata).
- **`business_summary`** -- the rule in plain English, for business users. Defining a `Rule` subclass without one raises `ValueError`.
- **`apply(row) -> RuleResult`** -- the per-row logic. Access columns via `row["field_name"]` or `row.get("field_name")`.

A rule may also define:

- **`ParamsModel`** -- a Pydantic `BaseModel` subclass that declares the rule's configuration parameters. Subclass `Rule[YourParams]` so `self.params` is typed. A rule without parameters omits it.
- **`limitations`** -- where the rule is heuristic, approximate, or depends on incomplete data.

Write `business_summary` and `limitations` as string literals: the server reads them from the source, as it reads `metadata`.

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

## Rule metadata

`metadata = RuleMetadata(...)` declares the rule's release, the columns it reads and writes, the field types it accepts and its defaults.

### Write metadata as literals

`qctl submit rules` does not import your file. The server reads each `RuleMetadata(...)` keyword from the source and builds a `RuleMetadata` from the values it read, so the model's validators run at submit. A keyword that is not a literal cannot be read: the server answers 422 and stores no rule from the file. A file that imports and runs locally can still be rejected this way.

These read as literals:

- strings, numbers, `True`, `False` and `None`
- list, tuple and dict literals whose items are literals
- calls with keyword arguments only, such as `EnrichedFieldSchema(type="Decimal", is_nullable=True)`, when every argument is a literal
- `RuleSeverity.<member>` and `RuleAlertAction.<member>`, written with those class names

These do not:

- calls to your own helpers: `column_field_types=_any("product_type", "price")`
- comprehensions: `{col: "any" for col in COLUMNS}`
- module-level names: `column_field_types=PRICE_TYPES`
- `**kwargs`: `RuleMetadata(**COMMON)`
- calls with positional arguments: `EnrichedFieldSchema("Decimal")`
- expressions, such as `"0.0." + "1"` or an f-string
- enum members reached through a module or an alias: `qluster_sdk.RuleSeverity.warning`, `RS.warning`

A call with keyword arguments only reads as a dict of those arguments, whatever it calls: `_types(price="any")` reads as `{"price": "any"}`, not as what `_types` returns.

Assign `metadata` a `RuleMetadata(...)` call, or a dict literal, directly in the class body. `metadata = make_metadata()` and `metadata = SHARED_METADATA` cannot be read either, and are rejected the same way, as is a rule with no `metadata` or no `release`.

The rejection names the rule class, and the keywords when those are what cannot be read:

```text
PriceShoesRule: metadata keyword(s) column_field_types, column_concepts are not literals; declare them inline so they can be validated here
PriceShoesRule: metadata is not a RuleMetadata(...) call or dict literal; declare it inline so it can be validated here
```

Before (rejected):

```python
CONCEPTS = {"product_type": "category", "price": "asking_price"}


def _any(*cols):
    return {col: "any" for col in cols}


class PriceShoesRule(Rule[PriceShoesParams]):
    metadata = RuleMetadata(
        release="0.0.1",
        input_columns=["product_type", "price"],
        column_field_types=_any("product_type", "price"),
        column_concepts=CONCEPTS,
    )
```

After (accepted):

```python
class PriceShoesRule(Rule[PriceShoesParams]):
    metadata = RuleMetadata(
        release="0.0.1",
        input_columns=["product_type", "price"],
        column_field_types={
            "product_type": ["String", "Text"],
            "price": ["Decimal", "Float", "Integer"],
        },
        column_concepts={
            "product_type": "category",
            "price": "asking_price",
        },
    )
```

### `column_field_types`

Every read-side column needs an entry: each column in `input_columns`, `validates_columns` or `corrects_columns`, except `"*"`.

- The keys are exactly the read-side columns. A missing or an extra key is rejected.
- Each value is a non-empty list of names from `qluster_sdk.FIELD_TYPE_NAMES` (`String`, `Text`, `UUID`, `SmallInteger`, `Integer`, `BigInteger`, `Decimal`, `Float`, `DateTime`, `Date`, `Boolean`, `Array`, `BigIntArray`, `IntArray`, `SmallIntArray`, `UUIDArray`, `Json`, `Jsonb`, `Bytea`, `Varbit`), or the string `"any"`.
- Columns in `enriches_columns` are typed by `enriched_field_schemas` instead, which needs an entry for each of them. List an enriched column in `column_field_types` only if the rule also reads it.
- A column the rule both reads and enriches must accept the type it produces: its list includes `enriched_field_schemas[col].type`, or it is `"any"`.

Declare the column lists yourself. A list left empty is inferred from the code at submit, and an inferred column is stored without a type.

The types are stored with the revision and returned as its `affected_column_types`. The UI's column matching and `qctl` show them next to each rule field when a user maps the rule's fields to table columns. Nothing enforces them: the user can map a column of any type, and at run time the rule gets whatever values the mapped column holds.

- List every type your code handles. A rule that parses values itself, such as dates or numbers from text, lists `String` and `Text` next to the native types: `["Date", "DateTime", "String", "Text"]`.
- Keep `"any"` for a rule that handles any value, such as a presence check. It tells the person mapping columns nothing.

### `optional_columns` and `column_concepts`

- `optional_columns` lists read-side columns a table rule may leave unmapped. Each must be in `input_columns` or `validates_columns`; `"*"` and corrected or enriched columns are rejected. Inside `apply()`, an unmapped optional column reads as absent: `row.get(name)` returns the default.
- `column_concepts` maps a rule field to the slug of a concept defined in the organization that submits the rule: `{"price": "asking_price"}`. Each key must be a column in `input_columns`, `validates_columns`, `corrects_columns` or `enriches_columns`, other than `"*"`, and each value must match `^[a-z][a-z0-9]*([_-][a-z0-9]+)*$`. A field the map does not list is generic, so a map may list only some fields, or none. An organization admin creates concepts; a submit that names a concept slug the organization does not have is rejected.

### Unknown keywords are rejected

`qctl submit rules` rejects a keyword `RuleMetadata` does not define: the server answers 422, stores no rule from the file, and names the keyword and, if one is close, the field you may have meant:

```text
PriceShoesRule: unknown metadata keyword(s) input_colums; did you mean input_columns?
```

When your class is defined, `RuleMetadata` drops such a keyword without a warning, so a file that imports and runs locally can still be rejected this way.

`default_treat_as_alert` is retired: write `default_severity=RuleSeverity.warning` in place of `default_treat_as_alert=False`, and delete `default_treat_as_alert=True` (the default, `RuleSeverity.as_declared`, behaves the same).

A file whose rule declares an unknown keyword is rejected even when that rule has not changed since you last submitted it. Remove the keyword. That changes the rule's code, so if its revision at that release is `enabled` or `disabled`, bump the `release` (see [Releases](#releases)).

### Releases

Each submit compares every rule in the file with that rule's revision at the same `release`:

| Revision at that release | Result |
|---|---|
| none | A new revision is stored. |
| same code | Nothing changes; the rule is reported as not changed. |
| different code, state `draft` or `in_review` | The revision is updated in place. |
| different code, state `enabled` or `disabled` | The submit is refused: "... cannot be modified. Bump the release to create a new revision." |

The code compared is the rule's source, metadata included, so a metadata-only change is a change. If your organization does not require rule review, a new revision is `enabled` as soon as it is stored, and every later change needs a new `release`.

`qctl submit rules --force` skips a changed `enabled` or `disabled` revision instead of refusing the submit. It never overwrites the revision.

Every revision of a rule declares the same set of columns: the union of `input_columns`, `validates_columns`, `corrects_columns` and `enriches_columns`, ignoring `"*"`. A revision that adds or drops a column is refused.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT -- see [LICENSE](LICENSE) for details.
