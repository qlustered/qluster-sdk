"""Names a rule author imports from the package root."""

import qluster_sdk
from qluster_sdk import rule


def test_field_type_names_is_exported_from_the_root():
    assert qluster_sdk.FIELD_TYPE_NAMES is rule.FIELD_TYPE_NAMES
    assert "FIELD_TYPE_NAMES" in qluster_sdk.__all__
