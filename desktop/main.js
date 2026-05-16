const { app, BrowserWindow, Tray, Menu, nativeImage, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const ICON_PATH = path.join(__dirname, "assets", "icon.ico");
const ICON_PNG_PATH = path.join(__dirname, "assets", "icon.png");
const BACKEND_PORT = 8002;
const FRONTEND_PORT = 3000;
const LOG_DIR = path.join(PROJECT_ROOT, "desktop", "logs");

// Ensure log directory
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });

let mainWindow = null;
let tray = null;
let backendProcess = null;
let frontendProcess = null;
let isQuitting = false;

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  fs.appendFileSync(path.join(LOG_DIR, "app.log"), line + "\n");
}

function createSplashWindow() {
  const splash = new BrowserWindow({
    width: 500,
    height: 400,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    icon: ICON_PATH,
    webPreferences: { nodeIntegration: false },
  });

  const iconBase64 = fs.readFileSync(ICON_PNG_PATH).toString("base64");

  splash.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
<!DOCTYPE html>
<html>
<head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;600;700;800&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { 
    background: radial-gradient(ellipse at 50% 40%, #0a1628, #060e1a);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100vh; font-family: 'Inter', sans-serif; color: white;
    overflow: hidden; user-select: none;
  }
  .shield {
    width: 120px; height: 120px; position: relative;
    animation: pulse 2s ease-in-out infinite;
  }
  .shield svg { width: 100%; height: 100%; }
  .title {
    font-size: 28px; font-weight: 800; letter-spacing: 2px;
    background: linear-gradient(135deg, #60a5fa, #3b82f6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-top: 16px;
  }
  .subtitle {
    font-size: 13px; font-weight: 300; color: #64748b; margin-top: 4px;
    letter-spacing: 3px; text-transform: uppercase;
  }
  .loader {
    margin-top: 32px; display: flex; gap: 6px;
  }
  .bar {
    width: 4px; height: 24px; background: #3b82f6; border-radius: 2px;
    animation: load 1.4s ease-in-out infinite;
  }
  .bar:nth-child(1) { animation-delay: 0s; }
  .bar:nth-child(2) { animation-delay: 0.15s; }
  .bar:nth-child(3) { animation-delay: 0.3s; }
  .bar:nth-child(4) { animation-delay: 0.45s; }
  .bar:nth-child(5) { animation-delay: 0.6s; }
  .status {
    font-size: 11px; color: #475569; margin-top: 16px;
    font-weight: 300; letter-spacing: 1px;
  }
  @keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.05); opacity: 0.8; }
  }
  @keyframes load {
    0%, 100% { transform: scaleY(0.4); opacity: 0.4; }
    50% { transform: scaleY(1); opacity: 1; }
  }
  .glow {
    position: absolute; width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(59,130,246,0.08), transparent);
    border-radius: 50%; top: 80px;
  }
</style>
</head>
<body>
<div class="glow"></div>
<div class="shield">
  <svg viewBox="0 0 180 180" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="20" y="25" width="140" height="130" rx="25" fill="#1e293b" stroke="#3b82f6" stroke-width="3"/>
    <rect x="35" y="38" width="110" height="90" rx="15" fill="#0f172a"/>
    <circle cx="90" cy="80" r="30" fill="#1e3a5f" stroke="#3b82f6" stroke-width="2"/>
    <circle cx="90" cy="80" r="14" fill="#3b82f6"/>
    <circle cx="90" cy="80" r="6" fill="#fff"/>
    <circle cx="98" cy="74" r="3" fill="#fff" opacity="0.7"/>
    <rect x="65" y="108" width="50" height="2" rx="1" fill="#3b82f6" opacity="0.5"/>
    <rect x="63" y="102" width="54" height="1" rx="0.5" fill="#3b82f6" opacity="0.3"/>
    <rect x="67" y="114" width="46" height="1" rx="0.5" fill="#3b82f6" opacity="0.3"/>
  </svg>
</div>
<div class="title">AI SENTINEL</div>
<div class="subtitle">Surveillance System</div>
<div class="loader">
  <div class="bar"></div><div class="bar"></div><div class="bar"></div>
  <div class="bar"></div><div class="bar"></div>
</div>
<div class="status" id="status">Initializing...</div>
<script>
  const statuses = [
    "Loading AI models...",
    "Connecting threat detection...",
    "Calibrating sensors...",
    "Starting surveillance...",
    "System ready."
  ];
  let i = 0;
  setInterval(() => {
    i = (i + 1) % statuses.length;
    document.getElementById('status').textContent = statuses[i];
  }, 3000);
