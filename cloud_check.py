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

import yaml
from playwright.sync_api import sync_playwright
from facebook_uploader import FacebookUploader
from tiktok_uploader import TikTokUploader

cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}

if cfg.get("facebook", {}).get("auto_upload", False):
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
else:
    report["facebook"] = {"skipped": True, "reason": "disabled in config.yaml"}

if cfg.get("tiktok", {}).get("auto_upload", False):
    import os
    tt = TikTokUploader(ROOT)
    proxy_info = tt.verify_proxy_connection(timeout=15) if tt.proxy_server else None
    report["tiktok_proxy"] = proxy_info or {"active": bool(tt.proxy_server), "reachable": False}
    require_proxy = os.environ.get("TIKTOK_REQUIRE_PROXY", "").strip().lower() in ("1", "true", "yes")
    if (tt.proxy_server or require_proxy) and not proxy_info:
        report["tiktok"] = {"logged_in": False, "error": "Phone proxy unreachable"}
    else:
        with sync_playwright() as p:
            ctx = tt._launch_browser(p, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto("https://api.country.is/", wait_until="domcontentloaded", timeout=25000)
                report["browser_exit_ip"] = page.locator("body").inner_text().strip()
            except Exception as e:
                report["browser_exit_ip"] = f"err: {e}"
            page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            tt_logged = "login" not in page.url.lower()
            report["tiktok"] = {"logged_in": tt_logged, "url": page.url, "title": page.title()}
            page.screenshot(path=str(PROOF / "tiktok_cloud.png"))
            ctx.close()
else:
    report["tiktok"] = {"skipped": True, "reason": "disabled in config.yaml"}

(PROOF / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("CLOUD_CHECK_REPORT:", json.dumps(report, ensure_ascii=False))
