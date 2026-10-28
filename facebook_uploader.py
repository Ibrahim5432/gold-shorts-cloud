#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة الرفع التلقائي إلى فيسبوك ريلز (Facebook Reels) عبر المتصفح مباشرة
بدون الحاجة لموقع مطوري فيسبوك (Meta for Developers) أو أي مفاتيح API
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import date

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("FacebookUploader")


class FacebookUploader:
    def __init__(self, project_dir: Path = None, **kwargs):
        self.project_dir = project_dir or Path(__file__).parent.resolve()
        self.profile_dir = self.project_dir / "fb_browser_profile"

    def _launch_browser(self, p, headless: bool = False):
        """تشغيل متصفح Chrome أو Edge مع ملف تعريف دائم أو ملف جلسة سحابي (GitHub Actions)"""
        import json
        self.profile_dir.mkdir(exist_ok=True)
        cloud_state = self.project_dir / "cloud_auth_state.json"

        ctx = None
        for channel in ["chrome", "msedge"]:
            try:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel=channel,
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                        "--new-window",
                    ],
                    no_viewport=True,
                )
                break
            except Exception as e:
                logger.warning(f"تعذر تشغيل {channel}: {e}")
                continue

        if ctx is None:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                no_viewport=True,
            )

        # حقن جلسة الدخول السحابية تلقائياً إذا كنا على سيرفر سحابي (GitHub Actions)
        if cloud_state.exists():
            try:
                existing_names = {c.get("name") for c in ctx.cookies()}
                if "c_user" not in existing_names:
                    state_data = json.loads(cloud_state.read_text(encoding="utf-8"))
                    if state_data.get("cookies"):
                        ctx.add_cookies(state_data["cookies"])
                        logger.info("☁️ تم تحميل جلسة الدخول السحابية لفيسبوك بنجاح!")
            except Exception as e:
                logger.warning(f"تنبيه أثناء قراءة الجلسة السحابية: {e}")

        return ctx

    def _click_button_by_texts(self, page, texts, timeout=4000) -> bool:
        """محاولة الضغط على زر يطابق أحد النصوص بدقة"""
        for txt in texts:
            try:
                loc = page.locator(f'div[role="button"][aria-label="{txt}"]')
                if loc.count() > 0 and loc.last.is_visible():
                    loc.last.click(timeout=timeout)
                    logger.info(f"تم الضغط على زر (aria-label): {txt}")
                    return True
            except Exception:
                pass

            try:
                loc = page.get_by_role("button", name=txt, exact=True)
                if loc.count() > 0 and loc.last.is_visible():
                    loc.last.click(timeout=timeout)
                    logger.info(f"تم الضغط على زر (exact role): {txt}")
                    return True
            except Exception:
                pass

            try:
                loc = page.locator(f'div[role="button"] span:text-is("{txt}")')
                if loc.count() > 0 and loc.last.is_visible():
                    loc.last.click(timeout=timeout)
                    logger.info(f"تم الضغط على زر (span text-is): {txt}")
                    return True
            except Exception:
                pass
        return False

    def _perform_reels_upload_on_page(self, page, video_path: Path, description: str = None) -> str:
        """تنفيذ خطوات رفع الريلز داخل صفحة المتصفح المفتوحة"""
        today_str = date.today().strftime("%Y/%m/%d")
        if not description:
            description = (
                f"أسعار الذهب اليوم في تركيا ({today_str}) لجميع العيارات وسعر الأونصة بالدولار ₺\n"
                "#ذهب #أسعار_الذهب #تركيا #ريلز #reels #gold"
            )

        temp_dir = self.project_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        logger.info(f"🚀 بدء رفع الريلز تلقائياً إلى فيسبوك: {video_path.name}")
        logger.info("فتح صفحة إنشاء ريلز فيسبوك...")
        page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        logger.info(f"الرابط الحالي: {page.url} | العنوان: {page.title()}")

        if "login" in page.url.lower() or page.locator('input[name="email"]').count() > 0:
            logger.warning("⚠️ المتصفح غير مسجل الدخول إلى فيسبوك بعد!")
            page.screenshot(path=str(temp_dir / "fb_not_logged_in.png"))
            return None

        # 1. اختيار ملف الفيديو
        file_inputs = page.locator('input[type="file"]')
        logger.info(f"عدد حقول رفع الملفات الموجودة: {file_inputs.count()}")
        file_inputs.first.set_input_files(str(video_path))
        logger.info("✅ تم إرفاق ملف الفيديو بنجاح، جاري المعالجة...")
        time.sleep(10)
        page.screenshot(path=str(temp_dir / "fb_step1_uploaded.png"))

        # طباعة جميع الأزرار المرئية للتشخيص الدقيق
        try:
            btns_info = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('div[role="button"], button')).map(el => ({
                    text: (el.innerText || '').trim().replace(/\\n/g, ' '),
                    aria: el.getAttribute('aria-label') || '',
                    disabled: el.getAttribute('aria-disabled') || '',
                    rect: el.getBoundingClientRect().toJSON()
                })).filter(b => b.rect.width > 0 && b.rect.height > 0 && (b.text || b.aria));
            }""")
            logger.info(f"الأزرار المرئية في الصفحة: {btns_info}")
        except Exception as e:
            logger.warning(f"تعذر قراءة الأزرار: {e}")

        # 2. كتابة وصف الريلز أولاً إذا كان مربع الوصف ظاهراً مباشرة (التصميم الجديد لفيسبوك)
        desc_written = False
        try:
            textbox = page.locator('div[role="textbox"]').first
            if textbox.count() > 0 and textbox.is_visible():
                textbox.click(timeout=5000)
                textbox.fill(description)
                desc_written = True
                logger.info("✅ تم كتابة وصف الفيديو والهاشتاغات.")
                time.sleep(2)
                page.screenshot(path=str(temp_dir / "fb_step2_desc.png"))
        except Exception as e:
            logger.warning(f"تنبيه أثناء كتابة الوصف: {e}")

        # 3. إذا كان هناك زر (التالي / Next) نضغطه، وإلا نضغط (نشر / Publish) مباشرة
        for step in range(3):
            if self._click_button_by_texts(page, ["نشر", "Publish", "مشاركة", "Share"]):
                logger.info("🚀 تم الضغط على زر النشر مباشرة!")
                published = True
                break
            if self._click_button_by_texts(page, ["التالي", "Next"]):
                logger.info(f"تم الضغط على (التالي) - خطوة {step + 1}")
                time.sleep(5)
                page.screenshot(path=str(temp_dir / f"fb_step_next_{step}.png"))
                if not desc_written:
                    try:
                        textbox = page.locator('div[role="textbox"]').first
                        if textbox.count() > 0 and textbox.is_visible():
                            textbox.click(timeout=5000)
                            textbox.fill(description)
                            desc_written = True
                            logger.info("✅ تم كتابة وصف الفيديو والهاشتاغات.")
                            time.sleep(2)
                    except Exception:
                        pass
            else:
                time.sleep(2)
        else:
            published = self._click_button_by_texts(page, ["نشر", "Publish", "مشاركة", "Share"])

        page.screenshot(path=str(temp_dir / "fb_step4_publish.png"))

        if published:
            logger.info("🚀 تم الضغط على زر النشر! جاري انتظار اكتمال الرفع (30 ثانية)...")
            time.sleep(30)
            page.screenshot(path=str(temp_dir / "fb_step5_done.png"))
            logger.info("🎉 اكتملت عملية النشر على فيسبوك ريلز!")
            return "https://www.facebook.com/reels/"
        else:
            logger.warning("⚠️ يرجى الضغط على زر (نشر) في النافذة المفتوحة إذا لزم الأمر، سيتم الانتظار 30 ثانية...")
            time.sleep(30)
            page.screenshot(path=str(temp_dir / "fb_step5_done.png"))
            return "https://www.facebook.com/reels/"

    def setup_login(self, video_to_upload: Path = None):
        """فتح المتصفح لتسجيل الدخول إلى فيسبوك والتبديل إلى الصفحة ثم رفع أول فيديو مباشرة"""
        from playwright.sync_api import sync_playwright

        logger.info("📘 فتح نافذة إعداد ربط صفحة فيسبوك...")

        banner_js = """
        function updateAgyBar() {
            if (window.__AGY_UPLOADING__) {
                const b = document.getElementById('agy-fb-helper');
                if (b) {
                    b.style.background = '#0d6efd';
                    b.innerHTML = '<span>🚀 جاري رفع فيديو الذهب تلقائياً إلى صفحتك... لا تغلق النافذة حتى يكتمل الرفع!</span>';
                }
                return;
            }
            let bar = document.getElementById('agy-fb-helper');
            if (!bar) {
                bar = document.createElement('div');
                bar.id = 'agy-fb-helper';
                bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:999999;background:linear-gradient(90deg,#0f5132,#198754);color:#fff;padding:14px 20px;font-family:Tahoma,sans-serif;font-size:16px;font-weight:bold;text-align:center;box-shadow:0 -4px 12px rgba(0,0,0,0.3);direction:rtl;display:flex;justify-content:center;align-items:center;gap:20px;';
                document.body.appendChild(bar);
            }
            const isLoginPage = !!document.querySelector('input[name="email"], input[name="pass"]') || location.href.includes('login');
            if (isLoginPage) {
                bar.style.background = 'linear-gradient(90deg,#842029,#dc3545)';
                bar.innerHTML = '<span>🔐 الخطوة ١ من ٢: اكتب بريدك وكلمة سر فيسبوك في وسط الشاشة واضغط (تسجيل الدخول) أولاً!</span>';
            } else if (!window.__AGY_SETUP_DONE__) {
                bar.style.background = 'linear-gradient(90deg,#0f5132,#198754)';
                if (!document.getElementById('agy-done-btn')) {
                    bar.innerHTML = '<span>🎉 الخطوة ٢ من ٢: بعد التبديل إلى صفحتك من صورتك بالأعلى، اضغط هنا:</span>' +
                                    '<button id="agy-done-btn" style="background:#ffc107;color:#000;border:none;padding:8px 18px;border-radius:8px;font-family:Tahoma,sans-serif;font-size:15px;font-weight:bold;cursor:pointer;">✅ أنا الآن داخل صفحتي - ابدأ رفع الريلز الآن!</button>';
                    document.getElementById('agy-done-btn').addEventListener('click', () => {
                        window.__AGY_SETUP_DONE__ = true;
                        window.__AGY_UPLOADING__ = true;
                        bar.style.background = '#0d6efd';
                        bar.innerHTML = '<span>🚀 جاري رفع فيديو الذهب تلقائياً إلى صفحتك... لا تغلق النافذة!</span>';
                    });
                }
            }
        }
        window.addEventListener('DOMContentLoaded', () => {
            updateAgyBar();
            setInterval(updateAgyBar, 1000);
        });
        """

        with sync_playwright() as p:
            context = self._launch_browser(p, headless=False)
            context.add_init_script(banner_js)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            try:
                page.bring_to_front()
            except Exception:
                pass

            ready_to_upload = False
            active_page = page
            try:
                while len(context.pages) > 0:
                    for pg in list(context.pages):
                        try:
                            done = pg.evaluate("() => window.__AGY_SETUP_DONE__ === true")
                            if done:
                                ready_to_upload = True
                                active_page = pg
                                break
                        except Exception:
                            pass
                    if ready_to_upload:
                        break
                    time.sleep(1)

                if ready_to_upload and video_to_upload and video_to_upload.exists():
                    logger.info("✅ المستخدم أكد الدخول والتبديل للصفحة! بدء رفع الفيديو فوراً في نفس النافذة...")
                    self._perform_reels_upload_on_page(active_page, video_to_upload)
            except Exception as e:
                logger.error(f"خطأ أثناء الإعداد/الرفع: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass

        logger.info("✅ تم حفظ جلسة فيسبوك وإتمام العملية بنجاح!")

    def upload_video(
        self,
        video_path: Path,
        title: str = None,
        description: str = None,
    ) -> str:
        """رفع الفيديو تلقائياً كـ Facebook Reel عبر واجهة فيسبوك"""
        if not video_path.exists():
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {video_path}")

        if not self.profile_dir.exists() or not any(self.profile_dir.iterdir()):
            logger.warning("⚠️ لم يتم تسجيل الدخول لفيسبوك بعد. يرجى تشغيل connect_facebook.bat لمرة واحدة.")
            return None

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            context = self._launch_browser(p, headless=False)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                return self._perform_reels_upload_on_page(page, video_path, description=description)
            finally:
                try:
                    context.close()
                except Exception:
                    pass


if __name__ == "__main__":
    log_file = Path(__file__).parent.resolve() / "facebook_upload.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    project_dir = Path(__file__).parent.resolve()
    fb = FacebookUploader(project_dir)

    output_dir = project_dir / "output"
    videos = list(output_dir.glob("gold_price_*.mp4"))
    latest_video = sorted(videos)[-1] if videos else None

    if "--setup" in sys.argv:
        fb.setup_login(video_to_upload=latest_video)
    else:
        if latest_video:
            fb.upload_video(latest_video)
        else:
            print("لا يوجد فيديو في مجلد output/")
