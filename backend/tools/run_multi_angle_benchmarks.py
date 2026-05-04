import os
import sys
import argparse
import json
from pathlib import Path

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_bulk_benchmark(input_dir, weights_path, iterations=100, output_dir=None):
    from tools.benchmark_threat_latency import run_benchmark
    video_extensions = ('.mp4', '.avi', '.mov', '.mkv')
    videos = [f for f in os.listdir(input_dir) if f.lower().endswith(video_extensions)]
    
    if not videos:
        print(f"No videos found in {input_dir}")
        return

    results = []
    print(f"\n[Bulk Benchmark] Found {len(videos)} videos. Starting process...")
    print("-" * 100)
    print(f"{'Video File':<40} | {'Angle':<10} | {'P95 Detect (ms)':<15} | {'P95 Weapon (ms)':<15}")
    print("-" * 100)

    for video in videos:
        video_path = os.path.join(input_dir, video)
        
        # Determine angle label from filename
        angle = "high" if "high" in video.lower() else "eye_level"
        
        try:
            report = run_benchmark(
                video_path=video_path,
                angle=angle,
                weights_path=weights_path,
                iterations=iterations
            )
            
            if report:
                detect_p95 = report['latencies_ms']['detection']['p95']
                weapon_p95 = report['latencies_ms']['weapon_inference']['p95']
                
                results.append(report)
                print(f"{video:<40} | {angle:<10} | {detect_p95:<15} | {weapon_p95:<15}")
                
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    out_path = os.path.join(output_dir, f"{Path(video).stem}_result.json")
                    with open(out_path, "w") as f:
                        json.dump(report, f, indent=2)
        except Exception as e:
            print(f"{video:<40} | ERROR: {str(e)}")

    print("-" * 100)
    print(f"[Bulk Benchmark] Completed. {len(results)}/{len(videos)} processed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk Multi-Angle Benchmark Runner")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing video files")
    parser.add_argument("--weights", type=str, default="backend/best_model.pt", help="Path to model weights")
    parser.add_argument("--iterations", type=int, default=100, help="Frames per video")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save individual JSON reports")
    
    args = parser.parse_args()
    
    run_bulk_benchmark(
        input_dir=args.dir,
        weights_path=args.weights,
        iterations=args.iterations,
        output_dir=args.output_dir
    )
