from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT_DIR / "notebooks" / "colab_zero_touch_train.ipynb"
DEFAULT_OUTPUT_PATH = ROOT_DIR / "notebooks" / "colab_zero_touch_train.ready.ipynb"


def _replace_bridge_url(source: list[str], bridge_url: str) -> list[str]:
    updated: list[str] = []
    for line in source:
        if line.startswith('BRIDGE_URL = "'):
            updated.append(f'BRIDGE_URL = "{bridge_url}"\n')
            continue
        updated.append(line)
    return updated


def render_notebook(bridge_url: str, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    notebook = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        if any(line.startswith('BRIDGE_URL = "') for line in source):
            cell["source"] = _replace_bridge_url(source, bridge_url)
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Colab notebook with a prefilled bridge URL.")
    parser.add_argument("--bridge-url", required=True, help="Public bridge URL without trailing slash.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path of the rendered notebook.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = render_notebook(args.bridge_url.rstrip("/"), Path(args.output))
    print(output_path)


if __name__ == "__main__":
    main()
