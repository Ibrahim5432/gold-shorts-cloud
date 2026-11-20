#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة النشر التلقائي إلى تيك توك عبر Buffer Official GraphQL API
(شريك رسمي معتمد لدى تيك توك - بدون متصفح وبدون بروكسي هاتف)
"""

import os
import time
import logging
from pathlib import Path
import requests

logger = logging.getLogger("BufferUploader")

BUFFER_API_URL = "https://api.buffer.com"


class BufferTikTokUploader:
    def __init__(self, api_key: str = None, channel_id: str = None):
        self.api_key = (api_key or os.environ.get("BUFFER_API_KEY", "")).strip()
        self.channel_id = (channel_id or os.environ.get("BUFFER_TIKTOK_CHANNEL_ID", "")).strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _gql(self, query: str, variables: dict = None, timeout: int = 60) -> dict:
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        r = requests.post(BUFFER_API_URL, headers=self._headers(), json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def resolve_tiktok_channel_id(self) -> str | None:
        """التحقق من قناة تيك توك المربوطة في Buffer وجلب معرّفها تلقائياً عند الحاجة"""
        if self.channel_id:
            return self.channel_id
        if not self.api_key:
            return None
        try:
            r_org = self._gql("query { account { organizations { id } } }", timeout=20)
            orgs = r_org.get("data", {}).get("account", {}).get("organizations", [])
            for org in orgs:
                oid = org.get("id")
                if not oid:
                    continue
                r_ch = self._gql(
                    f'query {{ channels(input: {{ organizationId: "{oid}" }}) {{ id name service }} }}',
                    timeout=20,
                )
                for ch in r_ch.get("data", {}).get("channels", []):
                    if (ch.get("service") or "").lower() == "tiktok":
                        self.channel_id = ch["id"]
                        logger.info(f"🔗 تم اكتشاف قناة تيك توك في Buffer: {ch.get('name')} ({self.channel_id})")
                        return self.channel_id
        except Exception as e:
            logger.error(f"❌ تعذر جلب قناة تيك توك من Buffer: {e}")
        return None

    def _upload_temp_public_mp4(self, video_path: Path) -> str:
        """رفع ملف الفيديو مؤقتاً (1-3 ساعات) للحصول على رابط MP4 مباشر يسحبه Buffer"""
        errors = []

        # 1. uguu.se (رابط مباشر MP4 لمدة 3 ساعات - مُختبَر بنجاح مع Buffer)
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    "https://uguu.se/upload",
                    files={"files[]": (video_path.name, f, "video/mp4")},
                    timeout=120,
                )
            if r.status_code == 200:
                files_list = r.json().get("files", [])
                if files_list and files_list[0].get("url"):
                    url = files_list[0]["url"]
                    rh = requests.head(url, timeout=15)
                    if rh.status_code == 200:
                        logger.info(f"☁️ تم رفع الفيديو مؤقتاً إلى uguu.se لـ Buffer: {url}")
                        return url
            errors.append(f"uguu status={r.status_code}")
        except Exception as e:
            errors.append(f"uguu err={e}")

        # 2. litterbox.catbox.moe (احتياطي مباشر لمدة ساعة واحدة)
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    "https://litterbox.catbox.moe/resources/internals/api.php",
                    data={"reqtype": "fileupload", "time": "1h"},
                    files={"fileToUpload": (video_path.name, f, "video/mp4")},
                    timeout=120,
                )
            txt = r.text.strip()
            if r.status_code == 200 and txt.startswith("https://"):
                rh = requests.head(txt, timeout=15)
                if rh.status_code == 200:
                    logger.info(f"☁️ تم رفع الفيديو مؤقتاً إلى litterbox لـ Buffer: {txt}")
                    return txt
            errors.append(f"litterbox status={r.status_code}")
        except Exception as e:
            errors.append(f"litterbox err={e}")

        # 3. 0x0.st (احتياطي ثالث)
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    "https://0x0.st",
                    files={"file": (video_path.name, f, "video/mp4")},
                    headers={"User-Agent": "gold-shorts-publisher/1.0"},
                    timeout=120,
                )
            txt = r.text.strip()
            if r.status_code == 200 and txt.startswith("https://"):
                logger.info(f"☁️ تم رفع الفيديو مؤقتاً إلى 0x0.st لـ Buffer: {txt}")
                return txt
            errors.append(f"0x0 status={r.status_code}")
        except Exception as e:
            errors.append(f"0x0 err={e}")

        raise RuntimeError(f"فشل رفع الفيديو المؤقت لـ Buffer عبر جميع المضيفين: {'; '.join(errors)}")

    def upload_video(
        self,
        video_path: Path,
        description: str,
        thumbnail_offset_ms: int = 2000,
    ) -> str | None:
        """إرسال الفيديو للنشر الفوري على تيك توك عبر Buffer Official GraphQL API"""
        if not video_path.exists():
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {video_path}")
        if not self.is_configured():
            logger.error("❌ لم يتم ضبط BUFFER_API_KEY.")
            return None

        ch_id = self.resolve_tiktok_channel_id()
        if not ch_id:
            logger.error("❌ لم يتم العثور على قناة تيك توك مربوطة في Buffer.")
            return None

        public_url = self._upload_temp_public_mp4(video_path)

        mut = """
        mutation CreateTikTokPost($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess {
              post {
                id
                status
                externalLink
              }
            }
            ... on InvalidInputError { message }
            ... on UnauthorizedError { message }
            ... on LimitReachedError { message }
            ... on RestProxyError { message }
            ... on UnexpectedError { message }
          }
        }
        """
        variables = {
            "input": {
                "channelId": ch_id,
                "text": description,
                "schedulingType": "automatic",
                "mode": "shareNow",
                "needsApproval": False,
                "assets": [
                    {
                        "video": {
                            "url": public_url,
                            "metadata": {
                                "thumbnailOffset": int(thumbnail_offset_ms),
                            },
                        }
                    }
                ],
            }
        }

        resp = self._gql(mut, variables=variables, timeout=90)
        res = resp.get("data", {}).get("createPost", {})
        if res.get("__typename") != "PostActionSuccess":
            logger.error(f"❌ رفض Buffer طلب النشر: {res or resp}")
            return None

        post = res.get("post") or {}
        pid = post.get("id")
        logger.info(f"🚀 تم إرسال الفيديو إلى Buffer الرسمي (post_id={pid}) — جاري انتظار تأكيد النشر من تيك توك...")

        q_poll = """
        query CheckPost($input: PostInput!) {
          post(input: $input) {
            id
            status
            sentAt
            externalLink
            error { __typename }
          }
        }
        """
        for _ in range(20):
            time.sleep(6)
            try:
                rp = self._gql(q_poll, variables={"input": {"id": pid}}, timeout=20)
                pinfo = rp.get("data", {}).get("post") or {}
                st = (pinfo.get("status") or "").lower()
                ext = pinfo.get("externalLink")
                if st == "sent":
                    final_url = ext or "https://www.tiktok.com/@as3aral"
                    logger.info(f"🎉 اكتمل النشر عبر Buffer Official API بنجاح: {final_url}")
                    return final_url
                if st == "error" or pinfo.get("error"):
                    logger.error(f"❌ فشل النشر في Buffer بعد الإرسال: {pinfo}")
                    return None
            except Exception as e:
                logger.warning(f"تنبيه أثناء متابعة حالة منشور Buffer: {e}")

        logger.info("⏳ ما يزال المنشور قيد الإرسال في Buffer (تم قبوله ولن نعيد إرساله منعاً للتكرار).")
        return "https://www.tiktok.com/@as3aral"
