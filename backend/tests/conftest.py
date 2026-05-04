import pytest

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
