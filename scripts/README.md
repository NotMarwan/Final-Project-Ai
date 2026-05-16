# Scripts

Utility scripts for setup, training, testing, and maintenance.

## Setup Scripts

| Script | Description |
|--------|-------------|
| `setup-go2rtc.ps1` | Downloads and installs go2rtc binary for WebRTC streaming |
| `create_desktop_shortcut.ps1` | Creates desktop shortcut for AI Sentinel |
| `fix_icon.py` | Fixes icon rendering/path issues |
| `generate_icon.py` | Generates application icons (PNG, ICO) from source |

## Weapon Detection

| Script | Description |
|--------|-------------|
| `prepare_weapon_dataset.py` | Downloads and prepares weapon datasets from Roboflow for YOLO training |
| `test_weapon_detector.py` | Tests weapon detector on images/videos with visualization |
| `test_yolo_weapon.py` | Tests YOLO weapon detection model specifically |
| `weapon_visual_demo.py` | Visual demo of weapon detection on sample images |
| `weapon_video_demo.py` | Video-file weapon detection demo |

## Testing & Integration

| Script | Description |
|--------|-------------|
| `test_integration.py` | End-to-end integration test suite |
| `convert_kilo_agents.py` | Converts Kilo agent definitions between formats |

## Usage

Most scripts should be run from the project root or the `backend/` directory:

```powershell
# Example: setup go2rtc
powershell -ExecutionPolicy Bypass -File scripts/setup-go2rtc.ps1

# Example: test weapon detector
python scripts/test_weapon_detector.py --image samples/test.jpg
```

## Preservation Note

During the freeze, existing utility scripts remain in their original locations (`rebuild_colab_zip.py`, `read_pdfs.py`, `start-colab-bridge.ps1` at the project root). Future cleanup should move all scripts into this folder intentionally.
