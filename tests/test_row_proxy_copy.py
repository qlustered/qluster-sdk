from qluster_sdk.row_proxy import RowProxy


class _CopyTracked:
    def __init__(self) -> None:
        self.copies = 0

    def __deepcopy__(self, memo):
        self.copies += 1
        return _CopyTracked()


def test_only_read_cells_are_copied():
    unused = _CopyTracked()
    used = _CopyTracked()
    proxy = RowProxy({"used": used, "unused": unused}, {"value": "used"})

    first = proxy["value"]
    assert first is proxy.get("used")
    assert used.copies == 1
    assert unused.copies == 0


def test_top_level_row_changes_after_construction_are_not_visible():
    raw = {"value": 1}
    proxy = RowProxy(raw, None)

    raw["value"] = 2
    raw["other"] = 3

    assert proxy["value"] == 1
    assert "other" not in proxy


def test_nested_mutation_stays_inside_one_proxy():
    raw = {"items": [{"name": "original"}]}
    first = RowProxy(raw, None)

    first["items"][0]["name"] = "changed"

    assert first["items"] == [{"name": "changed"}]
    assert raw["items"] == [{"name": "original"}]
    assert RowProxy(raw, None)["items"] == [{"name": "original"}]


def test_shared_cell_references_stay_shared_inside_proxy():
    shared = ["original"]
    raw = {"first": shared, "second": shared}
    proxy = RowProxy(raw, None)

    proxy["first"].append("changed")

    assert proxy["first"] is proxy["second"]
    assert raw == {"first": ["original"], "second": ["original"]}
