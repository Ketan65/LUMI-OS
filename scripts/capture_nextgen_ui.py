"""Capture High-Resolution Screenshots of the Next-Gen Smooth & Attractive UI, including dedicated Topbar HUD."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8765"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        print("[+] Navigating to LUMI UI...")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(2500)

        # Remove alert banners if any
        await page.evaluate("""
            () => {
                const b = document.getElementById('alertBanner');
                if (b) b.remove();
                const b2 = document.getElementById('banner');
                if (b2) b2.remove();
            }
        """)

        # 0. Dedicated Topbar HUD close-up crop
        print("[+] Capturing 00_nextgen_topbar_hud.png...")
        topbar_el = page.locator(".topbar")
        await topbar_el.screenshot(path=str(OUTPUT_DIR / "00_nextgen_topbar_hud.png"))

        # 1. Living Orb View (JARVIS Mode)
        print("[+] Capturing 01_nextgen_living_orb.png...")
        await page.evaluate("setAppMode('jarvis')")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUTPUT_DIR / "01_nextgen_living_orb.png"))

        # 2. Chat View
        print("[+] Capturing 02_nextgen_chat_view.png...")
        await page.evaluate("setAppMode('chat')")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "02_nextgen_chat_view.png"))

        # 3. Nexus Cockpit View
        print("[+] Capturing 03_nextgen_nexus_cockpit.png...")
        await page.evaluate("setAppMode('nexus')")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "03_nextgen_nexus_cockpit.png"))

        # 4. Swarm Dev View
        print("[+] Capturing 04_nextgen_swarm_dev.png...")
        await page.evaluate("setAppMode('swarm')")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "04_nextgen_swarm_dev.png"))

        await browser.close()
        print("[OK] All next-gen UI screenshots captured successfully!")


if __name__ == "__main__":
    asyncio.run(main())
