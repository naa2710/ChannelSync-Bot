from pyrogram import Client, enums
from pyrogram.types import Message
from html import escape
import re
import os
import asyncio

from config import settings_manager
from core.retry import with_retry
from core.logger import get_logger
from core.index import process_indexing
from core.db import add_file_to_db
from core.group_index import update_single_category, update_stats_message
from core.categorizer import categorize_by_name, make_file_hashtag

logger = get_logger("USERBOT")

def detect_category(file_name: str, file_type: str) -> str:
    """تحديد الفئة بشكل ذكي — يستخدم categorizer أولاً ثم file_type كبديل."""
    # أولوية 1: تصنيف ذكي بناءً على اسم الملف
    smart_cat = categorize_by_name(file_name)
    if smart_cat:
        return smart_cat
    # أولوية 2: الامتداد
    if file_name:
        ext = os.path.splitext(file_name)[1].lower().strip('.')
        if ext in ['pdf', 'epub', 'docx', 'doc', 'txt', 'xlsx', 'pptx', 'odt']:
            return '📚 الكتب والمراجع'
        if ext in ['mp4', 'mkv', 'mov', 'avi', 'wmv']:
            return '🎥 ملفات فيديو'
        if ext in ['mp3', 'wav', 'ogg', 'm4a', 'aac']:
            return '🎵 الصوتيات'
        if ext in ['apk', 'exe', 'dmg', 'ipa']:
            return '📱 البرمجيات'
        if ext in ['zip', 'rar', '7z', 'tar', 'gz']:
            return '📦 الأرشيف'
    # أولوية 3: نوع الملف
    if file_type == 'photo':    return '📸 الصور'
    if file_type == 'video':    return '🎥 ملفات فيديو'
    if file_type == 'audio':    return '🎵 الصوتيات'
    if file_type == 'text':     return '📝 النصوص'
    return '📄 أخرى'

def extract_hashtags(message: Message, file_name: str = None) -> str:
    """استخراج تصنيف (هاشتاج) احترافي من اسم الملف أو نص الرسالة."""
    if file_name:
        # استبدال كافة المسافات والرموز والنقاط بشرطة سفلية لضمان عمل الهاشتاج
        # تليجرام يدعم الحروف العربية واللاتينية والأرقام والشرطة السفلية في الهاشتاج
        clean_name = re.sub(r'[\s\.\-\(\)\[\]\{\}]+', '_', file_name).strip('_')
        
        if len(clean_name) > 1:
            return f"#{clean_name}"

    # إذا لم يفلح ذلك، نبحث في النص عن هاشتاق موجود بالفعل
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


def is_valid_message_type(message: Message, chat_id: int) -> bool:
    """التحقق من توافق الرسالة مع الأنواع المسموحة في إعدادات المصدر."""
    # 1. النصوص
    if message.text:
        return settings_manager.get_for_source(chat_id, "ALLOW_TEXT") and len(message.text) > 10
    
    # 2. الصور
    if message.photo:
        return settings_manager.get_for_source(chat_id, "ALLOW_PHOTO")
    
    # 3. المستندات والملفات
    if message.document:
        return settings_manager.get_for_source(chat_id, "ALLOW_DOCUMENT")
    
    # 4. الفيديوهات
    if message.video or message.video_note:
        return settings_manager.get_for_source(chat_id, "ALLOW_VIDEO")
    
    # 5. البصمات الصوتية
    if message.voice:
        return settings_manager.get_for_source(chat_id, "ALLOW_VOICE")
    
    # 6. الملفات الصوتية Music
    if message.audio:
        return settings_manager.get_for_source(chat_id, "ALLOW_AUDIO")
    
    # 7. الصور المتحركة GIF
    if message.animation:
        return settings_manager.get_for_source(chat_id, "ALLOW_ANIMATION")
    
    # 8. الكابشن الطويل للميديا
    if message.caption and len(message.caption) > 10:
        return True

    return False

