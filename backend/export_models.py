"""Export PyTorch YOLO models to ONNX for 2-3x faster inference."""
import sys
from pathlib import Path


def export_yolo_to_onnx(pt_path: str, onnx_path: str, imgsz: int = 640):
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ERROR: pip install ultralytics")
        sys.exit(1)

    pt = Path(pt_path)
    if not pt.exists():
        print(f"ERROR: Model not found: {pt_path}")
        sys.exit(1)

    print(f"Loading {pt_path}...")
    model = YOLO(pt_path)

    print(f"Exporting to ONNX (imgsz={imgsz})...")
    model.export(format="onnx", imgsz=imgsz, dynamic=True, simplify=True, opset=12)

    expected = pt.with_suffix(".onnx")
    if expected.exists():
        target = Path(onnx_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(str(expected), str(target))
        print(f"ONNX exported: {target}")
    else:
        print(f"Export may have failed. Expected: {expected}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export YOLO to ONNX")
    parser.add_argument("--pt", default="backend/weapon_yolo.pt")
    parser.add_argument("--onnx", default="backend/weapon_yolo.onnx")
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()
    export_yolo_to_onnx(args.pt, args.onnx, args.imgsz)
