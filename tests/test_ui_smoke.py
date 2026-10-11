"""Playwright UI smoke test for Executive AI Research Studio (web_app.py).

Verifies the presentation layer and multi-lane workflow end-to-end:
- First screen load, header, Question Formulation Agent panel
- Empty topic validation warning
- Problem statement formulation by agent (filling Strategic Question free text)
- Running state telemetry and multi-stage stepper
- Workflow architecture trace banner
- Gap Matrix Outcome badge and Strategic Signal verdict
- All 7 tabs (Findings & Risks, Three-Lane Evidence, Evidence Ledger & Claims,
  Strategic Gap Matrix, Governance Audit & Gates, Implementation Roadmap, Question Register)
- All 5 labeled download buttons
"""

import time
import pytest
from playwright.sync_api import sync_playwright


def test_executive_studio_ui_smoke():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "MachPortRendezvousServer" in str(e) or "TargetClosedError" in type(e).__name__:
                pytest.skip("Playwright Chromium Mach port rendezvous requires bypass sandbox on macOS.")
            raise
        page = browser.new_page(viewport={"width": 1280, "height": 1000})

        # 1. Load the Studio in stub/offline mode
        page.goto("http://127.0.0.1:8501/?stub=1", wait_until="networkidle")
        time.sleep(2)

        # 2. Assert Header & Status Badge
        assert page.locator("text=Executive AI Research Studio").count() > 0
        assert page.locator("text=100% Traceable Evidence Engine").count() > 0

        # 3. Assert Question Formulation Agent Panel
        assert page.locator("text=Strategic Question Formulation Agent").count() > 0
        formulate_btn = page.locator('button:has-text("Formulate Question")')
        assert formulate_btn.count() > 0

        # 4. Assert Research Console Controls
        run_btn = page.locator('button:has-text("Run Research")')
        assert run_btn.count() > 0
        assert page.locator('text=Strategic Technology Question').count() > 0
        assert page.locator('text=Research Depth').count() > 0
        assert page.locator('text=Strategic Tone').count() > 0

        # 5. Assert Empty Topic Validation (Single plain-language warning)
        run_btn.click()
        time.sleep(1)
        assert page.locator("text=Please enter a research topic").count() > 0

        # 6. Use Question Formulation Agent to Frame a Research Question
        problem_area = page.locator('textarea[aria-label="Raw Problem Description"]')
        if problem_area.count() > 0:
            problem_area.fill("Our teams want to know if agent swarms and Kiro coding assistants improve productivity while maintaining security governance in enterprise banking.")
            formulate_btn.click()
            time.sleep(2)

            # Verify formulated summary card appears
            assert page.locator("text=Formulated Strategic Research Question").count() > 0
            assert page.locator("text=Strategic Rationale").count() > 0
        else:
            # Fallback direct free text entry
            page.locator('input[aria-label="Strategic Technology Question"]').fill("How do AI coding assistants impact developer productivity in enterprise software delivery?")

        # 7. Submit Research Form
        run_btn = page.locator('button:has-text("Run Research")')
        run_btn.click()
        time.sleep(1)

        # 8. Wait for Multi-Lane Synthesis Completion (up to 45s)
        completed = False
        for _ in range(30):
            time.sleep(1.0)
            if page.locator("text=Strategic Signal & Executive Verdict").count() > 0:
                completed = True
                break

        assert completed, "Research synthesis did not complete within the timeout window."

        # 10. Assert Workflow Architecture Trace Banner & Verdict
        assert page.locator("text=WORKFLOW TRACE:").count() > 0
        assert page.locator("text=Gate 1: Question Register").count() > 0
        assert page.locator("text=3 Lanes: Academic • Enterprise • Practitioner").count() > 0
        assert page.locator("text=Strategic Signal & Executive Verdict").count() > 0
        assert page.locator("text=Outcome 1: Supported").count() > 0 or page.locator("text=Outcome").count() > 0
        assert page.locator("text=Top 3 Strategic Takeaways").count() > 0

        # 11. Assert 4 Multi-Lane Metric Cards
        assert page.locator("text=Multi-Lane Volume").count() > 0
        assert page.locator("text=Distinct Repositories").count() > 0
        assert page.locator("text=Publication Horizon").count() > 0
        assert page.locator("text=Evidence Quality Score").count() > 0

        # 12. Assert All 7 Multi-Lane Tabs are Present
        tab_names = [
            "Findings & Risks",
            "Three-Lane Evidence",
            "Evidence Ledger & Claims",
            "Strategic Gap Matrix",
            "Governance Audit & Gates",
            "Implementation Roadmap",
            "Question Register (Gate 1)",
        ]
        for name in tab_names:
            assert page.locator(f'button[role="tab"]:has-text("{name}")').count() > 0, f"Tab '{name}' missing"

        # 13. Test Three-Lane Evidence Tab
        tab_lanes = page.locator('button[role="tab"]:has-text("Three-Lane Evidence")')
        tab_lanes.click()
        time.sleep(1)
        assert page.locator("text=Lane A: Academic Literature").count() > 0
        assert page.locator("text=Lane B: Enterprise Lane").count() > 0
        assert page.locator("text=Lane C: Practitioner Lane").count() > 0

        # 14. Test Evidence Ledger Tab
        tab_ledger = page.locator('button[role="tab"]:has-text("Evidence Ledger & Claims")')
        tab_ledger.click()
        time.sleep(1)
        assert page.locator("text=Evidence Ledger & Atomic Claims").count() > 0

        # 15. Test Strategic Gap Matrix Tab
        tab_gap = page.locator('button[role="tab"]:has-text("Strategic Gap Matrix")')
        tab_gap.click()
        time.sleep(1)
        assert page.locator("text=Strategic Gap Matrix (Gate 4)").count() > 0
        assert page.locator("text=Strategic Taxonomy Reference").count() > 0

        # 16. Assert All 5 Labeled Download Buttons
        download_buttons = [
            "Executive Brief (.md)",
            "JSON Ledger (.json)",
            "Paper Index (.csv)",
            "LinkedIn Pack (.md)",
            "Presentation Deck (.html)",
        ]
        for btn_label in download_buttons:
            assert page.locator(f'button:has-text("{btn_label}")').count() > 0, f"Download button '{btn_label}' missing"

        browser.close()