def clean_text(text: str) -> str:
    """تنظيف النص من الروابط والمنشورات الدعائية."""
    if not text:
        return ""
    # حذف الروابط (http/https)
    text = re.sub(r'https?://\S+', '', text)
    # حذف معرفات التليجرام (@username)
    text = re.sub(r'@\w+', '', text)
    # حذف المسافات الزائدة
    text = re.sub(r'\n\s*\n', '\n', text).strip()
    return text

def build_header(message: Message, chat_id: int) -> str:
    sender_name = message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "") if message.from_user else "غير معروف"
    source_name = message.chat.title or str(message.chat.id)

    header_text = settings_manager.get_for_source(chat_id, "HEADER_TEXT")
    source_label = settings_manager.get_for_source(chat_id, "SOURCE_LABEL") or "المصدر"
    sender_label = settings_manager.get_for_source(chat_id, "SENDER_LABEL") or "المرسل"
    
    original_caption = message.caption or ""
    original_text = message.text or ""
    original_note = original_caption or original_text

    # تنظيف الكابشن إذا كان مفعلاً لهذا المصدر
    if settings_manager.get_for_source(chat_id, "DEFAULT_CLEAN_CAPTION"):
        original_note = clean_text(original_note)

    hide_source = settings_manager.get_for_source(chat_id, "HIDE_SOURCE_NAME")

    parts = [
        f"<b>{escape(header_text)}</b>",
    ]
    if not hide_source:
        parts.append(f"{escape(source_label)}: <b>{escape(source_name)}</b>")
        parts.append(f"{escape(sender_label)}: <b>{escape(sender_name)}</b>")
    if original_note.strip():
        parts.append(f"ملاحظة: {escape(original_note[:700])}")
    return "\n".join(parts)


