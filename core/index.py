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

from core.db import get_unindexed_files, mark_as_indexed, get_files_count, get_tag_group_stats

# قفل لضمان عدم حدوث تداخل أثناء معالجة الفهرس
index_lock = asyncio.Lock()

def get_file_icon(file_type: str) -> str:
    """إرجاع أيقونة مناسبة لنوع الملف."""
    icons = {
        "document": "📄",
        "video": "🎬",
        "photo": "🖼",
        "audio": "🎵",
        "voice": "🎤",
        "text": "📝"
    }
    return icons.get(file_type, "📁")

async def generate_master_hub(client: Client, target_chat_id: int):
    """توليد أو تحديث رسالة بوابة الملاحة المركزية."""
    stats = get_tag_group_stats()
    count = get_files_count()
    
    hub_text = "📚 **بوابة الفهرسة الشاملة للمكتبة** 📚\n"
    hub_text += "━━━━━━━━━━━━━━━━━━\n"
    hub_text += f"📊 إجمالي الملفات المؤرشفة: `{count}`\n\n"
    hub_text += "📂 **الأقسام المتاحة (اضغط للانتقال):**\n"
    
    for tag, c in stats:
        # الهاشتاقات تعمل كروابط بحث تلقائية في تليجرام
        hub_text += f"├ {tag} (`{c}` ملف)\n"
    
    hub_text += "━━━━━━━━━━━━━━━━━━\n"
    hub_text += "🔍 استخدم الهاشتاقات أعلاه للبحث السريع عن أي قسم."
    
    hub_msg_id = settings_manager.get("INDEX_HUB_MESSAGE_ID")
    
    try:
        if hub_msg_id:
            try:
                await client.edit_message_text(target_chat_id, hub_msg_id, hub_text)
                return
            except Exception:
                # إذا فشل التعديل (مثلا الرسالة محذوفة)، سننشر واحدة جديدة
                pass
        
        sent = await client.send_message(target_chat_id, hub_text)
        settings_manager.set("INDEX_HUB_MESSAGE_ID", sent.id)
        # تثبيت الرسالة للأهمية
        await sent.pin(disable_notification=True)
    except Exception as e:
        logger.error(f"Error updating Master Hub: {e}")

async def process_indexing(client: Client, target_chat_id: int):
    """المحرك المتقدم: يقوم بنشر فهارس مبوبة وتحديث بوابة الملاحة."""
    if not settings_manager.get("ENABLE_INDEXING"):
        return
        
    async with index_lock:
        unindexed_files = get_unindexed_files()
        threshold = int(settings_manager.get("INDEX_THRESHOLD") or 50)
        
        if len(unindexed_files) >= threshold:
            logger.info(f"🔰 جاري بناء فهرس متطور لـ {len(unindexed_files)} ملف...")
            
            try:
                chat = await client.get_chat(target_chat_id)
                username = chat.username
            except Exception:
                username = None
            
            # 1. تصنيف الملفات
            categories = {}
            for file in unindexed_files:
                tag = file['tag'] or "#نشر_عام"
                if tag not in categories:
                    categories[tag] = []
                categories[tag].append(file)
            
            per_category = settings_manager.get("INDEX_PER_CATEGORY")
            
            # 2. توليد ونشر الرسائل
            if per_category:
                for tag, files in categories.items():
                    chunks = split_index_into_chunks(files, tag, target_chat_id, username)
                    for chunk_text in chunks:
                        await client.send_message(target_chat_id, chunk_text, disable_web_page_preview=True)
            else:
                # الحفاظ على النمط القديم (رسالة واحدة مجمعة) ولكن بتنسيق الأيقونات الجديد
                all_files = unindexed_files
                chunks = split_index_into_chunks(all_files, "الفهرس الدوري", target_chat_id, username)
                for chunk_text in chunks:
                    await client.send_message(target_chat_id, chunk_text, disable_web_page_preview=True)
            
            # 3. تحديث البيانات والـ Hub
            file_ids = [f['id'] for f in unindexed_files]
            mark_as_indexed(file_ids)
            await generate_master_hub(client, target_chat_id)
            logger.info("✅ تم إكمال الفهرسة المتقدمة وتحديث البوابة.")

def split_index_into_chunks(files, title, chat_id, username):
    """تقسيم الفهرس لقطع صغيرة لتجنب تجاوز حد الـ 4000 حرف."""
    chunks = []
    current_chunk = f"📚 **{title}**\n━━━━━━━━━━━━━━\n"
    
    for i, file in enumerate(files, 1):
        link = build_msg_link(chat_id, file['msg_id'], username)
        icon = get_file_icon(file.get('file_type'))
        
        name = re.sub(r'\.[^.]+$', '', file['name'])
        if len(name) > 45: name = name[:42] + "..."
        
        line = f"{i}. {icon} [{name}]({link})\n"
        
        if len(current_chunk) + len(line) > 3900:
            chunks.append(current_chunk + "\n(يتبع...)")
            current_chunk = f"📚 **{title} (تابع)**\n━━━━━━━━━━━━━━\n" + line
        else:
            current_chunk += line
            
    chunks.append(current_chunk)
    return chunks



