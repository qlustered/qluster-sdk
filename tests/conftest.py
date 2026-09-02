import os
import sys
from atlas_test_support.pytest_markers import (
    pytest_addoption,
    pytest_configure,
    pytest_collection_modifyitems,
)


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             'tests')))


current_dir = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(current_dir, 'fixtures/')