async def send_header_if_needed(client: Client, message: Message, target_channel_id: int, source_chat_id: int):
    """إرسال الترويسة إذا كانت مفعلة."""
    if settings_manager.get_for_source(source_chat_id, "ADD_HEADER") and settings_manager.get_for_source(source_chat_id, "SEND_HEADER_AS_SEPARATE_MESSAGE"):
        header = build_header(message, source_chat_id)
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
    source_chat_id = message.chat.id
    target_channel_id = settings_manager.get_for_source(source_chat_id, "TARGET_CHANNEL_ID")
    if not target_channel_id:
        target_channel_id = settings_manager.get("TARGET_CHANNEL_ID")
    
    # 1. إرسال الهيدر
    await send_header_if_needed(client, message, target_channel_id, source_chat_id)
    
    # 2. تحضير معلومات الملف والوسم (قبل الإرسال)
    file_name = None
    file_type = "text"
    file_size = None
    
    if message.document:
        file_name = message.document.file_name
        file_size = message.document.file_size
        file_type = "document"
    elif message.video:
        file_name = message.video.file_name or f"video_{message.id}"
        file_size = message.video.file_size
        file_type = "video"
    elif message.audio:
        file_name = message.audio.title or message.audio.file_name
        file_size = message.audio.file_size
        file_type = "audio"
    elif message.photo:
        file_name = f"photo_{message.id}"
        file_type = "photo"

    # الهاشتاج يُولَّد فقط للملفات (documents)
    file_hashtag = make_file_hashtag(file_name) if (file_name and file_type == "document") else ""
    category = detect_category(file_name, file_type)
    
    # 3. تحضير الكابشن (بدون إلحاق الهاشتاج — سيُرسل منفصلاً)
    caption = message.caption or ""
    if settings_manager.get_for_source(source_chat_id, "DEFAULT_CLEAN_CAPTION"):
        caption = clean_text(caption)
    # لا نُلحق الهاشتاج بالكابشن — يُرسل كرسالة ردّ منفصلة تحت الملف

    # 4. النقل (Copy/Forward)
    sent_msg = None
    try:
        copy_mode = settings_manager.get_for_source(source_chat_id, "USE_COPY_INSTEAD_OF_FORWARD")
        if copy_mode:
            sent_msg = await with_retry(message.copy, chat_id=target_channel_id, caption=caption if caption else None)
        else:
            sent_msg = await with_retry(message.forward, chat_id=target_channel_id)
            # إذا كان Forward ولا يمكننا تعديل الكابشن مباشرة، والهاشتاج مطلوب في رسالة منفصلة
            if tag and settings_manager.get_for_source(source_chat_id, "APPEND_TAG_TO_CAPTION"):
                await client.send_message(target_channel_id, tag, reply_to_message_id=sent_msg.id)

    except Exception as e:
        error_str = str(e)
        if "CHAT_FORWARDS_RESTRICTED" in error_str or "restricted" in error_str.lower() or "can't be forwarded" in error_str.lower():
            logger.warning(f"تم اكتشاف حماية القناة للرسالة {message.id}. جاري التخطي بالتحميل اليدوي...")
            if message.media:
                file_path = await with_retry(message.download)
                if file_path:
                    try:
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
                text = clean_text(message.text) if settings_manager.get_for_source(source_chat_id, "DEFAULT_CLEAN_CAPTION") else message.text
                sent_msg = await with_retry(client.send_message, chat_id=target_channel_id, text=text)
        else:
            error_str = str(e)
            if "PEER_ID_INVALID" in error_str or "Could not find any entity" in error_str:
                logger.error(f"❌ خطأ فادح: اليوزربوت لا يملك صلاحية الوصول لقناة الوجهة ({target_channel_id}). يجب أن يكون الحساب عضواً فيها.")
            else:
                logger.error(f"فشل النقل (عذر غير الحماية): {e}")

    # 5. نظام الفهرسة التلقائي (للملفات فقط)
    if sent_msg and file_type == "document":
        # تسجيل في قاعدة البيانات
        add_file_to_db(
            name=file_name or "بدون اسم",
            tag=file_hashtag,
            source=message.chat.title or "Unknown",
            msg_id=sent_msg.id,
            file_size=file_size,
            file_type=file_type,
            caption=caption,
            category=category
        )

        # إرسال الهاشتاج كرسالة ردّ تحت الملف مباشرة
        if file_hashtag:
            try:
                await asyncio.sleep(0.5)  # تأخير بسيط لضمان استقبال الملف
                await client.send_message(
                    chat_id=target_channel_id,
                    text=file_hashtag,
                    reply_to_message_id=sent_msg.id,
                    disable_notification=True,
                    disable_web_page_preview=True,
                )
            except Exception as ht_err:
                logger.warning(f"فشل إرسال الهاشتاج: {ht_err}")

        # تحديث فهرس القناة
        if settings_manager.get_for_source(source_chat_id, "ENABLE_INDEXING"):
            await process_indexing(client, target_channel_id)

        # تحديث فهرس المجموعة التفاعلية (خلفية)
        if settings_manager.get("INDEX_GROUP_ID") and settings_manager.get("GROUP_AUTO_UPDATE"):
            asyncio.create_task(update_single_category(client, category))
            from core.db import get_files_count
            if get_files_count() % 10 == 0:
                asyncio.create_task(update_stats_message(client))

    elif sent_msg and file_type not in ("document",):
        # للصور والفيديوهات والنصوص: نقل فقط بدون فهرسة
        logger.info(f"تم نقل [{file_type}] بدون فهرسة: {message.id}")

    return sent_msg


async def transfer_last_n_files(client: Client, chat_id: int, limit: int = 5):
    """وظيفة جديدة لنقل آخر N رسائل من مصدر معين."""
    logger.info(f"بدء البحث عن آخر {limit} ملفات في المصدر {chat_id}")
    count = 0
    from core.dedup import dedup_manager
    
    try:
        # البحث عن الرسائل الأخيرة في القناة
        async for msg in client.get_chat_history(chat_id, limit=150):
            if count >= limit:
                break
                
            if is_valid_message_type(msg, chat_id) and message_has_required_hashtag(msg.text, msg.caption):
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
