#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة الرفع التلقائي إلى YouTube Shorts
YouTube Shorts Automatic Uploader using YouTube Data API v3
"""

import os
import sys
import logging
from pathlib import Path
from datetime import date

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("YouTubeUploader")

# الصلاحيات المطلوبة للرفع
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.secrets_file = project_dir / "client_secrets.json"
        self.token_file = project_dir / "youtube_token.json"

    def get_authenticated_service(self, interactive: bool = False):
        """الحصول على جلسة معتمدة للرفع، مع التجديد التلقائي للرمز (Token)"""
        creds = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as e:
                logger.warning(f"تعذر قراءة ملف الرمز القديم: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("تجديد تصريح الدخول لليوتيوب تلقائياً في الخلفية...")
                creds.refresh(Request())
            else:
                if not self.secrets_file.exists():
                    raise FileNotFoundError(
                        f"لم يتم العثور على ملف {self.secrets_file.name}!\n"
                        "يرجى تنزيله من Google Cloud Console ووضعه في مجلد المشروع."
                    )
                if not interactive:
                    raise RuntimeError(
                        "لم يتم ربط قناة اليوتيوب بعد (ملف youtube_token.json غير موجود). "
                        "يرجى تشغيل ملف connect_youtube.bat لمرة واحدة لتسجيل الدخول."
                    )
                logger.info("🌐 فتح المتصفح لتسجيل الدخول لأول مرة وربط قناتك...")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.secrets_file), SCOPES)
                creds = flow.run_local_server(port=8080, open_browser=True)

            # حفظ الرمز للاستخدام اليومي التلقائي
            with open(str(self.token_file), "w", encoding="utf-8") as token:
                token.write(creds.to_json())
                logger.info(f"✅ تم حفظ تصريح الدخول الدائم في: {self.token_file}")

        return build("youtube", "v3", credentials=creds)

    def upload_video(
        self,
        video_path: Path,
        title: str = None,
        description: str = None,
        tags: list = None,
        privacy_status: str = "public",
        interactive: bool = False,
    ) -> str:
        """رفع الفيديو إلى يوتيوب كـ Short"""
        if not video_path.exists():
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {video_path}")

        today_str = date.today().strftime("%Y/%m/%d")

        if not title:
            title = f"أسعار الذهب اليوم في تركيا {today_str} ₺ #shorts #gold"

        if not description:
            description = (
                f"أسعار الذهب اليوم في تركيا ({today_str}) لجميع العيارات (24، 22، 21، 18) وسعر الأونصة بالدولار.\n\n"
                "تحديث يومي فوري لأسعار الذهب.\n"
                "#ذهب #أسعار_الذهب #تركيا #اسعار_الذهب_في_تركيا #shorts #gold #goldprice"
            )

        if not tags:
            tags = [
                "ذهب", "اسعار الذهب", "أسعار الذهب اليوم", "تركيا",
                "اسعار الذهب في تركيا", "عيار 21", "عيار 24", "اونصة الذهب",
                "shorts", "gold", "gold price turkey"
            ]

        logger.info(f"🚀 بدء رفع الفيديو إلى يوتيوب: {video_path.name}")
        logger.info(f"العنوان: {title}")

        youtube = self.get_authenticated_service(interactive=interactive)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "22",
                "defaultLanguage": "ar",
                "defaultAudioLanguage": "ar",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=1024 * 1024 * 5,
            resumable=True
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"  تم رفع: {int(status.progress() * 100)}%...")

        video_id = response.get("id")
        video_url = f"https://youtube.com/shorts/{video_id}"
        logger.info(f"🎉 تم الرفع بنجاح! رابط الشورتس: {video_url}")
        return video_url


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    project_dir = Path(__file__).parent.resolve()
    uploader = YouTubeUploader(project_dir)

    print("=" * 60)
    print("🔗 ربط قناة اليوتيوب وتجربة الرفع التلقائي")
    print("=" * 60)

    try:
        # 1. المصادقة التفاعلية وحفظ youtube_token.json
        uploader.get_authenticated_service(interactive=True)
        print("\n✅ تم ربط قناتك بنجاح وحفظ الرمز الدائم (youtube_token.json)!")

        # 2. رفع أحدث فيديو كتجربة
        output_dir = project_dir / "output"
        videos = list(output_dir.glob("gold_price_*.mp4"))
        if videos:
            latest = sorted(videos)[-1]
            print(f"\n🚀 جاري رفع الفيديو التجريبي: {latest.name} ...")
            url = uploader.upload_video(latest, privacy_status="public", interactive=True)
            print(f"\n🎉 تم نشر الفيديو على قناتك بنجاح!\n🔗 الرابط: {url}")
        else:
            print("\nℹ️ لا يوجد فيديو حالياً في مجلد output، سيتم الرفع مع التشغيل القادم.")
    except Exception as e:
        print(f"\n❌ حدث خطأ: {e}")
        sys.exit(1)
