# AI Sentinel - Project Overview

An AI-powered real-time security surveillance system designed for violence detection and automated incident reporting.

## 📂 Project Structure

### 🌐 Frontend (Next.js & Tailwind)
*   `app/`: Core application logic using the Next.js App Router.
    *   `layout.tsx`: Root layout and global providers.
    *   `page.tsx`: Main dashboard interface.
*   `components/`: Reusable React components.
    *   `ai-report.tsx`: AI-generated forensic report display.
    *   `alert-feed.tsx`: Real-time incident alert sidebar.
    *   `dashboard-header.tsx`: Main navigation and status header.
    *   `incident-panel.tsx`: Detailed view for specific security incidents.
    *   `video-player.tsx`: Live stream and evidence playback component.
    *   `ui/`: Base UI components (buttons, cards, dialogs, etc.).
*   `hooks/`: Custom React hooks (e.g., `use-toast.ts`, `use-mobile.ts`).
*   `lib/`: Utility functions and shared data models.
    *   `dashboard-data.ts`: Mock or shared data for the dashboard.
    *   `utils.ts`: Tailwind CSS class merging and other helpers.
*   `public/`: Static assets, including icons, logos, and placeholder images.
*   `styles/`: Global CSS and utility styles.

### ⚙️ Backend (Python & FastAPI)
*   `backend/api.py`: The main FastAPI server handling video streaming, model inference, and SSE (Server-Sent Events) for alerts.
*   `backend/inference.py`: AI model logic. Upgraded to **X3D spatiotemporal architecture** (Task 2) using a **32-frame rolling window** mechanism for optimized performance.
*   `backend/best_model.pt`: Model weights (Fallback or active).
*   `backend/config.yml`: Centralized configuration for model thresholds, storage paths, and server settings (Task 1).
*   `backend/.env`: (Sensitive) Environment variables for API keys and connection strings (Task 1).
*   `backend/evidence_clips/`: Directory where recorded video clips of detected incidents are stored.
*   `backend/cam1.mp4`, `cam2.mp4`, `cam3.mp4`: Sample video streams.

### 🛠 Tools & Installers
*   `backend/cloudflared-windows-amd64.exe`: Utility for creating secure tunnels (likely for remote access).
*   `backend/Ditto Clipboard Installer.exe`: Third-party tools included in the repository.
*   `backend/Git-2.53.0.2-64-bit.exe`: Git installer for environment setup.

## 🚀 Getting Started

### Prerequisites
*   **Frontend**: Node.js 18+ and npm/yarn.
*   **Backend**: Python 3.9+ with PyTorch and OpenCV.

### Setup
1.  **Backend**: 
    - Navigate to `/backend`.
    - Install dependencies: `pip install fastapi uvicorn opencv-python torch torchvision pyyaml python-dotenv`.
    - Create `.env` from `.env.example`.
    - Run: `python api.py`.
2.  **Frontend**: 
    - Install dependencies: `npm install`.
    - Create `.env.local` from `.env.local.example`.
    - Start dev server: `npm run dev`.

## 🛡 Features
- **X3D Inference Engine**: Optimized 32-frame rolling window inference (96% accuracy) with prioritized performance and high accuracy.
- **Real-time Detection**: Live monitoring of security cameras with automated violence detection.
- **Instant Alerts**: Server-Sent Events (SSE) push notifications to the dashboard.
- **Evidence Management**: Automatic recording and storage of incident clips.
- **AI Forensic Analysis**: Integration with Groq VLM for descriptive incident reports in Arabic.
