"""Capture real app screenshots and smoke-test core flows with synthetic data.

Optional dependency: pip install playwright==1.51.0; playwright install chromium
Run: python scripts/capture_demo.py
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from demo import ROOT, demo_environment, seed_demo


def main() -> None:
    from playwright.sync_api import sync_playwright

    output = ROOT / "docs" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    password = "Demo1!" + secrets.token_urlsafe(12)
    with tempfile.TemporaryDirectory(prefix="medsync-capture-") as folder:
        ids = seed_demo(Path(folder), password)
        with open(Path(folder) / "server.log", "w") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", str(ROOT / "src/web_app.py"),
                 "--server.address=127.0.0.1", "--server.port=8502", "--server.headless=true"],
                cwd=folder, env=demo_environment(dict(os.environ)), stdout=log, stderr=log,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Demo server exited before becoming ready")
                    try:
                        with urlopen("http://127.0.0.1:8502/_stcore/health", timeout=1):
                            break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Demo server did not become ready")

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        def login(role):
                            page = browser.new_page(viewport={"width": 1440, "height": 1280})
                            # No outbound browser requests; local fonts may fall back.
                            page.route("**/*", lambda route: route.continue_()
                                       if urlparse(route.request.url).hostname in {"localhost", "127.0.0.1"}
                                       else route.abort())
                            page.goto("http://127.0.0.1:8502")
                            page.get_by_role("button", name="Use email instead").click()
                            page.get_by_label("Email Address", exact=True).fill(f"{role}@example.test")
                            page.get_by_label("Password", exact=True).fill(password)
                            page.get_by_role("button", name="Sign In", exact=True).click()
                            page.get_by_role("heading", name="Today's medications" if role == "patient" else "Dashboard", exact=True).wait_for()
                            return page

                        patient = login("patient")
                        patient.get_by_role("heading", name="Sample A (demo)", exact=True).wait_for()
                        patient.wait_for_timeout(700)  # finish the real app's CSS transition
                        assert patient.locator("pre code").count() == 0  # notes must render as text, not raw HTML
                        patient.screenshot(path=str(output / "today.png"))
                        patient.get_by_role("button", name="I took it", exact=True).first.click()
                        patient.get_by_text("2/3", exact=True).wait_for()
                        patient.get_by_role("button", name="Snooze 30 min", exact=True).click()
                        patient.get_by_text("Snoozed from 8:00 PM", exact=True).wait_for()
                        patient.close()

                        caregiver = login("caregiver")
                        caregiver.wait_for_timeout(700)
                        caregiver.screenshot(path=str(output / "caregiver-dashboard.png"))
                        caregiver.get_by_role("button", name="View", exact=True).click()
                        caregiver.get_by_role("heading", name="Jordan Rivera (demo)", exact=True).wait_for()
                        caregiver.get_by_text("Daily Medication Adherence", exact=True).wait_for()
                        caregiver.wait_for_timeout(700)
                        caregiver.screenshot(path=str(output / "patient-details.png"))
                        caregiver.get_by_role("button", name="Back to dashboard", exact=True).click()
                        caregiver.get_by_role("button", name="Add med", exact=True).click()
                        caregiver.get_by_role("heading", name="Add a medication", exact=True).wait_for()
                        caregiver.close()

                        viewer = login("viewer")
                        assert viewer.get_by_role("button", name="Add med", exact=True).count() == 0
                        viewer.get_by_role("link", name="Today's meds", exact=True).click()
                        viewer.get_by_text("View only", exact=True).wait_for()
                        assert viewer.get_by_role("button", name="I took it", exact=True).count() == 0
                        viewer.set_viewport_size({"width": 375, "height": 900})
                        viewer.wait_for_timeout(700)
                        assert viewer.locator('[data-testid="stException"]').count() == 0
                        viewer.close()
                        print("PASS: email sign-in, patient dose logging/snooze, caregiver View/Add med, view-only controls, 375px render")
                        print("Captured three unmodified application screenshots using disposable synthetic SQLite data.")
                    finally:
                        browser.close()
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    main()
