"""Run unchanged tests without importing local cloud/Telegram credentials."""
from pathlib import Path
import os

from bench.common import ROOT, prepare_environment


if __name__ == "__main__":
    prepare_environment()
    import pytest
    output = ROOT / "bench/results"
    output.mkdir(parents=True, exist_ok=True)
    os.environ["ADMIN_API_KEY"] = ""
    raise SystemExit(pytest.main(["backend/tests", "-q", "-p", "no:cacheprovider", "--tb=short", "--continue-on-collection-errors",
                                 "--junitxml=" + str(output / "legacy-suite.xml")]))
