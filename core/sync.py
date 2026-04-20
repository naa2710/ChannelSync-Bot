import os
import asyncio
from datetime import datetime
from config import get_data_path, settings_manager
from core.logger import get_logger

logger = get_logger("SYNC")

# الملفات التي نريد الحفاظ عليها
FILES_TO_SYNC = ["settings.json", "index.db"]

async def upload_backups(client):
    """رفع الملفات المهمة إلى الرسائل المحفوظة كنسخة احتياطية."""
    logger.info("جاري بدء عملية النسخ الاحتياطي السحابي...")
    for filename in FILES_TO_SYNC:
        # نحصل على المسار الفعلي (سواء كان في /data أو المجلد الحالي)
        path = get_data_path(filename)
        if os.path.exists(path):
            try:
                # نرفع الملف إلى Saved Messages (me)
                await client.send_document(
                    "me",
                    path,
                    caption=f"📦 Backup: {filename}\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    file_name=f"backup_{filename}"
                )
                logger.info(f"✅ تم رفع {filename} بنجاح إلى تلجرام.")
            except Exception as e:
                logger.error(f"❌ فشل رفع {filename}: {e}")
        else:
            logger.warning(f"⚠️ الملف {filename} غير موجود محلياً لتجاوزه.")

async def restore_backups(client):
    """البحث عن أحدث نسخة احتياطية في الرسائل المحفوظة وتحميلها."""
    logger.info("جاري فحص لوحة النقل لاستعادة البيانات المفقودة...")
    
    restored_files = set()
    
    try:
        async for message in client.get_chat_history("me", limit=100):
            if message.document and message.caption and "Backup:" in message.caption:
                # استخراج اسم الملف من التعليق
                filename = message.caption.split("Backup:")[1].split("\n")[0].strip()
                
                if filename in FILES_TO_SYNC and filename not in restored_files:
                    target_path = get_data_path(filename)
                    
                    # لا نستعيد الملف إلا إذا لم يكن موجوداً (لضمان عدم الكتابة فوق بيانات أحدث)
                    if not os.path.exists(target_path):
                        logger.info(f"📥 عثرت على نسخة احتياطية لـ {filename}، جاري التحميل...")
                        await client.download_media(message, file_name=target_path)
                        restored_files.add(filename)
                    else:
                        # إذا كان موجوداً نعتبره "تم تأمينه" ولا نحتاج لاستعادته من تلجرام
                        restored_files.add(filename)
                
                # إذا استعدنا كل شيء نتوقف
                if len(restored_files) >= len(FILES_TO_SYNC):
                    break
                    
    except Exception as e:
        logger.error(f"❌ خطأ أثناء محاولة الاستعادة: {e}")

    if restored_files:
        logger.info(f"✅ اكتملت عملية المزمنة. تم تأمين {len(restored_files)} ملفات.")
        return True
    
    logger.info("ℹ️ لم يتم العثور على نسخ احتياطية سابقة أو الملفات موجودة بالفعل.")
    return False

# للتحكم في وتيرة الرفع التلقائي
_lock = asyncio.Lock()
_last_sync = 0

async def safe_sync_backup(client):
    """تنفيذ النسخ الاحتياطي بأمان وبدون تكرار مفرط."""
    global _last_sync
    import time
    
    async with _lock:
        now = time.time()
        # السماح بالرفع مرة كل 5 دقائق على الأكثر لتجنب الـ Flood
        if now - _last_sync > 300:
            await upload_backups(client)
            _last_sync = now
