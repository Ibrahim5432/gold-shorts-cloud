#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة الرفع التلقائي إلى تيك توك (TikTok) عبر المتصفح مباشرة
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

logger = logging.getLogger("TikTokUploader")


class TikTokUploader:
    def __init__(
        self,
        project_dir: Path = None,
        proxy_server: str = None,
        proxy_username: str = None,
        proxy_password: str = None,
        **kwargs,
    ):
        self.project_dir = project_dir or Path(__file__).parent.resolve()
        self.profile_dir = self.project_dir / "fb_browser_profile"

        raw_srv = (proxy_server or os.environ.get("TIKTOK_PROXY_SERVER", "")).strip()
        if raw_srv and "://" not in raw_srv:
            raw_srv = f"http://{raw_srv}"
        self.proxy_server = raw_srv.rstrip("/")
        self.proxy_username = (proxy_username or os.environ.get("TIKTOK_PROXY_USERNAME", "")).strip()
        self.proxy_password = (proxy_password or os.environ.get("TIKTOK_PROXY_PASSWORD", "")).strip()

    def get_playwright_proxy(self) -> dict | None:
        if not self.proxy_server:
            return None
        cfg = {"server": self.proxy_server}
        if self.proxy_username:
            cfg["username"] = self.proxy_username
        if self.proxy_password:
            cfg["password"] = self.proxy_password
        return cfg

    def get_requests_proxies(self) -> dict | None:
        if not self.proxy_server:
            return None
        from urllib.parse import quote
        scheme, rest = self.proxy_server.split("://", 1)
        if self.proxy_username:
            auth = f"{quote(self.proxy_username, safe='')}:{quote(self.proxy_password, safe='')}@"
        else:
            auth = ""
        proxy_url = f"{scheme}://{auth}{rest}"
        return {"http": proxy_url, "https": proxy_url}

    def verify_proxy_connection(self, timeout: int = 12) -> dict | None:
        """التحقق من أن بروكسي الهاتف متصل فعلاً وجلب الدولة والمدينة بدون الرفع عبر IP أمريكي"""
        proxies = self.get_requests_proxies()
        if not proxies:
            return None
        import requests
        endpoints = [
            "https://ipinfo.io/json",
            "https://api.country.is/",
            "https://api.ipify.org?format=json",
        ]
        for url in endpoints:
            try:
                r = requests.get(url, proxies=proxies, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    country = data.get("country") or "?"
                    city = data.get("city") or ""
                    org = data.get("org") or ""
                    ip = data.get("ip") or "?"
                    logger.info(f"🌐 بروكسي الهاتف متصل بنجاح | IP={ip} | الدولة={country} | المدينة={city} | المزود={org}")
                    return data
            except Exception as e:
                logger.warning(f"محاولة فحص البروكسي عبر {url}: {e}")
        return None

    def _launch_browser(self, p, headless: bool = False):
        """تشغيل متصفح Chrome أو Edge مع ملف التعريف الدائم أو الجلسة السحابية (GitHub Actions)"""
        import json
        self.profile_dir.mkdir(exist_ok=True)
        cloud_state = self.project_dir / "cloud_auth_state.json"

        proxy_cfg = self.get_playwright_proxy()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--new-window",
        ]
        if proxy_cfg:
            launch_args.extend([
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--enforce-webrtc-ip-permission-check",
            ])

        ctx = None
        for channel in ["chrome", "msedge"]:
            try:
                ctx_kwargs = {
                    "user_data_dir": str(self.profile_dir),
                    "channel": channel,
                    "headless": headless,
                    "timezone_id": "Europe/Istanbul",
                    "locale": "ar-SY",
                    "args": launch_args,
                    "no_viewport": True,
                }
                if proxy_cfg:
                    ctx_kwargs["proxy"] = proxy_cfg
                ctx = p.chromium.launch_persistent_context(**ctx_kwargs)
                break
            except Exception as e:
                logger.warning(f"تعذر تشغيل {channel}: {e}")
                continue

        if ctx is None:
            fallback_args = ["--disable-blink-features=AutomationControlled", "--start-maximized"]
            if proxy_cfg:
                fallback_args.extend([
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--enforce-webrtc-ip-permission-check",
                ])
            ctx_kwargs = {
                "user_data_dir": str(self.profile_dir),
                "headless": headless,
                "timezone_id": "Europe/Istanbul",
                "locale": "ar-SY",
                "args": fallback_args,
                "no_viewport": True,
            }
            if proxy_cfg:
                ctx_kwargs["proxy"] = proxy_cfg
            ctx = p.chromium.launch_persistent_context(**ctx_kwargs)

        try:
            ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        except Exception:
            pass

        # حقن جلسة الدخول السحابية تلقائياً إذا كنا على سيرفر سحابي (GitHub Actions)
        if cloud_state.exists():
            try:
                existing_names = {c.get("name") for c in ctx.cookies()}
                if "uid_tt" not in existing_names and "sid_guard" not in existing_names:
                    state_data = json.loads(cloud_state.read_text(encoding="utf-8"))
                    if state_data.get("cookies"):
                        ctx.add_cookies(state_data["cookies"])
                        logger.info("☁️ تم تحميل جلسة الدخول السحابية لتيك توك بنجاح!")
            except Exception as e:
                logger.warning(f"تنبيه أثناء قراءة الجلسة السحابية: {e}")

        return ctx

    def _perform_tiktok_upload_on_page(self, page, video_path: Path, description: str = None) -> str:
        """تنفيذ خطوات رفع الفيديو على TikTok Studio داخل صفحة المتصفح"""
        today_str = date.today().strftime("%Y/%m/%d")
        if not description:
            description = (
                f"أسعار الذهب اليوم في تركيا ({today_str}) لجميع العيارات وسعر الأونصة بالدولار ₺ "
                "#ذهب #أسعار_الذهب #تركيا #اسطنبول #اكسبلور #gold #tiktok"
            )

        temp_dir = self.project_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        self._post_clicked = False
        logger.info(f"🚀 بدء رفع الفيديو تلقائياً إلى تيك توك: {video_path.name}")
        if "tiktokstudio/upload" not in page.url and "creator-center/upload" not in page.url:
            last_nav_err = None
            for nav_attempt in range(1, 4):
                try:
                    logger.info(f"فتح صفحة رفع تيك توك (TikTok Studio)... (محاولة {nav_attempt}/3)")
                    page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
                    last_nav_err = None
                    break
                except Exception as nav_err:
                    last_nav_err = nav_err
                    logger.warning(f"⚠️ تعثر لحظي أثناء فتح TikTok Studio (محاولة {nav_attempt}/3): {nav_err}")
                    if nav_attempt < 3:
                        time.sleep(7)
            if last_nav_err is not None:
                raise last_nav_err
            time.sleep(8)

        logger.info(f"الرابط الحالي لتيك توك: {page.url} | العنوان: {page.title()}")

        if "login" in page.url.lower():
            logger.warning("⚠️ المتصفح غير مسجل الدخول إلى تيك توك بعد!")
            page.screenshot(path=str(temp_dir / "tt_not_logged_in.png"))
            return None

        # إزالة شريط المساعدة إن وجد
        try:
            page.evaluate("() => document.getElementById('agy-tt-helper')?.remove()")
        except Exception:
            pass

        # 1. انتظار ظهور حقل رفع الملف في الصفحة الرئيسية أو داخل أي iframe (مهم مع بطء بروكسي الهاتف)
        target_frame = page
        file_inputs = page.locator('input[type="file"]')
        for fi_wait in range(18):
            try:
                if page.locator('input[type="file"]').count() > 0:
                    target_frame = page
                    file_inputs = page.locator('input[type="file"]')
                    break
                found_in_frame = False
                for frame in page.frames:
                    if frame.locator('input[type="file"]').count() > 0:
                        target_frame = frame
                        file_inputs = frame.locator('input[type="file"]')
                        found_in_frame = True
                        break
                if found_in_frame:
                    break
                if fi_wait == 9:
                    logger.info("🔄 إعادة تحميل صفحة TikTok Studio لظهور حقل رفع الملف...")
                    page.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                logger.warning(f"تنبيه أثناء انتظار حقل رفع الملف ({fi_wait + 1}): {e}")
            time.sleep(3)

        def _dismiss_popups():
            for sel in [
                '#react-joyride-portal button',
                'button:has-text("فهمت")',
                'button:has-text("Got it")',
                'button:has-text("حسناً")',
                'button:has-text("Not now")',
                'button:has-text("ليس الآن")',
                'div[role="button"]:has-text("فهمت")',
                'div[role="button"]:has-text("Got it")',
            ]:
                try:
                    btn = target_frame.locator(sel)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click(timeout=1500)
                        time.sleep(0.5)
                except Exception:
                    pass
            try:
                target_frame.evaluate("""() => {
                    const p = document.getElementById('react-joyride-portal');
                    if (p) p.remove();
                    document.querySelectorAll('.react-joyride__overlay').forEach(e => e.remove());
                }""")
            except Exception:
                pass

        logger.info(f"عدد حقول رفع الملفات الموجودة في تيك توك: {file_inputs.count()}")
        file_inputs.first.set_input_files(str(video_path), timeout=60000)
        logger.info("✅ تم إرفاق ملف الفيديو في تيك توك بنجاح، جاري انتظار تحميل محرر الفيديو...")

        # انتظار ظهور محرر TikTok Studio الفعلي (مربع الوصف وزر النشر) قبل إغلاق النوافذ أو الكتابة
        for ui_wait in range(30):
            _dismiss_popups()
            try:
                if target_frame.locator('div[contenteditable="true"]').count() > 0:
                    break
            except Exception:
                pass
            time.sleep(2)

        _dismiss_popups()
        page.screenshot(path=str(temp_dir / "tt_step1_uploaded.png"))

        # انتظار اكتمال رفع الفيديو بنسبة 100% (مهم خاصة عبر بروكسي الهاتف)
        for up_wait in range(36):
            _dismiss_popups()
            try:
                still_uploading = target_frame.evaluate("""() => {
                    const t = document.body ? document.body.innerText : '';
                    return /متبقي|\\bUploading\\b|\\bleft\\b|\\b\\d{1,2}(\\.\\d+)?%/.test(t);
                }""")
                if not still_uploading and up_wait >= 2:
                    logger.info("✅ اكتمل رفع ملف الفيديو إلى خوادم تيك توك بنسبة 100%.")
                    break
            except Exception:
                pass
            time.sleep(3)

        # 2. كتابة وصف الفيديو والهاشتاغات
        _dismiss_popups()
        try:
            editor = target_frame.locator('div[contenteditable="true"]').first
            if editor.count() > 0 and editor.is_visible():
                editor.click(timeout=5000)
                time.sleep(0.5)
                page.keyboard.press("Control+A")
                time.sleep(0.3)
                page.keyboard.press("Backspace")
                time.sleep(0.5)
                page.keyboard.insert_text(description)
                time.sleep(1)
                page.keyboard.press("Escape")
                logger.info("✅ تم كتابة وصف الفيديو والهاشتاغات في تيك توك.")
                time.sleep(2)
                page.screenshot(path=str(temp_dir / "tt_step2_desc.png"))
            else:
                logger.warning("⚠️ مربع وصف تيك توك لم يكن مرئياً للكتابة.")
        except Exception as e:
            logger.warning(f"تنبيه أثناء كتابة الوصف في تيك توك: {e}")

        # 3. التمرير لأسفل والانتظار حتى يكتمل فحص حقوق الطبع للموسيقى (~30 ثانية) قبل النشر
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
        except Exception:
            pass

        for chk_wait in range(15):
            _dismiss_popups()
            try:
                music_checking = target_frame.evaluate("""() => {
                    const t = document.body ? document.body.innerText : '';
                    return /٣٠ ثانية|30 seconds|30s/i.test(t) && /قيد التقدم|Checking/i.test(t);
                }""")
                if not music_checking:
                    logger.info("✅ انتهى فحص حقوق الطبع والنشر للموسيقى.")
                    break
                if chk_wait == 0:
                    logger.info("⏳ انتظار اكتمال فحص حقوق الطبع للموسيقى قبل النشر (~30 ثانية)...")
            except Exception:
                break
            time.sleep(3)

        # طباعة الأزرار المرئية للتشخيص
        try:
            btns_info = target_frame.evaluate("""() => {
                return Array.from(document.querySelectorAll('button, div[role="button"]')).map(el => ({
                    text: (el.innerText || '').trim().replace(/\\n/g, ' '),
                    e2e: el.getAttribute('data-e2e') || '',
                    disabled: el.disabled || el.getAttribute('aria-disabled') || '',
                    rect: el.getBoundingClientRect().toJSON()
                })).filter(b => b.rect.width > 0 && b.rect.height > 0 && (b.text || b.e2e));
            }""")
            logger.info(f"أزرار تيك توك المرئية: {btns_info}")
        except Exception as e:
            logger.warning(f"تعذر قراءة أزرار تيك توك: {e}")

        published = False
        # الانتظار حتى يصبح زر النشر الحقيقي (post_video_button) جاهزاً
        for attempt in range(12):
            _dismiss_popups()
            try:
                post_btn = target_frame.locator('button[data-e2e="post_video_button"]')
                if post_btn.count() == 0:
                    post_btn = target_frame.locator('button:text-is("Post"), button:text-is("نشر")')
                if post_btn.count() > 0:
                    btn = post_btn.first
                    is_disabled = (
                        btn.get_attribute("disabled") is not None
                        or btn.get_attribute("aria-disabled") == "true"
                        or btn.get_attribute("data-loading") == "true"
                    )
                    if not is_disabled:
                        btn.scroll_into_view_if_needed()
                        time.sleep(1)
                        self._post_clicked = True
                        btn.click(timeout=5000)
                        published = True
                        logger.info("🚀 تم الضغط على زر النشر الحقيقي (post_video_button) في تيك توك!")
                        break
            except Exception as e:
                logger.warning(f"محاولة ضغط زر النشر ({attempt + 1}): {e}")
            time.sleep(3)

        page.screenshot(path=str(temp_dir / "tt_step3_post.png"))
        if not published:
            logger.error("❌ لم يصبح زر النشر جاهزاً في تيك توك (توقف الرفع قبل الإرسال).")
            return None

        # التحقق من ظهور نافذة تأكيد إضافية مثل (نشر الآن / Post now / Continue to post)
        time.sleep(3)
        for confirm_txt in ["نشر الآن", "Post now", "متابعة النشر", "Continue to post", "نشر", "Post"]:
            try:
                modal_btn = target_frame.locator(f'div[role="dialog"] button:has-text("{confirm_txt}"), div[role="modal"] button:has-text("{confirm_txt}")')
                if modal_btn.count() > 0 and modal_btn.first.is_visible():
                    modal_btn.first.click(timeout=3000)
                    logger.info(f"تم تأكيد النشر عبر النافذة المنبثقة: {confirm_txt}")
                    break
            except Exception:
                pass

        logger.info("⏳ جاري انتظار إتمام النشر على خوادم تيك توك (25 ثانية)...")
        time.sleep(25)

        # محاولة تحويل الخصوصية من Private / أنا فقط إلى Everyone / الجميع في جدول المحتوى إن أمكن
        try:
            priv_btn = target_frame.locator(
                'button:has-text("Private"), div[role="button"]:has-text("Private"), '
                'button:has-text("أنا فقط"), div[role="button"]:has-text("أنا فقط")'
            ).first
            if priv_btn.count() > 0 and priv_btn.is_visible():
                priv_btn.click(timeout=3000)
                time.sleep(1.5)
                everyone_opt = target_frame.locator(
                    'div[role="option"]:has-text("Public"), '
                    'div[role="option"]:has-text("Everyone"), '
                    'div[role="option"]:has-text("الجميع"), '
                    'li:has-text("Public"), '
                    'li:has-text("الجميع"), '
                    'span:text-is("Public"), '
                    'span:text-is("Everyone"), '
                    'span:text-is("الجميع")'
                ).first
                if everyone_opt.count() > 0 and everyone_opt.is_visible():
                    everyone_opt.click(timeout=3000)
                    time.sleep(2)
        except Exception:
            pass

        page.screenshot(path=str(temp_dir / "tt_step4_done.png"))
        logger.info("🎉 اكتملت عملية النشر على تيك توك بنجاح!")
        return "https://www.tiktok.com/"

    def setup_login(self, video_to_upload: Path = None):
        """فتح المتصفح لتسجيل الدخول إلى تيك توك لمرة واحدة ثم رفع أول فيديو مباشرة"""
        from playwright.sync_api import sync_playwright

        logger.info("🎵 فتح نافذة إعداد ربط حساب تيك توك...")

        banner_js = """
        function updateAgyTikTokBar() {
            if (window.__AGY_TT_UPLOADING__) {
                const b = document.getElementById('agy-tt-helper');
                if (b) {
                    b.style.background = '#0d6efd';
                    b.innerHTML = '<span>🚀 جاري رفع فيديو الذهب تلقائياً إلى حسابك في تيك توك... لا تغلق النافذة!</span>';
                }
                return;
            }
            let bar = document.getElementById('agy-tt-helper');
            if (!bar) {
                bar = document.createElement('div');
                bar.id = 'agy-tt-helper';
                bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:999999;background:linear-gradient(90deg,#111,#ff0050);color:#fff;padding:14px 20px;font-family:Tahoma,sans-serif;font-size:16px;font-weight:bold;text-align:center;box-shadow:0 -4px 12px rgba(0,0,0,0.4);direction:rtl;display:flex;justify-content:center;align-items:center;gap:20px;';
                document.body.appendChild(bar);
            }
            const isLoginPage = location.href.toLowerCase().includes('login') || !!document.querySelector('#loginContainer, [data-e2e="login-modal"]');
            if (isLoginPage) {
                bar.style.background = 'linear-gradient(90deg,#842029,#ff0050)';
                bar.innerHTML = '<span>🎵 الخطوة ١ من ٢: سجّل الدخول إلى حسابك في تيك توك (عبر رمز QR بالهاتف أو البريد/جوجل) أولاً!</span>';
            } else if (!window.__AGY_TT_SETUP_DONE__) {
                bar.style.background = 'linear-gradient(90deg,#0f5132,#198754)';
                if (!document.getElementById('agy-tt-done-btn')) {
                    bar.innerHTML = '<span>🎉 تم تسجيل الدخول لتيك توك! اضغط الزر الأصفر لبدء رفع أول فيديو تلقائياً:</span>' +
                                    '<button id="agy-tt-done-btn" style="background:#ffc107;color:#000;border:none;padding:8px 18px;border-radius:8px;font-family:Tahoma,sans-serif;font-size:15px;font-weight:bold;cursor:pointer;">✅ أنا داخل حسابي في تيك توك - ابدأ رفع الفيديو الآن!</button>';
                    document.getElementById('agy-tt-done-btn').addEventListener('click', () => {
                        window.__AGY_TT_SETUP_DONE__ = true;
                        window.__AGY_TT_UPLOADING__ = true;
                        bar.style.background = '#0d6efd';
                        bar.innerHTML = '<span>🚀 جاري رفع فيديو الذهب تلقائياً إلى تيك توك... لا تغلق النافذة!</span>';
                    });
                }
            }
        }
        window.addEventListener('DOMContentLoaded', () => {
            updateAgyTikTokBar();
            setInterval(updateAgyTikTokBar, 1000);
        });
        """

        with sync_playwright() as p:
            context = self._launch_browser(p, headless=False)
            context.add_init_script(banner_js)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
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
                            done = pg.evaluate("() => window.__AGY_TT_SETUP_DONE__ === true")
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
                    logger.info("✅ المستخدم أكد الدخول لتيك توك! بدء رفع الفيديو فوراً في نفس النافذة...")
                    self._perform_tiktok_upload_on_page(active_page, video_to_upload)
            except Exception as e:
                logger.error(f"خطأ أثناء إعداد/رفع تيك توك: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass

        logger.info("✅ تم حفظ جلسة تيك توك وإتمام العملية بنجاح!")

    def upload_video(
        self,
        video_path: Path,
        title: str = None,
        description: str = None,
    ) -> str:
        """رفع الفيديو تلقائياً إلى تيك توك عبر المتصفح (وعبر بروكسي الهاتف إن وجد)"""
        if not video_path.exists():
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {video_path}")

        require_proxy = os.environ.get("TIKTOK_REQUIRE_PROXY", "").strip().lower() in ("1", "true", "yes")
        if require_proxy and not self.proxy_server:
            logger.warning("⚠️ تم طلب البروكسي الإلزامي لكن لم يُضبط عنوان البروكسي — تم تخطي تيك توك بأمان.")
            return None

        if self.proxy_server:
            proxy_info = self.verify_proxy_connection(timeout=12)
            if not proxy_info:
                logger.warning("⚠️ تعذر الاتصال ببروكسي الهاتف حالياً — تم تأجيل رفع تيك توك لتجنب الرفع بـ IP السحابة الأمريكي.")
                return None

        has_profile = self.profile_dir.exists() and any(self.profile_dir.iterdir())
        has_cloud_state = (self.project_dir / "cloud_auth_state.json").exists()
        if not has_profile and not has_cloud_state:
            logger.warning("⚠️ لم يتم تسجيل الدخول بعد.")
            return None

        from playwright.sync_api import sync_playwright

        for session_try in range(1, 3):
            self._post_clicked = False
            try:
                with sync_playwright() as p:
                    context = self._launch_browser(p, headless=False)
                    try:
                        page = context.pages[0] if context.pages else context.new_page()
                        res = self._perform_tiktok_upload_on_page(page, video_path, description=description)
                        if res or self._post_clicked:
                            return res
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"⚠️ محاولة جلسة تيك توك ({session_try}/2) تعثرت: {e}")
                if self._post_clicked or session_try >= 2:
                    raise
            if session_try < 2:
                logger.info("⏳ إعادة المحاولة تلقائياً بعد 10 ثوانٍ لإراحة اتصال بروكسي الهاتف...")
                time.sleep(10)
        return None


if __name__ == "__main__":
    log_file = Path(__file__).parent.resolve() / "tiktok_upload.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    project_dir = Path(__file__).parent.resolve()
    tt = TikTokUploader(project_dir)

    output_dir = project_dir / "output"
    videos = list(output_dir.glob("gold_price_*.mp4"))
    latest_video = sorted(videos)[-1] if videos else None

    if "--setup" in sys.argv:
        tt.setup_login(video_to_upload=latest_video)
    else:
        if latest_video:
            tt.upload_video(latest_video)
        else:
            print("لا يوجد فيديو في مجلد output/")
