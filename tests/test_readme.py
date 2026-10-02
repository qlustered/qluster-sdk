"""The README's Quick Start runs as written."""

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def _quick_start_blocks() -> list[str]:
    """The Python code blocks of the README's Quick Start section, in order."""
    section = README.read_text().split("\n## Quick Start\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```python\n(.*?)```", section, re.DOTALL)


def test_quick_start_defines_and_runs_its_rule():
    namespace: dict = {}
    for block in _quick_start_blocks():
        exec(block, namespace)  # noqa: S102

    result = namespace["result"]
    assert result.corrections == {"price": 100.0}
    assert [issue.field_names for issue in result.issues] == [["price"]]
