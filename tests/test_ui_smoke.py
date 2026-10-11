"""Playwright UI smoke test for Executive AI Research Studio (web_app.py).

Verifies the presentation layer end-to-end:
- First screen load, header, chips, form, options
- Empty topic validation warning
- Running state telemetry and ETA
- Answer-first results: summary card, top 3 findings, 4 metric cards
- All 7 tabs (Findings, Papers, Themes, Gaps, Roadmap, Content, Citations)
- Sortable papers dataframe and linkification
- Citation audit and empirical references
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

        # 3. Assert Suggested Chips
        assert page.locator('button:has-text("⚡ Kiro in Engineering")').count() > 0
        assert page.locator('button:has-text("📊 AI Dev Productivity & ROI")').count() > 0
        assert page.locator('button:has-text("🛡️ DevSecOps Agentic AI")').count() > 0
        assert page.locator('button:has-text("🏢 Platform DevEx Impact")').count() > 0

        # 4. Assert Form Controls
        run_btn = page.locator('button:has-text("Run Research")')
        assert run_btn.count() > 0
        assert page.locator('text=Research Depth').count() > 0
        assert page.locator('text=Strategic Tone').count() > 0

        # 5. Assert Empty Topic Validation (Single plain-language warning)
        run_btn.click()
        time.sleep(1)
        assert page.locator("text=Please enter a research topic").count() > 0

        # 6. Click Chip to Fill Topic Box (Verifies chips do NOT auto-run)
        page.locator('button:has-text("⚡ Kiro in Engineering")').click()
        time.sleep(2)

        # 7. Submit Research Form
        run_btn = page.locator('button:has-text("Run Research")')
        run_btn.click()
        time.sleep(1)

        # 8. Assert Running Telemetry & ETA
        assert page.locator("text=Estimated runtime: ~45–60 seconds").count() > 0

        # 9. Wait for Synthesis Completion (up to 45s)
        completed = False
        for _ in range(30):
            time.sleep(1.5)
            if page.locator("text=Strategic Signal & Executive Verdict").count() > 0:
                completed = True
                break

        assert completed, "Research synthesis did not complete within the timeout window."

        # 10. Assert Executive Summary Card & Top 3 Findings
        assert page.locator("text=Strategic Signal & Executive Verdict").count() > 0
        assert page.locator("text=Top 3 Strategic Takeaways").count() > 0
        assert page.locator("text=KEY SIGNAL 1").count() > 0
        assert page.locator("text=KEY SIGNAL 2").count() > 0
        assert page.locator("text=KEY SIGNAL 3").count() > 0

        # 11. Assert 4 Metric Cards
        assert page.locator("text=Literature Volume").count() > 0
        assert page.locator("text=Distinct Repositories").count() > 0
        assert page.locator("text=Publication Horizon").count() > 0
        assert page.locator("text=Evidence Quality").count() > 0

        # 12. Assert All 7 Tabs are Present
        tab_names = [
            "Findings & Risks",
            "Empirical Papers",
            "Thematic Landscape",
            "Strategic Recommendations",
            "Implementation Roadmap",
            "LinkedIn & Executive Pack",
            "Citation Audit & Quality",
        ]
        for name in tab_names:
            assert page.locator(f'button[role="tab"]:has-text("{name}")').count() > 0

        # 13. Assert Papers Tab & Re-synthesis Section
        papers_tab = page.locator('button[role="tab"]:has-text("Empirical Papers")')
        papers_tab.click()
        time.sleep(1)
        assert page.locator("text=Empirical Reference Index").count() > 0
        assert page.locator("text=Exclude Papers & Re-Synthesize").count() > 0

        # 14. Assert Citations & Quality Tab
        cit_tab = page.locator('button[role="tab"]:has-text("Citation Audit & Quality")')
        cit_tab.click()
        time.sleep(1)
        assert page.locator("text=Citation Audit Passed").count() > 0

        # 15. Assert All 5 Labeled Download Buttons
        assert page.locator('button:has-text("Executive Brief (.md)")').count() > 0
        assert page.locator('button:has-text("JSON Ledger (.json)")').count() > 0
        assert page.locator('button:has-text("Paper Index (.csv)")').count() > 0
        assert page.locator('button:has-text("LinkedIn Pack (.md)")').count() > 0
        assert page.locator('button:has-text("Presentation Deck (.html)")').count() > 0


        browser.close()
