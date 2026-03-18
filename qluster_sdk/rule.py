import re
import uuid
import enum
import hashlib
import random as _random
import uuid as _uuid
import sys as _sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone as _tz
from typing import Generic, Type, TypeVar, Any, Optional, ClassVar
from pydantic import BaseModel, Field, field_validator, ConfigDict
from packaging.version import Version, InvalidVersion

from qluster_sdk.row_proxy import RowProxy, RawRow, ColMap

# Type variable for pydantic params
ParamsT = TypeVar("ParamsT", bound=BaseModel)

# Alias mappings for compact wire serialization
_ISSUE_ALIASES = {
    "dataset_rule_id": "rid",
    "issue_reason": "r",
    "field_names": "f",
    "issue_pattern": "p",
    "suggested_values_per_field": "sv",
    "allowed_alert_actions": "a",
    "issue_type": "t",
    "severity": "s",
    "publisher": "pb",
}

_RR_ALIASES = {
    "issues": "i",
    "corrections": "c",
    "enrichments": "e",
    "modification_reasons_per_field": "m",
}


class EnumStrBase(enum.StrEnum):
    def __repr__(self):
        """Return a quoted representation for easy copy-paste in debugging sessions."""
        return f"'{self.name}'"

    def __str__(self):
        return self.name


class IssueSeverity(EnumStrBase):
    warning = "warning"
    blocker = "blocker"        # quarantines a row


class IssueType(EnumStrBase):
    validation = "validation"  # validation warnings that all other validation warnings are subclass of
    validation_problem = "validation_problem"  # When we have trouble validating something 
    rule_validation = "rule_validation"  # validation warnings that all other validation warnings are subclass of
    rule_bug = "rule_bug"  # A bug in the rule

    anomaly = "anomaly"  # An anomaly is detected. The user has the option to modify the value or declare this value as not an anomaly
    invalid_keyword = "invalid_keyword"
    not_nullable = "not_nullable"
    out_of_range = "out_of_range"
    required_field = "required_field"

    invalid_us_address_line = "invalid_us_address_line"  # Address line is invalid
    invalid_us_address_line2 = "invalid_us_address_line2"  # Address line is invalid
    invalid_us_full_address = "invalid_us_full_address"  # Full address is invalid
    invalid_us_city = "invalid_us_city"  # US City line is invalid
    invalid_uk_city = "invalid_uk_city"
    unknown_company_name = "unknown_company_name"  # validation for company name
    unknown_product_category = "unknown_product_category"  # validation for product category
    unknown_fabric_type = "unknown_fabric_type"
    unknown_week_day = "unknown_week_day"
    unknown_granularity = "unknown_granularity"
    unknown_cloth_sizing = "unknown_cloth_sizing"
    unknown_geometry_unit = "unknown_geometry_unit"
    unknown_mass_unit = "unknown_mass_unit"
    unknown_gender = "unknown_gender"
    unknown_material_phase = "unknown_material_phase"
    unknown_currency = "unknown_currency"
    unknown_car_body_type = "unknown_car_body_type"
    unknown_car_make = "unknown_car_make"
    unknown_country = "unknown_country"
    unknown_us_state = "unknown_us_state"
    unknown_us_district = "unknown_us_district"
    unknown_color = "unknown_color"
    unknown_brand = "unknown_brand"
    bad_looking_firstname = "bad_looking_firstname"
    bad_looking_lastname = "bad_looking_lastname"
    bad_looking_fullname = "bad_looking_fullname"
    unknown_time_unit = "unknown_time_unit"
    unknown_temprature_unit = "unknown_temprature_unit"
    invalid_us_zip = "invalid_us_zip"
    invalid_email = "invalid_email"
    invalid_upc = "invalid_upc"
    invalid_basic_upc = "invalid_basic_upc"
    invalid_gpc = "invalid_gpc"
    invalid_phone = "invalid_phone"
    invalid_no_area_code_phone = "invalid_no_area_code_phone"
    invalid_url = "invalid_url"
    invalid_url_array = "invalid_url_array"
    unknown_car_model = "unknown_car_model"
    unknown_car_model_for_make = "unknown_car_model_for_make"
    car_model_belongs_to_another_make = "car_model_belongs_to_another_make"
    unknown_apparel_size = "unknown_apparel_size"
    invalid_language = "invalid_language"




