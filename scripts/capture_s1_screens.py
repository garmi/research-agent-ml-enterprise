"""Capture 3 screenshots of the S1 intake UI states using Playwright."""

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
    repo_root = Path.cwd()
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
                page = browser.new_page(viewport={"width": 1280, "height": 1100})
                page.goto(f"{server_url}/?stub=1", wait_until="networkidle")
                time.sleep(2)

                # State 1: Empty
                print("Capturing State 1 (empty)...")
                path_1 = screens_dir / "01_intake_empty.png"
                page.screenshot(path=str(path_1), full_page=True)
                print(f"Saved: {path_1}")

                # State 2: Framings shown
                print("Entering question text...")
                q1_text = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
                page.locator("textarea").first.fill(q1_text)
                page.locator("textarea").first.press("Tab")
                time.sleep(2)

                print("Capturing State 2 (framings shown)...")
                path_2 = screens_dir / "02_intake_framings_shown.png"
                page.screenshot(path=str(path_2), full_page=True)
                print(f"Saved: {path_2}")

                # State 3: Approved with Run enabled
                print("Clicking Approve this framing...")
                approve_btn = page.locator('button:has-text("Approve this framing")')
                approve_btn.click()
                time.sleep(2)

                print("Capturing State 3 (approved with Run enabled)...")
                path_3 = screens_dir / "03_intake_approved_run_enabled.png"
                page.screenshot(path=str(path_3), full_page=True)
                print(f"Saved: {path_3}")

                browser.close()
                print("Done capturing screenshots.")

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
