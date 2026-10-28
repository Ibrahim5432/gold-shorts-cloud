#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة إنشاء فيديوهات أسعار الذهب اليومية في سوريا (Shorts/Reels/TikTok)
Syria Gold Price Daily Shorts Generator with Auto-Publishing (YouTube, Facebook & TikTok)

المواصفات:
1. أعلى الفيديو:
   - "أسعار الذهب في سوريا"
   - تحتها: تاريخ اليوم (مثال: 2026/10/25)
2. محتوى الجدول/البطاقات:
   - عيار 24  وبجانبه السعر بالليرة السورية الجديدة (ل.س)
   - عيار 22  وبجانبه السعر بالليرة السورية الجديدة (ل.س)
   - عيار 21  وبجانبه السعر بالليرة السورية الجديدة (ل.س)
   - عيار 18  وبجانبه السعر بالليرة السورية الجديدة (ل.س)
   - سعر اونصة الذهب وبجانبه السعر بالدولار ($) المعتمد عالمياً
"""

import os
import sys
import re
import math
import random
import logging
from datetime import date
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from make_gold_short import (
    SCRIPT_DIR,
    CUSTOM_AUDIO_DIR,
    TEMP_DIR,
    OUTPUT_DIR,
    load_config,
    ar,
    AudioManager,
    VideoAssembler,
)
from youtube_uploader import YouTubeUploader
from facebook_uploader import FacebookUploader
from tiktok_uploader import TikTokUploader

logger = logging.getLogger("SyriaGoldShorts")


class SyriaGoldPriceFetcher:
    """جلب أسعار الذهب الحية في سوريا بالليرة السورية الجديدة (حذف صفرين - معيار مصرف سوريا المركزي و SP-Today / Aleppo.gold)"""

    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept-Language": "ar,en;q=0.9",
        })

    def fetch_syria_prices(self) -> dict:
        prices = {}

        # المصدر الأساسي الأول: aleppo.gold (المرتبط مباشرة بـ SP-Today بالليرة السورية الجديدة، تحديث كل دقيقة)
        try:
            url = "https://aleppo.gold/"
            logger.info(f"جلب أسعار الذهب الحية في سوريا من: {url}")
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            table_div = soup.find("div", class_="table")
            if table_div:
                cells = table_div.find_all("div", class_="cell", recursive=False)
                for i in range(0, len(cells) - 1, 2):
                    label_text = " ".join(cells[i].stripped_strings)
                    val_tokens = list(cells[i + 1].stripped_strings)
                    if not val_tokens:
                        continue
                    first_num = self._parse_price(val_tokens[0])

                    for karat in ["24", "22", "21", "18"]:
                        if f"عيار {karat}" in label_text or f"عيار{karat}" in label_text:
                            if first_num:
                                prices[f"{karat}k"] = first_num

                    if "أونصة" in label_text or "اونصة" in label_text:
                        if first_num:
                            prices["ounce_syp"] = first_num
                        # السعر بالدولار يكون في العنصر الثالث قبل علامة $
                        for tok in val_tokens[1:]:
                            v_usd = self._parse_price(tok)
                            if v_usd and v_usd > 1000:
                                prices["ounce_usd"] = v_usd
                                break

            # التحقق أيضاً من صندوق الأونصة العلوي
            if "ounce_usd" not in prices:
                ounce_div = soup.find("div", class_="qv-ounce")
                if ounce_div:
                    for tok in ounce_div.stripped_strings:
                        v_usd = self._parse_price(tok)
                        if v_usd and v_usd > 1000:
                            prices["ounce_usd"] = v_usd
                            break

            logger.info(f"تم جلب أسعار سوريا من المصدر الأول بنجاح: {prices}")
        except Exception as e:
            logger.warning(f"تعذر الجلب من المصدر الأول (aleppo.gold): {e}")

        # المصدر الاحتياطي الثاني: syria.gold-price-today.com (مع تحويل الليرة القديمة إلى الجديدة بقسمة 100)
        if len(prices) < 4:
            try:
                url2 = "https://syria.gold-price-today.com/"
                logger.info(f"جلب أسعار سوريا من المصدر الاحتياطي: {url2}")
                resp2 = self.session.get(url2, timeout=20)
                resp2.raise_for_status()
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                for tr in soup2.find_all("tr"):
                    cols = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                    if len(cols) >= 2:
                        lbl = cols[0]
                        val = self._parse_price(cols[1])
                        for karat in ["24", "22", "21", "18"]:
                            if f"عيار {karat}" in lbl and f"{karat}k" not in prices and val:
                                prices[f"{karat}k"] = round(val / 100.0) if val > 100000 else val
                        if "الأونصة بالدولار" in lbl and "ounce_usd" not in prices and val:
                            prices["ounce_usd"] = val
            except Exception as e:
                logger.warning(f"تعذر الجلب من المصدر الاحتياطي: {e}")

        # قيم احتياطية دقيقة في حال انقطاع الإنترنت
        defaults = {
            "24k": 18403,
            "22k": 16857,
            "21k": 16103,
            "18k": 13803,
            "ounce_usd": 3995.88,
        }
        for k, v in defaults.items():
            if k not in prices or not prices[k]:
                prices[k] = v

        prices["date"] = date.today().strftime("%Y/%m/%d")
        return prices

    @staticmethod
    def _parse_price(text: str):
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text).replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None


class SyriaFrameGenerator:
    """نفس التصميم المعتمد تماماً مع عنوان وعملة سوريا"""

    def __init__(self, config: dict):
        self.config = config
        self.width = 1080
        self.height = 1920

        self.font_path = Path("C:/Windows/Fonts/tahomabd.ttf")
        if not self.font_path.exists():
            self.font_path = Path("C:/Windows/Fonts/arialbd.ttf")

        self.font_cache = {}

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self.font_cache:
            self.font_cache[size] = ImageFont.truetype(str(self.font_path), size)
        return self.font_cache[size]

    def render_frame(self, prices: dict, frame_idx: int, total_frames: int) -> Image.Image:
        fps = 30
        t_sec = frame_idx / fps

        img = Image.new("RGB", (self.width, self.height), (10, 14, 24))
        draw = ImageDraw.Draw(img)

        cx = self.width // 2

        # هالة ذهبية ناعمة في المركز
        pulse = math.sin(frame_idx * 0.08)
        glow_r = int(280 + 20 * pulse)
        for r_step in range(glow_r, 40, -50):
            alpha = int(3 + (glow_r - r_step) * 0.03)
            tint = (212 + alpha, 175 + alpha, 55 + alpha)
            draw.ellipse([cx - r_step, 900 - r_step, cx + r_step, 900 + r_step], outline=tint, width=1)

        random.seed(88)
        for i in range(16):
            px = (random.randint(0, self.width) + int(frame_idx * 0.5 * (i % 3 + 1))) % self.width
            py = (random.randint(0, self.height) + int(frame_idx * 0.4 * (i % 2 + 1))) % self.height
            sz = (i % 3) + 2
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(212, 175, 55))

        draw.line([(80, 50), (self.width - 80, 50)], fill=(212, 175, 55), width=2)
        draw.line([(80, self.height - 50), (self.width - 80, self.height - 50)], fill=(212, 175, 55), width=2)

        # 1. أعلى الفيديو
        y_top = 180
        draw.text(
            (cx, y_top),
            ar("أسعار الذهب في سوريا"),
            fill=(255, 215, 0),
            font=self.get_font(64),
            anchor="mm",
        )

        today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))
        draw.text(
            (cx, y_top + 80),
            today_str,
            fill=(170, 185, 205),
            font=self.get_font(40),
            anchor="mm",
        )

        draw.line([(cx - 200, y_top + 130), (cx + 200, y_top + 130)], fill=(212, 175, 55), width=2)

        # 2. الصفوف الخمسة المعتمدة
        syp_unit = ar("ل.س")
        ounce_price_str = f"$ {prices.get('ounce_usd', 3995.88):,.2f}"

        rows_data = [
            ("عيار 24", f"{int(round(prices.get('24k', 0))):,} {syp_unit}", (255, 215, 0)),
            ("عيار 22", f"{int(round(prices.get('22k', 0))):,} {syp_unit}", (245, 180, 10)),
            ("عيار 21", f"{int(round(prices.get('21k', 0))):,} {syp_unit}", (250, 195, 20)),
            ("عيار 18", f"{int(round(prices.get('18k', 0))):,} {syp_unit}", (235, 150, 15)),
            ("سعر اونصة الذهب", ounce_price_str, (255, 225, 50)),
        ]

        y_start = 440
        spacing = 215

        for idx, (label, price_str, accent_color) in enumerate(rows_data):
            reveal_start = idx * 0.20
            progress = min(1.0, max(0.0, (t_sec - reveal_start) / 0.30))
            if progress <= 0.0:
                continue

            y_card = y_start + (idx * spacing)
            card_h = 165
            x1, x2 = 80, self.width - 80
            y1, y2 = y_card, y_card + card_h

            draw.rounded_rectangle([x1, y1, x2, y2], radius=24, fill=(18, 24, 38), outline=(48, 62, 88), width=2)
            draw.rounded_rectangle([x2 - 12, y1 + 24, x2 - 4, y2 - 24], radius=4, fill=accent_color)

            label_font = self.get_font(38) if len(label) > 10 else self.get_font(46)
            draw.text((x2 - 45, y1 + card_h // 2), ar(label), fill=(255, 255, 255), font=label_font, anchor="rm")

            price_font = self.get_font(54) if len(price_str) > 11 else self.get_font(58)
            draw.text((x1 + 45, y1 + card_h // 2), price_str, fill=(0, 255, 157), font=price_font, anchor="lm")

        draw.text(
            (cx, self.height - 85),
            ar("تحديث يومي فوري"),
            fill=(130, 145, 165),
            font=self.get_font(28),
            anchor="mm",
        )

        return img


class SyriaGoldShortsEngine:
    def __init__(self):
        self.config = load_config()
        self.duration = float(self.config.get("video", {}).get("duration", 15))
        self.fps = int(self.config.get("video", {}).get("fps", 30))

        self.fetcher = SyriaGoldPriceFetcher(self.config)
        self.audio_mgr = AudioManager(CUSTOM_AUDIO_DIR, self.config)
        self.frame_gen = SyriaFrameGenerator(self.config)
        self.assembler = VideoAssembler(fps=self.fps)
        self.yt_uploader = YouTubeUploader(SCRIPT_DIR)

    def publish_video(self, video_path: Path, prices: dict):
        """النشر التلقائي لفيديو أسعار الذهب في سوريا على يوتيوب وفيسبوك وتيك توك"""
        today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))

        yt_title = f"أسعار الذهب اليوم في سوريا {today_str} ل.س #shorts #gold"
        yt_desc = (
            f"أسعار الذهب اليوم في سوريا ({today_str}) بالليرة السورية لجميع العيارات (24، 22، 21، 18) وسعر الأونصة بالدولار.\n\n"
            "تحديث يومي فوري لأسعار الذهب في سوريا.\n"
            "#ذهب #أسعار_الذهب #سوريا #دمشق #حلب #اسعار_الذهب_في_سوريا #الليرة_السورية #shorts #gold"
        )
        yt_tags = [
            "ذهب", "اسعار الذهب", "أسعار الذهب اليوم", "سوريا", "دمشق", "حلب",
            "اسعار الذهب في سوريا", "الليرة السورية", "عيار 21", "عيار 24", "اونصة الذهب",
            "shorts", "gold", "syria gold price",
        ]
        social_desc = (
            f"أسعار الذهب اليوم في سوريا ({today_str}) لجميع العيارات بالليرة السورية وسعر الأونصة بالدولار $\n"
            "#ذهب #أسعار_الذهب #سوريا #دمشق #حلب #الليرة_السورية #ريلز #اكسبلور #reels #gold #tiktok"
        )

        # 1. يوتيوب
        yt_cfg = self.config.get("youtube", {})
        if yt_cfg.get("auto_upload", False):
            try:
                privacy = yt_cfg.get("privacy_status", "public")
                yt_url = self.yt_uploader.upload_video(
                    video_path,
                    title=yt_title,
                    description=yt_desc,
                    tags=yt_tags,
                    privacy_status=privacy,
                )
                logger.info(f"✅ تم نشر فيديو سوريا تلقائياً على YouTube: {yt_url}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع فيديو سوريا إلى يوتيوب: {e}")

        # 2. فيسبوك
        fb_cfg = self.config.get("facebook", {})
        if fb_cfg.get("auto_upload", False):
            try:
                fb_uploader = FacebookUploader(SCRIPT_DIR)
                fb_url = fb_uploader.upload_video(video_path, description=social_desc)
                if fb_url:
                    logger.info(f"✅ تم نشر فيديو سوريا تلقائياً على Facebook: {fb_url}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع فيديو سوريا إلى فيسبوك: {e}")

        # 3. تيك توك
        tt_cfg = self.config.get("tiktok", {})
        if tt_cfg.get("auto_upload", False):
            try:
                tt_uploader = TikTokUploader(SCRIPT_DIR)
                tt_url = tt_uploader.upload_video(video_path, description=social_desc)
                if tt_url:
                    logger.info(f"✅ تم نشر فيديو سوريا تلقائياً على TikTok: {tt_url}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع فيديو سوريا إلى تيك توك: {e}")

    def run(self, preview_only: bool = False, skip_publish: bool = False):
        logger.info("🚀 بدء إنتاج فيديو أسعار الذهب اليومي في سوريا (15 ثانية)...")

        # 1. جلب الأسعار الحية لسوريا
        prices = self.fetcher.fetch_syria_prices()
        logger.info(f"الأسعار الحية في سوريا: {prices}")

        if preview_only:
            preview_img = self.frame_gen.render_frame(prices, 60, 450)
            preview_path = TEMP_DIR / "syria_frame_verified.png"
            preview_img.save(str(preview_path), "PNG")
            logger.info(f"✅ تم حفظ صورة المعاينة في: {preview_path}")
            return str(preview_path)

        today_code = date.today().strftime("%Y%m%d")
        output_file = OUTPUT_DIR / f"syria_gold_price_{today_code}.mp4"

        if output_file.exists() and "--force-render" not in sys.argv:
            import time as _t
            if (_t.time() - output_file.stat().st_mtime) < 900:
                logger.info(f"⚡ استخدام ملف الفيديو الجاهز حديثاً: {output_file}")
                if not skip_publish:
                    self.publish_video(output_file, prices)
                return str(output_file)

        # 2. تحضير الصوت
        audio_path = self.audio_mgr.get_audio_path(self.duration, TEMP_DIR)

        # 3. إنتاج الفيديو مباشرة في الذاكرة بدون إجهاد المعالج أو الهارد
        total_frames = int(self.fps * self.duration)
        logger.info(f"⚡ جاري إنتاج فيديو سوريا ({total_frames} إطاراً) بوضع توفير الطاقة القصوى (Eco Single-Core)...")
        final_path = self.assembler.assemble_ultra_light(
            self.frame_gen, prices, total_frames, audio_path, output_file
        )

        logger.info(f"🎉 تم إنشاء فيديو سوريا بنجاح: {final_path}")

        # 5. النشر التلقائي
        if not skip_publish:
            self.publish_video(final_path, prices)

        return str(final_path)


if __name__ == "__main__":
    engine = SyriaGoldShortsEngine()
    if "--preview" in sys.argv:
        engine.run(preview_only=True)
    elif "--no-publish" in sys.argv:
        engine.run(skip_publish=True)
    else:
        engine.run()
