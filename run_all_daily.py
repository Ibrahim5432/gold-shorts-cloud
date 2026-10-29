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


def main():
    force = "--force" in sys.argv
    now = datetime.now()
    today_key = date.today().strftime("%Y-%m-%d")

    history = load_history()
    today_status = history.get(today_key, {"turkey": False, "syria": False})

    need_turkey = force or (now.hour >= 12 and not today_status.get("turkey", False))
    need_syria = force or (now.hour >= 13 and not today_status.get("syria", False))

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
        today_status = history.get(today_key, {"turkey": False, "syria": False})

        # 1. فيديو أسعار الذهب في تركيا (الساعة 12:00 ظهراً أو تعويض بعد الظهر)
        if force or (now.hour >= 12 and not today_status.get("turkey", False)):
            logger.info("=" * 60)
            logger.info(f"🇹🇷 بدء مهمة فيديو أسعار الذهب في تركيا ليوم {today_key}")
            logger.info("=" * 60)
            try:
                tr_engine = FixedGoldShortsEngine()
                tr_engine.run()
                today_status["turkey"] = True
                today_status["turkey_time"] = datetime.now().strftime("%H:%M:%S")
                history[today_key] = today_status
                save_history(history)
                logger.info("✅ اكتملت مهمة تركيا بنجاح وتم تسجيلها في السجل اليومي.")
                time.sleep(5)
            except Exception as e:
                logger.error(f"❌ خطأ في مهمة تركيا: {e}")

        # 2. فيديو أسعار الذهب في سوريا (الساعة 01:00 ظهراً أو تعويض بعد الظهر)
        now = datetime.now()
        if force or (now.hour >= 13 and not today_status.get("syria", False)):
            logger.info("=" * 60)
            logger.info(f"🇸🇾 بدء مهمة فيديو أسعار الذهب في سوريا ليوم {today_key}")
            logger.info("=" * 60)
            try:
                sy_engine = SyriaGoldShortsEngine()
                sy_engine.run()
                today_status["syria"] = True
                today_status["syria_time"] = datetime.now().strftime("%H:%M:%S")
                history[today_key] = today_status
                save_history(history)
                logger.info("✅ اكتملت مهمة سوريا بنجاح وتم تسجيلها في السجل اليومي.")
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
