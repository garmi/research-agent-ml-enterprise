"""Playwright UI smoke test for Executive AI Research Studio (web_app.py).

Verifies presentation layer and multi-lane workflow:
- Only skips if Playwright is not installed at all.
- Launches Streamlit server automatically.
- Checks that first screen load renders the three lanes:
  - Lane A: Academic Literature
  - Lane B: Enterprise Literature
  - Lane C: Practitioner Delivery
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import pytest

try:
    import playwright
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _is_server_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status in (200, 304)
    except Exception:
        return False


def test_executive_studio_ui_smoke():
    if sync_playwright is None:
        pytest.skip("Playwright is not installed at all.")

    port = _find_free_port()
    server_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory() as tmp_home:
        st_dir = os.path.join(tmp_home, ".streamlit")
        os.makedirs(st_dir, exist_ok=True)
        with open(os.path.join(st_dir, "credentials.toml"), "w", encoding="utf-8") as f:
            f.write('[general]\nemail = ""\n')
        with open(os.path.join(st_dir, "config.toml"), "w", encoding="utf-8") as f:
            f.write('[server]\nheadless = true\n[browser]\ngatherUsageStats = false\n')

        env = dict(os.environ)
        env["HOME"] = tmp_home
        env["PYTHONPATH"] = "."
        env["HOSTED_DEMO"] = "0"
        env["STUB_LLM"] = "1"

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "web_app.py",
                f"--server.port={port}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
                "--server.fileWatcherType=none",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        try:
            # Wait up to 15 seconds for Streamlit to start
            server_ready = False
            for _ in range(30):
                if _is_server_ready(f"{server_url}/_stcore/health") or _is_server_ready(server_url):
                    server_ready = True
                    break
                time.sleep(0.5)

            assert server_ready, f"Streamlit server on {server_url} failed to start within 15 seconds."

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                page = browser.new_page(viewport={"width": 1280, "height": 1000})

                # 1. Load the Studio in stub/offline mode
                page.goto(f"{server_url}/?stub=1", wait_until="networkidle")
                time.sleep(2)

                # 2. Assert Header & Status Badge
                assert page.locator("text=Executive AI Research Studio").count() > 0
                assert page.locator("text=100% Traceable Evidence Engine").count() > 0

                # 3. Assert Active Three-Lane Architecture & Ingestion Readiness on FIRST LOAD
                assert page.locator("text=Active Three-Lane Architecture & Ingestion Readiness").count() > 0
                assert page.locator("text=Lane A: Academic Literature").count() > 0
                assert page.locator("text=Lane B: Enterprise Literature").count() > 0
                assert page.locator("text=Lane C: Practitioner Delivery").count() > 0

                # 4. Assert Intake Panel & Console
                assert page.locator("text=Frame your question").count() > 0
                assert page.locator('button:has-text("Reason about my question")').count() > 0

                run_btn = page.locator('button:has-text("Run Research")')
                assert run_btn.count() > 0
                assert page.locator("text=Strategic Technology Question").count() > 0

                # 5. Assert Empty Topic Validation & Approval Flow
                assert run_btn.is_disabled()
                assert page.locator("text=Type a question in Step 1.").count() > 0

                # Enter Q1 text
                q1_text = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
                page.locator("textarea").first.fill(q1_text)
                page.locator("textarea").first.press("Tab")
                time.sleep(1)

                # Reason about question in Step 1
                reason_btn = page.locator('button:has-text("Reason about my question")')
                assert reason_btn.count() > 0
                reason_btn.click()
                page.wait_for_selector('button:has-text("Approve this reasoned question")', timeout=10000)

                # Confirm terms checkbox if present
                confirm_lbl = page.locator("label:has-text('I acknowledge and confirm')")
                if confirm_lbl.count() > 0:
                    confirm_lbl.first.click()
                    time.sleep(1)

                # Approve proposal in Step 2
                approve_btn = page.locator('button:has-text("Approve this reasoned question")')
                assert approve_btn.count() > 0
                approve_btn.click()
                time.sleep(1)

                # Assert Run button is now enabled (do NOT click Run)
                assert run_btn.is_enabled()

                browser.close()

        finally:
            if proc.poll() is None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    else:
                        proc.terminate()
                except Exception:
                    proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
