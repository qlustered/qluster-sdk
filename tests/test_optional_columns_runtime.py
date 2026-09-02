import uuid

import pytest
from pydantic import BaseModel

from qluster_sdk.exceptions import CellNotFound
from qluster_sdk.row_proxy import RowProxy
from qluster_sdk.rule import Rule, RuleMetadata, RuleResult


# --------------------------- RowProxy unit tests ------------------------- #

def test_absent_key_get_returns_default_even_on_name_collision():
    # The raw row REALLY contains a column named "value_2" — without
    # absent_keys, the identity fallback would silently return 99.
    proxy = RowProxy(
        {"amount": 10, "value_2": 99},
        {"value": "amount"},
        absent_keys=frozenset({"value_2"}),
    )
    assert proxy.get("value_2") is None
    assert proxy.get("value_2", "fallback") == "fallback"


def test_absent_key_getitem_raises_cell_not_found():
    proxy = RowProxy({"value_2": 99}, {}, absent_keys=frozenset({"value_2"}))
    with pytest.raises(CellNotFound):
        proxy["value_2"]


def test_absent_key_not_contained():
    proxy = RowProxy({"value_2": 99}, {}, absent_keys=frozenset({"value_2"}))
    assert "value_2" not in proxy


def test_non_absent_keys_unaffected():
    proxy = RowProxy(
        {"amount": 10}, {"value": "amount"}, absent_keys=frozenset({"value_2"})
    )
    assert proxy["value"] == 10
    assert proxy.get("value") == 10
    assert "value" in proxy


def test_absent_keys_defaults_to_empty_backward_compatible():
    proxy = RowProxy({"value_2": 99}, {})
    assert proxy["value_2"] == 99  # identity fallback unchanged when not declared absent


# ----------------------- Rule.check() integration ------------------------ #

class _P(BaseModel):
    pass


class TwoOperandRule(Rule[_P]):
    metadata = RuleMetadata(
        release="1.0.0",
        input_columns=["value", "value_2"],
        validates_columns=["value"],
        optional_columns=["value_2"],
    )
    business_summary = "Compares value to value_2 when bound."
    ParamsModel = _P

    def apply(self, row):
        self.seen = row.get("value_2")
        self.bound = "value_2" in row
        return RuleResult()


def test_unbound_optional_reads_none_despite_colliding_dataset_column():
    rule = TwoOperandRule(uuid.uuid4(), {}, {"value": "amount"})  # value_2 unbound
    rule.check({"amount": 5, "value_2": 99})  # dataset column literally named value_2
    assert rule.seen is None
    assert rule.bound is False


def test_bound_optional_reads_mapped_value():
    rule = TwoOperandRule(uuid.uuid4(), {}, {"value": "amount", "value_2": "other"})
    rule.check({"amount": 5, "other": 7})
    assert rule.seen == 7
    assert rule.bound is True


def test_rule_without_metadata_attribute_still_checks():
    # Defensive: Rule.check must not require class metadata to exist.
    class NoMetaRule(Rule[_P]):
        business_summary = "No metadata."
        ParamsModel = _P

        def apply(self, row):
            self.seen = row.get("anything")
            return RuleResult()

    rule = NoMetaRule(uuid.uuid4(), {}, {})
    rule.check({"anything": 1})
    assert rule.seen == 1


# ------------------- Mapping-iteration absent-key consistency ------------- #

def _collision_proxy() -> RowProxy:
    # The raw row REALLY contains a column named "value_2"; the rule declared
    # "value_2" optional and left it unbound.
    return RowProxy(
        {"amount": 10, "value_2": 99},
        {"value": "amount"},
        absent_keys=frozenset({"value_2"}),
    )


def test_iter_skips_absent_colliding_key():
    assert list(_collision_proxy()) == ["amount"]


def test_len_agrees_with_iteration():
    proxy = _collision_proxy()
    assert len(proxy) == 1
    assert len(proxy) == len(list(proxy))


def test_items_and_dict_do_not_raise_on_collision_row():
    proxy = _collision_proxy()
    assert dict(proxy) == {"amount": 10}
    assert dict(proxy.items()) == {"amount": 10}
    assert list(proxy.values()) == [10]


def test_keys_view_agrees_with_contains():
    proxy = _collision_proxy()
    assert list(proxy.keys()) == ["amount"]
    assert "value_2" not in proxy.keys()
    assert ("value_2" in proxy) == ("value_2" in list(proxy)) == False


def test_mapping_eq_ignores_absent_colliding_key():
    assert _collision_proxy() == {"amount": 10}


def test_absent_key_not_in_raw_leaves_iteration_untouched():
    # Absent name that does NOT collide with a raw column: nothing to skip.
    proxy = RowProxy(
        {"amount": 10}, {"value": "amount"}, absent_keys=frozenset({"value_2"})
    )
    assert list(proxy) == ["amount"]
    assert len(proxy) == 1


def test_iteration_unchanged_when_no_absent_keys():
    # Pin the empty-absent fast path: raw-namespace iteration, order preserved.
    proxy = RowProxy({"amount": 10, "value_2": 99}, {"value": "amount"})
    assert list(proxy) == ["amount", "value_2"]
    assert len(proxy) == 2
    assert dict(proxy) == {"amount": 10, "value_2": 99}


class IteratingRule(Rule[_P]):
    metadata = RuleMetadata(
        release="1.0.0",
        input_columns=["value", "value_2"],
        validates_columns=["value"],
        optional_columns=["value_2"],
    )
    business_summary = "Snapshots the whole row via Mapping iteration."
    ParamsModel = _P

    def apply(self, row):
        self.snapshot = dict(row)
        return RuleResult()


def test_rule_iterating_proxy_survives_collision_row():
    rule = IteratingRule(uuid.uuid4(), {}, {"value": "amount"})  # value_2 unbound
    rule.check({"amount": 5, "value_2": 99})  # dataset column literally named value_2
    assert rule.snapshot == {"amount": 5}
