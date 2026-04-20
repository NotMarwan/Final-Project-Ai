# CCTV Acquisition and Integration Plan

This document turns the current dashboard from "internet live demo" mode into a real camera ingestion plan.

## Goal

Deploy local CCTV cameras that the AI Sentinel backend can ingest directly over LAN and then expose to the Next.js dashboard as one unified live view.

## Buying Recommendation

For this project, the best cameras are the ones that support `RTSP` and `ONVIF` on a local network, preferably with a built-in microphone.

### Recommended rule of thumb

- Buy cameras with a microphone for the main entry points and high-risk zones.
- Disable audio in software if privacy rules require it.
- Avoid battery-powered cameras for this project unless they explicitly support always-on RTSP/ONVIF.
- Prefer wired or wired/wireless cameras that can stay online 24/7.

### Best-value shortlist in the SAR 200-600 range

| Model | Typical KSA price found | Best use | Mic? | RTSP/ONVIF | Why it fits |
|---|---:|---|---|---|---|
| TP-Link Tapo C520WS | about SAR 204 | Outdoor perimeter | Yes | Yes | Strong all-round outdoor camera, 2K, pan/tilt, IP66, LAN-friendly. |
| TP-Link Tapo C246D | about SAR 252 | Indoor/outdoor mixed zones | Yes | Yes | Dual-lens coverage, smart tracking, flexible placement. |
| EZVIZ C8c 4K | about SAR 360 | Outdoor wide-area | Yes | ONVIF on supported SKU/firmware | Good quality, but firmware/SKU check is required before buying. |

### Budget fallback below SAR 200

| Model | Typical KSA price found | Best use | Mic? | RTSP/ONVIF | Why it fits |
|---|---:|---|---|---|---|
| TP-Link Tapo C320WS | about SAR 159 | Outdoor fixed view | Yes | Yes | Excellent value if you want the cheapest serious outdoor option. |
| TP-Link Tapo C200 | about SAR 75-79 | Indoor low-cost fallback | Yes | Yes | Good for cheap indoor tests, but lower priority than the outdoor models. |

### Default profile in this repository

The current default in `backend/camera_profiles.yml` is:

- `CAM-01`: Tapo C520WS (enabled)
- `CAM-02`: Tapo C246D (enabled)
- `CAM-03`: Tapo C320WS (enabled)

### Jarir options around the SAR 200 range (snapshot: 2026-04-18)

- `TP-Link Tapo C230` on Jarir product page shows `SR 12 Per Month /24 months` (about `SAR 288` total). This is the closest practical option in the "around 200" indoor tier with strong protocol compatibility.
- `TP-Link Tapo C222` is listed on Jarir and included as a disabled ready profile in backend files. Final checkout price should be verified on purchase day.
- `EZVIZ C6c` appears on Jarir security cameras list at `SAR 249`. Keep it as optional unless RTSP/ONVIF support is confirmed for the exact SKU/firmware.

Implementation status in this repo:

- Added disabled ready-to-enable profiles for Jarir-focused options in:
  - `backend/camera_profiles.yml` (`CAM-11`, `CAM-12`)
  - `backend/camera_profiles.example.yml` (`CAM-11`, `CAM-12`)

## Do We Want a Microphone?

### Short answer

Yes, on the main cameras.

### Why

- It lets the app support audio cues later without changing hardware.
- Two-way audio helps for warnings or live operator interaction.
- It gives us more future flexibility if we add audio-risk detection.

### When to skip the microphone

- If a site has strict privacy rules.
- If the camera is in a noisy area where audio adds little value.
- If the camera is in a room where only silent video is allowed.

### Practical recommendation

- Front entrance, lobby, reception, loading bay: microphone enabled.
- Hallways and secondary rooms: microphone optional.
- Private rooms, HR areas, meeting rooms: video-only or audio disabled.

## Recommended Purchase Mix

### Option A: Best balance

- 2 x Tapo C520WS for outdoor perimeter
- 1 x Tapo C246D for a shared indoor/outdoor choke point
- 1 x Tapo C200 for a cheap indoor test camera

### Option B: Outdoor-first

- 2 x Tapo C520WS
- 1 x Tapo C320WS
- 1 x EZVIZ C8c 4K if you want a higher-resolution PT camera

### Option C: Lowest cost pilot

- 2 x Tapo C200
- 1 x Tapo C320WS
- 1 x Tapo C246D

## Integration Strategy

Use these layers in this order:

1. Direct RTSP from the camera to the backend.
2. ONVIF discovery and fallback configuration.
3. Local NVR or camera gateway software if the vendor app is too closed.
4. Vendor cloud app only for setup, firmware updates, and testing.

## Connection Methods

### Method 1: Direct RTSP

Best when the camera supports RTSP locally.

Use this for:

- Tapo C200
- Tapo C320WS
- Tapo C246D
- Tapo C520WS

Expected format:

```text
rtsp://USER:PASSWORD@CAMERA_IP:554/stream1
```

