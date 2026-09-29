from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Playwright, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
# Next restricts dev-only resources to localhost unless extra origins are allowed.
BASE_URL = "http://localhost:3141"


@pytest.fixture(scope="session")
def dev_server() -> Iterator[str]:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 3141)) == 0:
            pytest.fail("Port 3141 is already in use; stop that process and rerun the suite.")

    log_file = tempfile.TemporaryFile(mode="w+b")
    process = subprocess.Popen(
        ["node", "node_modules/next/dist/bin/next", "dev", "--webpack", "-p", "3141"],
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    deadline = time.monotonic() + 120
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log_file.seek(0)
                pytest.fail("Next dev server exited before becoming ready:\n" + log_file.read().decode(errors="replace"))
            try:
                with urllib.request.urlopen(BASE_URL, timeout=2) as response:
                    if response.status < 500:
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(1)
        else:
            pytest.fail("Next dev server did not become ready within 120 seconds.")
        yield BASE_URL
    finally:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            else:
                os.killpg(process.pid, 15)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log_file.close()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser, dev_server: str) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    # Keep the test deterministic and prevent a locally running API from changing offline flows.
    page.route("http://localhost:8002/**", lambda route: route.abort())
    page.route("http://127.0.0.1:8002/**", lambda route: route.abort())
    yield page
    context.close()


def open_dashboard(page: Page, base_url: str, *, fixtures: bool = True) -> None:
    suffix = "?fixtures=1" if fixtures else ""
    page.goto(base_url + "/" + suffix, wait_until="domcontentloaded")
    page.locator("html[data-hydrated='true']").wait_for(state="attached")

