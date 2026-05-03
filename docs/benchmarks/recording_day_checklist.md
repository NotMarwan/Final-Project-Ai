# AI Sentinel: Multi-Angle Recording Day Checklist

This document serves as the operational guide for the benchmark recording session. Follow these steps to ensure high-quality, valid, and safe data collection.

## Equipment Checklist

### High CCTV Setup (high_3_5m)
- [ ] TP-Link VIGI C340 2.8mm (Primary high camera)
- [ ] PoE Injector or PoE Switch
- [ ] Cat6 Ethernet Cable (long enough for height + run)
- [ ] Adjustable stand (up to 4m)
- [ ] CCTV pole mount bracket or Super Clamp
- [ ] Sandbags / Weights (minimum 20kg per stand)
- [ ] Gaffer Tape (black or high-visibility)
- [ ] Cable Ties
- [ ] Laptop/Backend Machine for capture
- [ ] Power Extension Cord
- [ ] "Recording in Progress" Privacy Signage

### Eye-Level Setup (eye_170cm)
- [ ] Logitech C920/C920S
- [ ] Tripod (extending to 170cm+)
- [ ] Active USB Extension (if distance > 2m)
- [ ] Gaffer Tape
- [ ] Laptop/Backend Machine for capture

## Safety Checklist
- [ ] **Consent**: All participants have signed or verbally confirmed consent.
- [ ] **No Physical Contact**: Participants maintain a 1.5m "safety bubble" during staged aggression.
- [ ] **No Real Violence**: All movements are simulated and controlled.
- [ ] **No Weapons**: No real firearms, knives, or sharp tools.
- [ ] **No Realistic Props**: Only clearly artificial/toy props allowed if absolutely necessary.
- [ ] **Stop Word**: "STOP" is defined and understood by all as immediate termination.
- [ ] **Operator Supervision**: One person is assigned purely to monitor equipment stability.
- [ ] **Sandbagged Stands**: High stands are weighted and never left unattended.
- [ ] **Taped Cables**: All floor cables are secured with gaffer tape.
- [ ] **No Ladder Mounting**: Mounting must be done from floor level or approved platforms.

## Recording Environment Checklist
- [ ] **Lighting**: Even lighting, no bright windows directly behind participants.
- [ ] **Background**: Minimal clutter, avoid moving reflections or non-participating crowds.
- [ ] **Floor Zones**: Mark "Intrusion Zone" and "Boundary Line" clearly with tape.
- [ ] **Movement Space**: Minimum 4m x 4m clear area for safe participant movement.
- [ ] **Crowd Control**: Barrier or tape to keep bystanders 3m away from recording area.

## Required Clip List
Save all clips to `.runlogs/recordings/[angle_label]/`.

| Scenario ID | Filename (high_3_5m) | Filename (eye_170cm) | Action | Expected Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `high_3_5m_normal_01.mp4` | `eye_170cm_normal_01.mp4` | Normal walking/talking. | No alerts. |
| **02** | `high_3_5m_intrusion_01.mp4` | `eye_170cm_intrusion_01.mp4` | Stepping into marked zone. | Intrusion alert. |
| **03** | `high_3_5m_boundary_01.mp4` | `eye_170cm_boundary_01.mp4` | Crossing floor line. | Boundary alert. |
| **04** | `high_3_5m_violence_01.mp4` | `eye_170cm_violence_01.mp4` | Staged arm strikes (no contact). | Violence alert. |
| **05** | `high_3_5m_fast_move_01.mp4` | `eye_170cm_fast_move_01.mp4` | Rapid arm waving. | No violence alert. |

- **Duration Target**: 10–20 seconds per clip.
- **Safety Rule**: No contact, no weapons, no real force.

## Recording Procedure
1. Set up **High CCTV** camera at 3.2m–3.5m height.
2. Secure stand with sandbags and tape cables.
3. Verify view on laptop (full body + floor markers visible).
4. Record all scenarios (01-05) for high angle.
5. Move to **Eye-Level** setup at 170cm.
6. Record all scenarios (01-05) for eye-level angle.
7. Use `Get-ChildItem .runlogs\recordings -Recurse -Include *.mp4` to verify all 10 files.
8. **DO NOT COMMIT VIDEOS**.

## Benchmark Execution
Once recordings are verified, run the bulk benchmark runner:

```powershell
$env:PYTHONPATH="backend"

# Benchmark High Angle
python backend/tools/run_multi_angle_benchmarks.py `
  --dir .runlogs\recordings\high_3_5m `
  --weights backend\best_model.pt `
  --iterations 100 `
  --output-dir .runlogs\benchmarks\high_3_5m

# Benchmark Eye-Level
python backend/tools/run_multi_angle_benchmarks.py `
  --dir .runlogs\recordings\eye_170cm `
  --weights backend\best_model.pt `
  --iterations 100 `
  --output-dir .runlogs\benchmarks\eye_170cm
```

## Result Interpretation Rules
1. **No Data, No Claim**: Do not claim an angle is superior unless P95 latency and FP rate improve.
2. **GPU Disclaimer**: These are CPU baseline numbers only. GPU sub-500ms is unproven.
3. **Negative Case Check**: `normal_01` and `fast_move_01` must have 0 violence alerts.
4. **Manual Review**: Every detected alert must be visually confirmed to match the frame.
5. **Artifact Policy**: Benchmark JSONs are local evidence; do not commit unless approved.
