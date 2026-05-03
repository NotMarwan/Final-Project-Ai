# AI Sentinel: Multi-Angle Recording Benchmark Protocol

This document defines the procedure for recording valid benchmark footage to evaluate the performance of AI Sentinel across different camera angles.

## Camera Setups

### High CCTV Setup
- **Height**: 3.2m – 3.5m (simulating typical building corner/ceiling mount).
- **Angle**: 45–60 degrees downward.
- **Camera Placement**: Booth corner or wall/corner simulation.
- **Distance**: 4m – 6m from the center of the demo area.
- **Expected Coverage**: Full body of participants + floor zone for intrusion visualization.
- **Safety Requirements**:
    - Use industrial-grade heavy-duty stands with sandbag weighting.
    - Secure all cables with gaffer tape.
    - Maintain a clear visitor boundary around the stand.
    - No ladder mounting allowed in the exhibition hall without official permit.

### Eye-Level Setup
- **Height**: 150cm – 180cm (Target: 170cm).
- **Angle**: Horizontal or slight (5-10 degree) downward tilt.
- **Distance**: 2m – 4m from participants.
- **Expected Coverage**: Upper/full body depending on distance.

## Clip Scenarios
Record separate clips for each angle following these scenarios:

| ID | Scenario | Participant Action | Expected Behavior |
| :--- | :--- | :--- | :--- |
| **01** | Normal Movement | Walking, standing, talking normally. | Negative (No alerts). |
| **02** | Intrusion | Stepping into a marked "restricted" zone. | Positive (Intrusion alert). |
| **03** | Boundary Crossing | Crossing a virtual line on the floor. | Positive (Intrusion alert). |
| **04** | Simulated Aggression | Fast gestures, shouting, simulated striking (no contact). | Positive (Violence alert). |
| **05** | Fast Arm Movement | Rapid arm waving or reaching. | Measure false positive risk. |
| **06** | Two-Person Interaction | Staged confrontation at 1.5m distance. | Measure detection consistency. |

### Recording Requirements
- **Duration**: 10–20 seconds per clip.
- **Naming Convention**:
    - `high_3_5m_[scenario]_[idx].mp4` (e.g., `high_3_5m_intrusion_01.mp4`)
    - `eye_170cm_[scenario]_[idx].mp4` (e.g., `eye_170cm_normal_01.mp4`)

## Safety Rules
> [!IMPORTANT]
> **Strict Non-Violence Policy**
> 1. **No Real Violence**: All aggressive actions must be clearly staged and slow-motion if necessary.
> 2. **No Physical Contact**: Participants must maintain a minimum distance. No pushing or striking.
> 3. **No Real Weapons**: Use of real weapons or realistic weapon props is strictly prohibited.
> 4. **Consent**: All participants must provide written/verbal consent before recording.
> 5. **Privacy**: Display clear signs that recording is in progress for AI research purposes.
> 6. **Stop Word**: Establish a clear "STOP" command for immediate session termination.
> 7. **Supervision**: An operator must be present to monitor equipment stability.

## Benchmark Execution
Use the following commands to run benchmarks on the recorded footage.

### High CCTV Benchmark
```powershell
$env:PYTHONPATH="backend"
python backend/tools/benchmark_threat_latency.py --video data/high_3_5m_simulated_aggression_01.mp4 --angle high --weights backend/best_model.pt --iterations 100 --output .runlogs/benchmarks/high_baseline.json
```

### Eye-Level Benchmark
```powershell
$env:PYTHONPATH="backend"
python backend/tools/benchmark_threat_latency.py --video data/eye_170cm_simulated_aggression_01.mp4 --angle eye_level --weights backend/best_model.pt --iterations 100 --output .runlogs/benchmarks/eye_level_baseline.json
```

> [!NOTE]
> Ensure `.runlogs/` is added to `.gitignore` to avoid committing large benchmark outputs to the repository.
