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

    Absent keys
    -----------
    ``absent_keys`` marks rule field names as *definitively absent*: ``get()``
    returns the default, ``[]`` raises ``CellNotFound``, ``in`` is False, and
    iteration skips any raw column whose name collides with an absent key —
    all checked **before** the colmap identity fallback. Because ``keys()``,
    ``items()``, ``values()``, ``dict(proxy)`` and ``==`` are derived from
    ``__iter__``/``__getitem__`` by ``Mapping``, every view agrees: a raw
    column shadowed by an unbound optional is invisible under that name (its
    data stays reachable through whatever rule field name is bound to it).
    ``repr()``/``str()`` intentionally still show the full raw row, for
    debugging.

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
    __slots__ = ("_raw", "_colmap", "_absent", "_copied", "_copy_memo")

    def __init__(
        self,
        raw: RawRow,
        colmap: ColMap | None,
        *,
        absent_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._raw    = raw.copy()
        self._colmap = colmap or {}
        self._absent = absent_keys
        self._copied: dict[str, Any] = {}
        self._copy_memo: dict[int, Any] = {}

    def _read(self, actual: str) -> Any:
        if actual not in self._copied:
            self._copied[actual] = deepcopy(self._raw[actual], self._copy_memo)
        return self._copied[actual]

    def __getitem__(self, key: str) -> Any:
        if key in self._absent:
            raise CellNotFound(repr(key))
        actual = self._colmap.get(key, key)
        if actual not in self._raw:
            raise CellNotFound(repr(actual))
        return self._read(actual)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._absent:
            return default
        actual = self._colmap.get(key, key)
        if actual not in self._raw:
            return default
        return self._read(actual)

    def __iter__(self):
        if not self._absent:
            yield from self._raw
            return
        for key in self._raw:
            if key not in self._absent:
                yield key

    def __len__(self) -> int:
        if not self._absent:
            return len(self._raw)
        return sum(1 for key in self._raw if key not in self._absent)

    def __contains__(self, key: object) -> bool:
        match key:
            case str():
                if key in self._absent:
                    return False
                actual = self._colmap.get(key, key)
                return actual in self._raw
            case _:
                return False

    def __str__(self) -> str:
        return str(self._raw | self._copied)

    __repr__ = __str__