class RuleAlertAction(EnumStrBase):
    update_configs_to_recommended_value = "update_configs_to_recommended_value"  # if the alert has recommended_settings_value, we make it easy
    update_rule_param = "update_rule_param"  # For custom rules to update their params
    append_rule_param_list = "append_rule_param_list"  # For custom rules to add to the param when it is a list
    call_webhook = "call_webhook"  # For future
    other = "other"  # For the user to extend
    overwrite_value = "overwrite_value"
    overwrite_values_for_same_rule = "overwrite_values_for_same_rule"
    map_value = "map_value"
    ignore_issue_for_value = "ignore_issue_for_value"
    ignore_issue_for_pattern = "ignore_issue_for_pattern"


class Issue(BaseModel):
    """
    A single issue (alert or warning) raised by running a rule on one row.
    Alerts block the row; warnings do not.
    """
    model_config = ConfigDict(
        alias_generator=lambda f: _ISSUE_ALIASES.get(f, f),
        populate_by_name=True,
    )
    dataset_rule_id: uuid.UUID | None = Field(
        default=None,
        description="RuleInstance ID; None means system/infra issue not tied to a specific rule."
    )
    issue_reason: str = Field(
        ..., 
        description="Human-readable description of the issue shown to the SME."
    )
    field_names: list[str] = Field(
        ..., 
        description="The field(s) whose value(s) caused this issue."
    )
    publisher: str = Field(
        default="",
        description="What published the issue"
    )
    issue_pattern: Optional[str] = Field(
        default=None,
        description=(
            "Optional aggregation pattern. "
            "If provided, issues with the same pattern share an alert ID."
        )
    )
    suggested_values_per_field: dict[str, list[str]] = Field(
      default_factory=dict,
      description="For each field with an alert or warning, a static list of suggested values."
    )
    allowed_alert_actions: list[RuleAlertAction] | None = Field(default=None, description="optional per-issue override; if None → fall back to rule default")
    issue_type: IssueType = Field(default=IssueType.rule_validation, description="It has to be one of Qluster's supported issue types. In most cases you don't need to provide this.")
    severity: IssueSeverity = Field(default=IssueSeverity.blocker, description="Is this a warning or a blocker issue that causes an alert?")

    @field_validator("field_names", mode="before")
    @classmethod
    def _system_field_names(cls, v, info):
        data = info.data or {}
        if data.get("dataset_rule_id") is None:
            return []  # system/infra issue → not about a specific field
        return v or []


class RuleResult(BaseModel):
    """
    Outcome of applying a Rule to a single row.
    - If `alert_issue` then the row is not valid and it blocks the row.
    - `warning_issues` do not block.
    - `corrections` apply *before* `enrichments`.
    - `modification_reasons_per_field` joins correction + enrichment reasons.
    """
    model_config = ConfigDict(
        alias_generator=lambda f: _RR_ALIASES.get(f, f),
        populate_by_name=True,
    )
    issues: list[Issue] | None = Field(
        default=None,
        description="list of issues"
    )
    corrections: dict[str, Any] = Field(
        default_factory=dict,
        description="Field→new value mappings to apply first."
    )
    enrichments: dict[str, Any] = Field(
        default_factory=dict,
        description="Field→new value mappings to apply second."
    )
    modification_reasons_per_field: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Combined reason per field, e.g. "
            "'price': 'Corrected from 120 to 100'"
        )
    )

    def is_noop(self) -> bool:
        """
        Returns True if this result has no issues, corrections, enrichments, or modification reasons.
        Useful for determining if a rule result can be skipped entirely.
        """
        return not (self.issues or self.corrections or self.enrichments or self.modification_reasons_per_field)

    def dump_wire(self) -> dict:
        """
        Compact wire dict: alias keys, drop None/defaults/empties.
        Returns a dict suitable for JSON serialization with minimal bytes.
        """
        return self.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)

    @classmethod
    def load_wire(cls, blob: dict | str) -> "RuleResult":
        """
        Accept alias-keyed dict or JSON string.
        Reconstructs a RuleResult from compact wire format produced by ``dump_wire()``.

        Both aliased keys (``"i"``, ``"c"``, ``"e"``, ``"m"``) and full field names
        (``"issues"``, ``"corrections"``, etc.) are accepted, thanks to
        ``populate_by_name=True`` in the model config.

        This is mainly useful in tests; in production the platform deserializes
        wire dicts automatically via Pydantic model validation.
        """
        if isinstance(blob, str):
            return cls.model_validate_json(blob)
        return cls.model_validate(blob)


