"""Capture screenshots of the S1 intake UI states using Playwright (Slice S1 Round 3).

Captures:
1. 01_intake_empty.png (empty state)
2. 02_intake_framings_shown.png (framings shown)
3. 03_intake_approved_run_enabled.png (approved with Run enabled)
4. 04_intake_edited_after_approval.png (edited after approval)
5. 05_intake_approved_dark_mode.png (approved state in dark mode)
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
from pathlib import Path
from playwright.sync_api import sync_playwright


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status in (200, 304)
    except Exception:
        return False


def main():
    repo_root = Path(__file__).resolve().parent.parent
    screens_dir = repo_root / "docs" / "screens" / "s1"
    screens_dir.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
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
            print("Waiting for Streamlit server to start...")
            ready = False
            for _ in range(30):
                if is_ready(f"{server_url}/_stcore/health") or is_ready(server_url):
                    ready = True
                    break
                time.sleep(0.5)

            if not ready:
                print("Server failed to start in 15s")
                sys.exit(1)

            print("Server ready, launching Playwright...")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )

                # --------------------------------------------------------------
                # Light Mode Context
                # --------------------------------------------------------------
                context = browser.new_context(viewport={"width": 1280, "height": 1700})
                page = context.new_page()
                page.goto(f"{server_url}/", wait_until="networkidle")
                time.sleep(2)

                # State 1: Empty
                print("Capturing State 1 (empty)...")
                path_1 = screens_dir / "01_intake_empty.png"
                page.screenshot(path=str(path_1), full_page=True)
                print(f"Saved: {path_1.name}")

                # State 2: Framings shown
                print("Entering question text...")
                q1_text = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
                page.locator("textarea").first.fill(q1_text)
                page.locator("textarea").first.press("Tab")
                time.sleep(2)

                print("Capturing State 2 (framings shown)...")
                path_2 = screens_dir / "02_intake_framings_shown.png"
                page.screenshot(path=str(path_2), full_page=True)
                print(f"Saved: {path_2.name}")

                # State 3: Approved with Run enabled
                print("Clicking Approve this framing...")
                approve_btn = page.locator('button:has-text("Approve this framing")')
                approve_btn.click()
                time.sleep(2)

                print("Capturing State 3 (approved with Run enabled)...")
                path_3 = screens_dir / "03_intake_approved_run_enabled.png"
                page.screenshot(path=str(path_3), full_page=True)
                print(f"Saved: {path_3.name}")

                # State 4: Edited after approval
                print("Editing question text after approval...")
                page.locator("textarea").first.fill(q1_text + " and code quality metrics")
                page.locator("textarea").first.press("Tab")
                time.sleep(2)

                print("Capturing State 4 (edited after approval)...")
                path_4 = screens_dir / "04_intake_edited_after_approval.png"
                page.screenshot(path=str(path_4), full_page=True)
                print(f"Saved: {path_4.name}")

                context.close()

                # --------------------------------------------------------------
                # Dark Mode Context (Approved State: Deliberately Always Light)
                # --------------------------------------------------------------
                print("Setting up dark mode context...")
                dark_context = browser.new_context(
                    viewport={"width": 1280, "height": 1700},
                    color_scheme="dark",
                )
                dark_page = dark_context.new_page()
                dark_page.emulate_media(color_scheme="dark")
                dark_page.goto(f"{server_url}/", wait_until="networkidle")
                time.sleep(2)

                dark_page.locator("textarea").first.fill(q1_text)
                dark_page.locator("textarea").first.press("Tab")
                time.sleep(2)
                dark_approve_btn = dark_page.locator('button:has-text("Approve this framing")')
                dark_approve_btn.click()
                time.sleep(2)

                print("Capturing State 5 (approved state in dark OS mode - always light)...")
                path_5 = screens_dir / "05_intake_always_light_in_dark_os.png"
                dark_page.screenshot(path=str(path_5), full_page=True)
                print(f"Saved: {path_5.name}")

                dark_context.close()
                browser.close()
                print("Done capturing all screenshots.")

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


if __name__ == "__main__":
    main()
