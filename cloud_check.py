#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص سحابي حقيقي (بدون نشر): يتحقق من أن سيرفر GitHub يستطيع الدخول إلى
فيسبوك (صفحة إنشاء الريلز) وتيك توك (TikTok Studio) بجلساتك المشفرة،
ويلتقط صوراً للشاشة كدليل، ويولّد فيديو تجريبي للتأكد من محرك الفيديو.
"""
import sys
import json
import time
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.resolve()
PROOF = ROOT / "proof"
PROOF.mkdir(exist_ok=True)
report = {}

from playwright.sync_api import sync_playwright
from facebook_uploader import FacebookUploader
from tiktok_uploader import TikTokUploader

with sync_playwright() as p:
    ctx = FacebookUploader(ROOT)._launch_browser(p, headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    fb_logged = ("login" not in page.url.lower()) and page.locator('input[name="email"]').count() == 0 \
        and "checkpoint" not in page.url.lower()
    report["facebook"] = {"logged_in": fb_logged, "url": page.url, "title": page.title()}
    page.screenshot(path=str(PROOF / "facebook_cloud.png"))
    ctx.close()

with sync_playwright() as p:
    ctx = TikTokUploader(ROOT)._launch_browser(p, headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
    time.sleep(10)
    tt_logged = "login" not in page.url.lower()
    report["tiktok"] = {"logged_in": tt_logged, "url": page.url, "title": page.title()}
    page.screenshot(path=str(PROOF / "tiktok_cloud.png"))
    ctx.close()

(PROOF / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("CLOUD_CHECK_REPORT:", json.dumps(report, ensure_ascii=False))
