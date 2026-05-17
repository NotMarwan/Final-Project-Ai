"""Smoke test: verify the 3 demo clips are defined and AVI files exist at expected paths."""
import pytest
import re
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
API_FILE = BACKEND_DIR / "api.py"


def _read_api_source():
    return API_FILE.read_text(encoding="utf-8")


def test_exactly_three_example_sources_defined():
    source = _read_api_source()

    # Find all EXAMPLE-xx entries in the dict
    matches = re.findall(r'"EXAMPLE-\d+"', source)
    example_ids = [m.strip('"') for m in matches]

    # The _DEMO_SOURCE_NAMES dict also has EXAMPLE keys, so count unique
    unique_ids = sorted(set(example_ids))
    assert unique_ids == ["EXAMPLE-01", "EXAMPLE-02", "EXAMPLE-03"], (
        f"Expected only EXAMPLE-01,02,03 but found: {unique_ids}"
    )


def test_no_stale_example_04_through_10():
    source = _read_api_source()

    for i in range(4, 11):
        eid = f"EXAMPLE-{i:02d}"
        assert eid not in source, f"Stale entry {eid} still present in api.py"


def test_demo_source_names_descriptive():
    source = _read_api_source()

    assert '"EXAMPLE-01": "Fight Sample 1"' in source
    assert '"EXAMPLE-02": "Fight Sample 2"' in source
    assert '"EXAMPLE-03": "Violence Sample 3"' in source


def test_all_three_avi_files_exist():
    """Resolve paths the same way _load_example_sources() does."""
    project_root = BACKEND_DIR.parent  # BASE_DIR.parent

    paths = {
        "EXAMPLE-01": project_root / "test" / "Wq0BuA8GM84_0.avi",
        "EXAMPLE-02": project_root / "test" / "YDOJvzChqSg_0 (1).avi",
        "EXAMPLE-03": project_root / "unrelated" / "archived-projects" / "violence" / "1Kbw1bUw_0.avi",
    }

    missing = []
    for eid, p in paths.items():
        if not p.exists():
            missing.append(f"{eid}: {p}")

    assert len(missing) == 0, "Missing AVI files:\n" + "\n".join(missing)
