"""Smoke test: verify the 3 demo clips are defined and AVI files exist at expected paths."""
import re
import ast
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
    """Check the active packaged sources without loading the model runtime."""
    module = ast.parse(_read_api_source())
    loader = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_load_example_sources")
    namespace = {"BASE_DIR": BACKEND_DIR, "Dict": dict}
    exec(compile(ast.Module(body=[loader], type_ignores=[]), str(API_FILE), "exec"), namespace)
    paths = namespace["_load_example_sources"]()
    assert set(paths) == {"EXAMPLE-01", "EXAMPLE-02", "EXAMPLE-03"}
    for camera_id, value in paths.items():
        path = Path(value)
        assert path.is_relative_to(BACKEND_DIR.parent / "demo_assets" / "videos")
        assert path.is_file(), f"Packaged demo is absent: {camera_id}: {path}"
        with path.open("rb") as handle:
            header = handle.read(12)
        assert header[:4] == b"RIFF" and header[8:12] == b"AVI ", (
            f"Demo {camera_id} is not an AVI; materialize its Git LFS object before running the demo"
        )
