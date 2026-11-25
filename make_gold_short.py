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
from buffer_uploader import BufferTikTokUploader
from telegram_publisher import TelegramPublisher

# ============================================
# إعداد المسارات
# ============================================
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
LOG_PATH = SCRIPT_DIR / "gold_shorts.log"
FONTS_DIR = SCRIPT_DIR / "fonts"
CUSTOM_AUDIO_DIR = SCRIPT_DIR / "custom_audio"
TIKTOK_BG_DIR = SCRIPT_DIR / "tiktok_backgrounds"
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
# جلب الأسعار المباشرة لسوق تركيا (سعر المبيع الفعلي)
# ============================================

class GoldPriceFetcher:
    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9,ar;q=0.8,en;q=0.7",
        })

    @staticmethod
    def _make_soup(html_text: str) -> BeautifulSoup:
        try:
            return BeautifulSoup(html_text, "lxml")
        except Exception:
            return BeautifulSoup(html_text, "html.parser")

    def _fetch_kapalicarsi_canlidoviz(self, url: str) -> dict:
        """جلب سعر المبيع (Satış) المباشر من جدول السوق التركي في canlidoviz"""
        prices = {}
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = self._make_soup(resp.text)

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            headers = [c.get_text(" ", strip=True).upper() for c in rows[0].find_all(["th", "td"])]
            header_joined = " ".join(headers)
            has_satis = ("SATIŞ" in header_joined) or ("SATIS" in header_joined)

            # تحديد عمود الإغلاق السابق (KAPANIŞ) إن وجد للاستعانة به عند تغيير المصدر لأول يوم
            kapanis_idx = None
            for i, h in enumerate(headers):
                if "KAPANIŞ" in h or "KAPANIS" in h:
                    kapanis_idx = i
                    break

            for row in rows[1:]:
                cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                if len(cols) < 2:
                    continue
                name = cols[0].strip().lower()

                if has_satis and len(cols) >= 3 and "%" not in cols[2]:
                    satis_val = self._parse_tr_price(cols[2])
                    if name == "gram altın" and satis_val and 1000 < satis_val < 50000 and "24k" not in prices:
                        prices["24k"] = round(satis_val, 2)
                        if kapanis_idx is not None and kapanis_idx < len(cols):
                            kap_val = self._parse_tr_price(cols[kapanis_idx])
                            if kap_val and 1000 < kap_val < 50000:
                                prices["prev_21k"] = round(kap_val * 21.0 / 24.0, 2)
                    elif name == "22 ayar altın" and satis_val and 1000 < satis_val < 50000 and "22k" not in prices:
                        prices["22k"] = round(satis_val, 2)

                if name == "ons altın" and "%" not in cols[1]:
                    ons_val = self._parse_tr_price(cols[1])
                    if ons_val and 1500 < ons_val < 15000 and "ounce_usd" not in prices:
                        prices["ounce_usd"] = round(ons_val, 2)

        if "24k" not in prices:
            raise ValueError("لم يتم العثور على سعر مبيع Gram Altın في جدول canlidoviz")

        p24 = prices["24k"]
        if "22k" not in prices or not (0.85 * p24 < prices["22k"] < p24):
            prices["22k"] = round(p24 * 22.0 / 24.0, 2)
        prices["21k"] = round(p24 * 21.0 / 24.0, 2)
        prices["18k"] = round(p24 * 18.0 / 24.0, 2)
        prices["source"] = "kapalicarsi"
        return prices

    def _fetch_kapalicarsi_doviz(self) -> dict:
        """مصدر احتياطي لسعر المبيع (Satış) من altin.doviz.com (Kapalıçarşı / Harem)"""
        prices = {}

        # 1. عيار 24 (Satış) من صفحة gram-altin
        r_gram = self.session.get("https://altin.doviz.com/gram-altin", timeout=20)
        r_gram.raise_for_status()
        sp_gram = self._make_soup(r_gram.text)
        harem_24 = None
        for tr in sp_gram.select("table tr"):
            cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cols) >= 3:
                bank = cols[0].strip().lower()
                val = self._parse_tr_price(cols[2])
                if val and 1000 < val < 50000:
                    if "kapalıçarşı" in bank or "kapalicarsi" in bank:
                        prices["24k"] = round(val, 2)
                        break
                    if "harem" in bank and not harem_24:
                        harem_24 = round(val, 2)
        if "24k" not in prices and harem_24:
            prices["24k"] = harem_24

        # 2. عيار 22 (Satış Harem) من صفحة 22-ayar-bilezik
        try:
            r_22 = self.session.get("https://altin.doviz.com/22-ayar-bilezik", timeout=15)
            r_22.raise_for_status()
            sp_22 = self._make_soup(r_22.text)
            for tr in sp_22.select("table tr"):
                cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cols) >= 3 and "harem" in cols[0].strip().lower():
                    val22 = self._parse_tr_price(cols[2])
                    if val22 and 1000 < val22 < 50000:
                        prices["22k"] = round(val22, 2)
                        break
        except Exception:
            pass

        # 3. الأونصة بالدولار من الصفحة الرئيسية لـ altin.doviz.com
        try:
            r_main = self.session.get("https://altin.doviz.com/", timeout=15)
            r_main.raise_for_status()
            sp_main = self._make_soup(r_main.text)
            for tr in sp_main.select("table tr"):
                cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cols) >= 3 and "ons altın" in cols[0].strip().lower():
                    val_ons = self._parse_tr_price(cols[2])
                    if val_ons and 1500 < val_ons < 15000:
                        prices["ounce_usd"] = round(val_ons, 2)
                        break
        except Exception:
            pass

        if "24k" not in prices:
            raise ValueError("لم يتم العثور على سعر مبيع Kapalıçarşı في altin.doviz.com")

        p24 = prices["24k"]
        if "22k" not in prices or not (0.85 * p24 < prices["22k"] < p24):
            prices["22k"] = round(p24 * 22.0 / 24.0, 2)
        prices["21k"] = round(p24 * 21.0 / 24.0, 2)
        prices["18k"] = round(p24 * 18.0 / 24.0, 2)
        prices["source"] = "kapalicarsi"
        return prices

    def _fetch_turkeygoldprice_spot(self, url: str) -> dict:
        """مصدر احتياطي ثالث في حال تعطل المصادر التركية المباشرة"""
        prices = {}
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = self._make_soup(resp.text)

        page_text = soup.get_text()
        m_ounce = re.search(r'أونصة الذهب اليوم\s*([\d,]+(?:\.\d+)?)\s*دولار', page_text)
        if m_ounce:
            val = self._parse_price(m_ounce.group(1))
            if val and 1500 < val < 15000:
                prices["ounce_usd"] = val

        for row in soup.find_all("div", class_="divTableRow"):
            cells = row.find_all("div", class_="divTableCell")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                price_try_text = cells[1].get_text(strip=True)
                for karat in ["24", "22", "21", "18", "14"]:
                    if f"عيار {karat}" in label or f"عيار{karat}" in label:
                        val = self._parse_price(price_try_text)
                        if val and val > 500 and f"{karat}k" not in prices:
                            prices[f"{karat}k"] = val
                if ("أونصة" in label or "اونصة" in label) and "بيع" in label:
                    val_try = self._parse_price(price_try_text)
                    if val_try and val_try > 10000 and "ounce_try" not in prices:
                        prices["ounce_try"] = val_try
                    if len(cells) >= 3:
                        val_usd = self._parse_price(cells[2].get_text(strip=True))
                        if val_usd and 1500 < val_usd < 15000 and "ounce_usd" not in prices:
                            prices["ounce_usd"] = val_usd

        if "24k" not in prices:
            raise ValueError("تعذر استخراج أسعار تركيا من turkeygoldprice")
        prices["source"] = "spot"
        return prices

    def fetch_turkey_prices(self) -> dict:
        ds_cfg = self.config.get("data_sources", {})
        primary_url = ds_cfg.get("turkey_gold_url", "https://canlidoviz.com/altin-fiyatlari/kapali-carsi")
        fallback_spot_url = ds_cfg.get("turkey_fallback_url", "https://turkeygoldprice.com/")
        prices = {}

        # 1. المصدر الرئيسي: سعر المبيع الفعلي للسوق التركي (canlidoviz Kapalıçarşı)
        try:
            logger.info(f"جلب أسعار الذهب الحية في تركيا (سعر المبيع) من: {primary_url}")
            if "canlidoviz" in primary_url:
                prices = self._fetch_kapalicarsi_canlidoviz(primary_url)
            else:
                prices = self._fetch_turkeygoldprice_spot(primary_url)
            logger.info(f"✅ تم جلب الأسعار بنجاح من المصدر الأول: {prices}")
        except Exception as e:
            logger.warning(f"⚠️ تعذر الجلب من المصدر الأول ({primary_url}): {e}")

        # 2. المصدر الاحتياطي الأول: altin.doviz.com (سعر المبيع Kapalıçarşı / Harem)
        if not prices.get("24k") or not prices.get("ounce_usd"):
            try:
                logger.info("جلب أسعار المبيع الاحتياطية من: altin.doviz.com")
                dov_prices = self._fetch_kapalicarsi_doviz()
                for k, v in dov_prices.items():
                    if k not in prices or not prices[k]:
                        prices[k] = v
                logger.info(f"✅ تم استكمال الأسعار من altin.doviz.com: {prices}")
            except Exception as e:
                logger.warning(f"⚠️ تعذر الجلب من altin.doviz.com: {e}")

        # 3. المصدر الاحتياطي الثاني: turkeygoldprice.com
        if not prices.get("24k") or not prices.get("ounce_usd"):
            try:
                logger.info(f"جلب الأسعار الاحتياطية من: {fallback_spot_url}")
                sp_prices = self._fetch_turkeygoldprice_spot(fallback_spot_url)
                for k, v in sp_prices.items():
                    if k not in prices or not prices[k]:
                        prices[k] = v
            except Exception as e:
                logger.error(f"خطأ في جلب الأسعار الاحتياطية: {e}")

        # قيم احتياطية أخيرة في حال انقطاع الإنترنت
        defaults = {
            "24k": 6023.11,
            "22k": 5619.99,
            "21k": 5270.22,
            "18k": 4517.33,
            "ounce_usd": 3450.00,
        }
        for k, v in defaults.items():
            if k not in prices or not prices[k]:
                prices[k] = v

        if "ounce_try" not in prices or not prices["ounce_try"]:
            prices["ounce_try"] = round(prices["24k"] * 31.1034768, 2)

        prices["date"] = date.today().strftime("%Y/%m/%d")
        return prices

    @staticmethod
    def _parse_tr_price(text: str):
        """تحليل الأرقام بالصيغة التركية مثل 6.023,11 أو $3.450,71 إلى float"""
        if not text:
            return None
        cleaned = re.sub(r'[^\d.,]', '', text).strip(".,")
        if not cleaned:
            return None
        if "," in cleaned:
            # الصيغة التركية: النقطة للآلاف والفاصلة للكسور العشرية
            normalized = cleaned.replace(".", "").replace(",", ".")
        elif cleaned.count(".") > 1 or re.search(r'\.\d{3}$', cleaned):
            normalized = cleaned.replace(".", "")
        else:
            normalized = cleaned
        try:
            return float(normalized)
        except ValueError:
            return None

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
        preferred_track_name = self.config.get("audio", {}).get("selected_track", "Option_Nasheed_With_Mizhar_Duff.mp3")
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

    def get_tiktok_audio_path(self) -> Path | None:
        tt_track_name = self.config.get("audio", {}).get("tiktok_track")
        if not tt_track_name:
            return None
        tt_path = self.custom_dir / tt_track_name
        if tt_path.exists():
            return tt_path
        return None


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
        rows_data = self.get_rows_data(prices)

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

    def get_rows_data(self, prices: dict) -> list:
        ounce_cur = self.config.get("ounce_currency", "USD")
        if ounce_cur == "USD":
            ounce_price_str = f"$ {prices.get('ounce_usd', 3995.85):,.2f}"
        else:
            ounce_price_str = f"{prices.get('ounce_try', 199008.51):,.2f} ₺"

        return [
            ("عيار 24", f"{prices.get('24k', 0):,.2f} ₺", (255, 215, 0)),
            ("عيار 22", f"{prices.get('22k', 0):,.2f} ₺", (245, 180, 10)),
            ("عيار 21", f"{prices.get('21k', 0):,.2f} ₺", (250, 195, 20)),
            ("عيار 18", f"{prices.get('18k', 0):,.2f} ₺", (235, 150, 15)),
            ("سعر اونصة الذهب", ounce_price_str, (255, 225, 50)),
        ]

    @property
    def tiktok_title(self) -> str:
        return "أسعار الذهب في تركيا"


