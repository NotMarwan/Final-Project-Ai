# Frontend — AI Sentinel Dashboard

The frontend is a Next.js 16 (App Router) application with React 19, Tailwind CSS, and `shadcn/ui` components.

## Directory Structure

```
app/
  layout.tsx         # Root layout: fonts, metadata, PWA manifest, global styles
  page.tsx           # Main dashboard (523 lines, 6 tabs, SSE connection, state management)
  globals.css        # Global styles, CSS custom properties, animations
  manifest.ts        # PWA web app manifest

components/
  video-player.tsx   # Main video player (515 lines, MJPEG/WebRTC, overlays, HUD, face intel)
  webrtc-player.tsx  # WebRTC video player (184 lines, ICE/STUN, retry logic)
  canvas-overlay.tsx # Detection bounding boxes on canvas (131 lines)
  alert-feed.tsx     # Live incident alert sidebar (159 lines, category filtering)
  incident-panel.tsx # Detailed incident view (864 lines, evidence, reports, face policy, PDF export)
  ai-report.tsx      # AI forensic report display (452 lines, Groq/DeepSeek report viewer)
  dashboard-header.tsx # Main header (136 lines, SSE status, privacy toggle, face policy badge)
  clip-player.tsx    # Evidence clip video player (121 lines, loop/speed controls)
  clip-sidebar.tsx   # Clip list sidebar (230 lines, demo clip replay)
  incident-replay.tsx # Full incident replay (287 lines, auto-play, retry, volume)
  category-filter.tsx # Detection category filter (93 lines, toggle group)
  telegram-status.tsx # Telegram notification status card (230 lines)
  geo-dashboard.tsx  # Operations map (215 lines, geo-intelligence deck)
  theme-provider.tsx # Theme provider wrapper
  ui/                # Base UI components (button, card, dialog, badge, slider, switch, tabs, etc.)

hooks/
  use-detection-stream.ts  # SSE connection for detection overlay data (tracks, threats, FPS)
  use-clip-playback.ts     # Video clip playback controls (play, pause, loop, speed)
  use-toast.ts             # Toast notification system (from shadcn/ui)
  use-mobile.ts            # Responsive breakpoint detection

lib/
  detection-types.ts  # Type definitions: DetectionCategory, CategoryScore, CategoryCapability
  dashboard-data.ts   # Mock/shared dashboard data for development
  utils.ts            # cn() Tailwind class merger utility
```

## Data Flow

```
Backend (SSE) ───────► /alerts endpoint ──────► AlertFeed component (incident sidebar)
                              │
                              ├──► IncidentPanel (detailed view, PDF export, AI reports)
                              │
                              └──► ClipSidebar (evidence clip replay)

Backend (SSE) ───────► /detections endpoint ──► useDetectionStream hook
                              │
                              └──► CanvasOverlay (bounding boxes on video)
                              └──► VideoPlayer HUD (threat confidence, FPS, person count)

Backend (HTTP) ──────► /video_feed?camera_id= ─► VideoPlayer (MJPEG stream)
Backend (WebRTC) ────► /api/webrtc/{cam_id} ──► WebRTCPlayer (planned)

Backend (REST) ──────► /system/status ─────────► TelegramStatusCard, DashboardHeader
                              │
                              ├──► /face/policy ───► IncidentPanel (face policy controls)
                              ├──► /face/registry ──► Face registry CRUD
                              ├──► /api/categories ─► CategoryFilter
                              ├──► /download_report ─► PDF download
                              └──► /clips/{id} ─────► ClipPlayer, IncidentReplay
```

## Key Patterns

### Page Structure (`app/page.tsx`)
- **6 tabs**: Live Monitor, Demo Clips, Incidents, Intelligence, Operations, System
- `LiveSourceId`: "CAM-01", "CAM-02" (2 live camera sources)
- `DemoSourceId`: "EXAMPLE-01", "EXAMPLE-02" (2 demo clip sources)
- State management: `useState` for tabs, alerts, selected alert, camera, categories
- SSE connection with `useEffect` to `/alerts` endpoint
- Dynamic imports for `IncidentPanel` and `AiReport` (SSR disabled)

### Component Conventions
- All components use `"use client"` directive (client-side rendering)
- TypeScript interfaces defined at the top of each file
- `cn()` from `@/lib/utils` for conditional class merging
- Lucide icons from `lucide-react`
- `shadcn/ui` primitives for consistent design (Button, Badge, Card, etc.)
- API base URL from `NEXT_PUBLIC_API_BASE_URL` env var (fallback: `http://localhost:8002`)
- SSE URL from `NEXT_PUBLIC_SSE_URL` env var (fallback: `http://localhost:8002/alerts`)
- `memo()` wrappers on performance-critical components (AlertFeed, GeoDashboard)

### Video Player (`components/video-player.tsx`)
- Mode: `"live"` (MJPEG from `/video_feed`) or `"demo"` (HTTP from demo endpoints)
- WebRTC auto-upgrade: MJPEG renders immediately, upgrades to WebRTC in background
- Canvas overlay for detection boxes (tracks, weapons, faces)
- HUD overlay: threat badge, FPS, person count, face observations
- Privacy mode toggle to blur faces
- Face observations panel (known/unknown persons with confidence)

### Environment Variables
These are set in `.env.local` at the project root:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `NEXT_PUBLIC_SSE_URL` | `http://localhost:8000/alerts` | SSE alert stream URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws` | WebSocket URL |
| `NEXT_PUBLIC_ADMIN_API_KEY` | `sentinel-demo-2026` | API key for frontend HTTP requests |

## Running

```bash
npm install
cp .env.local.example .env.local
npm run dev      # Development on port 3000
npm run build    # Production build
npm run lint     # ESLint check
npm run typecheck # TypeScript check
```

## Preservation Note

During the preservation freeze (2026-05-07), the frontend source files remain in the root layout (`app/`, `components/`, `hooks/`, `lib/`, `public/`, `styles/`). The `frontend/` directory is a documentation placeholder only; sources were intentionally left in their existing locations to avoid risky structural moves.