class RuleMetadata(BaseModel):
    """
    Declare which columns this rule reads, validates, corrects, or enriches.

    Column Naming and Mapping
    -------------------------
    The column names in this metadata are the names your rule code will use to
    access data via the RowProxy (e.g., ``row["price"]``). These are called
    "rule field names" or "generic column names".

    When a rule is attached to a dataset, a **column mapping** connects your
    rule field names to the actual dataset column names. There are two approaches:

    1. **Manual Mapping (Recommended for Production)**:
       When creating a DatasetRule via the API, you provide an explicit mapping:
       ``{"price": "product_price", "name": "item_name"}``
       This maps your rule's "price" field to the dataset's "product_price" column.

    2. **Auto Mapping (For Testing Only)**:
       The ``create_all_custom_rules_for_dataset`` method can auto-generate mappings.
       It assumes ``input_columns`` contain names that, when normalized, match
       the dataset column names. This works if:

       - You use raw header names: ``input_columns=["Product Price"]`` normalizes
         to ``"product_price"`` which matches the dataset column.
       - You use the wildcard ``"*"``: expands to all dataset column names with
         identity mapping.

       Auto-mapping does NOT work if you use arbitrary logical names like
       ``["price"]`` when the dataset has ``"product_price"``.

    Example
    -------
    If your dataset has columns ["product_price", "item_name"] and your rule
    uses logical names ["price", "name"], you must provide a manual mapping::

        rule_column_mapping = {
            "price": "product_price",  # rule's "price" → dataset's "product_price"
            "name": "item_name",       # rule's "name" → dataset's "item_name"
        }
    """
    release: str = Field(
        ...,
        description="Semantic version of this rule (e.g. '1.0.0')."
    )
    input_columns: list[str] = Field(
        default_factory=list,
        description=(
            "Column names this rule reads. These are the names your rule code uses "
            "to access data (e.g., row['price']). Use '*' to indicate all columns. "
            "When the rule is attached to a dataset, a column mapping connects these "
            "names to actual dataset columns. See class docstring for details."
        ),
    )
    validates_columns: list[str] = Field(
        default_factory=list,
        description="Column names this rule validates. Uses the same naming as input_columns.",
    )
    corrects_columns: list[str] = Field(
        default_factory=list,
        description="Column names this rule may correct. Uses the same naming as input_columns.",
    )
    enriches_columns: list[str] = Field(
        default_factory=list,
        description="Column names this rule may enrich/add. Uses the same naming as input_columns.",
    )

    allowed_alert_actions: list[RuleAlertAction] = Field(
        default_factory=lambda: [
            RuleAlertAction.map_value,
            RuleAlertAction.overwrite_value,
            RuleAlertAction.overwrite_values_for_same_rule,
            RuleAlertAction.ignore_issue_for_value,
        ],
        description="Static list of resolve actions enabled for this rule.",
    )

    # field_validator runs on author-submitted payload
    @field_validator("release")
    @classmethod
    def _valid_semver(cls, v: str) -> str:
        try:
            Version(v)                           # raises on bad input
        except InvalidVersion:
            # Validation code should not raise ValidationError itself ... raise a ValueError
            raise ValueError(f"Invalid semantic version: {v!r}")
        return v

