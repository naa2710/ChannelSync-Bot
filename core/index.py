import asyncio
import re
from pyrogram import Client
from config import settings_manager
from core.logger import get_logger

logger = get_logger("INDEX")

def build_msg_link(chat_id: int, message_id: int, username: str = None) -> str:
    """توليد رابط الرسالة المباشر."""
    if username:
        return f"https://t.me/{username}/{message_id}"
    
    # للقنوات الخاصة، نحويل المعرف -100123... إلى 123...
    clean_id = str(chat_id).replace("-100", "")
    return f"https://t.me/c/{clean_id}/{message_id}"

async def add_to_index(source_name: str, file_name: str, msg_id: int, tag: str = None):
    """إضافة ملف جديد مع الهاشتاج الخاص به."""
    if not settings_manager.get("ENABLE_INDEXING"):
        return
        
    items = settings_manager.get("PENDING_INDEX_ITEMS") or []
    items.append({
        "source": source_name,
        "name": file_name,
        "msg_id": msg_id,
        "tag": tag or "نشر عام"
    })
    settings_manager.set("PENDING_INDEX_ITEMS", items)
    logger.info(f"تمت إضافة ملف للفهرس: {file_name} [#] {tag}")

# قفل لضمان عدم حدوث تداخل أثناء معالجة الفهرس
index_lock = asyncio.Lock()

from core.db import get_unindexed_files, mark_as_indexed, get_files_count

# قفل لضمان عدم حدوث تداخل أثناء معالجة الفهرس
index_lock = asyncio.Lock()

async def process_indexing(client: Client, target_chat_id: int):
    """المحرك الاحترافي: يقوم بجمع الملفات غير المفهرسة من القاعدة وتصنيفها."""
    if not settings_manager.get("ENABLE_INDEXING"):
        return
        
    async with index_lock:
        # جلب الملفات التي لم تفهرس بعد
        unindexed_files = get_unindexed_files()
        threshold = int(settings_manager.get("INDEX_THRESHOLD") or 50)
        
        if len(unindexed_files) >= threshold:
            logger.info(f"🔰 جاري بناء فهرس احترافي لـ {len(unindexed_files)} ملف...")
            
            # جلب معلومات القناة للروابط
            try:
                chat = await client.get_chat(target_chat_id)
                username = chat.username
            except Exception:
                username = None
            
            # 1. تصنيف الملفات في قاموس (Groups) بناءً على التاق
            categories = {}
            for file in unindexed_files:
                tag = file['tag'] or "#نشر_عام"
                if tag not in categories:
                    categories[tag] = []
                categories[tag].append(file)
            
            # 2. بناء نص الفهرس بتنسيق جمالي
            index_text = "📚 **الفهرس الدوري للمكتبة الرقمية** 📚\n"
            index_text += f"━━━━━━━━━━━━━━━━━━\n"
            index_text += f"📊 إجمالي الملفات في هذه الدفعة: `{len(unindexed_files)}`\n"
            
            for tag, files in categories.items():
                index_text += f"\n📂 **قسم: {tag}**\n"
                for i, file in enumerate(files, 1):
                    link = build_msg_link(target_chat_id, file['msg_id'], username)
                    # تنظيف الاسم للعرض (حذف الامتداد)
                    display_name = re.sub(r'\.[^.]+$', '', file['name'])
                    if len(display_name) > 40: display_name = display_name[:37] + "..."
                    
                    index_text += f"{i}. [{display_name}]({link})\n"
            
            index_text += f"\n━━━━━━━━━━━━━━━━━━\n"
            index_text += f"🔎 استخدم البحث في القناة للوصول السريع."
            
            # 3. إرسال الفهرس وتحديث حالة الملفات في القاعدة
            try:
                await client.send_message(target_chat_id, index_text, disable_web_page_preview=True)
                
                # تحديث قاعدة البيانات
                file_ids = [f['id'] for f in unindexed_files]
                mark_as_indexed(file_ids)
                
                logger.info("✅ تم نشر الفهرس الاحترافي وتحديث قاعدة البيانات.")
            except Exception as e:
                logger.error(f"❌ فشل نشر الفهرس الاحترافي: {e}")



