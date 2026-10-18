"""Capture required Slice S2 screenshots at 1280x1700 using Playwright.

Generates:
  docs/screens/s2/01_empty.png
  docs/screens/s2/02_proposal_shown.png
  docs/screens/s2/03_edited.png
  docs/screens/s2/04_approved.png
  docs/screens/s2/05_no_model.png
  docs/screens/s2/06_error_case.png
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


def run_server(env_overrides: dict) -> tuple[subprocess.Popen, str, tempfile.TemporaryDirectory]:
    port = find_free_port()
    server_url = f"http://127.0.0.1:{port}"
    tmp_home = tempfile.TemporaryDirectory()

    st_dir = os.path.join(tmp_home.name, ".streamlit")
    os.makedirs(st_dir, exist_ok=True)
    with open(os.path.join(st_dir, "credentials.toml"), "w", encoding="utf-8") as f:
        f.write('[general]\nemail = ""\n')
    with open(os.path.join(st_dir, "config.toml"), "w", encoding="utf-8") as f:
        f.write('[server]\nheadless = true\n[browser]\ngatherUsageStats = false\n')

    env = dict(os.environ)
    env["HOME"] = tmp_home.name
    env["PYTHONPATH"] = "."
    tmp_approvals = os.path.join(tmp_home.name, "approvals")
    tmp_outputs = os.path.join(tmp_home.name, "outputs")
    os.makedirs(tmp_approvals, exist_ok=True)
    os.makedirs(tmp_outputs, exist_ok=True)
    env["RESEARCH_APPROVALS_DIR"] = tmp_approvals
    env["OUTPUT_DIR"] = tmp_outputs
    env.update(env_overrides)

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

    for _ in range(30):
        if is_ready(f"{server_url}/_stcore/health") or is_ready(server_url):
            return proc, server_url, tmp_home
        time.sleep(0.5)

    proc.kill()
    tmp_home.cleanup()
    raise RuntimeError(f"Server on {server_url} failed to start")


def kill_proc(proc: subprocess.Popen):
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


def main():
    repo_root = Path(__file__).resolve().parent.parent
    screens_dir = repo_root / "docs" / "screens" / "s2"
    screens_dir.mkdir(parents=True, exist_ok=True)

    sample_query = (
        "AI coding assistants like Kiro are obviously doubling enterprise delivery velocity without any risk. "
        "However, some skeptical architects worry about technical debt. "
        "How does actual code review throughput change in practice?"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        # ----------------------------------------------------------------------
        # Session 1: Stub mode for 01_empty, 02_proposal_shown, 03_edited, 04_approved
        # ----------------------------------------------------------------------
        print("Starting Server 1 (STUB_LLM=1)...")
        proc1, url1, tmp1 = run_server({
            "HOSTED_DEMO": "0",
            "STUB_LLM": "1",
        })

        try:
            context = browser.new_context(viewport={"width": 1280, "height": 1700})
            page = context.new_page()
            page.goto(url1, wait_until="networkidle")
            time.sleep(2)

            # 01_empty.png
            print("Capturing 01_empty.png...")
            p1 = screens_dir / "01_empty.png"
            page.screenshot(path=str(p1), full_page=True)
            print(f"  Saved {p1.name}")

            # Enter question & reason
            print("Entering query and clicking Reason about my question...")
            page.locator("textarea").first.fill(sample_query)
            page.locator("textarea").first.press("Tab")
            time.sleep(1)

            reason_btn = page.locator('button:has-text("Reason about my question")')
            reason_btn.click()
            page.wait_for_selector('button:has-text("Approve this reasoned question")', timeout=10000)
            time.sleep(1)

            # Expand the changes & coverage expander so it is visible in screenshot
            expander = page.locator('text=View Changes, Reasons & 100% Sentence Coverage Map')
            if expander.count() > 0:
                expander.click()
                time.sleep(1)

            # 02_proposal_shown.png
            print("Capturing 02_proposal_shown.png...")
            p2 = screens_dir / "02_proposal_shown.png"
            page.screenshot(path=str(p2), full_page=True)
            print(f"  Saved {p2.name}")

            # Edit field
            print("Editing refined question field...")
            refined_input = page.locator('input[aria-label="Refined Research Question (One neutral, answerable sentence):"]')
            if refined_input.count() > 0:
                refined_input.fill("What measurable productivity impact do AI coding assistants have on enterprise software delivery velocity and code quality?")
                refined_input.press("Tab")
            else:
                # fallback text input
                page.locator('input[type="text"]').first.fill("What measurable productivity impact do AI coding assistants have on enterprise software delivery velocity and code quality?")
                page.locator('input[type="text"]').first.press("Tab")
            time.sleep(1)

            # 03_edited.png
            print("Capturing 03_edited.png...")
            p3 = screens_dir / "03_edited.png"
            page.screenshot(path=str(p3), full_page=True)
            print(f"  Saved {p3.name}")

            # Confirm terms checkbox if present
            confirm_lbl = page.locator("label:has-text('I acknowledge and confirm')")
            if confirm_lbl.count() > 0:
                confirm_lbl.first.click()
                time.sleep(1)

            # Approve
            print("Clicking Approve this reasoned question...")
            approve_btn = page.locator('button:has-text("Approve this reasoned question")')
            approve_btn.click()
            time.sleep(2)

            # 04_approved.png
            print("Capturing 04_approved.png...")
            p4 = screens_dir / "04_approved.png"
            page.screenshot(path=str(p4), full_page=True)
            print(f"  Saved {p4.name}")

            context.close()
        finally:
            kill_proc(proc1)
            tmp1.cleanup()

        # ----------------------------------------------------------------------
        # Session 2: No Model Available for 05_no_model.png
        # ----------------------------------------------------------------------
        print("\nStarting Server 2 (No Model: STUB_LLM=0, GEMINI_API_KEY unset, Ollama offline)...")
        proc2, url2, tmp2 = run_server({
            "HOSTED_DEMO": "0",
            "STUB_LLM": "0",
            "GEMINI_API_KEY": "",
            "OLLAMA_BASE_URL": "http://127.0.0.1:9999",
        })

        try:
            context = browser.new_context(viewport={"width": 1280, "height": 1700})
            page = context.new_page()
            page.goto(url2, wait_until="networkidle")
            time.sleep(2)

            page.locator("textarea").first.fill(sample_query)
            page.locator("textarea").first.press("Tab")
            time.sleep(1)

            reason_btn = page.locator('button:has-text("Reason about my question")')
            reason_btn.click()
            time.sleep(2)

            # 05_no_model.png
            print("Capturing 05_no_model.png...")
            p5 = screens_dir / "05_no_model.png"
            page.screenshot(path=str(p5), full_page=True)
            print(f"  Saved {p5.name}")

            context.close()
        finally:
            kill_proc(proc2)
            tmp2.cleanup()

        # ----------------------------------------------------------------------
        # Session 3: Validation Error Case for 06_error_case.png
        # ----------------------------------------------------------------------
        print("\nStarting Server 3 (Validation Error Simulation)...")
        proc3, url3, tmp3 = run_server({
            "HOSTED_DEMO": "0",
            "STUB_LLM": "1",
            "TEST_TRIGGER_REASONING_ERROR": "1",
        })

        try:
            context = browser.new_context(viewport={"width": 1280, "height": 1700})
            page = context.new_page()
            page.goto(url3, wait_until="networkidle")
            time.sleep(2)

            page.locator("textarea").first.fill(sample_query)
            page.locator("textarea").first.press("Tab")
            time.sleep(1)

            reason_btn = page.locator('button:has-text("Reason about my question")')
            reason_btn.click()
            time.sleep(2)

            # 06_error_case.png
            print("Capturing 06_error_case.png...")
            p6 = screens_dir / "06_error_case.png"
            page.screenshot(path=str(p6), full_page=True)
            print(f"  Saved {p6.name}")

            context.close()
        finally:
            kill_proc(proc3)
            tmp3.cleanup()

        browser.close()
        print("\nAll 6 screenshots captured successfully in docs/screens/s2/!")


if __name__ == "__main__":
    main()