This is the simplest method for our backend because OpenCV or FFmpeg can consume it directly.

### Method 2: ONVIF + RTSP discovery

Best when you want the camera to auto-discover on the LAN and still keep local control.

Use ONVIF for:

- Discovery
- PTZ control if supported
- Health checks

Use RTSP for:

- Actual frame ingestion

### Method 3: NVR or gateway bridge

Use this if the camera app is too vendor-specific.

Examples:

- Agent DVR
- Blue Iris
- Synology Surveillance Station
- QNAP QVR Pro
- An ONVIF-compatible NVR

The NVR becomes the "camera manager", and AI Sentinel only reads the NVR stream.

### Method 4: Vendor app only for setup

Use the vendor app for:

- First-time setup
- Firmware update
- Enabling RTSP/ONVIF
- Creating the camera account

Then move the feed into our backend locally.

## Software Mapping

### For TP-Link Tapo

- Enable the camera account in the Tapo app.
- Enable RTSP and ONVIF.
- Keep the camera on the same LAN as the backend.
- Use stream1 for the high-quality stream and stream2 for the low-quality stream.

TP-Link documents:

- RTSP default port: `554`
- ONVIF service port: `2020`
- RTSP URL examples: `rtsp://IP Address/stream1` or `rtsp://admin:password@IP:554/stream1`

### For EZVIZ

- Prefer only the models and firmware versions that EZVIZ explicitly lists as ONVIF-compatible.
- If the exact model is not on the ONVIF support list, do not buy it for this project.
- Keep EZVIZ mostly as a vendor-managed camera unless the ONVIF support is confirmed.

## Recommended System Design

```mermaid
flowchart LR
  Camera1["Camera 1 RTSP/ONVIF"]
  Camera2["Camera 2 RTSP/ONVIF"]
  Camera3["Camera 3 RTSP/ONVIF"]
  NVR["Optional NVR / Gateway"]
  Backend["AI Sentinel FastAPI"]
  Frontend["Next.js Dashboard"]

  Camera1 --> Backend
  Camera2 --> Backend
  Camera3 --> Backend
  Camera1 --> NVR
  Camera2 --> NVR
  Camera3 --> NVR
  NVR --> Backend
  Backend --> Frontend
```

## Implementation Plan

### Phase 1: Camera onboarding

- Assign fixed IPs or DHCP reservations.
- Rename cameras to `CAM-01`, `CAM-02`, `CAM-03`, etc.
- Enable RTSP and ONVIF.
- Test each camera in VLC first.

### Phase 2: Backend ingest

- Add a camera profile file to the backend.
- Map each camera ID to an RTSP URL.
- Add a per-camera health check.
- Keep a fallback low-resolution stream for weak links.

### Phase 3: Dashboard integration

- Keep the current dashboard layout.
- Let the user switch between cameras.
- Show the active camera, status, and audio availability.
- Optionally expose a "live demo" mode only for testing.

### Phase 4: AI features

- Run detection on the highest-quality stream that the network can sustain.
- Keep evidence clips local.
- Keep audio analysis optional.
- Store a camera-specific audit trail.

## Files To Keep Ready

Create or maintain these files:

- `backend/camera_profiles.example.yml`
- `backend/camera_profiles.yml` after purchase
- `backend/camera_profiles.jarir.yml` for Jarir-focused near-200 SAR setup
- `backend/camera_networking.example.yml` for LAN/IP/VLAN/port planning
- `backend/config.yml`
- `backend/api.py`
- `docs/cctv-acquisition-and-integration-plan.md`

Runtime wiring in this codebase:

- `backend/api.py` reads camera sources from `camera_profiles.yml` by default.
- Override path with env var `CAMERA_PROFILES_PATH` if needed.
- If profile file is missing/empty, backend falls back to `CAM1_SOURCE`, `CAM2_SOURCE`, `CAM3_SOURCE`.
- Quick switch examples:
  - `CAMERA_PROFILES_PATH=camera_profiles.yml` (default mixed profile)
  - `CAMERA_PROFILES_PATH=camera_profiles.jarir.yml` (Jarir near-200 preset)
- Keep `camera_networking.example.yml` aligned with camera profile IPs before onsite deployment.

## Rollout Checklist

1. Buy one Tapo C520WS and one Tapo C246D first.
2. Install them on the same LAN as the backend machine.
3. Enable RTSP/ONVIF in the vendor app.
4. Confirm VLC can open each RTSP URL.
5. Put the URLs into `backend/camera_profiles.yml`.
6. Run the backend and verify `/video_feed` and alerts.
7. Add the remaining cameras only after the pilot is stable.

## My Practical Recommendation

If you want the safest path for this codebase:

- Buy mostly TP-Link Tapo cameras.
- Use models that clearly support RTSP and ONVIF.
- Keep a microphone on the main cameras.
- Disable audio per camera if privacy requires it.
- Use EZVIZ only if the exact SKU is confirmed ONVIF-compatible.
