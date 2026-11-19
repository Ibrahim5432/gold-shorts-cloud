#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
المنسق اليومي الذكي الموحد (تركيا 12:00 ظهراً + سوريا 01:00 ظهراً)
- يمنع تشغيل المهمتين في نفس اللحظة نهائياً (يمنع تعارض المتصفح أو ملفات الفيديو)
- يعوض النشر تلقائياً وبالتتابع (تركيا أولاً ثم سوريا) فور فتح الجهاز بعد العودة من العمل
- يحفظ سجل النشر اليومي في published_history.json لعدم تكرار النشر في نفس اليوم
"""

import os
import sys
import json
import time
import msvcrt
import logging
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

from make_gold_short import SCRIPT_DIR, FixedGoldShortsEngine
from make_syria_gold_short import SyriaGoldShortsEngine

logger = logging.getLogger("DailyOrchestrator")
HISTORY_FILE = SCRIPT_DIR / "published_history.json"
LOCK_FILE = SCRIPT_DIR / "daily_runner.lock"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_history(data: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _bool_status(today_status: dict, key: str, legacy_key: str) -> bool:
    if key in today_status:
        return bool(today_status.get(key, False))
    return bool(today_status.get(legacy_key, False))


def main():
    force = "--force" in sys.argv
    platform = "all"
    if "--platform" in sys.argv:
        idx = sys.argv.index("--platform")
        if idx + 1 < len(sys.argv):
            platform = sys.argv[idx + 1].strip().lower()

    now = datetime.now()
    today_key = date.today().strftime("%Y-%m-%d")

    history = load_history()
    today_status = history.get(today_key, {})

    tr_yt_done = _bool_status(today_status, "turkey_yt", "turkey")
    tr_tt_done = _bool_status(today_status, "turkey_tt", "turkey")
    sy_yt_done = _bool_status(today_status, "syria_yt", "syria")
    sy_tt_done = _bool_status(today_status, "syria_tt", "syria")

    run_yt = platform in ("all", "youtube")
    run_tt = platform in ("all", "tiktok")

    need_turkey = (run_yt and (force or (now.hour >= 12 and not tr_yt_done))) or (
        run_tt and (force or (now.hour >= 12 and not tr_tt_done))
    )
    need_syria = (run_yt and (force or (now.hour >= 13 and not sy_yt_done))) or (
        run_tt and (force or (now.hour >= 13 and not sy_tt_done))
    )

    if not need_turkey and not need_syria:
        return

    # قفل ملف التشغيل لمنع أي تداخل بين المهام المجدولة
    lock_fp = open(LOCK_FILE, "w")
    try:
        msvcrt.locking(lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        logger.info("⏳ هناك عملية نشر جارية بالفعل في الخلفية؛ تم تجاهل التشغيل المزدوج.")
        lock_fp.close()
        return

    try:
        # إعادة قراءة السجل بعد الحصول على القفل
        history = load_history()
        today_status = history.get(today_key, {})
        tr_yt_done = _bool_status(today_status, "turkey_yt", "turkey")
        tr_tt_done = _bool_status(today_status, "turkey_tt", "turkey")
        sy_yt_done = _bool_status(today_status, "syria_yt", "syria")
        sy_tt_done = _bool_status(today_status, "syria_tt", "syria")

        # 1. فيديو أسعار الذهب في تركيا (الساعة 12:00 ظهراً أو تعويض بعد الظهر)
        want_tr_yt = run_yt and (force or (now.hour >= 12 and not tr_yt_done))
        want_tr_tt = run_tt and (force or (now.hour >= 12 and not tr_tt_done))
        if want_tr_yt or want_tr_tt:
            tr_plat = "all" if (want_tr_yt and want_tr_tt) else ("youtube" if want_tr_yt else "tiktok")
            logger.info("=" * 60)
            logger.info(f"🇹🇷 بدء مهمة فيديو أسعار الذهب في تركيا ليوم {today_key} (platform={tr_plat})")
            logger.info("=" * 60)
            try:
                tr_engine = FixedGoldShortsEngine()
                res = tr_engine.run(platform=tr_plat)
                pub = res.get("results", {}) if isinstance(res, dict) else {}
                if want_tr_yt and pub.get("youtube"):
                    today_status["turkey_yt"] = True
                    today_status["turkey_yt_time"] = datetime.now().strftime("%H:%M:%S")
                if want_tr_tt and pub.get("tiktok"):
                    today_status["turkey_tt"] = True
                    today_status["turkey_tt_time"] = datetime.now().strftime("%H:%M:%S")
                today_status["turkey_yt"] = bool(today_status.get("turkey_yt", tr_yt_done))
                today_status["turkey_tt"] = bool(today_status.get("turkey_tt", tr_tt_done))
                today_status["turkey"] = bool(today_status["turkey_yt"] and today_status["turkey_tt"])
                today_status["turkey_time"] = datetime.now().strftime("%H:%M:%S")
                history[today_key] = today_status
                save_history(history)
                logger.info(f"✅ حالة تركيا المحدثة: YT={today_status['turkey_yt']} | TT={today_status['turkey_tt']}")
                time.sleep(12 if want_tr_tt else 5)
            except Exception as e:
                logger.error(f"❌ خطأ في مهمة تركيا: {e}")

        # 2. فيديو أسعار الذهب في سوريا (الساعة 01:00 ظهراً أو تعويض بعد الظهر)
        now = datetime.now()
        want_sy_yt = run_yt and (force or (now.hour >= 13 and not sy_yt_done))
        want_sy_tt = run_tt and (force or (now.hour >= 13 and not sy_tt_done))
        if want_sy_yt or want_sy_tt:
            sy_plat = "all" if (want_sy_yt and want_sy_tt) else ("youtube" if want_sy_yt else "tiktok")
            logger.info("=" * 60)
            logger.info(f"🇸🇾 بدء مهمة فيديو أسعار الذهب في سوريا ليوم {today_key} (platform={sy_plat})")
            logger.info("=" * 60)
            try:
                sy_engine = SyriaGoldShortsEngine()
                res = sy_engine.run(platform=sy_plat)
                pub = res.get("results", {}) if isinstance(res, dict) else {}
                if want_sy_yt and pub.get("youtube"):
                    today_status["syria_yt"] = True
                    today_status["syria_yt_time"] = datetime.now().strftime("%H:%M:%S")
                if want_sy_tt and pub.get("tiktok"):
                    today_status["syria_tt"] = True
                    today_status["syria_tt_time"] = datetime.now().strftime("%H:%M:%S")
                today_status["syria_yt"] = bool(today_status.get("syria_yt", sy_yt_done))
                today_status["syria_tt"] = bool(today_status.get("syria_tt", sy_tt_done))
                today_status["syria"] = bool(today_status["syria_yt"] and today_status["syria_tt"])
                today_status["syria_time"] = datetime.now().strftime("%H:%M:%S")
                history[today_key] = today_status
                save_history(history)
                logger.info(f"✅ حالة سوريا المحدثة: YT={today_status['syria_yt']} | TT={today_status['syria_tt']}")
            except Exception as e:
                logger.error(f"❌ خطأ في مهمة سوريا: {e}")

    finally:
        try:
            msvcrt.locking(lock_fp.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        lock_fp.close()


if __name__ == "__main__":
    main()
