from collections.abc import Mapping
from typing import Any
from copy import deepcopy
from qluster_sdk.exceptions import CellNotFound

RawRow = dict[str, Any]
ColMap = dict[str, str]
"""
Column mapping type: maps rule field names to dataset column names.

The mapping direction is: **rule_field_name → dataset_column_name**

Example::

    colmap = {"price": "product_price", "name": "item_name"}

With this mapping, when a rule does ``row["price"]``, RowProxy will
return ``raw_row["product_price"]``.
"""


class RowProxy(Mapping[str, Any]):
    """
    A read-only view of a data row that transparently remaps column names.

    This allows rules to use their own logical field names (e.g., "price")
    while the underlying data uses different column names (e.g., "product_price").

    Column Mapping
    --------------
    The ``colmap`` parameter maps rule field names to dataset column names:

    - Key: the name your rule uses (e.g., ``"price"``)
    - Value: the actual column name in the data (e.g., ``"product_price"``)

    When you access ``row["price"]``, RowProxy looks up ``colmap.get("price", "price")``
    to find the actual column name, then returns ``raw_row[actual_column]``.

    Example
    -------
    ::

        raw_row = {"product_price": 100, "item_name": "Widget"}
        colmap = {"price": "product_price", "name": "item_name"}
        row = RowProxy(raw_row, colmap)

        row["price"]  # Returns 100 (from raw_row["product_price"])
        row["name"]   # Returns "Widget" (from raw_row["item_name"])

    If no mapping exists for a key, the key itself is used (identity mapping).
    """
    __slots__ = ("_raw", "_colmap")

    def __init__(self, raw: RawRow, colmap: ColMap | None) -> None:
        self._raw    = deepcopy(raw)
        self._colmap = colmap or {}

    def __getitem__(self, key: str) -> Any:
        actual = self._colmap.get(key, key)
        try:
            return self._raw[actual]
        except KeyError as err:
            raise CellNotFound(str(err)) from None

    def get(self, key: str, default: Any = None) -> Any:
        actual = self._colmap.get(key, key)
        return self._raw.get(actual, default)

    def __iter__(self):
        yield from self._raw

    def __len__(self) -> int:
        return len(self._raw)

    def __contains__(self, key: object) -> bool:
        match key:
            case str():
                actual = self._colmap.get(key, key)
                return actual in self._raw
            case _:
                return False

    def __str__(self) -> str:
        return str(self._raw)

    __repr__ = __str__
