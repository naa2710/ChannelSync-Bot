import asyncio
from pyrogram.errors import FloodWait

async def with_retry(func, *args, **kwargs):
    """
    تقوم بتنفيذ أي دالة (مثل نقل الرسالة) وتعالج حظر التيليجرام المؤقت (FloodWait).
    إذا واجهت FloodWait، تنام للمدة المطلوبة وتكمل النقل لاحقاً.
    """
    from core.logger import get_logger
    logger = get_logger("USERBOT")

    max_retries = 10  # زيادة عدد المحاولات للتحمل أثناء ضغط المزامنة العالي
    retries = 0

    while retries < max_retries:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = e.value + 1
            logger.warning(f"⚠️ تليجرام أخبرنا بالانتظار (FloodWait): {wait_time} ثانية. سيعود النقل تلقائياً.")
            await asyncio.sleep(wait_time)
            retries += 1
        except Exception as e:
            raise e
    
    logger.error("تم الوصول للحد الأقصى من محاولات الانتظار.")
    raise Exception("Max retries reached due to FloodWait.")