def load_previous_day_prices(
    country_code: str,
    today_key: str = None,
    expected_source: str = None,
) -> dict | None:
    """قراءة أسعار آخر يوم سابق من published_history.json (بنفس المصدر) لحساب الفرق اليومي (▲ / ▼)"""
    hist_file = SCRIPT_DIR / "published_history.json"
    if not hist_file.exists():
        return None
    try:
        hist = json.loads(hist_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    today_k = today_key or date.today().strftime("%Y-%m-%d")
    price_key = f"{country_code}_prices"
    for d_key in sorted(hist.keys(), reverse=True):
        if d_key < today_k:
            entry = hist.get(d_key) or {}
            p = entry.get(price_key)
            if isinstance(p, dict) and p.get("21k"):
                if expected_source and p.get("source") and p.get("source") != expected_source:
                    continue
                if expected_source == "kapalicarsi" and not p.get("source"):
                    # السجلات القديمة غير الموسومة كانت من المصدر العالمي (Spot) — نتجنب المقارنة بين مصدرين مختلفين
                    continue
                return p
    return None


def compute_daily_change(country_code: str, prices: dict, prev_prices: dict | None) -> dict | None:
    """حساب اتجاه ومقدار التغيّر اليومي لعيار 21 مقارنةً بسعر آخر يوم سابق"""
    if not prev_prices:
        return None
    try:
        cur_21 = float(prices.get("21k", 0) or 0)
        prev_21 = float(prev_prices.get("21k", 0) or 0)
    except (TypeError, ValueError):
        return None
    if cur_21 <= 0 or prev_21 <= 0:
        return None

    diff = cur_21 - prev_21
    pct = (diff / prev_21) * 100.0
    flat_threshold = 5.0 if country_code == "syria" else 0.50
    if diff >= flat_threshold:
        direction = "up"
    elif diff <= -flat_threshold:
        direction = "down"
    else:
        direction = "flat"

    if country_code == "syria":
        diff_abs = f"{int(round(abs(diff))):,}"
        sign = "+" if diff >= 0 else "-"
        syp_unit = ar("ل.س")
        diff_display = f"{sign}{diff_abs} {syp_unit} ({sign}{abs(pct):.2f}%)"
    else:
        sign = "+" if diff >= 0 else "-"
        diff_display = f"{sign}{abs(diff):,.2f} ₺ ({sign}{abs(pct):.2f}%)"

    return {
        "direction": direction,
        "diff": diff,
        "pct": pct,
        "diff_display": diff_display,
    }


def render_glass_cards_overlay(
    title_ar: str,
    prices: dict,
    rows_data: list,
    get_font_fn,
    revealed_count: int,
    width: int = 1080,
    height: int = 1920,
    country_code: str = "turkey",
    prev_prices: dict | None = None,
) -> Image.Image:
    """طبقة شفافة (RGBA) ببطاقات زجاجية داكنة في المنطقة الآمنة لتيك توك مع شارة الفرق اليومي وسؤال تفاعلي"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = width // 2

    # 1. بطاقة العنوان + التاريخ + شارة الفرق عن الأمس (▲ / ▼) تحت شريط تيك توك العلوي مباشرةً
    draw.rounded_rectangle([80, 185, width - 80, 442], radius=28, fill=(8, 12, 22, 192), outline=(212, 175, 55, 165), width=2)
    draw.line([(80, 45), (width - 80, 45)], fill=(212, 175, 55, 180), width=2)

    draw.text((cx, 248), ar(title_ar), fill=(255, 215, 0, 255), font=get_font_fn(60), anchor="mm")
    today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))
    draw.text((cx, 314), today_str, fill=(225, 234, 246, 255), font=get_font_fn(36), anchor="mm")

    change_info = compute_daily_change(country_code, prices, prev_prices)
    px1, py1, px2, py2 = 120, 356, width - 120, 420
    pm_y = (py1 + py2) // 2

    if change_info and change_info["direction"] == "up":
        draw.rounded_rectangle([px1, py1, px2, py2], radius=20, fill=(10, 56, 36, 232), outline=(0, 238, 145, 230), width=2)
        # مثلث صعود أخضر نقي (Vector Polygon بدون اعتماد على خطوط الإيموجي)
        tri = [(px2 - 36, pm_y - 12), (px2 - 50, pm_y + 11), (px2 - 22, pm_y + 11)]
        draw.polygon(tri, fill=(0, 255, 157, 255))
        draw.text((px2 - 66, pm_y), ar("ارتفاع عيار 21 عن الأمس"), fill=(195, 255, 225, 255), font=get_font_fn(29), anchor="rm")
        draw.text((px1 + 34, pm_y), change_info["diff_display"], fill=(0, 255, 157, 255), font=get_font_fn(30), anchor="lm")
    elif change_info and change_info["direction"] == "down":
        draw.rounded_rectangle([px1, py1, px2, py2], radius=20, fill=(64, 16, 24, 232), outline=(255, 92, 110, 230), width=2)
        # مثلث هبوط أحمر نقي
        tri = [(px2 - 36, pm_y + 12), (px2 - 50, pm_y - 11), (px2 - 22, pm_y - 11)]
        draw.polygon(tri, fill=(255, 98, 114, 255))
        draw.text((px2 - 66, pm_y), ar("انخفاض عيار 21 عن الأمس"), fill=(255, 210, 215, 255), font=get_font_fn(29), anchor="rm")
        draw.text((px1 + 34, pm_y), change_info["diff_display"], fill=(255, 112, 126, 255), font=get_font_fn(30), anchor="lm")
    elif change_info and change_info["direction"] == "flat":
        draw.rounded_rectangle([px1, py1, px2, py2], radius=20, fill=(38, 32, 16, 225), outline=(245, 200, 66, 215), width=2)
        draw.ellipse([px2 - 44, pm_y - 8, px2 - 28, pm_y + 8], fill=(255, 215, 0, 255))
        draw.text((cx, pm_y), ar("استقرار عيار 21 مقارنةً بسعر الأمس"), fill=(255, 232, 140, 255), font=get_font_fn(30), anchor="mm")
    else:
        draw.rounded_rectangle([px1 + 90, py1, px2 - 90, py2], radius=20, fill=(24, 28, 42, 210), outline=(212, 175, 55, 175), width=2)
        draw.text((cx, pm_y), ar("التحديث اليومي المباشر لأسعار اليوم"), fill=(255, 226, 120, 255), font=get_font_fn(30), anchor="mm")

    # 2. البطاقات الخمس للأسعار مع إبراز بصري خفيف لعيار 21 الأكثر بحثاً
    y_start = 468
    spacing = 186
    card_h = 148
    x1, x2 = 80, width - 80

    for idx, (label, price_str, accent_color) in enumerate(rows_data[:revealed_count]):
        y1 = y_start + (idx * spacing)
        y2 = y1 + card_h
        is_21k = "21" in label

        draw.rounded_rectangle(
            [x1, y1, x2, y2],
            radius=24,
            fill=(14, 19, 32, 212) if is_21k else (10, 14, 24, 196),
            outline=(255, 215, 0, 235) if is_21k else (212, 175, 55, 165),
            width=3 if is_21k else 2,
        )
        draw.rounded_rectangle(
            [x2 - 12, y1 + 20, x2 - 4, y2 - 20],
            radius=4,
            fill=(*accent_color, 255),
        )

        label_font = get_font_fn(38) if len(label) > 10 else get_font_fn(46)
        draw.text(
            (x2 - 45, y1 + card_h // 2),
            ar(label),
            fill=(255, 230, 128, 255) if is_21k else (255, 255, 255, 255),
            font=label_font,
            anchor="rm",
        )

        price_font = get_font_fn(54) if len(price_str) > 11 else get_font_fn(58)
        draw.text((x1 + 45, y1 + card_h // 2), price_str, fill=(0, 255, 157, 255), font=price_font, anchor="lm")

    # 3. شارة تفاعلية سفلية متجددة يومياً (تحفّز التعليقات والحفظ بدون إيموجي مكسور)
    ordinal = date.today().toordinal() + (1 if country_code == "syria" else 0)
    ctas = [
        "هل تتوقع صعود الذهب غداً أم هبوطه؟ اكتب بالتعليقات",
        "هل السعر مناسب للشراء اليوم؟ شاركنا رأيك",
        "احفظ الفيديو للرجوع إليه عند الشراء أو البيع",
        "تابع الحساب ليصلك سعر الذهب يومياً قبل الجميع",
    ]
    cta_text = ctas[ordinal % len(ctas)]
    draw.rounded_rectangle([95, 1412, width - 95, 1492], radius=24, fill=(14, 18, 30, 218), outline=(255, 215, 0, 200), width=2)
    draw.text((cx, 1452), ar(cta_text), fill=(255, 230, 128, 255), font=get_font_fn(30), anchor="mm")

    return img


def build_tiktok_caption(country_code: str, prices: dict, prev_prices: dict | None = None) -> str:
    """إنشاء وصف تشويقي تفاعلي لتيك توك (بدون حرق السعر في الوصف لرفع مدة المشاهدة والتعليقات)"""
    today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))
    ordinal = date.today().toordinal()
    change_info = compute_daily_change(country_code, prices, prev_prices)
    direction = change_info["direction"] if change_info else None

    if country_code == "syria":
        if direction == "up":
            hooks = [
                f"📈 ارتفاع جديد في أسعار الذهب اليوم في سوريا ({today_str})! هل يستمر الصعود غداً؟ اكتب توقعك 👇",
                f"🔥 صعود جديد لغرام الذهب اليوم في دمشق وحلب ({today_str}) — هل الوقت مناسب للبيع أم الانتظار؟ 👇",
            ]
        elif direction == "down":
            hooks = [
                f"📉 تراجع جديد في أسعار الذهب اليوم في سوريا ({today_str})! هل تعتبر اليوم فرصة للشراء؟ شاركنا رأيك 👇",
                f"⬇️ انخفاض غرام الذهب اليوم في دمشق وحلب ({today_str}) — احفظ الفيديو للرجوع إليه عند الشراء 🔖",
            ]
        else:
            hooks = [
                f"📊 كم وصل سعر عيار 21 اليوم في سوريا ({today_str})؟ شاهد التحديث الكامل واكتب توقعك لغداً 👇",
                f"✨ أسعار الذهب اليوم في دمشق وحلب ({today_str}) بالليرة السورية الجديدة — احفظ الفيديو 🔖",
                f"🔔 حركة أسعار الذهب والأونصة اليوم في سوريا ({today_str}) — هل تتوقع صعوداً أم هبوطاً غداً؟ 👇",
            ]
        tags_pool = [
            "#ذهب #أسعار_الذهب #سوريا #دمشق #حلب #الليرة_السورية #عيار_21 #اكسبلور",
            "#سعر_الذهب_في_سوريا #ذهب_سوريا #اسعار_الذهب #دمشق #سوريا #اقتصاد #فوريو",
            "#اسعار_الذهب_اليوم #سوريا #الليرة_السورية #عيار_21 #عيار_24 #ذهب #gold",
        ]
    else:
        if direction == "up":
            hooks = [
                f"📈 ارتفاع جديد في أسعار الذهب اليوم في تركيا ({today_str})! هل يستمر الصعود غداً أم يتراجع؟ اكتب توقعك 👇",
                f"🔥 صعود جديد لغرام الذهب اليوم في إسطنبول وتركيا ({today_str}) — هل الوقت مناسب للبيع أم الانتظار؟ 👇",
            ]
        elif direction == "down":
            hooks = [
                f"📉 تراجع جديد في أسعار الذهب اليوم في تركيا ({today_str})! هل اليوم فرصة للشراء أم ننتظر أكثر؟ 👇",
                f"⬇️ انخفاض غرام الذهب اليوم في إسطنبول وتركيا ({today_str}) — احفظ الفيديو للرجوع إليه عند الشراء 🔖",
            ]
        else:
            hooks = [
                f"📊 كم وصل سعر عيار 21 اليوم في تركيا ({today_str})؟ شاهد التحديث الكامل واكتب توقعك لغداً 👇",
                f"✨ أسعار غرام الذهب اليوم في إسطنبول وتركيا ({today_str}) — احفظ الفيديو للرجوع إليه عند الشراء 🔖",
                f"🔔 حركة أسعار الذهب والأونصة اليوم في تركيا ({today_str}) — هل تتوقع صعوداً أم هبوطاً غداً؟ 👇",
            ]
        tags_pool = [
            "#ذهب #أسعار_الذهب #تركيا #اسطنبول #الليرة_التركية #عيار_21 #اكسبلور",
            "#سعر_الذهب_في_تركيا #اسعار_الذهب #تركيا #اسطنبول #اقتصاد #فوريو #gold",
            "#اسعار_الذهب_اليوم #تركيا #عيار_21 #عيار_24 #الليرة_التركية #ذهب #اكسبلور",
        ]

    hook = hooks[ordinal % len(hooks)]
    tags = tags_pool[(ordinal + (1 if country_code == "syria" else 0)) % len(tags_pool)]
    return f"{hook}\n{tags}"


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

    def replace_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        """تبديل المسار الصوتي لنسخة تيك توك في أقل من ثانية بدون إعادة رندرة الفيديو (-c:v copy)"""
        ffmpeg_bin = self.find_ffmpeg()
        cmd = [
            ffmpeg_bin, "-y", "-nostdin", "-loglevel", "error",
            "-i", str(video_path),
            "-stream_loop", "-1",
            "-i", str(audio_path),
            "-t", "15",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def assemble_tiktok_video_with_bg(
        self,
        frame_gen,
        prices: dict,
        audio_path: Path,
        output_path: Path,
        bg_video_path: Path,
        country_offset: int = 0,
        duration: float = 8.0,
        country_code: str = "turkey",
        prev_prices: dict | None = None,
    ) -> Path:
        """إنشاء نسخة تيك توك (8 ثوانٍ بتدرّج ذكي + شارة الفرق اليومي + خلفية فيديو متحركة)"""
        ffmpeg_bin = self.find_ffmpeg()
        eco_dir = TEMP_DIR / f"tt_bg_{output_path.stem}"
        eco_dir.mkdir(parents=True, exist_ok=True)

        title_ar = getattr(frame_gen, "tiktok_title", "أسعار الذهب")
        rows_data = frame_gen.get_rows_data(prices)

        step_files = []
        for step_num in range(5):
            overlay_img = render_glass_cards_overlay(
                title_ar=title_ar,
                prices=prices,
                rows_data=rows_data,
                get_font_fn=frame_gen.get_font,
                revealed_count=step_num + 1,
                width=1080,
                height=1920,
                country_code=country_code,
                prev_prices=prev_prices,
            )
            step_path = eco_dir / f"step_{step_num}.png"
            overlay_img.save(str(step_path), "PNG", compress_level=1)
            step_files.append(step_path)

        # ظهور تدريجي أنيق خلال أول 2.90 ثانية (عيار 21 يظهر عند 1.30s والأونصة عند 2.90s ثم ثبات 5.10s)
        concat_file = eco_dir / "overlay_concat.txt"
        lines = [
            f"file '{step_files[0].as_posix()}'", "duration 0.65",
            f"file '{step_files[1].as_posix()}'", "duration 0.65",
            f"file '{step_files[2].as_posix()}'", "duration 0.85",
            f"file '{step_files[3].as_posix()}'", "duration 0.75",
            f"file '{step_files[4].as_posix()}'", f"duration {max(1.0, duration - 2.90):.2f}",
            f"file '{step_files[4].as_posix()}'",
        ]
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # تنويع بصري خفيف لكل يوم/دولة لمنع تطابق بصمة الفيديو عند تكرار الخلفيات
        seed = date.today().toordinal() + country_offset
        cycle = (date.today().toordinal() * 2 + country_offset) // max(1, len(list(TIKTOK_BG_DIR.glob("*.mp4"))))
        allow_hflip = ("bars" not in bg_video_path.name.lower()) and (cycle % 2 == 1)
        speed_factors = [1.0, 0.94, 1.06, 0.97, 1.03]
        pts_factor = speed_factors[seed % len(speed_factors)]
        hue_shifts = [0, -6, 6, -4, 4]
        hue_deg = hue_shifts[seed % len(hue_shifts)]

        bg_filters = [
            "scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
            f"setpts={pts_factor:.2f}*PTS",
            f"hue=h={hue_deg}:s=1.05",
        ]
        if "bars" not in bg_video_path.name.lower():
            bg_filters.append("eq=brightness=0.05:contrast=1.08:saturation=1.12")
        if allow_hflip:
            bg_filters.append("hflip")
        bg_filters.append(f"fps={self.fps}")
        bg_filters.append("format=rgba")

        # تخطي المقدمة الداكنة في molten_gold ليبدأ المقطع وصورة الغلاف بإضاءة ذهبية ساطعة منذ الإطار الأول
        bg_seek = ["-ss", "5.0"] if "molten" in bg_video_path.name.lower() else []

        # نقطة ضوئية ذهبية تنساب بنعومة أسفل الشارة التفاعلية طوال مدة الفيديو لإبقاء كل إطار حياً
        dur_str = f"{duration:.1f}"
        filter_complex = (
            f"[0:v]{','.join(bg_filters)}[bg];"
            f"[1:v]fps={self.fps},format=rgba[ov];"
            f"[bg][ov]overlay=0:0:shortest=1[comp];"
            f"color=c=0xFFD700:s=80x5,format=rgba[glow];"
            f"[comp][glow]overlay=x='95+(810*t/{dur_str})':y=1512:shortest=1,format=yuv420p[vout]"
        )

        cmd = [
            ffmpeg_bin, "-y", "-nostdin", "-loglevel", "error",
            "-stream_loop", "-1", *bg_seek, "-i", str(bg_video_path),
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-stream_loop", "-1", "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "2:a:0",
            "-t", f"{duration:.2f}",
            "-fps_mode", "cfr",
            "-c:v", "libx264",
            "-crf", "22",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        for f in eco_dir.glob("*"):
            f.unlink(missing_ok=True)
        eco_dir.rmdir()
        return output_path


def prepare_tiktok_video(
    config: dict,
    assembler: VideoAssembler,
    audio_mgr: AudioManager,
    frame_gen,
    base_video_path: Path,
    prices: dict,
    country_code: str,
    duration: float = 15.0,
) -> tuple[Path, str]:
    """تجهيز نسخة فيديو تيك توك (8 ثوانٍ بتدرّج ذكي + شارة الفرق عن الأمس + وصف تشويقي تفاعلي) بدون المساس بيوتيوب"""
    tt_cfg = config.get("tiktok", {})
    tt_duration = float(tt_cfg.get("duration", 8.0))
    prev_prices = load_previous_day_prices(country_code, expected_source=prices.get("source"))
    if not prev_prices and prices.get("prev_21k"):
        prev_prices = {"21k": prices["prev_21k"]}
    tt_audio = audio_mgr.get_tiktok_audio_path() or audio_mgr.get_audio_path(tt_duration, TEMP_DIR)
    tt_out = base_video_path.with_name(f"{base_video_path.stem}_tiktok.mp4")
    caption = build_tiktok_caption(country_code, prices, prev_prices=prev_prices)

    bg_files = sorted(TIKTOK_BG_DIR.glob("*.mp4")) if TIKTOK_BG_DIR.exists() else []
    use_video_bg = tt_cfg.get("video_background", True) and len(bg_files) > 0

    if use_video_bg:
        country_offset = 1 if country_code == "syria" else 0
        bg_idx = (date.today().toordinal() * 2 + country_offset) % len(bg_files)
        chosen_bg = bg_files[bg_idx]
        logger.info(
            f"🎬 تجهيز نسخة تيك توك ({tt_duration:.0f} ثوانٍ | خلفية {chosen_bg.name} | مقارنة الأمس={'نعم' if prev_prices else 'لا'})..."
        )
        assembler.assemble_tiktok_video_with_bg(
            frame_gen=frame_gen,
            prices=prices,
            audio_path=tt_audio,
            output_path=tt_out,
            bg_video_path=chosen_bg,
            country_offset=country_offset,
            duration=tt_duration,
            country_code=country_code,
            prev_prices=prev_prices,
        )
        return tt_out, caption

    if audio_mgr.get_tiktok_audio_path():
        assembler.replace_audio(base_video_path, tt_audio, tt_out)
        logger.info(f"🎵 تم دمج أنشودة تيك توك الخاصة ({tt_audio.name}) في: {tt_out.name}")
        return tt_out, caption

    return base_video_path, caption


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

    def publish_video(
        self,
        video_path: Path,
        prices: dict,
        platform: str = "all",
        yt_url: str = None,
        tg_msg_id: int = None,
    ) -> dict:
        """إدارة النشر التلقائي إلى يوتيوب وفيسبوك وتيك توك وتيليجرام مع دعم فصل المنصات"""
        today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))
        results = {
            "youtube": False,
            "youtube_url": yt_url,
            "facebook": False,
            "tiktok": False,
            "tiktok_url": None,
            "telegram": False,
            "telegram_msg_id": tg_msg_id,
        }

        # 1. يوتيوب
        yt_cfg = self.config.get("youtube", {})
        if platform in ("all", "youtube") and yt_cfg.get("auto_upload", False):
            try:
                title = yt_cfg.get("title_template", "أسعار الذهب اليوم في تركيا {date} ₺ #shorts").format(date=today_str)
                privacy = yt_cfg.get("privacy_status", "public")
                uploaded_yt = self.yt_uploader.upload_video(video_path, title=title, privacy_status=privacy)
                if uploaded_yt:
                    logger.info(f"✅ تم النشر التلقائي على YouTube: {uploaded_yt}")
                    results["youtube"] = True
                    results["youtube_url"] = uploaded_yt
            except FileNotFoundError as e:
                logger.warning(f"⚠️ تنبيه يوتيوب: {e}")
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى يوتيوب: {e}")

        # 2. فيسبوك
        fb_cfg = self.config.get("facebook", {})
        if platform in ("all", "facebook") and fb_cfg.get("auto_upload", False):
            try:
                fb_uploader = FacebookUploader(SCRIPT_DIR)
                fb_url = fb_uploader.upload_video(video_path)
                if fb_url:
                    logger.info(f"✅ تم النشر التلقائي على Facebook: {fb_url}")
                    results["facebook"] = True
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى فيسبوك: {e}")

        # 3. تيك توك
        tt_cfg = self.config.get("tiktok", {})
        if platform in ("all", "tiktok") and tt_cfg.get("auto_upload", False):
            try:
                tt_video_path, tt_desc = prepare_tiktok_video(
                    config=self.config,
                    assembler=self.assembler,
                    audio_mgr=self.audio_mgr,
                    frame_gen=self.frame_gen,
                    base_video_path=video_path,
                    prices=prices,
                    country_code="turkey",
                    duration=self.duration,
                )
                tt_method = (tt_cfg.get("upload_method") or "playwright").strip().lower()
                if tt_method == "buffer":
                    buf_uploader = BufferTikTokUploader()
                    thumb_ms = int(tt_cfg.get("thumbnail_offset_ms", 4500))
                    tt_url = buf_uploader.upload_video(tt_video_path, description=tt_desc, thumbnail_offset_ms=thumb_ms)
                else:
                    tt_uploader = TikTokUploader(SCRIPT_DIR)
                    tt_url = tt_uploader.upload_video(tt_video_path, description=tt_desc)
                if tt_url:
                    logger.info(f"✅ تم النشر التلقائي على TikTok ({tt_method}): {tt_url}")
                    results["tiktok"] = True
                    results["tiktok_url"] = tt_url
            except Exception as e:
                logger.error(f"❌ خطأ أثناء رفع الفيديو إلى تيك توك: {e}")

        # 4. قناة تيليجرام العامة (تُنشر مع جولة يوتيوب المباشرة وتُحدّث تلقائياً برابط تيك توك فور نشره)
        tg_cfg = self.config.get("telegram", {})
        if tg_cfg.get("auto_upload", False):
            tg = TelegramPublisher(self.config)
            if tg.is_configured():
                try:
                    if platform in ("all", "youtube", "telegram") and not results["telegram_msg_id"]:
                        card_path = None
                        send_video = None
                        if tg.post_mode != "text_only":
                            card_path = TEMP_DIR / "turkey_tg_card.png"
                            total_frames = int(self.fps * self.duration)
                            self.frame_gen.render_frame(prices, total_frames - 1, total_frames).save(str(card_path), "PNG")
                            if tg.post_mode == "media_group" and video_path.exists():
                                send_video = video_path
                        msg_id = tg.publish_gold_update(
                            country_code="turkey",
                            prices=prices,
                            photo_path=card_path,
                            video_path=send_video,
                            yt_url=results["youtube_url"],
                            tt_url=results["tiktok_url"],
                            duration=int(self.duration),
                        )
                        if card_path:
                            card_path.unlink(missing_ok=True)
                        if msg_id:
                            results["telegram"] = True
                            results["telegram_msg_id"] = msg_id
                    elif platform == "tiktok" and results["tiktok"] and results["telegram_msg_id"]:
                        if tg.update_caption_with_links(
                            message_id=results["telegram_msg_id"],
                            country_code="turkey",
                            prices=prices,
                            yt_url=results["youtube_url"],
                            tt_url=results["tiktok_url"],
                        ):
                            results["telegram"] = True
                except Exception as e:
                    logger.error(f"❌ خطأ أثناء النشر/التحديث على تيليجرام: {e}")

        return results

    def run(self, platform: str = "all", yt_url: str = None, tg_msg_id: int = None) -> dict:
        logger.info(f"🚀 بدء إنتاج فيديو الذهب اليومي (تركيا | platform={platform})...")

        # 1. جلب الأسعار
        prices = self.fetcher.fetch_turkey_prices()
        logger.info(f"الأسعار الحية: {prices}")

        today_code = date.today().strftime("%Y%m%d")
        output_file = OUTPUT_DIR / f"gold_price_{today_code}.mp4"

        tt_cfg = self.config.get("tiktok", {})
        has_bg = TIKTOK_BG_DIR.exists() and any(TIKTOK_BG_DIR.glob("*.mp4"))
        skip_base_render = (platform == "tiktok") and tt_cfg.get("video_background", True) and has_bg

        if not skip_base_render:
            audio_path = self.audio_mgr.get_audio_path(self.duration, TEMP_DIR)
            total_frames = int(self.fps * self.duration)
            logger.info(f"⚡ جاري إنتاج الفيديو الأساسي ({total_frames} إطاراً) بوضع توفير الطاقة القصوى (Eco Single-Core)...")
            final_path = self.assembler.assemble_ultra_light(
                self.frame_gen, prices, total_frames, audio_path, output_file
            )
            logger.info(f"🎉 تم إنشاء الفيديو بنجاح: {final_path}")
        else:
            final_path = output_file

        pub_res = self.publish_video(final_path, prices, platform=platform, yt_url=yt_url, tg_msg_id=tg_msg_id)
        return {"video": str(final_path), "results": pub_res, "prices": prices}


if __name__ == "__main__":
    plat = "all"
    if "--platform" in sys.argv:
        idx = sys.argv.index("--platform")
        if idx + 1 < len(sys.argv):
            plat = sys.argv[idx + 1].strip().lower()
    engine = FixedGoldShortsEngine()
    engine.run(platform=plat)
