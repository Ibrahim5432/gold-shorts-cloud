#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة النشر التلقائي إلى قناة تيليجرام العامة عبر Telegram Bot API الرسمي
ترسل صورة جدول الأسعار + الفيديو (15 ثانية) في منشور واحد أنيق مع الأسعار النصية
وروابط يوتيوب وتيك توك، مع دعم تحديث الرابط تلقائياً عند اكتمال رفع تيك توك.
"""

import os
import json
import logging
from datetime import date
from pathlib import Path
import requests

logger = logging.getLogger("TelegramPublisher")


class TelegramPublisher:
    def __init__(self, config: dict = None, bot_token: str = None, channel_id: str = None):
        self.config = config or {}
        tg_cfg = self.config.get("telegram", {})
        self.bot_token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.channel_id = (
            channel_id
            or os.environ.get("TELEGRAM_CHANNEL_ID", "")
            or tg_cfg.get("channel_id", "")
        ).strip()
        self.tiktok_profile_url = (tg_cfg.get("tiktok_profile_url") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.channel_id)

    def _api(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def build_caption(
        self,
        country_code: str,
        prices: dict,
        yt_url: str = None,
        tt_url: str = None,
    ) -> str:
        """بناء نص منسق بصيغة HTML يحتوي على جدول الأسعار وروابط يوتيوب وتيك توك"""
        today_str = prices.get("date", date.today().strftime("%Y/%m/%d"))
        ounce_usd = f"{prices.get('ounce_usd', 0):,.2f} $"

        if country_code == "syria":
            title = f"✨ <b>أسعار الذهب اليوم في سوريا — {today_str}</b>"
            p24 = f"{int(round(prices.get('24k', 0))):,} ل.س"
            p22 = f"{int(round(prices.get('22k', 0))):,} ل.س"
            p21 = f"{int(round(prices.get('21k', 0))):,} ل.س"
            p18 = f"{int(round(prices.get('18k', 0))):,} ل.س"
            tags = "#أسعار_الذهب #سوريا #دمشق #حلب #الليرة_السورية #ذهب"
        else:
            title = f"✨ <b>أسعار الذهب اليوم في تركيا — {today_str}</b>"
            p24 = f"{prices.get('24k', 0):,.2f} ₺"
            p22 = f"{prices.get('22k', 0):,.2f} ₺"
            p21 = f"{prices.get('21k', 0):,.2f} ₺"
            p18 = f"{prices.get('18k', 0):,.2f} ₺"
            tags = "#أسعار_الذهب #تركيا #اسطنبول #الليرة_التركية #ذهب"

        lines = [
            title,
            "",
            f"🟡 <b>عيار 24:</b> <code>{p24}</code>",
            f"🟡 <b>عيار 22:</b> <code>{p22}</code>",
            f"🟡 <b>عيار 21:</b> <code>{p21}</code>",
            f"🟡 <b>عيار 18:</b> <code>{p18}</code>",
            f"🌍 <b>سعر الأونصة:</b> <code>{ounce_usd}</code>",
        ]

        link_lines = []
        if yt_url and yt_url.startswith("http"):
            link_lines.append(f"▶️ <b>يوتيوب:</b> {yt_url}")
        final_tt = tt_url if (tt_url and "/video/" in tt_url) else (tt_url if (tt_url and "/@" in tt_url) else self.tiktok_profile_url)
        if final_tt and final_tt.startswith("http"):
            link_lines.append(f"🎵 <b>تيك توك:</b> {final_tt}")

        if link_lines:
            lines.append("")
            lines.extend(link_lines)

        ch_handle = self.channel_id if self.channel_id.startswith("@") else "@as3aral"
        lines.extend([
            "",
            f"📢 تحديث يومي فوري: {ch_handle}",
            tags,
        ])
        return "\n".join(lines)

    def publish_gold_update(
        self,
        country_code: str,
        prices: dict,
        photo_path: Path = None,
        video_path: Path = None,
        yt_url: str = None,
        tt_url: str = None,
        duration: int = 15,
    ) -> int | None:
        """نشر الصورة والفيديو معاً في منشور واحد (Media Group) مع جدول الأسعار والروابط"""
        if not self.is_configured():
            logger.warning("⚠️ بيانات بوت تيليجرام غير مضبوطة — تم تخطي النشر على تيليجرام.")
            return None

        caption = self.build_caption(country_code, prices, yt_url=yt_url, tt_url=tt_url)
        has_photo = bool(photo_path and Path(photo_path).exists())
        has_video = bool(video_path and Path(video_path).exists())

        try:
            if has_photo and has_video:
                media = [
                    {
                        "type": "photo",
                        "media": "attach://photo",
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    {
                        "type": "video",
                        "media": "attach://video",
                        "width": 1080,
                        "height": 1920,
                        "duration": int(duration),
                        "supports_streaming": True,
                    },
                ]
                with open(photo_path, "rb") as fp, open(video_path, "rb") as fv:
                    r = requests.post(
                        self._api("sendMediaGroup"),
                        data={
                            "chat_id": self.channel_id,
                            "media": json.dumps(media, ensure_ascii=False),
                        },
                        files={
                            "photo": (Path(photo_path).name, fp, "image/png"),
                            "video": (Path(video_path).name, fv, "video/mp4"),
                        },
                        timeout=120,
                    )
                data = r.json()
                if data.get("ok") and data.get("result"):
                    msg_id = data["result"][0].get("message_id")
                    logger.info(f"✅ تم النشر على قناة تيليجرام ({self.channel_id}) [صورة + فيديو] | message_id={msg_id}")
                    return msg_id
                logger.error(f"❌ فشل sendMediaGroup على تيليجرام: {data}")
                return None

            if has_video:
                with open(video_path, "rb") as fv:
                    r = requests.post(
                        self._api("sendVideo"),
                        data={
                            "chat_id": self.channel_id,
                            "caption": caption,
                            "parse_mode": "HTML",
                            "width": 1080,
                            "height": 1920,
                            "duration": int(duration),
                            "supports_streaming": True,
                        },
                        files={"video": (Path(video_path).name, fv, "video/mp4")},
                        timeout=120,
                    )
                data = r.json()
                if data.get("ok"):
                    msg_id = data["result"].get("message_id")
                    logger.info(f"✅ تم نشر الفيديو على قناة تيليجرام ({self.channel_id}) | message_id={msg_id}")
                    return msg_id
                logger.error(f"❌ فشل sendVideo على تيليجرام: {data}")
                return None

            if has_photo:
                with open(photo_path, "rb") as fp:
                    r = requests.post(
                        self._api("sendPhoto"),
                        data={
                            "chat_id": self.channel_id,
                            "caption": caption,
                            "parse_mode": "HTML",
                        },
                        files={"photo": (Path(photo_path).name, fp, "image/png")},
                        timeout=60,
                    )
                data = r.json()
                if data.get("ok"):
                    msg_id = data["result"].get("message_id")
                    logger.info(f"✅ تم نشر الصورة على قناة تيليجرام ({self.channel_id}) | message_id={msg_id}")
                    return msg_id
                logger.error(f"❌ فشل sendPhoto على تيليجرام: {data}")
                return None

            r = requests.post(
                self._api("sendMessage"),
                json={
                    "chat_id": self.channel_id,
                    "text": caption,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=30,
            )
            data = r.json()
            if data.get("ok"):
                msg_id = data["result"].get("message_id")
                logger.info(f"✅ تم نشر الرسالة على قناة تيليجرام ({self.channel_id}) | message_id={msg_id}")
                return msg_id
            logger.error(f"❌ فشل sendMessage على تيليجرام: {data}")
            return None
        except Exception as e:
            logger.error(f"❌ خطأ أثناء النشر على تيليجرام: {e}")
            return None

    def update_caption_with_links(
        self,
        message_id: int,
        country_code: str,
        prices: dict,
        yt_url: str = None,
        tt_url: str = None,
    ) -> bool:
        """تحديث وصف منشور تيليجرام المنشور مسبقاً لإضافة رابط فيديو تيك توك المباشر بدون إرسال منشور ثانٍ"""
        if not self.is_configured() or not message_id:
            return False
        caption = self.build_caption(country_code, prices, yt_url=yt_url, tt_url=tt_url)
        try:
            r = requests.post(
                self._api("editMessageCaption"),
                json={
                    "chat_id": self.channel_id,
                    "message_id": int(message_id),
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                timeout=30,
            )
            data = r.json()
            if data.get("ok"):
                logger.info(f"✅ تم تحديث منشور تيليجرام ({message_id}) بالرابط الجديد بنجاح!")
                return True
            if "message is not modified" in str(data.get("description", "")).lower():
                return True
            logger.warning(f"⚠️ تنبيه أثناء تحديث وصف تيليجرام ({message_id}): {data}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ تعذر تحديث وصف تيليجرام: {e}")
            return False