</script>
</body>
</html>
`)}`);

  return splash;
}

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    icon: ICON_PATH,
    show: false,
    backgroundColor: "#0f172a",
    title: "AI Sentinel",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadURL(`http://localhost:${FRONTEND_PORT}`);
  return win;
}

function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("AI Sentinel - Surveillance System");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Show Dashboard",
      click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } },
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => { isQuitting = true; app.quit(); },
    },
  ]);
  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
}

function waitForServer(url, timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error(`Timeout waiting for ${url}`));
        return;
      }
      http.get(url, (res) => resolve(res))
        .on("error", () => setTimeout(check, 500));
    };
    check();
  });
}

function cleanup() {
  log("Cleaning up processes...");

  if (backendProcess) {
    try { process.kill(-backendProcess.pid); } catch { }
    try { backendProcess.kill("SIGTERM"); } catch { }
    backendProcess = null;
  }

  if (frontendProcess) {
    try { process.kill(-frontendProcess.pid); } catch { }
    try { frontendProcess.kill("SIGTERM"); } catch { }
    frontendProcess = null;
  }
}

async function startBackend() {
  return new Promise((resolve, reject) => {
    log("Starting Python backend...");
    const pythonCmd = "python";
    const args = ["backend/api.py"];

    backendProcess = spawn(pythonCmd, args, {
      cwd: PROJECT_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      shell: true,
      windowsHide: true,
    });

    backendProcess.stdout.on("data", (data) => {
      fs.appendFileSync(path.join(LOG_DIR, "backend.log"), data);
    });

    backendProcess.stderr.on("data", (data) => {
      fs.appendFileSync(path.join(LOG_DIR, "backend-err.log"), data);
    });

    backendProcess.on("error", (err) => {
      log(`Backend error: ${err.message}`);
      reject(err);
    });

    backendProcess.on("exit", (code) => {
      log(`Backend exited with code ${code}`);
      if (!isQuitting) {
        log("Backend crashed — will not restart automatically.");
      }
    });

    resolve();
  });
}

async function startFrontend() {
  return new Promise((resolve, reject) => {
    log("Starting Next.js frontend...");
    const npmCmd = "npx";
    const args = ["next", "start", "--port", String(FRONTEND_PORT)];

    frontendProcess = spawn(npmCmd, args, {
      cwd: PROJECT_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      shell: true,
      windowsHide: true,
    });

    frontendProcess.stdout.on("data", (data) => {
      fs.appendFileSync(path.join(LOG_DIR, "frontend.log"), data);
    });

    frontendProcess.stderr.on("data", (data) => {
      fs.appendFileSync(path.join(LOG_DIR, "frontend-err.log"), data);
    });

    frontendProcess.on("error", (err) => {
      log(`Frontend error: ${err.message}`);
      reject(err);
    });

    frontendProcess.on("exit", (code) => {
      log(`Frontend exited with code ${code}`);
    });

    resolve();
  });
}

async function main() {
  log("=== AI Sentinel Desktop App Starting ===");

  const splash = createSplashWindow();

  try {
    await startBackend();
    await startFrontend();

    log("Waiting for servers...");
    await Promise.all([
      waitForServer(`http://localhost:${BACKEND_PORT}/health`),
      waitForServer(`http://localhost:${FRONTEND_PORT}`),
    ]);

    log("Both servers ready. Opening dashboard...");
    mainWindow = createMainWindow();

    mainWindow.once("ready-to-show", () => {
      splash.close();
      mainWindow.show();
    });

    mainWindow.on("close", (event) => {
      if (!isQuitting) {
        event.preventDefault();
        mainWindow.hide();
      }
    });

    mainWindow.on("closed", () => {
      mainWindow = null;
    });

    createTray();

  } catch (err) {
    log(`Fatal error: ${err.message}`);
    splash.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
<!DOCTYPE html>
<html><head><style>
body { background: #0f172a; color: #f87171; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; text-align: center; padding: 40px; }
h1 { font-size: 20px; margin-bottom: 12px; }
p { font-size: 13px; color: #94a3b8; max-width: 400px; line-height: 1.6; }
</style></head><body>
<div>
<h1>Failed to Start AI Sentinel</h1>
<p>${err.message.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</p>
<p style="margin-top:20px;font-size:11px;">Check desktop/logs/ for details.</p>
<button onclick="require('electron').remote.app.quit()" style="margin-top:16px;padding:8px 24px;background:#3b82f6;color:white;border:none;border-radius:6px;cursor:pointer;">Close</button>
</div></body></html>
`)}`);
  }
}

app.on("ready", main);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  cleanup();
});

app.on("will-quit", () => {
  cleanup();
});
