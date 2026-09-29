import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test (slow)")

def pytest_collection_modifyitems(config, items):
    if config.getoption("-m") == "integration":
        return
    # Optional: skip integration tests by default if needed
    # skip_integration = pytest.mark.skip(reason="need --integration option to run or -m integration")
    # for item in items:
    #     if "integration" in item.keywords:
    #         item.add_marker(skip_integration)
