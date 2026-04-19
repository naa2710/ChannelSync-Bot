import subprocess
import sys
import time

from core.logger import get_logger

import psutil
import os

logger = get_logger("RUN")

def cleanup_zombies():
    """البحث عن عمليات البوت العالقة وقتلها لضمان عدم قفل قاعدة البيانات."""
    current_pid = os.getpid()
    logger.info("جاري فحص وتنظيف العمليات العالقة...")
    
    deleted_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # نحن نبحث عن عمليات python التي ليست العملية الحالية
            if proc.info['pid'] == current_pid:
                continue
                
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline') or []
                # إذا كانت العملية تشغل bot.py أو user_bot.py في هذا المجلد
                if any(script in ' '.join(cmdline) for script in ["bot.py", "user_bot.py", "run.py"]):
                    logger.info(f"إغلاق عملية عالقة: {proc.info['pid']}")
                    proc.kill()
                    deleted_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if deleted_count > 0:
        logger.info(f"تم تنظيف {deleted_count} عمليات عالقة بنجاح.")
        time.sleep(1)
    else:
        logger.info("لم يتم العثور على عمليات عالقة.")

def run_bots():
    cleanup_zombies()
    logger.info("جاري بدء تشغيل النظام الكامل الشامل (Launcher)...")
    
    # تعريف قواميس العمليات
    # نستخدم قاموس بدلاً من قائمة لتسهيل التعرف على العملية (bot أو userbot)
    scripts = {
        "bot.py": None,
        "user_bot.py": None
    }
    
    try:
        while True:
            for script, proc in scripts.items():
                # إذا كانت العملية لم تبدأ بعد، أو توقفت
                if proc is None or proc.poll() is not None:
                    if proc is not None:
                        logger.error(f"⚠️ العملية {script} (PID: {proc.pid}) توقفت! جاري إعادة التشغيل...")
                        time.sleep(2) # انتظار قليل قبل إعادة التشغيل
                    
                    logger.info(f"🚀 بدء تشغيل {script}...")
                    scripts[script] = subprocess.Popen([sys.executable, script])
            
            time.sleep(5) # فحص كل 5 ثوانٍ
            
    except KeyboardInterrupt:
        logger.info("\nجاري إغلاق جميع العمليات بأمان...")
        for proc in scripts.values():
            if proc:
                proc.terminate()
                proc.wait()
        logger.info("تم تفريغ النظام وإغلاقه.")

if __name__ == "__main__":
    run_bots()
