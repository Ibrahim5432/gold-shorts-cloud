#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة إنشاء فيديوهات أسعار الذهب اليومية (Shorts) - النسخة المعتمدة الشاملة
Gold Price Daily Shorts Generator with Auto-Publishing (YouTube & Facebook)

المواصفات:
1. أعلى الفيديو:
   - "أسعار الذهب في تركيا"
   - تحتها: تاريخ اليوم (مثال: 2026/10/24)
2. محتوى الجدول/البطاقات (حرفياً):
   - عيار 24  وبجانبه السعر (بالليرة ₺)
   - عيار 22  وبجانبه السعر (بالليرة ₺)
   - عيار 21  وبجانبه السعر (بالليرة ₺)
   - عيار 18  وبجانبه السعر (بالليرة ₺)
   - سعر اونصة الذهب وبجانبه السعر بالدولار ($) المعتمد عالمياً
3. اختيار الصوت المفضل من بين 4 مسارات كيبورد متنوعة أو تسجيلك الخاص
4. خط عربي معتمد نقي 100% يظهر حروف الراء والألف بوضوح تام
5. النشر التلقائي المباشر على YouTube Shorts و Facebook
"""

import os
import sys
import re
import json
import random
import math
import logging
import subprocess
import wave
from datetime import datetime, date
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yaml
import requests
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

import arabic_reshaper
from bidi.algorithm import get_display

# استيراد وحدات النشر التلقائي
from youtube_uploader import YouTubeUploader
from facebook_uploader import FacebookUploader
from tiktok_uploader import TikTokUploader

# ============================================
# إعداد المسارات
# ============================================
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
LOG_PATH = SCRIPT_DIR / "gold_shorts.log"
FONTS_DIR = SCRIPT_DIR / "fonts"
CUSTOM_AUDIO_DIR = SCRIPT_DIR / "custom_audio"
TEMP_DIR = SCRIPT_DIR / "temp"
OUTPUT_DIR = SCRIPT_DIR / "output"

TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
FONTS_DIR.mkdir(exist_ok=True)
CUSTOM_AUDIO_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("GoldShortsFixed")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ar(text: str) -> str:
    """معالجة النص العربي لضمان اكتمال الحروف (بما فيها الراء والألف) والأرقام الغربية 1234"""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


# ============================================
# جلب الأسعار المباشرة من turkeygoldprice.com
# ============================================

class GoldPriceFetcher:
    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ar,en;q=0.9",
        })

    def fetch_turkey_prices(self) -> dict:
        url = self.config.get("data_sources", {}).get("turkey_gold_url", "https://turkeygoldprice.com/")
        logger.info(f"جلب الأسعار الحية من: {url}")
        prices = {}

        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml")

            # 1. البحث عن سعر الأونصة بالدولار من العنوان الرئيسي
            page_text = soup.get_text()
            m_ounce = re.search(r'أونصة الذهب اليوم\s*([\d,]+(?:\.\d+)?)\s*دولار', page_text)
            if m_ounce:
                val = self._parse_price(m_ounce.group(1))
                if val:
                    prices["ounce_usd"] = val

            # 2. البحث في جداول divTableRow
            rows = soup.find_all("div", class_="divTableRow")
            for row in rows:
                cells = row.find_all("div", class_="divTableCell")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    price_try_text = cells[1].get_text(strip=True)

                    for karat in ["24", "22", "21", "18", "14"]:
                        if f"عيار {karat}" in label or f"عيار{karat}" in label:
                            val = self._parse_price(price_try_text)
                            if val and f"{karat}k" not in prices:
                                prices[f"{karat}k"] = val

                    if ("أونصة" in label or "اونصة" in label):
                        val_try = self._parse_price(price_try_text)
                        if val_try and "ounce_try" not in prices:
                            prices["ounce_try"] = val_try
                        if len(cells) >= 3:
                            val_usd = self._parse_price(cells[2].get_text(strip=True))
                            if val_usd and "ounce_usd" not in prices:
                                prices["ounce_usd"] = val_usd

            logger.info(f"تم جلب الأسعار بنجاح: {prices}")
        except Exception as e:
            logger.error(f"خطأ في جلب الأسعار الحية: {e}")

        # قيم احتياطية
        defaults = {
            "24k": 6398.29,
            "22k": 5865.10,
            "21k": 5598.50,
            "18k": 4798.72,
            "ounce_try": 199008.51,
            "ounce_usd": 3995.85,
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
        cleaned = re.sub(r'[^\d.,]', '', text).replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None


# ============================================
# إدارة الصوت
# ============================================

class AudioManager:
    def __init__(self, custom_dir: Path, config: dict):
        self.custom_dir = custom_dir
        self.config = config

    def get_audio_path(self, duration_sec: float, temp_dir: Path) -> Path:
        preferred_track_name = self.config.get("audio", {}).get("selected_track", "Option_1_Deep_Mechanical_Thock.wav")
        preferred_path = self.custom_dir / preferred_track_name

        if preferred_path.exists():
            logger.info(f"🎵 استخدام المسار الصوتي المحدد: {preferred_path.name}")
            return preferred_path

        for ext in [".wav", ".mp3", ".m4a", ".aac", ".ogg"]:
            found = list(self.custom_dir.glob(f"*{ext}"))
            if found:
                logger.info(f"🎵 استخدام الصوت الموجود: {found[0].name}")
                return found[0]

        silent_wav = temp_dir / "neutral_audio.wav"
        sr = 44100
        total_samples = int(duration_sec * sr)
        silent_data = np.zeros(total_samples, dtype=np.int16)
        with wave.open(str(silent_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(silent_data.tobytes())

        return silent_wav


# ============================================
# رسم وتصميم الإطارات
# ============================================

class PerfectFrameGenerator:
    def __init__(self, config: dict):
        self.config = config
        self.width = 1080
        self.height = 1920

        self.font_path = Path("C:/Windows/Fonts/tahomabd.ttf")
        if not self.font_path.exists():
            self.font_path = Path("C:/Windows/Fonts/arialbd.ttf")

        logger.info(f"استخدام الخط العربي المثبت: {self.font_path}")
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

        # هالة ذهبية ناعمة برفق في المركز
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
            ar("أسعار الذهب في تركيا"),
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

        # 2. الصفوف الحرفية المطلوبة
        ounce_cur = self.config.get("ounce_currency", "USD")
        if ounce_cur == "USD":
            ounce_price_str = f"$ {prices.get('ounce_usd', 3995.85):,.2f}"
        else:
            ounce_price_str = f"{prices.get('ounce_try', 199008.51):,.2f} ₺"

        rows_data = [
            ("عيار 24", f"{prices.get('24k', 0):,.2f} ₺", (255, 215, 0)),
            ("عيار 22", f"{prices.get('22k', 0):,.2f} ₺", (245, 180, 10)),
            ("عيار 21", f"{prices.get('21k', 0):,.2f} ₺", (250, 195, 20)),
            ("عيار 18", f"{prices.get('18k', 0):,.2f} ₺", (235, 150, 15)),
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


# ============================================
# تجميع الفيديو عبر FFmpeg
# ============================================

class VideoAssembler:
    def __init__(self, fps=30, crf=20):
        self.fps = fps
        self.crf = crf

    def find_ffmpeg(self) -> str:
        local_ffmpeg = SCRIPT_DIR / "ffmpeg.exe"
        if local_ffmpeg.exists():
            return str(local_ffmpeg)
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def assemble_ultra_light(self, frame_gen, prices: dict, total_frames: int, audio_path: Path, output_path: Path) -> Path:
        """
        توليد الفيديو بأقل استهلاك ممكن للمعالج والبطارية (5-Keyframe Eco Engine):
        - يرسم 5 إطارات مفتاحية فقط بدلاً من 450 إطاراً (توفير 99% من استهلاك المعالج والقرص!)
        - يشغل FFmpeg في تمريرة واحدة على نواة واحدة فقط (-threads 1 -preset ultrafast -tune stillimage)
          وبأولوية معالج منخفضة جداً حتى لا يسخن اللابتوب إطلاقاً.
        """
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:
            pass

        ffmpeg_bin = self.find_ffmpeg()
        logger.info(f"⚡ محرك الفيديو فائق الخفة (5-Keyframe Eco Mode): {ffmpeg_bin}")

        eco_dir = TEMP_DIR / f"eco_{output_path.stem}"
        eco_dir.mkdir(parents=True, exist_ok=True)

        # رسم 5 إطارات مفتاحية فقط لظهور البطاقات الخمس (بدلاً من 450 صورة!)
        key_indices = [1, 7, 13, 19, 25]
        step_files = []
        for step_num, f_idx in enumerate(key_indices):
            img = frame_gen.render_frame(prices, f_idx, total_frames)
            step_path = eco_dir / f"step_{step_num}.png"
            img.save(str(step_path), "PNG", compress_level=1)
            step_files.append(step_path)

        concat_file = eco_dir / "concat_list.txt"
        lines = [
            f"file '{step_files[0].as_posix()}'",
            "duration 0.20",
            f"file '{step_files[1].as_posix()}'",
            "duration 0.20",
            f"file '{step_files[2].as_posix()}'",
            "duration 0.20",
            f"file '{step_files[3].as_posix()}'",
            "duration 0.20",
            f"file '{step_files[4].as_posix()}'",
            "duration 14.20",
            f"file '{step_files[4].as_posix()}'",
        ]
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            ffmpeg_bin, "-y", "-nostdin", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-stream_loop", "-1",
            "-i", str(audio_path),
            "-t", "15",
            "-vf", f"fps={self.fps},format=yuv420p",
            "-fps_mode", "cfr",
            "-g", str(self.fps),
            "-c:v", "libx264",
            "-crf", str(self.crf),
            "-preset", "ultrafast",
            "-threads", "1",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]

        creation_flags = 0x00004000 | 0x08000000  # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
        subprocess.run(cmd, check=True, capture_output=True, creationflags=creation_flags)

        for f in eco_dir.glob("*"):
            f.unlink(missing_ok=True)
        eco_dir.rmdir()

        return output_path

    def assemble(self, frames_dir: Path, audio_path: Path, output_path: Path) -> Path:
        ffmpeg_bin = self.find_ffmpeg()
        logger.info(f"محرك الفيديو: {ffmpeg_bin}")

        temp_video = output_path.with_name(f"_temp_{output_path.stem}.mp4")
        frame_pattern = str(frames_dir / "frame_%05d.png")

        cmd_v = [
            ffmpeg_bin, "-y",
            "-framerate", str(self.fps),
            "-i", frame_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(self.crf),
            "-preset", "fast",
            str(temp_video),
        ]
        logger.info("جاري رندرة الإطارات بدقة فائقة...")
        subprocess.run(cmd_v, check=True, capture_output=True)

        cmd_m = [
            ffmpeg_bin, "-y",
            "-i", str(temp_video),
            "-stream_loop", "-1",
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        logger.info("دمج الصوت مع الفيديو...")
        subprocess.run(cmd_m, check=True, capture_output=True)

        temp_video.unlink(missing_ok=True)
        return output_path


# ============================================
# المحرك الرئيسي وإدارة النشر
# ============================================

class FixedGoldShortsEngine:
    def __init__(self):
        self.config = load_config()
        self.duration = float(self.config.get("video", {}).get("duration", 15))
        self.fps = int(self.config.get("video", {}).get("fps", 30))

        self.fetcher = GoldPriceFetcher(self.config)
        self.audio_mgr = AudioManager(CUSTOM_AUDIO_DIR, self.config)
        self.frame_gen = PerfectFrameGenerator(self.config)
        self.assembler = VideoAssembler(fps=self.fps)
        self.yt_uploader = YouTubeUploader(SCRIPT_DIR)

    def publish_video(self, video_path: Path, prices: dict):
        """إدارة النشر التلقائي إلى يوتيوب وفيسبوك"""
        today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))

        # 1. يوتيوب
        yt_cfg = self.config.get("youtube", {})
        if yt_cfg.get("auto_upload", False):
            try:
                title = yt_cfg.get("title_template", "أسعار الذهب اليوم في تركيا {date} ₺ #shorts").format(date=today_str)
                privacy = yt_cfg.get("privacy_status", "public")
                yt_url = self.yt_uploader.upload_video(video_path, title=title, privacy_status=privacy)
                logger.info(f"✅ تم النشر التلقائي على YouTube: {yt_url}")
            except FileNotFoundError as e:
                logger.warning(f"⚠️ تنبيه يوتيوب: {e}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى يوتيوب: {e}")

        # 2. فيسبوك
        fb_cfg = self.config.get("facebook", {})
        if fb_cfg.get("auto_upload", False):
            try:
                fb_uploader = FacebookUploader(SCRIPT_DIR)
                fb_url = fb_uploader.upload_video(video_path)
                if fb_url:
                    logger.info(f"✅ تم النشر التلقائي على Facebook: {fb_url}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى فيسبوك: {e}")

        # 3. تيك توك
        tt_cfg = self.config.get("tiktok", {})
        if tt_cfg.get("auto_upload", False):
            try:
                tt_uploader = TikTokUploader(SCRIPT_DIR)
                tt_url = tt_uploader.upload_video(video_path)
                if tt_url:
                    logger.info(f"✅ تم النشر التلقائي على TikTok: {tt_url}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى تيك توك: {e}")

    def run(self):
        logger.info("🚀 بدء إنتاج فيديو الذهب اليومي (15 ثانية)...")

        # 1. جلب الأسعار
        prices = self.fetcher.fetch_turkey_prices()
        logger.info(f"الأسعار الحية: {prices}")

        # 2. تحضير الصوت
        audio_path = self.audio_mgr.get_audio_path(self.duration, TEMP_DIR)

        # 3. إنتاج الفيديو مباشرة في الذاكرة بدون إجهاد المعالج أو الهارد
        total_frames = int(self.fps * self.duration)
        today_code = date.today().strftime("%Y%m%d")
        output_file = OUTPUT_DIR / f"gold_price_{today_code}.mp4"

        logger.info(f"⚡ جاري إنتاج الفيديو ({total_frames} إطاراً) بوضع توفير الطاقة القصوى (Eco Single-Core)...")
        final_path = self.assembler.assemble_ultra_light(
            self.frame_gen, prices, total_frames, audio_path, output_file
        )

        logger.info(f"🎉 تم إنشاء الفيديو بنجاح: {final_path}")

        # 5. النشر التلقائي
        self.publish_video(final_path, prices)

        return str(final_path)


if __name__ == "__main__":
    engine = FixedGoldShortsEngine()
    engine.run()
