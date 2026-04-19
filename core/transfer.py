from pyrogram import Client, enums
from pyrogram.types import Message
from html import escape
import re

from config import settings_manager
from core.retry import with_retry
from core.logger import get_logger
from core.index import add_to_index, process_indexing
from core.db import add_file_to_db

logger = get_logger("USERBOT")

def extract_hashtags(message: Message, file_name: str = None) -> str:
    """استخراج تصنيف (هاشتاج) ذكي من اسم الملف أو نص الرسالة."""
    # إذا كان هناك اسم ملف، فهو الأهم للتصنيف الاحترافي
    if file_name:
        # تنظيف الاسم من الامتدادات والرموز
        clean_name = re.sub(r'\.(pdf|docx|zip|mp4|mp3|png|jpg|jpeg|rar|xlsx)$', '', file_name, flags=re.IGNORECASE)
        clean_name = clean_name.replace('_', ' ').replace('-', ' ').strip()
        
        # أخذ أول كلمة مفتاحية كـ تاق (بشرط أن تكون أكثر من حرفين)
        words = clean_name.split()
        if words and len(words[0]) > 2:
            return f"#{words[0]}"

    # إذا لم يفلح ذلك، نبحث في النص
    text = message.text or ""
    caption = message.caption or ""
    combined = f"{text}\n{caption}"
    tags = re.findall(r"(#\w+)", combined)
    
    if tags:
        return tags[0]
        
    return "#نشر_عام"

def message_has_required_hashtag(text: str | None, caption: str | None) -> bool:
    if not settings_manager.get("REQUIRE_HASHTAG"):
        return True
    combined = f"{text or ''}\n{caption or ''}"
    return settings_manager.get("REQUIRED_HASHTAG") in combined

def is_blacklisted(message: Message) -> bool:
    """التحقق مما إذا كانت الرسالة تحتوي على كلمات محظورة."""
    blacklist = settings_manager.get("BLACKLIST_WORDS") or []
    if not blacklist:
        return False
        
    # النصوص التي سنفحصها: (النص الأساسي، الشرح، اسم الملف)
    check_texts = [
        message.text or "",
        message.caption or "",
    ]
    
    if message.document and message.document.file_name:
        check_texts.append(message.document.file_name)
    
    for word in blacklist:
        word_lower = word.lower()
        for text in check_texts:
            if word_lower in text.lower():
                return True
    return False


def is_valid_message_type(message: Message) -> bool:
    """التحقق من توافق الرسالة مع الأنواع المسموحة في الإعدادات."""
    # 1. النصوص (بشرط الطول > 100 كما تم الاتفاق سابقا)
    if message.text:
        return settings_manager.get("ALLOW_TEXT") and len(message.text) > 100
    
    # 2. الصور
    if message.photo:
        return settings_manager.get("ALLOW_PHOTO")
    
    # 3. المستندات والملفات
    if message.document:
        return settings_manager.get("ALLOW_DOCUMENT")
    
    # 4. الفيديوهات
    if message.video or message.video_note:
        return settings_manager.get("ALLOW_VIDEO")
    
    # 5. البصمات الصوتية
    if message.voice:
        return settings_manager.get("ALLOW_VOICE")
    
    # 6. الملفات الصوتية Music
    if message.audio:
        return settings_manager.get("ALLOW_AUDIO")
    
    # 7. الصور المتحركة GIF
    if message.animation:
        return settings_manager.get("ALLOW_ANIMATION")
    
    # 8. الكابشن الطويل للميديا (إذا لم يتم التعرف على الميديا كنوع منفصل)
    if message.caption and len(message.caption) > 100:
        return True

    return False

def build_header(message: Message) -> str:
    sender_name = message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "") if message.from_user else "غير معروف"
    source_name = message.chat.title or str(message.chat.id)

    header_text = settings_manager.get("HEADER_TEXT")
    source_label = settings_manager.get("SOURCE_LABEL") or "المصدر"
    sender_label = settings_manager.get("SENDER_LABEL") or "المرسل"
    
    original_caption = message.caption or ""
    original_text = message.text or ""
    original_note = original_caption or original_text

    parts = [
        f"<b>{escape(header_text)}</b>",
        f"{escape(source_label)}: <b>{escape(source_name)}</b>",
        f"{escape(sender_label)}: <b>{escape(sender_name)}</b>",
    ]
    if original_note.strip():
        # Split logic in case note is extremely long (to avoid header failure)
        parts.append(f"ملاحظة: {escape(original_note[:700])}")
    return "\n".join(parts)