SLUG_REGEX = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
VALID_SLUG_RE = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')


def _auto_slugify(name: str) -> str:
    """
    Convert CamelCase or PascalCase into lowercase, hyphen-separated words,
    but keep consecutive uppercase letters (acronyms) grouped together.

    E.g.:
      "MyCoolRule"   → "my-cool-rule"
      "XMLParser"    → "xml-parser"
      "HTTPRequest"  → "http-request"
      "Rule2Test"    → "rule2-test"
    """
    # Insert hyphen between:
    #  1) lowercase/digit and uppercase
    #  2) uppercase followed by uppercase+lowercase (acronym boundary)
    return SLUG_REGEX.sub('-', name).lower()


def _validate_slug(name: str, class_name: str) -> None:
    if VALID_SLUG_RE.match(name):
        return
    suggested = _auto_slugify(class_name)
    raise ValueError(
        f"Invalid rule name {name!r}: must be a valid slug matching "
        f"{VALID_SLUG_RE.pattern!r}.\n"
        f"  Hint: did you mean {suggested!r}? "
        f"(Remove the explicit `name` to auto-generate from the class name.)"
    )


class ExecutionContext:
    """Typed, read-only, replay-safe execution context available via self.ctx."""

    __slots__ = ("_now_utc", "_seed", "_uuid_namespace", "_locale", "_timezone", "_injected")

    def __init__(self, spec: dict[str, Any], *, injected: bool = True) -> None:
        # Parse and normalize to UTC-aware datetime
        dt = datetime.fromisoformat(spec["now_utc"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        self._now_utc = dt
        self._seed = int(spec.get("seed", 0))
        ns = spec.get("uuid_namespace")
        if ns is not None:
            _uuid.UUID(ns)  # validate; raises ValueError on bad input
        self._uuid_namespace = ns
        self._locale = spec.get("locale", "en_US")
        self._timezone = spec.get("timezone", "UTC")
        self._injected = injected

    @property
    def injected(self) -> bool:
        """True if ctx was injected by the execution pipeline, False if lazy-created."""
        return self._injected

    @property
    def now_utc(self) -> datetime:
        """Pinned UTC timestamp for this job. Use instead of datetime.now()."""
        return self._now_utc

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def locale(self) -> str:
        return self._locale

    @property
    def timezone(self) -> str:
        return self._timezone

    def rng_for(self, key: str, stream: str = "default") -> _random.Random:
        """Deterministic RNG seeded per (key, stream). Independent of row order.

        Args:
            key: Stable row identifier (e.g. initial_signature_ or a field value).
            stream: Named stream to separate independent RNG uses.
        """
        seed_bytes = hashlib.blake2b(
            f"{self._seed}|{stream}|{key}".encode(), digest_size=8
        ).digest()
        return _random.Random(int.from_bytes(seed_bytes, "little"))

    def uuid_for(self, *parts: str, stream: str = "default") -> _uuid.UUID:
        """Deterministic UUID5 derived from namespace + parts. Replay-safe.

        Args:
            parts: Strings combined to form the UUID name (e.g. field values).
            stream: Named stream to separate independent UUID uses.
        """
        ns = _uuid.UUID(self._uuid_namespace) if self._uuid_namespace else _uuid.NAMESPACE_DNS
        name = stream + "|" + "|".join(parts)
        return _uuid.uuid5(ns, name)


class Rule(ABC, Generic[ParamsT]):
    """
    Base class for validation / correction / enrichment rules.
    Subclasses must provide:
      • ParamsModel: subclass of BaseModel defining typed params
      • metadata: an instance of RuleMetadata
      • apply(): the per-row logic
    """
    ParamsModel: Type[ParamsT]
    metadata: RuleMetadata
    name: ClassVar[str]


    def __init_subclass__(cls) -> None:
        """
        We need to set or override `name` at the class level (i.e. as soon as the subclass is defined),
        not once an instance is created. `__init_subclass__` runs exactly when Python
        finishes building the subclass, so it can inject a default `name` into `cls.__dict__`
        before anyone ever calls `Rule(...)`. By contrast, `__init__` only runs when
        you do `r = MyRule(dataset_rule_id, params)`, which is too late—at that point you already needed
        `MyRule.name` to exist (for registration, submission, etc.).
        """
        super().__init_subclass__()
        # If the subclass did not set a `name` attribute, auto-generate it
        if 'name' not in cls.__dict__:
            cls.name = _auto_slugify(cls.__name__)
        else:
            _validate_slug(cls.name, cls.__name__)

    def __init__(
        self,
        dataset_rule_id: uuid.UUID,
        params:  dict[str, Any],
        rule_column_mapping: ColMap | None = None,
    ) -> None:
        """
        Initialize a rule instance.

        Parameters
        ----------
        dataset_rule_id : uuid.UUID
            Unique identifier for this rule instance (DatasetRule.id).
        params : dict[str, Any]
            Rule parameters, validated against ParamsModel.
        rule_column_mapping : ColMap | None
            Maps rule field names to dataset column names.

            The mapping direction is: **rule_field_name → dataset_column_name**

            Example: If your rule uses ``row["price"]`` but the dataset has
            a column named ``"product_price"``, provide::

                rule_column_mapping = {"price": "product_price"}

            When ``row["price"]`` is accessed, RowProxy will look up
            ``colmap.get("price", "price")`` = ``"product_price"`` and return
            ``raw_row["product_price"]``.

            If None or empty, identity mapping is used (rule field names must
            match dataset column names exactly).
        """
        self.dataset_rule_id             = dataset_rule_id
        self.params: ParamsT     = self.ParamsModel.model_validate(params)
        # default to empty → identity for all keys
        self.rule_column_mapping = rule_column_mapping or {}
        self._execution_context: ExecutionContext | None = None

    _ctx_fallback_warned: bool = False  # class-level

    @property
    def ctx(self) -> ExecutionContext:
        """Job-scoped execution context. Use self.ctx.now_utc instead of datetime.now()."""
        if self._execution_context is None:
            if not self.__class__._ctx_fallback_warned:
                print(
                    f"WARNING: {self.__class__.__name__} using fallback ExecutionContext "
                    f"(not pipeline-injected)",
                    file=_sys.stderr,
                )
                self.__class__._ctx_fallback_warned = True
            self._execution_context = ExecutionContext({
                "now_utc": datetime.now(_tz.utc).isoformat(),
                "seed": 0,
                "locale": "en_US",
                "timezone": "UTC",
            }, injected=False)
        return self._execution_context

    @abstractmethod
    def apply(self, row: RowProxy) -> RuleResult:
        """
        Run your existing logic against `row`. Here, `row[key]`
        is already remapped via RowProxy if you call `check()`.
        """
        ...

    def _remap_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        return {
            self.rule_column_mapping.get(k, k): v
            for k, v in d.items()
        }

    def _remap_list(self, items: list[str]) -> list[str]:
        return [self.rule_column_mapping.get(k, k) for k in items]

    def check(self, raw_row: RawRow) -> RuleResult:
        """
        1) Wrap raw_row in RowProxy → lazy key‐mapping
        2) Call existing apply()
        3) Remap the tiny corrections/enrichments dicts back
           to the real column names in one pass.
        """
        proxy  = RowProxy(raw_row, self.rule_column_mapping)
        result = self.apply(proxy)
        if result.issues:
            for issue in result.issues:
                if issue.dataset_rule_id is not None:  # only remap for rule-scoped issues
                    issue.field_names = self._remap_list(issue.field_names)

        result.corrections  = self._remap_dict(result.corrections)
        result.enrichments  = self._remap_dict(result.enrichments)
        result.modification_reasons_per_field = self._remap_dict(
            result.modification_reasons_per_field
        )

        return result

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} {self.rule_column_mapping} {self.params} dataset_rule_id={str(self.dataset_rule_id)[:6]}...>"

    __repr__ = __str__