async def send_header_if_needed(client: Client, message: Message, target_channel_id: int):
    """إرسال الترويسة إذا كانت مفعلة."""
    if settings_manager.get("ADD_HEADER") and settings_manager.get("SEND_HEADER_AS_SEPARATE_MESSAGE"):
        header = build_header(message)
        await with_retry(
            client.send_message,
            chat_id=target_channel_id,
            text=header,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

import os
import asyncio

async def transfer_message(client: Client, message: Message):
    """المنطق الأساسي والوحيد لنقل الرسائل أو نسخها."""
    target_channel_id = settings_manager.get("TARGET_CHANNEL_ID")
    
    # 1. إرسال الهيدر
    await send_header_if_needed(client, message, target_channel_id)
    
    # 2. النقل (Copy/Forward)
    sent_msg = None
    try:
        if settings_manager.get("USE_COPY_INSTEAD_OF_FORWARD"):
            sent_msg = await with_retry(message.copy, chat_id=target_channel_id)
        else:
            sent_msg = await with_retry(message.forward, chat_id=target_channel_id)

    except Exception as e:
        error_str = str(e)
        if "CHAT_FORWARDS_RESTRICTED" in error_str or "restricted" in error_str.lower() or "can't be forwarded" in error_str.lower():
            logger.warning(f"تم اكتشاف حماية القناة للرسالة {message.id}. جاري التخطي بالتحميل اليدوي...")
            if message.media:
                file_path = await with_retry(message.download)
                if file_path:
                    try:
                        caption = message.caption or ""
                        if message.photo:
                            sent_msg = await with_retry(client.send_photo, chat_id=target_channel_id, photo=file_path, caption=caption)
                        elif message.video:
                            sent_msg = await with_retry(client.send_video, chat_id=target_channel_id, video=file_path, caption=caption)
                        elif message.document:
                            sent_msg = await with_retry(client.send_document, chat_id=target_channel_id, document=file_path, caption=caption)
                        elif message.audio:
                            sent_msg = await with_retry(client.send_audio, chat_id=target_channel_id, audio=file_path, caption=caption)
                        elif message.voice:
                            sent_msg = await with_retry(client.send_voice, chat_id=target_channel_id, voice=file_path, caption=caption)
                        elif message.animation:
                            sent_msg = await with_retry(client.send_animation, chat_id=target_channel_id, animation=file_path, caption=caption)
                    except Exception as upload_err:
                        logger.error(f"فشل الرفع اليدوي: {upload_err}")
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
            elif message.text:
                sent_msg = await with_retry(client.send_message, chat_id=target_channel_id, text=message.text)
        else:
            logger.error(f"فشل النقل (عذر غير الحماية): {e}")

    # 3. نظام الفهرسة التلقائي والوسم الذكي (Professional Indexing)
    if sent_msg:
        file_name = None
        if message.document: file_name = message.document.file_name
        elif message.video: file_name = f"فيديو: {message.video.file_name or message.id}"
        elif message.audio: file_name = message.audio.title or message.audio.file_name
        
        if file_name:
            tag = extract_hashtags(message, file_name)
            
            # إضافة الهاشتاج لكابشن الرسالة المنقولة لجعلها قابلة للبحث المباشر
            # البروغرام لا يدعم تعديل الكابشن بسهولة بعد النقل بالنسخ في بعض الحالات، 
            # لذا سنكتفي بالأرشفة في الفهرس المجمع حالياً لضمان استقرار النقل، 
            # أو يمكننا المحاولة إذا كان النص متاحاً.
            
            # تسجيل في قاعدة البيانات
            add_file_to_db(file_name, tag, message.chat.title or "Unknown", sent_msg.id)
            
            # تحديث الفهرس المجمع
            await process_indexing(client, target_channel_id)
            
    return sent_msg


async def transfer_last_n_files(client: Client, chat_id: int, limit: int = 5):
    """وظيفة جديدة لنقل آخر N رسائل من مصدر معين."""
    logger.info(f"بدء البحث عن آخر {limit} ملفات في المصدر {chat_id}")
    count = 0
    from core.dedup import dedup_manager
    
    try:
        # Search for recent messages in the group/channel
        async for msg in client.get_chat_history(chat_id, limit=50):
            if count >= limit:
                break
                
            if is_valid_message_type(msg) and message_has_required_hashtag(msg.text, msg.caption):
                # فحص القائمة السوداء
                if is_blacklisted(msg):
                    logger.info(f"تخطي رسالة محظورة (Blacklisted): {msg.id}")
                    continue

                if not dedup_manager.is_duplicate(chat_id, msg.id):
                    logger.info(f"نقل ملف متأخر من المصدر: {msg.id}")
                    try:
                        await transfer_message(client, msg)
                        dedup_manager.mark_processed(chat_id, msg.id)
                        count += 1
                        # تأخير بسيط بين كل رسالة وأخرى لتجنب الحظر
                        await asyncio.sleep(1.5) 
                    except Exception as e:
                        logger.error(f"خطأ أثناء تفريغ الرسالة {msg.id}: {e}")
                
        logger.info(f"تم إكمال نقل {count} ملفات جديدة من {chat_id}.")
    except Exception as e:
        logger.error(f"حدث خطأ أثناء نقل الملفات المتأخرة من {chat_id}: {e}")
